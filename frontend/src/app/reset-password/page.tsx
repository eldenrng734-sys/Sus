
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") || "");
  }, []);

  async function requestReset(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const result = await apiFetch<{ message: string }>(
        "/auth/password-reset",
        {
          method: "POST",
          body: JSON.stringify({ email }),
        }
      );
      setMessage(result.message || "If the account exists, a reset email has been sent.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not request password reset.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmReset(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const response = await fetch("/api/v1/auth/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(
          body.detail?.message || body.detail || "Invalid or expired reset link."
        );
      }

      setMessage("Password changed successfully. Redirecting to login...");
      setTimeout(() => router.push("/login"), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password reset failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md rounded-xl bg-white p-8 shadow">
        <h1 className="mb-2 text-2xl font-bold">Reset password</h1>
        <p className="mb-6 text-sm text-gray-600">
          {token ? "Enter your new password." : "Enter your email to receive a reset link."}
        </p>

        {token ? (
          <form onSubmit={confirmReset} className="space-y-4">
            <label className="block text-sm font-medium">
              New password (minimum 12 characters)
              <input
                type="password"
                required
                minLength={12}
                maxLength={128}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
              />
            </label>
            <button disabled={loading} className="w-full rounded-lg bg-blue-600 px-4 py-3 font-semibold text-white disabled:opacity-50">
              {loading ? "Updating..." : "Update password"}
            </button>
          </form>
        ) : (
          <form onSubmit={requestReset} className="space-y-4">
            <label className="block text-sm font-medium">
              Email address
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
              />
            </label>
            <button disabled={loading} className="w-full rounded-lg bg-blue-600 px-4 py-3 font-semibold text-white disabled:opacity-50">
              {loading ? "Sending..." : "Send reset link"}
            </button>
          </form>
        )}

        {error && <p role="alert" className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        {message && <p role="status" className="mt-4 rounded bg-green-50 p-3 text-sm text-green-700">{message}</p>}

        <p className="mt-5 text-center text-sm">
          <a href="/login" className="text-blue-600 hover:underline">Back to login</a>
        </p>
      </div>
    </main>
  );
}
