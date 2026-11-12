import Link from "next/link";

interface ErrorFallbackProps {
  title: string;
  message: string;
  onRetry: () => void;
  homeHref: string;
  homeLabel: string;
  /** Next.js's server-log correlation id - shown so a user can quote it, never the raw error. */
  digest?: string;
}

/**
 * The shared fallback UI for the route-level error boundaries (app/error.tsx,
 * app/(app)/error.tsx, app/global-error.tsx). It deliberately never renders
 * the thrown error's `message`: a render-time exception can carry internal
 * detail (a stack-derived string, a malformed payload fragment), and
 * CLAUDE.md §17 forbids surfacing raw exceptions to the user.
 */
export function ErrorFallback({
  title,
  message,
  onRetry,
  homeHref,
  homeLabel,
  digest,
}: ErrorFallbackProps) {
  return (
    <div
      role="alert"
      className="mx-auto flex w-full max-w-md flex-col items-center gap-4 rounded-xl border border-red-200 bg-red-50 p-8 text-center dark:border-red-900 dark:bg-red-950"
    >
      <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">{title}</h1>
      <p className="text-sm text-red-700 dark:text-red-400">{message}</p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex h-10 items-center justify-center rounded-md bg-zinc-900 px-4 text-sm font-medium text-white hover:bg-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 focus-visible:ring-offset-2 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          Try again
        </button>
        <Link
          href={homeHref}
          className="text-sm font-medium text-zinc-700 underline hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-50"
        >
          {homeLabel}
        </Link>
      </div>
      {digest && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">Reference: {digest}</p>
      )}
    </div>
  );
}
