"use client";

import { useEffect, useState } from "react";

type CountdownProps = {
  endsAt: string;
  labels: { days: string; hours: string; minutes: string; seconds: string; ended: string };
};

export function Countdown({ endsAt, labels }: CountdownProps) {
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    const target = new Date(endsAt).getTime();
    const update = () => setRemaining(Math.max(0, target - Date.now()));
    update();
    const interval = window.setInterval(update, 1_000);
    return () => window.clearInterval(interval);
  }, [endsAt]);

  if (remaining === 0) {
    return (
      <p className="rounded-full bg-sale-amber px-4 py-2 font-extrabold text-deep-indigo">
        {labels.ended}
      </p>
    );
  }

  const seconds = remaining === null ? 0 : Math.floor(remaining / 1_000);
  const units = [
    { label: labels.days, value: Math.floor(seconds / 86_400) },
    { label: labels.hours, value: Math.floor((seconds % 86_400) / 3_600) },
    { label: labels.minutes, value: Math.floor((seconds % 3_600) / 60) },
    { label: labels.seconds, value: seconds % 60 },
  ];

  return (
    <div aria-live="off" className="flex gap-2" role="timer">
      {units.map((unit) => (
        <span
          key={unit.label}
          className="min-w-14 rounded-xl bg-deep-indigo px-2 py-2 text-center text-white shadow-sm"
        >
          <span className="block text-lg font-extrabold tabular-nums">
            {String(unit.value).padStart(2, "0")}
          </span>
          <span className="block text-[0.62rem] font-bold tracking-wide text-white/70 uppercase">
            {unit.label}
          </span>
        </span>
      ))}
    </div>
  );
}
