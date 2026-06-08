from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.ai import AIInterpretation
from backend.app.schemas.dictionaries import DictionaryMatch


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
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_ACTION = "NO_ACTION"
    MALFORMED_ROW = "MALFORMED_ROW"


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ValidationStatus
    details: str
    matches: list[DictionaryMatch]
    npi_registry_name: str | None
    needs_manual_review: bool


class RowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: str
    sheet_name: str
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


class RowDetail(RowResult):
    deterministic_interpretation: AIInterpretation
    ai_interpretation: AIInterpretation
    validation: ValidationResult

