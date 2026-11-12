"use client";

import "./globals.css";

import { useEffect } from "react";

import { ErrorFallback } from "@/components/ui/error-fallback";

/**
 * Last-resort boundary for exceptions thrown by the root layout itself
 * (AuthProvider, ThemeSync, service-worker registration). It replaces the
 * root layout while active, so it must render its own <html>/<body> and
 * import globals.css itself. The saved theme class isn't applied here, so it
 * follows the OS color scheme via Tailwind's `dark:` variants.
 */
export default function GlobalError({
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
    <html lang="en">
      <body className="flex min-h-screen items-center justify-center bg-white px-6 dark:bg-zinc-950">
        <title>Something went wrong — Finance App</title>
        <ErrorFallback
          title="Something went wrong"
          message="The app couldn't start properly. Please try again."
          onRetry={retry}
          homeHref="/"
          homeLabel="Go to home page"
          digest={error.digest}
        />
      </body>
    </html>
  );
}
