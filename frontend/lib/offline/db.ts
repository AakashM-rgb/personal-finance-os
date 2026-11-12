/**
 * IndexedDB-backed local storage for offline expense drafts and the
 * offline transaction sync queue.
 *
 * SECURITY: one IndexedDB database is shared by the whole origin (that is
 * how IndexedDB works - it cannot be partitioned per signed-in user by the
 * browser itself). Isolation between users on the same device is instead
 * enforced HERE, in every function in this module: every record carries a
 * `userId`, every read is filtered by the caller's authenticated user id
 * (never "whichever records happen to exist"), and every write requires
 * one. There is no function in this module that can return or mutate a
 * record without a matching userId - callers always pass the id from
 * useAuth(), never a value read back out of storage itself. No access
 * token, refresh token, or other secret is ever written here - only
 * transaction-shaped financial draft data, queued operation payloads, and
 * the minimal account/category labels the Add Expense sheet needs to work
 * offline (never balances or any other account detail).
 */

const DB_NAME = "finance-app-offline";
// v2 adds STORE_REFERENCE. Upgrades only ever create missing stores, so an
// existing user's drafts and queued (not yet synced) expenses survive it.
const DB_VERSION = 2;
const STORE_DRAFTS = "drafts";
const STORE_QUEUE = "syncQueue";
const STORE_REFERENCE = "referenceData";

export type SyncStatus = "pending" | "syncing" | "synced" | "failed" | "needs_attention";

/** Exactly the shape POST /api/v1/transactions accepts - see lib/transactions.ts TransactionInput. */
export interface QueuedTransactionPayload {
  account_id: string;
  type: "expense" | "income" | "transfer";
  amount_minor: number;
  category_id?: string | null;
  merchant?: string | null;
  description?: string | null;
  occurred_at?: string;
}

export interface QueuedTransactionOp {
  /** Client-generated (crypto.randomUUID()) - doubles as the Idempotency-Key
   * sent to the server, so a retried/duplicated sync attempt can never
   * create two transactions (see lib/offline/sync-queue.ts). */
  id: string;
  userId: string;
  payload: QueuedTransactionPayload;
  status: SyncStatus;
  createdAt: string;
  updatedAt: string;
  attempts: number;
  lastError: string | null;
  /** Set only after a confirmed 2xx response naming the created/matched
   * server transaction - never guessed, never set on send. */
  serverTransactionId: string | null;
}

export interface ExpenseDraft {
  /** One in-progress Add-Expense draft per user - keyed by userId itself,
   * so "the draft" is unambiguous and a second device/tab editing the
   * same user's draft simply overwrites it (last write wins), same as
   * any other per-user local UI state. */
  userId: string;
  amountInput: string;
  categoryId: string | null;
  accountId: string | null;
  merchant: string;
  note: string;
  date: string;
  updatedAt: string;
}

/** The last-known accounts/categories for one user, so expense entry still
 * works offline. Only labels and ids - enough to pick an account and
 * category - plus the currency, which decides how an amount is parsed. */
export interface ReferenceDataSnapshot {
  userId: string;
  accounts: { id: string; name: string; currency: string }[];
  categories: { id: string; name: string; icon: string }[];
  recentAccountIds: string[];
  recentCategoryIds: string[];
  updatedAt: string;
}

let dbPromise: Promise<IDBDatabase> | null = null;

function isIndexedDBAvailable(): boolean {
  return typeof indexedDB !== "undefined";
}

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;

  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_DRAFTS)) {
        db.createObjectStore(STORE_DRAFTS, { keyPath: "userId" });
      }
      if (!db.objectStoreNames.contains(STORE_QUEUE)) {
        const store = db.createObjectStore(STORE_QUEUE, { keyPath: "id" });
        store.createIndex("byUser", "userId", { unique: false });
      }
      if (!db.objectStoreNames.contains(STORE_REFERENCE)) {
        db.createObjectStore(STORE_REFERENCE, { keyPath: "userId" });
      }
    };

    request.onsuccess = () => {
      const db = request.result;
      // Let a newer version of the app (another tab) upgrade the database
      // instead of being blocked by this connection; the next call reopens.
      db.onversionchange = () => {
        db.close();
        dbPromise = null;
      };
      resolve(db);
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("IndexedDB upgrade blocked by another tab."));
  });

  return dbPromise;
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** Resolves once the transaction actually commits - awaiting a request's
 * own onsuccess only means it was queued/applied within the transaction,
 * not that it's durably committed; every write in this module waits for
 * this too, so a caller who awaits e.g. saveDraft() can trust the write
 * really landed before doing anything else with it. */
