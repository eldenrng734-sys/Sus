"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { RouteGuard } from "@/components/auth/route-guard";
import { useAuth } from "@/providers/auth-provider";
import {
  useMembers,
  useInviteMember,
  useChangeMemberRole,
  useDeactivateMember,
  useTeams,
  useCreateTeam,
  useRenameTeam,
  useAutomationSettings,
  useUpdateAutomationSettings,
} from "@/hooks/use-settings";
import {
  Users,
  Building2,
  Clock,
  Shield,
  UserPlus,
  Plus,
  Save,
  CheckCircle2,
  AlertTriangle,
  X,
  Edit2,
  Check,
} from "lucide-react";
import type { RoleType, TenantMember, Team } from "@/lib/api/settings";
import { parseApiError } from "@/lib/api-error";
import { ErrorBanner } from "@/components/shared/error-banner";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { DEFAULT_TIMEZONE } from "@/lib/format";

type SettingsTab = "users" | "teams" | "automation";

const TIMEZONE_OPTIONS = [
  { value: "Asia/Dhaka", label: "Asia/Dhaka (UTC+06:00)" },
  { value: "Asia/Kolkata", label: "Asia/Kolkata (UTC+05:30)" },
  { value: "Asia/Singapore", label: "Asia/Singapore (UTC+08:00)" },
  { value: "Asia/Dubai", label: "Asia/Dubai (UTC+04:00)" },
  { value: "Europe/London", label: "Europe/London (UTC+00:00 / +01:00)" },
  { value: "America/New_York", label: "America/New York (UTC-05:00 / -04:00)" },
  { value: "UTC", label: "UTC (Coordinated Universal Time)" },
];

