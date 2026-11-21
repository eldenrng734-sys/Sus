let csrfToken: string | null = null;

function readStorage(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return (
      sessionStorage.getItem("csrf_token") ??
      localStorage.getItem("csrf_token")
    );
  } catch {
    return null;
  }
}

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
    return csrfToken ?? readStorage() ?? readCookie("csrf_token");
  },

  set(token: string | null): void {
    csrfToken = token;
    if (typeof window !== "undefined") {
      try {
        if (token) {
          sessionStorage.setItem("csrf_token", token);
          localStorage.setItem("csrf_token", token);
        } else {
          sessionStorage.removeItem("csrf_token");
          localStorage.removeItem("csrf_token");
        }
      } catch {
        // ignore
      }
    }
  },

  clear(): void {
    csrfToken = null;
    if (typeof window !== "undefined") {
      try {
        sessionStorage.removeItem("csrf_token");
        localStorage.removeItem("csrf_token");
      } catch {
        // ignore
      }
    }
  },
};
