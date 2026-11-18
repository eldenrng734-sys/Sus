import { apiRequest } from "@/lib/api/client";

export type DashboardScope = "me" | "team" | "company";

export interface DashboardPeriod {
  from: string;
  to: string;
  timezone: string;
}

export interface RepKPIs {
  new_leads: number;
  high_priority_leads: number;
  follow_ups_due_today: number;
  overdue_tasks: number;
  conversion_rate: number;
}

export interface TeamKPIs {
  new_leads: number;
  high_priority_leads: number;
  follow_ups_due_today: number;
  overdue_tasks: number;
  conversion_rate: number;
  avg_first_response_seconds?: number | null;
  follow_up_completion_rate?: number | null;
}

export interface CompanyKPIs {
  new_leads: number;
  won_leads: number;
  high_priority_leads: number;
  conversion_rate: number;
}

export interface PipelineCounts {
  new: number;
  contacted: number;
  qualified: number;
  proposal: number;
  won: number;
  lost: number;
}

export interface SourceCount {
  source: string;
  count: number;
}

export interface StatusCount {
  status: string;
  count: number;
}

export interface LostReasonCount {
  reason: string;
  count: number;
}

export interface RepPerformance {
  user_id: string;
  name: string;
  leads: number;
  won: number;
  conversion_rate: number;
}

export interface RecentConversation {
  id: string;
  lead_id: string;
  lead_name: string;
  channel: string;
  status: string;
  last_message_at: string | null;
}

export interface IntegrationHealthItem {
  provider: string;
  status: string;
  last_event_at: string | null;
}

export interface AutomationHealthSummary {
  workflow_a_success_rate: number;
  workflow_b_success_rate: number;
  failed_runs_24h: number;
}

export interface DashboardMeResponse {
  scope: "me";
  period: DashboardPeriod;
  kpis: RepKPIs;
  pipeline: PipelineCounts;
  recent_conversations: RecentConversation[];
}

export interface DashboardTeamResponse {
  scope: "team";
  period: DashboardPeriod;
  kpis: TeamKPIs;
  pipeline: PipelineCounts;
  leads_by_source: SourceCount[];
  leads_by_status: StatusCount[];
  lost_reasons: LostReasonCount[];
  reps: RepPerformance[];
}

export interface DashboardCompanyResponse {
  scope: "company";
  period: DashboardPeriod;
  kpis: CompanyKPIs;
  pipeline: PipelineCounts;
  leads_by_source: SourceCount[];
  leads_by_status: StatusCount[];
  lost_reasons: LostReasonCount[];
  reps: RepPerformance[];
  users_by_role: Record<string, number>;
  integration_health: IntegrationHealthItem[];
  automation_health?: AutomationHealthSummary | null;
}

export type DashboardSummaryData =
  | DashboardMeResponse
  | DashboardTeamResponse
  | DashboardCompanyResponse;

export async function getDashboardSummary(params: {
  scope?: DashboardScope;
  from?: string;
  to?: string;
  team_id?: string;
}): Promise<DashboardSummaryData> {
  const query = new URLSearchParams();
  if (params.scope) query.set("scope", params.scope);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.team_id) query.set("team_id", params.team_id);

  const path = query.toString()
    ? `/dashboard/summary?${query.toString()}`
    : "/dashboard/summary";

  const res = await apiRequest<{ data: DashboardSummaryData }>(path);
  return res.data;
}
