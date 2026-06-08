from typing import Any

import pandas as pd


COLUMN_MAP = {
    "cbcode": "cbcode",
    "cb code": "cbcode",
    "cb_code": "cbcode",
    "last - title": "last_title",
    "last title": "last_title",
    "first": "first",
    "npi": "npi",
    "sin": "sin",
    "practice": "practice",
    "facility": "facility",
    "comments": "comments",
    "source": "source",
    "deactivation_flag": "deactivation_flag",
    "npi_number": "npi_number",
    "provmnemonic": "prov_mnemonic",
    "prov mnemonic": "prov_mnemonic",
    "prov_mnemonic": "prov_mnemonic",
    "ba_mnemonic": "ba_mnemonic",
    "number": "number",
    "lastname": "last_name",
    "last name": "last_name",
    "firstname": "first_name",
    "first name": "first_name",
    "middlename": "middle_name",
    "middle name": "middle_name",
    "name": "name",
    "numeric_code": "numeric_code",
    "specialty": "specialty",
    "divmnemonic": "division",
    "div mnemonic": "division",
    "mnemonic": "mnemonic",
    "type": "type",
    "dos": "dos",
    "patientlast": "patientLast",
    "patientfirst": "patientFirst",
    "dob": "DOB",
    "accnumber": "AccNumber",
}


def clean_scalar(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", "").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def normalize_column_name(column: Any) -> str:
    cleaned = clean_scalar(column)
    key = cleaned.lower().replace("-", " ").replace("/", " ").strip()
    key = "_".join(key.split()) if key in {"deactivation flag", "npi number", "ba mnemonic"} else key
    return COLUMN_MAP.get(key, COLUMN_MAP.get(cleaned.lower(), cleaned.strip()))


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [normalize_column_name(col) for col in normalized.columns]
    for column in normalized.columns:
        normalized[column] = normalized[column].map(clean_scalar)
    return normalized.fillna("")

