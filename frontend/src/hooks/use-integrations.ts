import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getIntegrations,
  connectIntegration,
  disconnectIntegration,
  getPrimaryLeadForm,
  type ConnectIntegrationPayload,
  type IntegrationProvider,
} from "@/lib/api/integrations";

export function useIntegrations() {
  return useQuery({
    queryKey: ["integrations"],
    queryFn: () => getIntegrations(),
  });
}

export function useConnectIntegration() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      provider,
      data,
    }: {
      provider: IntegrationProvider;
      data: ConnectIntegrationPayload;
    }) => connectIntegration(provider, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["integrations"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
  });
}

export function useDisconnectIntegration() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (integrationId: string) =>
      disconnectIntegration(integrationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["integrations"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
  });
}

export function useLeadForm() {
  return useQuery({
    queryKey: ["primary-lead-form"],
    queryFn: () => getPrimaryLeadForm(),
  });
}
