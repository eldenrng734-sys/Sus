
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

type SignupResponse = {
  tenant: { id: string; name: string; slug: string };
  user: { id: string; email: string; full_name: string };
  membership: { role: string; is_active: boolean };
};

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    company_name: "",
    company_slug: "",
    full_name: "",
    email: "",
    password: "",
    accept_terms: false,
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  function update(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSignup(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      const result = await apiFetch<SignupResponse>("/auth/signup", {
        method: "POST",
        body: JSON.stringify(form),
      });

      setSuccess(
        `Account created for ${result.user.email}. Please verify your email before logging in.`
      );
      setTimeout(() => router.push("/login"), 2500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-8">
      <div className="w-full max-w-lg rounded-xl bg-white p-8 shadow">
        <h1 className="mb-2 text-2xl font-bold">Create your account</h1>
        <p className="mb-6 text-sm text-gray-600">
          Register your company and create your admin account.
        </p>

        <form onSubmit={handleSignup} className="space-y-4">
          {[
            ["company_name", "Company name", "text"],
            ["company_slug", "Company URL slug", "text"],
            ["full_name", "Full name", "text"],
            ["email", "Email address", "email"],
            ["password", "Password (minimum 12 characters)", "password"],
          ].map(([field, label, type]) => (
            <div key={field}>
              <label htmlFor={field} className="mb-1 block text-sm font-medium">
                {label}
              </label>
              <input
                id={field}
                type={type}
                required
                minLength={field === "password" ? 12 : undefined}
                value={form[field as keyof typeof form] as string}
                onChange={(e) => update(field, e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-blue-600"
              />
            </div>
          ))}

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              required
              checked={form.accept_terms}
              onChange={(e) => update("accept_terms", e.target.checked)}
            />
            I accept the terms and conditions.
          </label>

          {error && (
            <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">
              {error}
            </p>
          )}

          {success && (
            <p role="status" className="rounded bg-green-50 p-3 text-sm text-green-700">
              {success}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-blue-600 px-4 py-3 font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-gray-600">
          Already have an account?{" "}
          <a href="/login" className="font-medium text-blue-600 hover:underline">
            Sign in
          </a>
        </p>
      </div>
    </main>
  );
}
