"use client";

import { useEffect, useState } from "react";
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
  created_at: string;
};

const statuses = [
  "new",
  "contacted",
  "qualified",
  "proposal",
  "won",
  "lost",
];

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

    const timer = setTimeout(async () => {
      setLoading(true);
      setError("");

      try {
        const params = new URLSearchParams();
        params.set("limit", "25");

        if (search.trim()) params.set("q", search.trim());
        if (status) params.set("status", status);
        if (priority) params.set("priority", priority);
        if (source) params.set("source", source);
        if (owner) params.set("assigned_user_id", owner);
        if (cursor) params.set("cursor", cursor);

        const result = await fetchLeads<Lead>(params);

        if (!cancelled) {
          setLeads(result.data);
          setNextCursor(result.meta.next_cursor);
          setHasMore(result.meta.has_more);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Something went wrong"
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
      clearTimeout(timer);
    };
  }, [search, status, priority, source, owner, cursor]);

  function resetPagination() {
    setCursor(null);
    setCursorStack([]);
  }

  function changeStatus(value: string) {
    setStatus(value);
    resetPagination();
  }

  function changePriority(value: string) {
    setPriority(value);
    resetPagination();
  }

  function changeSource(value: string) {
    setSource(value);
    resetPagination();
  }

  function changeOwner(value: string) {
    setOwner(value);
    resetPagination();
  }

  function changeSearch(value: string) {
    setSearch(value);
    resetPagination();
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
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              Leads
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              Manage and track your leads
            </p>
          </div>
        </div>

        <div className="mb-6 grid gap-3 rounded-lg border bg-white p-4 md:grid-cols-2 lg:grid-cols-4">
          <input
            type="search"
            placeholder="Search name, email, phone or company..."
            value={search}
            onChange={(e) => changeSearch(e.target.value)}
            maxLength={100}
            className="rounded-md border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
          />

          <select
            value={status}
            onChange={(e) => changeStatus(e.target.value)}
            className="rounded-md border px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            {statuses.map((item) => (
              <option key={item} value={item}>
                {formatOption(item)}
              </option>
            ))}
          </select>

          <select
            value={priority}
            onChange={(e) => changePriority(e.target.value)}
            className="rounded-md border px-3 py-2 text-sm"
          >
            <option value="">All priorities</option>
            {priorities.map((item) => (
              <option key={item} value={item}>
                {formatOption(item)}
              </option>
            ))}
          </select>

          <select
            value={source}
            onChange={(e) => changeSource(e.target.value)}
            className="rounded-md border px-3 py-2 text-sm"
          >
            <option value="">All sources</option>
            {sources.map((item) => (
              <option key={item} value={item}>
                {formatOption(item)}
              </option>
            ))}
          </select>

          <input
            type="text"
            placeholder="Owner user ID (UUID)..."
            value={owner}
            onChange={(e) => changeOwner(e.target.value)}
            maxLength={100}
            className="rounded-md border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {loading && (
          <p className="rounded-lg bg-white p-6 text-center text-gray-500">
            Loading leads...
          </p>
        )}

        {!loading && error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
            {error}
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="overflow-x-auto rounded-lg border bg-white">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-100 text-gray-600">
                  <tr>
                    <th className="p-4">Name</th>
                    <th className="p-4">Company</th>
                    <th className="p-4">Email</th>
                    <th className="p-4">Phone</th>
                    <th className="p-4">Source</th>
                    <th className="p-4">Status</th>
                    <th className="p-4">Priority</th>
                  </tr>
                </thead>

                <tbody className="divide-y">
                  {leads.map((lead) => (
                    <tr key={lead.id} className="hover:bg-gray-50">
                      <td className="p-4 font-medium text-gray-900">
                        {lead.name}
                      </td>
                      <td className="p-4">
                        {lead.company_name || "-"}
                      </td>
                      <td className="p-4">
                        {lead.email || "-"}
                      </td>
                      <td className="p-4">
                        {lead.phone || "-"}
                      </td>
                      <td className="p-4">
                        {formatOption(lead.source)}
                      </td>
                      <td className="p-4">
                        <span className="rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-700">
                          {lead.status}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-700">
                          {lead.priority}
                        </span>
                      </td>
                    </tr>
                  ))}

                  {leads.length === 0 && (
                    <tr>
                      <td
                        colSpan={7}
                        className="p-8 text-center text-gray-500"
                      >
                        No leads found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <p className="text-sm text-gray-500">
                Showing {leads.length} leads
              </p>

              <div className="flex gap-2">
                <button
                  disabled={cursorStack.length === 0}
                  onClick={goToPreviousPage}
                  className="rounded-md bg-gray-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-300"
                >
                  Previous Page
                </button>
                <button
                  disabled={!hasMore || !nextCursor}
                  onClick={goToNextPage}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-300"
                >
                  Next Page
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
