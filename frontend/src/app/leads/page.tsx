"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Plus,
  Search,
  UserPlus,
  Upload,
  FileSpreadsheet,
  X,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { useAuth } from "@/providers/auth-provider";
import { fetchLeads } from "@/lib/leads-api";
import { useImportCsv, useLeadStats } from "@/hooks/use-leads";
import type { CsvImportResult } from "@/lib/api/leads";
import { parseApiError } from "@/lib/api-error";
import { ErrorBanner } from "@/components/shared/error-banner";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { RefreshButton } from "@/components/shared/refresh-button";
import { DEFAULT_TIMEZONE } from "@/lib/format";

type Lead = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  company_name: string | null;
  source: string;
  status: string;
  priority: string;
  assigned_user_id: string | null;
};

const statuses = ["new", "contacted", "qualified", "proposal", "won", "lost"];
const priorities = ["low", "medium", "high"];
const sources = [
  "website_form",
  "tracking",
  "whatsapp",
  "facebook_lead_ads",
  "messenger",
  "manual",
  "csv",
];

const statusStyles: Record<string, string> = {
  new: "bg-blue-50 text-blue-700",
  contacted: "bg-cyan-50 text-cyan-700",
  qualified: "bg-emerald-50 text-emerald-700",
  proposal: "bg-violet-50 text-violet-700",
  won: "bg-green-50 text-green-700",
  lost: "bg-red-50 text-red-700",
};

const priorityStyles: Record<string, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};

