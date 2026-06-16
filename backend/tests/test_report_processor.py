from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from backend.app.core.config import Settings
from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode
from backend.app.schemas.files import FileKind
from backend.app.services.correction_parser import ParsedCorrection
from backend.app.services.report_processor import ReportProcessor, _normalize_interpretation_targets, _promote_direct_column_replacement


def _interpretation(
    action: AIAction,
    reason_code: AIReasonCode,
    *,
    provider_name: str | None = None,
    npi: str | None = None,
    cbcode: str | None = None,
    pending: bool = False,
) -> AIInterpretation:
    return AIInterpretation(
        action=action,
        reason_code=reason_code,
        target_provider_name=provider_name,
        target_npi=npi,
        target_cbcode=cbcode,
        requires_add_to_ge=action == AIAction.ADD_TO_GE,
        is_pending_usap=pending or action == AIAction.AWAITING_USAP,
        confidence=1,
        needs_manual_review=False,
        explanation=reason_code.value,
    )


def _correction_file(path: str):
    return SimpleNamespace(path=path, inspection=SimpleNamespace(kind=FileKind.CORRECTIONS))


def _parsed(interpretation: AIInterpretation, row: dict[str, str] | None = None) -> ParsedCorrection:
    return ParsedCorrection(interpretation=interpretation, row=row or {})


