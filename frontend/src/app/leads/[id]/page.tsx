"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

type Assessment = {
  intent?: string | null;
  priority?: string | null;
  lead_score?: number | null;
  confidence?: number | null;
  summary?: string | null;
  needs_human_review?: boolean;
  review_status?: string;
  created_at?: string;
};

type Lead = {
  id: string;
  name?: string;
  email?: string | null;
  phone?: string | null;
  company_name?: string | null;
  source?: string | null;
  status: string;
  priority?: string;
  intent?: string | null;
  lead_score?: number | null;
  version: number;
  created_at?: string;
  updated_at?: string;
  owner?: { id: string; email: string; full_name?: string } | null;
  team?: { id: string; name: string } | null;
  latest_assessment?: Assessment | null;
  next_task?: {
    id: string;
    title: string;
    type: string;
    due_at: string;
    status: string;
  } | null;
};

type Note = {
  id: string;
  text: string;
  created_at: string;
};

const statuses = ["new", "contacted", "qualified", "proposal", "won"];

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function LeadDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [lead, setLead] = useState<Lead | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [noteText, setNoteText] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingNote, setSavingNote] = useState(false);
  const [savingStatus, setSavingStatus] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function loadLead() {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<Lead>(
        `/leads/${id}?include=owner,team,latest_assessment,next_task`
      );
      setLead(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load lead");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (id) loadLead();
  }, [id]);

  async function updateStatus(status: string) {
    if (!lead || status === lead.status) return;

    setSavingStatus(true);
    setError("");
    setSuccess("");

    try {
      const updated = await apiFetch<Lead>(`/leads/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ version: lead.version, status }),
      });
      setLead((current) =>
        current ? { ...current, ...updated } : updated
      );
      setSuccess("Lead status updated successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Status update failed");
    } finally {
      setSavingStatus(false);
    }
  }

  async function addNote(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = noteText.trim();
    if (!text) return;

    setSavingNote(true);
    setError("");
    setSuccess("");

    try {
      const note = await apiFetch<Note>(`/leads/${id}/notes`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      setNotes((current) => [note, ...current]);
      setNoteText("");
      setSuccess("Note saved successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save note");
    } finally {
      setSavingNote(false);
    }
  }

  if (loading) {
    return <div className="p-8 text-sm text-gray-500">Loading lead details...</div>;
  }

  if (error && !lead) {
    return (
      <div className="p-8">
        <p className="text-red-600">{error}</p>
        <button onClick={loadLead} className="mt-4 rounded-lg bg-gray-900 px-4 py-2 text-white">
          Try again
        </button>
        <Link href="/leads" className="ml-4 text-sm underline">Back to leads</Link>
      </div>
    );
  }

  if (!lead) return null;

  const assessment = lead.latest_assessment;

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link href="/leads" className="text-sm text-gray-500 hover:text-gray-900">
            ← Back to leads
          </Link>
          <h1 className="mt-3 text-2xl font-bold text-gray-900">
            {lead.name || "Unnamed lead"}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Lead ID: {lead.id}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label htmlFor="lead-status" className="text-sm font-medium text-gray-600">
            Status
          </label>
          <select
            id="lead-status"
            value={lead.status}
            disabled={savingStatus}
            onChange={(e) => updateStatus(e.target.value)}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm capitalize disabled:opacity-50"
          >
            {!statuses.includes(lead.status) && (
              <option value={lead.status}>{lead.status}</option>
            )}
            {statuses.map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
        </div>
      </div>

      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {success && <p role="status" className="rounded-lg bg-green-50 p-3 text-sm text-green-700">{success}</p>}

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="rounded-xl border border-gray-200 bg-white p-5 lg:col-span-2">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Lead information</h2>
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <p className="text-xs text-gray-500">Email</p>
              <p className="mt-1 break-all text-sm font-medium">{lead.email || "Not provided"}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Phone</p>
              <p className="mt-1 text-sm font-medium">{lead.phone || "Not provided"}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Company</p>
              <p className="mt-1 text-sm font-medium">{lead.company_name || "Not provided"}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Lead source</p>
              <p className="mt-1 text-sm font-medium">{lead.source || "Unknown"}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Assigned owner</p>
              <p className="mt-1 text-sm font-medium">
                {lead.owner?.full_name || lead.owner?.email || "Unassigned"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Team</p>
              <p className="mt-1 text-sm font-medium">{lead.team?.name || "No team assigned"}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Created</p>
              <p className="mt-1 text-sm font-medium">{formatDate(lead.created_at)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Last updated</p>
              <p className="mt-1 text-sm font-medium">{formatDate(lead.updated_at)}</p>
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Lead intelligence</h2>
          <div className="space-y-4">
            <div>
              <p className="text-xs text-gray-500">Lead score</p>
              <p className="mt-1 text-3xl font-bold text-gray-900">
                {assessment?.lead_score ?? lead.lead_score ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Intent</p>
              <p className="mt-1 text-sm font-medium capitalize">
                {assessment?.intent || lead.intent || "Not assessed"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Priority</p>
              <p className="mt-1 text-sm font-medium capitalize">
                {assessment?.priority || lead.priority || "—"}
              </p>
            </div>
            {assessment && (
              <>
                <div>
                  <p className="text-xs text-gray-500">Assessment confidence</p>
                  <p className="mt-1 text-sm font-medium">
                    {assessment.confidence != null
                      ? `${Math.round(assessment.confidence * 100)}%`
                      : "—"}
                  </p>
                </div>
                {assessment.summary && (
                  <div>
                    <p className="text-xs text-gray-500">AI summary</p>
                    <p className="mt-1 text-sm leading-6 text-gray-700">{assessment.summary}</p>
                  </div>
                )}
                {assessment.needs_human_review && (
                  <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                    Human review required
                  </p>
                )}
              </>
            )}
            {!assessment && (
              <p className="text-sm text-gray-500">No AI assessment available yet.</p>
            )}
          </div>
        </section>
      </div>

      <section className="rounded-xl border border-gray-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-gray-900">Next task</h2>
        {lead.next_task ? (
          <div className="mt-3 rounded-lg bg-gray-50 p-4">
            <p className="font-medium text-gray-900">{lead.next_task.title}</p>
            <p className="mt-1 text-sm text-gray-500">
              {lead.next_task.type} · Due: {formatDate(lead.next_task.due_at)}
            </p>
          </div>
        ) : (
          <p className="mt-2 text-sm text-gray-500">No open task for this lead.</p>
        )}
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-gray-900">Notes & activity</h2>
        <form onSubmit={addNote} className="mt-4 space-y-3">
          <textarea
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="Write a note about this lead..."
            className="w-full rounded-lg border border-gray-300 p-3 text-sm outline-none focus:border-gray-500"
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={savingNote || !noteText.trim()}
              className="rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {savingNote ? "Saving..." : "Add note"}
            </button>
          </div>
        </form>

        <div className="mt-5 space-y-3">
          {notes.map((note) => (
            <article key={note.id} className="border-l-2 border-gray-300 py-1 pl-4">
              <p className="whitespace-pre-wrap text-sm text-gray-800">{note.text}</p>
              <p className="mt-1 text-xs text-gray-400">{formatDate(note.created_at)}</p>
            </article>
          ))}
          {notes.length === 0 && (
            <p className="text-sm text-gray-500">
              Newly added notes will appear here. Existing activity timeline is not exposed by the current lead detail API.
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
