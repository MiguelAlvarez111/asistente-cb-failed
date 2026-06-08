from backend.app.services.privacy_sanitizer import build_ai_payload, sanitize_row


def test_patient_fields_and_sin_removed_from_sanitized_row() -> None:
    row = {"patientLast": "Secret", "patientFirst": "Person", "DOB": "1/1/2000", "AccNumber": "A1", "sin": "S1", "npi": "123"}
    sanitized = sanitize_row(row)
    assert "patientLast" not in sanitized
    assert "patientFirst" not in sanitized
    assert "DOB" not in sanitized
    assert "AccNumber" not in sanitized
    assert "sin" not in sanitized
    assert sanitized["npi"] == "123"


def test_ai_payload_is_operational_only() -> None:
    payload = build_ai_payload({"patientLast": "Secret", "sin": "S1", "last_title": "Doe", "first": "Jane", "comments": "Pending"})
    assert "patientLast" not in payload
    assert "sin" not in payload
    assert payload["current_last_title"] == "Doe"

