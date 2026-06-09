import axios from "axios";
import type { FileKind, JobStatusResponse, RowDetail, RowResult, SINLookupResponse, UploadInspectionResponse, WorkStatus } from "../types/api";

export const api = axios.create({
  baseURL: "",
  withCredentials: true
});

export async function login(secret: string) {
  const { data } = await api.post<{ authenticated: boolean }>("/api/auth/login", { secret });
  return data;
}

export async function logout() {
  const { data } = await api.post<{ authenticated: boolean }>("/api/auth/logout");
  return data;
}

export async function session() {
  const { data } = await api.get<{ authenticated: boolean }>("/api/auth/session");
  return data;
}

export async function inspectUploads(files: File[]) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const { data } = await api.post<UploadInspectionResponse>("/api/uploads/inspect", form);
  return data;
}

export async function createJob(uploadId: string, fileOverrides: Record<string, FileKind>) {
  const { data } = await api.post<{ job_id: string; status: string }>("/api/jobs", { upload_id: uploadId, file_overrides: fileOverrides });
  return data;
}

export async function getJob(jobId: string) {
  const { data } = await api.get<JobStatusResponse>(`/api/jobs/${jobId}`);
  return data;
}

export async function getResults(jobId: string) {
  const { data } = await api.get<RowResult[]>(`/api/results/${jobId}`);
  return data;
}

export async function getRowDetail(jobId: string, rowId: string) {
  const { data } = await api.get<RowDetail>(`/api/results/${jobId}/rows/${rowId}`);
  return data;
}

export async function lookupSin(jobId: string, sin: string) {
  const { data } = await api.get<SINLookupResponse>(`/api/results/${jobId}/lookup`, { params: { sin } });
  return data;
}

export async function updateWorkStatus(jobId: string, rowId: string, status: WorkStatus) {
  const { data } = await api.put<{ row_id: string; status: WorkStatus }>(`/api/jobs/${jobId}/rows/${rowId}/work-status`, { status });
  return data;
}

export async function submitFeedback(jobId: string, rowId: string, status: string, note?: string) {
  const { data } = await api.post(`/api/jobs/${jobId}/feedback/${rowId}`, {
    status,
    manual_correction: null,
    note: note ?? null
  });
  return data;
}

export type ExportKind = "full" | "manual_review" | "high_confidence" | "summary" | "apply_ready" | "usap" | "numbers_ready";

export function exportUrl(jobId: string, kind: ExportKind) {
  return `/api/export/${jobId}?kind=${kind}`;
}