function formatOption(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function LeadsPage() {
  const { role, user, timezone } = useAuth();
  const isManagerOrAdmin = role === "manager" || role === "admin";
  // User initial for the header avatar — falls back to "?" when session loads
  const userInitial = (user?.display_name || user?.email || "?").charAt(0).toUpperCase();

  const [leads, setLeads] = useState<Lead[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [source, setSource] = useState("");
  const [owner, setOwner] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorStack, setCursorStack] = useState<(string | null)[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // CSV Import Modal state
  const [showCsvModal, setShowCsvModal] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState(false);
  const [csvResult, setCsvResult] = useState<CsvImportResult | null>(null);
  const [csvError, setCsvError] = useState<{ title: string; message: string } | null>(null);

  const importCsvMutation = useImportCsv();
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useLeadStats();

  useEffect(() => {
    let cancelled = false;

    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");

      try {
        const params = new URLSearchParams({ limit: "25" });
        if (search.trim()) params.set("q", search.trim());
        if (status) params.set("status", status);
        if (priority) params.set("priority", priority);
        if (source) params.set("source", source);
        if (owner.trim()) params.set("assigned_user_id", owner.trim());
        if (cursor) params.set("cursor", cursor);

        const result = await fetchLeads<Lead>(params);

        if (!cancelled) {
          setLeads(result.data);
          setNextCursor(result.meta.next_cursor);
          setHasMore(result.meta.has_more);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Could not load leads."
          );
          setLeads([]);
          setNextCursor(null);
          setHasMore(false);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [search, status, priority, source, owner, cursor, refreshTrigger]);

  function resetPagination() {
    setCursor(null);
    setCursorStack([]);
  }

  function goToNextPage() {
    if (!hasMore || !nextCursor) return;
    setCursorStack((stack) => [...stack, cursor]);
    setCursor(nextCursor);
  }

  function goToPreviousPage() {
    if (cursorStack.length === 0) return;
    const previousCursor = cursorStack[cursorStack.length - 1];
    setCursorStack((stack) => stack.slice(0, -1));
    setCursor(previousCursor);
  }

  const handleCsvSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!csvFile) return;

    setCsvError(null);
    setCsvResult(null);

    try {
      const res = await importCsvMutation.mutateAsync({
        file: csvFile,
        dryRun,
      });
      setCsvResult(res);
      if (!dryRun) {
        setRefreshTrigger((prev) => prev + 1);
        void refetchStats();
      }
    } catch (err) {
      const parsed = parseApiError(err);
      setCsvError({ title: parsed.title, message: parsed.message });
    }
  };

  const handleCloseCsvModal = () => {
    setShowCsvModal(false);
    setCsvFile(null);
    setCsvResult(null);
    setCsvError(null);
    setDryRun(false);
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-6 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">
              <Link href="/" className="hover:text-blue-600">
                Workspace
              </Link>
              {" / Leads"}
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">
              Lead Management
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 sm:inline-flex">
              Timezone: {timezone || DEFAULT_TIMEZONE}
            </span>
            <div
              title={user?.display_name || user?.email || "User"}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700"
            >
              {userInitial}
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-7xl space-y-6 p-6 sm:p-8">
          <section className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold text-slate-900">Leads</h2>
              <p className="mt-1 text-sm text-slate-500">
                Manage, import, and track your potential customers.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <RefreshButton
                onRefresh={() => {
                  setRefreshTrigger((prev) => prev + 1);
                  void refetchStats();
                }}
                isRefreshing={loading || statsLoading}
                iconSize={17}
                className="px-3.5 py-2.5 text-sm font-semibold"
              />

              {/* CSV Import Button (Manager/Admin only) */}
              {isManagerOrAdmin && (
                <button
                  onClick={() => setShowCsvModal(true)}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
                >
                  <Upload size={17} />
                  Import CSV
                </button>
              )}

              <Link
                href="/leads/new"
                className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 shadow-sm"
              >
                <Plus size={18} />
                Add New Lead
              </Link>
            </div>
          </section>

          <section className="grid gap-4 sm:grid-cols-3">
            {[
              {
                label: "Total leads overall",
                value: stats ? stats.total.toLocaleString() : (statsLoading ? "--" : "0"),
                note: "All leads in workspace",
              },
              {
                label: "Total new leads",
                value: stats ? stats.new.toLocaleString() : (statsLoading ? "--" : "0"),
                note: "Status = New",
              },
              {
                label: "Total high priority",
                value: stats ? stats.high_priority.toLocaleString() : (statsLoading ? "--" : "0"),
                note: "Priority = High",
              },
            ].map((metric) => (
              <article
                key={metric.label}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <p className="text-sm font-medium text-slate-500">{metric.label}</p>
                <p className="mt-3 text-2xl font-bold text-slate-900">
                  {statsLoading && !stats ? "--" : metric.value}
                </p>
                {"note" in metric && (
                  <p className="mt-1 text-xs text-slate-400">{metric.note}</p>
                )}
              </article>
            ))}
          </section>

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 p-5">
              <h3 className="font-semibold text-slate-900">All Leads</h3>
              <p className="mt-1 text-xs text-slate-500">
                {loading ? "Loading records..." : `${leads.length} records shown`}
              </p>
            </div>

            <div className="grid gap-3 border-b border-slate-100 p-5 sm:grid-cols-2 xl:grid-cols-5">
              <div className="relative sm:col-span-2 xl:col-span-1">
                <Search
                  size={18}
                  aria-hidden="true"
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  type="search"
                  aria-label="Search leads"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    resetPagination();
                  }}
                  placeholder="Search leads..."
                  maxLength={100}
                  className="w-full rounded-lg border border-slate-200 py-2.5 pl-10 pr-4 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>

              <select
                aria-label="Filter by status"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  resetPagination();
                }}
                className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-600 outline-none focus:border-blue-500"
              >
                <option value="">All statuses</option>
                {statuses.map((item) => (
                  <option key={item} value={item}>
                    {formatOption(item)}
                  </option>
                ))}
              </select>

              <select
                aria-label="Filter by priority"
                value={priority}
                onChange={(event) => {
                  setPriority(event.target.value);
                  resetPagination();
                }}
                className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-600 outline-none focus:border-blue-500"
              >
                <option value="">All priorities</option>
                {priorities.map((item) => (
                  <option key={item} value={item}>
                    {formatOption(item)}
                  </option>
                ))}
              </select>

              <select
                aria-label="Filter by source"
                value={source}
                onChange={(event) => {
                  setSource(event.target.value);
                  resetPagination();
                }}
                className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-600 outline-none focus:border-blue-500"
              >
                <option value="">All sources</option>
                {sources.map((item) => (
                  <option key={item} value={item}>
                    {formatOption(item)}
                  </option>
                ))}
              </select>

              <input
                aria-label="Filter by assigned user ID (UUID)"
                type="text"
                placeholder="Owner UUID (optional)"
                title="Paste a team member's user ID to filter by assignee"
                value={owner}
                onChange={(event) => {
                  setOwner(event.target.value);
                  resetPagination();
                }}
                className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
              />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[850px] text-left text-sm">
                <thead className="bg-slate-50">
                  <tr className="text-xs uppercase tracking-wide text-slate-400">
                    <th className="px-5 py-4 font-medium">Lead</th>
                    <th className="px-5 py-4 font-medium">Company</th>
                    <th className="px-5 py-4 font-medium">Source</th>
                    <th className="px-5 py-4 font-medium">Status</th>
                    <th className="px-5 py-4 font-medium">Priority</th>
                    <th className="px-5 py-4 font-medium">Assigned to</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {!loading &&
                    !error &&
                    leads.map((lead) => (
                      <tr key={lead.id} className="hover:bg-slate-50 transition">
                        <td className="px-5 py-4">
                          <Link
                            href={`/leads/${lead.id}`}
                            className="font-semibold text-slate-800 hover:text-blue-600"
                          >
                            {lead.name}
                          </Link>
                          <p className="mt-1 text-xs text-slate-500">
                            {lead.email || lead.phone || "No contact details"}
                          </p>
                        </td>
                        <td className="px-5 py-4 text-slate-600">
                          {lead.company_name || "--"}
                        </td>
                        <td className="px-5 py-4 capitalize text-slate-600">
                          {formatOption(lead.source)}
                        </td>
                        <td className="px-5 py-4">
                          <span
                            className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize ${statusStyles[lead.status] ?? "bg-slate-100 text-slate-600"}`}
                          >
                            {formatOption(lead.status)}
                          </span>
                        </td>
                        <td className="px-5 py-4">
                          <span
                            className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize ${priorityStyles[lead.priority] ?? "bg-slate-100 text-slate-600"}`}
                          >
                            {formatOption(lead.priority)}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-slate-500">
                          {lead.assigned_user_id ? (
                            <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 rounded-full px-2 py-0.5">
                              Assigned
                            </span>
                          ) : (
                            <span className="text-xs text-slate-400 italic">
                              Unassigned
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}

                  {!loading && !error && leads.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-5 py-16 text-center">
                        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
                          <UserPlus size={23} aria-hidden="true" />
                        </div>
                        <p className="mt-3 font-medium text-slate-700">
                          No leads found
                        </p>
                        <p className="mt-1 text-sm text-slate-400">
                          Try changing your search or filters, or add a new lead.
                        </p>
                      </td>
                    </tr>
                  )}
                  {loading && (
                    <tr>
                      <td colSpan={6} className="px-5 py-16 text-center text-slate-500">
                        Loading leads...
                      </td>
                    </tr>
                  )}
                  {!loading && error && (
                    <tr>
                      <td colSpan={6} className="px-5 py-8 text-center">
                        <p role="alert" className="text-sm text-red-700">
                          {error}
                        </p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {!loading && !error && (
            <nav
              aria-label="Lead list pagination"
              className="flex flex-wrap items-center justify-between gap-3"
            >
              <p className="text-sm text-slate-500">
                Showing {leads.length} leads on this page
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={cursorStack.length === 0}
                  onClick={goToPreviousPage}
                  className="rounded-lg bg-slate-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={!hasMore || !nextCursor}
                  onClick={goToNextPage}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  Next
                </button>
              </div>
            </nav>
          )}
        </div>
      </main>

      {/* CSV Import Modal */}
      {showCsvModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <FileSpreadsheet size={20} className="text-blue-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Import Leads from CSV
                </h3>
              </div>
              <button
                onClick={handleCloseCsvModal}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>

            {/* Error display */}
            {csvError && (
              <div className="mt-4">
                <ErrorBanner
                  title={csvError.title}
                  message={csvError.message}
                  onDismiss={() => setCsvError(null)}
                />
              </div>
            )}

            {/* Import Results Display */}
            {csvResult ? (
              <div className="mt-4 space-y-4">
                <div
                  className={`rounded-xl border p-4 ${
                    csvResult.error_count > 0
                      ? "border-amber-200 bg-amber-50/60"
                      : "border-green-200 bg-green-50/60"
                  }`}
                >
                  <p className="font-semibold text-slate-900">
                    {csvResult.dry_run
                      ? "Dry Run Completed (No changes saved)"
                      : "CSV Import Completed"}
                  </p>
                  <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                    <div className="rounded-lg bg-white p-2 shadow-xs">
                      <p className="text-xs text-slate-500">Total Rows</p>
                      <p className="text-base font-bold text-slate-900">
                        {csvResult.total_rows}
                      </p>
                    </div>
                    <div className="rounded-lg bg-white p-2 shadow-xs">
                      <p className="text-xs text-green-700">Created</p>
                      <p className="text-base font-bold text-green-700">
                        {csvResult.created_count}
                      </p>
                    </div>
                    <div className="rounded-lg bg-white p-2 shadow-xs">
                      <p className="text-xs text-amber-700">Duplicates</p>
                      <p className="text-base font-bold text-amber-700">
                        {csvResult.duplicate_count}
                      </p>
                    </div>
                    <div className="rounded-lg bg-white p-2 shadow-xs">
                      <p className="text-xs text-red-700">Errors</p>
                      <p className="text-base font-bold text-red-700">
                        {csvResult.error_count}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Row-level errors and duplicates breakdown */}
                {csvResult.errors.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-slate-700 mb-2">
                      Row Details & Validation Issues:
                    </p>
                    <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-2 space-y-1.5 text-xs">
                      {csvResult.errors.map((err, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-2 rounded-lg bg-white p-2 shadow-2xs"
                        >
                          <span
                            className={`rounded px-1.5 py-0.5 font-bold ${
                              err.code === "duplicate_lead"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-red-100 text-red-800"
                            }`}
                          >
                            Row {err.row}
                          </span>
                          <span className="text-slate-700 flex-1">
                            {err.message}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex justify-end pt-2">
                  <button
                    onClick={handleCloseCsvModal}
                    className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700"
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              /* Upload Form */
              <form onSubmit={handleCsvSubmit} className="mt-4 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Upload CSV File
                  </label>
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    required
                    onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                    className="w-full text-xs text-slate-500 file:mr-3 file:rounded-lg file:border-0 file:bg-blue-50 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-blue-700 hover:file:bg-blue-100"
                  />
                  <p className="mt-1 text-xs text-slate-400">
                    File must include a &apos;name&apos; column and either
                    &apos;email&apos; or &apos;phone&apos;. Max 10 MB / 10,000 rows.
                  </p>
                </div>

                <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={dryRun}
                    onChange={(e) => setDryRun(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>
                    Dry Run — Validate file without creating leads in database
                  </span>
                </label>

                <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={handleCloseCsvModal}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={importCsvMutation.isPending || !csvFile}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {importCsvMutation.isPending ? (
                      <>
                        <LoadingSpinner size="sm" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <Upload size={14} />
                        {dryRun ? "Test CSV (Dry Run)" : "Start Import"}
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
