from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AIAction(StrEnum):
    COMPLETE_INFO = "COMPLETE_INFO"
    CHANGE_TICKET = "CHANGE_TICKET"
    AWAITING_USAP = "AWAITING_USAP"
    ADD_TO_GE = "ADD_TO_GE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_ACTION = "NO_ACTION"
    UNKNOWN = "UNKNOWN"


class AIReasonCode(StrEnum):
    CHG_TO = "CHG_TO"
    ADD_TO_GE = "ADD_TO_GE"
    ADD_TO_GE_NPI = "ADD_TO_GE_NPI"
    PENDING_USAP = "PENDING_USAP"
    AWAITING_USAP = "AWAITING_USAP"
    CORRECT_PROVIDER_CB = "CORRECT_PROVIDER_CB"
    CORRECT_PROVIDER_NPI = "CORRECT_PROVIDER_NPI"
    DIRECT_CBCODE = "DIRECT_CBCODE"
    DIRECT_NPI = "DIRECT_NPI"
    MALFORMED_ROW = "MALFORMED_ROW"
    AMBIGUOUS_COMMENT = "AMBIGUOUS_COMMENT"
    AI_DISABLED = "AI_DISABLED"
    AI_SCHEMA_FAILURE = "AI_SCHEMA_FAILURE"
    AI_TIMEOUT = "AI_TIMEOUT"
    AI_LOW_CONFIDENCE = "AI_LOW_CONFIDENCE"
    NO_SIGNAL = "NO_SIGNAL"
    UNKNOWN_REASON = "UNKNOWN_REASON"


class AIInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: AIAction
    reason_code: AIReasonCode
    target_provider_name: str | None
    target_npi: str | None
    target_cbcode: str | None
    requires_add_to_ge: bool
    is_pending_usap: bool
    confidence: float = Field(ge=0, le=1)
    needs_manual_review: bool
    explanation: str


def fallback_interpretation(reason_code: AIReasonCode, explanation: str) -> AIInterpretation:
    return AIInterpretation(
        action=AIAction.MANUAL_REVIEW,
        reason_code=reason_code,
        target_provider_name=None,
        target_npi=None,
        target_cbcode=None,
        requires_add_to_ge=False,
        is_pending_usap=False,
        confidence=0,
        needs_manual_review=True,
        explanation=explanation,
    )

