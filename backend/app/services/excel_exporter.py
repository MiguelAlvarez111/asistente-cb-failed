from io import BytesIO
from pathlib import Path

import pandas as pd

from backend.app.schemas.results import RowDetail


OUTPUT_COLUMNS = [
    "Bot_Accion",
    "Bot_Suggestion",
    "Bot_Details",
    "AI_Action",
    "AI_Reason_Code",
    "AI_Confidence",
    "Needs_Manual_Review",
    "Validation_Status",
    "Validation_Details",
    "Dictionary_Match_Type",
    "Matched_Dictionary",
    "Matched_NPI",
    "Matched_CBCode",
    "Matched_Provider_Name",
    "Deactivation_Status",
    "AI_Explanation",
    "Final_Action",
    "Final_Recommendation",
]


def write_processed_workbook(processed_sheets: dict[str, pd.DataFrame], output_path: Path) -> None:
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in processed_sheets.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])


def rows_to_workbook(rows: list[RowDetail], *, kind: str) -> bytes:
    output = BytesIO()
    summary_rows = []
    if kind == "summary":
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.Final_Action] = counts.get(row.Final_Action, 0) + 1
        summary_rows = [{"Final_Action": key, "Count": value} for key, value in sorted(counts.items())]
        df = pd.DataFrame(summary_rows)
    else:
        if kind == "manual_review":
            rows = [row for row in rows if row.Needs_Manual_Review]
        elif kind == "high_confidence":
            rows = [row for row in rows if row.AI_Confidence >= 0.9 and not row.Needs_Manual_Review]
        df = pd.DataFrame([row.model_dump(mode="json", exclude={"deterministic_interpretation", "ai_interpretation", "validation"}) for row in rows])
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=kind[:31])
    return output.getvalue()

