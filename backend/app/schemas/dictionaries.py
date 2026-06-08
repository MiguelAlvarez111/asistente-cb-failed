from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DictionaryType(StrEnum):
    USAP_PROVIDERS = "USAP_PROVIDERS"
    REFERRING_PROVIDERS = "REFERRING_PROVIDERS"
    UNKNOWN = "UNKNOWN"


class DictionaryDetection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detected_type: DictionaryType
    confidence: float
    columns_found: list[str]
    missing_columns: list[str]
    row_count: int
    warnings: list[str]


class DictionaryMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dictionary_name: str
    dictionary_type: DictionaryType
    match_type: str
    npi: str | None
    cbcode: str | None
    provider_name: str | None
    deactivation_status: str | None
    division: str | None
    ba_mnemonic: str | None

