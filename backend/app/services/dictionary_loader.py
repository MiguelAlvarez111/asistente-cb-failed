from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from backend.app.schemas.dictionaries import DictionaryMatch, DictionaryType
from backend.app.services.column_normalizer import normalize_dataframe
from backend.app.services.file_classifier import detect_dictionary


@dataclass
class LoadedDictionary:
    filename: str
    dictionary_type: DictionaryType
    df: pd.DataFrame

    @property
    def cbcode_column(self) -> str:
        return "prov_mnemonic" if self.dictionary_type == DictionaryType.USAP_PROVIDERS else "number"


def load_dictionary(path: Path, filename: str) -> LoadedDictionary | None:
    df = normalize_dataframe(pd.read_csv(path, sep="|", header=0, encoding="latin1", low_memory=False, dtype=str))
    detection = detect_dictionary(df)
    if detection.detected_type == DictionaryType.UNKNOWN:
        return None
    return LoadedDictionary(filename=filename, dictionary_type=detection.detected_type, df=df)


def _provider_name(row: pd.Series) -> str:
    parts = [row.get("last_name", ""), row.get("first_name", ""), row.get("middle_name", "")]
    return " ".join(part for part in parts if part).strip() or str(row.get("name", "")).strip()


def _to_match(dictionary: LoadedDictionary, row: pd.Series, match_type: str) -> DictionaryMatch:
    return DictionaryMatch(
        dictionary_name=dictionary.filename,
        dictionary_type=dictionary.dictionary_type,
        match_type=match_type,
        npi=str(row.get("npi_number", "") or "") or None,
        cbcode=str(row.get(dictionary.cbcode_column, "") or "") or None,
        provider_name=_provider_name(row) or None,
        deactivation_status=str(row.get("deactivation_flag", "") or "") or None,
        division=str(row.get("division", "") or "") or None,
        ba_mnemonic=str(row.get("ba_mnemonic", "") or "") or None,
    )


class DictionaryIndex:
    def __init__(self, dictionaries: list[LoadedDictionary]) -> None:
        self.dictionaries = dictionaries

    def lookup(self, *, npi: str | None = None, cbcode: str | None = None, provider_name: str | None = None) -> list[DictionaryMatch]:
        matches: list[DictionaryMatch] = []
        for dictionary in self.dictionaries:
            df = dictionary.df
            if npi and "npi_number" in df.columns:
                subset = df[df["npi_number"].str.lower() == npi.lower()]
                matches.extend(_to_match(dictionary, row, "NPI") for _, row in subset.iterrows())
            if cbcode and dictionary.cbcode_column in df.columns:
                subset = df[df[dictionary.cbcode_column].str.lower() == cbcode.lower()]
                matches.extend(_to_match(dictionary, row, "CBCODE") for _, row in subset.iterrows())
            if provider_name:
                needle = provider_name.lower().strip()
                for _, row in df.iterrows():
                    if needle and needle in _provider_name(row).lower():
                        matches.append(_to_match(dictionary, row, "PROVIDER_NAME"))
        unique: dict[tuple[str, str | None, str | None], DictionaryMatch] = {}
        for match in matches:
            unique[(match.dictionary_name, match.npi, match.cbcode)] = match
        return list(unique.values())

