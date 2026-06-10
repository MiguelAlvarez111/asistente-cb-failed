import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileCheck2, Play, Search, X } from "lucide-react";
import {
  createJob,
  deleteJob,
  type ExportKind,
  exportUrl,
  getJob,
  getResults,
  getRowDetail,
  inspectUploads,
  login,
  logout,
  lookupSin,
  session,
  updateWorkStatus
} from "../api/client";
import { Shell } from "../components/Shell";
import { Stat } from "../components/Stat";
import { LoginPage } from "./LoginPage";
import type { FileKind, RowResult, SINLookupMatch, SINLookupResponse, UploadInspectionResponse, WorkStatus } from "../types/api";

type Section = "search" | "review" | "upload" | "export";
type ReviewFilter = "READY" | "CHANGE_TICKET" | "COMPLETE_INFO" | "AWAITING_USAP" | "MANUAL_REVIEW" | "REMOVE_FROM_TICKET";
type BadgeTone = "neutral" | "good" | "warn" | "danger";

const WORK_STATUSES: WorkStatus[] = ["Pending", "Copied", "Applied", "Skipped"];
const REVIEW_FILTERS: Array<{ label: string; value: ReviewFilter }> = [
  { label: "Ready", value: "READY" },
  { label: "Change", value: "CHANGE_TICKET" },
  { label: "Complete", value: "COMPLETE_INFO" },
  { label: "Awaiting", value: "AWAITING_USAP" },
  { label: "Manual", value: "MANUAL_REVIEW" },
  { label: "Remove", value: "REMOVE_FROM_TICKET" }
];
const OVERRIDE_OPTIONS: Array<{ label: string; value: FileKind }> = [
  { label: "Original report", value: "CB_FAILED_REPORT" },
  { label: "Corrections", value: "CORRECTIONS" },
  { label: "Dictionary", value: "DICTIONARY" },
  { label: "Ignore", value: "IGNORE" }
];
const ACTION_LABELS: Record<string, string> = {
  CHANGE_TICKET: "Change Ticket",
  COMPLETE_INFO: "Complete Fields",
  AWAITING_USAP: "Awaiting USAP",
  MANUAL_REVIEW: "Manual Review",
  REMOVE_FROM_TICKET: "Remove from Ticket",
  MALFORMED_ROW: "Invalid Row",
  NO_ACTION: "No Action",
  ADD_TO_GE: "Awaiting USAP"
};
const FILE_KIND_LABELS: Record<string, string> = {
  CB_FAILED_REPORT: "Original report",
  CORRECTIONS: "Corrections",
  DICTIONARY: "Dictionary",
  IGNORE: "Ignore",
  UNKNOWN: "Unknown"
};

function cleanSearchValue(value: string) {
  return value.replace(/[\u200B-\u200D\uFEFF]/g, "").trim();
}

function normalizeSin(value: string) {
  return cleanSearchValue(value).replace(/\s+/g, "").toUpperCase();
}

function actionLabel(action: string, fallback?: string) {
  return ACTION_LABELS[action] ?? fallback ?? action.replace(/_/g, " ");
}

function actionTone(action: string): BadgeTone {
  if (action === "CHANGE_TICKET" || action === "REMOVE_FROM_TICKET") return "danger";
  if (action === "COMPLETE_INFO") return "good";
  if (action === "AWAITING_USAP") return "warn";
  if (action === "MANUAL_REVIEW" || action === "MALFORMED_ROW") return "warn";
  return "neutral";
}

function applyLabel(value: string) {
  return value === "YES" ? "Ready to Apply" : "Do Not Apply Yet";
}

function providerSummary(lastTitle: string, first: string) {
  const last = lastTitle.trim();
  const given = first.trim();
  if (last && given) return `${last}, ${given}`;
  return last || given || "No provider";
}

function roleLabel(role?: string | null) {
  const value = String(role || "").trim();
  if (!value) return "Provider";
  if (value.toLowerCase() === "surgeon") return "Surgeon";
  if (value.toLowerCase() === "provider") return "Provider";
  return value;
}

function roleNoun(role?: string | null) {
  return roleLabel(role);
}

function recommendedProvider(row: Pick<RowResult, "Recommended_Last_Title" | "Recommended_First">) {
  return providerSummary(row.Recommended_Last_Title, row.Recommended_First);
}

function recommendedProviderFromMatch(match: SINLookupMatch) {
  return providerSummary(match.recommended.last_title, match.recommended.first);
}

function fullCorrectionMatch(match: SINLookupMatch) {
  return [
    match.recommended.last_title,
    match.recommended.first,
    match.recommended.npi,
    match.recommended.cbcode,
    match.recommended.comments,
    match.recommended.source
  ].join("\t");
}

function trustLine(match: SINLookupMatch) {
  if (
    match.final_action === "CHANGE_TICKET" &&
    match.recommended.source === "USAP" &&
    match.recommended.cbcode.toLowerCase().includes("awaiting")
  ) {
    return "USAP change ticket; CBCode awaiting creation";
  }
  if (match.final_action === "CHANGE_TICKET") return "Change target validated in dictionary";
  if (match.final_action === "COMPLETE_INFO") {
    return match.recommended.cbcode ? `Dictionary validated CBCode ${match.recommended.cbcode}` : "Dictionary validated correction";
  }
  if (match.final_action === "AWAITING_USAP" && match.recommended.source === "USAP") return "USAP correction received; awaiting CBCode";
  if (match.final_action === "AWAITING_USAP" || match.final_action === "ADD_TO_GE") return "Awaiting USAP confirmation";
  if (match.final_action === "MANUAL_REVIEW") return "Manual review required";
  if (match.final_action === "REMOVE_FROM_TICKET") return "Remove from ticket requires verification";
  if (match.final_action === "MALFORMED_ROW") return "Invalid row";
  return match.validation_status || "Correction reviewed";
}

