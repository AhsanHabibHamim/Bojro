export type OtpDeadlines = {
  expiresAt: number;
  resendAt: number;
};

export function otpDeadlines(
  expiresInSeconds: number,
  resendAfterSeconds: number,
  now = Date.now(),
): OtpDeadlines {
  return {
    expiresAt: now + expiresInSeconds * 1_000,
    resendAt: now + resendAfterSeconds * 1_000,
  };
}

export function secondsUntil(deadline: number, now = Date.now()): number {
  return Math.max(0, Math.ceil((deadline - now) / 1_000));
}
