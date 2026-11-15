"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

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
    setForm({ ...form, [key]: value });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!form.name.trim()) {
      setError("Name is required");
      return;
    }
    if (!form.email.trim() && !form.phone.trim()) {
      setError("Provide an email or a phone number");
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
      const lead = await apiFetch<{ id: string }>("/leads", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      router.push(`/leads/${lead.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create lead");
    } finally {
      setLoading(false);
    }
  }

  const inputClass = "w-full border p-2 rounded";

  return (
    <div className="max-w-lg mx-auto p-6">
      <h1 className="text-2xl font-bold mb-4">Create Lead</h1>
      <form onSubmit={handleSubmit} className="space-y-3">
        <input
          placeholder="Name *"
          value={form.name}
          onChange={(e) => setField("name", e.target.value)}
          className={inputClass}
        />
        <input
          type="email"
          placeholder="Email"
          value={form.email}
          onChange={(e) => setField("email", e.target.value)}
          className={inputClass}
        />
        <input
          placeholder="Phone (e.g. +8801712345678)"
          value={form.phone}
          onChange={(e) => setField("phone", e.target.value)}
          className={inputClass}
        />
        <input
          placeholder="Company name"
          value={form.company_name}
          onChange={(e) => setField("company_name", e.target.value)}
          className={inputClass}
        />
        <textarea
          placeholder="Notes"
          rows={3}
          value={form.notes}
          onChange={(e) => setField("notes", e.target.value)}
          className={inputClass}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.consent}
            onChange={(e) => setField("consent", e.target.checked)}
          />
          Lead has given consent to be contacted
        </label>

        <p className="text-xs text-gray-500">* Email or phone is required.</p>

        {error && <p className="text-red-600 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="bg-black text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {loading ? "Creating..." : "Create Lead"}
        </button>
      </form>
    </div>
  );
}