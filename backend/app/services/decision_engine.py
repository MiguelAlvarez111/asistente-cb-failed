from backend.app.schemas.ai import AIAction, AIInterpretation
from backend.app.schemas.results import FinalAction, ValidationResult, ValidationStatus


def choose_final_action(interpretation: AIInterpretation, validation: ValidationResult) -> tuple[FinalAction, str, bool]:
    if validation.status == ValidationStatus.MALFORMED_ROW:
        return FinalAction.MALFORMED_ROW, "Ignore or fix malformed source row.", True
    if interpretation.action == AIAction.REMOVE_FROM_TICKET:
        return FinalAction.REMOVE_FROM_TICKET, "Verify ticket context before removing this provider.", True
    if interpretation.requires_add_to_ge or validation.status == ValidationStatus.ADD_TO_GE_REQUIRED:
        return FinalAction.AWAITING_USAP, "Send to USAP for GE setup or confirmation.", False
    if interpretation.is_pending_usap or interpretation.action == AIAction.AWAITING_USAP:
        return FinalAction.AWAITING_USAP, "Await USAP confirmation.", False
    if validation.status in {ValidationStatus.DEACTIVATED_PROVIDER, ValidationStatus.MULTIPLE_MATCHES}:
        return FinalAction.MANUAL_REVIEW, validation.details, True
    if interpretation.action == AIAction.CHANGE_TICKET and validation.status in {
        ValidationStatus.VALIDATED,
        ValidationStatus.CBCODE_FOUND,
        ValidationStatus.NPI_FOUND,
    } and validation.matches:
        return FinalAction.CHANGE_TICKET, "Change ticket with validated target provider.", False
    if interpretation.action == AIAction.CHANGE_TICKET:
        return FinalAction.MANUAL_REVIEW, "Change target could not be validated in dictionary.", True
    if interpretation.action == AIAction.COMPLETE_INFO and validation.status in {
        ValidationStatus.VALIDATED,
        ValidationStatus.CBCODE_FOUND,
        ValidationStatus.NPI_FOUND,
    } and validation.matches:
        return FinalAction.COMPLETE_INFO, "Complete missing provider information.", False
    if validation.status in {
        ValidationStatus.NPI_FOUND,
        ValidationStatus.CBCODE_NOT_FOUND,
        ValidationStatus.NPI_NOT_FOUND,
        ValidationStatus.AMBIGUOUS_COMMENT,
        ValidationStatus.ADD_TO_GE_REQUIRED,
    }:
        return FinalAction.AWAITING_USAP, "Send to USAP for confirmation.", False
    if validation.needs_manual_review or interpretation.needs_manual_review or interpretation.action == AIAction.MANUAL_REVIEW:
        return FinalAction.MANUAL_REVIEW, validation.details or interpretation.explanation, True
    return FinalAction.MANUAL_REVIEW, "Decision conflict or insufficient validation.", True
