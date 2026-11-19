"use client";

import React from "react";
import { AlertCircle, RefreshCw, X } from "lucide-react";
import { parseApiError } from "@/lib/api-error";
import { cn } from "@/lib/utils";

interface ErrorBannerProps {
  error?: unknown;
  title?: string;
  message?: string;
  onRetry?: () => void;
  onDismiss?: () => void;
  className?: string;
}

export function ErrorBanner({
  error,
  title,
  message,
  onRetry,
  onDismiss,
  className,
}: ErrorBannerProps) {
  const parsed = error ? parseApiError(error) : null;
  const displayTitle = title || parsed?.title || "Error Occurred";
  const displayMessage = message || parsed?.message || "An unexpected error occurred.";

  return (
    <div
      role="alert"
      className={cn(
        "relative flex flex-col gap-2 rounded-xl border border-red-200 bg-red-50/90 p-4 text-red-900 shadow-sm sm:flex-row sm:items-center sm:justify-between",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-red-900">{displayTitle}</p>
          <p className="mt-0.5 text-xs text-red-700">{displayMessage}</p>

          {parsed?.details && parsed.details.length > 0 && (
            <ul className="mt-2 list-disc pl-4 text-xs text-red-700">
              {parsed.details.map((detail, idx) => (
                <li key={idx}>
                  {detail.field ? <span className="font-semibold">{detail.field}: </span> : null}
                  {detail.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 self-end sm:self-auto">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-lg bg-red-100 px-2.5 py-1.5 text-xs font-semibold text-red-800 transition hover:bg-red-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        )}

        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss error"
            className="rounded-md p-1 text-red-600 transition hover:bg-red-200/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
