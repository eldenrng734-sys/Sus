"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  message?: string;
  className?: string;
}

const sizeClasses = {
  sm: "h-4 w-4 border-2",
  md: "h-8 w-8 border-[3px]",
  lg: "h-12 w-12 border-4",
};

export function LoadingSpinner({
  size = "md",
  message,
  className,
}: LoadingSpinnerProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 p-4", className)}>
      <div
        className={cn(
          "animate-spin rounded-full border-solid border-blue-600 border-t-transparent",
          sizeClasses[size]
        )}
      />
      {message && (
        <p className="text-sm font-medium text-slate-500 animate-pulse">{message}</p>
      )}
    </div>
  );
}
