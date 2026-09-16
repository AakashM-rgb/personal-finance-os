/**
 * Offline transaction sync queue - the durable, duplicate-safe bridge
 * between "user saved an expense while offline (or the request otherwise
 * couldn't be confirmed)" and "the existing POST /api/v1/transactions
 * endpoint, the single source of truth, has it."
 *
 * Duplicate safety: every queued operation's `id` (a crypto-random UUID,
 * generated once, at enqueue time) is sent as the Idempotency-Key header
 * on every attempt - including every retry. The backend already
 * recognizes a repeated Idempotency-Key for the same user and returns the
 * original transaction instead of creating a second one (see
 * backend/app/services/transaction_service.py::create_transaction, now
 * also race-safe against the database's own unique constraint). That
 * backend guarantee is what makes "retry after a lost response" and
 * "accidentally submitted twice" both safe here - this module never tries
 * to reinvent that guarantee client-side, it just always resends the same
 * id.
 *
 * State machine per queued item: pending -> syncing -> (synced | pending
 * [transient failure, will retry] | needs_attention [permanent failure,
 * requires the user's attention]). A synced item is removed from the
 * queue only after the server has confirmed it - never before, never
 * merely because a request was sent.
 */

import { ApiError } from "@/lib/api-client";
import { createTransaction } from "@/lib/transactions";
import {
  enqueueTransaction,
  listQueuedTransactionsForUser,
  removeQueuedTransaction,
  updateQueuedTransaction,
  type QueuedTransactionOp,
  type QueuedTransactionPayload,
} from "@/lib/offline/db";

const MAX_AUTO_RETRIES = 6;
const BASE_BACKOFF_MS = 2000;
const MAX_BACKOFF_MS = 60_000;

function nowIso(): string {
  return new Date().toISOString();
}

function backoffDelayMs(attempts: number): number {
  // A never-yet-attempted item (attempts === 0) must be immediately due -
  // backoff only applies AFTER a failure, never before the first try.
  if (attempts <= 0) return 0;
  return Math.min(BASE_BACKOFF_MS * 2 ** (attempts - 1), MAX_BACKOFF_MS);
}

function isDueForRetry(item: QueuedTransactionOp): boolean {
  if (item.status !== "pending") return item.status === "syncing"; // stuck mid-sync (e.g. tab closed) - safe to resume
  const dueAt = new Date(item.updatedAt).getTime() + backoffDelayMs(item.attempts);
  return Date.now() >= dueAt;
}

const queueEvents = new EventTarget();

/** UI subscribes here instead of polling IndexedDB - called after every
 * mutation so components stay in sync without any external state library. */
export function subscribeToQueueChanges(userId: string, listener: () => void): () => void {
  const handler = (event: Event) => {
    if ((event as CustomEvent<string>).detail === userId) listener();
  };
  queueEvents.addEventListener("changed", handler);
  return () => queueEvents.removeEventListener("changed", handler);
}

function notifyChanged(userId: string) {
  queueEvents.dispatchEvent(new CustomEvent("changed", { detail: userId }));
}

export async function listQueue(userId: string): Promise<QueuedTransactionOp[]> {
  return listQueuedTransactionsForUser(userId);
}

export async function queueOfflineExpense(
  userId: string,
  payload: QueuedTransactionPayload,
  /** Reuse a specific id/Idempotency-Key when one was already generated for
   * a direct online attempt that then failed with a network-level error
   * (never a definitive rejection) - the request may have actually reached
   * and been processed by the server with that key; queuing under a
   * DIFFERENT key would risk creating a second transaction once this item
   * eventually syncs. Falls back to a fresh id for the ordinary "we knew
   * we were offline before attempting anything" path. */
  id: string = crypto.randomUUID()
): Promise<QueuedTransactionOp> {
  const op: QueuedTransactionOp = {
    id,
    userId,
    payload,
    status: "pending",
    createdAt: nowIso(),
    updatedAt: nowIso(),
    attempts: 0,
    lastError: null,
    serverTransactionId: null,
  };
  await enqueueTransaction(op);
  notifyChanged(userId);
  return op;
}

/** Lets the user explicitly retry a needs_attention item (e.g. after
 * picking a different, still-valid account) - resets the backoff clock
 * but keeps the SAME id/Idempotency-Key, so it is still impossible for
 * this to ever create a second transaction even if an earlier attempt's
 * response is still in flight somewhere. */
export async function retryQueuedTransaction(userId: string, id: string): Promise<void> {
  const items = await listQueuedTransactionsForUser(userId);
  const item = items.find((i) => i.id === id);
  if (!item) return;
  await updateQueuedTransaction({
    ...item,
    status: "pending",
    attempts: 0,
    lastError: null,
    updatedAt: nowIso(),
  });
  notifyChanged(userId);
}

