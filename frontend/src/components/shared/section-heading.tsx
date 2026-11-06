import { Lightning } from "@phosphor-icons/react/dist/ssr";

type SectionHeadingProps = {
  title: string;
  eyebrow?: string;
  description?: string;
  align?: "left" | "center";
  inverse?: boolean;
};

export function SectionHeading({
  title,
  eyebrow,
  description,
  align = "center",
  inverse = false,
}: SectionHeadingProps) {
  return (
    <div className={align === "center" ? "mx-auto max-w-3xl text-center" : "max-w-2xl"}>
      {eyebrow ? (
        <p
          className={`inline-flex items-center gap-2 text-sm font-extrabold tracking-[0.12em] uppercase ${inverse ? "text-soft-lavender" : "text-brand-purple"}`}
        >
          <Lightning aria-hidden size={19} weight="duotone" />
          {eyebrow}
        </p>
      ) : null}
      <h2
        className={`mt-2 text-[clamp(1.8rem,4.8vw,2.75rem)] font-extrabold ${inverse ? "text-white" : "text-deep-indigo"}`}
      >
        {title}
      </h2>
      <div
        aria-hidden
        className={`signature-gradient mt-4 h-1 w-16 rounded-full ${align === "center" ? "mx-auto" : ""}`}
      />
      {description ? (
        <p className={`mt-5 text-[1.02rem] leading-8 ${inverse ? "text-white/80" : "text-muted"}`}>
          {description}
        </p>
      ) : null}
    </div>
  );
}
