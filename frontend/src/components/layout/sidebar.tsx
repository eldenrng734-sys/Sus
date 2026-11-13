"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  CheckSquare,
  MessageSquare,
  Plug,
  Settings,
  LogOut,
  PanelLeftClose,
} from "lucide-react";
import { logout } from "@/lib/api/auth";

const navigation = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Leads", href: "/leads", icon: Users },
  { label: "Tasks", href: "/tasks", icon: CheckSquare },
  { label: "Conversations", href: "/conversations", icon: MessageSquare },
  { label: "Integrations", href: "/integrations", icon: Plug },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  async function handleLogout() {
    try {
      await logout();
    } finally {
      window.location.href = "/login";
    }
  }

  return (
    <aside className="flex min-h-screen w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex h-20 items-center gap-3 border-b border-slate-100 px-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 font-bold text-white">
          S
        </div>
        <div>
          <p className="text-lg font-bold tracking-wide text-slate-900">
            SYNTRIX
          </p>
          <p className="text-xs text-slate-500">AI Sales Assistant</p>
        </div>
      </div>

      <div className="px-4 pt-7">
        <p className="mb-3 px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Workspace
        </p>

        <nav className="space-y-1">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition ${
                  active
                    ? "bg-blue-50 text-blue-700"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                <Icon size={19} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="mt-auto border-t border-slate-100 p-4">
        <div className="mb-4 flex items-center gap-3 rounded-lg bg-slate-50 p-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700">
            U
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-800">
              Your workspace
            </p>
            <p className="text-xs text-slate-500">Sales team</p>
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium text-slate-600 transition hover:bg-red-50 hover:text-red-600"
        >
          <LogOut size={18} />
          Sign out
        </button>
      </div>
    </aside>
  );
}
