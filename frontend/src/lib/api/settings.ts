import { apiRequest } from "@/lib/api/client";

export type RoleType = "admin" | "manager" | "rep";

export interface TenantMember {
  id: string;
  membership_id?: string;
  email: string;
  display_name: string | null;
  role: RoleType;
  team_id: string | null;
  is_active: boolean;
  tenant_timezone?: string;
}

export interface Team {
  id: string;
  name: string;
  created_at?: string;
}

export interface AutomationSettings {
  timezone: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
}

export async function listMembers(): Promise<TenantMember[]> {
  const res = await apiRequest<{ data: TenantMember[] }>("/users");
  return res.data;
}

export async function inviteMember(payload: {
  email: string;
  role: RoleType;
}): Promise<unknown> {
  const res = await apiRequest<{ data: unknown }>("/invitations", {
    method: "POST",
    body: payload,
  });
  return res.data;
}

export async function changeMemberRole(
  membershipId: string,
  role: RoleType
): Promise<unknown> {
  const res = await apiRequest<{ data: unknown }>(
    `/memberships/${membershipId}/role`,
    {
      method: "PATCH",
      body: { role },
    }
  );
  return res.data;
}

export async function deactivateMember(membershipId: string): Promise<unknown> {
  const res = await apiRequest<{ data: unknown }>(
    `/memberships/${membershipId}/deactivate`,
    {
      method: "POST",
    }
  );
  return res.data;
}

export async function listTeams(): Promise<Team[]> {
  const res = await apiRequest<{ data: Team[] }>("/teams");
  return res.data;
}

export async function createTeam(name: string): Promise<Team> {
  const res = await apiRequest<{ data: Team }>("/teams", {
    method: "POST",
    body: { name },
  });
  return res.data;
}

export async function renameTeam(teamId: string, name: string): Promise<Team> {
  const res = await apiRequest<{ data: Team }>(`/teams/${teamId}`, {
    method: "PATCH",
    body: { name },
  });
  return res.data;
}

export async function getAutomationSettings(): Promise<AutomationSettings> {
  const res = await apiRequest<{ data: AutomationSettings }>(
    "/settings/automation"
  );
  return res.data;
}

export async function updateAutomationSettings(
  payload: AutomationSettings
): Promise<AutomationSettings> {
  const res = await apiRequest<{ data: AutomationSettings }>(
    "/settings/automation",
    {
      method: "PUT",
      body: payload,
    }
  );
  return res.data;
}
