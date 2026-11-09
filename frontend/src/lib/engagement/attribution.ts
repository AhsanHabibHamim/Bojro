function analyticsCookie(name: "_fbp" | "_fbc"): string | undefined {
  if (typeof document === "undefined") return undefined;
  const prefix = `${name}=`;
  const value = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix))
    ?.slice(prefix.length);
  const valid =
    name === "_fbp"
      ? /^fb\.1\.[0-9]+\.[0-9]+$/.test(value ?? "")
      : /^fb\.1\.[0-9]+\.[A-Za-z0-9_-]+$/.test(value ?? "");
  return value && value.length <= 255 && valid ? value : undefined;
}

export function metaAttributionCookies(): { fbp?: string; fbc?: string } {
  return { fbp: analyticsCookie("_fbp"), fbc: analyticsCookie("_fbc") };
}
