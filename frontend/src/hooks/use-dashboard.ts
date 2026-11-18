import { useQuery } from "@tanstack/react-query";
import {
  getDashboardSummary,
  type DashboardScope,
  type DashboardSummaryData,
} from "@/lib/api/dashboard";

export function useDashboardSummary(params: {
  scope: DashboardScope;
  from?: string;
  to?: string;
  team_id?: string;
}) {
  return useQuery<DashboardSummaryData>({
    queryKey: ["dashboard-summary", params.scope, params.from, params.to, params.team_id],
    queryFn: () => getDashboardSummary(params),
    retry: false, // Don't retry on 403 access denied
    staleTime: 60_000, // Stale after 1 minute
  });
}
