from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from backend.app.core.config import Settings
from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode
from backend.app.schemas.files import FileKind
from backend.app.services.report_processor import ReportProcessor


def _interpretation(
    action: AIAction,
    reason_code: AIReasonCode,
    *,
    provider_name: str | None = None,
    npi: str | None = None,
    cbcode: str | None = None,
) -> AIInterpretation:
    return AIInterpretation(
        action=action,
        reason_code=reason_code,
        target_provider_name=provider_name,
        target_npi=npi,
        target_cbcode=cbcode,
        requires_add_to_ge=action == AIAction.ADD_TO_GE,
        is_pending_usap=action == AIAction.AWAITING_USAP,
        confidence=1,
        needs_manual_review=False,
        explanation=reason_code.value,
    )


def _correction_file(path: str):
    return SimpleNamespace(path=path, inspection=SimpleNamespace(kind=FileKind.CORRECTIONS))


def test_load_corrections_keeps_concrete_over_later_generic_awaiting(monkeypatch) -> None:
    concrete = _interpretation(
        AIAction.CHANGE_TICKET,
        AIReasonCode.CORRECT_PROVIDER_CB,
        provider_name="MANI MD,PREETHI",
        cbcode="TX22898",
    )
    awaiting = _interpretation(AIAction.AWAITING_USAP, AIReasonCode.AWAITING_USAP)

    def fake_parse(path: Path, **_) -> dict[str, AIInterpretation]:
        return {"ME-ce26d01d-bd0b-48e3-8ba1-8a7f40164269": concrete if path.name == "first.xlsx" else awaiting}

    monkeypatch.setattr("backend.app.services.report_processor.parse_corrections", fake_parse)
    processor = ReportProcessor.__new__(ReportProcessor)

    corrections = processor._load_corrections([_correction_file("first.xlsx"), _correction_file("second.xlsx")])

    result = corrections["ME-ce26d01d-bd0b-48e3-8ba1-8a7f40164269"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_cbcode == "TX22898"


def test_load_corrections_replaces_generic_awaiting_with_later_concrete(monkeypatch) -> None:
    awaiting = _interpretation(AIAction.AWAITING_USAP, AIReasonCode.AWAITING_USAP)
    concrete = _interpretation(
        AIAction.CHANGE_TICKET,
        AIReasonCode.CORRECT_PROVIDER_NPI,
        npi="1255593950",
        cbcode="DN6835",
    )

    def fake_parse(path: Path, **_) -> dict[str, AIInterpretation]:
        return {"CR-708f6ea9-9e63-45eb-8cab-21b8f83e1fd4": awaiting if path.name == "first.xlsx" else concrete}

    monkeypatch.setattr("backend.app.services.report_processor.parse_corrections", fake_parse)
    processor = ReportProcessor.__new__(ReportProcessor)

    corrections = processor._load_corrections([_correction_file("first.xlsx"), _correction_file("second.xlsx")])

    result = corrections["CR-708f6ea9-9e63-45eb-8cab-21b8f83e1fd4"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_npi == "1255593950"
    assert result.target_cbcode == "DN6835"


def test_load_corrections_uses_ai_for_generic_awaiting_with_free_text(tmp_path, monkeypatch) -> None:
    path = tmp_path / "corrections.xlsx"
    pd.DataFrame(
        [
            {
                "Type": "Surgeon",
                "Last - Title": "ROWLEY",
                "First": "MICHAEL WILLIAM",
                "NPI": "1801916341",
                "CBcode": "Awaiting for USAP’s Confirmation",
                "Comments": "Please use the replacement target mentioned by USAP.",
                "Source": "USAP",
                "SIN": "CR-hidden-test",
                "patientLast": "Secret",
                "patientFirst": "Person",
                "DOB": "1950-01-01",
                "AccNumber": "A1",
            }
        ]
    ).to_excel(path, index=False)
    settings = Settings()
    settings.ai_enabled = True
    settings.openai_api_key = "test"
    processor = ReportProcessor(settings)
    captured_payloads: list[dict[str, str]] = []

    def fake_interpret(payload):
        captured_payloads.append(payload)
        return (
            _interpretation(
                AIAction.CHANGE_TICKET,
                AIReasonCode.CORRECT_PROVIDER_NPI,
                npi="1255593950",
                cbcode="DN6835",
            ),
            "test-model",
            42,
        )

    monkeypatch.setattr(processor.ai, "interpret", fake_interpret)

    corrections = processor._load_corrections([_correction_file(str(path))])

    result = corrections["CR-hidden-test"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_npi == "1255593950"
    assert result.target_cbcode == "DN6835"
    assert processor._ai_usage_rows == 1
    assert processor._ai_usage_tokens == 42
    assert processor._ai_usage_models == {"test-model"}
    assert captured_payloads
    assert "sin" not in captured_payloads[0]
    assert "patientLast" not in captured_payloads[0]
    assert "patientFirst" not in captured_payloads[0]
    assert "DOB" not in captured_payloads[0]
    assert "AccNumber" not in captured_payloads[0]


def test_load_corrections_uses_ai_for_free_text_correct_npi_cbcode(tmp_path, monkeypatch) -> None:
    path = tmp_path / "colorado.xlsx"
    pd.DataFrame(
        [
            {
                "Type": "Surgeon",
                "Last - Title": "ROWLEY",
                "First": "MICHAEL WILLIAM",
                "NPI": "1801916341",
                "CBcode": "Awaiting for USAP’s Confirmation",
                "Comments": "Correct NPI 1255593950 with DN6835. One you provided on this report is for an anesthesia MD in Florida.",
                "Source": "USAP",
                "SIN": "CR-colorado",
            }
        ]
    ).to_excel(path, index=False)
    settings = Settings()
    settings.ai_enabled = True
    settings.openai_api_key = "test"
    processor = ReportProcessor(settings)

    def fake_interpret(payload):
        assert "sin" not in payload
        assert payload["comments"].startswith("Correct NPI")
        return (
            _interpretation(
                AIAction.CHANGE_TICKET,
                AIReasonCode.CORRECT_PROVIDER_NPI,
                npi="1255593950",
                cbcode="DN6835",
            ),
            "test-model",
            50,
        )

    monkeypatch.setattr(processor.ai, "interpret", fake_interpret)

    corrections = processor._load_corrections([_correction_file(str(path))])

    result = corrections["CR-colorado"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_npi == "1255593950"
    assert result.target_cbcode == "DN6835"
