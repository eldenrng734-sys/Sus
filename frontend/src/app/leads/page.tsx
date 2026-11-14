"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  Search, Plus, Users, Download,
  X, UserPlus,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";

type Lead = {
  id: string;
  name: string;
  email: string;
  company: string;
  source: string;
  status: string;
  priority: string;
  assigned: string;
};

const initialLeads: Lead[] = [];

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

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>(initialLeads);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [priority, setPriority] = useState("all");
  const [showForm, setShowForm] = useState(false);

  const [form, setForm] = useState({
    name: "",
    email: "",
    company: "",
    source: "manual",
    priority: "medium",
  });

  const filteredLeads = useMemo(() => {
    return leads.filter((lead) => {
      const query = search.toLowerCase();

      const matchesSearch =
        lead.name.toLowerCase().includes(query) ||
        lead.email.toLowerCase().includes(query) ||
        lead.company.toLowerCase().includes(query);

      return (
        matchesSearch &&
        (status === "all" || lead.status === status) &&
        (priority === "all" || lead.priority === priority)
      );
    });
  }, [leads, search, status, priority]);

  function handleAddLead(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const newLead: Lead = {
      id: crypto.randomUUID(),
      name: form.name,
      email: form.email,
      company: form.company,
      source: form.source,
      status: "new",
      priority: form.priority,
      assigned: "Unassigned",
    };

    setLeads((current) => [newLead, ...current]);
    setForm({
      name: "",
      email: "",
      company: "",
      source: "manual",
      priority: "medium",
    });
    setShowForm(false);
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-6 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">
              <Link href="/" className="hover:text-blue-600">Workspace</Link>
              {" / Leads"}
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">
              Lead Management
            </h1>
          </div>

          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-200 text-sm font-semibold text-slate-700">
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

            <button
              onClick={() => setShowForm(true)}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700"
            >
              <Plus size={18} />
              Add New Lead
            </button>
          </section>

          <section className="grid gap-4 sm:grid-cols-3">
            <article className="rounded-xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-slate-500">Total Leads</p>
                <Users size={19} className="text-blue-600" />
              </div>
              <p className="mt-3 text-2xl font-bold text-slate-900">
                {leads.length}
              </p>
            </article>

            <article className="rounded-xl border border-slate-200 bg-white p-5">
              <p className="text-sm text-slate-500">New Leads</p>
              <p className="mt-3 text-2xl font-bold text-slate-900">
                {leads.filter((lead) => lead.status === "new").length}
              </p>
            </article>

            <article className="rounded-xl border border-slate-200 bg-white p-5">
              <p className="text-sm text-slate-500">High Priority</p>
              <p className="mt-3 text-2xl font-bold text-slate-900">
                {leads.filter((lead) => lead.priority === "high").length}
              </p>
            </article>
          </section>

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 p-5">
              <div>
                <h3 className="font-semibold text-slate-900">All Leads</h3>
                <p className="mt-1 text-xs text-slate-500">
                  {filteredLeads.length} records shown
                </p>
              </div>

              <button
                onClick={() => setShowForm(true)}
                className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
              >
                <Download size={16} />
                Export
              </button>
            </div>

            <div className="flex flex-col gap-3 border-b border-slate-100 p-5 lg:flex-row">
              <div className="relative flex-1">
                <Search
                  size={18}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by name, email or company..."
                  className="w-full rounded-lg border border-slate-200 py-2.5 pl-10 pr-4 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>

              <div className="flex flex-wrap gap-3">
                <select
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                  className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-600 outline-none focus:border-blue-500"
                >
                  <option value="all">All statuses</option>
                  <option value="new">New</option>
                  <option value="contacted">Contacted</option>
                  <option value="qualified">Qualified</option>
                  <option value="proposal">Proposal</option>
                  <option value="won">Won</option>
                  <option value="lost">Lost</option>
                </select>

                <select
                  value={priority}
                  onChange={(event) => setPriority(event.target.value)}
                  className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-600 outline-none focus:border-blue-500"
                >
                  <option value="all">All priorities</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
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

                <tbody>
                  {filteredLeads.map((lead) => (
                    <tr key={lead.id} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="px-5 py-4">
                        <p className="font-semibold text-slate-800">{lead.name}</p>
                        <p className="mt-1 text-xs text-slate-500">{lead.email}</p>
                      </td>
                      <td className="px-5 py-4 text-slate-600">{lead.company || "--"}</td>
                      <td className="px-5 py-4 capitalize text-slate-600">{lead.source.replaceAll("_", " ")}</td>
                      <td className="px-5 py-4">
                        <span className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize ${statusStyles[lead.status]}`}>
                          {lead.status}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <span className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize ${priorityStyles[lead.priority]}`}>
                          {lead.priority}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-slate-600">{lead.assigned}</td>
                    </tr>
                  ))}

                  {filteredLeads.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-5 py-16 text-center">
                        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
                          <UserPlus size={23} />
                        </div>
                        <p className="mt-3 font-medium text-slate-700">
                          {leads.length === 0 ? "No leads yet" : "No matching leads"}
                        </p>
                        <p className="mt-1 text-sm text-slate-400">
                          {leads.length === 0
                            ? "Add your first lead to get started."
                            : "Try changing your search or filters."}
                        </p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </main>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-slate-900">Add New Lead</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Enter the customer&apos;s basic information.
                </p>
              </div>
              <button
                onClick={() => setShowForm(false)}
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                aria-label="Close form"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleAddLead} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Full name *
                </label>
                <input
                  required
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  placeholder="Customer name"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Email address
                </label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(event) => setForm({ ...form, email: event.target.value })}
                  placeholder="customer@example.com"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Company
                </label>
                <input
                  value={form.company}
                  onChange={(event) => setForm({ ...form, company: event.target.value })}
                  placeholder="Company name"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    Source
                  </label>
                  <select
                    value={form.source}
                    onChange={(event) => setForm({ ...form, source: event.target.value })}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
                  >
                    <option value="manual">Manual</option>
                    <option value="website_form">Website form</option>
                    <option value="whatsapp">WhatsApp</option>
                    <option value="facebook_lead_ads">Facebook Lead Ads</option>
                    <option value="csv">CSV</option>
                  </select>
                </div>

                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    Priority
                  </label>
                  <select
                    value={form.priority}
                    onChange={(event) => setForm({ ...form, priority: event.target.value })}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
              </div>

              <p className="text-xs text-slate-400">
                This is a UI-only draft. It is not saved to the backend yet.
              </p>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
                >
                  Add Lead
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
