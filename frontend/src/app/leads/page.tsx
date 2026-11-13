
"use client";

import { useEffect, useState } from "react";

type Lead = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  company_name: string | null;
  status: string;
  priority: string;
  created_at: string;
};

type LeadsResponse = {
  data: Lead[];
  meta: {
    next_cursor: string | null;
    has_more: boolean;
  };
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

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
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
        if (cursor) params.set("cursor", cursor);

        const token = localStorage.getItem("access_token");
        const tenantId = localStorage.getItem("tenant_id");

        const response = await fetch(
          `/api/v1/leads?${params.toString()}`,
          {
            headers: {
              "Content-Type": "application/json",
              ...(token
                ? { Authorization: `Bearer ${token}` }
                : {}),
              ...(tenantId
                ? { "X-Tenant-ID": tenantId }
                : {}),
            },
          }
        );

        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(
            body?.detail?.[0]?.msg ||
              body?.detail ||
              body?.error?.message ||
              `Request failed (${response.status})`
          );
        }

        const result: LeadsResponse = await response.json();

        if (!cancelled) {
          setLeads(result.data ?? []);
          setNextCursor(result.meta?.next_cursor ?? null);
          setHasMore(result.meta?.has_more ?? false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Something went wrong"
          );
          setLeads([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [search, status, priority, cursor]);

  function changeStatus(value: string) {
    setStatus(value);
    setCursor(null);
  }

  function changePriority(value: string) {
    setPriority(value);
    setCursor(null);
  }

  function changeSearch(value: string) {
    setSearch(value);
    setCursor(null);
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

        <div className="mb-6 grid gap-3 rounded-lg border bg-white p-4 md:grid-cols-3">
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
                {item.charAt(0).toUpperCase() + item.slice(1)}
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
                {item.charAt(0).toUpperCase() + item.slice(1)}
              </option>
            ))}
          </select>
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
                        colSpan={6}
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

              <button
                disabled={!hasMore || !nextCursor}
                onClick={() => setCursor(nextCursor)}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-300"
              >
                Next Page
              </button>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
