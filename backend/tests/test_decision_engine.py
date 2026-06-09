from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode
from backend.app.schemas.dictionaries import DictionaryMatch, DictionaryType
from backend.app.schemas.results import ValidationResult, ValidationStatus
from backend.app.services.decision_engine import choose_final_action


def interpretation(action: AIAction) -> AIInterpretation:
    return AIInterpretation(
        action=action,
        reason_code=AIReasonCode.DIRECT_NPI,
        target_provider_name=None,
        target_npi="1234567890",
        target_cbcode=None,
        requires_add_to_ge=False,
        is_pending_usap=False,
        confidence=1,
        needs_manual_review=False,
        explanation="test",
    )


def validation(status: ValidationStatus, review: bool = False) -> ValidationResult:
    return ValidationResult(status=status, details="details", matches=[], npi_registry_name=None, needs_manual_review=review)


def match() -> DictionaryMatch:
    return DictionaryMatch(
        dictionary_name="dict",
        dictionary_type=DictionaryType.REFERRING_PROVIDERS,
        match_type="NPI",
        npi="1234567890",
        cbcode="CB1",
        provider_name="DOE JANE",
        deactivation_status="",
        division=None,
        ba_mnemonic=None,
    )


def test_complete_info_requires_dictionary_match() -> None:
    final_action, _, review = choose_final_action(interpretation(AIAction.COMPLETE_INFO), validation(ValidationStatus.NPI_FOUND))
    assert final_action == "AWAITING_USAP"
    assert review is False


def test_complete_info_validated() -> None:
    result = validation(ValidationStatus.NPI_FOUND)
    result.matches = [match()]
    result.effective_match = result.matches[0]
    final_action, _, review = choose_final_action(interpretation(AIAction.COMPLETE_INFO), result)
    assert final_action == "COMPLETE_INFO"
    assert review is False


def test_deactivated_provider_forces_manual_review() -> None:
    final_action, _, review = choose_final_action(interpretation(AIAction.COMPLETE_INFO), validation(ValidationStatus.DEACTIVATED_PROVIDER))
    assert final_action == "MANUAL_REVIEW"
    assert review is True
