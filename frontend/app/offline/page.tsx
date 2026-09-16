export const metadata = {
  title: "You're offline — Finance App",
};

/**
 * The service worker's navigation fallback (public/sw.js) - shown only
 * when a page navigation fails with no network AND nothing was already
 * cached for that route. This is intentionally static and makes no
 * network/API call, so it always renders even with zero connectivity.
 */
export default function OfflinePage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-white px-6 text-center dark:bg-zinc-950">
      <div
        className="flex h-14 w-14 items-center justify-center rounded-full bg-zinc-100 text-2xl dark:bg-zinc-900"
        aria-hidden="true"
      >
        📡
      </div>
      <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
        You&apos;re offline
      </h1>
      <p className="max-w-sm text-sm text-zinc-600 dark:text-zinc-400">
        This page hasn&apos;t been loaded before, so it isn&apos;t available offline. Any
        expenses you added while offline are saved on this device and will sync automatically
        once you&apos;re back online.
      </p>
      <a
        href="/dashboard"
        className="mt-2 rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
      >
        Try again
      </a>
    </div>
  );
}
