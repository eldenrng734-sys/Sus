import { apiRequest, createIdempotencyKeyForAction } from "@/lib/api/client";

export type LeadStatus =
  | "new"
  | "contacted"
  | "qualified"
  | "proposal"
  | "won"
  | "lost";

export type LeadPriority = "low" | "medium" | "high";

export type LostReason =
  | "price"
  | "timing"
  | "no_response"
  | "competitor"
  | "not_qualified"
  | "other";

export const LOST_REASONS: { value: LostReason; label: string }[] = [
  { value: "price", label: "Price / Budget" },
  { value: "timing", label: "Timing not right" },
  { value: "no_response", label: "No response / Ghosted" },
  { value: "competitor", label: "Chose competitor" },
  { value: "not_qualified", label: "Not qualified" },
  { value: "other", label: "Other" },
];

export interface LeadAssessment {
  id: string;
  intent?: string | null;
  sentiment?: "positive" | "neutral" | "negative" | null;
  priority?: string | null;
  lead_score?: number | null;
  recommended_action?: string | null;
  confidence?: number | null;
  needs_human_review?: boolean;
  review_status?: "not_required" | "pending" | "approved" | "rejected";
  status?: "ok" | "fallback" | "failed";
  summary?: string | null;
  model?: string;
  prompt_version?: string;
  created_at?: string;
}

export interface Lead {
  id: string;
  tenant_id?: string;
  name: string;
  email: string | null;
  phone: string | null;
  company_name: string | null;
  source: string;
  source_campaign?: string | null;
  external_id?: string | null;
  status: LeadStatus;
  lost_reason?: LostReason | null;
  assigned_user_id: string | null;
  team_id?: string | null;
  intent?: string | null;
  lead_score?: number | null;
  priority: LeadPriority;
  consent?: boolean;
  opted_out?: boolean;
  version: number;
  created_at?: string;
  updated_at?: string;
  owner?: { id: string; email: string; full_name?: string } | null;
  team?: { id: string; name: string } | null;
  latest_assessment?: LeadAssessment | null;
  next_task?: {
    id: string;
    title: string;
    type: string;
    due_at: string;
    status: string;
  } | null;
}

export interface TimelineEvent {
  kind: "interaction" | "message";
  type: string;
  at: string;
  summary: string | null;
  details: Record<string, unknown>;
}

export interface CsvImportError {
  row: number;
  code: string;
  message: string;
}

export interface CsvImportResult {
  status: string;
  dry_run: boolean;
  total_rows: number;
  created_count: number;
  duplicate_count: number;
  error_count: number;
  errors: CsvImportError[];
}

export interface LeadListResponse {
  data: Lead[];
  meta: {
    next_cursor: string | null;
    has_more: boolean;
  };
}

export async function getLeads(params: URLSearchParams): Promise<LeadListResponse> {
  const query = params.toString();
  const path = `/leads${query ? `?${query}` : ""}`;
  return apiRequest<LeadListResponse>(path);
}

export async function getLead(id: string): Promise<Lead> {
  const res = await apiRequest<{ data: Lead }>(
    `/leads/${id}?include=owner,team,latest_assessment,next_task`
  );
  return res.data;
}

export async function updateLead(
  id: string,
  payload: {
    version: number;
    status?: LeadStatus;
    lost_reason?: LostReason | null;
    reopen_reason?: string | null;
    name?: string;
    priority?: LeadPriority;
    email?: string | null;
    phone?: string | null;
    company_name?: string | null;
  }
): Promise<Lead> {
  const res = await apiRequest<{ data: Lead }>(`/leads/${id}`, {
    method: "PATCH",
    body: payload,
  });
  return res.data;
}

export async function getLeadTimeline(
  leadId: string,
  limit = 50,
  offset = 0
): Promise<TimelineEvent[]> {
  const res = await apiRequest<{ data: TimelineEvent[] }>(
    `/leads/${leadId}/timeline?limit=${limit}&offset=${offset}`
  );
  return res.data;
}

export async function addLeadNote(
  leadId: string,
  text: string
): Promise<{ id: string; text: string; created_at: string }> {
  const res = await apiRequest<{
    data: { id: string; text: string; created_at: string };
  }>(`/leads/${leadId}/notes`, {
    method: "POST",
    body: { text },
  });
  return res.data;
}

export async function reviewAssessment(
  assessmentId: string,
  payload: {
    review_status: "approved" | "rejected";
    review_note?: string | null;
  }
): Promise<unknown> {
  const res = await apiRequest<{ data: unknown }>(
    `/assessments/${assessmentId}/review`,
    {
      method: "PATCH",
      body: payload,
    }
  );
  return res.data;
}

export async function importLeadsCsv(
  file: File,
  dryRun = false
): Promise<CsvImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("dry_run", String(dryRun));

  const res = await apiRequest<{ data: CsvImportResult }>("/leads/import", {
    method: "POST",
    body: formData,
    idempotencyKey: createIdempotencyKeyForAction(),
  });
  return res.data;
}
