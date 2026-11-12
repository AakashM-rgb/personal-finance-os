"use client";

import { useSyncExternalStore } from "react";

/**
 * One app-wide "the ledger changed" signal. Anything that creates, edits or
 * deletes a transaction - including flows that live outside the page being
 * viewed, like the mobile Add sheet or the offline queue syncing in the
 * background - calls notifyLedgerChanged(); every view showing ledger-derived
 * numbers (balances, totals, budgets, charts) includes useLedgerVersion() in
 * its fetch dependencies, so it refetches instead of showing stale figures.
 *
 * It carries no data and fetches nothing itself: each page still loads
 * through lib/<feature>.ts as before. A shared query cache would replace this
 * with targeted invalidation.
 */

let version = 0;
const listeners = new Set<() => void>();

export function notifyLedgerChanged(): void {
  version += 1;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Increments every time the ledger changes; use it as an effect dependency. */
export function useLedgerVersion(): number {
  return useSyncExternalStore(
    subscribe,
    () => version,
    () => 0
  );
}