def test_load_corrections_keeps_concrete_over_later_generic_awaiting(monkeypatch) -> None:
    concrete = _interpretation(
        AIAction.CHANGE_TICKET,
        AIReasonCode.CORRECT_PROVIDER_CB,
        provider_name="MANI MD,PREETHI",
        cbcode="TX22898",
    )
    awaiting = _interpretation(AIAction.AWAITING_USAP, AIReasonCode.AWAITING_USAP)

    def fake_parse(path: Path, **_) -> dict[str, ParsedCorrection]:
        return {"ME-ce26d01d-bd0b-48e3-8ba1-8a7f40164269": _parsed(concrete if path.name == "first.xlsx" else awaiting)}

    monkeypatch.setattr("backend.app.services.report_processor.parse_correction_records", fake_parse)
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

    def fake_parse(path: Path, **_) -> dict[str, ParsedCorrection]:
        return {"CR-708f6ea9-9e63-45eb-8cab-21b8f83e1fd4": _parsed(awaiting if path.name == "first.xlsx" else concrete)}

    monkeypatch.setattr("backend.app.services.report_processor.parse_correction_records", fake_parse)
    processor = ReportProcessor.__new__(ReportProcessor)

    corrections = processor._load_corrections([_correction_file("first.xlsx"), _correction_file("second.xlsx")])

    result = corrections["CR-708f6ea9-9e63-45eb-8cab-21b8f83e1fd4"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_npi == "1255593950"
    assert result.target_cbcode == "DN6835"


def test_load_corrections_keeps_complete_info_over_awaiting_with_ai_extracted_target(monkeypatch) -> None:
    complete = _interpretation(AIAction.COMPLETE_INFO, AIReasonCode.DIRECT_CBCODE, cbcode="TX25093")
    awaiting_with_target = _interpretation(
        AIAction.AWAITING_USAP,
        AIReasonCode.AWAITING_USAP,
        provider_name="JOSEPH SEUNGHYUN LIM",
        npi="1740817303",
    )

    def fake_parse(path: Path, **_) -> dict[str, ParsedCorrection]:
        return {"EX-de6d8a70-d2e0-41d5-839e-2999fdc08589": _parsed(complete if path.name == "dfw.xlsx" else awaiting_with_target)}

    monkeypatch.setattr("backend.app.services.report_processor.parse_correction_records", fake_parse)
    processor = ReportProcessor.__new__(ReportProcessor)

    corrections = processor._load_corrections([_correction_file("dfw.xlsx"), _correction_file("fl.xlsx")])

    result = corrections["EX-de6d8a70-d2e0-41d5-839e-2999fdc08589"]
    assert result.action == AIAction.COMPLETE_INFO
    assert result.target_cbcode == "TX25093"


def test_load_corrections_add_to_ge_does_not_replace_more_specific_correction(monkeypatch) -> None:
    change_ticket = _interpretation(AIAction.CHANGE_TICKET, AIReasonCode.CHG_TO, provider_name="JONES", cbcode="FK40")
    add_to_ge = _interpretation(AIAction.ADD_TO_GE, AIReasonCode.ADD_TO_GE, npi="1689712655")

    def fake_parse(path: Path, **_) -> dict[str, ParsedCorrection]:
        return {"JQ-ticket": _parsed(change_ticket if path.name == "first.xlsx" else add_to_ge)}

    monkeypatch.setattr("backend.app.services.report_processor.parse_correction_records", fake_parse)
    processor = ReportProcessor.__new__(ReportProcessor)

    corrections = processor._load_corrections([_correction_file("first.xlsx"), _correction_file("second.xlsx")])

    result = corrections["JQ-ticket"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_provider_name == "JONES"
    assert result.target_cbcode == "FK40"


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


def test_ai_action_preserves_deterministic_cbcode_target(tmp_path, monkeypatch) -> None:
    path = tmp_path / "preserve_cbcode.xlsx"
    pd.DataFrame(
        [
            {
                "Type": "Surgeon",
                "Last - Title": "CHOU",
                "First": "JEFF DANIEL",
                "NPI": "1154360857",
                "CBcode": "TX25094",
                "Comments": "Correct name per license is DONOHOE MD,AMANDA CARLSON",
                "Source": "",
                "SIN": "SIN-preserve-cbcode",
            }
        ]
    ).to_excel(path, index=False)
    settings = Settings()
    settings.ai_enabled = True
    settings.openai_api_key = "test"
    processor = ReportProcessor(settings)

    def fake_interpret(payload):
        assert payload["cbcode_field"] == "TX25094"
        return (
            _interpretation(
                AIAction.CHANGE_TICKET,
                AIReasonCode.CORRECT_PROVIDER_CB,
                provider_name="DONOHOE MD,AMANDA CARLSON",
            ),
            "test-model",
            25,
        )

    monkeypatch.setattr(processor.ai, "interpret", fake_interpret)

    corrections = processor._load_corrections([_correction_file(str(path))])

    result = corrections["SIN-preserve-cbcode"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_provider_name == "DONOHOE MD,AMANDA CARLSON"
    assert result.target_cbcode == "TX25094"


def test_ai_action_preserves_deterministic_npi_target(tmp_path, monkeypatch) -> None:
    path = tmp_path / "preserve_npi.xlsx"
    pd.DataFrame(
        [
            {
                "Type": "Surgeon",
                "Last - Title": "FREIBERG",
                "First": "STEPHEN L",
                "NPI": "1609175306",
                "CBcode": "",
                "Comments": "please change ticket to SHAH, cb not created yet",
                "Source": "",
                "SIN": "SIN-preserve-npi",
            }
        ]
    ).to_excel(path, index=False)
    settings = Settings()
    settings.ai_enabled = True
    settings.openai_api_key = "test"
    processor = ReportProcessor(settings)

    def fake_interpret(payload):
        assert payload["npi_field"] == "1609175306"
        return (
            _interpretation(
                AIAction.CHANGE_TICKET,
                AIReasonCode.CORRECT_PROVIDER_NPI,
                provider_name="SHAH",
            ),
            "test-model",
            25,
        )

    monkeypatch.setattr(processor.ai, "interpret", fake_interpret)

    corrections = processor._load_corrections([_correction_file(str(path))])

    result = corrections["SIN-preserve-npi"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_provider_name == "SHAH"
    assert result.target_npi == "1609175306"


def test_target_normalization_moves_10_digit_cbcode_to_npi_for_change_intent() -> None:
    row = {
        "npi": "CHG TO MAKIA",
        "cbcode": "ADD TO GE 1629271002",
        "comments": "",
        "source": "",
    }
    interpretation = _interpretation(
        AIAction.CHANGE_TICKET,
        AIReasonCode.CHG_TO,
        provider_name="MAKIA",
        cbcode="1629271002",
    )

    result = _normalize_interpretation_targets(row, interpretation)

    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_provider_name == "MAKIA"
    assert result.target_npi == "1629271002"
    assert result.target_cbcode is None
    assert result.requires_add_to_ge is False
    assert result.is_pending_usap is True


def test_target_normalization_keeps_pure_add_to_ge_as_awaiting_setup() -> None:
    row = {
        "npi": "1376777342",
        "cbcode": "ADD TO GE",
        "comments": "",
        "source": "",
    }
    interpretation = _interpretation(
        AIAction.CHANGE_TICKET,
        AIReasonCode.CHG_TO,
        npi="1376777342",
        pending=True,
    )

    result = _normalize_interpretation_targets(row, interpretation)

    assert result.action == AIAction.ADD_TO_GE
    assert result.reason_code == AIReasonCode.ADD_TO_GE_NPI
    assert result.target_npi == "1376777342"
    assert result.target_cbcode is None
    assert result.requires_add_to_ge is True
    assert result.is_pending_usap is False


def test_target_normalization_turns_correct_provider_addition_into_pending_change_ticket() -> None:
    row = {
        "npi": "1497169239",
        "cbcode": "Awaiting for USAP’s Confirmation",
        "comments": "Pending addition of correct provider GUPTA MD,RAJESH KUMAR with NPI 1558674747",
        "source": "",
    }
    interpretation = _interpretation(
        AIAction.ADD_TO_GE,
        AIReasonCode.PENDING_USAP,
        provider_name="GUPTA MD,RAJESH KUMAR",
        npi="1558674747",
    )

    result = _normalize_interpretation_targets(row, interpretation)

    assert result.action == AIAction.CHANGE_TICKET
    assert result.reason_code == AIReasonCode.CORRECT_PROVIDER_NPI
    assert result.target_provider_name == "GUPTA MD,RAJESH KUMAR"
    assert result.target_npi == "1558674747"
    assert result.target_cbcode is None
    assert result.requires_add_to_ge is False
    assert result.is_pending_usap is True


def test_direct_column_replacement_promotes_complete_info_to_change_ticket() -> None:
    original_row = {
        "type": "Surgeon",
        "last_title": "RODNEY",
        "first": "NATASHA A",
        "npi": "1306105093",
        "cbcode": "",
    }
    correction_row = {
        "type": "Surgeon",
        "last_title": "MAKIA",
        "first": "ARETHA N",
        "npi": "1629271002",
        "cbcode": "MD9071",
        "comments": "CORRECTING NAME IN GE",
    }
    interpretation = _interpretation(AIAction.COMPLETE_INFO, AIReasonCode.DIRECT_CBCODE, cbcode="MD9071")

    result = _promote_direct_column_replacement(original_row, correction_row, interpretation)

    assert result.action == AIAction.CHANGE_TICKET
    assert result.reason_code == AIReasonCode.CHANGE_IN_TICKET
    assert result.target_provider_name == "MAKIA ARETHA N"
    assert result.target_npi == "1629271002"
    assert result.target_cbcode == "MD9071"


def test_direct_column_replacement_keeps_same_npi_as_complete_info() -> None:
    original_row = {
        "type": "Surgeon",
        "last_title": "MURPHY",
        "first": "HEATHER",
        "npi": "1376777342",
        "cbcode": "",
    }
    correction_row = {
        "type": "Surgeon",
        "last_title": "MURPHY",
        "first": "HEATHER MARIE",
        "npi": "1376777342",
        "cbcode": "MD9072",
    }
    interpretation = _interpretation(AIAction.COMPLETE_INFO, AIReasonCode.DIRECT_CBCODE, cbcode="MD9072")

    result = _promote_direct_column_replacement(original_row, correction_row, interpretation)

    assert result.action == AIAction.COMPLETE_INFO
    assert result.target_cbcode == "MD9072"


def test_ai_bad_target_cbcode_npi_is_normalized_before_correction_merge(tmp_path, monkeypatch) -> None:
    path = tmp_path / "add_to_ge_npi.xlsx"
    pd.DataFrame(
        [
            {
                "Type": "Surgeon",
                "Last - Title": "JOSEPH",
                "First": "DANIA",
                "NPI": "CHG TO MAKIA",
                "CBcode": "ADD TO GE 1629271002",
                "Comments": "",
                "Source": "",
                "SIN": "SIN-add-to-ge-npi",
            }
        ]
    ).to_excel(path, index=False)
    settings = Settings()
    settings.ai_enabled = True
    settings.openai_api_key = "test"
    processor = ReportProcessor(settings)

    def fake_interpret(payload):
        return (
            _interpretation(
                AIAction.CHANGE_TICKET,
                AIReasonCode.CHG_TO,
                provider_name="MAKIA",
                cbcode="1629271002",
            ),
            "test-model",
            25,
        )

    monkeypatch.setattr(processor.ai, "interpret", fake_interpret)

    corrections = processor._load_corrections([_correction_file(str(path))])

    result = corrections["SIN-add-to-ge-npi"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_provider_name == "MAKIA"
    assert result.target_npi == "1629271002"
    assert result.target_cbcode is None
    assert result.is_pending_usap is True


def test_ai_direct_npi_with_free_text_change_intent_becomes_change_ticket(tmp_path, monkeypatch) -> None:
    path = tmp_path / "free_text_change_npi.xlsx"
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
                "SIN": "SIN-free-text-change",
            }
        ]
    ).to_excel(path, index=False)
    settings = Settings()
    settings.ai_enabled = True
    settings.openai_api_key = "test"
    processor = ReportProcessor(settings)

    def fake_interpret(payload):
        assert payload["npi_field"] == "make change to SHAH"
        assert payload["cbcode_field"] == "el right NPI es 1609175306"
        return (
            _interpretation(
                AIAction.COMPLETE_INFO,
                AIReasonCode.DIRECT_NPI,
                npi="1609175306",
            ),
            "test-model",
            25,
        )

    monkeypatch.setattr(processor.ai, "interpret", fake_interpret)

    corrections = processor._load_corrections([_correction_file(str(path))])

    result = corrections["SIN-free-text-change"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.reason_code == AIReasonCode.CORRECT_PROVIDER_NPI
    assert result.target_npi == "1609175306"
    assert result.is_pending_usap is True


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


def test_plain_awaiting_placeholder_does_not_call_ai(tmp_path, monkeypatch) -> None:
    path = tmp_path / "plain_awaiting.xlsx"
    pd.DataFrame(
        [
            {
                "Type": "Surgeon",
                "Last - Title": "FREIBERG",
                "First": "STEPHEN L",
                "NPI": "1922445857",
                "CBcode": "Awaiting for USAP’s Confirmation",
                "Comments": "",
                "Source": "",
                "SIN": "SIN-plain-awaiting",
            }
        ]
    ).to_excel(path, index=False)
    settings = Settings()
    settings.ai_enabled = True
    settings.openai_api_key = "test"
    processor = ReportProcessor(settings)

    def fail_interpret(payload):
        raise AssertionError(f"AI should not be called for plain awaiting placeholder: {payload}")

    monkeypatch.setattr(processor.ai, "interpret", fail_interpret)

    corrections = processor._load_corrections([_correction_file(str(path))])

    result = corrections["SIN-plain-awaiting"]
    assert result.action == AIAction.AWAITING_USAP
    assert processor._ai_usage_rows == 0
