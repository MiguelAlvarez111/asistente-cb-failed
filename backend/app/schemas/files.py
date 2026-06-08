from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.dictionaries import DictionaryDetection


class FileKind(StrEnum):
    CB_FAILED_REPORT = "CB_FAILED_REPORT"
    CORRECTIONS = "CORRECTIONS"
    DICTIONARY = "DICTIONARY"
    UNKNOWN = "UNKNOWN"


class FileInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str
    filename: str
    kind: FileKind
    row_count: int
    column_count: int
    columns_found: list[str]
    missing_columns: list[str]
    warnings: list[str]
    dictionary_detection: DictionaryDetection | None


class UploadInspectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str
    files: list[FileInspection]
    warnings: list[str]

