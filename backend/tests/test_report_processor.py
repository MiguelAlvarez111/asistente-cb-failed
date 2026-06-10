from pathlib import Path
from types import SimpleNamespace

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

    def fake_parse(path: Path) -> dict[str, AIInterpretation]:
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

    def fake_parse(path: Path) -> dict[str, AIInterpretation]:
        return {"CR-708f6ea9-9e63-45eb-8cab-21b8f83e1fd4": awaiting if path.name == "first.xlsx" else concrete}

    monkeypatch.setattr("backend.app.services.report_processor.parse_corrections", fake_parse)
    processor = ReportProcessor.__new__(ReportProcessor)

    corrections = processor._load_corrections([_correction_file("first.xlsx"), _correction_file("second.xlsx")])

    result = corrections["CR-708f6ea9-9e63-45eb-8cab-21b8f83e1fd4"]
    assert result.action == AIAction.CHANGE_TICKET
    assert result.target_npi == "1255593950"
    assert result.target_cbcode == "DN6835"
