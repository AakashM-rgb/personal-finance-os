"use client";

import type { OfflineSyncState } from "@/lib/offline/use-offline-sync";

/** A small, honest indicator of local offline-queue state - never implies
 * "your data is up to date" while offline, and never hides that something
 * needs attention. Renders nothing when there's nothing to say. */
export function SyncStatusIndicator({ state }: { state: OfflineSyncState }) {
  const { isOnline, pendingCount, needsAttentionCount } = state;

  if (needsAttentionCount > 0) {
    return (
      <span
        role="status"
        className="flex items-center gap-1.5 rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 dark:bg-red-950 dark:text-red-400"
      >
        <span aria-hidden="true">⚠️</span>
        {needsAttentionCount} need{needsAttentionCount === 1 ? "s" : ""} attention
      </span>
    );
  }

  if (!isOnline) {
    return (
      <span
        role="status"
        className="flex items-center gap-1.5 rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
      >
        <span aria-hidden="true">📡</span>
        Offline{pendingCount > 0 ? ` · ${pendingCount} pending` : ""}
      </span>
    );
  }

  if (pendingCount > 0) {
    return (
      <span
        role="status"
        className="flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300"
      >
        <span aria-hidden="true">🔄</span>
        Syncing {pendingCount}…
      </span>
    );
  }

  return null;
}
