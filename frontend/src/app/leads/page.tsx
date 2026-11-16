"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Search, UserPlus } from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { fetchLeads } from "@/lib/leads-api";

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
              : "Could not load leads.",
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
  }, [search, status, priority, source, owner, cursor]);

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
          <div
            aria-hidden="true"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-200 text-sm font-semibold text-slate-700"
          >
            U
          </div>
        </header>

        <div className="mx-auto max-w-7xl space-y-6 p-6 sm:p-8">
          <section className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold text-slate-900">Leads</h2>
              <p className="mt-1 text-sm text-slate-500">
                Manage and track your potential customers.
              </p>
            </div>
            <Link
              href="/leads/new"
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700"
            >
              <Plus size={18} />
              Add New Lead
            </Link>
          </section>

          <section className="grid gap-4 sm:grid-cols-3">
            {[
              { label: "Leads on this page", value: leads.length },
              {
                label: "New on this page",
                value: leads.filter((lead) => lead.status === "new").length,
              },
              {
                label: "High priority on this page",
                value: leads.filter((lead) => lead.priority === "high").length,
              },
            ].map((metric) => (
              <article
                key={metric.label}
                className="rounded-xl border border-slate-200 bg-white p-5"
              >
                <p className="text-sm text-slate-500">{metric.label}</p>
                <p className="mt-3 text-2xl font-bold text-slate-900">
                  {loading ? "--" : metric.value}
                </p>
              </article>
            ))}
          </section>

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
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
                aria-label="Filter by assigned user ID"
                type="text"
                placeholder="Assigned user ID"
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
                      <tr key={lead.id} className="hover:bg-slate-50">
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
                        <td className="px-5 py-4 text-slate-600">
                          {lead.assigned_user_id ? "Assigned" : "Unassigned"}
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
    </div>
  );
}
