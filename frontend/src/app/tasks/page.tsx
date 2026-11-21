"use client";

import { FormEvent, useMemo, useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import {
  Plus,
  Search,
  CalendarDays,
  CheckCircle2,
  Circle,
  Clock,
  ListTodo,
  X,
  ClipboardCheck,
  AlertTriangle,
  Play,
  RotateCcw,
} from "lucide-react";
import { useAuth } from "@/providers/auth-provider";
import {
  useTasks,
  useApprovalQueue,
  useCreateTask,
  useUpdateTask,
  useDecideApproval,
  getTaskDayBucket,
} from "@/hooks/use-tasks";
import {
  formatTenantDateTime,
  buildTenantDateTime,
  DEFAULT_TIMEZONE,
} from "@/lib/format";
import type { Task, TaskType } from "@/lib/api/tasks";
import { parseApiError } from "@/lib/api-error";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorBanner } from "@/components/shared/error-banner";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { RefreshButton } from "@/components/shared/refresh-button";

type TaskTab = "today" | "overdue" | "upcoming" | "approval_queue" | "completed" | "all";

const taskTypeLabels: Record<TaskType, string> = {
  call: "Call",
  meeting: "Meeting",
  reminder: "Reminder",
  follow_up: "Follow-up",
};

export default function TasksPage() {
  const { user, role, timezone } = useAuth();

  const isManagerOrAdmin = role === "manager" || role === "admin";

  const {
    data: tasks = [],
    isLoading: isLoadingTasks,
    isError: isTasksError,
    error: tasksError,
    refetch: refetchTasks,
  } = useTasks();

  const {
    data: approvalQueue = [],
    isLoading: isLoadingApprovalQueue,
    refetch: refetchApprovalQueue,
  } = useApprovalQueue({ enabled: isManagerOrAdmin });

  const createTaskMutation = useCreateTask();
  const updateTaskMutation = useUpdateTask();
  const decideApprovalMutation = useDecideApproval();

  const [activeTab, setActiveTab] = useState<TaskTab>("today");
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);

  // Form state
  const [title, setTitle] = useState("");
  const [leadId, setLeadId] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [dueTime, setDueTime] = useState("09:00");
  const [taskType, setTaskType] = useState<TaskType>("follow_up");
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [notes, setNotes] = useState("");

  const [notice, setNotice] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<{
    title: string;
    message: string;
  } | null>(null);

  // Inline 409 conflict state
  const [conflictState, setConflictState] = useState<{
    taskId: string;
    action: "done" | "open" | "approve" | "reject";
    message: string;
  } | null>(null);

  // Refresh handler
  const handleRefresh = async () => {
    setErrorBanner(null);
    setConflictState(null);
    await Promise.all([
      refetchTasks(),
      isManagerOrAdmin ? refetchApprovalQueue() : Promise.resolve(),
    ]);
  };

  // Grouping and counts
  const {
    todayTasks,
    overdueTasks,
    upcomingTasks,
    pendingApprovalTasks,
    completedTasks,
  } = useMemo(() => {
    const today: Task[] = [];
    const overdue: Task[] = [];
    const upcoming: Task[] = [];
    const pendingApproval: Task[] = [];
    const completed: Task[] = [];

    // Combine tasks and approvalQueue deduplicating by ID
    const taskMap = new Map<string, Task>();
    for (const t of tasks) {
      taskMap.set(t.id, t);
    }
    for (const t of approvalQueue) {
      if (!taskMap.has(t.id)) {
        taskMap.set(t.id, t);
      }
    }

    const allCombined = Array.from(taskMap.values());

    for (const task of allCombined) {
      if (task.status === "done") {
        completed.push(task);
      }

      if (task.approval_status === "pending") {
        pendingApproval.push(task);
      }

      if (task.status === "open" || task.status === "paused") {
        const bucket = getTaskDayBucket(task, timezone);
        if (bucket === "overdue") {
          overdue.push(task);
        } else if (bucket === "today") {
          today.push(task);
        } else {
          upcoming.push(task);
        }
      }
    }

    return {
      todayTasks: today,
      overdueTasks: overdue,
      upcomingTasks: upcoming,
      pendingApprovalTasks: pendingApproval,
      completedTasks: completed,
    };
  }, [tasks, approvalQueue, timezone]);

  // Tab filtered items
  const tabTasks = useMemo(() => {
    switch (activeTab) {
      case "today":
        return todayTasks;
      case "overdue":
        return overdueTasks;
      case "upcoming":
        return upcomingTasks;
      case "approval_queue":
        return isManagerOrAdmin && approvalQueue.length > 0
          ? approvalQueue
          : pendingApprovalTasks;
      case "completed":
        return completedTasks;
      case "all":
      default:
        return tasks;
    }
  }, [
    activeTab,
    todayTasks,
    overdueTasks,
    upcomingTasks,
    approvalQueue,
    pendingApprovalTasks,
    completedTasks,
    tasks,
    isManagerOrAdmin,
  ]);

  // Search filtered items
  const filteredTasks = useMemo(() => {
    if (!search.trim()) return tabTasks;
    const query = search.toLowerCase();
    return tabTasks.filter(
      (task) =>
        task.title.toLowerCase().includes(query) ||
        (task.notes && task.notes.toLowerCase().includes(query))
    );
  }, [tabTasks, search]);

  // Actions
  const handleMarkDone = async (task: Task) => {
    if (task.status === "done" || task.status === "cancelled") return;
    setConflictState(null);
    setErrorBanner(null);

    try {
      await updateTaskMutation.mutateAsync({
        taskId: task.id,
        payload: { status: "done", version: task.version },
      });
      setNotice("Task marked as completed.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err: unknown) {
      const apiErr = err as { status?: number; message?: string };
      if (apiErr?.status === 409) {
        setConflictState({
          taskId: task.id,
          action: "done",
          message:
            "This task was modified by another request. Reloaded with latest version.",
        });
        await handleRefresh();
      } else {
        const parsed = parseApiError(err);
        setErrorBanner({ title: parsed.title, message: parsed.message });
      }
    }
  };

  const handleResumeTask = async (task: Task) => {
    setConflictState(null);
    setErrorBanner(null);

    try {
      await updateTaskMutation.mutateAsync({
        taskId: task.id,
        payload: { status: "open", version: task.version },
      });
      setNotice("Task resumed successfully.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err: unknown) {
      const apiErr = err as { status?: number; message?: string };
      if (apiErr?.status === 409) {
        setConflictState({
          taskId: task.id,
          action: "open",
          message:
            "This task was modified by another request. Reloaded with latest version.",
        });
        await handleRefresh();
      } else {
        const parsed = parseApiError(err);
        setErrorBanner({ title: parsed.title, message: parsed.message });
      }
    }
  };

  const handleApprovalDecision = async (task: Task, approved: boolean) => {
    setConflictState(null);
    setErrorBanner(null);

    try {
      await decideApprovalMutation.mutateAsync({
        taskId: task.id,
        approved,
        note: null,
      });
      setNotice(approved ? "Task approved." : "Task rejected.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err: unknown) {
      const apiErr = err as { status?: number; message?: string };
      if (apiErr?.status === 409) {
        setConflictState({
          taskId: task.id,
          action: approved ? "approve" : "reject",
          message:
            "This task was modified by another request. Reloaded with latest version.",
        });
        await handleRefresh();
      } else {
        const parsed = parseApiError(err);
        setErrorBanner({ title: parsed.title, message: parsed.message });
      }
    }
  };

  const handleRetryConflict = async (taskId: string) => {
    if (!conflictState) return;
    const action = conflictState.action;
    setConflictState(null);

    const target =
      tasks.find((t) => t.id === taskId) ||
      approvalQueue.find((t) => t.id === taskId);
    if (!target) return;

    if (action === "done") {
      await handleMarkDone(target);
    } else if (action === "open") {
      await handleResumeTask(target);
    } else if (action === "approve") {
      await handleApprovalDecision(target, true);
    } else if (action === "reject") {
      await handleApprovalDecision(target, false);
    }
  };

  const handleCreateTask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!title.trim() || !leadId.trim() || !dueDate) return;

    setErrorBanner(null);

    try {
      const dueAt = buildTenantDateTime(
        dueDate,
        dueTime,
        timezone || DEFAULT_TIMEZONE
      );

      await createTaskMutation.mutateAsync({
        title: title.trim(),
        lead_id: leadId.trim(),
        due_at: dueAt,
        type: taskType,
        requires_approval: requiresApproval,
        notes: notes.trim() || null,
        assigned_user_id: user?.id ?? null,
      });

      setTitle("");
      setLeadId("");
      setDueDate("");
      setDueTime("09:00");
      setTaskType("follow_up");
      setRequiresApproval(false);
      setNotes("");
      setShowForm(false);
      setNotice("Task created successfully.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err: unknown) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const isLoading = isLoadingTasks || (isManagerOrAdmin && isLoadingApprovalQueue);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-6 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">Workspace / Activities</p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">Tasks</h1>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600">
              Timezone: {timezone || DEFAULT_TIMEZONE}
            </span>
            <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
              Task management
            </span>
          </div>
        </header>

        <div className="mx-auto max-w-7xl space-y-7 p-5 sm:p-8">
          {/* Action Row */}
          <section className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold text-slate-900">Task Board</h2>
              <p className="mt-1 text-sm text-slate-500">
                Organize your work, monitor due follow-ups, and manage approvals.
              </p>
            </div>

            <div className="flex gap-2">
              <RefreshButton
                onRefresh={handleRefresh}
                iconSize={17}
                className="px-3 py-2.5 text-sm font-medium text-slate-600"
              />
              <button
                onClick={() => setShowForm(true)}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
              >
                <Plus size={18} />
                New Task
              </button>
            </div>
          </section>

          {/* Feedback Banners */}
          {errorBanner && (
            <ErrorBanner
              title={errorBanner.title}
              message={errorBanner.message}
              onDismiss={() => setErrorBanner(null)}
              onRetry={() => void handleRefresh()}
            />
          )}

          {isTasksError && !errorBanner && (
            <ErrorBanner
              error={tasksError}
              onRetry={() => void handleRefresh()}
            />
          )}

          {notice && (
            <div className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
              <span>{notice}</span>
              <button
                onClick={() => setNotice(null)}
                className="text-green-600 hover:text-green-800"
              >
                <X size={16} />
              </button>
            </div>
          )}

          {/* Statistics Cards */}
          <section className="grid gap-4 sm:grid-cols-4">
            {[
              { label: "Total Tasks", value: tasks.length, icon: ListTodo, color: "text-blue-700", bg: "bg-blue-50" },
              { label: "Today", value: todayTasks.length, icon: CalendarDays, color: "text-blue-700", bg: "bg-blue-50" },
              {
                label: "Overdue",
                value: overdueTasks.length,
                icon: Clock,
                color: overdueTasks.length > 0 ? "text-red-700" : "text-slate-600",
                bg: overdueTasks.length > 0 ? "bg-red-50" : "bg-slate-50",
              },
              {
                label: "Pending Approval",
                value: pendingApprovalTasks.length,
                icon: ClipboardCheck,
                color: pendingApprovalTasks.length > 0 ? "text-amber-700" : "text-slate-600",
                bg: pendingApprovalTasks.length > 0 ? "bg-amber-50" : "bg-slate-50",
              },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <article
                  key={item.label}
                  className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-slate-500">{item.label}</p>
                    <div className={`rounded-lg p-2 ${item.bg} ${item.color}`}>
                      <Icon size={19} />
                    </div>
                  </div>
                  <p className="mt-4 text-3xl font-bold text-slate-900">{item.value}</p>
                </article>
              );
            })}
          </section>

          {/* Main Card: Tabs + Search + Table */}
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="flex flex-col gap-4 border-b border-slate-100 pb-5 sm:flex-row sm:items-center sm:justify-between">
              {/* Tab Navigation */}
              <div className="flex flex-wrap gap-2">
                {[
                  { id: "today", label: "Today", count: todayTasks.length },
                  {
                    id: "overdue",
                    label: "Overdue",
                    count: overdueTasks.length,
                    badgeStyle:
                      overdueTasks.length > 0
                        ? "bg-red-100 text-red-700"
                        : "bg-slate-200 text-slate-700",
                  },
                  { id: "upcoming", label: "Upcoming", count: upcomingTasks.length },
                  {
                    id: "approval_queue",
                    label: "Approval queue",
                    count: isManagerOrAdmin
                      ? approvalQueue.length
                      : pendingApprovalTasks.length,
                    badgeStyle:
                      (isManagerOrAdmin ? approvalQueue.length : pendingApprovalTasks.length) > 0
                        ? "bg-amber-100 text-amber-800"
                        : "bg-slate-200 text-slate-700",
                  },
                  { id: "completed", label: "Completed", count: completedTasks.length },
                  { id: "all", label: "All Tasks", count: tasks.length },
                ].map((tab) => {
                  const isActive = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id as TaskTab)}
                      className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition ${
                        isActive
                          ? "bg-blue-600 text-white shadow-sm"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      <span>{tab.label}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                          isActive
                            ? "bg-blue-700 text-white"
                            : tab.badgeStyle || "bg-slate-200 text-slate-700"
                        }`}
                      >
                        {tab.count}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Search Box */}
              <div className="relative w-full sm:max-w-xs">
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                  size={17}
                />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search tasks or notes..."
                  className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>
            </div>

            {/* Tasks Table */}
            <div className="mt-4 overflow-x-auto">
              {isLoading ? (
                <div className="py-16 text-center">
                  <LoadingSpinner size="md" message="Loading tasks..." />
                </div>
              ) : filteredTasks.length === 0 ? (
                <div className="py-12">
                  <EmptyState
                    icon={ListTodo}
                    title={search ? "No matching tasks found" : `No tasks in ${activeTab.replace("_", " ")}`}
                    description={
                      search
                        ? "Try clearing your search query or switching tabs."
                        : activeTab === "approval_queue"
                        ? "No tasks currently require manager approval."
                        : activeTab === "overdue"
                        ? "Great job! You have no overdue tasks."
                        : "Create a new task to stay organized."
                    }
                    action={
                      search
                        ? { label: "Clear search", onClick: () => setSearch("") }
                        : { label: "New Task", onClick: () => setShowForm(true) }
                    }
                  />
                </div>
              ) : (
                <table className="w-full min-w-[720px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
                      <th className="pb-3 font-medium">Task</th>
                      <th className="pb-3 font-medium">Due (Tenant Time)</th>
                      <th className="pb-3 font-medium">Type</th>
                      <th className="pb-3 font-medium">Approval</th>
                      <th className="pb-3 font-medium">Status</th>
                      <th className="pb-3 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredTasks.map((task) => {
                      const isDone = task.status === "done";
                      const isCancelled = task.status === "cancelled";
                      const isPaused = task.status === "paused";
                      const needsApproval =
                        task.requires_approval && task.approval_status !== "approved";
                      const hasConflict = conflictState?.taskId === task.id;

                      return (
                        <tr
                          key={task.id}
                          className={`transition hover:bg-slate-50/60 ${
                            isCancelled ? "opacity-60 bg-slate-50/40" : ""
                          }`}
                        >
                          {/* Task Title & Checkbox */}
                          <td className="py-4 pr-3">
                            <div className="flex items-start gap-3">
                              <button
                                onClick={() => void handleMarkDone(task)}
                                disabled={
                                  isDone ||
                                  isCancelled ||
                                  isPaused ||
                                  needsApproval ||
                                  updateTaskMutation.isPending
                                }
                                title={
                                  isDone
                                    ? "Task completed"
                                    : isCancelled
                                    ? "Cancelled task (read-only)"
                                    : isPaused
                                    ? "Task is paused; resume before completing"
                                    : needsApproval
                                    ? "This task needs manager approval before completion"
                                    : "Mark task as completed"
                                }
                                className="mt-0.5 shrink-0 disabled:cursor-not-allowed"
                              >
                                {isDone ? (
                                  <CheckCircle2 size={19} className="text-green-600" />
                                ) : (
                                  <Circle
                                    size={19}
                                    className={
                                      needsApproval || isPaused || isCancelled
                                        ? "text-slate-300"
                                        : "text-slate-400 hover:text-blue-600"
                                    }
                                  />
                                )}
                              </button>

                              <div className="min-w-0">
                                <p
                                  className={`font-medium ${
                                    isDone
                                      ? "text-slate-400 line-through"
                                      : isCancelled
                                      ? "text-slate-400"
                                      : "text-slate-900"
                                  }`}
                                >
                                  {task.title}
                                </p>

                                {task.notes && (
                                  <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">
                                    {task.notes}
                                  </p>
                                )}

                                {/* Inline 409 Conflict Banner */}
                                {hasConflict && (
                                  <div className="mt-2 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                                    <AlertTriangle size={15} className="shrink-0 text-amber-600" />
                                    <span className="flex-1">{conflictState.message}</span>
                                    <button
                                      onClick={() => void handleRetryConflict(task.id)}
                                      className="inline-flex items-center gap-1 rounded bg-amber-600 px-2 py-0.5 font-semibold text-white hover:bg-amber-700"
                                    >
                                      <RotateCcw size={12} />
                                      Retry
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>

                          {/* Due Date */}
                          <td className="py-4 text-slate-600 whitespace-nowrap text-xs">
                            {formatTenantDateTime(task.due_at, timezone)}
                          </td>

                          {/* Task Type */}
                          <td className="py-4 whitespace-nowrap">
                            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
                              {taskTypeLabels[task.type] || task.type}
                            </span>
                          </td>

                          {/* Approval Status */}
                          <td className="py-4 whitespace-nowrap">
                            {task.approval_status === "pending" ? (
                              <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                                Pending review
                              </span>
                            ) : task.approval_status === "approved" ? (
                              <span className="rounded-full bg-green-50 px-2.5 py-1 text-xs font-medium text-green-700">
                                Approved
                              </span>
                            ) : task.approval_status === "rejected" ? (
                              <span className="rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700">
                                Rejected
                              </span>
                            ) : (
                              <span className="text-xs text-slate-400">Not required</span>
                            )}
                          </td>

                          {/* Status / Badges */}
                          <td className="py-4 whitespace-nowrap">
                            {isPaused ? (
                              <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
                                <span className="h-1.5 w-1.5 rounded-full bg-amber-600" />
                                Paused: customer replied
                              </span>
                            ) : isCancelled ? (
                              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
                                Cancelled
                              </span>
                            ) : isDone ? (
                              <span className="rounded-full bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-700">
                                Completed
                              </span>
                            ) : (
                              <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                                Open
                              </span>
                            )}
                          </td>

                          {/* Actions Column */}
                          <td className="py-4 text-right whitespace-nowrap">
                            <div className="flex items-center justify-end gap-2">
                              {/* Resume button for paused task */}
                              {isPaused && (
                                <button
                                  onClick={() => void handleResumeTask(task)}
                                  disabled={updateTaskMutation.isPending}
                                  className="inline-flex items-center gap-1 rounded-lg bg-blue-50 px-2.5 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100"
                                >
                                  <Play size={13} />
                                  Resume
                                </button>
                              )}

                              {/* Approval Buttons for Manager/Admin */}
                              {task.approval_status === "pending" && isManagerOrAdmin && (
                                <>
                                  <button
                                    onClick={() => void handleApprovalDecision(task, true)}
                                    disabled={decideApprovalMutation.isPending}
                                    className="rounded-lg bg-green-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-green-700"
                                  >
                                    Approve
                                  </button>
                                  <button
                                    onClick={() => void handleApprovalDecision(task, false)}
                                    disabled={decideApprovalMutation.isPending}
                                    className="rounded-lg border border-red-200 px-2.5 py-1 text-xs font-semibold text-red-600 hover:bg-red-50"
                                  >
                                    Reject
                                  </button>
                                </>
                              )}

                              {/* Rep view of pending approval */}
                              {task.approval_status === "pending" && !isManagerOrAdmin && (
                                <span className="text-xs text-slate-400 italic">
                                  Awaiting manager
                                </span>
                              )}

                              {/* Cancelled indicator */}
                              {isCancelled && (
                                <span className="text-xs text-slate-400">Read-only</span>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </div>
      </main>

      {/* Create Task Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-slate-900">Create a task</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Add a new activity or follow-up.
                </p>
              </div>
              <button
                onClick={() => setShowForm(false)}
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
                aria-label="Close form"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreateTask} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Task title
                </label>
                <input
                  required
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="e.g. Follow up on proposal"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Lead UUID
                </label>
                <input
                  required
                  value={leadId}
                  onChange={(event) => setLeadId(event.target.value)}
                  placeholder="Paste the lead UUID (e.g. from lead details)"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
                <p className="mt-1 text-xs text-slate-400">
                  Find the lead UUID from the Leads page or conversation thread.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    Due date
                  </label>
                  <div className="relative">
                    <CalendarDays
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                      size={17}
                    />
                    <input
                      required
                      type="date"
                      value={dueDate}
                      onChange={(event) => setDueDate(event.target.value)}
                      className="w-full rounded-lg border border-slate-200 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    Time
                  </label>
                  <input
                    type="time"
                    value={dueTime}
                    onChange={(event) => setDueTime(event.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Task type
                </label>
                <select
                  value={taskType}
                  onChange={(event) => setTaskType(event.target.value as TaskType)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
                >
                  <option value="follow_up">Follow-up</option>
                  <option value="call">Call</option>
                  <option value="meeting">Meeting</option>
                  <option value="reminder">Reminder</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Notes (optional)
                </label>
                <textarea
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder="Additional context or notes..."
                  rows={2}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={requiresApproval}
                  onChange={(event) => setRequiresApproval(event.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                />
                Requires manager approval
              </label>

              <div className="flex justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createTaskMutation.isPending}
                  className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {createTaskMutation.isPending ? "Creating..." : "Create task"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
