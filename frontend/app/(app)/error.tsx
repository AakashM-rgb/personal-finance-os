"use client";

import { useEffect } from "react";

import { ErrorFallback } from "@/components/ui/error-fallback";

/**
 * Catches render-time exceptions in any signed-in page. It renders inside
 * app/(app)/layout.tsx (an error.tsx never wraps its own segment's layout),
 * so the sidebar and bottom nav stay usable and one broken page never takes
 * down the whole app shell.
 *
 * This complements, not replaces, each page's own inline error state: data
 * fetch failures are caught in the page and shown next to the content with
 * their own "Try again"; this boundary only sees exceptions thrown while
 * rendering.
 */
export default function AppError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex flex-1 items-start justify-center py-12">
      <ErrorFallback
        title="This page couldn't be displayed"
        message="Something went wrong while showing this page. Your data is safe - please try again."
        onRetry={retry}
        homeHref="/dashboard"
        homeLabel="Go to dashboard"
        digest={error.digest}
      />
    </div>
  );
}