function rowToMatch(row: RowResult): SINLookupMatch {
  return {
    row_id: row.row_id,
    sin: row.SIN,
    region: row.Region || row.sheet_name,
    row_index: row.Row_Index,
    final_action: row.Final_Action,
    quick_action: row.Quick_Action,
    apply_this: row.Apply_This,
    work_status: row.Work_Status,
    role: row.Current_Type,
    current_provider: providerSummary(row.Current_Last_Title, row.Current_First),
    current: {
      last_title: row.Current_Last_Title,
      first: row.Current_First,
      npi: row.Current_NPI,
      cbcode: row.Current_CBCode
    },
    recommended: {
      last_title: row.Recommended_Last_Title,
      first: row.Recommended_First,
      npi: row.Recommended_NPI,
      cbcode: row.Recommended_CBCode,
      comments: row.Recommended_Comments,
      source: row.Recommended_Source
    },
    cell_colors: {
      last_title: row.Cell_Color_Last_Title,
      first: row.Cell_Color_First,
      npi: row.Cell_Color_NPI,
      cbcode: row.Cell_Color_CBCode,
      comments: row.Cell_Color_Comments,
      source: row.Cell_Color_Source
    },
    correction_summary: row.Correction_Summary,
    analyst_next_step: row.Analyst_Next_Step,
    validation_status: row.Validation_Status,
    manual_reason: row.Manual_Reason || null
  };
}

function colorClass(color: string) {
  const normalized = color.toLowerCase();
  if (normalized === "red") return "bg-red-500";
  if (normalized === "green") return "bg-green-600";
  if (normalized === "yellow") return "bg-yellow-400";
  return "bg-gray-400";
}

function correctionCellClass(color: string) {
  const normalized = color.toLowerCase();
  if (normalized === "red") return "border-red-200 bg-red-50 text-red-900";
  if (normalized === "green") return "border-green-200 bg-green-50 text-green-900";
  if (normalized === "yellow") return "border-yellow-200 bg-yellow-50 text-yellow-900";
  return "border-line bg-white text-ink";
}

function currentDisplay(value: string | undefined | null) {
  return value && String(value).trim() ? String(value) : "blank";
}

function recommendedDisplay(value: string | undefined | null) {
  return value && String(value).trim() ? String(value) : "—";
}

function sanitizedString(row: RowResult | undefined, keys: string[]) {
  if (!row) return "";
  for (const key of keys) {
    const value = row.sanitized_original?.[key];
    if (value !== undefined && value !== null && String(value).trim()) return String(value);
  }
  return "";
}

function ColorDot({ color }: { color: string }) {
  return <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${colorClass(color)}`} title={color} />;
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: BadgeTone }) {
  const styles = {
    neutral: "border-line bg-field text-ink",
    good: "border-green-200 bg-green-50 text-green-800",
    warn: "border-yellow-200 bg-yellow-50 text-yellow-800",
    danger: "border-red-200 bg-red-50 text-red-800"
  };
  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${styles[tone]}`}>{children}</span>;
}

function ActionBadge({ action, label }: { action: string; label?: string }) {
  return <Badge tone={actionTone(action)}>{actionLabel(action, label)}</Badge>;
}

function ApplyBadge({ apply }: { apply: string }) {
  return <Badge tone={apply === "YES" ? "good" : "warn"}>{applyLabel(apply)}</Badge>;
}

function WorkStatusPill({ value }: { value: WorkStatus }) {
  const tone: BadgeTone = value === "Applied" ? "good" : value === "Skipped" ? "warn" : "neutral";
  return <Badge tone={tone}>{value}</Badge>;
}

