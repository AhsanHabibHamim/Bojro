import { LottieIcon } from "@/components/motion/lottie-icon";

type EmptyStateProps = {
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
};

export function EmptyState({ title, description, actionLabel, actionHref }: EmptyStateProps) {
  return (
    <div className="rounded-2xl border border-dashed border-brand-purple/25 bg-white px-5 py-14 text-center">
      <div className="mx-auto inline-flex rounded-full bg-soft-lavender p-4 text-brand-purple">
        <LottieIcon name="loader" size={42} />
      </div>
      <h2 className="mt-5 text-2xl font-bold">{title}</h2>
      <p className="mx-auto mt-2 max-w-lg text-muted">{description}</p>
      {actionLabel && actionHref ? (
        <a
          className="signature-gradient mt-6 inline-flex rounded-full px-6 py-3 font-bold text-white"
          href={actionHref}
        >
          {actionLabel}
        </a>
      ) : null}
    </div>
  );
}
