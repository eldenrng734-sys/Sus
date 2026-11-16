import { Sidebar } from "@/components/layout/sidebar";
import {
  Users,
  UserPlus,
  CalendarClock,
  AlertCircle,
  ArrowUpRight,
  TrendingUp,
  Clock3,
} from "lucide-react";

const metrics = [
  {
    label: "Total Leads",
    value: "--",
    note: "All leads in your workspace",
    icon: Users,
  },
  {
    label: "New Leads",
    value: "--",
    note: "Recently captured leads",
    icon: UserPlus,
  },
  {
    label: "Follow-ups Due",
    value: "--",
    note: "Scheduled for today",
    icon: CalendarClock,
  },
  {
    label: "Overdue Tasks",
    value: "--",
    note: "Tasks past their due date",
    icon: AlertCircle,
  },
];

export default function DashboardPage() {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-6 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">Workspace / Overview</p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">
              Dashboard
            </h1>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 sm:inline-flex">
              Sales workspace
            </span>
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-200 text-sm font-semibold text-slate-700">
              U
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-7xl space-y-7 p-6 sm:p-8">
          <section className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold text-slate-900">
                Sales overview
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Monitor your leads and sales activities in one place.
              </p>
            </div>

            <span className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600">
              Current period
            </span>
          </section>

          <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map((metric) => {
              const Icon = metric.icon;

              return (
                <article
                  key={metric.label}
                  className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-slate-500">
                      {metric.label}
                    </p>
                    <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                      <Icon size={19} />
                    </div>
                  </div>

                  <p className="mt-5 text-3xl font-bold text-slate-900">
                    {metric.value}
                  </p>
                  <p className="mt-2 text-xs text-slate-500">
                    {metric.note}
                  </p>
                </article>
              );
            })}
          </section>

          <section className="grid gap-5 xl:grid-cols-3">
            <article className="rounded-xl border border-slate-200 bg-white p-6 xl:col-span-2">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-slate-900">
                    Lead pipeline
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">
                    Track leads through each sales stage.
                  </p>
                </div>
                <TrendingUp size={20} className="text-slate-400" />
              </div>

              <div className="mt-8 flex min-h-44 flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-center">
                <Users size={27} className="text-slate-300" />
                <p className="mt-3 text-sm font-medium text-slate-600">
                  No pipeline data available yet
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  Lead analytics will appear here when data is connected.
                </p>
              </div>
            </article>

            <article className="rounded-xl border border-slate-200 bg-white p-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-slate-900">
                    Conversion rate
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">
                    Lead-to-customer performance
                  </p>
                </div>
                <ArrowUpRight size={20} className="text-slate-400" />
              </div>

              <div className="mt-8 flex min-h-44 flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-center">
                <TrendingUp size={27} className="text-slate-300" />
                <p className="mt-3 text-2xl font-bold text-slate-400">--</p>
                <p className="mt-1 text-xs text-slate-400">
                  Waiting for dashboard data
                </p>
              </div>
            </article>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-900">
                  Recent leads
                </h3>
                <p className="mt-1 text-sm text-slate-500">
                  Your latest customer opportunities.
                </p>
              </div>
              <Clock3 size={20} className="text-slate-400" />
            </div>

            <div className="mt-6 overflow-x-auto">
              <table className="w-full min-w-[600px] text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
                    <th className="pb-3 font-medium">Lead</th>
                    <th className="pb-3 font-medium">Source</th>
                    <th className="pb-3 font-medium">Status</th>
                    <th className="pb-3 font-medium">Priority</th>
                    <th className="pb-3 font-medium">Assigned to</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td
                      colSpan={5}
                      className="py-10 text-center text-sm text-slate-400"
                    >
                      No leads to display yet. Connect the leads API to see
                      your customer records here.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
