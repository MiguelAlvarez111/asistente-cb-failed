from pathlib import Path

import pandas as pd

from backend.app.schemas.ai import AIInterpretation
from backend.app.services.column_normalizer import normalize_dataframe
from backend.app.services.deterministic_interpreter import interpret_row


def _find_header_row(raw: pd.DataFrame) -> int | None:
    for index, row in raw.iterrows():
        values = " ".join(str(value).lower() for value in row.values)
        if "sin" in values and ("npi" in values or "last - title" in values or "comments" in values):
            return int(index)
    return None


def parse_corrections(path: Path) -> dict[str, AIInterpretation]:
    corrections: dict[str, AIInterpretation] = {}
    xls = pd.ExcelFile(path)
    for sheet_name in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str).fillna("")
        header = _find_header_row(raw)
        if header is None:
            continue
        df = raw.iloc[header + 1 :].reset_index(drop=True)
        df.columns = raw.iloc[header]
        df = normalize_dataframe(df)
        if "sin" not in df.columns:
            continue
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            sin = str(row_dict.get("sin", "")).strip()
            if not sin:
                continue
            interpretation = interpret_row(row_dict)
            if sin not in corrections or not interpretation.is_pending_usap:
                corrections[sin] = interpretation
    return corrections

