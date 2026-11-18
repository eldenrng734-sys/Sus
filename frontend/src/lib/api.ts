import {
  apiRequest,
  type RequestOptions,
  refreshAccessToken,
  createIdempotencyKeyForAction,
} from "@/lib/api/client";

export { apiRequest, refreshAccessToken, createIdempotencyKeyForAction };

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { tenantScoped?: boolean; auth?: boolean } = {},
): Promise<T> {
  const method = (options.method as RequestOptions["method"]) || "GET";
  let body: unknown = options.body;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch {
      // keep raw string if not JSON
    }
  }

  const res = await apiRequest<{ data?: T } | T>(path, {
    method,
    body,
    headers: options.headers,
    auth: options.auth ?? true,
    tenantScoped: options.tenantScoped ?? true,
  });

  if (res && typeof res === "object" && "data" in res) {
    return (res as { data: T }).data;
  }
  return res as T;
}