/** Lets the user intentionally discard a permanently-failed item - the
 * ONLY way a queued item is ever removed without a confirmed server
 * success. Never called automatically. */
export async function discardQueuedTransaction(userId: string, id: string): Promise<void> {
  await removeQueuedTransaction(userId, id);
  notifyChanged(userId);
}

let isProcessing = false;

/** Attempts to sync every due item in this user's queue, one at a time.
 * Safe to call repeatedly/concurrently (e.g. from an `online` listener, a
 * periodic timer, and a manual "sync now" button all at once) - re-entrant
 * calls are no-ops while a run is already in flight. */
export async function processQueue(userId: string, accessToken: string | null): Promise<void> {
  if (isProcessing) return;
  isProcessing = true;
  try {
    const items = await listQueuedTransactionsForUser(userId);

    if (!accessToken) {
      // Case H: not authenticated right now - block, don't burn retry
      // attempts, and say so; a subsequent call once signed back in will
      // pick these items straight back up (still "pending").
      for (const item of items) {
        if (item.status === "needs_attention") continue;
        if (item.lastError === AUTH_REQUIRED_MESSAGE && item.status === "pending") continue;
        await updateQueuedTransaction({
          ...item,
          status: "pending",
          lastError: AUTH_REQUIRED_MESSAGE,
          updatedAt: nowIso(),
        });
      }
      notifyChanged(userId);
      return;
    }

    for (const item of items) {
      if (item.status === "needs_attention") continue;
      if (!isDueForRetry(item)) continue;

      const stop = await syncOne(userId, item, accessToken);
      if (stop) break; // network/auth-wide failure - the rest would fail identically right now
    }
  } finally {
    isProcessing = false;
  }
}

const AUTH_REQUIRED_MESSAGE = "Sign in again to sync this expense.";

/** Returns true if the caller should stop processing the rest of the
 * queue this run (a network-wide or auth-wide condition, not something
 * specific to this one item). */
async function syncOne(
  userId: string,
  item: QueuedTransactionOp,
  accessToken: string
): Promise<boolean> {
  await updateQueuedTransaction({ ...item, status: "syncing", updatedAt: nowIso() });
  notifyChanged(userId);

  try {
    const transaction = await createTransaction(accessToken, item.payload, item.id);
    // Removed ONLY now, after a confirmed server response naming the
    // created (or, on a replayed Idempotency-Key, the original) transaction.
    await removeQueuedTransaction(userId, item.id);
    notifyChanged(userId);
    void transaction; // server id isn't needed locally - the transactions list already reflects it
    return false;
  } catch (err) {
    return await handleSyncFailure(userId, item, err);
  }
}

async function handleSyncFailure(
  userId: string,
  item: QueuedTransactionOp,
  err: unknown
): Promise<boolean> {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      await updateQueuedTransaction({
        ...item,
        status: "pending",
        lastError: AUTH_REQUIRED_MESSAGE,
        updatedAt: nowIso(),
      });
      notifyChanged(userId);
      return true; // every other item would also 401 right now
    }

    if (err.status === 429 || err.status >= 500) {
      // Transient - back off and retry automatically, but not forever.
      const attempts = item.attempts + 1;
      const permanentlyStuck = attempts >= MAX_AUTO_RETRIES;
      await updateQueuedTransaction({
        ...item,
        status: permanentlyStuck ? "needs_attention" : "pending",
        attempts,
        lastError: permanentlyStuck
          ? `Still failing after ${attempts} attempts: ${err.message}`
          : err.message,
        updatedAt: nowIso(),
      });
      notifyChanged(userId);
      return false; // item-specific-ish (server load); keep trying the rest of the queue
    }

    // 400/403/404/422 and anything else 4xx: a genuine, non-retryable
    // problem with THIS operation (Case I - e.g. the account or category
    // it referenced no longer exists/isn't valid) - never silently
    // dropped, never auto-retried into the same failure forever, and
    // never reinterpreted as "just use some other account instead".
    await updateQueuedTransaction({
      ...item,
      status: "needs_attention",
      attempts: item.attempts + 1,
      lastError: err.message,
      updatedAt: nowIso(),
    });
    notifyChanged(userId);
    return false;
  }

  // Not an ApiError at all - fetch() itself threw, i.e. no response was
  // ever received (offline, DNS failure, request aborted). We genuinely
  // don't know whether the server processed it - that's exactly why the
  // Idempotency-Key exists. Treat as transient and retry later; never
  // count this against the permanent-failure threshold the way a real
  // 5xx does, since "the network is down" isn't this operation's fault.
  await updateQueuedTransaction({
    ...item,
    status: "pending",
    attempts: item.attempts + 1,
    lastError: "Couldn't reach the server - will retry automatically.",
    updatedAt: nowIso(),
  });
  notifyChanged(userId);
  return true; // the rest of the queue would fail identically right now
}
