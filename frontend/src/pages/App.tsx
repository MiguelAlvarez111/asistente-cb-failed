import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileCheck2, Play, Search, X } from "lucide-react";
import {
  createJob,
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
  { label: "Ready to Apply", value: "READY" },
  { label: "Change Ticket", value: "CHANGE_TICKET" },
  { label: "Complete Fields", value: "COMPLETE_INFO" },
  { label: "Awaiting USAP", value: "AWAITING_USAP" },
  { label: "Manual Review", value: "MANUAL_REVIEW" },
  { label: "Remove from Ticket", value: "REMOVE_FROM_TICKET" }
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
  return [lastTitle, first].filter(Boolean).join(" ").trim() || "No provider";
}

function recommendedProvider(row: Pick<RowResult, "Recommended_Last_Title" | "Recommended_First">) {
  return providerSummary(row.Recommended_Last_Title, row.Recommended_First);
}

function recommendedProviderFromMatch(match: SINLookupMatch) {
  return providerSummary(match.recommended.last_title, match.recommended.first);
}

function fullCorrectionRow(row: Pick<RowResult, "Recommended_Last_Title" | "Recommended_First" | "Recommended_NPI" | "Recommended_CBCode" | "Recommended_Comments" | "Recommended_Source">) {
  return [
    row.Recommended_Last_Title,
    row.Recommended_First,
    row.Recommended_NPI,
    row.Recommended_CBCode,
    row.Recommended_Comments,
    row.Recommended_Source
  ].join("\t");
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

function colorMeaning(field: string, color: string) {
  const normalized = color.toLowerCase();
  const labels: Record<string, string> = {
    last_title: "Last name/title",
    first: "First name",
    npi: "NPI",
    cbcode: "CBCode",
    comments: "Comments",
    source: "Source"
  };
  const label = labels[field] ?? field;
  if (normalized === "red") return `${label} will change`;
  if (normalized === "green") return field === "source" ? "Source validated by Dictionary" : `${label} completed or validated`;
  if (normalized === "yellow") return `${label} needs review or USAP confirmation`;
  return `${label}: no action`;
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
  const singleActiveMatch = lookupResult?.match_count === 1 ? lookupResult.matches[0] : null;
  const activeSingleRow = singleActiveMatch ? rows.find((row) => row.row_id === singleActiveMatch.row_id) : null;

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

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.tagName === "SELECT";
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setActiveSection("search");
        window.setTimeout(() => searchInputRef.current?.focus(), 0);
      } else if (event.key === "Escape") {
        setSelectedRow(null);
      } else if (!isTyping && event.key.toLowerCase() === "c" && singleActiveMatch) {
        copyText("full row", fullCorrectionMatch(singleActiveMatch), singleActiveMatch.row_id);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [copyText, singleActiveMatch]);

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
          regions={regions}
          selectedRegion={selectedRegion}
          setSelectedRegion={setReviewRegion}
          reviewFilter={reviewFilter}
          setReviewFilter={setReviewFilter}
          reviewSearch={reviewSearch}
          setReviewSearch={setReviewSearch}
          onOpenRow={setSelectedRow}
          onCopy={copyText}
          onStatus={updateStatus}
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
          jobStatus={jobQuery.data?.status}
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
        <p className="mt-3 text-xs text-ink/50">Tip: Cmd/Ctrl + K focuses search. Press C to copy the active full correction row.</p>
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
  return (
    <article className="rounded border border-line bg-white p-5 shadow-sm">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-ink/50">SIN</p>
          <h3 className="text-2xl font-semibold">{match.sin}</h3>
          <p className="mt-1 text-sm text-ink/60">{match.region} · Row {match.row_index} · {match.current_provider}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ActionBadge action={match.final_action} label={match.quick_action} />
          <ApplyBadge apply={match.apply_this} />
          <WorkStatusSelect value={match.work_status} onChange={onStatus} />
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_1.25fr]">
        <section className="rounded border border-line bg-field/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink/55">What to do</p>
          <h4 className="mt-2 text-2xl font-semibold">{actionLabel(match.final_action, match.quick_action)}</h4>
          <p className="mt-3 text-sm">{match.correction_summary || "Use the recommended values for this correction."}</p>
          <p className="mt-3 rounded border border-line bg-white p-3 text-sm">{match.analyst_next_step}</p>
        </section>

        <section className="rounded border border-line p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink/55">Copy values</p>
            <button
              className="rounded bg-pine px-3 py-2 text-sm font-semibold text-white hover:bg-pine/90"
              onClick={() => onCopy("full row", fullCorrectionMatch(match), match.row_id)}
            >
              Copy full correction row
            </button>
          </div>
          <div className="grid gap-2">
            <CopyValue label="Last - Title" value={match.recommended.last_title} color={match.cell_colors.last_title} onCopy={() => onCopy("Last - Title", match.recommended.last_title, match.row_id)} />
            <CopyValue label="First" value={match.recommended.first} color={match.cell_colors.first} onCopy={() => onCopy("First", match.recommended.first, match.row_id)} />
            <CopyValue label="NPI" value={match.recommended.npi} color={match.cell_colors.npi} onCopy={() => onCopy("NPI", match.recommended.npi, match.row_id)} />
            <CopyValue label="CBCode" value={match.recommended.cbcode} color={match.cell_colors.cbcode} onCopy={() => onCopy("CBCode", match.recommended.cbcode, match.row_id)} />
            <CopyValue label="Comments" value={match.recommended.comments} color={match.cell_colors.comments} onCopy={() => onCopy("Comments", match.recommended.comments, match.row_id)} />
            <CopyValue label="Source" value={match.recommended.source} color={match.cell_colors.source} onCopy={() => onCopy("Source", match.recommended.source, match.row_id)} />
          </div>
        </section>
      </div>

      <CurrentRecommendedComparison match={match} />

      <AdvancedDetails row={row} match={match} onOpen={onOpen} />
    </article>
  );
}

