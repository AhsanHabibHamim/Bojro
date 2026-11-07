import type { AdminSession } from "./types";

export function adminSessionDeadline(session: AdminSession | null): number | null {
  if (!session?.authenticated) return null;
  const deadlines = [session.idle_expires_at, session.absolute_expires_at]
    .map((value) => (value ? Date.parse(value) : Number.NaN))
    .filter(Number.isFinite);
  return deadlines.length ? Math.min(...deadlines) : null;
}
