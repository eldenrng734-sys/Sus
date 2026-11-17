let selectedTenantId: string | null = null;

export const tenantStore = {
  get(): string | null {
    return selectedTenantId;
  },

  set(tenantId: string | null): void {
    selectedTenantId = tenantId;
  },

  clear(): void {
    selectedTenantId = null;
  },
};