function WorkStatusSelect({ value, onChange }: { value: WorkStatus; onChange: (status: WorkStatus) => void }) {
  return (
    <select
      className="rounded border border-line bg-white px-2 py-1 text-xs"
      value={value}
      onClick={(event) => event.stopPropagation()}
      onChange={(event) => onChange(event.target.value as WorkStatus)}
    >
      {WORK_STATUSES.map((status) => (
        <option key={status} value={status}>{status}</option>
      ))}
    </select>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeSection, setActiveSection] = useState<Section>("search");
  const [inspection, setInspection] = useState<UploadInspectionResponse | null>(null);
  const [fileOverrides, setFileOverrides] = useState<Record<string, FileKind>>({});
  const [jobId, setJobId] = useState<string | null>(null);
  const [selectedRow, setSelectedRow] = useState<RowResult | null>(null);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("READY");
  const [reviewSearch, setReviewSearch] = useState("");
  const [sinInput, setSinInput] = useState("");
  const [lookupResult, setLookupResult] = useState<SINLookupResponse | null>(null);
  const [reviewRegion, setReviewRegion] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  const sessionQuery = useQuery({ queryKey: ["session"], queryFn: session });
  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["session"] })
  });
  const uploadMutation = useMutation({
    mutationFn: inspectUploads,
    onSuccess: (data) => {
      setInspection(data);
      setActiveSection("upload");
      setFileOverrides(Object.fromEntries(data.files.map((file) => [file.file_id, file.kind === "UNKNOWN" ? "IGNORE" : file.kind])));
    }
  });
  const jobMutation = useMutation({
    mutationFn: (uploadId: string) => createJob(uploadId, fileOverrides),
    onSuccess: (data) => {
      setJobId(data.job_id);
      setLookupResult(null);
      setActiveSection("search");
      window.history.replaceState(null, "", `/?job=${data.job_id}`);
      window.setTimeout(() => searchInputRef.current?.focus(), 100);
    }
  });
  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data?.status === "COMPLETED" || query.state.data?.status === "FAILED" ? false : 1500)
  });
  const resultsQuery = useQuery({
    queryKey: ["results", jobId],
    queryFn: () => getResults(jobId!),
    enabled: Boolean(jobId && jobQuery.data?.status === "COMPLETED")
  });
  const detailQuery = useQuery({
    queryKey: ["row", jobId, selectedRow?.row_id],
    queryFn: () => getRowDetail(jobId!, selectedRow!.row_id),
    enabled: Boolean(jobId && selectedRow)
  });
  const lookupMutation = useMutation({
    mutationFn: ({ currentJobId, sin }: { currentJobId: string; sin: string }) => lookupSin(currentJobId, sin),
    onSuccess: (data) => setLookupResult(data)
  });
  const workStatusMutation = useMutation({
    mutationFn: ({ rowId, status }: { rowId: string; status: WorkStatus }) => updateWorkStatus(jobId!, rowId, status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["results", jobId] });
      await queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      if (selectedRow) await queryClient.invalidateQueries({ queryKey: ["row", jobId, selectedRow.row_id] });
      if (lookupResult && sinInput) {
        const refreshed = await lookupSin(jobId!, sinInput);
        setLookupResult(refreshed);
      }
    }
  });
  const clearJobMutation = useMutation({
    mutationFn: deleteJob
  });

  useEffect(() => {
    const job = new URLSearchParams(window.location.search).get("job");
    if (job) setJobId(job);
  }, []);

  const rows = resultsQuery.data ?? [];
  const sortedRows = useMemo(
    () => [...rows].sort((a, b) => (a.Region || a.sheet_name).localeCompare(b.Region || b.sheet_name) || a.Row_Index - b.Row_Index),
    [rows]
  );
  const regions = useMemo(() => [...new Set(sortedRows.map((row) => row.Region || row.sheet_name).filter(Boolean))], [sortedRows]);
  const selectedRegion = reviewRegion || regions[0] || "";
  const detail = detailQuery.data ?? selectedRow;
  const summary = useMemo(() => {
    const count = (predicate: (row: RowResult) => boolean) => rows.filter(predicate).length;
    return {
      ready: count((row) => row.Apply_This === "YES"),
      applied: count((row) => row.Work_Status === "Applied"),
      change: count((row) => row.Final_Action === "CHANGE_TICKET"),
      complete: count((row) => row.Final_Action === "COMPLETE_INFO"),
      awaiting: count((row) => row.Final_Action === "AWAITING_USAP"),
      manual: count((row) => row.Needs_Manual_Review)
    };
  }, [rows]);
  const reviewRows = useMemo(() => {
    const needle = reviewSearch.toLowerCase();
    const sinNeedle = normalizeSin(reviewSearch);
    return sortedRows.filter((row) => {
      const regionMatch = !selectedRegion || (row.Region || row.sheet_name) === selectedRegion;
      const filterMatch = reviewFilter === "READY" ? row.Apply_This === "YES" : row.Final_Action === reviewFilter;
      const searchText = [
        row.SIN,
        row.Current_Type,
        row.Current_Last_Title,
        row.Current_First,
        row.Recommended_Last_Title,
        row.Recommended_First,
        row.Recommended_NPI,
        row.Recommended_CBCode,
        row.Recommended_Comments,
        row.Recommended_Source
      ].join(" ").toLowerCase();
      const sinMatch = sinNeedle && normalizeSin(row.SIN).includes(sinNeedle);
      return regionMatch && filterMatch && (!needle || searchText.includes(needle) || sinMatch);
    });
  }, [reviewFilter, reviewSearch, selectedRegion, sortedRows]);
  const progressState = uploadMutation.isPending
    ? { status: "INSPECTING", progress: 18, message: "Inspecting files..." }
    : jobMutation.isPending
      ? { status: "QUEUED", progress: 5, message: "Preparing files..." }
      : jobQuery.data && (jobQuery.data.status !== "COMPLETED" || resultsQuery.isFetching)
        ? {
            status: jobQuery.data.status,
            progress: jobQuery.data.status === "COMPLETED" ? 100 : jobQuery.data.progress,
            message: jobQuery.data.status === "COMPLETED" ? "Completed" : jobQuery.data.message
          }
        : null;
  const isJobBusy = jobMutation.isPending || jobQuery.data?.status === "QUEUED" || jobQuery.data?.status === "PROCESSING";

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 1800);
  }, []);

  const markCopied = useCallback((rowId: string) => {
    if (jobId) workStatusMutation.mutate({ rowId, status: "Copied" });
  }, [jobId, workStatusMutation]);

  const copyText = useCallback((label: string, value: string, rowId?: string) => {
    if (!value) return;
    navigator.clipboard?.writeText(value).catch(() => undefined);
    showToast(`Copied ${label}`);
    if (rowId) markCopied(rowId);
  }, [markCopied, showToast]);

  const resetLocalJobState = useCallback(() => {
    setInspection(null);
    setFileOverrides({});
    setJobId(null);
    setSelectedRow(null);
    setLookupResult(null);
    setSinInput("");
    setReviewFilter("READY");
    setReviewSearch("");
    setReviewRegion("");
    setToast(null);
    setActiveSection("upload");
    window.history.replaceState(null, "", "/");
    queryClient.removeQueries({ queryKey: ["job"] });
    queryClient.removeQueries({ queryKey: ["results"] });
    queryClient.removeQueries({ queryKey: ["row"] });
    window.setTimeout(() => fileInputRef.current?.focus(), 100);
  }, [queryClient]);

  const clearCurrentJob = useCallback(async () => {
    if (isJobBusy || clearJobMutation.isPending) return;
    const confirmed = window.confirm("This will clear the current job results from this session. Download any needed exports first.");
    if (!confirmed) return;
    const currentJobId = jobId;
    if (currentJobId) {
      await clearJobMutation.mutateAsync(currentJobId).catch(() => undefined);
    }
    resetLocalJobState();
  }, [clearJobMutation, isJobBusy, jobId, resetLocalJobState]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setActiveSection("search");
        window.setTimeout(() => searchInputRef.current?.focus(), 0);
      } else if (event.key === "Escape") {
        setSelectedRow(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    setToast(null);
  }, [activeSection]);

  useEffect(() => {
    if (jobQuery.data?.status === "COMPLETED") {
      setActiveSection("search");
      window.setTimeout(() => searchInputRef.current?.focus(), 100);
    }
  }, [jobQuery.data?.status]);

  if (sessionQuery.isLoading) {
    return <div className="p-8">Loading...</div>;
  }
  if (!sessionQuery.data?.authenticated) {
    return <LoginPage onLogin={(secret) => loginMutation.mutateAsync(secret).then(() => undefined)} />;
  }

  const runLookup = () => {
    const cleaned = normalizeSin(sinInput);
    setSinInput(cleaned);
    if (!jobId) {
      showToast("Upload and process files first");
      setActiveSection("upload");
      return;
    }
    if (cleaned) lookupMutation.mutate({ currentJobId: jobId, sin: cleaned });
  };
  const updateStatus = (rowId: string, status: WorkStatus) => {
    if (jobId) workStatusMutation.mutate({ rowId, status });
  };
  const openRow = (rowId: string) => {
    const row = rows.find((item) => item.row_id === rowId);
    if (row) setSelectedRow(row);
  };

  return (
    <Shell
      actions={jobId ? (
        <button
          className="rounded border border-line px-3 py-2 text-sm font-medium hover:bg-field disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isJobBusy || clearJobMutation.isPending}
          onClick={() => void clearCurrentJob()}
        >
          New Report
        </button>
      ) : null}
      onLogout={async () => {
        await logout();
        queryClient.invalidateQueries({ queryKey: ["session"] });
      }}
    >
      <nav className="mb-6 flex flex-wrap gap-2">
        {[
          ["search", "Search"],
          ["review", "Review Sheet"],
          ["upload", "Upload"],
          ["export", "Export"]
        ].map(([key, label]) => (
          <button
            key={key}
            className={`rounded-full border px-4 py-2 text-sm font-medium ${activeSection === key ? "border-pine bg-pine text-white" : "border-line bg-white hover:bg-field"}`}
            onClick={() => setActiveSection(key as Section)}
          >
            {label}
          </button>
        ))}
      </nav>

      {progressState && <ProcessingProgress status={progressState.status} progress={progressState.progress} message={progressState.message} />}

      {activeSection === "search" && (
        <MainSearch
          inputRef={searchInputRef}
          sinInput={sinInput}
          setSinInput={setSinInput}
          runLookup={runLookup}
          isSearching={lookupMutation.isPending}
          lookupResult={lookupResult}
          summary={summary}
          rows={rows}
          jobStatus={jobQuery.data?.status ?? "No job"}
          onOpenRow={openRow}
          onCopy={copyText}
          onStatus={updateStatus}
          onGoUpload={() => setActiveSection("upload")}
          onGoReview={() => setActiveSection("review")}
        />
      )}

      {activeSection === "review" && (
        <ReviewSheet
          rows={reviewRows}
          totalRows={sortedRows.length}
          regions={regions}
          selectedRegion={selectedRegion}
          setSelectedRegion={setReviewRegion}
          reviewFilter={reviewFilter}
          setReviewFilter={setReviewFilter}
          reviewSearch={reviewSearch}
          setReviewSearch={setReviewSearch}
          onOpenRow={setSelectedRow}
        />
      )}

      {activeSection === "upload" && (
        <UploadPanel
          inspection={inspection}
          fileOverrides={fileOverrides}
          setFileOverrides={setFileOverrides}
          uploadPending={uploadMutation.isPending}
          processPending={jobMutation.isPending}
          onUploadFiles={(files) => uploadMutation.mutate(files)}
          onProcess={(uploadId) => jobMutation.mutate(uploadId)}
          onContinue={() => setActiveSection("search")}
          onNewReport={() => void clearCurrentJob()}
          newReportDisabled={isJobBusy || clearJobMutation.isPending}
          jobStatus={jobQuery.data?.status}
          jobId={jobId}
          fileInputRef={fileInputRef}
        />
      )}

      {activeSection === "export" && <ExportPanel jobId={jobId} />}

      {selectedRow && detail && (
        <DetailPanel
          row={detail}
          onClose={() => setSelectedRow(null)}
          onCopy={copyText}
          onStatus={(status) => updateStatus(detail.row_id, status)}
        />
      )}

      {toast && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-full bg-ink px-4 py-2 text-sm font-medium text-white shadow-lg">
          {toast}
        </div>
      )}
    </Shell>
  );
}

