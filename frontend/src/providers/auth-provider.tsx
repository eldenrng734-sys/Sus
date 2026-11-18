"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { usePathname, useRouter } from "next/navigation";
import { refreshAccessToken } from "@/lib/api/client";
import { tokenStore } from "@/lib/auth/token-store";
import { tenantStore } from "@/lib/auth/tenant";
import { getCurrentUser, logout as apiLogout, type CurrentUser } from "@/lib/api/auth";

export type AuthContextValue = {
  isLoading: boolean;
  isAuthenticated: boolean;
  user: CurrentUser | null;
  role: "rep" | "manager" | "admin" | null;
  timezone: string;
  refresh: () => Promise<boolean>;
  logout: () => Promise<void>;
  selectTenant: (tenantId: string) => void;
};

const AuthContext = createContext<AuthContextValue>({
  isLoading: true,
  isAuthenticated: false,
  user: null,
  role: null,
  timezone: "Asia/Dhaka",
  refresh: async () => false,
  logout: async () => {},
  selectTenant: () => {},
});

const PUBLIC_PATHS = [
  "/login",
  "/signup",
  "/accept-invite",
  "/reset-password",
  "/403",
];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isPublicPath = PUBLIC_PATHS.some((path) => pathname?.startsWith(path));

  const [isLoading, setIsLoading] = useState(!isPublicPath);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);

  const fetchProfile = useCallback(async (): Promise<boolean> => {
    try {
      if (tenantStore.get()) {
        const profile = await getCurrentUser();
        setUser(profile);
        setIsAuthenticated(true);
        return true;
      }
      setIsAuthenticated(true);
      return true;
    } catch {
      setUser(null);
      setIsAuthenticated(false);
      return false;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
      setIsAuthenticated(false);
      router.push("/login");
    }
  }, [router]);

  const selectTenant = useCallback(
    (tenantId: string) => {
      tenantStore.set(tenantId);
      void fetchProfile();
    },
    [fetchProfile]
  );

  useEffect(() => {
    let isMounted = true;

    async function initSession() {
      if (isPublicPath) {
        setIsLoading(false);
        return;
      }

      // If we don't have an in-memory access token yet, refresh via HttpOnly cookie + CSRF token
      if (!tokenStore.get()) {
        const refreshed = await refreshAccessToken();
        if (!refreshed) {
          if (isMounted) {
            setIsAuthenticated(false);
            setIsLoading(false);
            router.push("/login");
          }
          return;
        }
      }

      // Access token available; fetch user profile if tenant is available
      try {
        if (tenantStore.get()) {
          const profile = await getCurrentUser();
          if (isMounted) {
            setUser(profile);
            setIsAuthenticated(true);
          }
        } else {
          if (isMounted) {
            setIsAuthenticated(true);
          }
        }
      } catch {
        // If profile fetch fails with 401, redirect to login
        if (isMounted) {
          setIsAuthenticated(false);
          router.push("/login");
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void initSession();

    return () => {
      isMounted = false;
    };
  }, [pathname, isPublicPath, router]);

  const contextValue: AuthContextValue = {
    isLoading,
    isAuthenticated,
    user,
    role: user?.role ?? null,
    timezone: user?.tenant_timezone ?? "Asia/Dhaka",
    refresh: refreshAccessToken,
    logout,
    selectTenant,
  };

  if (isLoading && !isPublicPath) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
          <p className="text-sm font-medium text-slate-500">Loading session...</p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
