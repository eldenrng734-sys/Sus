"use client";

import { useQuery } from "@tanstack/react-query";
import { getCurrentUser, type CurrentUser } from "@/lib/api/auth";
import { tokenStore } from "@/lib/auth/token-store";
import { tenantStore } from "@/lib/auth/tenant";

export const CURRENT_USER_QUERY_KEY = ["currentUser"] as const;

export function useCurrentUser() {
  const hasToken = Boolean(tokenStore.get());
  const hasTenant = Boolean(tenantStore.get());

  return useQuery<CurrentUser, Error>({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: getCurrentUser,
    enabled: hasToken && hasTenant,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 1,
  });
}
