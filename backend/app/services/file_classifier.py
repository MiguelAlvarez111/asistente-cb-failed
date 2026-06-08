from pathlib import Path

import pandas as pd

from backend.app.schemas.dictionaries import DictionaryDetection, DictionaryType
from backend.app.schemas.files import FileInspection, FileKind
from backend.app.services.column_normalizer import normalize_dataframe

USAP_PROVIDER_REQUIRED = {"npi_number", "prov_mnemonic", "ba_mnemonic"}
REFERRING_REQUIRED = {"npi_number", "number", "last_name", "first_name"}
REPORT_REQUIRED = {"type", "last_title", "first", "npi", "cbcode", "sin"}


def detect_dictionary(df: pd.DataFrame) -> DictionaryDetection:
    columns = set(df.columns)
    warnings: list[str] = []
    if USAP_PROVIDER_REQUIRED.issubset(columns):
        missing: list[str] = []
        detected = DictionaryType.USAP_PROVIDERS
        confidence = 0.99
    elif REFERRING_REQUIRED.issubset(columns):
        missing = []
        detected = DictionaryType.REFERRING_PROVIDERS
        confidence = 0.98
    else:
        provider_missing = sorted(USAP_PROVIDER_REQUIRED - columns)
        referring_missing = sorted(REFERRING_REQUIRED - columns)
        missing = provider_missing if len(provider_missing) <= len(referring_missing) else referring_missing
        detected = DictionaryType.UNKNOWN
        confidence = 0.2
        warnings.append("Dictionary schema was not recognized from columns.")
    return DictionaryDetection(
        detected_type=detected,
        confidence=confidence,
        columns_found=sorted(columns),
        missing_columns=missing,
        row_count=len(df.index),
        warnings=warnings,
    )


def _read_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".txt":
        return pd.read_csv(path, sep="|", header=0, encoding="latin1", low_memory=False, dtype=str)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=0, dtype=str)
    return pd.DataFrame()


def _inspect_excel(path: Path) -> FileInspection | None:
    workbook = pd.ExcelFile(path)
    report_columns: set[str] = set()
    correction_columns: set[str] = set()
    report_rows = 0
    correction_rows = 0
    report_sheets: list[str] = []
    correction_sheets: list[str] = []
    first_df: pd.DataFrame | None = None

    for sheet_name in workbook.sheet_names:
        df = normalize_dataframe(pd.read_excel(path, sheet_name=sheet_name, dtype=str).fillna(""))
        if first_df is None:
            first_df = df
        columns = set(df.columns)
        if REPORT_REQUIRED.issubset(columns):
            report_rows += len(df.index)
            report_columns.update(columns)
            report_sheets.append(sheet_name)
        elif {"comments", "sin"} & columns:
            correction_rows += len(df.index)
            correction_columns.update(columns)
            correction_sheets.append(sheet_name)

    if report_sheets:
        skipped = [sheet for sheet in workbook.sheet_names if sheet not in report_sheets]
        warnings = [f"Skipped non-report sheets: {', '.join(skipped)}"] if skipped else []
        return FileInspection(
            file_id="",
            filename="",
            kind=FileKind.CB_FAILED_REPORT,
            row_count=report_rows,
            column_count=len(report_columns),
            columns_found=sorted(report_columns),
            missing_columns=[],
            warnings=warnings,
            dictionary_detection=None,
        )

    if correction_sheets:
        return FileInspection(
            file_id="",
            filename="",
            kind=FileKind.CORRECTIONS,
            row_count=correction_rows,
            column_count=len(correction_columns),
            columns_found=sorted(correction_columns),
            missing_columns=sorted({"sin"} - correction_columns),
            warnings=[],
            dictionary_detection=None,
        )

    if first_df is not None:
        return FileInspection(
            file_id="",
            filename="",
            kind=FileKind.UNKNOWN,
            row_count=len(first_df.index),
            column_count=len(first_df.columns),
            columns_found=sorted(first_df.columns),
            missing_columns=sorted(REPORT_REQUIRED - set(first_df.columns)),
            warnings=["File type was not recognized from workbook sheets."],
            dictionary_detection=None,
        )
    return None


def inspect_file(path: Path, file_id: str, filename: str) -> FileInspection:
    warnings: list[str] = []
    try:
        if path.suffix.lower() in {".xlsx", ".xls"}:
            inspection = _inspect_excel(path)
            if inspection is not None:
                return inspection.model_copy(update={"file_id": file_id, "filename": filename})
        df = normalize_dataframe(_read_file(path))
    except Exception as exc:
        return FileInspection(
            file_id=file_id,
            filename=filename,
            kind=FileKind.UNKNOWN,
            row_count=0,
            column_count=0,
            columns_found=[],
            missing_columns=[],
            warnings=[f"Unable to read file: {exc}"],
            dictionary_detection=None,
        )

    columns = set(df.columns)
    dictionary_detection = detect_dictionary(df) if path.suffix.lower() == ".txt" else None
    if dictionary_detection and dictionary_detection.detected_type != DictionaryType.UNKNOWN:
        kind = FileKind.DICTIONARY
        missing = dictionary_detection.missing_columns
    elif REPORT_REQUIRED.issubset(columns):
        kind = FileKind.CB_FAILED_REPORT
        missing = []
    elif {"comments", "sin"} & columns and path.suffix.lower() in {".xlsx", ".xls"}:
        kind = FileKind.CORRECTIONS
        missing = sorted({"sin"} - columns)
    else:
        kind = FileKind.UNKNOWN
        missing = sorted(REPORT_REQUIRED - columns)
        warnings.append("File type was not recognized from columns.")

    return FileInspection(
        file_id=file_id,
        filename=filename,
        kind=kind,
        row_count=len(df.index),
        column_count=len(df.columns),
        columns_found=sorted(columns),
        missing_columns=missing,
        warnings=warnings,
        dictionary_detection=dictionary_detection,
    )
