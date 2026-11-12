export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const tenantId =
    typeof window !== "undefined" ? localStorage.getItem("tenant_id") : null;

  const res = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(tenantId ? { "X-Tenant-ID": tenantId } : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    let detail = `Request failed (${res.status})`;
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body.detail)) {
      detail = body.detail.map((d: { msg?: string }) => d.msg).join(", ");
    } else if (body?.error?.message) {
      detail = body.error.message;
    }
    throw new Error(detail);
  }

  const json = await res.json();
  return (json.data ?? json) as T;
}