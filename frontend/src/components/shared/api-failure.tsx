import { WarningCircle } from "@phosphor-icons/react/dist/ssr";

type ApiFailureProps = {
  title: string;
  description: string;
  retryLabel: string;
  detail?: string;
};

export function ApiFailure({ title, description, retryLabel, detail }: ApiFailureProps) {
  return (
    <section className="container-shell py-16" role="alert">
      <div className="rounded-2xl border border-error/20 bg-white p-7 text-center shadow-soft sm:p-10">
        <WarningCircle aria-hidden className="mx-auto text-error" size={48} weight="duotone" />
        <h1 className="mt-4 text-2xl font-bold">{title}</h1>
        <p className="mx-auto mt-3 max-w-xl text-muted">{description}</p>
        {detail && process.env.NODE_ENV === "development" ? (
          <pre className="mx-auto mt-5 max-w-2xl overflow-x-auto rounded-xl bg-deep-indigo p-4 text-left text-xs whitespace-pre-wrap text-white">
            {detail}
          </pre>
        ) : null}
        <a
          className="signature-gradient mt-6 inline-flex rounded-full px-6 py-3 font-bold text-white"
          href=""
        >
          {retryLabel}
        </a>
      </div>
    </section>
  );
}
