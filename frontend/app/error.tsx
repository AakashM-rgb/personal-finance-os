"use client";

import { useEffect } from "react";

import { ErrorFallback } from "@/components/ui/error-fallback";

/**
 * Catches render-time exceptions in the public pages (landing, login,
 * register, offline). Signed-in pages are caught first by the closer
 * app/(app)/error.tsx; failures in the root layout itself are handled by
 * app/global-error.tsx, since an error.tsx never wraps its own layout.
 */
export default function RootError({
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
    <div className="flex flex-1 items-center justify-center px-6 py-12">
      <ErrorFallback
        title="Something went wrong"
        message="This page couldn't be displayed. Please try again."
        onRetry={retry}
        homeHref="/"
        homeLabel="Go to home page"
        digest={error.digest}
      />
    </div>
  );
}
