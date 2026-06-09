import pandas as pd

from backend.app.schemas.dictionaries import DictionaryType
from backend.app.schemas.results import FinalAction, ValidationStatus
from backend.app.services.correction_builder import AWAITING_USAP_CBCODE, CorrectionBuilder
from backend.app.services.decision_engine import choose_final_action
from backend.app.services.deterministic_interpreter import interpret_row
from backend.app.services.dictionary_loader import DictionaryIndex, LoadedDictionary
from backend.app.services.validator import validate_interpretation


def _dictionary(rows: list[dict[str, str]]) -> DictionaryIndex:
    return DictionaryIndex(
        [
            LoadedDictionary(
                filename="Referring Providers.txt",
                dictionary_type=DictionaryType.REFERRING_PROVIDERS,
                df=pd.DataFrame(rows),
            )
        ]
    )


def _run(row: dict[str, str], index: DictionaryIndex):
    interpretation = interpret_row(row)
    validation = validate_interpretation(interpretation, index, row)
    final_action, recommendation, needs_review = choose_final_action(interpretation, validation)
    instruction = CorrectionBuilder().build(row, interpretation, validation, final_action, recommendation, needs_review)
    return instruction, validation


def test_change_ticket_chg_to_with_cbcode_builds_recommended_fields() -> None:
    row = {"last_title": "ABUSOUFEH", "first": "RANA", "npi": "CHG TO JONES", "cbcode": "FK40", "comments": ""}
    index = _dictionary(
        [
            {
                "npi_number": "1689712655",
                "number": "FK40",
                "last_name": "JONES",
                "first_name": "DERRICK",
                "deactivation_flag": "",
            }
        ]
    )

    instruction, _ = _run(row, index)

    assert instruction.action == FinalAction.CHANGE_TICKET
    assert instruction.apply_this == "YES"
    assert instruction.recommended_last_title == "JONES"
    assert "DERRICK" in instruction.recommended_first
    assert instruction.recommended_npi == "1689712655"
    assert instruction.recommended_cbcode == "FK40"
    assert instruction.recommended_comments == "Change in the ticket"
    assert instruction.recommended_source == "Dictionary"
    assert instruction.cell_color_last_title == "red"
    assert instruction.cell_color_first == "red"
    assert instruction.cell_color_npi == "red"
    assert instruction.cell_color_cbcode == "red"
    assert instruction.cell_color_comments == "red"
    assert instruction.cell_color_source == "green"


def test_correct_provider_with_cbcode_builds_change_ticket_instruction() -> None:
    row = {"last_title": "OLD", "first": "PROVIDER", "npi": "", "cbcode": "", "comments": "Correct provider RAPHAELI MD,TAL with CB code H5290"}
    index = _dictionary(
        [
            {
                "npi_number": "1111111111",
                "number": "H5290",
                "last_name": "RAPHAELI",
                "first_name": "TAL",
                "deactivation_flag": "",
            }
        ]
    )

    instruction, _ = _run(row, index)

    assert instruction.action == FinalAction.CHANGE_TICKET
    assert instruction.apply_this == "YES"
    assert instruction.recommended_cbcode == "H5290"
    assert instruction.recommended_npi == "1111111111"
    assert instruction.recommended_source == "Dictionary"


