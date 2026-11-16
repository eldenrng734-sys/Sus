
import { apiRequest } from "@/lib/api/client";

export type IntegrationProvider = "whatsapp" | "meta";

export type IntegrationStatus = "active" | "disabled" | "error";

export type IntegrationItem = {
  id: string;
  provider: IntegrationProvider;
  provider_account_id: string;
  status: IntegrationStatus;
  scopes: string[];
  created_at: string;
  connected: boolean;
};

export type ConnectIntegrationInput = {
  provider_account_id: string;
  access_token: string;
  waba_id?: string | null;
  scopes?: string[];
};

export type ConnectIntegrationResult = {
  connected: boolean;
  id: string;
  provider: IntegrationProvider;
  provider_account_id: string;
  status: IntegrationStatus;
  scopes: string[];
};

export type DisconnectIntegrationResult = {
  connected: boolean;
  id: string;
  status: IntegrationStatus;
};

type ApiResponse<T> = {
  data: T;
};

export async function listIntegrations(): Promise<IntegrationItem[]> {
  const response = await apiRequest<ApiResponse<IntegrationItem[]>>(
    "/integrations",
    { method: "GET" },
  );

  return response.data;
}

export async function connectIntegration(
  provider: IntegrationProvider,
  input: ConnectIntegrationInput,
): Promise<ConnectIntegrationResult> {
  const response = await apiRequest<ApiResponse<ConnectIntegrationResult>>(
    `/integrations/${provider}/connect`,
    {
      method: "POST",
      body: input,
      csrf: true,
      idempotencyKey: crypto.randomUUID(),
    },
  );

  return response.data;
}

export async function disconnectIntegration(
  integrationId: string,
): Promise<DisconnectIntegrationResult> {
  const response = await apiRequest<ApiResponse<DisconnectIntegrationResult>>(
    `/integrations/${integrationId}`,
    {
      method: "DELETE",
      csrf: true,
      idempotencyKey: crypto.randomUUID(),
    },
  );

  return response.data;
}
