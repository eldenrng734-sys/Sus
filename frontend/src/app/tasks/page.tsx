
"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
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
  RefreshCw,
  ClipboardCheck,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

type TaskType = "call" | "meeting" | "reminder" | "follow_up";
type TaskStatus = "open" | "done" | "cancelled" | "paused";

type Task = {
  id: string;
  lead_id: string;
  title: string;
  notes: string | null;
  type: TaskType;
  status: TaskStatus;
  due_at: string;
  requires_approval: boolean;
  approval_status: "not_required" | "pending" | "approved" | "rejected";
  created_at: string;
};

const taskTypeLabels: Record<TaskType, string> = {
  call: "Call",
  meeting: "Meeting",
  reminder: "Reminder",
  follow_up: "Follow-up",
};

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [approvalQueue, setApprovalQueue] = useState<Task[]>([]);
  const [filter, setFilter] = useState("All");
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [leadId, setLeadId] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [taskType, setTaskType] = useState<TaskType>("follow_up");
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const result = await apiFetch<Task[]>("/tasks");
      setTasks(result);

      // This endpoint is restricted to managers and admins.
      // A 403 for other roles is expected and should not block the Tasks page.
      try {
        const queue = await apiFetch<Task[]>("/tasks/approval-queue");
        setApprovalQueue(queue);
      } catch {
        setApprovalQueue([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load tasks.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const matchesSearch =
        task.title.toLowerCase().includes(search.toLowerCase());

      const matchesFilter =
        filter === "All" ||
        (filter === "Pending" && task.status !== "done") ||
        (filter === "Completed" && task.status === "done");

      return matchesSearch && matchesFilter;
    });
  }, [tasks, filter, search]);

  const pendingCount = tasks.filter((task) => task.status !== "done").length;
  const completedCount = tasks.filter((task) => task.status === "done").length;

  async function addTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim() || !leadId.trim() || !dueDate) return;

    setSaving(true);
    setError("");
    setNotice("");

    try {
      // Use local 9:00 AM for the selected date, then send an ISO timestamp.
      const dueAt = new Date(`${dueDate}T09:00:00`).toISOString();

      await apiFetch<Task>("/tasks", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          lead_id: leadId.trim(),
          due_at: dueAt,
          type: taskType,
          requires_approval: requiresApproval,
        }),
      });

      setTitle("");
      setLeadId("");
      setDueDate("");
      setTaskType("follow_up");
      setRequiresApproval(false);
      setShowForm(false);
      setNotice("Task created successfully.");
      await loadTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create task.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleTask(task: Task) {
    if (task.status === "done") return;

    setError("");
    setNotice("");

    try {
      await apiFetch<Task>(`/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "done" }),
      });
      setNotice("Task marked as completed.");
      await loadTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update task.");
    }
  }

  async function decideApproval(taskId: string, approved: boolean) {
    setError("");
    setNotice("");

    try {
      await apiFetch<Task>(
        `/tasks/${taskId}/${approved ? "approve" : "reject"}`,
        {
          method: "POST",
          body: JSON.stringify({ note: null }),
        }
      );

      setNotice(approved ? "Task approved." : "Task rejected.");
      await loadTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval action failed.");
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-6 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">Workspace / Activities</p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">Tasks</h1>
          </div>
          <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
            Task management
          </span>
        </header>

        <div className="mx-auto max-w-7xl space-y-7 p-5 sm:p-8">
          <section className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold text-slate-900">My Tasks</h2>
              <p className="mt-1 text-sm text-slate-500">
                Organize your work and stay on top of follow-ups.
              </p>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => void loadTasks()}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                <RefreshCw size={17} />
                Refresh
              </button>
              <button
                onClick={() => setShowForm(true)}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
              >
                <Plus size={18} />
                New Task
              </button>
            </div>
          </section>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {notice && (
            <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
              {notice}
            </div>
          )}

          <section className="grid gap-4 sm:grid-cols-3">
            {[
              { label: "Total Tasks", value: tasks.length, icon: ListTodo },
              { label: "Pending", value: pendingCount, icon: Clock },
              { label: "Completed", value: completedCount, icon: CheckCircle2 },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <article
                  key={item.label}
                  className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-slate-500">
                      {item.label}
                    </p>
                    <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                      <Icon size={19} />
                    </div>
                  </div>
                  <p className="mt-4 text-3xl font-bold text-slate-900">
                    {item.value}
                  </p>
                </article>
              );
            })}
          </section>

          {approvalQueue.length > 0 && (
            <section className="rounded-xl border border-amber-200 bg-white p-5 shadow-sm sm:p-6">
              <div className="mb-4 flex items-center gap-2">
                <ClipboardCheck size={20} className="text-amber-600" />
                <h2 className="text-lg font-bold text-slate-900">
                  Approval Queue
                </h2>
                <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
                  {approvalQueue.length} pending
                </span>
              </div>

              <div className="space-y-3">
                {approvalQueue.map((task) => (
                  <div
                    key={task.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-100 p-4"
                  >
                    <div>
                      <p className="font-medium text-slate-800">{task.title}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {taskTypeLabels[task.type]} · Due {formatDate(task.due_at)}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => void decideApproval(task.id, false)}
                        className="rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-50"
                      >
                        Reject
                      </button>
                      <button
                        onClick={() => void decideApproval(task.id, true)}
                        className="rounded-lg bg-green-600 px-3 py-2 text-xs font-semibold text-white hover:bg-green-700"
                      >
                        Approve
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap gap-2">
                {["All", "Pending", "Completed"].map((item) => (
                  <button
                    key={item}
                    onClick={() => setFilter(item)}
                    className={`rounded-lg px-4 py-2 text-sm font-medium ${
                      filter === item
                        ? "bg-blue-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {item}
                  </button>
                ))}
              </div>

              <div className="relative w-full sm:max-w-xs">
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                  size={17}
                />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search tasks..."
                  className="w-full rounded-lg border border-slate-200 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>
            </div>

            <div className="mt-6 overflow-x-auto">
              <table className="w-full min-w-[650px] text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
                    <th className="pb-3 font-medium">Task</th>
                    <th className="pb-3 font-medium">Due date</th>
                    <th className="pb-3 font-medium">Type</th>
                    <th className="pb-3 font-medium">Approval</th>
                    <th className="pb-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTasks.map((task) => (
                    <tr
                      key={task.id}
                      className="border-b border-slate-100 last:border-0"
                    >
                      <td className="py-4">
                        <button
                          onClick={() => void toggleTask(task)}
                          disabled={
                            task.status === "done" ||
                            (task.requires_approval &&
                              task.approval_status !== "approved")
                          }
                          title={
                            task.requires_approval &&
                            task.approval_status !== "approved"
                              ? "This task needs approval before completion"
                              : "Mark task as completed"
                          }
                          className="flex items-center gap-3 text-left disabled:cursor-not-allowed"
                        >
                          {task.status === "done" ? (
                            <CheckCircle2
                              size={19}
                              className="shrink-0 text-green-600"
                            />
                          ) : (
                            <Circle
                              size={19}
                              className="shrink-0 text-slate-400"
                            />
                          )}
                          <span
                            className={
                              task.status === "done"
                                ? "text-slate-400 line-through"
                                : "font-medium text-slate-800"
                            }
                          >
                            {task.title}
                          </span>
                        </button>
                      </td>
                      <td className="py-4 text-slate-500">
                        {formatDate(task.due_at)}
                      </td>
                      <td className="py-4">
                        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                          {taskTypeLabels[task.type]}
                        </span>
                      </td>
                      <td className="py-4">
                        <span className="text-xs font-medium text-slate-600">
                          {task.approval_status === "not_required"
                            ? "Not required"
                            : task.approval_status}
                        </span>
                      </td>
                      <td className="py-4">
                        <span
                          className={`text-xs font-medium ${
                            task.status === "done"
                              ? "text-green-600"
                              : "text-blue-600"
                          }`}
                        >
                          {task.status === "done" ? "Completed" : task.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {loading && (
                <div className="py-12 text-center text-sm text-slate-500">
                  Loading tasks...
                </div>
              )}

              {!loading && filteredTasks.length === 0 && (
                <div className="flex min-h-64 flex-col items-center justify-center text-center">
                  <div className="rounded-full bg-slate-100 p-4">
                    <ListTodo size={28} className="text-slate-400" />
                  </div>
                  <h3 className="mt-4 font-semibold text-slate-700">
                    {search ? "No matching tasks" : "No tasks yet"}
                  </h3>
                  <p className="mt-1 text-sm text-slate-400">
                    {search
                      ? "Try another search term."
                      : "Create your first task to get started."}
                  </p>
                </div>
              )}
            </div>
          </section>
        </div>
      </main>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Create a task
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Add a new activity to your list.
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

            <form onSubmit={addTask} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Task title
                </label>
                <input
                  required
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="e.g. Follow up with a lead"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Lead ID
                </label>
                <input
                  required
                  value={leadId}
                  onChange={(event) => setLeadId(event.target.value)}
                  placeholder="Paste the lead UUID"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
                <p className="mt-1 text-xs text-slate-400">
                  Enter the ID of the lead this task belongs to.
                </p>
              </div>

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
                  Task type
                </label>
                <select
                  value={taskType}
                  onChange={(event) =>
                    setTaskType(event.target.value as TaskType)
                  }
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
                >
                  <option value="call">Call</option>
                  <option value="meeting">Meeting</option>
                  <option value="reminder">Reminder</option>
                  <option value="follow_up">Follow-up</option>
                </select>
              </div>

              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={requiresApproval}
                  onChange={(event) =>
                    setRequiresApproval(event.target.checked)
                  }
                  className="h-4 w-4 rounded border-slate-300"
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
                  disabled={saving}
                  className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? "Creating..." : "Create task"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