function MainSearch({
  inputRef,
  sinInput,
  setSinInput,
  runLookup,
  isSearching,
  lookupResult,
  summary,
  rows,
  jobStatus,
  onOpenRow,
  onCopy,
  onStatus,
  onGoUpload,
  onGoReview
}: {
  inputRef: React.RefObject<HTMLInputElement>;
  sinInput: string;
  setSinInput: (value: string) => void;
  runLookup: () => void;
  isSearching: boolean;
  lookupResult: SINLookupResponse | null;
  summary: { ready: number; applied: number; change: number; complete: number; awaiting: number; manual: number };
  rows: RowResult[];
  jobStatus: string;
  onOpenRow: (rowId: string) => void;
  onCopy: (label: string, value: string, rowId?: string) => void;
  onStatus: (rowId: string, status: WorkStatus) => void;
  onGoUpload: () => void;
  onGoReview: () => void;
}) {
  return (
    <section className="mx-auto max-w-6xl space-y-6">
      <div className="rounded border border-line bg-white px-6 py-8 text-center shadow-sm">
        <p className="text-sm font-medium uppercase tracking-wide text-pine">CB Failed Assistant</p>
        <h2 className="mt-2 text-3xl font-semibold">Search a SIN to see exactly what to apply.</h2>
        <p className="mx-auto mt-2 max-w-2xl text-sm text-ink/65">
          Copy a SIN from Numbers, paste it here, and the assistant will show the correction.
        </p>
        <div className="mx-auto mt-6 flex max-w-4xl flex-col gap-3 md:flex-row">
          <input
            ref={inputRef}
            className="min-h-14 flex-1 rounded border border-line px-4 text-xl outline-none focus:border-pine focus:ring-2 focus:ring-pine/15"
            placeholder="Paste SIN and press Enter"
            value={sinInput}
            onChange={(event) => setSinInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") runLookup();
            }}
          />
          <button className="rounded bg-pine px-7 py-3 text-lg font-semibold text-white hover:bg-pine/90" onClick={runLookup}>
            {isSearching ? "Searching..." : "Search"}
          </button>
        </div>
        <p className="mt-3 text-xs text-ink/50">Tip: Cmd/Ctrl + K focuses search.</p>
      </div>

      {!lookupResult && (
        <>
          <SummaryCards summary={summary} jobStatus={jobStatus} />
          <div className="rounded border border-line bg-white p-4 text-center text-sm text-ink/65">
            {rows.length ? "Ready. Start by searching a SIN from your Numbers file." : (
              <button className="rounded border border-line px-3 py-2 text-sm hover:bg-field" onClick={onGoUpload}>
                Upload and process files to begin
              </button>
            )}
          </div>
        </>
      )}

      {lookupResult?.match_count === 0 && <NoMatchState onGoUpload={onGoUpload} onGoReview={onGoReview} />}

      {lookupResult?.match_count === 1 && (
        <SinResultCard
          match={lookupResult.matches[0]}
          row={rows.find((row) => row.row_id === lookupResult.matches[0].row_id)}
          onOpen={() => onOpenRow(lookupResult.matches[0].row_id)}
          onCopy={onCopy}
          onStatus={(status) => onStatus(lookupResult.matches[0].row_id, status)}
        />
      )}

      {lookupResult && lookupResult.match_count > 1 && (
        <MultipleMatchResults
          matches={lookupResult.matches}
          onOpen={onOpenRow}
        />
      )}
    </section>
  );
}

