from io import BytesIO

import pandas as pd

from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode
from backend.app.schemas.results import RowDetail, ValidationResult, ValidationStatus
from backend.app.services.excel_exporter import rows_to_workbook


def _row(*, row_id: str = "r1", final_action: str = "COMPLETE_INFO", apply_this: str = "YES", source: str = "Dictionary") -> RowDetail:
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
    return RowDetail(
        row_id=row_id,
        sheet_name="Sheet1",
        SIN="SIN1",
        Region="MARYLAND",
        Row_Index=8,
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
        Final_Action=final_action,
        Final_Recommendation="ok",
        Quick_Action="Complete fields",
        Apply_This=apply_this,
        Current_Type="Provider",
        Recommended_Type="Provider",
        Recommended_CBCode="CB1",
        Recommended_Source=source,
        Cell_Color_CBCode="green",
        Cell_Color_Source="green",
        deterministic_interpretation=interp,
        ai_interpretation=interp,
        validation=validation,
    )


def test_summary_export_returns_workbook_bytes() -> None:
    row = _row()
    assert rows_to_workbook([row], kind="summary").startswith(b"PK")


def test_apply_ready_export_filters_yes_rows() -> None:
    data = rows_to_workbook([_row(row_id="ready", apply_this="YES"), _row(row_id="hold", apply_this="NO")], kind="apply_ready")
    df = pd.read_excel(BytesIO(data))
    assert df["row_id"].tolist() == ["ready"]
    assert "Current_Type" in df.columns
    assert "Recommended_Type" in df.columns
    assert "Recommended_CBCode" in df.columns
    assert "Cell_Color_CBCode" in df.columns


def test_usap_export_filters_awaiting_and_clears_source() -> None:
    data = rows_to_workbook(
        [
            _row(row_id="apply", final_action="COMPLETE_INFO", apply_this="YES", source="Dictionary"),
            _row(row_id="usap", final_action="AWAITING_USAP", apply_this="NO", source="Dictionary"),
        ],
        kind="usap",
    )
    df = pd.read_excel(BytesIO(data)).fillna("")
    assert df["row_id"].tolist() == ["usap"]
    assert df.loc[0, "Recommended_Source"] == ""


def test_numbers_ready_export_groups_by_region_and_includes_color_fields() -> None:
    data = rows_to_workbook([_row(row_id="md", apply_this="YES")], kind="numbers_ready")
    df = pd.read_excel(BytesIO(data), sheet_name="MARYLAND")
    assert "Current_Type" in df.columns
    assert "Recommended_CBCode" in df.columns
    assert "Cell_Color_CBCode" in df.columns
