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


def test_load_corrections_uses_ai_for_weird_free_text_in_operational_fields(tmp_path, monkeypatch) -> None:
    path = tmp_path / "weird_text.xlsx"
    rows = [
        {
            "Type": "Surgeon",
            "Last - Title": "FREIBERG",
            "First": "STEPHEN L",
            "NPI": "make change to SHAH",
            "CBcode": "el right NPI es 1609175306",
            "Comments": "",
            "Source": "",
            "SIN": "SIN-weird-npi-cbcode",
        },
        {
            "Type": "Surgeon",
            "Last - Title": "FREIBERG",
            "First": "STEPHEN L",
            "NPI": "change surgeon to SHAH",
            "CBcode": "",
            "Comments": "correct npi should be 1609175306",
            "Source": "",
            "SIN": "SIN-weird-npi-comments",
        },
        {
            "Type": "Surgeon",
            "Last - Title": "FREIBERG",
            "First": "STEPHEN L",
            "NPI": "",
            "CBcode": "no tenemos cb code aun",
            "Comments": "right NPI 1609175306 for SHAH",
            "Source": "",
            "SIN": "SIN-weird-cbcode-comments",
        },
        {
            "Type": "Surgeon",
            "Last - Title": "FREIBERG",
            "First": "STEPHEN L",
            "NPI": "",
            "CBcode": "",
            "Comments": "",
            "Source": "USAP said use NPI 1609175306, CB pending",
            "SIN": "SIN-weird-source",
        },
        {
            "Type": "Surgeon",
            "Last - Title": "FREIBERG",
            "First": "STEPHEN L",
            "NPI": "",
            "CBcode": "",
            "Comments": "please change ticket to SHAH, npi is 1609175306, cb not created yet",
            "Source": "",
            "SIN": "SIN-weird-comments",
        },
    ]
    for row in rows:
        row.update(
            {
                "patientLast": "Secret",
                "patientFirst": "Person",
                "DOB": "1950-01-01",
                "AccNumber": "A1",
            }
        )
    pd.DataFrame(rows).to_excel(path, index=False)
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
                provider_name="SHAH",
                npi="1609175306",
            ),
            "test-model",
            30,
        )

    monkeypatch.setattr(processor.ai, "interpret", fake_interpret)

    corrections = processor._load_corrections([_correction_file(str(path))])

    assert set(corrections) == {str(row["SIN"]) for row in rows}
    assert processor._ai_usage_rows == len(rows)
    assert processor._ai_usage_tokens == 30 * len(rows)
    assert len(captured_payloads) == len(rows)
    for payload in captured_payloads:
        assert "sin" not in payload
        assert "patientLast" not in payload
        assert "patientFirst" not in payload
        assert "DOB" not in payload
        assert "AccNumber" not in payload
    for result in corrections.values():
        assert result.action == AIAction.CHANGE_TICKET
        assert result.target_provider_name == "SHAH"
        assert result.target_npi == "1609175306"


def test_ai_disabled_free_text_fallback_does_not_invent_direct_cbcode(tmp_path) -> None:
    path = tmp_path / "ai_disabled.xlsx"
    pd.DataFrame(
        [
            {
                "Type": "Surgeon",
                "Last - Title": "FREIBERG",
                "First": "STEPHEN L",
                "NPI": "make change to SHAH",
                "CBcode": "el right NPI es 1609175306",
                "Comments": "",
                "Source": "",
                "SIN": "SIN-ai-disabled",
            }
        ]
    ).to_excel(path, index=False)
    settings = Settings()
    settings.ai_enabled = False
    processor = ReportProcessor(settings)

    corrections = processor._load_corrections([_correction_file(str(path))])

    result = corrections["SIN-ai-disabled"]
    assert result.action == AIAction.UNKNOWN
    assert result.reason_code == AIReasonCode.NO_SIGNAL
    assert result.target_cbcode is None
