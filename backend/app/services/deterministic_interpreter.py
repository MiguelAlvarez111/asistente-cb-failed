import re

from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode


MALFORMED_RE = re.compile(r"^\s*line\s+\d+\s*:?\s*$", re.IGNORECASE)
DEGREE_TOKENS = {"MD", "DO", "CRNA", "MDA", "DPM", "PA", "NP", "RN"}
CB_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{2,16}$")


def _target_cbcode(value: str) -> str | None:
    text = value.strip()
    lower = text.lower()
    if (
        not text
        or "awaiting" in lower
        or "pending" in lower
        or "add to ge" in lower
        or "cb code" in lower
        or re.search(r"\b\d{10}\b", text)
        or not CB_CODE_RE.match(text)
    ):
        return None
    return text


def _target_npi_from_operational_text(*values: str) -> str | None:
    text = " ".join(value for value in values if value).strip()
    npi_values = re.findall(r"\b\d{10}\b", text)
    return npi_values[-1] if npi_values else None


def _row_role(row: dict[str, str]) -> str:
    return str(row.get("type", "") or "").strip().lower()


def _provider_name_from_row(row: dict[str, str]) -> str | None:
    last = str(row.get("last_title", "") or "").strip()
    first = str(row.get("first", "") or "").strip()
    if last and first:
        return f"{last} {first}"
    return last or first or None


def _strip_degree_tokens(value: str) -> str:
    tokens = [token for token in value.split() if token.upper().strip(".,") not in DEGREE_TOKENS]
    return " ".join(tokens).strip()


def _target_name_from_combined_fields(row: dict[str, str]) -> str | None:
    last_parts = str(row.get("last_title", "") or "").strip().split()
    first_parts = str(row.get("first", "") or "").strip().split()
    if len(last_parts) < 2 or len(first_parts) < 2:
        return None
    target_last = _strip_degree_tokens(last_parts[-1])
    target_first = first_parts[-1].strip()
    if target_last and target_first:
        return f"{target_last},{target_first}"
    return None


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

    if "ff provider override" in lower:
        return _make(
            AIAction.AWAITING_USAP,
            AIReasonCode.FF_PROVIDER_OVERRIDE,
            pending=True,
            confidence=1,
            explanation="FF Provider Override requires USAP confirmation.",
        )

    remove_hints = [
        "remove from the ticket",
        "remove from ticket",
        "remove provider from ticket",
        "rn/internal audit",
        "rn internal audit",
        "rn audit",
        "internal audit",
    ]
    if any(hint in lower for hint in remove_hints):
        reason = AIReasonCode.RN_INTERNAL_AUDIT if "audit" in lower else AIReasonCode.REMOVE_FROM_TICKET
        return _make(
            AIAction.REMOVE_FROM_TICKET,
            reason,
            confidence=0.95,
            review=True,
            explanation="Remove-from-ticket instruction detected.",
        )

    npi_values = re.findall(r"\b\d{10}\b", npi_field)
    if len(npi_values) >= 2 and "awaiting" in cbcode_field.lower() and ("change in the ticket" in lower or source.lower() == "usap"):
        return _make(
            AIAction.CHANGE_TICKET,
            AIReasonCode.USAP_PENDING_CBCODE,
            provider_name=_target_name_from_combined_fields(row),
            npi=npi_values[-1],
            pending=True,
            confidence=0.9,
            explanation="USAP correction with target NPI is awaiting CBCode.",
        )

    chg_match = re.search(r"chg\s+to\s+(?P<name>.+)", npi_field, re.IGNORECASE) or re.search(r"chg\s+to\s+(?P<name>.+)", comments, re.IGNORECASE)
    if chg_match:
        add_to_ge_match = re.search(r"add\s+to\s+ge(?:\s+(?P<npi>\d{10}))?", haystack, re.IGNORECASE)
        target_cbcode = _target_cbcode(cbcode_field)
        target_npi = (
            add_to_ge_match.group("npi")
            if add_to_ge_match and add_to_ge_match.group("npi")
            else _target_npi_from_operational_text(cbcode_field, comments, source)
        )
        is_pending_target = bool(add_to_ge_match or (target_npi and not target_cbcode))
        return _make(
            AIAction.CHANGE_TICKET,
            AIReasonCode.CHG_TO,
            provider_name=chg_match.group("name").strip(),
            npi=target_npi,
            cbcode=target_cbcode,
            pending=is_pending_target,
            confidence=0.95,
            explanation=(
                "CHG TO provider instruction detected; target NPI is awaiting GE/CBCode setup."
                if is_pending_target
                else "CHG TO provider instruction detected."
            ),
        )

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

    if "change in the ticket" in lower:
        target_npi = npi_field if npi_field.isdigit() else None
        target_cbcode = _target_cbcode(cbcode_field)
        return _make(
            AIAction.CHANGE_TICKET,
            AIReasonCode.CHANGE_IN_TICKET,
            npi=target_npi,
            cbcode=target_cbcode,
            confidence=0.85 if (target_npi or target_cbcode) else 0.55,
            review=not bool(target_npi or target_cbcode),
            explanation="Change-in-ticket instruction detected.",
        )

    if "pending" in lower:
        return _make(AIAction.AWAITING_USAP, AIReasonCode.PENDING_USAP, pending=True, confidence=1, explanation="Pending USAP confirmation.")
    if "awaiting" in lower:
        return _make(AIAction.AWAITING_USAP, AIReasonCode.AWAITING_USAP, pending=True, confidence=1, explanation="Awaiting USAP confirmation.")

    if cbcode_field:
        return _make(AIAction.COMPLETE_INFO, AIReasonCode.DIRECT_CBCODE, cbcode=cbcode_field, confidence=0.9, explanation="Direct CBCode value present.")
    if npi_field and npi_field.isdigit():
        return _make(AIAction.COMPLETE_INFO, AIReasonCode.DIRECT_NPI, npi=npi_field, confidence=0.85, explanation="Direct NPI value present.")
    if _row_role(row) == "provider" and _provider_name_from_row(row):
        return _make(
            AIAction.COMPLETE_INFO,
            AIReasonCode.PROVIDER_NAME_LOOKUP,
            provider_name=_provider_name_from_row(row),
            confidence=0.75,
            explanation="Provider name lookup requested for missing NPI/CBCode.",
        )

    return _make(
        AIAction.UNKNOWN,
        AIReasonCode.NO_SIGNAL,
        confidence=0.2,
        review=True,
        explanation="No deterministic instruction found.",
    )
