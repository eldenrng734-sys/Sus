import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listMembers,
  inviteMember,
  changeMemberRole,
  deactivateMember,
  listTeams,
  createTeam,
  renameTeam,
  getAutomationSettings,
  updateAutomationSettings,
  type RoleType,
  type AutomationSettings,
} from "@/lib/api/settings";

export function useMembers() {
  return useQuery({
    queryKey: ["settings-members"],
    queryFn: () => listMembers(),
  });
}

export function useInviteMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { email: string; role: RoleType }) =>
      inviteMember(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["settings-members"] });
    },
  });
}

export function useChangeMemberRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      membershipId,
      role,
    }: {
      membershipId: string;
      role: RoleType;
    }) => changeMemberRole(membershipId, role),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["settings-members"] });
    },
  });
}

export function useDeactivateMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (membershipId: string) => deactivateMember(membershipId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["settings-members"] });
    },
  });
}

export function useTeams() {
  return useQuery({
    queryKey: ["settings-teams"],
    queryFn: () => listTeams(),
  });
}

export function useCreateTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (name: string) => createTeam(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["settings-teams"] });
    },
  });
}

export function useRenameTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ teamId, name }: { teamId: string; name: string }) =>
      renameTeam(teamId, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["settings-teams"] });
    },
  });
}

export function useAutomationSettings() {
  return useQuery({
    queryKey: ["settings-automation"],
    queryFn: () => getAutomationSettings(),
  });
}

export function useUpdateAutomationSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AutomationSettings) =>
      updateAutomationSettings(payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(["settings-automation"], updated);
    },
  });
}
