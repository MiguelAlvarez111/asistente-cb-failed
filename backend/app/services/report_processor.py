from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
import re
from time import perf_counter

import pandas as pd

from backend.app.core.config import Settings, get_settings
from backend.app.repositories.audit_repository import audit_repository
from backend.app.repositories.feedback_repository import feedback_repository
from backend.app.repositories.job_repository import JobRecord, job_repository
from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode
from backend.app.schemas.files import FileKind
from backend.app.schemas.jobs import JobStatus, JobSummary
from backend.app.schemas.results import RowDetail
from backend.app.services.ai_interpreter import AIInterpreter
from backend.app.services.column_normalizer import normalize_dataframe
from backend.app.services.correction_builder import CorrectionBuilder
from backend.app.services.correction_parser import parse_corrections
from backend.app.services.decision_engine import choose_final_action
from backend.app.services.deterministic_interpreter import interpret_row
from backend.app.services.dictionary_loader import DictionaryIndex, LoadedDictionary, load_dictionary
from backend.app.services.excel_exporter import OUTPUT_COLUMNS, write_processed_workbook
from backend.app.services.file_classifier import REPORT_REQUIRED
from backend.app.services.privacy_sanitizer import build_ai_payload, sanitize_row
from backend.app.services.validator import validate_interpretation


def _confidence_bucket(value: float) -> str:
    if value >= 0.9:
        return "high"
    if value >= 0.7:
        return "medium"
    return "low"


def _apply_output(row: dict[str, str], result: RowDetail) -> dict[str, str]:
    output = dict(row)
    for column in OUTPUT_COLUMNS:
        output[column] = str(getattr(result, column))
    return output


COMPACT_OPERATIONAL_VALUE_RE = re.compile(r"^[A-Za-z0-9_-]{2,16}$")
NPI_RE = re.compile(r"\b\d{10}\b")
TEXT_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
KNOWN_SOURCE_VALUES = {"", "dictionary", "usap", "npi registry", "usap / npi registry"}


def _correction_priority(interpretation: AIInterpretation | None) -> int:
    if interpretation is None:
        return -1
    if interpretation.action == AIAction.CHANGE_TICKET:
        return 3 if (interpretation.target_provider_name or interpretation.target_npi or interpretation.target_cbcode) else 0
    if interpretation.action == AIAction.COMPLETE_INFO:
        return 2 if (interpretation.target_npi or interpretation.target_cbcode) else 0
    if interpretation.action in {AIAction.ADD_TO_GE, AIAction.REMOVE_FROM_TICKET}:
        return 1
    return 0


def _is_concrete_correction(interpretation: AIInterpretation) -> bool:
    return _correction_priority(interpretation) >= 2


def _should_replace_correction(existing: AIInterpretation | None, incoming: AIInterpretation) -> bool:
    if existing is None:
        return True

    existing_priority = _correction_priority(existing)
    incoming_priority = _correction_priority(incoming)

    if incoming_priority > existing_priority:
        return True
    if incoming_priority < existing_priority:
        return False
    return True


def _merge_interpretation_targets(primary: AIInterpretation, fallback: AIInterpretation) -> AIInterpretation:
    updates: dict[str, object] = {}
    if not primary.target_provider_name and fallback.target_provider_name:
        updates["target_provider_name"] = fallback.target_provider_name
    if not primary.target_npi and fallback.target_npi:
        updates["target_npi"] = fallback.target_npi
    if not primary.target_cbcode and fallback.target_cbcode:
        updates["target_cbcode"] = fallback.target_cbcode
    if fallback.is_pending_usap and not primary.is_pending_usap:
        updates["is_pending_usap"] = True
    if fallback.requires_add_to_ge and primary.action == AIAction.ADD_TO_GE:
        updates["requires_add_to_ge"] = True
    return primary.model_copy(update=updates) if updates else primary


def _select_interpretation(deterministic: AIInterpretation, ai_interpretation: AIInterpretation, settings: Settings) -> AIInterpretation:
    if ai_interpretation.action == AIAction.MANUAL_REVIEW and not _is_concrete_correction(ai_interpretation):
        return deterministic
    if ai_interpretation.confidence < settings.ai_confidence_fallback_threshold:
        return deterministic

    deterministic_priority = _correction_priority(deterministic)
    ai_priority = _correction_priority(ai_interpretation)
    if ai_priority > deterministic_priority:
        return _merge_interpretation_targets(ai_interpretation, deterministic)
    if ai_priority < deterministic_priority:
        return deterministic
    if deterministic.confidence < 0.7 and ai_interpretation.confidence > deterministic.confidence:
        return _merge_interpretation_targets(ai_interpretation, deterministic)
    if ai_priority > 0 and ai_interpretation.confidence >= deterministic.confidence:
        return _merge_interpretation_targets(ai_interpretation, deterministic)
    return deterministic


