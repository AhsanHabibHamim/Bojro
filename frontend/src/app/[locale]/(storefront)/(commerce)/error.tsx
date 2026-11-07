"use client";

export default function CommerceErrorBoundary({ reset }: { error: Error; reset: () => void }) {
  return (
    <div
      className="container-shell grid min-h-[55vh] place-content-center py-16 text-center"
      role="alert"
    >
      <h1 className="text-3xl font-extrabold">Something went wrong / কিছু একটা সমস্যা হয়েছে</h1>
      <p className="mt-3 text-muted">Your cart and form details remain protected.</p>
      <button
        className="signature-gradient mx-auto mt-6 min-h-12 rounded-full px-7 font-extrabold text-white"
        onClick={reset}
        type="button"
      >
        Try again / আবার চেষ্টা করুন
      </button>
    </div>
  );
}
