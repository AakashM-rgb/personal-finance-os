const PRIVACY_POINTS = [
  {
    title: "Your data, isolated",
    description: "Every account, transaction, budget, and goal is scoped to your own account - enforced at the database query level, not just hidden in the interface.",
  },
  {
    title: "Passwords never stored in plain text",
    description: "Passwords are hashed with Argon2id before they're ever saved. We can't see or recover your password.",
  },
  {
    title: "Sessions you control",
    description: "Sign out of one device or all of them at once. Refresh tokens rotate on use and are revoked if reuse is detected.",
  },
  {
    title: "Receipts stay private",
    description: "Uploaded receipts have no public link - every view or download is authenticated and checked against your account.",
  },
  {
    title: "AI access is restricted, not open-ended",
    description: "The AI assistant and natural-language search can only call a fixed set of read-only tools scoped to your data. Neither can execute arbitrary database queries.",
  },
  {
    title: "Offline data stays scoped to you",
    description: "Expenses saved while offline are stored on your device tied to your account, and never surface for a different signed-in user on the same device.",
  },
];

export function PrivacySection() {
  return (
    <section id="privacy" className="border-t border-zinc-100 bg-zinc-50/60 dark:border-zinc-900 dark:bg-zinc-900/20">
      <div className="mx-auto max-w-6xl px-6 py-20 sm:py-28">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold tracking-[0.2em] text-zinc-500 uppercase dark:text-zinc-500">
            Privacy
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl dark:text-zinc-50">
            Your financial data should stay yours.
          </h2>
          <p className="mt-4 text-base text-zinc-600 dark:text-zinc-400">
            No claims we can&apos;t back up - here&apos;s specifically what&apos;s in place today.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-x-8 gap-y-8 sm:grid-cols-2">
          {PRIVACY_POINTS.map((point) => (
            <div key={point.title} className="flex gap-3">
              <span
                className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                aria-hidden="true"
              >
                <svg viewBox="0 0 16 16" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M3 8.5l3 3 7-7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <div>
                <h3 className="font-medium text-zinc-900 dark:text-zinc-50">{point.title}</h3>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{point.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