def _correction_haystack(row: dict[str, str]) -> str:
    return " ".join(
        str(row.get(key, "") or "")
        for key in ["npi", "cbcode", "comments", "source"]
    ).lower()


def _looks_like_free_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if NPI_RE.search(text) and not re.fullmatch(r"\d{10}", text):
        return True
    if "\n" in text or "\t" in text:
        return True
    words = TEXT_WORD_RE.findall(text)
    if len(words) >= 3:
        return True
    return len(text) > 24 and not COMPACT_OPERATIONAL_VALUE_RE.fullmatch(text)


def _has_suspicious_operational_text(row: dict[str, str]) -> bool:
    npi = str(row.get("npi", "") or "").strip()
    cbcode = str(row.get("cbcode", "") or "").strip()
    comments = str(row.get("comments", "") or "").strip()
    source = str(row.get("source", "") or "").strip()

    if npi and not re.fullmatch(r"\d{10}(?:\s+\d{10})*", npi) and not re.match(r"^\s*chg\s+to\b", npi, re.IGNORECASE):
        if _looks_like_free_text(npi):
            return True
    if cbcode and not COMPACT_OPERATIONAL_VALUE_RE.fullmatch(cbcode) and _looks_like_free_text(cbcode):
        return True
    if comments and _looks_like_free_text(comments):
        return True
    if source and source.lower() not in KNOWN_SOURCE_VALUES and _looks_like_free_text(source):
        return True
    return False


def _has_change_intent(row: dict[str, str]) -> bool:
    haystack = _correction_haystack(row)
    return bool(
        re.search(r"\b(chg|change|correct|replace|switch)\b", haystack)
        and re.search(r"\b(to|ticket|provider|surgeon|npi|cb)\b", haystack)
    )


def _promote_free_text_change(row: dict[str, str], interpretation: AIInterpretation) -> AIInterpretation:
    if (
        interpretation.action == AIAction.COMPLETE_INFO
        and _has_change_intent(row)
        and (interpretation.target_npi or interpretation.target_cbcode or interpretation.target_provider_name)
    ):
        reason = AIReasonCode.CORRECT_PROVIDER_NPI if interpretation.target_npi else AIReasonCode.CORRECT_PROVIDER_CB
        return interpretation.model_copy(
            update={
                "action": AIAction.CHANGE_TICKET,
                "reason_code": reason,
                "is_pending_usap": bool(interpretation.target_npi and not interpretation.target_cbcode),
                "explanation": f"{interpretation.explanation} Interpreted as change-ticket correction from free-text change intent.",
            }
        )
    return interpretation


def _should_ai_review_correction(row: dict[str, str], deterministic: AIInterpretation) -> bool:
    if deterministic.action == AIAction.REMOVE_FROM_TICKET:
        return False
    if _has_suspicious_operational_text(row):
        return True
    if deterministic.confidence < 0.7:
        return True
    haystack = _correction_haystack(row)
    has_free_text = bool(str(row.get("comments", "") or "").strip())
    has_concrete_signal = any(
        signal in haystack
        for signal in [
            "chg to",
            "correct",
            "change in the ticket",
            "with npi",
            "with cb",
        ]
    )
    if deterministic.action in {AIAction.AWAITING_USAP, AIAction.UNKNOWN} and (has_free_text or has_concrete_signal):
        return True
    if deterministic.action == AIAction.ADD_TO_GE and has_concrete_signal:
        return True
    return False


