let csrfToken: string | null = null;

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;

  const prefix = `${name}=`;
  const item = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith(prefix));

  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
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
