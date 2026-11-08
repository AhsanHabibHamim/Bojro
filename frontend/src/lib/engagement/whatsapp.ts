const bengaliDigits: Record<string, string> = {
  "০": "0",
  "১": "1",
  "২": "2",
  "৩": "3",
  "৪": "4",
  "৫": "5",
  "৬": "6",
  "৭": "7",
  "৮": "8",
  "৯": "9",
};

export function whatsappDigits(value: string): string | null {
  let digits = value.replace(/[০-৯]/g, (digit) => bengaliDigits[digit] ?? "").replace(/\D/g, "");
  if (digits.startsWith("00")) digits = digits.slice(2);
  if (/^01[3-9]\d{8}$/.test(digits)) digits = `88${digits}`;
  return /^\d{8,15}$/.test(digits) ? digits : null;
}

export function buildWhatsAppHref({
  enabled,
  phone,
  message,
}: {
  enabled: boolean;
  phone: string;
  message: string;
}): string | null {
  if (!enabled) return null;
  const digits = whatsappDigits(phone);
  const configuredMessage = message.trim().slice(0, 500);
  if (!digits || !configuredMessage) return null;
  return `https://wa.me/${digits}?text=${encodeURIComponent(configuredMessage)}`;
}