function transactionComplete(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error ?? new Error("IndexedDB transaction aborted."));
  });
}

/** Whether durable local storage is usable at all right now - callers
 * (drafts, sync queue) must check this and clearly tell the user their
 * work is NOT being saved locally when it's false, rather than silently
 * behaving as if it were (private browsing, storage quota exhaustion,
 * and browsers without IndexedDB all surface here the same way). */
export async function isOfflineStorageAvailable(): Promise<boolean> {
  if (!isIndexedDBAvailable()) return false;
  try {
    await openDb();
    return true;
  } catch {
    return false;
  }
}

// --- drafts -----------------------------------------------------------------

export async function saveDraft(draft: ExpenseDraft): Promise<void> {
  const db = await openDb();
  const tx = db.transaction(STORE_DRAFTS, "readwrite");
  tx.objectStore(STORE_DRAFTS).put(draft);
  await transactionComplete(tx);
}

export async function getDraft(userId: string): Promise<ExpenseDraft | null> {
  const db = await openDb();
  const tx = db.transaction(STORE_DRAFTS, "readonly");
  const result = await requestToPromise(tx.objectStore(STORE_DRAFTS).get(userId));
  return (result as ExpenseDraft | undefined) ?? null;
}

export async function deleteDraft(userId: string): Promise<void> {
  const db = await openDb();
  const tx = db.transaction(STORE_DRAFTS, "readwrite");
  tx.objectStore(STORE_DRAFTS).delete(userId);
  await transactionComplete(tx);
}

// --- reference data (accounts/categories for offline entry) ----------------

export async function saveReferenceData(snapshot: ReferenceDataSnapshot): Promise<void> {
  const db = await openDb();
  const tx = db.transaction(STORE_REFERENCE, "readwrite");
  tx.objectStore(STORE_REFERENCE).put(snapshot);
  await transactionComplete(tx);
}

export async function getReferenceData(userId: string): Promise<ReferenceDataSnapshot | null> {
  const db = await openDb();
  const tx = db.transaction(STORE_REFERENCE, "readonly");
  const result = await requestToPromise(tx.objectStore(STORE_REFERENCE).get(userId));
  return (result as ReferenceDataSnapshot | undefined) ?? null;
}

// --- sync queue ---------------------------------------------------------------

export async function enqueueTransaction(op: QueuedTransactionOp): Promise<void> {
  const db = await openDb();
  const tx = db.transaction(STORE_QUEUE, "readwrite");
  tx.objectStore(STORE_QUEUE).put(op);
  await transactionComplete(tx);
}

export async function updateQueuedTransaction(op: QueuedTransactionOp): Promise<void> {
  return enqueueTransaction(op);
}

/** Deletes a queued item ONLY if it actually belongs to `userId` - mirrors
 * the backend's own "never trust a bare id, always scope by owner"
 * repository pattern (see e.g. TransactionRepository.get_by_id_for_user).
 * A ref to a different user's item is a silent no-op, not an error - the
 * caller asked to remove something that, as far as THEY are concerned,
 * doesn't exist. */
export async function removeQueuedTransaction(userId: string, id: string): Promise<void> {
  const db = await openDb();
  const tx = db.transaction(STORE_QUEUE, "readwrite");
  const store = tx.objectStore(STORE_QUEUE);
  const existing = (await requestToPromise(store.get(id))) as QueuedTransactionOp | undefined;
  if (existing && existing.userId === userId) {
    store.delete(id);
  }
  await transactionComplete(tx);
}

/** Every queued operation for ONE user, oldest first - the only read
 * function the sync queue manager or any UI may use; there is no
 * "list everything" function in this module on purpose. */
export async function listQueuedTransactionsForUser(
  userId: string
): Promise<QueuedTransactionOp[]> {
  const db = await openDb();
  const tx = db.transaction(STORE_QUEUE, "readonly");
  const index = tx.objectStore(STORE_QUEUE).index("byUser");
  const results = await requestToPromise(index.getAll(userId));
  return (results as QueuedTransactionOp[]).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function getQueuedTransaction(
  userId: string,
  id: string
): Promise<QueuedTransactionOp | null> {
  const items = await listQueuedTransactionsForUser(userId);
  return items.find((item) => item.id === id) ?? null;
}
