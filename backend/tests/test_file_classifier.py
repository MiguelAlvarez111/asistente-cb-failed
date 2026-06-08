import pandas as pd

from backend.app.schemas.dictionaries import DictionaryType
from backend.app.services.column_normalizer import normalize_dataframe
from backend.app.services.file_classifier import detect_dictionary


def test_usap_providers_detected_by_columns() -> None:
    df = normalize_dataframe(pd.DataFrame(columns=["NAME", "NPI_NUMBER", "ProvMnemonic", "BA_MNEMONIC"]))
    detection = detect_dictionary(df)
    assert detection.detected_type == DictionaryType.USAP_PROVIDERS
    assert detection.missing_columns == []


def test_referring_providers_detected_by_columns() -> None:
    df = normalize_dataframe(pd.DataFrame(columns=["NAME", "NUMBER", "NPI_NUMBER", "Lastname", "Firstname"]))
    detection = detect_dictionary(df)
    assert detection.detected_type == DictionaryType.REFERRING_PROVIDERS

