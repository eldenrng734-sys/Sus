let selectedTenantId: string | null = null;

function readStorage(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return sessionStorage.getItem("selected_tenant_id");
  } catch {
    return null;
  }
}

export const tenantStore = {
  get(): string | null {
    return selectedTenantId ?? readStorage();
  },

  set(tenantId: string | null): void {
    selectedTenantId = tenantId;
    if (typeof window !== "undefined") {
      try {
        if (tenantId) {
          sessionStorage.setItem("selected_tenant_id", tenantId);
        } else {
          sessionStorage.removeItem("selected_tenant_id");
        }
      } catch {
        // ignore
      }
    }
  },

  clear(): void {
    selectedTenantId = null;
    if (typeof window !== "undefined") {
      try {
        sessionStorage.removeItem("selected_tenant_id");
      } catch {
        // ignore
      }
    }
  },
};
