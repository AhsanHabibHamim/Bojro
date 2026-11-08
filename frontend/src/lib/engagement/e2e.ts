export function isExplicitLocalEngagementMock(
  href: string,
  enabled = process.env.NEXT_PUBLIC_E2E_ENGAGEMENT_MOCK,
): boolean {
  if (enabled !== "1") return false;
  try {
    const host = new URL(href).hostname;
    return host === "localhost" || host === "127.0.0.1" || host === "::1";
  } catch {
    return false;
  }
}
