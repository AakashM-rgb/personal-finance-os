import { describe, expect, it } from "vitest";

import {
  getDraft,
  getReferenceData,
  listQueuedTransactionsForUser,
  saveReferenceData,
} from "@/lib/offline/db";

/** Builds the database exactly as the v1 app left it on a user's device. */
function createVersion1Database(): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("finance-app-offline", 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore("drafts", { keyPath: "userId" });
      const queue = db.createObjectStore("syncQueue", { keyPath: "id" });
      queue.createIndex("byUser", "userId", { unique: false });
      queue.put({
        id: "op-1",
        userId: "u1",
        payload: { account_id: "acc-1", type: "expense", amount_minor: 4500 },
        status: "pending",
        createdAt: "2026-10-01T00:00:00Z",
        updatedAt: "2026-10-01T00:00:00Z",
        attempts: 0,
        lastError: null,
        serverTransactionId: null,
      });
    };
    request.onsuccess = () => {
      const db = request.result;
      const tx = db.transaction("drafts", "readwrite");
      tx.objectStore("drafts").put({
        userId: "u1",
        amountInput: "45",
        categoryId: null,
        accountId: null,
        merchant: "",
        note: "",
        date: "2026-10-01T00:00:00Z",
        updatedAt: "2026-10-01T00:00:00Z",
      });
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => reject(tx.error);
    };
    request.onerror = () => reject(request.error);
  });
}

describe("offline database upgrade (v1 -> v2)", () => {
  it("keeps unsynced expenses and drafts, and adds the reference-data store", async () => {
    await createVersion1Database();

    const queued = await listQueuedTransactionsForUser("u1");
    expect(queued).toHaveLength(1);
    expect(queued[0]).toMatchObject({ id: "op-1", status: "pending" });
    expect(queued[0].payload.amount_minor).toBe(4500);
    expect((await getDraft("u1"))?.amountInput).toBe("45");

    expect(await getReferenceData("u1")).toBeNull();
    await saveReferenceData({
      userId: "u1",
      accounts: [{ id: "acc-1", name: "Main", currency: "INR" }],
      categories: [],
      recentAccountIds: [],
      recentCategoryIds: [],
      updatedAt: "2026-10-09T00:00:00Z",
    });
    expect((await getReferenceData("u1"))?.accounts).toHaveLength(1);
  });

  it("scopes saved reference data per user", async () => {
    expect(await getReferenceData("someone-else")).toBeNull();
  });
});
