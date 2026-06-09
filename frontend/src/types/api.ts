export type JobStatus = "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED" | "EXPIRED";
export type WorkStatus = "Pending" | "Copied" | "Applied" | "Skipped";
export type FileKind = "CB_FAILED_REPORT" | "CORRECTIONS" | "DICTIONARY" | "IGNORE" | "UNKNOWN";

export type FileInspection = {
  file_id: string;
  filename: string;
  kind: FileKind;
  row_count: number;
  column_count: number;
  columns_found: string[];
  missing_columns: string[];
  warnings: string[];
  dictionary_detection: null | {
    detected_type: string;
    confidence: number;
    columns_found: string[];
    missing_columns: string[];
    row_count: number;
    warnings: string[];
  };
};

export type UploadInspectionResponse = {
  upload_id: string;
  files: FileInspection[];
  warnings: string[];
};

export type JobSummary = {
  total_rows: number;
  malformed_rows: number;
  ignored_rows: number;
  final_action_counts: Record<string, number>;
  confidence_counts: Record<string, number>;
  work_status_counts: Record<string, number>;
  manual_review_count: number;
  ai_rows_count: number;
};

export type JobStatusResponse = {
  job_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  summary: JobSummary;
};

export type RowResult = {
  row_id: string;
  sheet_name: string;
  SIN: string;
  Region: string;
  Row_Index: number;
  Work_Status: WorkStatus;
  sanitized_original: Record<string, unknown>;
  Bot_Accion: string;
  Bot_Suggestion: string;
  Bot_Details: string;
  AI_Action: string;
  AI_Reason_Code: string;
  AI_Confidence: number;
  Needs_Manual_Review: boolean;
  Validation_Status: string;
  Validation_Details: string;
  Dictionary_Match_Type: string | null;
  Matched_Dictionary: string | null;
  Matched_NPI: string | null;
  Matched_CBCode: string | null;
  Matched_Provider_Name: string | null;
  Deactivation_Status: string | null;
  AI_Explanation: string;
  Final_Action: string;
  Final_Recommendation: string;
  Quick_Action: string;
  Apply_This: "YES" | "NO" | string;
  Current_Last_Title: string;
  Current_First: string;
  Current_NPI: string;
  Current_CBCode: string;
  Recommended_Last_Title: string;
  Recommended_First: string;
  Recommended_NPI: string;
  Recommended_CBCode: string;
  Recommended_Comments: string;
  Recommended_Source: string;
  Correction_Summary: string;
  Analyst_Next_Step: string;
  Manual_Reason: string;
  Cell_Color_Last_Title: string;
  Cell_Color_First: string;
  Cell_Color_NPI: string;
  Cell_Color_CBCode: string;
  Cell_Color_Comments: string;
  Cell_Color_Source: string;
  correction_instruction: Record<string, unknown>;
};

export type RowDetail = RowResult & {
  deterministic_interpretation: Record<string, unknown>;
  ai_interpretation: Record<string, unknown>;
  validation: Record<string, unknown>;
};

export type LookupValues = {
  last_title: string;
  first: string;
  npi: string;
  cbcode: string;
};

export type LookupRecommendedValues = LookupValues & {
  comments: string;
  source: string;
};

export type LookupCellColors = {
  last_title: string;
  first: string;
  npi: string;
  cbcode: string;
  comments: string;
  source: string;
};

export type SINLookupMatch = {
  row_id: string;
  sin: string;
  region: string;
  row_index: number;
  final_action: string;
  quick_action: string;
  apply_this: string;
  work_status: WorkStatus;
  current_provider: string;
  current: LookupValues;
  recommended: LookupRecommendedValues;
  cell_colors: LookupCellColors;
  correction_summary: string;
  analyst_next_step: string;
  validation_status: string;
  manual_reason: string | null;
};

export type SINLookupResponse = {
  query: string;
  normalized_query: string;
  match_count: number;
  matches: SINLookupMatch[];
};
