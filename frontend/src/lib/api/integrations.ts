/**
 * Integrations API Client.
 *
 * All credentials (access tokens, API keys) are strictly write-only:
 * they are transmitted over HTTPS / same-origin proxy, encrypted with AES-256-GCM
 * at the backend, and never returned in GET responses or stored in browser state.
 */

import { apiRequest } from "@/lib/api/client";

export type IntegrationProvider = "whatsapp" | "meta";

export interface IntegrationItem {
  id: string;
  provider: IntegrationProvider;
  provider_account_id: string;
  status: "active" | "disabled" | "error";
  scopes: string[];
  created_at: string;
  connected: boolean;
}

export interface ConnectIntegrationPayload {
  provider_account_id: string;
  access_token: string;
  waba_id?: string;
  scopes?: string[];
}

export interface LeadFormInfo {
  id: string;
  public_id: string;
  name: string;
  allowed_fields: string[];
  consent_text: string | null;
  is_active: boolean;
  embed_code: string;
  endpoint_url: string;
}

export async function getIntegrations(): Promise<IntegrationItem[]> {
  const resp = await apiRequest<{ data: IntegrationItem[] }>("/integrations");
  return resp.data;
}

export async function connectIntegration(
  provider: IntegrationProvider,
  data: ConnectIntegrationPayload
): Promise<IntegrationItem> {
  const resp = await apiRequest<{ data: IntegrationItem }>(
    `/integrations/${provider}/connect`,
    {
      method: "POST",
      body: data,
    }
  );
  return resp.data;
}

export async function disconnectIntegration(
  integrationId: string
): Promise<{ connected: boolean; id: string; status: string }> {
  const resp = await apiRequest<{
    data: { connected: boolean; id: string; status: string };
  }>(`/integrations/${integrationId}`, {
    method: "DELETE",
  });
  return resp.data;
}

export async function getPrimaryLeadForm(): Promise<LeadFormInfo> {
  const resp = await apiRequest<{ data: LeadFormInfo }>("/lead-forms/primary");
  return resp.data;
}
