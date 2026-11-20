/**
 * Shared formatting utilities for tenant-aware date/time display.
 * Previously these lived in @/hooks/use-tasks — moved here so non-hook
 * files (pages, plain components) can import them without breaking the
 * Rules of Hooks.
 */

/** The workspace default timezone used when the tenant setting is unavailable. */
export const DEFAULT_TIMEZONE = "Asia/Dhaka";

/**
 * Format an ISO 8601 string in the tenant's configured timezone.
 * Falls back to the browser's locale if the timezone string is invalid.
 *
 * @param isoString - e.g. "2026-11-20T15:30:00Z"
 * @param timezone  - e.g. "Asia/Dhaka" (from useAuth().timezone)
 * @returns Human-readable string like "Nov 20, 2026, 9:30 PM"
 */
export function formatTenantDateTime(
  isoString: string,
  timezone: string
): string {
  try {
    const date = new Date(isoString);
    return new Intl.DateTimeFormat("en-US", {
      timeZone: timezone || DEFAULT_TIMEZONE,
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }).format(date);
  } catch {
    // Invalid timezone string — fall back to browser locale
    return new Date(isoString).toLocaleDateString();
  }
}

/**
 * Returns today's date string (YYYY-MM-DD) as seen in the tenant timezone.
 * Used for task bucket comparison (today / overdue / upcoming).
 */
export function getTenantTodayString(timezone: string): string {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone || DEFAULT_TIMEZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  } catch {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: DEFAULT_TIMEZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  }
}

/**
 * Returns the date portion (YYYY-MM-DD) of an ISO string in the tenant timezone.
 */
export function getTenantDateString(
  isoString: string,
  timezone: string
): string {
  try {
    const date = new Date(isoString);
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone || DEFAULT_TIMEZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  } catch {
    return isoString.slice(0, 10);
  }
}

/**
 * Builds an ISO 8601 timestamp from a date string + time string, interpreting
 * them as wall-clock time in the given tenant timezone (not the browser's local
 * timezone). This prevents tasks from being scheduled at the wrong UTC offset
 * when the user's browser timezone differs from the tenant workspace timezone.
 *
 * @param dateStr  - "YYYY-MM-DD" from an <input type="date">
 * @param timeStr  - "HH:MM" from an <input type="time">, defaults to "09:00"
 * @param timezone - Tenant timezone (e.g. "Asia/Dhaka")
 * @returns UTC ISO string ready to send to the backend
 */
export function buildTenantDateTime(
  dateStr: string,
  timeStr: string,
  timezone: string
): string {
  const time = timeStr || "09:00";
  // Construct a local datetime string with seconds
  const localStr = `${dateStr}T${time}:00`;

  // Use Intl to find the UTC offset for this wall-clock moment in the tenant tz
  const tz = timezone || DEFAULT_TIMEZONE;

  // Parse the naive datetime as if it were in the tenant timezone by computing
  // the offset difference. We do this without a third-party library by using
  // a trick: format a known UTC date in the target timezone and compare.
  const naiveMs = new Date(localStr).getTime(); // treated as local by JS

  // Get what JS's local timezone thinks the UTC offset is for this moment
  const localOffset = new Date(localStr).getTimezoneOffset() * 60_000; // ms

  // Get what the tenant timezone's offset is for this moment (approximation)
  // by formatting a UTC candidate and reading back the parts
  try {
    // Build a Date that represents the wall-clock time in the tenant timezone
    // Strategy: format an arbitrary Date in the tenant tz, compare to target
    const utcCandidate = new Date(localStr + "Z"); // treat as UTC for formatting
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).formatToParts(utcCandidate);

    const get = (type: string) =>
      parts.find((p) => p.type === type)?.value ?? "00";

    // The tenant-tz wall-clock representation of utcCandidate
    const tenantStr = `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}:${get("second")}`;
    const tenantMs = new Date(tenantStr).getTime(); // naive parse

    // Offset = (UTC candidate as naive) - (its tenant-tz representation as naive)
    const tenantOffset = naiveMs - tenantMs; // ms to add to naive to get UTC

    // Unused localOffset to avoid TS unused-variable warning
    void localOffset;

    const utcMs = naiveMs + tenantOffset;
    return new Date(utcMs).toISOString();
  } catch {
    // Fallback: treat the input as browser-local time (old behavior)
    return new Date(localStr).toISOString();
  }
}
