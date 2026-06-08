import pandas as pd

from backend.app.schemas.dictionaries import DictionaryType
from backend.app.services.dictionary_loader import DictionaryIndex, LoadedDictionary


def test_lookup_uses_prov_mnemonic_for_usap_providers() -> None:
    dictionary = LoadedDictionary(
        filename="USAP Providers.txt",
        dictionary_type=DictionaryType.USAP_PROVIDERS,
        df=pd.DataFrame(
            [
                {
                    "npi_number": "1111111111",
                    "prov_mnemonic": "CB123",
                    "ba_mnemonic": "BA1",
                    "last_name": "Doe",
                    "first_name": "Jane",
                    "deactivation_flag": "",
                }
            ]
        ),
    )
    matches = DictionaryIndex([dictionary]).lookup(cbcode="CB123")
    assert matches[0].cbcode == "CB123"
    assert matches[0].dictionary_type == DictionaryType.USAP_PROVIDERS


def test_lookup_uses_number_for_referring_providers() -> None:
    dictionary = LoadedDictionary(
        filename="Referring Providers.txt",
        dictionary_type=DictionaryType.REFERRING_PROVIDERS,
        df=pd.DataFrame(
            [
                {
                    "npi_number": "2222222222",
                    "number": "9876",
                    "last_name": "Smith",
                    "first_name": "Alex",
                    "deactivation_flag": "",
                }
            ]
        ),
    )
    matches = DictionaryIndex([dictionary]).lookup(npi="2222222222")
    assert matches[0].cbcode == "9876"

