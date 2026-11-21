"use client";

import React from "react";

/**
 * Root Template for Next.js App Router Page Transitions.
 *
 * In Next.js App Router, `template.tsx` mounts a fresh instance on every route
 * navigation (unlike `layout.tsx` which persists). Wrapping page children in
 * `.page-transition` enables smooth enter transitions between routes without
 * disrupting persistent shell components or causing layout thrashing.
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="page-transition min-h-screen w-full">{children}</div>;
}
