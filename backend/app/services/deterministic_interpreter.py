import re

from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode


MALFORMED_RE = re.compile(r"^\s*line\s+\d+\s*:?\s*$", re.IGNORECASE)


def _make(
    action: AIAction,
    reason_code: AIReasonCode,
    *,
    provider_name: str | None = None,
    npi: str | None = None,
    cbcode: str | None = None,
    add_to_ge: bool = False,
    pending: bool = False,
    confidence: float = 1.0,
    review: bool = False,
    explanation: str = "",
) -> AIInterpretation:
    return AIInterpretation(
        action=action,
        reason_code=reason_code,
        target_provider_name=provider_name,
        target_npi=npi,
        target_cbcode=cbcode,
        requires_add_to_ge=add_to_ge,
        is_pending_usap=pending,
        confidence=confidence,
        needs_manual_review=review,
        explanation=explanation or reason_code.value,
    )


def interpret_row(row: dict[str, str]) -> AIInterpretation:
    npi_field = str(row.get("npi", "") or "").strip()
    cbcode_field = str(row.get("cbcode", "") or "").strip()
    comments = str(row.get("comments", "") or "").strip()
    source = str(row.get("source", "") or "").strip()
    haystack = " ".join([npi_field, cbcode_field, comments, source]).strip()
    lower = haystack.lower()

    if any(MALFORMED_RE.match(value) for value in [npi_field, cbcode_field, comments]):
        return _make(AIAction.MANUAL_REVIEW, AIReasonCode.MALFORMED_ROW, confidence=1, review=True, explanation="Malformed line marker.")

    add_to_ge_match = re.search(r"add\s+to\s+ge(?:\s+(?P<npi>\d{10}))?", lower, re.IGNORECASE)
    if add_to_ge_match:
        return _make(
            AIAction.ADD_TO_GE,
            AIReasonCode.ADD_TO_GE_NPI if add_to_ge_match.group("npi") else AIReasonCode.ADD_TO_GE,
            npi=add_to_ge_match.group("npi"),
            add_to_ge=True,
            confidence=1,
            explanation="ADD TO GE instruction detected.",
        )

    if "pending" in lower:
        return _make(AIAction.AWAITING_USAP, AIReasonCode.PENDING_USAP, pending=True, confidence=1, explanation="Pending USAP confirmation.")
    if "awaiting" in lower:
        return _make(AIAction.AWAITING_USAP, AIReasonCode.AWAITING_USAP, pending=True, confidence=1, explanation="Awaiting USAP confirmation.")

    chg_match = re.search(r"chg\s+to\s+(?P<name>.+)", npi_field, re.IGNORECASE) or re.search(r"chg\s+to\s+(?P<name>.+)", comments, re.IGNORECASE)
    if chg_match:
        return _make(
            AIAction.CHANGE_TICKET,
            AIReasonCode.CHG_TO,
            provider_name=chg_match.group("name").strip(),
            cbcode=cbcode_field or None,
            confidence=0.95,
            explanation="CHG TO provider instruction detected.",
        )

    cb_match = re.search(r"correct provider (?P<name>.*?) with cb\s*code (?P<cb>[A-Za-z0-9_-]+)", comments, re.IGNORECASE)
    if cb_match:
        return _make(
            AIAction.CHANGE_TICKET,
            AIReasonCode.CORRECT_PROVIDER_CB,
            provider_name=cb_match.group("name").strip(),
            cbcode=cb_match.group("cb").strip(),
            confidence=1,
            explanation="Correct provider with CBCode instruction detected.",
        )

    npi_match = re.search(r"correct provider (?P<name>.*?) with npi (?P<npi>\d{10})", comments, re.IGNORECASE)
    if npi_match:
        return _make(
            AIAction.CHANGE_TICKET,
            AIReasonCode.CORRECT_PROVIDER_NPI,
            provider_name=npi_match.group("name").strip(),
            npi=npi_match.group("npi").strip(),
            confidence=1,
            explanation="Correct provider with NPI instruction detected.",
        )

    if cbcode_field:
        return _make(AIAction.COMPLETE_INFO, AIReasonCode.DIRECT_CBCODE, cbcode=cbcode_field, confidence=0.9, explanation="Direct CBCode value present.")
    if npi_field and npi_field.isdigit():
        return _make(AIAction.COMPLETE_INFO, AIReasonCode.DIRECT_NPI, npi=npi_field, confidence=0.85, explanation="Direct NPI value present.")

    return _make(
        AIAction.UNKNOWN,
        AIReasonCode.NO_SIGNAL,
        confidence=0.2,
        review=True,
        explanation="No deterministic instruction found.",
    )

