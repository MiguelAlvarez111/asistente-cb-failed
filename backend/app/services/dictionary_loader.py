from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pandas as pd

from backend.app.schemas.dictionaries import DictionaryMatch, DictionaryType
from backend.app.services.column_normalizer import normalize_dataframe
from backend.app.services.file_classifier import detect_dictionary


DEGREE_TOKENS = {"MD", "DO", "CRNA", "MDA", "DPM", "PA", "NP", "RN"}


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


def _clean_name_part(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _provider_name(row: pd.Series) -> str:
    parts = [_clean_name_part(row.get("last_name", "")), _clean_name_part(row.get("first_name", "")), _clean_name_part(row.get("middle_name", ""))]
    return " ".join(part for part in parts if part).strip() or _clean_name_part(row.get("name", ""))


def _normalize_match_value(value: Any) -> str:
    text = re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()
    return " ".join(text.split())


def _name_tokens(value: Any) -> list[str]:
    return [token for token in _normalize_match_value(value).split() if token not in DEGREE_TOKENS]


def _tokens_are_ordered_subset(shorter: list[str], longer: list[str]) -> bool:
    if len(shorter) < 2 or len(shorter) > len(longer):
        return False
    cursor = 0
    for token in longer:
        if token == shorter[cursor]:
            cursor += 1
            if cursor == len(shorter):
                return True
    return False


def _provider_name_matches(needle: str, candidate: str) -> bool:
    needle_tokens = _name_tokens(needle)
    candidate_tokens = _name_tokens(candidate)
    if not needle_tokens or not candidate_tokens:
        return False
    needle_text = " ".join(needle_tokens)
    candidate_text = " ".join(candidate_tokens)
    return (
        needle_text in candidate_text
        or all(token in candidate_tokens for token in needle_tokens)
        or _tokens_are_ordered_subset(candidate_tokens, needle_tokens)
    )


def _effective_key(match: DictionaryMatch) -> tuple[str, str, str]:
    return (
        _normalize_match_value(match.npi),
        _normalize_match_value(match.cbcode),
        _normalize_match_value(match.provider_name),
    )


def _context_score(match: DictionaryMatch, row: dict[str, Any] | None) -> int:
    if not row:
        return 0
    context = _normalize_match_value(" ".join(str(row.get(key, "") or "") for key in ["practice", "facility", "type"]))
    score = 0
    for value in [match.ba_mnemonic, match.division, match.dictionary_name]:
        token = _normalize_match_value(value)
        if token and token in context:
            score += 1
    return score


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

    def lookup(
        self,
        *,
        npi: str | None = None,
        cbcode: str | None = None,
        provider_name: str | None = None,
        dictionary_types: set[DictionaryType] | None = None,
    ) -> list[DictionaryMatch]:
        matches: list[DictionaryMatch] = []
        for dictionary in self.dictionaries:
            if dictionary_types is not None and dictionary.dictionary_type not in dictionary_types:
                continue
            df = dictionary.df
            if npi and "npi_number" in df.columns:
                subset = df[df["npi_number"].str.lower() == npi.lower()]
                matches.extend(_to_match(dictionary, row, "NPI") for _, row in subset.iterrows())
            if cbcode and dictionary.cbcode_column in df.columns:
                subset = df[df[dictionary.cbcode_column].str.lower() == cbcode.lower()]
                matches.extend(_to_match(dictionary, row, "CBCODE") for _, row in subset.iterrows())
            if provider_name:
                for _, row in df.iterrows():
                    if _provider_name_matches(provider_name, _provider_name(row)):
                        matches.append(_to_match(dictionary, row, "PROVIDER_NAME"))
        unique: dict[tuple[str, str | None, str | None], DictionaryMatch] = {}
        for match in matches:
            unique[(match.dictionary_name, match.npi, match.cbcode)] = match
        return list(unique.values())


def resolve_effective_matches(matches: list[DictionaryMatch], row: dict[str, Any] | None = None) -> list[DictionaryMatch]:
    exact_unique: dict[tuple[str, str | None, str | None, str | None], DictionaryMatch] = {}
    for match in matches:
        exact_unique[(match.dictionary_name, match.npi, match.cbcode, match.provider_name)] = match
    unique_matches = list(exact_unique.values())
    if len(unique_matches) <= 1:
        return unique_matches

    effective_keys = {_effective_key(match) for match in unique_matches}
    if len(effective_keys) == 1:
        return [unique_matches[0]]

    scored = [(_context_score(match, row), match) for match in unique_matches]
    max_score = max(score for score, _ in scored)
    if max_score > 0:
        best = [match for score, match in scored if score == max_score]
        if len(best) == 1:
            return best
        if len({_effective_key(match) for match in best}) == 1:
            return [best[0]]

    return unique_matches
