import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileCheck2, Play, RefreshCw, Search } from "lucide-react";
import { createJob, exportUrl, getJob, getResults, getRowDetail, inspectUploads, login, logout, session, submitFeedback } from "../api/client";
import { Shell } from "../components/Shell";
import { Stat } from "../components/Stat";
import { LoginPage } from "./LoginPage";
import type { RowResult, UploadInspectionResponse } from "../types/api";

export default function App() {
  const queryClient = useQueryClient();
  const [inspection, setInspection] = useState<UploadInspectionResponse | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [selectedRow, setSelectedRow] = useState<RowResult | null>(null);
  const [filters, setFilters] = useState({ action: "", validation: "", review: "", search: "" });

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

  useEffect(() => {
    const job = new URLSearchParams(window.location.search).get("job");
    if (job) setJobId(job);
  }, []);

  const rows = resultsQuery.data ?? [];
  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const text = JSON.stringify(row).toLowerCase();
      return (
        (!filters.action || row.Final_Action === filters.action) &&
        (!filters.validation || row.Validation_Status === filters.validation) &&
        (!filters.review || String(row.Needs_Manual_Review) === filters.review) &&
        (!filters.search || text.includes(filters.search.toLowerCase()))
      );
    });
  }, [rows, filters]);

  if (sessionQuery.isLoading) {
    return <div className="p-8">Loading...</div>;
  }
  if (!sessionQuery.data?.authenticated) {
    return <LoginPage onLogin={(secret) => loginMutation.mutateAsync(secret).then(() => undefined)} />;
  }

  return (
    <Shell
      onLogout={async () => {
        await logout();
        queryClient.invalidateQueries({ queryKey: ["session"] });
      }}
    >
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
            <div className="grid gap-3 md:grid-cols-4">
              <Stat label="Status" value={jobQuery.data?.status ?? "No job"} />
              <Stat label="Rows" value={jobQuery.data?.summary.total_rows ?? 0} />
              <Stat label="Manual Review" value={jobQuery.data?.summary.manual_review_count ?? 0} />
              <Stat label="AI Rows" value={jobQuery.data?.summary.ai_rows_count ?? 0} />
            </div>
            {jobQuery.data && <p className="mt-3 text-sm text-ink/60">{jobQuery.data.message}</p>}
          </div>

          <div className="rounded border border-line bg-white p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-semibold">Results Table</h2>
              <div className="flex flex-wrap gap-2">
                <select className="rounded border border-line px-2 py-2 text-sm" value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })}>
                  <option value="">Final Action</option>
                  {[...new Set(rows.map((row) => row.Final_Action))].map((value) => <option key={value}>{value}</option>)}
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
            </div>
            <div className="max-h-[420px] overflow-auto border border-line">
              <table className="min-w-full text-left text-sm">
                <thead className="sticky top-0 bg-field">
                  <tr>
                    <th className="p-2">Action</th>
                    <th className="p-2">Validation</th>
                    <th className="p-2">Provider</th>
                    <th className="p-2">CBCode</th>
                    <th className="p-2">Review</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((row) => (
                    <tr key={row.row_id} className="cursor-pointer border-t border-line hover:bg-field" onClick={() => setSelectedRow(row)}>
                      <td className="p-2">{row.Final_Action}</td>
                      <td className="p-2">{row.Validation_Status}</td>
                      <td className="p-2">{row.Matched_Provider_Name ?? String(row.sanitized_original.last_title ?? "")}</td>
                      <td className="p-2">{row.Matched_CBCode ?? ""}</td>
                      <td className="p-2">{row.Needs_Manual_Review ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div className="rounded border border-line bg-white p-4">
              <h2 className="mb-3 font-semibold">Manual Review Queue</h2>
              <div className="space-y-2">
                {rows.filter((row) => row.Needs_Manual_Review).slice(0, 8).map((row) => (
                  <div className="flex items-center justify-between rounded border border-line p-2" key={row.row_id}>
                    <span className="text-sm">{row.Final_Recommendation}</span>
                    <button className="rounded bg-gold px-2 py-1 text-xs text-white" onClick={() => jobId && submitFeedback(jobId, row.row_id, "accepted")}>
                      Accept
                    </button>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded border border-line bg-white p-4">
              <h2 className="mb-3 font-semibold">Export Center</h2>
              <div className="grid grid-cols-2 gap-2">
                {(["full", "manual_review", "high_confidence", "summary"] as const).map((kind) => (
                  <a key={kind} className="flex items-center justify-center gap-2 rounded border border-line px-3 py-2 text-sm hover:bg-field" href={jobId ? exportUrl(jobId, kind) : "#"}>
                    <Download size={15} /> {kind}
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {selectedRow && (
        <aside className="fixed inset-y-0 right-0 w-full max-w-xl overflow-auto border-l border-line bg-white p-5 shadow-xl">
          <button className="mb-4 rounded border border-line px-3 py-2 text-sm" onClick={() => setSelectedRow(null)}>
            Close
          </button>
          <h2 className="mb-2 text-lg font-semibold">Row Detail</h2>
          <p className="mb-4 text-sm text-ink/60">{selectedRow.row_id}</p>
          <pre className="mb-4 overflow-auto rounded bg-field p-3 text-xs">{JSON.stringify(detailQuery.data ?? selectedRow, null, 2)}</pre>
        </aside>
      )}
    </Shell>
  );
}
