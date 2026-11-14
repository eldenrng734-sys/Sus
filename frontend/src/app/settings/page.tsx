"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import {
  User,
  Building2,
  Users,
  ShieldCheck,
  Bell,
  Save,
  Camera,
  Lock,
} from "lucide-react";

const sections = [
  { id: "profile", label: "My profile", icon: User },
  { id: "workspace", label: "Workspace", icon: Building2 },
  { id: "team", label: "Team members", icon: Users },
  { id: "security", label: "Security", icon: ShieldCheck },
  { id: "notifications", label: "Notifications", icon: Bell },
];

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState("profile");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [timezone, setTimezone] = useState("Asia/Dhaka");
  const [saved, setSaved] = useState(false);
  const [notifications, setNotifications] = useState({
    email: true,
    followups: true,
    leads: true,
    assignments: false,
  });

  function handleSave(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2500);
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">Workspace / Preferences</p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">Settings</h1>
          </div>
          <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
            Account settings
          </span>
        </header>

        <div className="mx-auto max-w-7xl space-y-7 p-5 sm:p-8">
          <section>
            <h2 className="text-2xl font-bold text-slate-900">Settings</h2>
            <p className="mt-1 text-sm text-slate-500">
              Manage your account, workspace and application preferences.
            </p>
          </section>

          <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
            <aside className="h-fit rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
              <nav className="flex gap-2 overflow-x-auto lg:flex-col">
                {sections.map((section) => {
                  const Icon = section.icon;
                  return (
                    <button
                      key={section.id}
                      type="button"
                      onClick={() => setActiveSection(section.id)}
                      className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-3 text-left text-sm font-medium transition ${
                        activeSection === section.id
                          ? "bg-blue-50 text-blue-700"
                          : "text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      <Icon size={18} />
                      {section.label}
                    </button>
                  );
                })}
              </nav>
            </aside>

            <section className="min-w-0 rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
              {activeSection === "profile" && (
                <form onSubmit={handleSave} className="space-y-6">
                  <div className="border-b border-slate-100 pb-5">
                    <h3 className="text-lg font-semibold text-slate-900">My profile</h3>
                    <p className="mt-1 text-sm text-slate-500">
                      Manage your personal account information.
                    </p>
                  </div>

                  <div className="flex items-center gap-4">
                    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-50 text-xl font-bold text-blue-700">
                      U
                    </div>
                    <div>
                      <p className="font-medium text-slate-800">Profile photo</p>
                      <p className="mt-1 text-xs text-slate-400">Profile photo upload will be available later.</p>
                      <button type="button" disabled className="mt-2 inline-flex cursor-not-allowed items-center gap-2 text-xs font-medium text-slate-400">
                        <Camera size={14} /> Change photo
                      </button>
                    </div>
                  </div>

                  <div className="grid gap-5 sm:grid-cols-2">
                    <div>
                      <label className="mb-1.5 block text-sm font-medium text-slate-700">Full name</label>
                      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Enter your name" className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500" />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-sm font-medium text-slate-700">Email address</label>
                      <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500" />
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5">
                    <p className="text-xs text-slate-400">Changes are currently local to this page.</p>
                    <button type="submit" className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700">
                      <Save size={16} /> Save changes
                    </button>
                  </div>
                  {saved && <p role="status" className="text-sm text-green-600">Form submitted. Backend persistence is not connected yet.</p>}
                </form>
              )}

              {activeSection === "workspace" && (
                <form onSubmit={handleSave} className="space-y-6">
                  <div className="border-b border-slate-100 pb-5">
                    <h3 className="text-lg font-semibold text-slate-900">Workspace settings</h3>
                    <p className="mt-1 text-sm text-slate-500">Configure your organization&apos;s workspace.</p>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-700">Workspace name</label>
                    <input value={workspace} onChange={(e) => setWorkspace(e.target.value)} placeholder="Enter workspace name" className="w-full max-w-lg rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500" />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-700">Timezone</label>
                    <select value={timezone} onChange={(e) => setTimezone(e.target.value)} className="w-full max-w-lg rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-500">
                      <option value="Asia/Dhaka">Asia/Dhaka (UTC+06:00)</option>
                      <option value="Asia/Kolkata">Asia/Kolkata (UTC+05:30)</option>
                      <option value="UTC">UTC</option>
                      <option value="Europe/London">Europe/London</option>
                      <option value="America/New_York">America/New York</option>
                    </select>
                  </div>
                  <div className="flex justify-end border-t border-slate-100 pt-5">
                    <button type="submit" className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"><Save size={16} /> Save changes</button>
                  </div>
                  {saved && <p role="status" className="text-sm text-green-600">Form submitted. Backend persistence is not connected yet.</p>}
                </form>
              )}

              {activeSection === "team" && (
                <div className="space-y-5">
                  <div className="border-b border-slate-100 pb-5">
                    <h3 className="text-lg font-semibold text-slate-900">Team members</h3>
                    <p className="mt-1 text-sm text-slate-500">Manage workspace members and their access.</p>
                  </div>
                  <div className="flex min-h-56 flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
                    <Users size={30} className="text-slate-300" />
                    <h4 className="mt-3 font-semibold text-slate-700">Team management</h4>
                    <p className="mt-1 max-w-sm text-sm text-slate-400">Team member records and invitations will appear here when the team API is connected.</p>
                  </div>
                  <div className="rounded-lg bg-blue-50 p-4 text-sm text-blue-800">
                    <p className="font-medium">Roles and permissions</p>
                    <p className="mt-1 text-xs leading-5 text-blue-700">Access control must be enforced by the backend. This page does not grant or change permissions.</p>
                  </div>
                </div>
              )}

              {activeSection === "security" && (
                <div className="space-y-5">
                  <div className="border-b border-slate-100 pb-5">
                    <h3 className="text-lg font-semibold text-slate-900">Security</h3>
                    <p className="mt-1 text-sm text-slate-500">Review account protection and security options.</p>
                  </div>
                  <div className="flex items-start gap-4 rounded-lg border border-slate-200 p-4">
                    <div className="rounded-lg bg-slate-100 p-2.5 text-slate-600"><Lock size={20} /></div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-slate-800">Password management</p>
                      <p className="mt-1 text-sm text-slate-500">Change your password securely through the account authentication service.</p>
                      <button type="button" disabled className="mt-3 cursor-not-allowed rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-400">Change password — unavailable</button>
                    </div>
                  </div>
                  <div className="rounded-lg bg-amber-50 p-4 text-sm text-amber-800">
                    <p className="font-medium">Security controls</p>
                    <p className="mt-1 text-xs leading-5">Session management, two-factor authentication and audit logs require backend support.</p>
                  </div>
                </div>
              )}

              {activeSection === "notifications" && (
                <div className="space-y-6">
                  <div className="border-b border-slate-100 pb-5">
                    <h3 className="text-lg font-semibold text-slate-900">Notifications</h3>
                    <p className="mt-1 text-sm text-slate-500">Choose which activities you want to be notified about.</p>
                  </div>
                  {[
                    { id: "email", label: "Email notifications", description: "Receive important updates through email." },
                    { id: "followups", label: "Follow-up reminders", description: "Get reminders about upcoming customer follow-ups." },
                    { id: "leads", label: "New lead notifications", description: "Get notified when new leads enter your workspace." },
                    { id: "assignments", label: "Task assignments", description: "Receive alerts when tasks are assigned to you." },
                  ].map((item) => (
                    <div key={item.id} className="flex items-center justify-between gap-4 border-b border-slate-100 pb-4">
                      <div>
                        <p className="text-sm font-medium text-slate-800">{item.label}</p>
                        <p className="mt-1 text-xs text-slate-500">{item.description}</p>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={notifications[item.id as keyof typeof notifications]}
                        onClick={() => setNotifications((current) => ({ ...current, [item.id]: !current[item.id as keyof typeof current] }))}
                        className={`relative h-6 w-11 shrink-0 rounded-full transition ${notifications[item.id as keyof typeof notifications] ? "bg-blue-600" : "bg-slate-300"}`}
                      >
                        <span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${notifications[item.id as keyof typeof notifications] ? "left-6" : "left-1"}`} />
                      </button>
                    </div>
                  ))}
                  <p className="text-xs text-slate-400">Notification preferences are currently held in page state and are not saved to the server.</p>
                </div>
              )}
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}

