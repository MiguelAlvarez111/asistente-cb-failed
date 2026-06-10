from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.ai import AIInterpretation
from backend.app.schemas.dictionaries import DictionaryMatch
from backend.app.schemas.jobs import RowWorkStatus


class ValidationStatus(StrEnum):
    VALIDATED = "VALIDATED"
    CBCODE_FOUND = "CBCODE_FOUND"
    NPI_FOUND = "NPI_FOUND"
    CBCODE_NOT_FOUND = "CBCODE_NOT_FOUND"
    NPI_NOT_FOUND = "NPI_NOT_FOUND"
    PROVIDER_NAME_MISMATCH = "PROVIDER_NAME_MISMATCH"
    DEACTIVATED_PROVIDER = "DEACTIVATED_PROVIDER"
    MULTIPLE_MATCHES = "MULTIPLE_MATCHES"
    ADD_TO_GE_REQUIRED = "ADD_TO_GE_REQUIRED"
    AMBIGUOUS_COMMENT = "AMBIGUOUS_COMMENT"
    MALFORMED_ROW = "MALFORMED_ROW"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class FinalAction(StrEnum):
    COMPLETE_INFO = "COMPLETE_INFO"
    CHANGE_TICKET = "CHANGE_TICKET"
    AWAITING_USAP = "AWAITING_USAP"
    ADD_TO_GE = "ADD_TO_GE"
    REMOVE_FROM_TICKET = "REMOVE_FROM_TICKET"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_ACTION = "NO_ACTION"
    MALFORMED_ROW = "MALFORMED_ROW"


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ValidationStatus
    details: str
    matches: list[DictionaryMatch]
    npi_registry_name: str | None
    npi_registry_data: dict[str, str] | None = None
    needs_manual_review: bool
    effective_match: DictionaryMatch | None = None


class CorrectionInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: FinalAction = FinalAction.MANUAL_REVIEW
    display_label: str = "Manual review"
    apply_this: str = "NO"
    current_type: str = ""
    recommended_type: str = ""
    current_last_title: str = ""
    current_first: str = ""
    current_npi: str = ""
    current_cbcode: str = ""
    recommended_last_title: str = ""
    recommended_first: str = ""
    recommended_npi: str = ""
    recommended_cbcode: str = ""
    recommended_comments: str = ""
    recommended_source: str = ""
    correction_summary: str = ""
    analyst_next_step: str = ""
    confidence: float = 0
    needs_manual_review: bool = True
    manual_reason: str = ""
    source_priority: str = ""
    validation_status: str = ""
    matched_dictionary: str | None = None
    matched_provider_name: str | None = None
    matched_npi: str | None = None
    matched_cbcode: str | None = None
    cell_color_last_title: str = "gray"
    cell_color_first: str = "gray"
    cell_color_npi: str = "gray"
    cell_color_cbcode: str = "gray"
    cell_color_comments: str = "gray"
    cell_color_source: str = "gray"


class RowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: str
    sheet_name: str
    SIN: str = ""
    Region: str = ""
    Row_Index: int = 0
    Work_Status: RowWorkStatus = RowWorkStatus.PENDING
    sanitized_original: dict[str, Any]
    Bot_Accion: str
    Bot_Suggestion: str
    Bot_Details: str
    AI_Action: str
    AI_Reason_Code: str
    AI_Confidence: float
    Needs_Manual_Review: bool
    Validation_Status: str
    Validation_Details: str
    Dictionary_Match_Type: str | None
    Matched_Dictionary: str | None
    Matched_NPI: str | None
    Matched_CBCode: str | None
    Matched_Provider_Name: str | None
    Deactivation_Status: str | None
    AI_Explanation: str
    Final_Action: str
    Final_Recommendation: str
    Quick_Action: str = ""
    Apply_This: str = "NO"
    Current_Type: str = ""
    Recommended_Type: str = ""
    Current_Last_Title: str = ""
    Current_First: str = ""
    Current_NPI: str = ""
    Current_CBCode: str = ""
    Recommended_Last_Title: str = ""
    Recommended_First: str = ""
    Recommended_NPI: str = ""
    Recommended_CBCode: str = ""
    Recommended_Comments: str = ""
    Recommended_Source: str = ""
    Correction_Summary: str = ""
    Analyst_Next_Step: str = ""
    Manual_Reason: str = ""
    Cell_Color_Last_Title: str = "gray"
    Cell_Color_First: str = "gray"
    Cell_Color_NPI: str = "gray"
    Cell_Color_CBCode: str = "gray"
    Cell_Color_Comments: str = "gray"
    Cell_Color_Source: str = "gray"
    correction_instruction: CorrectionInstruction = Field(default_factory=CorrectionInstruction)


class RowDetail(RowResult):
    deterministic_interpretation: AIInterpretation
    ai_interpretation: AIInterpretation
    validation: ValidationResult


class LookupCurrentValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_title: str
    first: str
    npi: str
    cbcode: str


class LookupRecommendedValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_title: str
    first: str
    npi: str
    cbcode: str
    comments: str
    source: str


class LookupCellColors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_title: str
    first: str
    npi: str
    cbcode: str
    comments: str
    source: str


class SINLookupMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: str
    sin: str
    region: str
    row_index: int
    final_action: str
    quick_action: str
    apply_this: str
    work_status: RowWorkStatus
    role: str
    current_provider: str
    current: LookupCurrentValues
    recommended: LookupRecommendedValues
    cell_colors: LookupCellColors
    correction_summary: str
    analyst_next_step: str
    validation_status: str
    manual_reason: str | None


class SINLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    normalized_query: str
    match_count: int
    matches: list[SINLookupMatch]