function SummaryCards({ summary, jobStatus }: { summary: { ready: number; applied: number; change: number; complete: number; awaiting: number; manual: number }; jobStatus: string }) {
  return (
    <div>
      <div className="grid gap-3 md:grid-cols-6">
        <Stat label="Ready" value={summary.ready} />
        <Stat label="Applied" value={summary.applied} />
        <Stat label="Change Tickets" value={summary.change} />
        <Stat label="Complete Fields" value={summary.complete} />
        <Stat label="Awaiting USAP" value={summary.awaiting} />
        <Stat label="Manual Review" value={summary.manual} />
      </div>
      <p className="mt-2 text-xs text-ink/50">Job status: {jobStatus}</p>
    </div>
  );
}

function ProcessingProgress({ status, progress, message }: { status: string; progress: number; message: string }) {
  const rawProgress = Number.isFinite(progress) ? progress : 0;
  const percent = Math.max(0, Math.min(100, Math.round(rawProgress <= 1 ? rawProgress * 100 : rawProgress)));
  const visiblePercent = status === "QUEUED" ? Math.max(percent, 5) : status === "INSPECTING" ? Math.max(percent, 18) : percent;
  const isFailed = status === "FAILED" || status === "EXPIRED";
  const isCompleted = status === "COMPLETED";
  const title =
    status === "INSPECTING"
      ? "Uploading / Inspecting files"
      : status === "QUEUED"
        ? "Preparing files..."
        : status === "PROCESSING"
          ? "Processing report..."
          : isCompleted
            ? "Completed"
          : isFailed
            ? "Processing failed"
            : "Working...";
  const displayMessage = message || (status === "QUEUED" ? "Preparing files..." : "Processing report...");

  return (
    <section className={`mx-auto mb-6 max-w-3xl rounded border p-5 shadow-sm ${isFailed ? "border-coral bg-red-50" : "border-line bg-white"}`}>
      <div className="mb-3 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-sm text-ink/60">{displayMessage}</p>
        </div>
        <span className={`text-2xl font-semibold tabular-nums ${isFailed ? "text-coral" : "text-pine"}`}>{visiblePercent}%</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-field">
        <div
          className={`h-full rounded-full bg-gradient-to-r transition-all duration-700 ${isFailed ? "from-coral to-gold" : isCompleted ? "from-green-600 to-pine" : "from-pine via-green-500 to-gold animate-pulse"}`}
          style={{ width: `${visiblePercent}%` }}
        />
      </div>
    </section>
  );
}

function SinResultCard({
  match,
  row,
  onOpen,
  onCopy,
  onStatus
}: {
  match: SINLookupMatch;
  row?: RowResult;
  onOpen?: () => void;
  onCopy: (label: string, value: string, rowId?: string) => void;
  onStatus: (status: WorkStatus) => void;
}) {
  const currentProvider = providerSummary(match.current.last_title, match.current.first);
  const nextProvider = recommendedProviderFromMatch(match);
  const noun = roleNoun(match.role);
  return (
    <article className="rounded border border-line bg-white p-5 shadow-sm transition-opacity">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-ink/50">SIN</p>
          <h3 className="text-2xl font-semibold">{match.sin}</h3>
          <p className="mt-1 text-sm text-ink/60">{roleLabel(match.role)} · {match.region} · Row {match.row_index} · {currentProvider}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{roleLabel(match.role)}</Badge>
          <ActionBadge action={match.final_action} label={match.quick_action} />
          <ApplyBadge apply={match.apply_this} />
          <WorkStatusSelect value={match.work_status} onChange={onStatus} />
        </div>
      </div>

      <section className="mt-4 grid items-center gap-3 rounded border border-line bg-field/40 p-4 md:grid-cols-[1fr_auto_1fr]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-ink/45">Current {noun}</p>
          <p className="mt-1 break-words text-xl font-semibold">{currentProvider}</p>
        </div>
        <div className="text-2xl font-semibold text-coral md:px-2" aria-hidden="true">→</div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-ink/45">Recommended {noun}</p>
          <p className="mt-1 break-words text-xl font-semibold">{nextProvider}</p>
        </div>
      </section>

      <CorrectionComparisonTable match={match} row={row} />

      <p className="mt-3 text-sm font-medium text-ink/70">{trustLine(match)}.</p>

      <AdvancedDetails row={row} match={match} onOpen={onOpen} onCopy={onCopy} />
    </article>
  );
}

