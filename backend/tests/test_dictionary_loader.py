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


def test_lookup_provider_name_normalizes_degree_and_comma() -> None:
    dictionary = LoadedDictionary(
        filename="USAP Providers.txt",
        dictionary_type=DictionaryType.USAP_PROVIDERS,
        df=pd.DataFrame(
            [
                {
                    "npi_number": "1134782147",
                    "prov_mnemonic": "TEDAJ",
                    "last_name": "EDMUNDS",
                    "first_name": "ALISA",
                    "middle_name": "JO",
                    "deactivation_flag": "",
                }
            ]
        ),
    )

    matches = DictionaryIndex([dictionary]).lookup(provider_name="EDMUNDS, ALISA", dictionary_types={DictionaryType.USAP_PROVIDERS})

    assert len(matches) == 1
    assert matches[0].npi == "1134782147"
    assert matches[0].cbcode == "TEDAJ"


def test_lookup_provider_name_allows_extra_system_name_tokens() -> None:
    dictionary = LoadedDictionary(
        filename="USAP Providers.txt",
        dictionary_type=DictionaryType.USAP_PROVIDERS,
        df=pd.DataFrame(
            [
                {
                    "npi_number": "1932369964",
                    "prov_mnemonic": "TSESH",
                    "last_name": "SEGAN",
                    "first_name": "SHIVANI",
                    "deactivation_flag": "",
                }
            ]
        ),
    )

    matches = DictionaryIndex([dictionary]).lookup(provider_name="Segan Shivani Pj", dictionary_types={DictionaryType.USAP_PROVIDERS})

    assert len(matches) == 1
    assert matches[0].npi == "1932369964"
    assert matches[0].cbcode == "TSESH"
