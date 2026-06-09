import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, FileCheck2, Play, RefreshCw, Search } from "lucide-react";
import {
  createJob,
  exportUrl,
  getJob,
  getResults,
  getRowDetail,
  inspectUploads,
  login,
  logout,
  lookupSin,
  session,
  submitFeedback,
  updateWorkStatus
} from "../api/client";
import { Shell } from "../components/Shell";
import { Stat } from "../components/Stat";
import { LoginPage } from "./LoginPage";
import type { RowResult, SINLookupMatch, SINLookupResponse, UploadInspectionResponse, WorkStatus } from "../types/api";

type Tab = "dashboard" | "apply" | "sin" | "preview" | "exports";
type Filters = {
  action: string;
  validation: string;
  review: string;
  apply: string;
  search: string;
};

const WORK_STATUSES: WorkStatus[] = ["Pending", "Copied", "Applied", "Skipped"];
const EXPORTS = ["full", "apply_ready", "usap", "numbers_ready", "manual_review", "high_confidence", "summary"] as const;

function normalizeSin(value: string) {
  return value.replace(/\s+/g, "").toUpperCase();
}

function providerSummary(lastTitle: string, first: string) {
  return [lastTitle, first].filter(Boolean).join(" ").trim();
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

function colorClass(color: string) {
  const normalized = color.toLowerCase();
  if (normalized === "red") return "bg-red-500";
  if (normalized === "green") return "bg-green-600";
  if (normalized === "yellow") return "bg-yellow-400";
  return "bg-gray-400";
}

function ColorMarker({ color }: { color: string }) {
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${colorClass(color)}`} title={color} />;
}

function CopyButton({ label, value, onCopied }: { label: string; value: string; onCopied?: () => void }) {
  if (!value) return null;
  return (
    <button
      className="flex items-center gap-1 rounded border border-line px-2 py-1 text-xs hover:bg-field"
      onClick={(event) => {
        event.stopPropagation();
        navigator.clipboard?.writeText(value);
        onCopied?.();
      }}
    >
      <Copy size={13} /> {label}
    </button>
  );
}

function DetailField({ label, value, color }: { label: string; value: unknown; color?: string }) {
  return (
    <div>
      <dt className="flex items-center gap-2 text-xs uppercase text-ink/50">
        {color && <ColorMarker color={color} />}
        {label}
      </dt>
      <dd className="break-words text-sm">{String(value ?? "")}</dd>
    </div>
  );
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warn" | "danger" }) {
  const styles = {
    neutral: "border-line bg-field text-ink",
    good: "border-green-200 bg-green-50 text-green-800",
    warn: "border-yellow-200 bg-yellow-50 text-yellow-800",
    danger: "border-red-200 bg-red-50 text-red-800"
  };
  return <span className={`rounded border px-2 py-1 text-xs font-medium ${styles[tone]}`}>{children}</span>;
}

function WorkStatusSelect({
  value,
  onChange
}: {
  value: WorkStatus;
  onChange: (status: WorkStatus) => void;
}) {
  return (
    <select
      className="rounded border border-line px-2 py-1 text-xs"
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
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");
  const [inspection, setInspection] = useState<UploadInspectionResponse | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [selectedRow, setSelectedRow] = useState<RowResult | null>(null);
  const [filters, setFilters] = useState<Filters>({ action: "", validation: "", review: "", apply: "", search: "" });
  const [queueAction, setQueueAction] = useState("");
  const [sinInput, setSinInput] = useState("");
  const [lookupResult, setLookupResult] = useState<SINLookupResponse | null>(null);
  const [previewRegion, setPreviewRegion] = useState("");
  const [previewSin, setPreviewSin] = useState("");

  const sessionQuery = useQuery({ queryKey: ["session"], queryFn: session });
  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["session"] })
  });
  const uploadMutation = useMutation({ mutationFn: inspectUploads, onSuccess: setInspection });
  const jobMutation = useMutation({
    mutationFn: createJob,
    onSuccess: (data) => {
      setJobId(data.job_id);
      setLookupResult(null);
      window.history.replaceState(null, "", `/?job=${data.job_id}`);
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
  const regions = useMemo(() => [...new Set(rows.map((row) => row.Region || row.sheet_name).filter(Boolean))], [rows]);
  const selectedRegion = previewRegion || regions[0] || "";
  const detail = detailQuery.data ?? selectedRow;
  const summary = useMemo(() => {
    const count = (predicate: (row: RowResult) => boolean) => rows.filter(predicate).length;
    return {
      ready: count((row) => row.Apply_This === "YES"),
      change: count((row) => row.Final_Action === "CHANGE_TICKET"),
      complete: count((row) => row.Final_Action === "COMPLETE_INFO"),
      awaiting: count((row) => row.Final_Action === "AWAITING_USAP"),
      manual: count((row) => row.Needs_Manual_Review),
      applied: count((row) => row.Work_Status === "Applied")
    };
  }, [rows]);
  const sortedRows = useMemo(
    () => [...rows].sort((a, b) => (a.Region || a.sheet_name).localeCompare(b.Region || b.sheet_name) || a.Row_Index - b.Row_Index),
    [rows]
  );
  const filteredRows = useMemo(() => {
    return sortedRows.filter((row) => {
      const text = JSON.stringify(row).toLowerCase();
      return (
        (!filters.action || row.Final_Action === filters.action) &&
        (!filters.validation || row.Validation_Status === filters.validation) &&
        (!filters.review || String(row.Needs_Manual_Review) === filters.review) &&
        (!filters.apply || row.Apply_This === filters.apply) &&
        (!filters.search || text.includes(filters.search.toLowerCase()))
      );
    });
  }, [sortedRows, filters]);
  const queueRows = useMemo(() => {
    return sortedRows.filter((row) => {
      if (queueAction === "READY") return row.Apply_This === "YES";
      if (queueAction) return row.Final_Action === queueAction;
      return row.Apply_This === "YES";
    });
  }, [sortedRows, queueAction]);
  const previewRows = useMemo(() => {
    return sortedRows.filter((row) => {
      const regionMatch = !selectedRegion || (row.Region || row.sheet_name) === selectedRegion;
      const sinMatch = !previewSin || normalizeSin(row.SIN).includes(normalizeSin(previewSin));
      return regionMatch && sinMatch;
    });
  }, [sortedRows, selectedRegion, previewSin]);

  if (sessionQuery.isLoading) {
    return <div className="p-8">Loading...</div>;
  }
  if (!sessionQuery.data?.authenticated) {
    return <LoginPage onLogin={(secret) => loginMutation.mutateAsync(secret).then(() => undefined)} />;
  }

  const markCopied = (rowId: string) => {
    if (jobId) workStatusMutation.mutate({ rowId, status: "Copied" });
  };
  const updateStatus = (rowId: string, status: WorkStatus) => {
    if (jobId) workStatusMutation.mutate({ rowId, status });
  };
  const openRow = (rowId: string) => {
    const row = rows.find((item) => item.row_id === rowId);
    if (row) setSelectedRow(row);
  };
  const runLookup = () => {
    if (jobId && sinInput.trim()) lookupMutation.mutate({ currentJobId: jobId, sin: sinInput });
  };
  const setQuickFilter = (next: Partial<Filters>) => {
    setActiveTab("dashboard");
    setFilters({ action: "", validation: "", review: "", apply: "", search: filters.search, ...next });
  };

  return (
    <Shell
      onLogout={async () => {
        await logout();
        queryClient.invalidateQueries({ queryKey: ["session"] });
      }}
    >
      <div className="mb-5 flex flex-wrap gap-2">
        {[
          ["dashboard", "Dashboard"],
          ["apply", "Apply Queue"],
          ["sin", "SIN Lookup"],
          ["preview", "Spreadsheet Preview"],
          ["exports", "Exports"]
        ].map(([key, label]) => (
          <button
            key={key}
            className={`rounded border px-3 py-2 text-sm ${activeTab === key ? "border-pine bg-pine text-white" : "border-line bg-white hover:bg-field"}`}
            onClick={() => setActiveTab(key as Tab)}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === "dashboard" && (
        <section className="grid gap-5 lg:grid-cols-[420px_1fr]">
          <div className="space-y-5">
            <div className="rounded border border-line bg-white p-4">
              <h2 className="mb-3 flex items-center gap-2 font-semibold">
                <FileCheck2 size={18} /> Upload Center
              </h2>
              <input
                type="file"
                multiple
                accept=".xlsx,.xls,.txt"
                className="mb-3 w-full rounded border border-line p-2"
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  if (files.length) uploadMutation.mutate(files);
                }}
              />
              {uploadMutation.isPending && <p className="text-sm text-ink/60">Inspecting files...</p>}
              {inspection && (
                <button
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded bg-pine px-3 py-2 font-medium text-white"
                  onClick={() => jobMutation.mutate(inspection.upload_id)}
                >
                  <Play size={16} /> Process Report
                </button>
              )}
            </div>

            {inspection && (
              <div className="rounded border border-line bg-white p-4">
                <h2 className="mb-3 font-semibold">File Validation Preview</h2>
                <div className="space-y-3">
                  {inspection.files.map((file) => (
                    <div key={file.file_id} className="rounded border border-line p-3">
                      <div className="flex justify-between gap-3">
                        <strong className="truncate">{file.filename}</strong>
                        <span className="rounded bg-field px-2 py-1 text-xs">{file.kind}</span>
                      </div>
                      <p className="mt-1 text-sm text-ink/65">
                        {file.row_count} rows, {file.column_count} columns
                      </p>
                      {file.dictionary_detection && <p className="text-sm text-pine">{file.dictionary_detection.detected_type}</p>}
                      {[...file.warnings, ...file.missing_columns.map((col) => `Missing ${col}`)].map((warning) => (
                        <p className="text-sm text-coral" key={warning}>{warning}</p>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-5">
            <div className="rounded border border-line bg-white p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-semibold">Processing Summary</h2>
                {jobId && (
                  <button className="flex items-center gap-2 rounded border border-line px-3 py-2 text-sm" onClick={() => jobQuery.refetch()}>
                    <RefreshCw size={16} /> Refresh
                  </button>
                )}
              </div>
              <div className="grid gap-3 md:grid-cols-6">
                <Stat label="Ready" value={summary.ready} />
                <Stat label="Applied" value={summary.applied} />
                <Stat label="Change" value={summary.change} />
                <Stat label="Complete" value={summary.complete} />
                <Stat label="Awaiting" value={summary.awaiting} />
                <Stat label="Manual" value={summary.manual || jobQuery.data?.summary.manual_review_count || 0} />
              </div>
              {jobQuery.data && <p className="mt-3 text-sm text-ink/60">{jobQuery.data.message}</p>}
            </div>

            <div className="rounded border border-line bg-white p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-semibold">Results Table</h2>
                <div className="flex flex-wrap gap-2">
                  <button className="rounded border border-line px-2 py-2 text-sm hover:bg-field" onClick={() => setQuickFilter({ apply: "YES" })}>Apply YES</button>
                  {["CHANGE_TICKET", "COMPLETE_INFO", "AWAITING_USAP", "MANUAL_REVIEW", "REMOVE_FROM_TICKET"].map((action) => (
                    <button key={action} className="rounded border border-line px-2 py-2 text-sm hover:bg-field" onClick={() => setQuickFilter({ action })}>
                      {action.replace(/_/g, " ")}
                    </button>
                  ))}
                  <button className="rounded border border-line px-2 py-2 text-sm hover:bg-field" onClick={() => setFilters({ action: "", validation: "", review: "", apply: "", search: "" })}>Clear</button>
                </div>
              </div>
              <div className="mb-3 flex flex-wrap gap-2">
                <select className="rounded border border-line px-2 py-2 text-sm" value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })}>
                  <option value="">Final Action</option>
                  {[...new Set(rows.map((row) => row.Final_Action))].map((value) => <option key={value}>{value}</option>)}
                </select>
                <select className="rounded border border-line px-2 py-2 text-sm" value={filters.apply} onChange={(e) => setFilters({ ...filters, apply: e.target.value })}>
                  <option value="">Apply</option>
                  <option value="YES">YES</option>
                  <option value="NO">NO</option>
                </select>
                <select className="rounded border border-line px-2 py-2 text-sm" value={filters.validation} onChange={(e) => setFilters({ ...filters, validation: e.target.value })}>
                  <option value="">Validation</option>
                  {[...new Set(rows.map((row) => row.Validation_Status))].map((value) => <option key={value}>{value}</option>)}
                </select>
                <select className="rounded border border-line px-2 py-2 text-sm" value={filters.review} onChange={(e) => setFilters({ ...filters, review: e.target.value })}>
                  <option value="">Review</option>
                  <option value="true">Needs Review</option>
                  <option value="false">No Review</option>
                </select>
                <div className="flex items-center gap-2 rounded border border-line px-2">
                  <Search size={15} />
                  <input className="py-2 text-sm outline-none" placeholder="Search" value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} />
                </div>
              </div>
              <CorrectionTable rows={filteredRows} onOpen={setSelectedRow} onCopied={markCopied} onStatus={updateStatus} />
            </div>
          </div>
        </section>
      )}

      {activeTab === "apply" && (
        <section className="space-y-4">
          <div className="rounded border border-line bg-white p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">Apply Queue</h2>
                <p className="text-sm text-ink/60">Rows sorted by region and row number. Default view is ready to apply.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {[
                  ["READY", "Ready to Apply"],
                  ["CHANGE_TICKET", "Change Ticket"],
                  ["COMPLETE_INFO", "Complete Fields"],
                  ["AWAITING_USAP", "Awaiting USAP"],
                  ["MANUAL_REVIEW", "Manual Review"],
                  ["REMOVE_FROM_TICKET", "Remove from Ticket"]
                ].map(([value, label]) => (
                  <button
                    key={value}
                    className={`rounded border px-2 py-2 text-sm ${queueAction === value || (!queueAction && value === "READY") ? "border-pine bg-pine text-white" : "border-line hover:bg-field"}`}
                    onClick={() => setQueueAction(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <CorrectionTable rows={queueRows} onOpen={setSelectedRow} onCopied={markCopied} onStatus={updateStatus} showSin />
          </div>
        </section>
      )}

      {activeTab === "sin" && (
        <section className="space-y-4">
          <div className="rounded border border-line bg-white p-4">
            <h2 className="mb-3 font-semibold">SIN Lookup</h2>
            <div className="flex flex-col gap-2 md:flex-row">
              <input
                className="min-h-12 flex-1 rounded border border-line px-3 text-lg outline-none focus:border-pine"
                placeholder="Paste SIN from Numbers or Excel"
                value={sinInput}
                onChange={(event) => setSinInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") runLookup();
                }}
              />
              <button className="rounded bg-pine px-4 py-3 font-medium text-white" onClick={runLookup} disabled={!jobId || !sinInput.trim()}>
                Search SIN
              </button>
            </div>
            {lookupMutation.isPending && <p className="mt-3 text-sm text-ink/60">Searching current job...</p>}
          </div>

          {lookupResult && (
            <div className="space-y-3">
              <div className="rounded border border-line bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase text-ink/50">SIN searched</p>
                    <h3 className="text-lg font-semibold">{lookupResult.query}</h3>
                  </div>
                  <Badge tone={lookupResult.match_count ? "good" : "warn"}>{lookupResult.match_count} match{lookupResult.match_count === 1 ? "" : "es"}</Badge>
                </div>
                {lookupResult.match_count === 0 && <p className="mt-3 text-sm text-ink/70">No correction found for this SIN in the current job.</p>}
              </div>

              {lookupResult.matches.map((match) => (
                <SINLookupCard
                  key={match.row_id}
                  match={match}
                  onOpen={() => openRow(match.row_id)}
                  onCopied={() => markCopied(match.row_id)}
                  onStatus={(status) => updateStatus(match.row_id, status)}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {activeTab === "preview" && (
        <section className="space-y-4">
          <div className="rounded border border-line bg-white p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">Spreadsheet Preview</h2>
                <p className="text-sm text-ink/60">Lightweight verification view grouped by region tab.</p>
              </div>
              <div className="flex items-center gap-2 rounded border border-line px-2">
                <Search size={15} />
                <input className="py-2 text-sm outline-none" placeholder="Search SIN" value={previewSin} onChange={(event) => setPreviewSin(event.target.value)} />
              </div>
            </div>
            <div className="mb-3 flex flex-wrap gap-2">
              {regions.map((region) => (
                <button
                  key={region}
                  className={`rounded border px-3 py-2 text-sm ${selectedRegion === region ? "border-pine bg-pine text-white" : "border-line hover:bg-field"}`}
                  onClick={() => setPreviewRegion(region)}
                >
                  {region}
                </button>
              ))}
            </div>
            <div className="max-h-[560px] overflow-auto border border-line">
              <table className="min-w-[1200px] text-left text-sm">
                <thead className="sticky top-0 bg-field">
                  <tr>
                    <th className="p-2">SIN</th>
                    <th className="p-2">Row</th>
                    <th className="p-2">Current Last</th>
                    <th className="p-2">Current First</th>
                    <th className="p-2">Current NPI</th>
                    <th className="p-2">Current CBCode</th>
                    <th className="p-2">Recommended Last</th>
                    <th className="p-2">Recommended First</th>
                    <th className="p-2">Recommended NPI</th>
                    <th className="p-2">Recommended CBCode</th>
                    <th className="p-2">Comments</th>
                    <th className="p-2">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row) => (
                    <tr key={row.row_id} className="cursor-pointer border-t border-line hover:bg-field" onClick={() => setSelectedRow(row)}>
                      <td className="p-2">{row.SIN}</td>
                      <td className="p-2">{row.Row_Index}</td>
                      <td className="p-2">{row.Current_Last_Title}</td>
                      <td className="p-2">{row.Current_First}</td>
                      <td className="p-2">{row.Current_NPI}</td>
                      <td className="p-2">{row.Current_CBCode}</td>
                      <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_Last_Title} /></span>{row.Recommended_Last_Title}</td>
                      <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_First} /></span>{row.Recommended_First}</td>
                      <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_NPI} /></span>{row.Recommended_NPI}</td>
                      <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_CBCode} /></span>{row.Recommended_CBCode}</td>
                      <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_Comments} /></span>{row.Recommended_Comments}</td>
                      <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_Source} /></span>{row.Recommended_Source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {activeTab === "exports" && (
        <section className="rounded border border-line bg-white p-4">
          <h2 className="mb-3 font-semibold">Export Center</h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {EXPORTS.map((kind) => (
              <a key={kind} className="flex items-center justify-center gap-2 rounded border border-line px-3 py-3 text-sm hover:bg-field" href={jobId ? exportUrl(jobId, kind) : "#"}>
                <Download size={15} /> {kind}
              </a>
            ))}
          </div>
        </section>
      )}

      {selectedRow && detail && (
        <aside className="fixed inset-y-0 right-0 w-full max-w-2xl overflow-auto border-l border-line bg-white p-5 shadow-xl">
          <button className="mb-4 rounded border border-line px-3 py-2 text-sm" onClick={() => setSelectedRow(null)}>
            Close
          </button>
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Row Detail</h2>
              <p className="text-sm text-ink/60">{detail.Region || detail.sheet_name} · Row {detail.Row_Index} · SIN {detail.SIN}</p>
            </div>
            <WorkStatusSelect value={detail.Work_Status} onChange={(statusValue) => updateStatus(detail.row_id, statusValue)} />
          </div>

          <div className="space-y-4">
            <section className="rounded border border-line p-4">
              <div className="mb-3 flex flex-wrap gap-2">
                <Badge tone={detail.Apply_This === "YES" ? "good" : "warn"}>Apply {detail.Apply_This}</Badge>
                <Badge>{detail.Final_Action}</Badge>
                <Badge>{detail.Quick_Action}</Badge>
              </div>
              <p className="text-sm">{detail.Analyst_Next_Step}</p>
            </section>

            <section className="rounded border border-line p-4">
              <h3 className="mb-3 font-semibold">Current Values</h3>
              <dl className="grid gap-3 sm:grid-cols-2">
                <DetailField label="Last - Title" value={detail.Current_Last_Title} />
                <DetailField label="First" value={detail.Current_First} />
                <DetailField label="NPI" value={detail.Current_NPI} />
                <DetailField label="CBCode" value={detail.Current_CBCode} />
              </dl>
            </section>

            <section className="rounded border border-line p-4">
              <h3 className="mb-3 font-semibold">Recommended Values</h3>
              <dl className="grid gap-3 sm:grid-cols-2">
                <DetailField label="Last - Title" value={detail.Recommended_Last_Title} color={detail.Cell_Color_Last_Title} />
                <DetailField label="First" value={detail.Recommended_First} color={detail.Cell_Color_First} />
                <DetailField label="NPI" value={detail.Recommended_NPI} color={detail.Cell_Color_NPI} />
                <DetailField label="CBCode" value={detail.Recommended_CBCode} color={detail.Cell_Color_CBCode} />
                <DetailField label="Comments" value={detail.Recommended_Comments} color={detail.Cell_Color_Comments} />
                <DetailField label="Source" value={detail.Recommended_Source} color={detail.Cell_Color_Source} />
              </dl>
              <div className="mt-3 flex flex-wrap gap-2">
                <CopyButton label="Copy Last" value={detail.Recommended_Last_Title} onCopied={() => markCopied(detail.row_id)} />
                <CopyButton label="Copy First" value={detail.Recommended_First} onCopied={() => markCopied(detail.row_id)} />
                <CopyButton label="Copy NPI" value={detail.Recommended_NPI} onCopied={() => markCopied(detail.row_id)} />
                <CopyButton label="Copy CBCode" value={detail.Recommended_CBCode} onCopied={() => markCopied(detail.row_id)} />
                <CopyButton label="Copy Comments" value={detail.Recommended_Comments} onCopied={() => markCopied(detail.row_id)} />
                <CopyButton label="Copy Source" value={detail.Recommended_Source} onCopied={() => markCopied(detail.row_id)} />
                <CopyButton label="Copy row" value={fullCorrectionRow(detail)} onCopied={() => markCopied(detail.row_id)} />
              </div>
            </section>

            <section className="rounded border border-line p-4">
              <h3 className="mb-3 font-semibold">Why</h3>
              <dl className="grid gap-3">
                <DetailField label="Correction Summary" value={detail.Correction_Summary} />
                <DetailField label="Validation Status" value={detail.Validation_Status} />
                <DetailField label="Matched Dictionary" value={detail.Matched_Dictionary} />
                <DetailField label="Matched Provider" value={detail.Matched_Provider_Name} />
                <DetailField label="AI Explanation" value={detail.AI_Explanation} />
                <DetailField label="Manual Reason" value={detail.Manual_Reason} />
              </dl>
            </section>
          </div>
        </aside>
      )}
    </Shell>
  );
}

function CorrectionTable({
  rows,
  onOpen,
  onCopied,
  onStatus,
  showSin = false
}: {
  rows: RowResult[];
  onOpen: (row: RowResult) => void;
  onCopied: (rowId: string) => void;
  onStatus: (rowId: string, status: WorkStatus) => void;
  showSin?: boolean;
}) {
  return (
    <div className="max-h-[520px] overflow-auto border border-line">
      <table className="min-w-[1450px] text-left text-sm">
        <thead className="sticky top-0 bg-field">
          <tr>
            {showSin && <th className="p-2">SIN</th>}
            <th className="p-2">Region</th>
            <th className="p-2">Row</th>
            <th className="p-2">Quick Action</th>
            <th className="p-2">Apply</th>
            <th className="p-2">Status</th>
            <th className="p-2">Current Provider</th>
            <th className="p-2">Recommended Provider</th>
            <th className="p-2">Recommended NPI</th>
            <th className="p-2">Recommended CBCode</th>
            <th className="p-2">Comments</th>
            <th className="p-2">Source</th>
            <th className="p-2">Copy</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.row_id} className="cursor-pointer border-t border-line hover:bg-field" onClick={() => onOpen(row)}>
              {showSin && <td className="p-2">{row.SIN}</td>}
              <td className="p-2">{row.Region || row.sheet_name}</td>
              <td className="p-2">{row.Row_Index}</td>
              <td className="p-2 font-medium">{row.Quick_Action || row.Final_Action}</td>
              <td className="p-2">{row.Apply_This}</td>
              <td className="p-2"><WorkStatusSelect value={row.Work_Status} onChange={(status) => onStatus(row.row_id, status)} /></td>
              <td className="p-2">{providerSummary(row.Current_Last_Title, row.Current_First)}</td>
              <td className="p-2">{providerSummary(row.Recommended_Last_Title, row.Recommended_First)}</td>
              <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_NPI} /></span>{row.Recommended_NPI}</td>
              <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_CBCode} /></span>{row.Recommended_CBCode}</td>
              <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_Comments} /></span>{row.Recommended_Comments}</td>
              <td className="p-2"><span className="mr-2"><ColorMarker color={row.Cell_Color_Source} /></span>{row.Recommended_Source}</td>
              <td className="p-2">
                <div className="flex flex-wrap gap-1">
                  <CopyButton label="NPI" value={row.Recommended_NPI} onCopied={() => onCopied(row.row_id)} />
                  <CopyButton label="CB" value={row.Recommended_CBCode} onCopied={() => onCopied(row.row_id)} />
                  <CopyButton label="Row" value={fullCorrectionRow(row)} onCopied={() => onCopied(row.row_id)} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SINLookupCard({
  match,
  onOpen,
  onCopied,
  onStatus
}: {
  match: SINLookupMatch;
  onOpen: () => void;
  onCopied: () => void;
  onStatus: (status: WorkStatus) => void;
}) {
  return (
    <div className="rounded border border-line bg-white p-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase text-ink/50">SIN</p>
          <h3 className="text-lg font-semibold">{match.sin}</h3>
          <p className="text-sm text-ink/60">{match.region} · Row {match.row_index} · {match.current_provider}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{match.final_action}</Badge>
          <Badge tone={match.apply_this === "YES" ? "good" : "warn"}>Apply {match.apply_this}</Badge>
          <WorkStatusSelect value={match.work_status} onChange={onStatus} />
        </div>
      </div>

      <section className="mb-4 rounded border border-line p-3">
        <h4 className="mb-2 font-semibold">Action</h4>
        <p className="text-sm"><strong>{match.quick_action}</strong></p>
        <p className="mt-1 text-sm">{match.analyst_next_step}</p>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded border border-line p-3">
          <h4 className="mb-2 font-semibold">Current Values</h4>
          <dl className="grid gap-2">
            <DetailField label="Last - Title" value={match.current.last_title} />
            <DetailField label="First" value={match.current.first} />
            <DetailField label="NPI" value={match.current.npi} />
            <DetailField label="CBCode" value={match.current.cbcode} />
          </dl>
        </section>
        <section className="rounded border border-line p-3">
          <h4 className="mb-2 font-semibold">Recommended Values</h4>
          <dl className="grid gap-2">
            <DetailField label="Last - Title" value={match.recommended.last_title} color={match.cell_colors.last_title} />
            <DetailField label="First" value={match.recommended.first} color={match.cell_colors.first} />
            <DetailField label="NPI" value={match.recommended.npi} color={match.cell_colors.npi} />
            <DetailField label="CBCode" value={match.recommended.cbcode} color={match.cell_colors.cbcode} />
            <DetailField label="Comments" value={match.recommended.comments} color={match.cell_colors.comments} />
            <DetailField label="Source" value={match.recommended.source} color={match.cell_colors.source} />
          </dl>
          <div className="mt-3 flex flex-wrap gap-2">
            <CopyButton label="Copy Last" value={match.recommended.last_title} onCopied={onCopied} />
            <CopyButton label="Copy First" value={match.recommended.first} onCopied={onCopied} />
            <CopyButton label="Copy NPI" value={match.recommended.npi} onCopied={onCopied} />
            <CopyButton label="Copy CBCode" value={match.recommended.cbcode} onCopied={onCopied} />
            <CopyButton label="Copy Comments" value={match.recommended.comments} onCopied={onCopied} />
            <CopyButton label="Copy Source" value={match.recommended.source} onCopied={onCopied} />
            <CopyButton label="Copy full row" value={fullCorrectionMatch(match)} onCopied={onCopied} />
          </div>
        </section>
      </div>

      <section className="mt-4 rounded border border-line p-3">
        <h4 className="mb-2 font-semibold">Color Guide</h4>
        <div className="grid gap-2 text-sm sm:grid-cols-3">
          {Object.entries(match.cell_colors).map(([field, color]) => (
            <span key={field} className="flex items-center gap-2"><ColorMarker color={color} /> {field}: {color}</span>
          ))}
        </div>
      </section>

      <section className="mt-4 rounded border border-line p-3">
        <h4 className="mb-2 font-semibold">Details</h4>
        <p className="text-sm">{match.correction_summary}</p>
        <p className="mt-1 text-sm text-ink/60">Validation: {match.validation_status}</p>
        {match.manual_reason && <p className="mt-1 text-sm text-coral">Manual reason: {match.manual_reason}</p>}
        <button className="mt-3 rounded border border-line px-3 py-2 text-sm hover:bg-field" onClick={onOpen}>
          Open row detail
        </button>
      </section>
    </div>
  );
}
