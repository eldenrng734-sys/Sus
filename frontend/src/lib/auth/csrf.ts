let csrfToken: string | null = null;

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;

  const prefix = `${name}=`;
  const parts = document.cookie.split(";");
  for (const rawPart of parts) {
    const part = rawPart.trim();
    if (part.startsWith(prefix)) {
      return decodeURIComponent(part.slice(prefix.length));
    }
  }
  return null;
}

export const csrfStore = {
  get(): string | null {
    return csrfToken ?? readCookie("csrf_token");
  },

  set(token: string | null): void {
    csrfToken = token;
  },

  clear(): void {
    csrfToken = null;
  },
};
