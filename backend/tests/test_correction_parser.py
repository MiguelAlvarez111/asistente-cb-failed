from backend.app.schemas.ai import AIAction, AIReasonCode
from backend.app.services.deterministic_interpreter import interpret_row


def test_chg_to_parsing() -> None:
    result = interpret_row({"npi": "CHG TO Jane Doe", "cbcode": "CB1", "comments": ""})
    assert result.action == AIAction.CHANGE_TICKET
    assert result.reason_code == AIReasonCode.CHG_TO
    assert result.target_provider_name == "Jane Doe"


def test_add_to_ge_parsing() -> None:
    result = interpret_row({"npi": "", "cbcode": "ADD TO GE 1234567890", "comments": ""})
    assert result.action == AIAction.ADD_TO_GE
    assert result.requires_add_to_ge is True
    assert result.target_npi == "1234567890"


def test_remove_from_ticket_parsing() -> None:
    result = interpret_row({"npi": "", "cbcode": "", "comments": "Remove from the ticket"})
    assert result.action == AIAction.REMOVE_FROM_TICKET
    assert result.reason_code == AIReasonCode.REMOVE_FROM_TICKET
