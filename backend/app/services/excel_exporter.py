from io import BytesIO
from pathlib import Path

import pandas as pd
from openpyxl.styles import PatternFill

from backend.app.schemas.results import RowDetail


ANALYST_COLUMNS = [
    "SIN",
    "Region",
    "Row_Index",
    "Final_Action",
    "Quick_Action",
    "Apply_This",
    "Current_Type",
    "Recommended_Type",
    "Current_Last_Title",
    "Current_First",
    "Current_NPI",
    "Current_CBCode",
    "Recommended_Last_Title",
    "Recommended_First",
    "Recommended_NPI",
    "Recommended_CBCode",
    "Recommended_Comments",
    "Recommended_Source",
    "Correction_Summary",
    "Analyst_Next_Step",
    "Needs_Manual_Review",
    "Manual_Reason",
    "Validation_Status",
    "Matched_Dictionary",
    "Matched_Provider_Name",
    "Matched_NPI",
    "Matched_CBCode",
    "AI_Confidence",
    "Cell_Color_Last_Title",
    "Cell_Color_First",
    "Cell_Color_NPI",
    "Cell_Color_CBCode",
    "Cell_Color_Comments",
    "Cell_Color_Source",
]

LEGACY_COLUMNS = [
    "Bot_Accion",
    "Bot_Suggestion",
    "Bot_Details",
    "AI_Action",
    "AI_Reason_Code",
    "Validation_Details",
    "Dictionary_Match_Type",
    "Deactivation_Status",
    "AI_Explanation",
    "Final_Recommendation",
]

OUTPUT_COLUMNS = ANALYST_COLUMNS + LEGACY_COLUMNS

FILL_COLORS = {
    "red": "FFFFC7CE",
    "green": "FFC6EFCE",
    "yellow": "FFFFEB9C",
    "gray": "FFE7E6E6",
    "neutral": "FFE7E6E6",
}

COLOR_TO_VALUE_COLUMN = {
    "Cell_Color_Last_Title": "Recommended_Last_Title",
    "Cell_Color_First": "Recommended_First",
    "Cell_Color_NPI": "Recommended_NPI",
    "Cell_Color_CBCode": "Recommended_CBCode",
    "Cell_Color_Comments": "Recommended_Comments",
    "Cell_Color_Source": "Recommended_Source",
}


def _export_row(row: RowDetail) -> dict[str, object]:
    data = row.model_dump(
        mode="json",
        exclude={"sanitized_original", "deterministic_interpretation", "ai_interpretation", "validation", "correction_instruction"},
    )
    export_row: dict[str, object] = {"row_id": data.get("row_id", ""), "sheet_name": data.get("sheet_name", "")}
    export_row.update({column: data.get(column, "") for column in OUTPUT_COLUMNS})
    return export_row


def _apply_color_styles(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame) -> None:
    worksheet = writer.sheets[sheet_name]
    columns = {column: index + 1 for index, column in enumerate(df.columns)}
    for color_column, value_column in COLOR_TO_VALUE_COLUMN.items():
        if color_column not in columns or value_column not in columns:
            continue
        color_index = columns[color_column]
        value_index = columns[value_column]
        for row_number in range(2, len(df) + 2):
            color_name = str(worksheet.cell(row=row_number, column=color_index).value or "").lower()
            rgb = FILL_COLORS.get(color_name)
            if rgb:
                fill = PatternFill(start_color=rgb, end_color=rgb, fill_type="solid")
                worksheet.cell(row=row_number, column=value_index).fill = fill
                worksheet.cell(row=row_number, column=color_index).fill = fill


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
        summary_rows.append({"Final_Action": "READY_TO_APPLY", "Count": sum(1 for row in rows if row.Apply_This == "YES")})
        df = pd.DataFrame(summary_rows)
    else:
        if kind == "manual_review":
            rows = [row for row in rows if row.Needs_Manual_Review]
        elif kind == "high_confidence":
            rows = [row for row in rows if row.AI_Confidence >= 0.9 and not row.Needs_Manual_Review]
        elif kind == "apply_ready":
            rows = [row for row in rows if row.Apply_This == "YES"]
        elif kind == "usap":
            rows = [row for row in rows if row.Final_Action == "AWAITING_USAP"]
        df = pd.DataFrame([_export_row(row) for row in rows])
        if kind == "usap" and not df.empty:
            df["Recommended_Source"] = ""
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if kind == "numbers_ready":
            source_rows = [_export_row(row) for row in rows]
            grouped: dict[str, list[dict[str, object]]] = {}
            for export_row in source_rows:
                region = str(export_row.get("Region") or export_row.get("sheet_name") or "Results")
                grouped.setdefault(region[:31], []).append(export_row)
            if not grouped:
                grouped["Results"] = []
            for sheet_name, group_rows in grouped.items():
                sheet_df = pd.DataFrame(group_rows)
                sheet_df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
                _apply_color_styles(writer, sheet_name[:31], sheet_df)
        else:
            df.to_excel(writer, index=False, sheet_name=kind[:31])
            if kind in {"full", "apply_ready", "manual_review", "high_confidence", "usap"}:
                _apply_color_styles(writer, kind[:31], df)
    return output.getvalue()
