"use client";

import { useCallback, useEffect, useState } from "react";

import type { QueuedTransactionOp } from "@/lib/offline/db";
import { listQueue, processQueue, subscribeToQueueChanges } from "@/lib/offline/sync-queue";

const SYNC_RETRY_INTERVAL_MS = 25_000;

export interface OfflineSyncState {
  queue: QueuedTransactionOp[];
  isOnline: boolean;
  pendingCount: number;
  needsAttentionCount: number;
  refresh: () => void;
}

/** The single place that drives the offline sync queue's lifecycle:
 * loads/refreshes this user's queue, attempts a sync pass on mount, on
 * reconnect, and on a periodic backoff-respecting interval while online.
 * `userId`/`accessToken` are passed in (never read from storage here) so
 * this hook only ever acts as the currently authenticated user - see
 * lib/offline/db.ts for why that matters for cross-user isolation. */
export function useOfflineSync(
  userId: string | null,
  accessToken: string | null
): OfflineSyncState {
  const [queue, setQueue] = useState<QueuedTransactionOp[]>([]);
  const [isOnline, setIsOnline] = useState(
    typeof navigator === "undefined" ? true : navigator.onLine
  );

  const refresh = useCallback(() => {
    // Resolved asynchronously even for the "no user" case, so a user
    // change (e.g. logout) never leaves the PREVIOUS user's queue
    // rendered synchronously for even one commit - see lib/offline/db.ts
    // for why cross-user leakage is the thing being guarded against here.
    void (userId ? listQueue(userId) : Promise.resolve([])).then(setQueue);
  }, [userId]);

  useEffect(() => {
    refresh();
    if (!userId) return undefined;
    return subscribeToQueueChanges(userId, refresh);
  }, [userId, refresh]);

  useEffect(() => {
    function handleOnline() {
      setIsOnline(true);
      if (userId) void processQueue(userId, accessToken);
    }
    function handleOffline() {
      setIsOnline(false);
    }
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [userId, accessToken]);

  useEffect(() => {
    if (!userId) return undefined;
    void processQueue(userId, accessToken);
    const interval = window.setInterval(() => {
      void processQueue(userId, accessToken);
    }, SYNC_RETRY_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [userId, accessToken]);

  const pendingCount = queue.filter((i) => i.status === "pending" || i.status === "syncing").length;
  const needsAttentionCount = queue.filter((i) => i.status === "needs_attention").length;

  return { queue, isOnline, pendingCount, needsAttentionCount, refresh };
}