function CopyValue({ label, value, color, onCopy }: { label: string; value: string; color: string; onCopy: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded border border-line bg-white px-3 py-2">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-xs uppercase text-ink/50"><ColorDot color={color} /> {label}</p>
        <p className="truncate text-lg font-semibold">{value || "blank"}</p>
      </div>
      <button className="shrink-0 rounded border border-line px-3 py-1.5 text-sm hover:bg-field" onClick={onCopy}>
        Copy
      </button>
    </div>
  );
}

function CurrentRecommendedComparison({ match }: { match: SINLookupMatch }) {
  return (
    <div className="mt-5 grid gap-4 lg:grid-cols-2">
      <section className="rounded border border-line p-4">
        <h4 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink/55">Current</h4>
        <ValueLine label="Last - Title" value={match.current.last_title} />
        <ValueLine label="First" value={match.current.first} />
        <ValueLine label="NPI" value={match.current.npi} />
        <ValueLine label="CBCode" value={match.current.cbcode} />
      </section>
      <section className="rounded border border-line p-4">
        <h4 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink/55">Recommended</h4>
        <ValueLine label="Last - Title" value={match.recommended.last_title} color={match.cell_colors.last_title} />
        <ValueLine label="First" value={match.recommended.first} color={match.cell_colors.first} />
        <ValueLine label="NPI" value={match.recommended.npi} color={match.cell_colors.npi} />
        <ValueLine label="CBCode" value={match.recommended.cbcode} color={match.cell_colors.cbcode} />
        <ValueLine label="Comments" value={match.recommended.comments} color={match.cell_colors.comments} />
        <ValueLine label="Source" value={match.recommended.source} color={match.cell_colors.source} />
        <div className="mt-4 grid gap-1 text-xs text-ink/65 sm:grid-cols-2">
          {Object.entries(match.cell_colors)
            .filter(([, color]) => color !== "gray")
            .map(([field, color]) => (
              <span key={field} className="flex items-center gap-2"><ColorDot color={color} /> {colorMeaning(field, color)}</span>
            ))}
        </div>
      </section>
    </div>
  );
}

function ValueLine({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="mb-2 flex items-start justify-between gap-3 border-b border-line/70 pb-2 last:mb-0 last:border-b-0 last:pb-0">
      <span className="flex items-center gap-2 text-sm text-ink/55">{color && <ColorDot color={color} />}{label}</span>
      <span className="max-w-[65%] break-words text-right text-sm font-medium">{value || "blank"}</span>
    </div>
  );
}

