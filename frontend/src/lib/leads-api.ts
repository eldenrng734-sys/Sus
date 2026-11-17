import { apiRequest } from "@/lib/api/client";

export type LeadListResponse<T> = {
  data: T[];
  meta: {
    next_cursor: string | null;
    has_more: boolean;
  };
};

export async function fetchLeads<T>(
  params: URLSearchParams
): Promise<LeadListResponse<T>> {
  const query = params.toString();
  const path = `/leads${query ? `?${query}` : ""}`;
  return apiRequest<LeadListResponse<T>>(path);
}
