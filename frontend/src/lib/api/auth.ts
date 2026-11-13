import { apiRequest } from "@/lib/api/client";
import { tokenStore } from "@/lib/auth/token-store";
import { csrfStore } from "@/lib/auth/csrf";
import { tenantStore } from "@/lib/auth/tenant";

type Membership = {
  tenant_id: string;
  tenant_name: string;
  role: "rep" | "manager" | "admin" | "platform_admin";
  team_id: string | null;
  is_active: boolean;
};

type User = {
  id: string;
  email: string;
  full_name: string;
  email_verified: boolean;
};

type AuthSession = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  csrf_token: string;
  user: User;
  memberships: Membership[];
};

type LoginResult =
  | AuthSession
  | {
      mfa_required: true;
      challenge_token: string;
      expires_in: number;
    }
  | {
      mfa_setup_required: true;
      setup_token: string;
      expires_in: number;
    };

type LoginInput = {
  email: string;
  password: string;
};

type MfaVerifyInput = {
  challenge_token: string;
  code: string;
};

type MeResponse = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  mfa_enabled: boolean;
  memberships: Membership[];
};

function saveSession(session: AuthSession): void {
  tokenStore.set(session.access_token);
  csrfStore.set(session.csrf_token);

  const activeMembership = session.memberships.find(
    (membership) => membership.is_active,
  );

  tenantStore.set(activeMembership?.tenant_id ?? null);
}

export async function login(input: LoginInput): Promise<LoginResult> {
  const response = await apiRequest<{ data: LoginResult }>("/auth/login", {
    method: "POST",
    body: input,
    auth: false,
    tenantScoped: false,
  });

  if ("access_token" in response.data) {
    saveSession(response.data);
  }

  return response.data;
}

export async function verifyMfa(
  input: MfaVerifyInput,
): Promise<AuthSession> {
  const response = await apiRequest<{ data: AuthSession }>(
    "/auth/mfa/verify",
    {
      method: "POST",
      body: input,
      auth: false,
      tenantScoped: false,
    },
  );

  saveSession(response.data);
  return response.data;
}

export async function getCurrentUser(): Promise<MeResponse> {
  const response = await apiRequest<{ data: MeResponse }>("/auth/me", {
    method: "GET",
    auth: true,
    tenantScoped: false,
  });

  return response.data;
}

export async function logout(): Promise<void> {
  try {
    await apiRequest<void>("/auth/logout", {
      method: "POST",
      auth: false,
      tenantScoped: false,
      csrf: true,
    });
  } finally {
    tokenStore.clear();
    csrfStore.clear();
    tenantStore.clear();
  }
}

export function selectTenant(tenantId: string): void {
  tenantStore.set(tenantId);
}

export function clearAuthSession(): void {
  tokenStore.clear();
  csrfStore.clear();
  tenantStore.clear();
}
