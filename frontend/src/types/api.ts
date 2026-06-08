export type JobStatus = "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED" | "EXPIRED";

export type FileInspection = {
  file_id: string;
  filename: string;
  kind: string;
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
};

export type RowDetail = RowResult & {
  deterministic_interpretation: Record<string, unknown>;
  ai_interpretation: Record<string, unknown>;
  validation: Record<string, unknown>;
};

