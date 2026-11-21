"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

interface RefreshButtonProps {
  onRefresh: () => void | Promise<unknown>;
  /** Optional external loading flag (e.g. React Query's isFetching). */
  isRefreshing?: boolean;
  label?: string;
  iconSize?: number;
  disabled?: boolean;
  className?: string;
}

// Keep the icon spinning long enough to be noticeable even when the request
// finishes almost instantly.
const MIN_SPIN_MS = 450;

export function RefreshButton({
  onRefresh,
  isRefreshing = false,
  label = "Refresh",
  iconSize = 15,
  disabled = false,
  className,
}: RefreshButtonProps) {
  const [isPending, setIsPending] = useState(false);
  const spinning = isPending || isRefreshing;

  const handleClick = async () => {
    if (spinning || disabled) return;

    setIsPending(true);
    const startedAt = Date.now();

    try {
      await onRefresh();
    } finally {
      const elapsed = Date.now() - startedAt;
      if (elapsed < MIN_SPIN_MS) {
        await new Promise((resolve) => setTimeout(resolve, MIN_SPIN_MS - elapsed));
      }
      setIsPending(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={disabled || spinning}
      aria-busy={spinning}
      className={cn(
        "inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-xs transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40 disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
    >
      <RefreshCw
        size={iconSize}
        aria-hidden="true"
        className={cn(spinning && "animate-spin")}
      />
      {label}
    </button>
  );
}
