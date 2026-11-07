export const ADMIN_PAGE_SIZES = [25, 50, 100] as const;
export type AdminPageSize = (typeof ADMIN_PAGE_SIZES)[number];

export type AdminFilters = {
  q: string;
  sort: string;
  direction: "asc" | "desc";
  limit: AdminPageSize;
  cursor: string | null;
  status: string;
  from: string;
  to: string;
};

export function parseAdminFilters(
  search: Pick<URLSearchParams, "get">,
  defaults: Partial<AdminFilters> = {},
): AdminFilters {
  const parsedLimit = Number(search.get("limit"));
  const limit = ADMIN_PAGE_SIZES.includes(parsedLimit as AdminPageSize)
    ? (parsedLimit as AdminPageSize)
    : (defaults.limit ?? 25);
  return {
    q: (search.get("q") ?? defaults.q ?? "").slice(0, 100),
    sort: search.get("sort") ?? defaults.sort ?? "updated_at",
    direction: search.get("direction") === "asc" ? "asc" : (defaults.direction ?? "desc"),
    limit,
    cursor: search.get("cursor") || defaults.cursor || null,
    status: search.get("status") ?? defaults.status ?? "",
    from: search.get("from") ?? defaults.from ?? "",
    to: search.get("to") ?? defaults.to ?? "",
  };
}

export function updateAdminSearch(
  current: Pick<URLSearchParams, "toString">,
  updates: Record<string, string | number | null | undefined>,
): string {
  const next = new URLSearchParams(current.toString());
  Object.entries(updates).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") next.delete(key);
    else next.set(key, String(value));
  });
  if (!("cursor" in updates)) next.delete("cursor");
  if (!("cursor" in updates)) next.delete("cursor_stack");
  return next.toString();
}

export function parseCursorStack(value: string | null): string[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as unknown;
    return Array.isArray(parsed) &&
      parsed.length <= 100 &&
      parsed.every((item) => typeof item === "string")
      ? parsed
      : [];
  } catch {
    return [];
  }
}

export function serializeCursorStack(value: string[]): string {
  return JSON.stringify(value.slice(-100));
}

export function filtersToQuery(filters: AdminFilters): Record<string, string | number | undefined> {
  return {
    q: filters.q || undefined,
    sort: filters.sort,
    direction: filters.direction,
    limit: filters.limit,
    cursor: filters.cursor ?? undefined,
    status: filters.status || undefined,
    from: filters.from || undefined,
    to: filters.to || undefined,
  };
}
