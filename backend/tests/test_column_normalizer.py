import pandas as pd

from backend.app.services.column_normalizer import clean_scalar, normalize_dataframe, normalize_column_name


def test_column_variants_normalize() -> None:
    assert normalize_column_name("CB Code") == "cbcode"
    assert normalize_column_name("Last - Title") == "last_title"
    assert normalize_column_name("NPI_NUMBER") == "npi_number"
    assert normalize_column_name("LastName") == "last_name"


def test_values_are_cleaned() -> None:
    assert clean_scalar(" 123.0 ") == "123"
    assert clean_scalar("nan") == ""
    df = normalize_dataframe(pd.DataFrame({"CBCode": [" A  "], "NPI": ["123.0"]}))
    assert df.loc[0, "cbcode"] == "A"
    assert df.loc[0, "npi"] == "123"

