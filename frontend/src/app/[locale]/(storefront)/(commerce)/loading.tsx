export default function CommerceLoading() {
  return (
    <div className="container-shell py-14" role="status">
      <span className="sr-only">Loading</span>
      <div className="h-10 w-56 animate-pulse rounded-xl bg-soft-lavender" />
      <div className="mt-8 grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div className="h-96 animate-pulse rounded-3xl bg-soft-lavender" />
        <div className="h-72 animate-pulse rounded-3xl bg-soft-lavender" />
      </div>
    </div>
  );
}
