from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import pandas as pd

from backend.app.core.config import Settings, get_settings
from backend.app.repositories.audit_repository import audit_repository
from backend.app.repositories.feedback_repository import feedback_repository
from backend.app.repositories.job_repository import JobRecord, job_repository
from backend.app.schemas.ai import AIInterpretation
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


class ReportProcessor:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.ai = AIInterpreter(self.settings)
        self.correction_builder = CorrectionBuilder()

    def process(self, job_id: str, upload_id: str) -> None:
        started = perf_counter()
        job_repository.update_job(job_id, status=JobStatus.PROCESSING, progress=0.05, message="Loading files")
        upload = job_repository.get_upload(upload_id)
        job = job_repository.get_job(job_id)
        if not upload or not job:
            return

        try:
            dictionaries = self._load_dictionaries(upload.files)
            dictionary_index = DictionaryIndex(dictionaries)
            corrections = self._load_corrections(upload.files)
            report_files = [item for item in upload.files if item.inspection.kind == FileKind.CB_FAILED_REPORT]
            if not report_files:
                raise ValueError("No CB Failed report file detected.")

            rows: list[RowDetail] = []
            processed_sheets: dict[str, pd.DataFrame] = {}
            ai_rows = 0
            token_estimate = 0
            models_used: set[str] = set()
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
                corrections.update(parse_corrections(Path(item.path)))
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
