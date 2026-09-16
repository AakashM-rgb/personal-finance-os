import { afterEach, describe, expect, it } from "vitest";

import {
  deleteDraft,
  enqueueTransaction,
  getDraft,
  isOfflineStorageAvailable,
  listQueuedTransactionsForUser,
  removeQueuedTransaction,
  saveDraft,
  updateQueuedTransaction,
  type ExpenseDraft,
  type QueuedTransactionOp,
} from "@/lib/offline/db";

function makeDraft(userId: string, overrides: Partial<ExpenseDraft> = {}): ExpenseDraft {
  return {
    userId,
    amountInput: "120",
    categoryId: null,
    accountId: null,
    merchant: "",
    note: "",
    date: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
}

function makeQueueItem(userId: string, overrides: Partial<QueuedTransactionOp> = {}): QueuedTransactionOp {
  return {
    id: crypto.randomUUID(),
    userId,
    payload: { account_id: "acc-1", type: "expense", amount_minor: 1000 },
    status: "pending",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    attempts: 0,
    lastError: null,
    serverTransactionId: null,
    ...overrides,
  };
}

// IndexedDB in fake-indexeddb persists per-test-file-process; clear both
// stores between tests by removing every record we know about.
async function clearAllQueueItemsForUser(userId: string) {
  const items = await listQueuedTransactionsForUser(userId);
  await Promise.all(items.map((item) => removeQueuedTransaction(userId, item.id)));
}

describe("offline drafts", () => {
  afterEach(async () => {
    await deleteDraft("user-a");
    await deleteDraft("user-b");
  });

  it("reports offline storage as available under the fake-indexeddb polyfill", async () => {
    expect(await isOfflineStorageAvailable()).toBe(true);
  });

  it("saves and retrieves a draft for a user", async () => {
    await saveDraft(makeDraft("user-a", { amountInput: "499.50", merchant: "Coffee shop" }));
    const draft = await getDraft("user-a");
    expect(draft?.amountInput).toBe("499.50");
    expect(draft?.merchant).toBe("Coffee shop");
  });

  it("returns null when no draft exists for a user", async () => {
    expect(await getDraft("nobody")).toBeNull();
  });

  it("overwrites the previous draft on save (one active draft per user)", async () => {
    await saveDraft(makeDraft("user-a", { amountInput: "100" }));
    await saveDraft(makeDraft("user-a", { amountInput: "200" }));
    const draft = await getDraft("user-a");
    expect(draft?.amountInput).toBe("200");
  });

  it("deletes a draft", async () => {
    await saveDraft(makeDraft("user-a"));
    await deleteDraft("user-a");
    expect(await getDraft("user-a")).toBeNull();
  });

  // --- cross-user isolation -----------------------------------------------

  it("never returns User A's draft when queried as User B", async () => {
    await saveDraft(makeDraft("user-a", { amountInput: "777", merchant: "User A's secret" }));
    const draftForB = await getDraft("user-b");
    expect(draftForB).toBeNull();
  });

  it("deleting User B's draft never touches User A's draft", async () => {
    await saveDraft(makeDraft("user-a", { amountInput: "111" }));
    await saveDraft(makeDraft("user-b", { amountInput: "222" }));
    await deleteDraft("user-b");
    expect(await getDraft("user-a")).not.toBeNull();
    expect((await getDraft("user-a"))?.amountInput).toBe("111");
  });
});

describe("offline sync queue storage", () => {
  afterEach(async () => {
    await clearAllQueueItemsForUser("user-a");
    await clearAllQueueItemsForUser("user-b");
  });

  it("enqueues and lists a queued transaction for a user", async () => {
    const op = makeQueueItem("user-a");
    await enqueueTransaction(op);
    const items = await listQueuedTransactionsForUser("user-a");
    expect(items).toHaveLength(1);
    expect(items[0].id).toBe(op.id);
  });

  it("lists items oldest-first", async () => {
    const first = makeQueueItem("user-a", { createdAt: "2026-01-01T00:00:00Z" });
    const second = makeQueueItem("user-a", { createdAt: "2026-01-02T00:00:00Z" });
    await enqueueTransaction(second);
    await enqueueTransaction(first);
    const items = await listQueuedTransactionsForUser("user-a");
    expect(items.map((i) => i.id)).toEqual([first.id, second.id]);
  });

  it("updates a queued item in place (same id)", async () => {
    const op = makeQueueItem("user-a", { status: "pending" });
    await enqueueTransaction(op);
    await updateQueuedTransaction({ ...op, status: "syncing" });
    const items = await listQueuedTransactionsForUser("user-a");
    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("syncing");
  });

  it("removes a queued item only when explicitly asked", async () => {
    const op = makeQueueItem("user-a");
    await enqueueTransaction(op);
    await removeQueuedTransaction("user-a", op.id);
    expect(await listQueuedTransactionsForUser("user-a")).toHaveLength(0);
  });

  it("never removes an item that belongs to a different user, even if the id is known", async () => {
    const op = makeQueueItem("user-a");
    await enqueueTransaction(op);
    await removeQueuedTransaction("user-b", op.id); // wrong owner
    expect(await listQueuedTransactionsForUser("user-a")).toHaveLength(1);
  });

  // --- cross-user isolation -----------------------------------------------

  it("never lists User A's queue items when queried as User B", async () => {
    await enqueueTransaction(makeQueueItem("user-a", { payload: { account_id: "a", type: "expense", amount_minor: 999999 } }));
    const itemsForB = await listQueuedTransactionsForUser("user-b");
    expect(itemsForB).toHaveLength(0);
  });

  it("removing one user's queue item never affects another user's queue", async () => {
    const aOp = makeQueueItem("user-a");
    const bOp = makeQueueItem("user-b");
    await enqueueTransaction(aOp);
    await enqueueTransaction(bOp);
    await removeQueuedTransaction("user-a", aOp.id);
    expect(await listQueuedTransactionsForUser("user-a")).toHaveLength(0);
    const bItems = await listQueuedTransactionsForUser("user-b");
    expect(bItems).toHaveLength(1);
    expect(bItems[0].id).toBe(bOp.id);
  });
});