function CorrectionComparisonTable({ match, row }: { match: SINLookupMatch; row?: RowResult }) {
  const current = {
    last_title: match.current.last_title,
    first: match.current.first,
    npi: match.current.npi,
    cbcode: match.current.cbcode,
    comments: sanitizedString(row, ["comments", "Comments"]),
    source: sanitizedString(row, ["source", "Source"])
  };
  const recommended = match.recommended;
  const columns = [
    { key: "last_title", label: "Last - Title", color: match.cell_colors.last_title, current: current.last_title, recommended: recommended.last_title },
    { key: "first", label: "First", color: match.cell_colors.first, current: current.first, recommended: recommended.first },
    { key: "npi", label: "NPI", color: match.cell_colors.npi, current: current.npi, recommended: recommended.npi },
    { key: "cbcode", label: "CBCode", color: match.cell_colors.cbcode, current: current.cbcode, recommended: recommended.cbcode },
    { key: "comments", label: "Comments", color: match.cell_colors.comments, current: current.comments, recommended: recommended.comments },
    { key: "source", label: "Source", color: match.cell_colors.source, current: current.source, recommended: recommended.source }
  ];

  return (
    <section className="mt-4 rounded border border-line bg-white">
      <div className="border-b border-line px-4 py-3">
        <h4 className="text-sm font-semibold uppercase tracking-wide text-ink/55">Correction Preview</h4>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-[960px] table-fixed text-left text-sm">
          <colgroup>
            <col style={{ width: 118 }} />
            <col style={{ width: 140 }} />
            <col style={{ width: 150 }} />
            <col style={{ width: 150 }} />
            <col style={{ width: 140 }} />
            <col style={{ width: 235 }} />
            <col style={{ width: 150 }} />
          </colgroup>
          <thead className="bg-field">
            <tr>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/45" />
              {columns.map((column) => (
                <th key={column.key} className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            <tr>
              <th className="bg-field/45 px-3 py-3 text-xs font-semibold uppercase tracking-wide text-ink/55">Current</th>
              {columns.map((column) => (
                <td key={column.key} className="px-3 py-3 align-top">
                  <span className="select-text break-words font-medium text-ink/80">{currentDisplay(column.current)}</span>
                </td>
              ))}
            </tr>
            <tr>
              <th className="bg-field/45 px-3 py-3 text-xs font-semibold uppercase tracking-wide text-ink/55">Recommended</th>
              {columns.map((column) => (
                <td key={column.key} className="px-2 py-2 align-top">
                  <span className={`block rounded border px-2 py-1.5 font-semibold select-text ${correctionCellClass(column.color)}`}>
                    {recommendedDisplay(column.recommended)}
                  </span>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AdvancedDetails({
  row,
  match,
  onOpen,
  onCopy
}: {
  row?: RowResult;
  match: SINLookupMatch;
  onOpen?: () => void;
  onCopy?: (label: string, value: string, rowId?: string) => void;
}) {
  return (
    <details className="mt-5 rounded border border-line p-4">
      <summary className="cursor-pointer text-sm font-semibold">Show validation details</summary>
      <div className="mt-3 grid gap-3 text-sm text-ink/70">
        {onCopy && (
          <button
            className="w-fit rounded border border-line px-3 py-1.5 text-xs font-medium hover:bg-field"
            onClick={() => onCopy("recommended row", fullCorrectionMatch(match), match.row_id)}
          >
            Copy recommended row
          </button>
        )}
        <p>Validation status: {match.validation_status}</p>
        {match.manual_reason && <p>Manual reason: {match.manual_reason}</p>}
        {row && (
          <>
            <p>Matched dictionary: {row.Matched_Dictionary || "none"}</p>
            <p>Matched provider: {row.Matched_Provider_Name || "none"}</p>
            <p>AI confidence: {row.AI_Confidence}</p>
            <p>AI explanation: {row.AI_Explanation}</p>
            <pre className="max-h-64 overflow-auto rounded bg-field p-3 text-xs">{JSON.stringify(row, null, 2)}</pre>
          </>
        )}
        {onOpen && <button className="w-fit rounded border border-line px-3 py-2 text-sm hover:bg-field" onClick={onOpen}>Open full row detail</button>}
      </div>
    </details>
  );
}

function MultipleMatchResults({ matches, onOpen }: { matches: SINLookupMatch[]; onOpen: (rowId: string) => void }) {
  return (
    <section className="space-y-3">
      <div className="rounded border border-line bg-white p-4">
        <h3 className="font-semibold">Multiple corrections found</h3>
        <p className="text-sm text-ink/65">This SIN appears more than once. Choose the row that matches your Numbers file.</p>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {matches.map((match) => (
          <div key={match.row_id} className="rounded border border-line bg-white p-4">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">{match.region} · Row {match.row_index}</p>
                <p className="text-sm text-ink/60">{roleLabel(match.role)} · {providerSummary(match.current.last_title, match.current.first)}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <ActionBadge action={match.final_action} label={match.quick_action} />
                <ApplyBadge apply={match.apply_this} />
              </div>
            </div>
            <p className="text-sm">Recommended {roleNoun(match.role)}: {recommendedProviderFromMatch(match)}</p>
            <p className="text-sm">CBCode: {match.recommended.cbcode || "blank"}</p>
            <button className="mt-3 rounded bg-pine px-3 py-2 text-sm font-semibold text-white" onClick={() => onOpen(match.row_id)}>
              Open
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function NoMatchState({ onGoUpload, onGoReview }: { onGoUpload: () => void; onGoReview: () => void }) {
  return (
    <section className="rounded border border-line bg-white p-6 text-center">
      <h3 className="text-xl font-semibold">No correction found for this SIN in the current job.</h3>
      <div className="mx-auto mt-3 max-w-xl text-sm text-ink/65">
        <p>Check if the correct files were uploaded.</p>
        <p>Check if the correction file was marked as Corrections.</p>
        <p>Try searching in Review Sheet.</p>
      </div>
      <div className="mt-4 flex justify-center gap-2">
        <button className="rounded border border-line px-3 py-2 text-sm hover:bg-field" onClick={onGoUpload}>Go to Upload</button>
        <button className="rounded bg-pine px-3 py-2 text-sm font-semibold text-white" onClick={onGoReview}>Open Review Sheet</button>
      </div>
    </section>
  );
}

function ReviewSheet({
  rows,
  totalRows,
  regions,
  selectedRegion,
  setSelectedRegion,
  reviewFilter,
  setReviewFilter,
  reviewSearch,
  setReviewSearch,
  onOpenRow
}: {
  rows: RowResult[];
  totalRows: number;
  regions: string[];
  selectedRegion: string;
  setSelectedRegion: (region: string) => void;
  reviewFilter: ReviewFilter;
  setReviewFilter: (filter: ReviewFilter) => void;
  reviewSearch: string;
  setReviewSearch: (value: string) => void;
  onOpenRow: (row: RowResult) => void;
}) {
  return (
    <section className="rounded border border-line bg-white p-4 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Review Sheet</h2>
          <p className="text-sm text-ink/60">Scan rows by region. Search is for working one ticket at a time.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="rounded-full border border-line bg-field px-3 py-1.5 text-sm font-semibold tabular-nums text-ink/70">
            Rows: {rows.length} / {totalRows}
          </div>
          <div className="flex items-center gap-2 rounded border border-line px-2">
            <Search size={15} />
            <input
              className="py-2 text-sm outline-none"
              placeholder="Search SIN or provider"
              value={reviewSearch}
              onChange={(event) => setReviewSearch(event.target.value)}
            />
          </div>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap gap-2">
        {regions.map((region) => (
          <button
            key={region}
            className={`rounded-full border px-3 py-1.5 text-sm ${selectedRegion === region ? "border-pine bg-pine text-white" : "border-line hover:bg-field"}`}
            onClick={() => setSelectedRegion(region)}
          >
            {region}
          </button>
        ))}
      </div>
      <div className="mb-3 flex flex-wrap gap-2">
        {REVIEW_FILTERS.map((filter) => (
          <button
            key={filter.value}
            className={`rounded border px-2 py-2 text-sm ${reviewFilter === filter.value ? "border-pine bg-pine text-white" : "border-line hover:bg-field"}`}
            onClick={() => setReviewFilter(filter.value)}
          >
            {filter.label}
          </button>
        ))}
      </div>
      <div className="max-h-[640px] overflow-auto rounded border border-line">
        <table className="min-w-[1510px] table-fixed text-left text-sm">
          <colgroup>
            <col style={{ width: 165 }} />
            <col style={{ width: 62 }} />
            <col style={{ width: 90 }} />
            <col style={{ width: 138 }} />
            <col style={{ width: 132 }} />
            <col style={{ width: 190 }} />
            <col style={{ width: 210 }} />
            <col style={{ width: 148 }} />
            <col style={{ width: 150 }} />
            <col style={{ width: 210 }} />
            <col style={{ width: 120 }} />
            <col style={{ width: 102 }} />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-field">
            <tr>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">SIN</th>
              <th className="border-b border-line px-3 py-2 text-center text-xs font-semibold uppercase tracking-wide text-ink/55">Row</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Type</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Action</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Apply</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Current Name</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Recommended Name</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Recommended NPI</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Recommended CBCode</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Comments</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Source</th>
              <th className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink/55">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/80">
            {rows.map((row) => (
              <tr
                key={row.row_id}
                className="h-14 cursor-pointer odd:bg-white even:bg-field/35 hover:bg-pine/5 focus:bg-pine/5 focus:outline-none"
                tabIndex={0}
                onClick={() => onOpenRow(row)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onOpenRow(row);
                }}
              >
                <td className="px-3 py-2 font-mono text-xs leading-5 text-ink/85" title={row.SIN}>
                  <div className="max-h-10 overflow-hidden break-all">{row.SIN}</div>
                </td>
                <td className="px-3 py-2 text-center tabular-nums">{row.Row_Index}</td>
                <td className="px-3 py-2 whitespace-nowrap"><Badge>{roleLabel(row.Current_Type)}</Badge></td>
                <td className="px-3 py-2 whitespace-nowrap"><ActionBadge action={row.Final_Action} label={row.Quick_Action} /></td>
                <td className="px-3 py-2 whitespace-nowrap"><ApplyBadge apply={row.Apply_This} /></td>
                <td className="px-3 py-2" title={providerSummary(row.Current_Last_Title, row.Current_First)}>
                  <div className="max-h-10 overflow-hidden leading-5">{providerSummary(row.Current_Last_Title, row.Current_First)}</div>
                </td>
                <td className="px-3 py-2" title={recommendedProvider(row)}>
                  <div className="max-h-10 overflow-hidden leading-5">{recommendedProvider(row)}</div>
                </td>
                <td className="px-3 py-2 font-mono whitespace-nowrap"><span className="mr-2"><ColorDot color={row.Cell_Color_NPI} /></span>{row.Recommended_NPI}</td>
                <td className="px-3 py-2 font-mono whitespace-nowrap"><span className="mr-2"><ColorDot color={row.Cell_Color_CBCode} /></span>{row.Recommended_CBCode}</td>
                <td className="truncate px-3 py-2" title={row.Recommended_Comments}>{row.Recommended_Comments}</td>
                <td className="px-3 py-2 whitespace-nowrap" title={row.Recommended_Source}>
                  <span className="mr-2"><ColorDot color={row.Cell_Color_Source} /></span>{row.Recommended_Source}
                </td>
                <td className="px-3 py-2 whitespace-nowrap"><WorkStatusPill value={row.Work_Status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function UploadPanel({
  inspection,
  fileOverrides,
  setFileOverrides,
  uploadPending,
  processPending,
  onUploadFiles,
  onProcess,
  onContinue,
  onNewReport,
  newReportDisabled,
  jobStatus,
  jobId,
  fileInputRef
}: {
  inspection: UploadInspectionResponse | null;
  fileOverrides: Record<string, FileKind>;
  setFileOverrides: (overrides: Record<string, FileKind>) => void;
  uploadPending: boolean;
  processPending: boolean;
  onUploadFiles: (files: File[]) => void;
  onProcess: (uploadId: string) => void;
  onContinue: () => void;
  onNewReport: () => void;
  newReportDisabled: boolean;
  jobStatus?: string;
  jobId: string | null;
  fileInputRef: React.RefObject<HTMLInputElement>;
}) {
  return (
    <section className="mx-auto max-w-5xl space-y-5">
      {jobId && (
        <div className="rounded border border-line bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink/50">Current job</p>
              <p className="text-sm text-ink/70">{jobStatus ?? "Loading"}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="rounded bg-pine px-3 py-2 text-sm font-semibold text-white hover:bg-pine/90" onClick={onContinue}>
                Continue working
              </button>
              <button
                className="rounded border border-line px-3 py-2 text-sm font-medium hover:bg-field disabled:cursor-not-allowed disabled:opacity-50"
                disabled={newReportDisabled}
                onClick={onNewReport}
              >
                New Report
              </button>
            </div>
          </div>
        </div>
      )}
      <div className="rounded border border-line bg-white p-5">
        <h2 className="mb-3 flex items-center gap-2 text-xl font-semibold"><FileCheck2 size={20} /> Upload</h2>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".xlsx,.xls,.txt"
          className="mb-3 w-full rounded border border-line p-2"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            if (files.length) onUploadFiles(files);
          }}
        />
        {uploadPending && <p className="text-sm text-ink/60">Inspecting selected files...</p>}
        {jobStatus && <p className="text-sm text-ink/60">Current job: {jobStatus}</p>}
      </div>

      {inspection && (
        <div className="rounded border border-line bg-white p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold">File Validation Preview</h3>
              <p className="text-sm text-ink/60">Confirm ambiguous files before processing.</p>
            </div>
            <button
              className="flex items-center gap-2 rounded bg-pine px-4 py-2 font-semibold text-white"
              disabled={processPending}
              onClick={() => onProcess(inspection.upload_id)}
            >
              <Play size={16} /> {processPending ? "Processing..." : "Process Report"}
            </button>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {inspection.files.map((file) => {
              const override = fileOverrides[file.file_id] ?? file.kind;
              const correctionSignal = file.kind === "CORRECTIONS" && file.warnings.some((warning) => warning.toLowerCase().includes("correction signals"));
              const details = [...file.warnings, ...file.missing_columns.map((col) => `Missing ${col}`)];
              return (
                <div key={file.file_id} className="rounded border border-line p-3">
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h4 className="truncate font-semibold">{file.filename}</h4>
                      <p className="text-sm text-ink/60">Detected: {FILE_KIND_LABELS[file.kind]}</p>
                    </div>
                    <Badge tone={file.kind === "UNKNOWN" ? "warn" : "neutral"}>{FILE_KIND_LABELS[override]}</Badge>
                  </div>
                  <p className="text-sm text-ink/65">{file.row_count} rows · {file.column_count} columns</p>
                  {correctionSignal && <p className="mt-2 text-sm text-pine">Detected as Corrections because correction-style fields or values were found.</p>}
                  {(file.kind === "UNKNOWN" || override === "IGNORE") && <p className="mt-2 text-sm text-gold">Please confirm file type.</p>}
                  <label className="mt-3 block text-xs uppercase text-ink/50">Use as</label>
                  <select
                    className="mt-1 w-full rounded border border-line px-2 py-2 text-sm"
                    value={override}
                    onChange={(event) => setFileOverrides({ ...fileOverrides, [file.file_id]: event.target.value as FileKind })}
                  >
                    {OVERRIDE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                  {details.length > 0 && (
                    <details className="mt-3 rounded border border-line bg-field/50 p-2">
                      <summary className="cursor-pointer text-xs font-semibold text-ink/65">Detection details</summary>
                      <div className="mt-2 space-y-1">
                        {details.map((warning) => (
                          <p className="text-xs text-coral" key={warning}>{warning}</p>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

function ExportPanel({ jobId }: { jobId: string | null }) {
  const advancedExports: Array<{ kind: ExportKind; label: string }> = [
    { kind: "full", label: "Full processed data" },
    { kind: "usap", label: "USAP awaiting rows" },
    { kind: "apply_ready", label: "Apply-ready rows" },
    { kind: "summary", label: "Summary" }
  ];

  return (
    <section className="mx-auto max-w-4xl rounded border border-line bg-white p-6">
      <h2 className="text-xl font-semibold">Export</h2>
      <p className="mt-1 text-sm text-ink/65">Download one clean workbook for Numbers/Excel when you need it.</p>
      <a
        className="mt-5 flex items-center justify-center gap-2 rounded bg-pine px-5 py-4 text-lg font-semibold text-white hover:bg-pine/90"
        href={jobId ? exportUrl(jobId, "numbers_ready") : "#"}
      >
        <Download size={20} /> Download Numbers-ready workbook
      </a>
      <p className="mt-2 text-sm text-ink/60">Includes region tabs, recommended corrections, and color guidance.</p>
      <details className="mt-5 rounded border border-line p-4">
        <summary className="cursor-pointer text-sm font-semibold">Advanced exports</summary>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {advancedExports.map(({ kind, label }) => (
            <a key={kind} className="rounded border border-line px-3 py-2 text-sm hover:bg-field" href={jobId ? exportUrl(jobId, kind) : "#"}>
              {label}
            </a>
          ))}
        </div>
      </details>
    </section>
  );
}

function DetailPanel({
  row,
  onClose,
  onCopy,
  onStatus
}: {
  row: RowResult;
  onClose: () => void;
  onCopy: (label: string, value: string, rowId?: string) => void;
  onStatus: (status: WorkStatus) => void;
}) {
  const match = rowToMatch(row);
  return (
    <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-3xl overflow-auto border-l border-line bg-white p-5 shadow-xl">
      <button className="mb-4 flex items-center gap-2 rounded border border-line px-3 py-2 text-sm hover:bg-field" onClick={onClose}>
        <X size={14} /> Close
      </button>
      <SinResultCard
        match={match}
        row={row}
        onCopy={onCopy}
        onStatus={onStatus}
      />
    </aside>
  );
}
