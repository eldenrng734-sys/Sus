"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

type AcceptResponse = {
  user_id: string;
  tenant_id: string;
  role: string;
};

export default function AcceptInvitePage() {
  const router = useRouter();
  const [token] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }

    return new URLSearchParams(window.location.search).get("token") || "";
  });
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleAccept(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!token) {
      setError("Invitation token is missing. Please open the invitation link again.");
      return;
    }

    setLoading(true);

    try {
      const result = await apiFetch<AcceptResponse>("/invitations/accept", {
        method: "POST",
        body: JSON.stringify({
          token,
          full_name: fullName || null,
          password: password || null,
        }),
      });

      localStorage.setItem("tenant_id", result.tenant_id);
      setSuccess(`Invitation accepted. Your role is ${result.role}. Redirecting to login...`);
      setTimeout(() => router.push("/login"), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not accept invitation.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md rounded-xl bg-white p-8 shadow">
        <h1 className="mb-2 text-2xl font-bold">Accept invitation</h1>
        <p className="mb-6 text-sm text-gray-600">
          Complete the form to join your company. If you already have an account,
          leave the name and password fields blank.
        </p>

        <form onSubmit={handleAccept} className="space-y-4">
          <label className="block text-sm font-medium">
            Full name (for a new account)
            <input
              type="text"
              maxLength={200}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <label className="block text-sm font-medium">
            Password (for a new account, minimum 8 characters)
            <input
              type="password"
              minLength={8}
              maxLength={128}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          {!token && (
            <p className="rounded bg-red-50 p-3 text-sm text-red-700">
              Invitation token is missing from the link.
            </p>
          )}

          {error && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          {success && <p role="status" className="rounded bg-green-50 p-3 text-sm text-green-700">{success}</p>}

          <button
            type="submit"
            disabled={loading || !token}
            className="w-full rounded-lg bg-blue-600 px-4 py-3 font-semibold text-white disabled:opacity-50"
          >
            {loading ? "Accepting..." : "Accept invitation"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm">
          <a href="/login" className="text-blue-600 hover:underline">Back to login</a>
        </p>
      </div>
    </main>
  );
}
