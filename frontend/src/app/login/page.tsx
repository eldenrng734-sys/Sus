"use client";

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  LoaderCircle,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from "lucide-react";

import { login, verifyMfa } from "@/lib/api/auth";
import { ApiRequestError } from "@/types/api";

export default function LoginPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [challengeToken, setChallengeToken] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [setupRequired, setSetupRequired] = useState(false);

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: (result) => {
      if ("access_token" in result) {
        router.push("/");
        return;
      }

      if ("mfa_required" in result) {
        setChallengeToken(result.challenge_token);
        return;
      }

      if ("mfa_setup_required" in result) {
        setSetupRequired(true);
      }
    },
  });

  const mfaMutation = useMutation({
    mutationFn: verifyMfa,
    onSuccess: () => {
      router.push("/");
    },
  });

  function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    loginMutation.mutate({ email, password });
  }

  function handleMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!challengeToken) return;

    mfaMutation.mutate({
      challenge_token: challengeToken,
      code: mfaCode,
    });
  }

  const error = loginMutation.error ?? mfaMutation.error;
  const errorMessage =
    error instanceof ApiRequestError || error instanceof Error
      ? error.message
      : null;

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl md:grid-cols-2">
        <section className="hidden flex-col justify-between bg-slate-950 p-10 text-white md:flex">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 font-bold">
                S
              </div>
              <span className="text-xl font-semibold tracking-wide">
                SYNTRIX
              </span>
            </div>

            <div className="mt-24">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-400">
                AI Sales Assistant
              </p>
              <h1 className="mt-4 text-4xl font-bold leading-tight">
                Turn every lead into an opportunity.
              </h1>
              <p className="mt-5 max-w-sm leading-7 text-slate-300">
                Organize your leads, understand customer intent, and keep
                every follow-up on track.
              </p>
            </div>
          </div>

          <p className="text-sm text-slate-400">
            Intelligent sales workflow management.
          </p>
        </section>

        <section className="flex items-center justify-center px-6 py-12 sm:px-10">
          <div className="w-full max-w-md">
            <div className="mb-8 md:hidden">
              <p className="text-xl font-bold tracking-wide text-slate-900">
                SYNTRIX
              </p>
              <p className="mt-1 text-sm text-slate-500">
                AI Sales Assistant
              </p>
            </div>

            {challengeToken ? (
              <>
                <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
                  <ShieldCheck size={25} />
                </div>

                <h2 className="text-2xl font-bold text-slate-900">
                  Verify your identity
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  Enter the verification code from your authenticator app.
                </p>

                <form onSubmit={handleMfa} className="mt-8 space-y-5">
                  <div>
                    <label
                      htmlFor="mfa-code"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Verification code
                    </label>
                    <input
                      id="mfa-code"
                      value={mfaCode}
                      onChange={(event) => setMfaCode(event.target.value)}
                      required
                      autoComplete="one-time-code"
                      inputMode="numeric"
                      placeholder="Enter your code"
                      className="w-full rounded-lg border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={mfaMutation.isPending}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {mfaMutation.isPending ? (
                      <LoaderCircle className="animate-spin" size={19} />
                    ) : (
                      <>
                        Verify and continue
                        <ArrowRight size={18} />
                      </>
                    )}
                  </button>
                </form>
              </>
            ) : setupRequired ? (
              <>
                <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-amber-50 text-amber-700">
                  <ShieldCheck size={25} />
                </div>
                <h2 className="text-2xl font-bold text-slate-900">
                  MFA setup required
                </h2>
                <p className="mt-3 text-sm leading-6 text-slate-600">
                  Your account requires multi-factor authentication setup.
                  The setup screen will be available in the next authentication
                  step. Please contact your administrator if you need access
                  now.
                </p>
              </>
            ) : (
              <>
                <h2 className="text-2xl font-bold text-slate-900">
                  Welcome back
                </h2>
                <p className="mt-2 text-sm text-slate-500">
                  Sign in to continue to your workspace.
                </p>

                <form onSubmit={handleLogin} className="mt-8 space-y-5">
                  <div>
                    <label
                      htmlFor="email"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Email address
                    </label>
                    <div className="relative">
                      <Mail
                        size={18}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                      />
                      <input
                        id="email"
                        type="email"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        required
                        autoComplete="email"
                        placeholder="you@company.com"
                        className="w-full rounded-lg border border-slate-300 py-3 pl-10 pr-4 text-slate-900 outline-none transition focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                      />
                    </div>
                  </div>

                  <div>
                    <label
                      htmlFor="password"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Password
                    </label>
                    <div className="relative">
                      <LockKeyhole
                        size={18}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                      />
                      <input
                        id="password"
                        type="password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        required
                        autoComplete="current-password"
                        placeholder="Enter your password"
                        className="w-full rounded-lg border border-slate-300 py-3 pl-10 pr-4 text-slate-900 outline-none transition focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                      />
                    </div>
                  </div>

                  {errorMessage && (
                    <p
                      role="alert"
                      className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
                    >
                      {errorMessage}
                    </p>
                  )}

                  <button
                    type="submit"
                    disabled={loginMutation.isPending}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {loginMutation.isPending ? (
                      <LoaderCircle className="animate-spin" size={19} />
                    ) : (
                      <>
                        Sign in
                        <ArrowRight size={18} />
                      </>
                    )}
                  </button>
                </form>
              </>
            )}

            {(challengeToken || setupRequired) && errorMessage && (
              <p
                role="alert"
                className="mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
              >
                {errorMessage}
              </p>
            )}

            <p className="mt-8 text-center text-xs text-slate-400">
              © 2026 SYNTRIX. All rights reserved.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
