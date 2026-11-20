"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Building,
  Mail,
  Phone,
  Plus,
  ShieldCheck,
  User,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { apiRequest, createIdempotencyKeyForAction } from "@/lib/api";

export default function NewLeadPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    company_name: "",
    notes: "",
    consent: false,
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function setField(key: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!form.name.trim()) {
      setError("Lead name is required.");
      return;
    }
    if (!form.email.trim() && !form.phone.trim()) {
      setError("Please provide at least an email address or a phone number.");
      return;
    }

    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      consent: form.consent,
    };
    if (form.email.trim()) payload.email = form.email.trim();
    if (form.phone.trim()) payload.phone = form.phone.trim();
    if (form.company_name.trim()) payload.company_name = form.company_name.trim();
    if (form.notes.trim()) payload.notes = form.notes.trim();

    setLoading(true);
    try {
      const response = await apiRequest<{ data: { id: string } }>("/leads", {
        method: "POST",
        body: payload,
        idempotencyKey: createIdempotencyKeyForAction(),
      });
      router.push(`/leads/${response.data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create lead.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        {/* Header */}
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-6 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">
              <Link href="/leads" className="hover:text-blue-600">
                Leads
              </Link>
              {" / New"}
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">
              Create New Lead
            </h1>
          </div>
          <Link
            href="/leads"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 transition"
          >
            <ArrowLeft size={14} /> Back to Leads
          </Link>
        </header>

        <div className="mx-auto max-w-2xl p-6 sm:p-8">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
            <div className="border-b border-slate-100 pb-5">
              <h2 className="text-lg font-bold text-slate-900">
                Lead Information
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Enter contact and business details to start tracking this opportunity.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="mt-6 space-y-5">
              {error && (
                <div
                  role="alert"
                  className="rounded-xl border border-red-200 bg-red-50 p-3.5 text-xs font-medium text-red-700"
                >
                  {error}
                </div>
              )}

              {/* Name */}
              <div>
                <label className="mb-1.5 block text-xs font-semibold text-slate-700">
                  Full Name <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <User
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                  />
                  <input
                    required
                    placeholder="e.g. Sarah Jenkins"
                    value={form.name}
                    onChange={(e) => setField("name", e.target.value)}
                    className="w-full rounded-xl border border-slate-200 py-2.5 pl-9 pr-3 text-xs outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                  />
                </div>
              </div>

              {/* Email & Phone grid */}
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-slate-700">
                    Email Address
                  </label>
                  <div className="relative">
                    <Mail
                      size={16}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                    />
                    <input
                      type="email"
                      placeholder="sarah@example.com"
                      value={form.email}
                      onChange={(e) => setField("email", e.target.value)}
                      className="w-full rounded-xl border border-slate-200 py-2.5 pl-9 pr-3 text-xs outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-slate-700">
                    Phone Number
                  </label>
                  <div className="relative">
                    <Phone
                      size={16}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                    />
                    <input
                      placeholder="+1 (555) 012-3456"
                      value={form.phone}
                      onChange={(e) => setField("phone", e.target.value)}
                      className="w-full rounded-xl border border-slate-200 py-2.5 pl-9 pr-3 text-xs outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                    />
                  </div>
                </div>
              </div>

              <p className="text-[11px] text-slate-400">
                * At least one contact method (email or phone) is required to create a lead.
              </p>

              {/* Company */}
              <div>
                <label className="mb-1.5 block text-xs font-semibold text-slate-700">
                  Company Name
                </label>
                <div className="relative">
                  <Building
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                  />
                  <input
                    placeholder="Acme Corporation"
                    value={form.company_name}
                    onChange={(e) => setField("company_name", e.target.value)}
                    className="w-full rounded-xl border border-slate-200 py-2.5 pl-9 pr-3 text-xs outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                  />
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="mb-1.5 block text-xs font-semibold text-slate-700">
                  Initial Notes
                </label>
                <textarea
                  placeholder="Key background, requirements, or conversation context..."
                  rows={3}
                  value={form.notes}
                  onChange={(e) => setField("notes", e.target.value)}
                  className="w-full rounded-xl border border-slate-200 p-3 text-xs outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                />
              </div>

              {/* Consent checkbox */}
              <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3.5">
                <label className="flex items-start gap-2.5 text-xs text-slate-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.consent}
                    onChange={(e) => setField("consent", e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div>
                    <span className="font-semibold text-slate-900">
                      Marketing & Outreach Consent
                    </span>
                    <p className="text-slate-500 text-[11px] mt-0.5">
                      Lead has explicitly agreed to receive follow-up messages and calls.
                    </p>
                  </div>
                </label>
              </div>

              {/* Form buttons */}
              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
                <Link
                  href="/leads"
                  className="rounded-lg border border-slate-200 px-4 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
                >
                  Cancel
                </Link>
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-5 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-blue-700 disabled:opacity-50 transition"
                >
                  <Plus size={15} />
                  {loading ? "Creating Lead..." : "Create Lead"}
                </button>
              </div>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
