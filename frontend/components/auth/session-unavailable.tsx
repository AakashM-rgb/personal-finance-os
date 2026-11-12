import Link from "next/link";

import { Button } from "@/components/ui/button";

/** Shown instead of the login redirect when a stored session couldn't be
 * checked because the server didn't answer - the session itself may be fine. */
export function SessionUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-1 items-center justify-center p-4">
      <div role="alert" className="flex max-w-sm flex-col items-center gap-4 text-center">
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          We couldn&apos;t reach the server
        </h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Your account couldn&apos;t be loaded because the server didn&apos;t respond. Check your
          connection and try again.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button onClick={onRetry}>Try again</Button>
          <Link
            href="/login"
            className="inline-flex h-10 items-center rounded-md px-4 text-sm font-medium text-zinc-700 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Go to sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