function AdvancedDetails({ row, match, onOpen }: { row?: RowResult; match: SINLookupMatch; onOpen?: () => void }) {
  return (
    <details className="mt-5 rounded border border-line p-4">
      <summary className="cursor-pointer text-sm font-semibold">Show validation details</summary>
      <div className="mt-3 grid gap-3 text-sm text-ink/70">
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
                <p className="text-sm text-ink/60">{match.current_provider}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <ActionBadge action={match.final_action} label={match.quick_action} />
                <ApplyBadge apply={match.apply_this} />
              </div>
            </div>
            <p className="text-sm">Recommended: {recommendedProviderFromMatch(match)}</p>
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
  regions,
  selectedRegion,
  setSelectedRegion,
  reviewFilter,
  setReviewFilter,
  reviewSearch,
  setReviewSearch,
  onOpenRow,
  onCopy,
  onStatus
}: {
  rows: RowResult[];
  regions: string[];
  selectedRegion: string;
  setSelectedRegion: (region: string) => void;
  reviewFilter: ReviewFilter;
  setReviewFilter: (filter: ReviewFilter) => void;
  reviewSearch: string;
  setReviewSearch: (value: string) => void;
  onOpenRow: (row: RowResult) => void;
  onCopy: (label: string, value: string, rowId?: string) => void;
  onStatus: (rowId: string, status: WorkStatus) => void;
}) {
  return (
    <section className="rounded border border-line bg-white p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Review Sheet</h2>
          <p className="text-sm text-ink/60">Scan rows by region. Search is for working one ticket at a time.</p>
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
      <div className="max-h-[620px] overflow-auto border border-line">
        <table className="min-w-[1200px] text-left text-sm">
          <thead className="sticky top-0 bg-field">
            <tr>
              <th className="p-2">SIN</th>
              <th className="p-2">Row</th>
              <th className="p-2">Action</th>
              <th className="p-2">Apply</th>
              <th className="p-2">Current Provider</th>
              <th className="p-2">Recommended Provider</th>
              <th className="p-2">Recommended NPI</th>
              <th className="p-2">Recommended CBCode</th>
              <th className="p-2">Comments</th>
              <th className="p-2">Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.row_id} className="cursor-pointer border-t border-line hover:bg-field" onClick={() => onOpenRow(row)}>
                <td className="p-2">{row.SIN}</td>
                <td className="p-2">{row.Row_Index}</td>
                <td className="p-2"><ActionBadge action={row.Final_Action} label={row.Quick_Action} /></td>
                <td className="p-2"><ApplyBadge apply={row.Apply_This} /></td>
                <td className="p-2">{providerSummary(row.Current_Last_Title, row.Current_First)}</td>
                <td className="p-2">{recommendedProvider(row)}</td>
                <td className="p-2"><span className="mr-2"><ColorDot color={row.Cell_Color_NPI} /></span>{row.Recommended_NPI}</td>
                <td className="p-2"><span className="mr-2"><ColorDot color={row.Cell_Color_CBCode} /></span>{row.Recommended_CBCode}</td>
                <td className="p-2">{row.Recommended_Comments}</td>
                <td className="p-2">
                  <div className="flex items-center gap-2">
                    <span><ColorDot color={row.Cell_Color_Source} /></span>
                    <span>{row.Recommended_Source}</span>
                    <button className="rounded border border-line px-2 py-1 text-xs hover:bg-white" onClick={(event) => {
                      event.stopPropagation();
                      onCopy("full row", fullCorrectionRow(row), row.row_id);
                    }}>Copy row</button>
                    <WorkStatusSelect value={row.Work_Status} onChange={(status) => onStatus(row.row_id, status)} />
                  </div>
                </td>
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
  jobStatus
}: {
  inspection: UploadInspectionResponse | null;
  fileOverrides: Record<string, FileKind>;
  setFileOverrides: (overrides: Record<string, FileKind>) => void;
  uploadPending: boolean;
  processPending: boolean;
  onUploadFiles: (files: File[]) => void;
  onProcess: (uploadId: string) => void;
  jobStatus?: string;
}) {
  return (
    <section className="mx-auto max-w-5xl space-y-5">
      <div className="rounded border border-line bg-white p-5">
        <h2 className="mb-3 flex items-center gap-2 text-xl font-semibold"><FileCheck2 size={20} /> Upload</h2>
        <input
          type="file"
          multiple
          accept=".xlsx,.xls,.txt"
          className="mb-3 w-full rounded border border-line p-2"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            if (files.length) onUploadFiles(files);
          }}
        />
        {uploadPending && <p className="text-sm text-ink/60">Inspecting files...</p>}
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
              return (
                <div key={file.file_id} className="rounded border border-line p-4">
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h4 className="truncate font-semibold">{file.filename}</h4>
                      <p className="text-sm text-ink/60">Detected: {FILE_KIND_LABELS[file.kind]}</p>
                    </div>
                    <Badge tone={file.kind === "UNKNOWN" ? "warn" : "neutral"}>{FILE_KIND_LABELS[override]}</Badge>
                  </div>
                  <p className="text-sm text-ink/65">{file.row_count} rows · {file.column_count} columns</p>
                  {correctionSignal && <p className="mt-2 text-sm text-pine">Detected as Corrections because this file contains correction signals or correction values.</p>}
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
                  {[...file.warnings, ...file.missing_columns.map((col) => `Missing ${col}`)].map((warning) => (
                    <p className="mt-2 text-sm text-coral" key={warning}>{warning}</p>
                  ))}
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