class ReportProcessor:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.ai = AIInterpreter(self.settings)
        self.correction_builder = CorrectionBuilder()
        self._reset_ai_usage()

    def _reset_ai_usage(self) -> None:
        self._ai_usage_rows = 0
        self._ai_usage_tokens = 0
        self._ai_usage_models: set[str] = set()

    def _record_ai_usage(self, model_used: str | None, tokens: int) -> None:
        self._ai_usage_rows = getattr(self, "_ai_usage_rows", 0) + 1
        self._ai_usage_tokens = getattr(self, "_ai_usage_tokens", 0) + tokens
        if model_used:
            models = getattr(self, "_ai_usage_models", set())
            models.add(model_used)
            self._ai_usage_models = models

    def _interpret_correction_row(self, row: dict[str, str]) -> AIInterpretation:
        deterministic = interpret_row(row)
        settings = getattr(self, "settings", None)
        ai = getattr(self, "ai", None)
        if not settings or not ai or not settings.ai_enabled:
            return deterministic
        if getattr(self, "_ai_usage_rows", 0) >= settings.max_ai_rows_per_job:
            return deterministic
        if not _should_ai_review_correction(row, deterministic):
            return deterministic

        ai_interpretation, model_used, tokens = ai.interpret(build_ai_payload(row))
        ai_interpretation = _promote_free_text_change(row, ai_interpretation)
        self._record_ai_usage(model_used, tokens)
        return _select_interpretation(deterministic, ai_interpretation, settings)

    def process(self, job_id: str, upload_id: str) -> None:
        started = perf_counter()
        job_repository.update_job(job_id, status=JobStatus.PROCESSING, progress=0.05, message="Loading files")
        upload = job_repository.get_upload(upload_id)
        job = job_repository.get_job(job_id)
        if not upload or not job:
            return

        try:
            self._reset_ai_usage()
            dictionaries = self._load_dictionaries(upload.files)
            dictionary_index = DictionaryIndex(dictionaries)
            corrections = self._load_corrections(upload.files)
            report_files = [item for item in upload.files if item.inspection.kind == FileKind.CB_FAILED_REPORT]
            if not report_files:
                raise ValueError("No CB Failed report file detected.")

            rows: list[RowDetail] = []
            processed_sheets: dict[str, pd.DataFrame] = {}
            ai_rows = getattr(self, "_ai_usage_rows", 0)
            token_estimate = getattr(self, "_ai_usage_tokens", 0)
            models_used: set[str] = set(getattr(self, "_ai_usage_models", set()))
            row_count = sum(item.inspection.row_count for item in report_files)
            if row_count > self.settings.max_rows_per_job:
                raise ValueError(f"Job exceeds MAX_ROWS_PER_JOB={self.settings.max_rows_per_job}.")

            for report_file in report_files:
                xls = pd.ExcelFile(report_file.path)
                for sheet_name in xls.sheet_names:
                    df = normalize_dataframe(pd.read_excel(xls, sheet_name=sheet_name, dtype=str).fillna(""))
                    if not REPORT_REQUIRED.issubset(set(df.columns)):
                        continue
                    processed_rows: list[dict[str, str]] = []
                    for row_index, row in df.iterrows():
                        row_dict = row.to_dict()
                        sin = str(row_dict.get("sin", "")).strip()
                        deterministic = corrections.get(sin) if sin else None
                        if deterministic is None:
                            deterministic = interpret_row(row_dict)

                        selected: AIInterpretation = deterministic
                        ai_interpretation = deterministic
                        if (
                            self.settings.ai_enabled
                            and deterministic.confidence < 0.7
                            and ai_rows < self.settings.max_ai_rows_per_job
                        ):
                            ai_interpretation, model_used, tokens = self.ai.interpret(build_ai_payload(row_dict))
                            ai_rows += 1
                            token_estimate += tokens
                            if model_used:
                                models_used.add(model_used)
                            selected = ai_interpretation if ai_interpretation.confidence >= deterministic.confidence else deterministic
                            if ai_interpretation.confidence < self.settings.ai_confidence_auto_accept_threshold:
                                selected.needs_manual_review = True

                        validation = validate_interpretation(selected, dictionary_index, row_dict)
                        final_action, recommendation, needs_review = choose_final_action(selected, validation)
                        instruction = self.correction_builder.build(
                            row_dict,
                            selected,
                            validation,
                            final_action,
                            recommendation,
                            needs_review,
                        )
                        first_match = validation.effective_match or (validation.matches[0] if validation.matches else None)
                        result = RowDetail(
                            row_id=f"{sheet_name}-{row_index}",
                            sheet_name=sheet_name,
                            SIN=sin,
                            Region=sheet_name,
                            Row_Index=int(row_index) + 2,
                            sanitized_original=sanitize_row(row_dict),
                            Bot_Accion=instruction.action.value,
                            Bot_Suggestion=instruction.correction_summary,
                            Bot_Details=validation.details,
                            AI_Action=ai_interpretation.action.value,
                            AI_Reason_Code=ai_interpretation.reason_code.value,
                            AI_Confidence=ai_interpretation.confidence,
                            Needs_Manual_Review=instruction.needs_manual_review,
                            Validation_Status=validation.status.value,
                            Validation_Details=validation.details,
                            Dictionary_Match_Type=first_match.match_type if first_match else None,
                            Matched_Dictionary=first_match.dictionary_name if first_match else None,
                            Matched_NPI=first_match.npi if first_match else None,
                            Matched_CBCode=first_match.cbcode if first_match else None,
                            Matched_Provider_Name=first_match.provider_name if first_match else None,
                            Deactivation_Status=first_match.deactivation_status if first_match else None,
                            AI_Explanation=ai_interpretation.explanation,
                            Final_Action=instruction.action.value,
                            Final_Recommendation=instruction.analyst_next_step,
                            Quick_Action=instruction.display_label,
                            Apply_This=instruction.apply_this,
                            Current_Type=instruction.current_type,
                            Recommended_Type=instruction.recommended_type,
                            Current_Last_Title=instruction.current_last_title,
                            Current_First=instruction.current_first,
                            Current_NPI=instruction.current_npi,
                            Current_CBCode=instruction.current_cbcode,
                            Recommended_Last_Title=instruction.recommended_last_title,
                            Recommended_First=instruction.recommended_first,
                            Recommended_NPI=instruction.recommended_npi,
                            Recommended_CBCode=instruction.recommended_cbcode,
                            Recommended_Comments=instruction.recommended_comments,
                            Recommended_Source=instruction.recommended_source,
                            Correction_Summary=instruction.correction_summary,
                            Analyst_Next_Step=instruction.analyst_next_step,
                            Manual_Reason=instruction.manual_reason,
                            Cell_Color_Last_Title=instruction.cell_color_last_title,
                            Cell_Color_First=instruction.cell_color_first,
                            Cell_Color_NPI=instruction.cell_color_npi,
                            Cell_Color_CBCode=instruction.cell_color_cbcode,
                            Cell_Color_Comments=instruction.cell_color_comments,
                            Cell_Color_Source=instruction.cell_color_source,
                            correction_instruction=instruction,
                            deterministic_interpretation=deterministic,
                            ai_interpretation=ai_interpretation,
                            validation=validation,
                        )
                        rows.append(result)
                        processed_rows.append(_apply_output(row_dict, result))
                    processed_sheets[sheet_name] = pd.DataFrame(processed_rows)
                    job_repository.update_job(job_id, progress=min(0.95, len(rows) / max(row_count, 1)), message=f"Processed {sheet_name}")

            export_path = Path(job.temp_dir) / "processed_full.xlsx"
            write_processed_workbook(processed_sheets, export_path)
            summary = self._summary(rows, ai_rows)
            audit = {
                "job_id": job_id,
                "file_types": [item.inspection.kind.value for item in upload.files],
                "row_counts": {item.filename: item.inspection.row_count for item in upload.files},
                "final_action_counts": summary.final_action_counts,
                "ai_rows_count": ai_rows,
                "model_used": sorted(models_used),
                "token_estimate": token_estimate,
                "duration": round(perf_counter() - started, 3),
                "user_feedback_counts": feedback_repository.counts(job_id),
            }
            audit_repository.add(audit)
            job_repository.update_job(
                job_id,
                status=JobStatus.COMPLETED,
                progress=1,
                message="Completed",
                rows=rows,
                summary=summary,
                full_export_path=str(export_path),
                audit={**audit, "timestamp": datetime.now(UTC).isoformat()},
            )
            job_repository.persist_rows(job_id)
        except Exception as exc:
            job_repository.update_job(job_id, status=JobStatus.FAILED, progress=1, message=str(exc))

    def _load_dictionaries(self, files) -> list[LoadedDictionary]:
        dictionaries: list[LoadedDictionary] = []
        for item in files:
            if item.inspection.kind == FileKind.DICTIONARY:
                loaded = load_dictionary(Path(item.path), item.filename)
                if loaded:
                    dictionaries.append(loaded)
        return dictionaries

    def _load_corrections(self, files) -> dict[str, AIInterpretation]:
        corrections: dict[str, AIInterpretation] = {}
        for item in files:
            if item.inspection.kind == FileKind.CORRECTIONS:
                parsed = parse_corrections(Path(item.path), interpret=self._interpret_correction_row)
                for sin, interpretation in parsed.items():
                    if _should_replace_correction(corrections.get(sin), interpretation):
                        corrections[sin] = interpretation
        return corrections

    def _summary(self, rows: list[RowDetail], ai_rows: int) -> JobSummary:
        final_counts = Counter(row.Final_Action for row in rows)
        confidence_counts = Counter(_confidence_bucket(row.AI_Confidence) for row in rows)
        work_status_counts = Counter(row.Work_Status.value for row in rows)
        return JobSummary(
            total_rows=len(rows),
            malformed_rows=final_counts.get("MALFORMED_ROW", 0),
            ignored_rows=0,
            final_action_counts=dict(final_counts),
            confidence_counts=dict(confidence_counts),
            work_status_counts=dict(work_status_counts),
            manual_review_count=sum(1 for row in rows if row.Needs_Manual_Review),
            ai_rows_count=ai_rows,
        )


report_processor = ReportProcessor()
