import { apiFetch } from "@/lib/api";

export type LeadListResponse<T> = {
  data: T[];
  meta: {
    next_cursor: string | null;
    has_more: boolean;
  };
};

const LIMIT = 25;

/**
 * Encode a cursor matching the backend's _encode_cursor format:
 * base64url(JSON.stringify({sort, descending, value, id})) with padding stripped.
 * The backend sorts by -created_at (descending).
 */
function encodeCursor(createdAt: string, id: string): string {
  const payload = {
    descending: true,
    id,
    sort: "created_at",
    value: createdAt,
  };
  // Match Python's json.dumps(sort_keys=True, separators=(",", ":"))
  const typed = payload as Record<string, unknown>;
  const sortedObj: Record<string, unknown> = {};
  for (const key of Object.keys(typed).sort()) {
    sortedObj[key] = typed[key];
  }
  const raw = JSON.stringify(sortedObj);
  const b64 = btoa(raw);
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function fetchLeads<T>(
  params: URLSearchParams
): Promise<LeadListResponse<T>> {
  // apiFetch returns json.data ?? json. The backend wraps results as
  // {data, meta}, so apiFetch unwraps to just the data array. We therefore
  // reconstruct next_cursor client-side from the last lead's created_at/id
  // using the same encoding the backend uses for cursors.
  const data = await apiFetch<T[]>(`/api/v1/leads?${params.toString()}`);

  const hasMore = data.length === LIMIT;
  const last = data[data.length - 1] as
    | { id: string; created_at: string }
    | undefined;
  const nextCursor =
    last?.created_at && last?.id
      ? encodeCursor(last.created_at, last.id)
      : null;

  return {
    data: data as T[],
    meta: {
      next_cursor: nextCursor,
      has_more: hasMore,
    },
  };
}
