"use client";

import { useMemo, useState } from "react";
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
} from "lucide-react";

type Task = {
  id: number;
  title: string;
  dueDate: string;
  priority: "Low" | "Medium" | "High";
  completed: boolean;
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState("All");
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [priority, setPriority] = useState<Task["priority"]>("Medium");

  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const matchesSearch = task.title.toLowerCase().includes(search.toLowerCase());
      const matchesFilter =
        filter === "All" ||
        (filter === "Pending" && !task.completed) ||
        (filter === "Completed" && task.completed);

      return matchesSearch && matchesFilter;
    });
  }, [tasks, filter, search]);

  const pendingCount = tasks.filter((task) => !task.completed).length;
  const completedCount = tasks.filter((task) => task.completed).length;

  function addTask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!title.trim()) return;

    setTasks((current) => [
      ...current,
      {
        id: Date.now(),
        title: title.trim(),
        dueDate,
        priority,
        completed: false,
      },
    ]);

    setTitle("");
    setDueDate("");
    setPriority("Medium");
    setShowForm(false);
  }

  function toggleTask(id: number) {
    setTasks((current) =>
      current.map((task) =>
        task.id === id ? { ...task, completed: !task.completed } : task
      )
    );
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

            <button
              onClick={() => setShowForm(true)}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
            >
              <Plus size={18} />
              New Task
            </button>
          </section>

          <section className="grid gap-4 sm:grid-cols-3">
            {[
              { label: "Total Tasks", value: tasks.length, icon: ListTodo },
              { label: "Pending", value: pendingCount, icon: Clock },
              { label: "Completed", value: completedCount, icon: CheckCircle2 },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <article key={item.label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-slate-500">{item.label}</p>
                    <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                      <Icon size={19} />
                    </div>
                  </div>
                  <p className="mt-4 text-3xl font-bold text-slate-900">{item.value}</p>
                </article>
              );
            })}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6">
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
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search tasks..."
                  className="w-full rounded-lg border border-slate-200 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>
            </div>

            <div className="mt-6 overflow-x-auto">
              <table className="w-full min-w-[550px] text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
                    <th className="pb-3 font-medium">Task</th>
                    <th className="pb-3 font-medium">Due date</th>
                    <th className="pb-3 font-medium">Priority</th>
                    <th className="pb-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTasks.map((task) => (
                    <tr key={task.id} className="border-b border-slate-100 last:border-0">
                      <td className="py-4">
                        <button
                          onClick={() => toggleTask(task.id)}
                          className="flex items-center gap-3 text-left"
                        >
                          {task.completed ? (
                            <CheckCircle2 size={19} className="shrink-0 text-green-600" />
                          ) : (
                            <Circle size={19} className="shrink-0 text-slate-400" />
                          )}
                          <span className={task.completed ? "text-slate-400 line-through" : "font-medium text-slate-800"}>
                            {task.title}
                          </span>
                        </button>
                      </td>
                      <td className="py-4 text-slate-500">
                        {task.dueDate || "Not set"}
                      </td>
                      <td className="py-4">
                        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                          task.priority === "High"
                            ? "bg-red-50 text-red-700"
                            : task.priority === "Medium"
                              ? "bg-amber-50 text-amber-700"
                              : "bg-slate-100 text-slate-600"
                        }`}>
                          {task.priority}
                        </span>
                      </td>
                      <td className="py-4">
                        <span className={`text-xs font-medium ${task.completed ? "text-green-600" : "text-blue-600"}`}>
                          {task.completed ? "Completed" : "Pending"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {filteredTasks.length === 0 && (
                <div className="flex min-h-64 flex-col items-center justify-center text-center">
                  <div className="rounded-full bg-slate-100 p-4">
                    <ListTodo size={28} className="text-slate-400" />
                  </div>
                  <h3 className="mt-4 font-semibold text-slate-700">
                    {search ? "No matching tasks" : "No tasks yet"}
                  </h3>
                  <p className="mt-1 text-sm text-slate-400">
                    {search ? "Try another search term." : "Create your first task to get started."}
                  </p>
                  {!search && (
                    <button
                      onClick={() => setShowForm(true)}
                      className="mt-4 text-sm font-semibold text-blue-600 hover:text-blue-700"
                    >
                      + Create your first task
                    </button>
                  )}
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
                <h2 className="text-lg font-bold text-slate-900">Create a task</h2>
                <p className="mt-1 text-sm text-slate-500">Add a new activity to your list.</p>
              </div>
              <button onClick={() => setShowForm(false)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100" aria-label="Close form">
                <X size={20} />
              </button>
            </div>

            <form onSubmit={addTask} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">Task title</label>
                <input
                  required
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="e.g. Follow up with a lead"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">Due date</label>
                <div className="relative">
                  <CalendarDays className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
                  <input
                    type="date"
                    value={dueDate}
                    onChange={(event) => setDueDate(event.target.value)}
                    className="w-full rounded-lg border border-slate-200 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">Priority</label>
                <select
                  value={priority}
                  onChange={(event) => setPriority(event.target.value as Task["priority"])}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500"
                >
                  <option>Low</option>
                  <option>Medium</option>
                  <option>High</option>
                </select>
              </div>

              <div className="flex justify-end gap-3 pt-3">
                <button type="button" onClick={() => setShowForm(false)} className="rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Cancel
                </button>
                <button type="submit" className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700">
                  Create task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
