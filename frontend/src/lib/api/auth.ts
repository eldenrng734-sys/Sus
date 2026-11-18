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
      mfa_setup_required: false;
      challenge: string;
    }
  | {
      mfa_required: false;
      mfa_setup_required: true;
      challenge: string;
    };

type LoginInput = {
  email: string;
  password: string;
};

type MfaCodeInput = {
  challenge: string;
  code: string;
};

export type MfaEnrollment = {
  secret: string;
  otpauth_uri: string;
};

type MfaEnrollmentSession = AuthSession & {
  recovery_codes: string[];
};

export type CurrentUser = {
  id: string;
  email: string;
  display_name: string;
  role: "rep" | "manager" | "admin";
  team_id: string | null;
  is_active: boolean;
  tenant_timezone: string;
};

export type MeResponse = CurrentUser;

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
  input: MfaCodeInput,
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

export async function startMfaEnrollment(
  challenge: string,
): Promise<MfaEnrollment> {
  const response = await apiRequest<{ data: MfaEnrollment }>("/auth/mfa/setup", {
    method: "POST",
    body: { challenge },
    auth: false,
    tenantScoped: false,
  });

  return response.data;
}

export async function confirmMfaEnrollment(
  input: MfaCodeInput,
): Promise<MfaEnrollmentSession> {
  const response = await apiRequest<{ data: MfaEnrollmentSession }>(
    "/auth/mfa/confirm",
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
  const response = await apiRequest<{ data: MeResponse }>("/users/me", {
    method: "GET",
    auth: true,
    tenantScoped: Boolean(tenantStore.get()),
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
