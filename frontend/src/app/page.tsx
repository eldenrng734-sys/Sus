"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Users,
  UserPlus,
  CalendarClock,
  AlertCircle,
  TrendingUp,
  ArrowUpRight,
  ShieldAlert,
  RefreshCw,
  MessageSquare,
  Award,
  Bot,
  Plug,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";
import { Sidebar } from "@/components/layout/sidebar";
import { useAuth } from "@/providers/auth-provider";
import { useDashboardSummary } from "@/hooks/use-dashboard";
import type {
  DashboardScope,
  DashboardMeResponse,
  DashboardTeamResponse,
  DashboardCompanyResponse,
} from "@/lib/api/dashboard";
import { formatTenantDateTime } from "@/hooks/use-tasks";
import { LoadingSpinner } from "@/components/shared/loading-spinner";

type DatePreset = "7d" | "30d" | "90d";

const PIPELINE_COLORS: Record<string, string> = {
  new: "#3b82f6", // blue
  contacted: "#06b6d4", // cyan
  qualified: "#10b981", // emerald
  proposal: "#8b5cf6", // violet
  won: "#22c55e", // green
  lost: "#ef4444", // red
};

export default function DashboardPage() {
  const { user, role, timezone } = useAuth();

  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  // Allowed scopes based on user role
  const allowedScopes = useMemo<DashboardScope[]>(() => {
    if (role === "admin") return ["me", "team", "company"];
    if (role === "manager") return ["me", "team"];
    return ["me"];
  }, [role]);

  const [scope, setScope] = useState<DashboardScope>("me");
  const [preset, setPreset] = useState<DatePreset>("30d");

  // Ensure selected scope is valid for role
  useEffect(() => {
    if (!allowedScopes.includes(scope)) {
      setScope(allowedScopes[0] || "me");
    }
  }, [allowedScopes, scope]);

  // Compute from/to dates based on preset
  const { fromDate, toDate } = useMemo(() => {
    const now = new Date();
    const to = now.toISOString().slice(0, 10);
    const past = new Date();
    if (preset === "7d") {
      past.setDate(now.getDate() - 7);
    } else if (preset === "90d") {
      past.setDate(now.getDate() - 90);
    } else {
      past.setDate(now.getDate() - 30);
    }
    const from = past.toISOString().slice(0, 10);
    return { fromDate: from, toDate: to };
  }, [preset]);

  const {
    data: summaryData,
    isLoading,
    isError,
    error,
    refetch,
  } = useDashboardSummary({
    scope,
    from: fromDate,
    to: toDate,
  });

  const is403AccessDenied =
    isError && (error as { status?: number })?.status === 403;

  // Cast response data according to active scope
  const meData = scope === "me" ? (summaryData as DashboardMeResponse) : null;
  const teamData = scope === "team" ? (summaryData as DashboardTeamResponse) : null;
  const companyData =
    scope === "company" ? (summaryData as DashboardCompanyResponse) : null;

  // Pipeline bar chart data
  const pipelineChartData = useMemo(() => {
    const pipeline = summaryData?.pipeline;
    if (!pipeline) return [];
    return [
      { name: "New", key: "new", count: pipeline.new, fill: PIPELINE_COLORS.new },
      { name: "Contacted", key: "contacted", count: pipeline.contacted, fill: PIPELINE_COLORS.contacted },
      { name: "Qualified", key: "qualified", count: pipeline.qualified, fill: PIPELINE_COLORS.qualified },
      { name: "Proposal", key: "proposal", count: pipeline.proposal, fill: PIPELINE_COLORS.proposal },
      { name: "Won", key: "won", count: pipeline.won, fill: PIPELINE_COLORS.won },
      { name: "Lost", key: "lost", count: pipeline.lost, fill: PIPELINE_COLORS.lost },
    ];
  }, [summaryData]);

  // Sources breakdown data (for team and company)
  const sourcesData = useMemo(() => {
    if (teamData?.leads_by_source) return teamData.leads_by_source;
    if (companyData?.leads_by_source) return companyData.leads_by_source;
    return [];
  }, [teamData, companyData]);

  // Rep performance data (for team and company)
  const repsData = useMemo(() => {
    if (teamData?.reps) return teamData.reps;
    if (companyData?.reps) return companyData.reps;
    return [];
  }, [teamData, companyData]);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        {/* Header */}
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-6 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">Workspace / Analytics</p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">Dashboard</h1>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 sm:inline-flex">
              Timezone: {timezone || "Asia/Dhaka"}
            </span>
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700">
              {(user?.display_name || user?.email || "U").charAt(0).toUpperCase()}
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-7xl space-y-7 p-6 sm:p-8">
          {/* Controls Bar: Scope Selector + Period Filter */}
          <section className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold text-slate-900">
                {scope === "company"
                  ? "Company Performance"
                  : scope === "team"
                  ? "Team Performance"
                  : "My Sales Overview"}
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                {scope === "company"
                  ? "Executive metrics, reps leaderboard, and integration health."
                  : scope === "team"
                  ? "Team pipeline, rep distribution, and lead sources."
                  : "Track your personal pipeline, tasks, and recent conversations."}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              {/* Scope Selector: offers only allowed scopes */}
              {allowedScopes.length > 1 && (
                <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-xs">
                  {allowedScopes.map((sc) => (
                    <button
                      key={sc}
                      onClick={() => setScope(sc)}
                      className={`rounded-md px-3 py-1.5 text-xs font-semibold capitalize transition ${
                        scope === sc
                          ? "bg-blue-600 text-white shadow-xs"
                          : "text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      {sc === "me" ? "My View" : sc === "team" ? "Team" : "Company"}
                    </button>
                  ))}
                </div>
              )}

              {/* Date Presets */}
              <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-xs">
                {(["7d", "30d", "90d"] as DatePreset[]).map((p) => (
                  <button
                    key={p}
                    onClick={() => setPreset(p)}
                    className={`rounded-md px-2.5 py-1.5 text-xs font-medium transition ${
                      preset === p
                        ? "bg-slate-900 text-white"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {p === "7d" ? "7 Days" : p === "30d" ? "30 Days" : "90 Days"}
                  </button>
                ))}
              </div>

              {/* Refresh button */}
              <button
                onClick={() => void refetch()}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50"
              >
                <RefreshCw size={13} className={isLoading ? "animate-spin" : ""} />
                Refresh
              </button>
            </div>
          </section>

          {/* Access Denied Card (403) */}
          {is403AccessDenied && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
              <ShieldAlert size={36} className="text-red-600" />
              <h3 className="mt-3 text-base font-bold text-red-900">
                Access Denied
              </h3>
              <p className="mt-1 max-w-md text-xs text-red-700">
                You do not have permission to view the &apos;{scope}&apos; dashboard.
                Access is restricted to authorized roles.
              </p>
              <button
                onClick={() => setScope("me")}
                className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-red-700"
              >
                Switch to My Dashboard
              </button>
            </div>
          )}

          {/* Loading State */}
          {isLoading && !summaryData && (
            <div className="flex min-h-[300px] items-center justify-center py-16">
              <LoadingSpinner size="lg" message="Loading dashboard metrics..." />
            </div>
          )}

          {/* Main Dashboard Content */}
          {summaryData && !is403AccessDenied && (
            <>
              {/* Top KPIs Grid */}
              <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
                {scope === "company" && companyData ? (
                  <>
                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-500">New Leads</p>
                        <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                          <UserPlus size={19} />
                        </div>
                      </div>
                      <p className="mt-4 text-3xl font-bold text-slate-900">
                        {companyData.kpis.new_leads}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">Total captured in period</p>
                    </article>

                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-500">Won Deals</p>
                        <div className="rounded-lg bg-green-50 p-2 text-green-700">
                          <Award size={19} />
                        </div>
                      </div>
                      <p className="mt-4 text-3xl font-bold text-green-700">
                        {companyData.kpis.won_leads}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">Converted customers</p>
                    </article>

                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-500">High Priority</p>
                        <div className="rounded-lg bg-amber-50 p-2 text-amber-700">
                          <AlertCircle size={19} />
                        </div>
                      </div>
                      <p className="mt-4 text-3xl font-bold text-slate-900">
                        {companyData.kpis.high_priority_leads}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">Needs prompt follow-up</p>
                    </article>

                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-500">Conversion Rate</p>
                        <div className="rounded-lg bg-purple-50 p-2 text-purple-700">
                          <ArrowUpRight size={19} />
                        </div>
                      </div>
                      <p className="mt-4 text-3xl font-bold text-slate-900">
                        {(companyData.kpis.conversion_rate * 100).toFixed(1)}%
                      </p>
                      <p className="mt-1 text-xs text-slate-400">Overall lead-to-won ratio</p>
                    </article>
                  </>
                ) : (
                  <>
                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-500">New Leads</p>
                        <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                          <UserPlus size={19} />
                        </div>
                      </div>
                      <p className="mt-4 text-3xl font-bold text-slate-900">
                        {meData ? meData.kpis.new_leads : teamData?.kpis.new_leads ?? 0}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">Assigned in period</p>
                    </article>

                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-500">Due Today</p>
                        <div className="rounded-lg bg-cyan-50 p-2 text-cyan-700">
                          <CalendarClock size={19} />
                        </div>
                      </div>
                      <p className="mt-4 text-3xl font-bold text-slate-900">
                        {meData
                          ? meData.kpis.follow_ups_due_today
                          : teamData?.kpis.follow_ups_due_today ?? 0}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">Follow-up tasks today</p>
                    </article>

                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-500">Overdue Tasks</p>
                        <div
                          className={`rounded-lg p-2 ${
                            (meData
                              ? meData.kpis.overdue_tasks
                              : teamData?.kpis.overdue_tasks ?? 0) > 0
                              ? "bg-red-50 text-red-700"
                              : "bg-slate-50 text-slate-600"
                          }`}
                        >
                          <AlertCircle size={19} />
                        </div>
                      </div>
                      <p
                        className={`mt-4 text-3xl font-bold ${
                          (meData
                            ? meData.kpis.overdue_tasks
                            : teamData?.kpis.overdue_tasks ?? 0) > 0
                            ? "text-red-700"
                            : "text-slate-900"
                        }`}
                      >
                        {meData ? meData.kpis.overdue_tasks : teamData?.kpis.overdue_tasks ?? 0}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">Requires urgent action</p>
                    </article>

                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-500">Conversion Rate</p>
                        <div className="rounded-lg bg-green-50 p-2 text-green-700">
                          <TrendingUp size={19} />
                        </div>
                      </div>
                      <p className="mt-4 text-3xl font-bold text-slate-900">
                        {(
                          (meData
                            ? meData.kpis.conversion_rate
                            : teamData?.kpis.conversion_rate ?? 0) * 100
                        ).toFixed(1)}
                        %
                      </p>
                      <p className="mt-1 text-xs text-slate-400">Converted in period</p>
                    </article>
                  </>
                )}
              </section>

              {/* Middle Section: Lead Pipeline Chart & Details */}
              <section className="grid gap-6 xl:grid-cols-3">
                {/* Pipeline Bar Chart (2 cols) */}
                <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm xl:col-span-2">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                    <div>
                      <h3 className="font-bold text-slate-900">Lead Pipeline</h3>
                      <p className="text-xs text-slate-500">
                        Distribution across sales lifecycle stages
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-slate-500">
                      <span className="h-2 w-2 rounded-full bg-blue-600" />
                      Active Funnel
                    </div>
                  </div>

                  <div className="mt-6 h-64 w-full">
                    {mounted && pipelineChartData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={pipelineChartData}
                          margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                          <XAxis
                            dataKey="name"
                            tick={{ fontSize: 11, fill: "#64748b" }}
                            axisLine={false}
                            tickLine={false}
                          />
                          <YAxis
                            tick={{ fontSize: 11, fill: "#64748b" }}
                            axisLine={false}
                            tickLine={false}
                            allowDecimals={false}
                          />
                          <Tooltip
                            contentStyle={{
                              borderRadius: "12px",
                              border: "1px solid #e2e8f0",
                              boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
                              fontSize: "12px",
                            }}
                          />
                          <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                            {pipelineChartData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.fill} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-slate-400">
                        Loading chart...
                      </div>
                    )}
                  </div>
                </article>

                {/* Right Card: Sources or Recent Activity */}
                <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm flex flex-col justify-between">
                  <div>
                    <h3 className="font-bold text-slate-900">
                      {sourcesData.length > 0 ? "Leads by Source" : "Pipeline Summary"}
                    </h3>
                    <p className="text-xs text-slate-500">
                      {sourcesData.length > 0
                        ? "Channel attribution for current period"
                        : "Stage count breakdown"}
                    </p>
                  </div>

                  <div className="mt-4 space-y-3 flex-1 overflow-y-auto">
                    {sourcesData.length > 0
                      ? sourcesData.map((s) => (
                          <div
                            key={s.source}
                            className="flex items-center justify-between rounded-xl bg-slate-50 p-2.5 text-xs"
                          >
                            <span className="font-semibold capitalize text-slate-700">
                              {s.source.replace("_", " ")}
                            </span>
                            <span className="rounded-md bg-white px-2 py-0.5 font-bold text-blue-700 shadow-2xs">
                              {s.count}
                            </span>
                          </div>
                        ))
                      : pipelineChartData.map((p) => (
                          <div
                            key={p.name}
                            className="flex items-center justify-between rounded-xl bg-slate-50 p-2.5 text-xs"
                          >
                            <span className="font-semibold text-slate-700">{p.name}</span>
                            <span
                              className="rounded-md px-2 py-0.5 font-bold text-white text-[11px]"
                              style={{ backgroundColor: p.fill }}
                            >
                              {p.count}
                            </span>
                          </div>
                        ))}
                  </div>

                  <div className="mt-4 border-t border-slate-100 pt-3 text-right">
                    <Link
                      href="/leads"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800"
                    >
                      View All Leads <ArrowUpRight size={13} />
                    </Link>
                  </div>
                </article>
              </section>

              {/* Scope-specific Bottom Section */}

              {/* 1. Rep View: Recent Conversations */}
              {scope === "me" && meData && (
                <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                    <div>
                      <h3 className="font-bold text-slate-900">Recent Conversations</h3>
                      <p className="text-xs text-slate-500">
                        Your latest customer inquiries and follow-ups
                      </p>
                    </div>
                    <Link
                      href="/conversations"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800"
                    >
                      Open Inbox <ArrowUpRight size={13} />
                    </Link>
                  </div>

                  <div className="mt-4 overflow-x-auto">
                    {meData.recent_conversations.length === 0 ? (
                      <div className="py-10 text-center text-xs text-slate-400">
                        <MessageSquare size={26} className="mx-auto text-slate-300 mb-2" />
                        No conversations in this period.
                      </div>
                    ) : (
                      <table className="w-full min-w-[500px] text-left text-xs">
                        <thead>
                          <tr className="border-b border-slate-100 text-[11px] uppercase tracking-wider text-slate-400">
                            <th className="pb-2.5 font-medium">Customer</th>
                            <th className="pb-2.5 font-medium">Channel</th>
                            <th className="pb-2.5 font-medium">Status</th>
                            <th className="pb-2.5 font-medium text-right">Last Message</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {meData.recent_conversations.map((c) => (
                            <tr key={c.id} className="hover:bg-slate-50/60 transition">
                              <td className="py-3 font-semibold text-slate-800">
                                <Link
                                  href={`/leads/${c.lead_id}`}
                                  className="hover:text-blue-600"
                                >
                                  {c.lead_name}
                                </Link>
                              </td>
                              <td className="py-3 capitalize text-slate-600">
                                {c.channel}
                              </td>
                              <td className="py-3">
                                <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700 capitalize">
                                  {c.status}
                                </span>
                              </td>
                              <td className="py-3 text-right text-slate-400">
                                {c.last_message_at
                                  ? formatTenantDateTime(c.last_message_at, timezone)
                                  : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </section>
              )}

              {/* 2. Team & Company View: Rep Performance Leaderboard */}
              {(scope === "team" || scope === "company") && repsData.length > 0 && (
                <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                    <div>
                      <h3 className="font-bold text-slate-900">Sales Rep Performance</h3>
                      <p className="text-xs text-slate-500">
                        Lead volume and conversion per team member
                      </p>
                    </div>
                    <Users size={18} className="text-slate-400" />
                  </div>

                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full min-w-[550px] text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-100 text-[11px] uppercase tracking-wider text-slate-400">
                          <th className="pb-2.5 font-medium">Representative</th>
                          <th className="pb-2.5 font-medium">Assigned Leads</th>
                          <th className="pb-2.5 font-medium">Won Deals</th>
                          <th className="pb-2.5 font-medium text-right">Conversion Rate</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {repsData.map((rep) => (
                          <tr key={rep.user_id} className="hover:bg-slate-50/60 transition">
                            <td className="py-3 font-semibold text-slate-800">
                              {rep.name}
                            </td>
                            <td className="py-3 text-slate-600">{rep.leads}</td>
                            <td className="py-3 font-semibold text-green-700">
                              {rep.won}
                            </td>
                            <td className="py-3 text-right font-bold text-slate-900">
                              {(rep.conversion_rate * 100).toFixed(1)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {/* 3. Company View: System & Automation Health */}
              {scope === "company" && companyData && (
                <section className="grid gap-6 md:grid-cols-2">
                  {/* Automation Health */}
                  {companyData.automation_health && (
                    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                      <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
                        <Bot size={18} className="text-blue-600" />
                        <h3 className="font-bold text-slate-900">
                          Automation Workflows Health
                        </h3>
                      </div>

                      <div className="mt-4 space-y-3 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="text-slate-600">Workflow A (New Lead)</span>
                          <span className="font-bold text-green-700">
                            {(
                              companyData.automation_health.workflow_a_success_rate * 100
                            ).toFixed(1)}
                            % success
                          </span>
                        </div>

                        <div className="flex items-center justify-between">
                          <span className="text-slate-600">Workflow B (Follow-up)</span>
                          <span className="font-bold text-green-700">
                            {(
                              companyData.automation_health.workflow_b_success_rate * 100
                            ).toFixed(1)}
                            % success
                          </span>
                        </div>

                        <div className="flex items-center justify-between border-t border-slate-100 pt-2">
                          <span className="text-slate-600">Failed Runs (24h)</span>
                          <span
                            className={`rounded-md px-2 py-0.5 font-bold ${
                              companyData.automation_health.failed_runs_24h > 0
                                ? "bg-red-100 text-red-700"
                                : "bg-slate-100 text-slate-700"
                            }`}
                          >
                            {companyData.automation_health.failed_runs_24h}
                          </span>
                        </div>
                      </div>
                    </article>
                  )}

                  {/* Integration Health */}
                  {companyData.integration_health && companyData.integration_health.length > 0 && (
                    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                      <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
                        <Plug size={18} className="text-blue-600" />
                        <h3 className="font-bold text-slate-900">
                          Integrations Status
                        </h3>
                      </div>

                      <div className="mt-4 space-y-2.5 text-xs">
                        {companyData.integration_health.map((item) => (
                          <div
                            key={item.provider}
                            className="flex items-center justify-between rounded-xl bg-slate-50 p-2.5"
                          >
                            <span className="font-semibold capitalize text-slate-800">
                              {item.provider}
                            </span>
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                                item.status === "healthy" || item.status === "active"
                                  ? "bg-green-100 text-green-700"
                                  : "bg-amber-100 text-amber-800"
                              }`}
                            >
                              {item.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    </article>
                  )}
                </section>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
