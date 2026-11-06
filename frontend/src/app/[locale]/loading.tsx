import { LottieIcon } from "@/components/motion/lottie-icon";

export default function Loading() {
  return (
    <div className="container-shell grid min-h-[45vh] place-items-center py-16" role="status">
      <div className="text-center">
        <span className="mx-auto inline-flex rounded-full bg-soft-lavender p-5 text-brand-purple">
          <LottieIcon name="loader" size={44} />
        </span>
        <span className="sr-only">Loading</span>
      </div>
    </div>
  );
}