export default function SettingsPage() {
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState<SettingsTab>("users");
  const [notice, setNotice] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<{
    title: string;
    message: string;
  } | null>(null);

  // Users tab state
  const {
    data: members = [],
    isLoading: isLoadingMembers,
    refetch: refetchMembers,
  } = useMembers();

  const inviteMemberMutation = useInviteMember();
  const changeRoleMutation = useChangeMemberRole();
  const deactivateMutation = useDeactivateMember();

  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<RoleType>("rep");

  // Deactivate confirmation modal
  const [deactivatingMember, setDeactivatingMember] = useState<TenantMember | null>(null);

  // Teams tab state
  const {
    data: teams = [],
    isLoading: isLoadingTeams,
    refetch: refetchTeams,
  } = useTeams();

  const createTeamMutation = useCreateTeam();
  const renameTeamMutation = useRenameTeam();

  const [showCreateTeamModal, setShowCreateTeamModal] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");

  const [editingTeamId, setEditingTeamId] = useState<string | null>(null);
  const [editingTeamName, setEditingTeamName] = useState("");

  // Automation tab state
  const {
    data: automationSettings,
    isLoading: isLoadingAutomation,
    refetch: refetchAutomation,
  } = useAutomationSettings();

  const updateAutomationMutation = useUpdateAutomationSettings();

  const [tz, setTz] = useState(DEFAULT_TIMEZONE);
  const [quietStart, setQuietStart] = useState("22:00");
  const [quietEnd, setQuietEnd] = useState("08:00");

  useEffect(() => {
    if (automationSettings) {
      setTz(automationSettings.timezone || DEFAULT_TIMEZONE);
      setQuietStart(automationSettings.quiet_hours_start || "22:00");
      setQuietEnd(automationSettings.quiet_hours_end || "08:00");
    }
  }, [automationSettings]);

  // Handlers: Users
  const handleInviteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;

    setErrorBanner(null);

    try {
      await inviteMemberMutation.mutateAsync({
        email: inviteEmail.trim().toLowerCase(),
        role: inviteRole,
      });
      setShowInviteModal(false);
      setInviteEmail("");
      setInviteRole("rep");
      setNotice(`Invitation sent to ${inviteEmail}.`);
      window.setTimeout(() => setNotice(null), 3500);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleChangeRole = async (member: TenantMember, newRole: RoleType) => {
    const membershipId = member.membership_id || member.id;
    if (!membershipId || member.role === newRole) return;

    setErrorBanner(null);

    try {
      await changeRoleMutation.mutateAsync({
        membershipId,
        role: newRole,
      });
      setNotice(`Updated role for ${member.display_name || member.email} to ${newRole}.`);
      window.setTimeout(() => setNotice(null), 3500);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleConfirmDeactivate = async () => {
    if (!deactivatingMember) return;
    const membershipId = deactivatingMember.membership_id || deactivatingMember.id;

    setErrorBanner(null);

    try {
      await deactivateMutation.mutateAsync(membershipId);
      setNotice(`Member ${deactivatingMember.display_name || deactivatingMember.email} deactivated.`);
      setDeactivatingMember(null);
      window.setTimeout(() => setNotice(null), 3500);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  // Handlers: Teams
  const handleCreateTeamSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTeamName.trim()) return;

    setErrorBanner(null);

    try {
      await createTeamMutation.mutateAsync(newTeamName.trim());
      setShowCreateTeamModal(false);
      setNewTeamName("");
      setNotice("Team created successfully.");
      window.setTimeout(() => setNotice(null), 3500);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleRenameTeamSubmit = async (teamId: string) => {
    if (!editingTeamName.trim()) return;

    setErrorBanner(null);

    try {
      await renameTeamMutation.mutateAsync({
        teamId,
        name: editingTeamName.trim(),
      });
      setEditingTeamId(null);
      setEditingTeamName("");
      setNotice("Team renamed successfully.");
      window.setTimeout(() => setNotice(null), 3500);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  // Handlers: Automation
  const handleSaveAutomation = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorBanner(null);

    try {
      await updateAutomationMutation.mutateAsync({
        timezone: tz,
        quiet_hours_start: quietStart,
        quiet_hours_end: quietEnd,
      });
      setNotice("Automation settings and quiet hours updated.");
      window.setTimeout(() => setNotice(null), 3500);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleRefresh = async () => {
    setErrorBanner(null);
    if (activeTab === "users") await refetchMembers();
    else if (activeTab === "teams") await refetchTeams();
    else if (activeTab === "automation") await refetchAutomation();
  };

  return (
    <RouteGuard allowedRoles={["admin"]}>
      <div className="flex min-h-screen bg-slate-50">
        <Sidebar />

        <main className="min-w-0 flex-1">
          {/* Header */}
          <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8">
            <div>
              <p className="text-sm text-slate-500">Workspace / Configuration</p>
              <h1 className="mt-1 text-xl font-bold text-slate-900">
                Workspace Settings
              </h1>
            </div>

            {/* Current Role Badge */}
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-purple-200 bg-purple-50 px-3 py-1 text-xs font-bold text-purple-700">
                <Shield size={13} />
                ADMIN ROLE
              </span>
            </div>
          </header>

          <div className="mx-auto max-w-7xl space-y-6 p-5 sm:p-8">
            {/* Notices */}
            {errorBanner && (
              <ErrorBanner
                title={errorBanner.title}
                message={errorBanner.message}
                onDismiss={() => setErrorBanner(null)}
                onRetry={() => void handleRefresh()}
              />
            )}

            {notice && (
              <div className="flex items-center justify-between rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={16} />
                  <span>{notice}</span>
                </div>
                <button
                  onClick={() => setNotice(null)}
                  className="text-green-600 hover:text-green-800"
                >
                  <X size={15} />
                </button>
              </div>
            )}

            {/* Tab Navigation */}
            <div className="flex border-b border-slate-200">
              {[
                { id: "users", label: "Users & Access", icon: Users, count: members.length },
                { id: "teams", label: "Teams", icon: Building2, count: teams.length },
                { id: "automation", label: "Automation & Quiet Hours", icon: Clock },
              ].map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;

                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as SettingsTab)}
                    className={`inline-flex items-center gap-2 border-b-2 px-5 py-3.5 text-sm font-semibold transition ${
                      isActive
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800"
                    }`}
                  >
                    <Icon size={17} />
                    <span>{tab.label}</span>
                    {tab.count !== undefined && (
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs ${
                          isActive
                            ? "bg-blue-100 text-blue-700 font-bold"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {tab.count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Tab 1: Users & Access */}
            {activeTab === "users" && (
              <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-5">
                  <div>
                    <h2 className="text-base font-bold text-slate-900">
                      Workspace Members
                    </h2>
                    <p className="mt-0.5 text-xs text-slate-500">
                      Manage team member roles, invite new colleagues, or revoke access.
                    </p>
                  </div>

                  <button
                    onClick={() => setShowInviteModal(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-2 text-xs font-semibold text-white shadow-xs hover:bg-blue-700"
                  >
                    <UserPlus size={15} />
                    Invite Member
                  </button>
                </div>

                <div className="mt-4 overflow-x-auto">
                  {isLoadingMembers ? (
                    <div className="py-12 text-center">
                      <LoadingSpinner size="md" message="Loading workspace members..." />
                    </div>
                  ) : members.length === 0 ? (
                    <p className="py-8 text-center text-xs text-slate-400">
                      No members found in this tenant.
                    </p>
                  ) : (
                    <table className="w-full min-w-[650px] text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-100 text-[11px] uppercase tracking-wider text-slate-400">
                          <th className="pb-3 font-medium">Member</th>
                          <th className="pb-3 font-medium">Role</th>
                          <th className="pb-3 font-medium">Status</th>
                          <th className="pb-3 font-medium text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {members.map((m) => {
                          const isCurrentUser = m.email === user?.email;

                          return (
                            <tr key={m.id} className="hover:bg-slate-50/60 transition">
                              <td className="py-3.5 pr-4">
                                <div className="flex items-center gap-3">
                                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-700">
                                    {(m.display_name || m.email).charAt(0).toUpperCase()}
                                  </div>
                                  <div>
                                    <div className="flex items-center gap-1.5">
                                      <span className="font-semibold text-slate-900">
                                        {m.display_name || "Unnamed"}
                                      </span>
                                      {isCurrentUser && (
                                        <span className="rounded bg-blue-100 px-1.5 py-0.2 text-[10px] font-bold text-blue-800">
                                          You
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-slate-400">{m.email}</p>
                                  </div>
                                </div>
                              </td>

                              <td className="py-3.5">
                                <select
                                  value={m.role}
                                  disabled={
                                    isCurrentUser || changeRoleMutation.isPending
                                  }
                                  onChange={(e) =>
                                    void handleChangeRole(
                                      m,
                                      e.target.value as RoleType
                                    )
                                  }
                                  className={`rounded-lg border px-2.5 py-1 text-xs font-bold capitalize transition outline-none ${
                                    m.role === "admin"
                                      ? "border-purple-200 bg-purple-50 text-purple-700"
                                      : m.role === "manager"
                                      ? "border-blue-200 bg-blue-50 text-blue-700"
                                      : "border-slate-200 bg-slate-50 text-slate-700"
                                  } ${isCurrentUser ? "cursor-not-allowed opacity-80" : ""}`}
                                >
                                  <option value="rep">Rep</option>
                                  <option value="manager">Manager</option>
                                  <option value="admin">Admin</option>
                                </select>
                              </td>

                              <td className="py-3.5">
                                {m.is_active ? (
                                  <span className="inline-flex items-center gap-1 text-green-700 font-semibold">
                                    <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                                    Active
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 text-slate-400">
                                    <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
                                    Inactive
                                  </span>
                                )}
                              </td>

                              <td className="py-3.5 text-right">
                                {!isCurrentUser && m.is_active && (
                                  <button
                                    onClick={() => setDeactivatingMember(m)}
                                    className="rounded-lg border border-red-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-red-600 hover:bg-red-50 transition"
                                  >
                                    Deactivate
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </section>
            )}

            {/* Tab 2: Teams */}
            {activeTab === "teams" && (
              <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-5">
                  <div>
                    <h2 className="text-base font-bold text-slate-900">
                      Teams & Departments
                    </h2>
                    <p className="mt-0.5 text-xs text-slate-500">
                      Organize sales representatives into regional or specialized teams for routing and auto-assignment.
                    </p>
                  </div>

                  <button
                    onClick={() => setShowCreateTeamModal(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-2 text-xs font-semibold text-white shadow-xs hover:bg-blue-700"
                  >
                    <Plus size={15} />
                    Create Team
                  </button>
                </div>

                <div className="mt-4 overflow-x-auto">
                  {isLoadingTeams ? (
                    <div className="py-12 text-center">
                      <LoadingSpinner size="md" message="Loading teams..." />
                    </div>
                  ) : teams.length === 0 ? (
                    <div className="py-12 text-center text-xs text-slate-400">
                      <Building2 size={28} className="mx-auto text-slate-300 mb-2" />
                      No teams created yet. Create your first team above.
                    </div>
                  ) : (
                    <table className="w-full min-w-[550px] text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-100 text-[11px] uppercase tracking-wider text-slate-400">
                          <th className="pb-3 font-medium">Team Name</th>
                          <th className="pb-3 font-medium">Team UUID</th>
                          <th className="pb-3 font-medium text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {teams.map((t: Team) => {
                          const isEditing = editingTeamId === t.id;

                          return (
                            <tr key={t.id} className="hover:bg-slate-50/60 transition">
                              <td className="py-3.5 pr-4">
                                {isEditing ? (
                                  <div className="flex items-center gap-2">
                                    <input
                                      value={editingTeamName}
                                      onChange={(e) => setEditingTeamName(e.target.value)}
                                      className="rounded-lg border border-blue-500 px-2 py-1 text-xs outline-none"
                                    />
                                    <button
                                      onClick={() => void handleRenameTeamSubmit(t.id)}
                                      className="rounded bg-blue-600 p-1 text-white hover:bg-blue-700"
                                    >
                                      <Check size={13} />
                                    </button>
                                    <button
                                      onClick={() => setEditingTeamId(null)}
                                      className="rounded border border-slate-200 p-1 text-slate-500 hover:bg-slate-50"
                                    >
                                      <X size={13} />
                                    </button>
                                  </div>
                                ) : (
                                  <span className="font-semibold text-slate-900">
                                    {t.name}
                                  </span>
                                )}
                              </td>

                              <td className="py-3.5 font-mono text-slate-400 text-[11px]">
                                {t.id}
                              </td>

                              <td className="py-3.5 text-right">
                                {!isEditing && (
                                  <button
                                    onClick={() => {
                                      setEditingTeamId(t.id);
                                      setEditingTeamName(t.name);
                                    }}
                                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
                                  >
                                    <Edit2 size={11} />
                                    Rename
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </section>
            )}

            {/* Tab 3: Automation & Quiet Hours */}
            {activeTab === "automation" && (
              <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="border-b border-slate-100 pb-5">
                  <h2 className="text-base font-bold text-slate-900">
                    Automation & Quiet Hours
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Control workspace business timezone and define quiet hours during which automated customer outreach is held.
                  </p>
                </div>

                {isLoadingAutomation ? (
                  <div className="py-12 text-center">
                    <LoadingSpinner size="md" message="Loading automation settings..." />
                  </div>
                ) : (
                  <form onSubmit={handleSaveAutomation} className="mt-6 space-y-6 max-w-xl">
                    {/* Timezone */}
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                        Tenant Business Timezone
                      </label>
                      <select
                        value={tz}
                        onChange={(e) => setTz(e.target.value)}
                        className="w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs outline-none focus:border-blue-500"
                      >
                        {TIMEZONE_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                      <p className="mt-1 text-[11px] text-slate-400">
                        All task due dates and quiet-hour window checks are evaluated against this timezone.
                      </p>
                    </div>

                    {/* Quiet Hours */}
                    <div className="rounded-2xl border border-slate-100 bg-slate-50/70 p-4 space-y-4">
                      <div>
                        <h3 className="text-xs font-bold text-slate-900">
                          Automated Messaging Quiet Hours
                        </h3>
                        <p className="mt-0.5 text-[11px] text-slate-500">
                          During this window, automated messages (such as follow-up WhatsApp notifications) are held and rescheduled to the end of quiet hours.
                        </p>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            Quiet Hours Start
                          </label>
                          <input
                            type="time"
                            value={quietStart}
                            onChange={(e) => setQuietStart(e.target.value)}
                            required
                            className="w-full rounded-lg border border-slate-200 bg-white p-2 text-xs outline-none focus:border-blue-500"
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            Quiet Hours End
                          </label>
                          <input
                            type="time"
                            value={quietEnd}
                            onChange={(e) => setQuietEnd(e.target.value)}
                            required
                            className="w-full rounded-lg border border-slate-200 bg-white p-2 text-xs outline-none focus:border-blue-500"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="flex justify-end pt-2">
                      <button
                        type="submit"
                        disabled={updateAutomationMutation.isPending}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-blue-700 disabled:opacity-50"
                      >
                        <Save size={14} />
                        {updateAutomationMutation.isPending
                          ? "Saving..."
                          : "Save Automation Settings"}
                      </button>
                    </div>
                  </form>
                )}
              </section>
            )}
          </div>
        </main>

        {/* Invite Member Modal */}
        {showInviteModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <h3 className="text-base font-bold text-slate-900">
                  Invite Workspace Member
                </h3>
                <button
                  onClick={() => setShowInviteModal(false)}
                  className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleInviteSubmit} className="mt-4 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Email Address
                  </label>
                  <input
                    type="email"
                    required
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="colleague@company.com"
                    className="w-full rounded-xl border border-slate-200 p-2.5 text-xs outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Assigned Role
                  </label>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value as RoleType)}
                    className="w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs outline-none focus:border-blue-500"
                  >
                    <option value="rep">Representative (Rep)</option>
                    <option value="manager">Manager</option>
                    <option value="admin">Administrator (Admin)</option>
                  </select>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setShowInviteModal(false)}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={inviteMemberMutation.isPending || !inviteEmail.trim()}
                    className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {inviteMemberMutation.isPending
                      ? "Sending Invitation..."
                      : "Send Invitation"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Deactivation Confirmation Modal */}
        {deactivatingMember && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
              <div className="flex items-center gap-2 text-red-600">
                <AlertTriangle size={20} />
                <h3 className="text-base font-bold text-slate-900">
                  Confirm Member Deactivation
                </h3>
              </div>

              <p className="mt-3 text-xs text-slate-600 leading-relaxed">
                Are you sure you want to deactivate{" "}
                <span className="font-bold text-slate-900">
                  {deactivatingMember.display_name || deactivatingMember.email}
                </span>
                ? They will immediately lose access to this workspace and all their active login sessions will be revoked.
              </p>

              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setDeactivatingMember(null)}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={deactivateMutation.isPending}
                  onClick={() => void handleConfirmDeactivate()}
                  className="rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {deactivateMutation.isPending
                    ? "Deactivating..."
                    : "Confirm Deactivation"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Create Team Modal */}
        {showCreateTeamModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <h3 className="text-base font-bold text-slate-900">
                  Create New Team
                </h3>
                <button
                  onClick={() => setShowCreateTeamModal(false)}
                  className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleCreateTeamSubmit} className="mt-4 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Team Name
                  </label>
                  <input
                    required
                    value={newTeamName}
                    onChange={(e) => setNewTeamName(e.target.value)}
                    placeholder="e.g. Enterprise Sales East"
                    className="w-full rounded-xl border border-slate-200 p-2.5 text-xs outline-none focus:border-blue-500"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setShowCreateTeamModal(false)}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createTeamMutation.isPending || !newTeamName.trim()}
                    className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {createTeamMutation.isPending ? "Creating..." : "Create Team"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </RouteGuard>
  );
}
