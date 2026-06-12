from backend.app.schemas.ai import AIAction, AIReasonCode
from backend.app.services.deterministic_interpreter import interpret_row


def test_chg_to_parsing() -> None:
    result = interpret_row({"npi": "CHG TO Jane Doe", "cbcode": "CB1", "comments": ""})
    assert result.action == AIAction.CHANGE_TICKET
    assert result.reason_code == AIReasonCode.CHG_TO
    assert result.target_provider_name == "Jane Doe"


def test_chg_to_ignores_awaiting_placeholder_cbcode() -> None:
    result = interpret_row(
        {
            "npi": "CHG TO WING",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "",
        }
    )

    assert result.action == AIAction.CHANGE_TICKET
    assert result.reason_code == AIReasonCode.CHG_TO
    assert result.target_provider_name == "WING"
    assert result.target_cbcode is None


def test_add_to_ge_parsing() -> None:
    result = interpret_row({"npi": "", "cbcode": "ADD TO GE 1234567890", "comments": ""})
    assert result.action == AIAction.ADD_TO_GE
    assert result.requires_add_to_ge is True
    assert result.target_npi == "1234567890"


def test_chg_to_wins_over_add_to_ge_pending_npi() -> None:
    result = interpret_row(
        {
            "npi": "CHG TO SHAH",
            "cbcode": "ADD TO GE 1609175306",
            "comments": "",
        }
    )

    assert result.action == AIAction.CHANGE_TICKET
    assert result.reason_code == AIReasonCode.CHG_TO
    assert result.target_provider_name == "SHAH"
    assert result.target_npi == "1609175306"
    assert result.target_cbcode is None
    assert result.requires_add_to_ge is False
    assert result.is_pending_usap is True


def test_chg_to_with_pending_cbcode_text_extracts_target_npi() -> None:
    result = interpret_row(
        {
            "npi": "CHG TO SHAH",
            "cbcode": "NO TENEMOS CB CODE AUN. NPI CORRECTO 1609175306",
            "comments": "",
        }
    )

    assert result.action == AIAction.CHANGE_TICKET
    assert result.reason_code == AIReasonCode.CHG_TO
    assert result.target_provider_name == "SHAH"
    assert result.target_npi == "1609175306"
    assert result.target_cbcode is None
    assert result.is_pending_usap is True


def test_remove_from_ticket_parsing() -> None:
    result = interpret_row({"npi": "", "cbcode": "", "comments": "Remove from the ticket"})
    assert result.action == AIAction.REMOVE_FROM_TICKET
    assert result.reason_code == AIReasonCode.REMOVE_FROM_TICKET


def test_correct_provider_free_text_defers_to_ai_review() -> None:
    result = interpret_row(
        {
            "npi": "1952805236",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "Correct provider MANI MD,PREETHI with CB code TX22898",
        }
    )

    assert result.action == AIAction.AWAITING_USAP
    assert result.reason_code == AIReasonCode.AWAITING_USAP
    assert result.target_provider_name is None
    assert result.target_cbcode is None


def test_correct_npi_with_cbcode_free_text_defers_to_ai_review() -> None:
    result = interpret_row(
        {
            "npi": "1801916341",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "Correct NPI 1255593950 with CB code DN6835",
        }
    )

    assert result.action == AIAction.AWAITING_USAP
    assert result.reason_code == AIReasonCode.AWAITING_USAP
    assert result.target_npi is None
    assert result.target_cbcode is None


def test_correct_npi_with_implicit_cbcode_free_text_defers_to_ai_review() -> None:
    result = interpret_row(
        {
            "npi": "1801916341",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "Correct NPI 1255593950 with DN6835. One you provided on this report is for an anesthesia MD in Florida.",
        }
    )

    assert result.action == AIAction.AWAITING_USAP
    assert result.reason_code == AIReasonCode.AWAITING_USAP
    assert result.target_npi is None
    assert result.target_cbcode is None


def test_pending_confirmation_stays_awaiting() -> None:
    result = interpret_row(
        {
            "npi": "1598709719",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "Pending confirmation of correct provider",
        }
    )

    assert result.action == AIAction.AWAITING_USAP
    assert result.reason_code == AIReasonCode.PENDING_USAP


def test_pending_addition_with_provider_npi_defers_to_ai_review() -> None:
    result = interpret_row(
        {
            "npi": "1174967541",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "Pending addition of correct provider COLE MD,JUSTIN BRYON with NPI 1073003075",
        }
    )

    assert result.action == AIAction.AWAITING_USAP
    assert result.reason_code == AIReasonCode.PENDING_USAP
    assert result.target_provider_name is None
    assert result.target_npi is None


def test_correct_provider_with_npi_free_text_defers_to_ai_review() -> None:
    result = interpret_row(
        {
            "npi": "1467778795",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "Correct provider ELSBERND MD,BENJAMIN LAWRENCE with NPI 1487073748",
        }
    )

    assert result.action == AIAction.AWAITING_USAP
    assert result.reason_code == AIReasonCode.AWAITING_USAP
    assert result.target_provider_name is None
    assert result.target_npi is None


def test_correct_provider_with_npi_without_name_defers_to_ai_review() -> None:
    result = interpret_row(
        {
            "npi": "1467778795",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "Correct provider with NPI 1487073748",
        }
    )

    assert result.action == AIAction.AWAITING_USAP
    assert result.target_provider_name is None
    assert result.target_npi is None


def test_correct_provider_with_npi_and_cbcode_defers_to_ai_review() -> None:
    result = interpret_row(
        {
            "npi": "1104867365",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "Correct provider GEORGE DPM,THOMAS with NPI 1770169542 and CB code TX23195",
        }
    )

    assert result.action == AIAction.AWAITING_USAP
    assert result.reason_code == AIReasonCode.AWAITING_USAP
    assert result.target_provider_name is None
    assert result.target_npi is None
    assert result.target_cbcode is None


def test_double_npi_usap_change_extracts_second_npi_as_pending_target() -> None:
    result = interpret_row(
        {
            "type": "Surgeon",
            "last_title": "MORELAND COLE",
            "first": "JUSTIN PATRICK JUSTIN",
            "npi": "1174967541 1073003075",
            "cbcode": "Awaiting for USAP’s Confirmation",
            "comments": "Change in the ticket",
            "source": "USAP",
        }
    )

    assert result.action == AIAction.CHANGE_TICKET
    assert result.reason_code == AIReasonCode.USAP_PENDING_CBCODE
    assert result.is_pending_usap is True
    assert result.target_npi == "1073003075"
    assert result.target_provider_name == "COLE,JUSTIN"


def test_provider_missing_fields_requests_name_lookup() -> None:
    result = interpret_row(
        {
            "type": "Provider",
            "last_title": "Edmunds",
            "first": "Alisa",
            "npi": "",
            "cbcode": "",
            "comments": "",
            "source": "",
        }
    )

    assert result.action == AIAction.COMPLETE_INFO
    assert result.reason_code == AIReasonCode.PROVIDER_NAME_LOOKUP
    assert result.target_provider_name == "Edmunds Alisa"
