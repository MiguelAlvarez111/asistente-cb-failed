from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode
from backend.app.schemas.results import RowDetail, ValidationResult, ValidationStatus
from backend.app.services.excel_exporter import rows_to_workbook


def test_summary_export_returns_workbook_bytes() -> None:
    interp = AIInterpretation(
        action=AIAction.COMPLETE_INFO,
        reason_code=AIReasonCode.DIRECT_NPI,
        target_provider_name=None,
        target_npi="1234567890",
        target_cbcode=None,
        requires_add_to_ge=False,
        is_pending_usap=False,
        confidence=1,
        needs_manual_review=False,
        explanation="ok",
    )
    validation = ValidationResult(status=ValidationStatus.NPI_FOUND, details="ok", matches=[], npi_registry_name=None, needs_manual_review=False)
    row = RowDetail(
        row_id="r1",
        sheet_name="Sheet1",
        sanitized_original={"npi": "1234567890"},
        Bot_Accion="COMPLETE_INFO",
        Bot_Suggestion="ok",
        Bot_Details="ok",
        AI_Action="COMPLETE_INFO",
        AI_Reason_Code="DIRECT_NPI",
        AI_Confidence=1,
        Needs_Manual_Review=False,
        Validation_Status="NPI_FOUND",
        Validation_Details="ok",
        Dictionary_Match_Type=None,
        Matched_Dictionary=None,
        Matched_NPI=None,
        Matched_CBCode=None,
        Matched_Provider_Name=None,
        Deactivation_Status=None,
        AI_Explanation="ok",
        Final_Action="COMPLETE_INFO",
        Final_Recommendation="ok",
        deterministic_interpretation=interp,
        ai_interpretation=interp,
        validation=validation,
    )
    assert rows_to_workbook([row], kind="summary").startswith(b"PK")

