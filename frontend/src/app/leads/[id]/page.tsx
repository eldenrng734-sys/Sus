"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [lead, setLead] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<Record<string, unknown>>(`/leads/${id}`)
      .then(setLead)
      .catch((e) => setError(e instanceof Error ? e.message : "Lead not found"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="p-6">Loading...</p>;
  if (error) return <p className="p-6 text-red-600">{error}</p>;
  if (!lead) return null;

  return (
    <div className="max-w-lg mx-auto p-6">
      <Link href="/leads" className="text-sm underline">
        ← Back to leads
      </Link>
      <h1 className="text-2xl font-bold my-4">{String(lead.name ?? "Lead")}</h1>
      <dl className="space-y-2">
        {Object.entries(lead).map(([key, value]) => (
          <div key={key} className="flex gap-4">
            <dt className="w-40 font-medium">{key}</dt>
            <dd className="break-all">
              {value === null || value === undefined || value === ""
                ? "-"
                : typeof value === "object"
                  ? JSON.stringify(value)
                  : String(value)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}