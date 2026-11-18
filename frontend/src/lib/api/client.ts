import { env } from "@/lib/env";
import { tokenStore } from "@/lib/auth/token-store";
import { csrfStore } from "@/lib/auth/csrf";
import { tenantStore } from "@/lib/auth/tenant";
import { ApiRequestError } from "@/types/api";

export type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  headers?: HeadersInit;
  auth?: boolean;
  tenantScoped?: boolean;
  csrf?: boolean;
  idempotencyKey?: string;
  retryOnUnauthorized?: boolean;
};

type RefreshResponse = {
  data?: {
    access_token?: string;
    csrf_token?: string;
  };
};

let refreshPromise: Promise<boolean> | null = null;

function createIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function parseError(status: number, payload: unknown): ApiRequestError {
  let fallbackMessage = "The request could not be completed.";
  if (status === 502 || status === 503 || status === 504) {
    fallbackMessage = "Backend server is unavailable. Please check that the backend is running.";
  } else if (status === 500 && payload === null) {
    fallbackMessage = "Unable to connect to the backend server. Please verify the backend is running on port 8000.";
  }

  const fallback = {
    code: "request_failed",
    message: fallbackMessage,
    details: null,
    request_id: null,
  };

  if (
    typeof payload === "object" &&
    payload !== null &&
    "error" in payload &&
    typeof payload.error === "object" &&
    payload.error !== null
  ) {
    return new ApiRequestError(
      status,
      { ...fallback, ...payload.error } as typeof fallback,
    );
  }

  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload
  ) {
    let msg = fallback.message;
    if (typeof (payload as { detail: unknown }).detail === "string") {
      msg = (payload as { detail: string }).detail;
    } else if (Array.isArray((payload as { detail: unknown }).detail)) {
      msg = (payload as { detail: Array<{ msg?: string }> }).detail
        .map((d) => d.msg || "")
        .filter(Boolean)
        .join(", ");
    }
    return new ApiRequestError(status, { ...fallback, message: msg });
  }

  if (
    typeof payload === "object" &&
    payload !== null &&
    "message" in payload &&
    typeof (payload as { message: unknown }).message === "string"
  ) {
    return new ApiRequestError(status, {
      ...fallback,
      message: (payload as { message: string }).message,
    });
  }

  return new ApiRequestError(status, fallback);
}

export async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const csrfToken = csrfStore.get();

    if (!csrfToken) {
      tokenStore.clear();
      return false;
    }

    try {
      const response = await fetch(`${env.apiBaseUrl}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: {
          "X-CSRF-Token": csrfToken,
        },
      });

      if (!response.ok) {
        tokenStore.clear();
        csrfStore.clear();
        tenantStore.clear();
        return false;
      }

      const payload = (await response.json()) as RefreshResponse;
      const accessToken = payload.data?.access_token;
      const newCsrfToken = payload.data?.csrf_token;

      if (!accessToken || !newCsrfToken) {
        tokenStore.clear();
        csrfStore.clear();
        tenantStore.clear();
        return false;
      }

      tokenStore.set(accessToken);
      csrfStore.set(newCsrfToken);
      return true;
    } catch {
      tokenStore.clear();
      csrfStore.clear();
      tenantStore.clear();
      return false;
    }
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    body,
    headers: customHeaders,
    auth = true,
    tenantScoped = true,
    csrf = false,
    idempotencyKey,
    retryOnUnauthorized = true,
  } = options;

  if (auth && !tokenStore.get()) {
    const refreshed = await refreshAccessToken();

    if (!refreshed) {
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
      throw new ApiRequestError(401, {
        code: "unauthorized",
        message: "Your session has expired. Please log in again.",
      });
    }
  }

  const headers = new Headers(customHeaders);

  if (body !== undefined && !(body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  headers.set("Accept", "application/json");

  if (auth) {
    const accessToken = tokenStore.get();

    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }
  }

  if (tenantScoped) {
    const tenantId = tenantStore.get();

    if (!tenantId) {
      throw new Error("Select a tenant before making this request.");
    }

    headers.set("X-Tenant-ID", tenantId);
  }

  if (csrf) {
    const csrfToken = csrfStore.get();

    if (!csrfToken) {
      throw new Error("CSRF token is missing.");
    }

    headers.set("X-CSRF-Token", csrfToken);
  }

  if (idempotencyKey) {
    headers.set("Idempotency-Key", idempotencyKey);
  }

  const normalizedPath = path.startsWith("/api/v1")
    ? path
    : `${env.apiBaseUrl}${path.startsWith("/") ? "" : "/"}${path}`;

  const response = await fetch(normalizedPath, {
    method,
    headers,
    credentials: "include",
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : typeof body === "string"
            ? body
            : JSON.stringify(body),
  });

  if (
    response.status === 401 &&
    auth &&
    retryOnUnauthorized &&
    path !== "/auth/refresh"
  ) {
    const refreshed = await refreshAccessToken();

    if (refreshed) {
      return apiRequest<T>(path, {
        ...options,
        retryOnUnauthorized: false,
      });
    }

    tokenStore.clear();
    csrfStore.clear();
    tenantStore.clear();

    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }

    throw new ApiRequestError(401, {
      code: "unauthorized",
      message: "Your session has expired. Please log in again.",
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw parseError(response.status, payload);
  }

  return payload as T;
}

export function createIdempotencyKeyForAction(): string {
  return createIdempotencyKey();
}
