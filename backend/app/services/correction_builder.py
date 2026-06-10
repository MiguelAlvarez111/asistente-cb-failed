import re
from typing import Any

from backend.app.schemas.ai import AIInterpretation
from backend.app.schemas.dictionaries import DictionaryMatch
from backend.app.schemas.results import CorrectionInstruction, FinalAction, ValidationResult, ValidationStatus


AWAITING_USAP_CBCODE = "Awaiting for USAP confirmation"
DEGREE_TOKENS = {"MD", "DO", "CRNA", "MDA", "DPM", "PA", "NP", "RN"}

DISPLAY_LABELS = {
    FinalAction.COMPLETE_INFO: "Complete fields",
    FinalAction.CHANGE_TICKET: "Change ticket",
    FinalAction.AWAITING_USAP: "Awaiting USAP",
    FinalAction.REMOVE_FROM_TICKET: "Remove from ticket",
    FinalAction.MANUAL_REVIEW: "Manual review",
    FinalAction.MALFORMED_ROW: "Malformed row",
    FinalAction.ADD_TO_GE: "Awaiting USAP",
    FinalAction.NO_ACTION: "No action",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", _clean(value).upper()).strip()


def _split_provider_name(provider_name: str | None) -> tuple[str, str]:
    name = _clean(provider_name)
    if not name:
        return "", ""
    if "," in name:
        last, first = name.split(",", 1)
        return _strip_degree_suffix(last), _strip_degree_suffix(first)
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return _strip_degree_suffix(parts[0]), _strip_degree_suffix(" ".join(parts[1:]))


def _strip_degree_suffix(value: str) -> str:
    tokens = [token for token in value.strip().split() if token.upper().strip(".,") not in DEGREE_TOKENS]
    return " ".join(tokens).strip()


def _role_from_row(row: dict[str, Any], match: DictionaryMatch | None = None) -> str:
    role = _clean(row.get("type"))
    if role:
        return role
    if match:
        return "Provider" if str(match.dictionary_type) == "USAP_PROVIDERS" else "Surgeon"
    return ""


def _base_instruction(
    row: dict[str, Any],
    interpretation: AIInterpretation,
    validation: ValidationResult,
    final_action: FinalAction,
    needs_review: bool,
) -> CorrectionInstruction:
    match = validation.effective_match or (validation.matches[0] if validation.matches else None)
    return CorrectionInstruction(
        action=final_action,
        display_label=DISPLAY_LABELS.get(final_action, final_action.value.replace("_", " ").title()),
        apply_this="NO",
        current_type=_role_from_row(row, match),
        recommended_type=_role_from_row(row, match),
        current_last_title=_clean(row.get("last_title")),
        current_first=_clean(row.get("first")),
        current_npi=_clean(row.get("npi")),
        current_cbcode=_clean(row.get("cbcode")),
        confidence=interpretation.confidence,
        needs_manual_review=needs_review,
        validation_status=validation.status.value,
        matched_dictionary=match.dictionary_name if match else None,
        matched_provider_name=match.provider_name if match else None,
        matched_npi=match.npi if match else None,
        matched_cbcode=match.cbcode if match else None,
    )


def _set_all_colors(instruction: CorrectionInstruction, color: str) -> None:
    instruction.cell_color_last_title = color
    instruction.cell_color_first = color
    instruction.cell_color_npi = color
    instruction.cell_color_cbcode = color
    instruction.cell_color_comments = color
    instruction.cell_color_source = color


def _has_useful_completion(row: dict[str, Any], match: DictionaryMatch, recommended_last: str, recommended_first: str) -> bool:
    current_npi = _clean(row.get("npi"))
    current_cbcode = _clean(row.get("cbcode"))
    current_last = _clean(row.get("last_title"))
    current_first = _clean(row.get("first"))
    current_source = _clean(row.get("source"))
    return any(
        [
            bool(match.npi and _norm(current_npi) != _norm(match.npi)),
            bool(match.cbcode and _norm(current_cbcode) != _norm(match.cbcode)),
            bool(recommended_last and _norm(current_last) != _norm(recommended_last)),
            bool(recommended_first and _norm(current_first) != _norm(recommended_first)),
            not current_source,
        ]
    )


def _npi_registry_name_parts(validation: ValidationResult) -> tuple[str, str]:
    registry = validation.npi_registry_data or {}
    last = _strip_degree_suffix(_clean(registry.get("last_name")))
    first = _strip_degree_suffix(" ".join(part for part in [_clean(registry.get("first_name")), _clean(registry.get("middle_name"))] if part))
    if last or first:
        return last, first
    return _split_provider_name(validation.npi_registry_name)


def _best_npi_change_name(row: dict[str, Any], interpretation: AIInterpretation, validation: ValidationResult) -> tuple[str, str, str]:
    registry_last, registry_first = _npi_registry_name_parts(validation)
    if registry_last or registry_first:
        return registry_last, registry_first, "USAP / NPI Registry"
    comment_last, comment_first = _split_provider_name(interpretation.target_provider_name)
    if comment_last or comment_first:
        return comment_last, comment_first, "USAP"
    return _clean(row.get("last_title")), _clean(row.get("first")), "USAP"


class CorrectionBuilder:
    def build(
        self,
        row: dict[str, Any],
        interpretation: AIInterpretation,
        validation: ValidationResult,
        final_action: FinalAction,
        recommendation: str,
        needs_review: bool,
    ) -> CorrectionInstruction:
        instruction = _base_instruction(row, interpretation, validation, final_action, needs_review)
        match = validation.effective_match or (validation.matches[0] if validation.matches else None)

        if final_action == FinalAction.MALFORMED_ROW:
            _set_all_colors(instruction, "yellow")
            instruction.correction_summary = "Malformed source row marker detected."
            instruction.analyst_next_step = "Ignore this row or fix the source formatting before processing."
            instruction.manual_reason = validation.details
            instruction.source_priority = "Manual Review"
            return instruction

        if final_action == FinalAction.REMOVE_FROM_TICKET:
            instruction.cell_color_comments = "red"
            instruction.cell_color_source = "gray"
            instruction.recommended_comments = "Remove from the ticket"
            instruction.correction_summary = "Possible RN/Internal Audit/remove-from-ticket case."
            instruction.analyst_next_step = "Verify the ticket has another main provider before removing this provider."
            instruction.manual_reason = interpretation.explanation or "Remove-from-ticket instruction requires analyst verification."
            instruction.source_priority = "Ticket verification"
            instruction.needs_manual_review = True
            return instruction

        if final_action == FinalAction.CHANGE_TICKET:
            if match:
                recommended_last, recommended_first = _split_provider_name(match.provider_name)
                instruction.apply_this = "YES"
                instruction.cell_color_last_title = "red"
                instruction.cell_color_first = "red"
                instruction.cell_color_npi = "red"
                instruction.cell_color_cbcode = "red"
                instruction.cell_color_comments = "red"
                instruction.cell_color_source = "green"
                instruction.recommended_last_title = recommended_last
                instruction.recommended_first = recommended_first
                instruction.recommended_npi = _clean(match.npi)
                instruction.recommended_cbcode = _clean(match.cbcode)
                instruction.recommended_comments = "Change in the ticket"
                instruction.recommended_source = "Dictionary"
                instruction.correction_summary = (
                    f"Change ticket from {instruction.current_last_title} {instruction.current_first} "
                    f"to {match.provider_name or 'validated provider'} using validated CBCode {match.cbcode or ''}."
                ).strip()
                instruction.analyst_next_step = (
                    "Replace the current provider/surgeon fields with the recommended values and verify the target provider "
                    "in RCMLinx before database submission."
                )
                instruction.source_priority = "Dictionary"
                return instruction
            if interpretation.target_npi and not interpretation.target_cbcode and validation.status == ValidationStatus.NPI_FOUND:
                recommended_last, recommended_first, source = _best_npi_change_name(row, interpretation, validation)
                instruction.apply_this = "YES"
                instruction.needs_manual_review = False
                instruction.cell_color_last_title = "red" if recommended_last else "gray"
                instruction.cell_color_first = "red" if recommended_first else "gray"
                instruction.cell_color_npi = "red" if interpretation.target_npi else "gray"
                instruction.cell_color_cbcode = "yellow"
                instruction.cell_color_comments = "red"
                instruction.cell_color_source = "green"
                instruction.recommended_last_title = recommended_last
                instruction.recommended_first = recommended_first
                instruction.recommended_npi = _clean(interpretation.target_npi)
                instruction.recommended_cbcode = AWAITING_USAP_CBCODE
                instruction.recommended_comments = "Change in the ticket"
                instruction.recommended_source = source
                instruction.correction_summary = "Change ticket with NPI Registry validated target; CBCode is awaiting creation."
                instruction.analyst_next_step = (
                    "Apply the change-ticket correction and keep CBCode as awaiting USAP confirmation."
                )
                instruction.source_priority = source
                return instruction
            instruction.action = FinalAction.MANUAL_REVIEW
            instruction.display_label = DISPLAY_LABELS[FinalAction.MANUAL_REVIEW]
            _set_all_colors(instruction, "yellow")
            instruction.manual_reason = (
                "Target NPI could not be validated in NPI Registry or dictionary."
                if interpretation.target_npi and validation.status == ValidationStatus.NPI_NOT_FOUND
                else "Change target could not be validated in dictionary."
            )
            instruction.correction_summary = "Change-ticket target could not be safely validated."
            instruction.analyst_next_step = "Review the target provider manually before changing the ticket."
            instruction.source_priority = "Manual Review"
            instruction.needs_manual_review = True
            return instruction

        if final_action == FinalAction.COMPLETE_INFO:
            if match:
                recommended_last, recommended_first = _split_provider_name(match.provider_name)
                completion_color = "red" if _role_from_row(row, match).lower() == "provider" else "green"
                instruction.recommended_last_title = recommended_last
                instruction.recommended_first = recommended_first
                instruction.recommended_npi = _clean(match.npi)
                instruction.recommended_cbcode = _clean(match.cbcode)
                instruction.recommended_source = "Dictionary"
                instruction.cell_color_last_title = completion_color if recommended_last and _norm(row.get("last_title")) != _norm(recommended_last) else "gray"
                instruction.cell_color_first = completion_color if recommended_first and _norm(row.get("first")) != _norm(recommended_first) else "gray"
                instruction.cell_color_npi = completion_color if match.npi and _norm(row.get("npi")) != _norm(match.npi) else "gray"
                instruction.cell_color_cbcode = completion_color if match.cbcode and _norm(row.get("cbcode")) != _norm(match.cbcode) else "gray"
                instruction.cell_color_source = completion_color
                instruction.correction_summary = "Complete missing NPI and CBCode from Dictionary."
                instruction.analyst_next_step = "Apply the recommended NPI and CBCode to the report."
                instruction.source_priority = "Dictionary"
                if _has_useful_completion(row, match, recommended_last, recommended_first):
                    instruction.apply_this = "YES"
                else:
                    instruction.manual_reason = "Dictionary validated the provider, but no missing operational field was identified."
                return instruction

        if final_action == FinalAction.AWAITING_USAP:
            _set_all_colors(instruction, "yellow")
            instruction.cell_color_source = "gray"
            instruction.recommended_cbcode = AWAITING_USAP_CBCODE
            instruction.recommended_source = ""
            instruction.apply_this = "NO"
            instruction.correction_summary = "No validated CBCode/NPI was found or identity conflict exists."
            if interpretation.action.value == "CHANGE_TICKET" and (interpretation.target_provider_name or interpretation.target_npi):
                recommended_last, recommended_first = _split_provider_name(interpretation.target_provider_name)
                instruction.recommended_last_title = recommended_last
                instruction.recommended_first = recommended_first
                instruction.recommended_npi = _clean(interpretation.target_npi)
                instruction.recommended_comments = "Change in the ticket"
                instruction.recommended_source = "USAP"
                instruction.cell_color_source = "yellow"
                instruction.correction_summary = "USAP correction received; awaiting CBCode."
                instruction.analyst_next_step = "Wait for USAP to confirm the CBCode before applying this correction."
                instruction.source_priority = "USAP"
                return instruction
            if validation.status == ValidationStatus.NPI_FOUND and not match:
                instruction.recommended_comments = "The NPI appears valid in NPI Registry, but no CBCode was found in the dictionary."
                instruction.correction_summary = "NPI Registry validates identity but does not provide CBCode."
            elif interpretation.requires_add_to_ge:
                instruction.recommended_comments = "Provider must be added to GE before completion."
                instruction.correction_summary = "ADD TO GE requires USAP/GE confirmation."
            elif interpretation.reason_code.value == "FF_PROVIDER_OVERRIDE":
                instruction.recommended_comments = "FF Provider Override requires USAP confirmation."
                instruction.correction_summary = "FF Provider Override detected."
            instruction.analyst_next_step = "Send this row to USAP for confirmation."
            instruction.source_priority = "USAP"
            return instruction

        instruction.action = FinalAction.MANUAL_REVIEW
        _set_all_colors(instruction, "yellow")
        instruction.display_label = DISPLAY_LABELS[FinalAction.MANUAL_REVIEW]
        instruction.correction_summary = "Manual review is required before applying any correction."
        instruction.analyst_next_step = "Check the row, dictionary candidates, and source comments manually."
        instruction.manual_reason = recommendation or validation.details or interpretation.explanation
        instruction.source_priority = "Manual Review"
        instruction.needs_manual_review = True
        return instruction