def test_complete_missing_cbcode_from_dictionary(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.validator.get_npi_data", lambda npi: None)
    row = {"last_title": "JONES", "first": "DERRICK", "npi": "1689712655", "cbcode": "", "comments": ""}
    index = _dictionary(
        [
            {
                "npi_number": "1689712655",
                "number": "FK40",
                "last_name": "JONES",
                "first_name": "DERRICK",
                "deactivation_flag": "",
            }
        ]
    )

    instruction, _ = _run(row, index)

    assert instruction.action == FinalAction.COMPLETE_INFO
    assert instruction.apply_this == "YES"
    assert instruction.recommended_cbcode == "FK40"
    assert instruction.recommended_source == "Dictionary"
    assert instruction.cell_color_cbcode == "green"
    assert instruction.cell_color_source == "green"


def test_npi_registry_only_is_not_complete_info(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.validator.get_npi_data", lambda npi: {"full_name": "JONES, DERRICK", "npi": npi})
    row = {"last_title": "JONES", "first": "DERRICK", "npi": "1689712655", "cbcode": "", "comments": ""}

    instruction, validation = _run(row, DictionaryIndex([]))

    assert validation.status == ValidationStatus.NPI_FOUND
    assert instruction.action == FinalAction.AWAITING_USAP
    assert instruction.apply_this == "NO"
    assert instruction.recommended_cbcode == AWAITING_USAP_CBCODE
    assert instruction.cell_color_cbcode == "yellow"


def test_no_dictionary_match_routes_to_awaiting_usap() -> None:
    row = {"last_title": "UNKNOWN", "first": "PROVIDER", "npi": "", "cbcode": "", "comments": ""}

    instruction, _ = _run(row, DictionaryIndex([]))

    assert instruction.action == FinalAction.AWAITING_USAP
    assert instruction.apply_this == "NO"
    assert instruction.recommended_cbcode == AWAITING_USAP_CBCODE


def test_duplicate_effective_dictionary_matches_do_not_force_manual_review(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.validator.get_npi_data", lambda npi: None)
    dictionary = LoadedDictionary(
        filename="Referring Providers.txt",
        dictionary_type=DictionaryType.REFERRING_PROVIDERS,
        df=pd.DataFrame(
            [
                {"npi_number": "1689712655", "number": "FK40", "last_name": "JONES", "first_name": "DERRICK", "ba_mnemonic": "BA1", "deactivation_flag": ""},
                {"npi_number": "1689712655", "number": "FK40", "last_name": "JONES", "first_name": "DERRICK", "ba_mnemonic": "BA2", "deactivation_flag": ""},
            ]
        ),
    )
    row = {"last_title": "JONES", "first": "DERRICK", "npi": "1689712655", "cbcode": "", "comments": ""}

    instruction, validation = _run(row, DictionaryIndex([dictionary]))

    assert validation.status != ValidationStatus.MULTIPLE_MATCHES
    assert instruction.needs_manual_review is False


def test_conflicting_dictionary_matches_force_manual_review(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.validator.get_npi_data", lambda npi: None)
    dictionary = LoadedDictionary(
        filename="Referring Providers.txt",
        dictionary_type=DictionaryType.REFERRING_PROVIDERS,
        df=pd.DataFrame(
            [
                {"npi_number": "1689712655", "number": "FK40", "last_name": "JONES", "first_name": "DERRICK", "deactivation_flag": ""},
                {"npi_number": "1689712655", "number": "FK41", "last_name": "JONES", "first_name": "DERRICK", "deactivation_flag": ""},
            ]
        ),
    )
    row = {"last_title": "JONES", "first": "DERRICK", "npi": "1689712655", "cbcode": "", "comments": ""}

    instruction, validation = _run(row, DictionaryIndex([dictionary]))

    assert validation.status == ValidationStatus.MULTIPLE_MATCHES
    assert instruction.action == FinalAction.MANUAL_REVIEW
    assert instruction.needs_manual_review is True


def test_remove_from_ticket_instruction() -> None:
    row = {"last_title": "DOE", "first": "JANE", "npi": "", "cbcode": "", "comments": "Remove from the ticket"}

    instruction, _ = _run(row, DictionaryIndex([]))

    assert instruction.action == FinalAction.REMOVE_FROM_TICKET
    assert instruction.apply_this == "NO"
    assert instruction.needs_manual_review is True
    assert instruction.recommended_comments == "Remove from the ticket"


def test_instruction_does_not_include_phi() -> None:
    row = {
        "last_title": "DOE",
        "first": "JANE",
        "npi": "",
        "cbcode": "",
        "comments": "",
        "patientLast": "SECRET",
        "patientFirst": "PERSON",
        "DOB": "1/1/2000",
        "AccNumber": "A1",
        "sin": "S1",
    }

    instruction, _ = _run(row, DictionaryIndex([]))
    dumped = instruction.model_dump_json()

    assert "SECRET" not in dumped
    assert "PERSON" not in dumped
    assert "1/1/2000" not in dumped
    assert "A1" not in dumped
    assert "S1" not in dumped
