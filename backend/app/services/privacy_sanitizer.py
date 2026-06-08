from typing import Any

from backend.app.services.column_normalizer import normalize_column_name

PHI_FIELDS = {"patientLast", "patientFirst", "DOB", "AccNumber"}
AI_EXCLUDED_FIELDS = PHI_FIELDS | {"sin"}
AI_ALLOWED_FIELDS = {
    "type",
    "current_last_title",
    "current_first",
    "npi_field",
    "cbcode_field",
    "practice",
    "facility",
    "comments",
    "source",
}


def is_phi_field(field: str) -> bool:
    return normalize_column_name(field) in PHI_FIELDS


def sanitize_row(row: dict[str, Any], *, include_sin: bool = False) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in row.items():
        normalized = normalize_column_name(key)
        if normalized in PHI_FIELDS:
            continue
        if normalized == "sin" and not include_sin:
            continue
        sanitized[normalized] = value
    return sanitized


def build_ai_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "type": row.get("type", ""),
        "current_last_title": row.get("last_title", ""),
        "current_first": row.get("first", ""),
        "npi_field": row.get("npi", ""),
        "cbcode_field": row.get("cbcode", ""),
        "practice": row.get("practice", ""),
        "facility": row.get("facility", ""),
        "comments": row.get("comments", ""),
        "source": row.get("source", ""),
    }
    return {key: str(payload.get(key, "")) for key in AI_ALLOWED_FIELDS}

