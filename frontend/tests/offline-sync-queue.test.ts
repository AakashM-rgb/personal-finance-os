import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";
import { listQueuedTransactionsForUser, removeQueuedTransaction, updateQueuedTransaction } from "@/lib/offline/db";
import {
  discardQueuedTransaction,
  listQueue,
  processQueue,
  queueOfflineExpense,
  retryQueuedTransaction,
} from "@/lib/offline/sync-queue";
import * as transactionsLib from "@/lib/transactions";

const PAYLOAD = { account_id: "acc-1", type: "expense" as const, amount_minor: 1500 };

async function clearQueue(userId: string) {
  const items = await listQueuedTransactionsForUser(userId);
  await Promise.all(items.map((item) => removeQueuedTransaction(userId, item.id)));
}

/** Forces the backoff check to always consider an item "due" regardless
 * of how many attempts it's had, by backdating updatedAt far into the
 * past - avoids needing fake timers to test multi-attempt escalation. */
async function backdateItem(userId: string, id: string) {
  const items = await listQueuedTransactionsForUser(userId);
  const item = items.find((i) => i.id === id);
  if (!item) throw new Error("item not found");
  await updateQueuedTransaction({ ...item, updatedAt: new Date(0).toISOString() });
}

afterEach(async () => {
  vi.restoreAllMocks();
  await clearQueue("user-a");
  await clearQueue("user-b");
});

describe("queueOfflineExpense", () => {
  it("creates a pending item with a fresh random id when none is given", async () => {
    const op = await queueOfflineExpense("user-a", PAYLOAD);
    expect(op.status).toBe("pending");
    expect(op.userId).toBe("user-a");
    expect(op.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(op.attempts).toBe(0);
  });

  it("reuses a caller-supplied id (shared idempotency key with a prior online attempt)", async () => {
    const op = await queueOfflineExpense("user-a", PAYLOAD, "predetermined-id");
    expect(op.id).toBe("predetermined-id");
  });
});

describe("processQueue - success path", () => {
  it("syncs a pending item and removes it from the queue only after server confirmation", async () => {
    const createSpy = vi
      .spyOn(transactionsLib, "createTransaction")
      .mockResolvedValue({ id: "server-txn-1" } as never);

    const op = await queueOfflineExpense("user-a", PAYLOAD);
    await processQueue("user-a", "token-a");

    expect(createSpy).toHaveBeenCalledWith("token-a", PAYLOAD, op.id);
    expect(await listQueue("user-a")).toHaveLength(0);
  });
});

describe("processQueue - transient failures (retry, never lost)", () => {
  it("a network-level failure (no response) leaves the item pending, never removes it", async () => {
    vi.spyOn(transactionsLib, "createTransaction").mockRejectedValue(new TypeError("Failed to fetch"));

    await queueOfflineExpense("user-a", PAYLOAD);
    await processQueue("user-a", "token-a");

    const items = await listQueue("user-a");
    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("pending");
    expect(items[0].lastError).toMatch(/retry/i);
  });

  it("a 5xx response is treated as transient and retried, never immediately dropped", async () => {
    vi.spyOn(transactionsLib, "createTransaction").mockRejectedValue(
      new ApiError(503, { code: "server_error", message: "Service unavailable", field_errors: null })
    );

    await queueOfflineExpense("user-a", PAYLOAD);
    await processQueue("user-a", "token-a");

    const items = await listQueue("user-a");
    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("pending");
    expect(items[0].attempts).toBe(1);
  });

  it("escalates to needs_attention after repeated transient failures, never retries forever silently", async () => {
    vi.spyOn(transactionsLib, "createTransaction").mockRejectedValue(
      new ApiError(500, { code: "server_error", message: "Boom", field_errors: null })
    );

    const op = await queueOfflineExpense("user-a", PAYLOAD);
    for (let i = 0; i < 6; i++) {
      await backdateItem("user-a", op.id);
      await processQueue("user-a", "token-a");
    }

    const items = await listQueue("user-a");
    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("needs_attention");
    expect(items[0].lastError).toMatch(/still failing/i);
  });
});

describe("processQueue - permanent failures (Case I: stale account/category)", () => {
  it("a 422 validation error marks the item needs_attention, never silently drops it", async () => {
    vi.spyOn(transactionsLib, "createTransaction").mockRejectedValue(
      new ApiError(422, { code: "validation_error", message: "Account not found.", field_errors: null })
    );

    await queueOfflineExpense("user-a", PAYLOAD);
    await processQueue("user-a", "token-a");

    const items = await listQueue("user-a");
    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("needs_attention");
    expect(items[0].lastError).toBe("Account not found.");
  });

  it("needs_attention items are never auto-retried by subsequent processQueue calls", async () => {
    const createSpy = vi
      .spyOn(transactionsLib, "createTransaction")
      .mockRejectedValue(new ApiError(404, { code: "not_found", message: "Account not found.", field_errors: null }));

    await queueOfflineExpense("user-a", PAYLOAD);
    await processQueue("user-a", "token-a"); // -> needs_attention
    createSpy.mockClear();
    await processQueue("user-a", "token-a"); // must not retry

    expect(createSpy).not.toHaveBeenCalled();
  });

  it("never redirects the operation to a different account - the original payload is preserved verbatim", async () => {
    vi.spyOn(transactionsLib, "createTransaction").mockRejectedValue(
      new ApiError(404, { code: "not_found", message: "Account not found.", field_errors: null })
    );
    await queueOfflineExpense("user-a", PAYLOAD);
    await processQueue("user-a", "token-a");
    const items = await listQueue("user-a");
    expect(items[0].payload.account_id).toBe(PAYLOAD.account_id);
  });
});

describe("processQueue - authentication required (Case H)", () => {
  it("never bypasses authentication - with no access token, items stay pending and no request is sent", async () => {
    const createSpy = vi.spyOn(transactionsLib, "createTransaction");
    await queueOfflineExpense("user-a", PAYLOAD);
    await processQueue("user-a", null);

    expect(createSpy).not.toHaveBeenCalled();
    const items = await listQueue("user-a");
    expect(items[0].status).toBe("pending");
    expect(items[0].lastError).toMatch(/sign in/i);
  });

  it("a 401 from the server blocks further items in the same run rather than burning through them", async () => {
    const createSpy = vi
      .spyOn(transactionsLib, "createTransaction")
      .mockRejectedValue(new ApiError(401, { code: "unauthenticated", message: "Expired.", field_errors: null }));

    await queueOfflineExpense("user-a", PAYLOAD);
    await queueOfflineExpense("user-a", PAYLOAD);
    await processQueue("user-a", "stale-token");

    expect(createSpy).toHaveBeenCalledTimes(1);
    const items = await listQueue("user-a");
    expect(items.every((i) => i.status === "pending")).toBe(true);
  });
});

describe("duplicate-submission safety", () => {
  it("concurrent processQueue calls for the same user only sync each item once", async () => {
    const createSpy = vi
      .spyOn(transactionsLib, "createTransaction")
      .mockResolvedValue({ id: "server-txn-x" } as never);

    await queueOfflineExpense("user-a", PAYLOAD);
    await Promise.all([processQueue("user-a", "token-a"), processQueue("user-a", "token-a")]);

    expect(createSpy).toHaveBeenCalledTimes(1);
    expect(await listQueue("user-a")).toHaveLength(0);
  });

  it("Case F: an item stuck in 'syncing' (e.g. the browser closed mid-request) resumes and completes exactly once, never duplicating", async () => {
    const createSpy = vi
      .spyOn(transactionsLib, "createTransaction")
      .mockResolvedValue({ id: "server-txn-resumed" } as never);

    const op = await queueOfflineExpense("user-a", PAYLOAD);
    // Simulate the app being killed after syncOne() flipped the item to
    // "syncing" but before the request resolved - IndexedDB durably kept
    // that state across the (simulated) restart.
    await updateQueuedTransaction({ ...op, status: "syncing" });

    await processQueue("user-a", "token-a");

    expect(createSpy).toHaveBeenCalledTimes(1);
    expect(createSpy).toHaveBeenCalledWith("token-a", PAYLOAD, op.id); // same Idempotency-Key, safe even if the original request had actually landed
    expect(await listQueue("user-a")).toHaveLength(0);
  });
});

describe("retry and discard", () => {
  it("retryQueuedTransaction resets a needs_attention item back to pending with the SAME id", async () => {
    vi.spyOn(transactionsLib, "createTransaction").mockRejectedValueOnce(
      new ApiError(404, { code: "not_found", message: "Account not found.", field_errors: null })
    );
    const op = await queueOfflineExpense("user-a", PAYLOAD);
    await processQueue("user-a", "token-a");
    expect((await listQueue("user-a"))[0].status).toBe("needs_attention");

    await retryQueuedTransaction("user-a", op.id);
    const items = await listQueue("user-a");
    expect(items[0].status).toBe("pending");
    expect(items[0].id).toBe(op.id);
    expect(items[0].attempts).toBe(0);
  });

  it("discardQueuedTransaction removes the item - the only non-success removal path", async () => {
    const op = await queueOfflineExpense("user-a", PAYLOAD);
    await discardQueuedTransaction("user-a", op.id);
    expect(await listQueue("user-a")).toHaveLength(0);
  });
});

describe("cross-user isolation", () => {
  it("processing User A's queue never touches or syncs User B's items", async () => {
    const createSpy = vi
      .spyOn(transactionsLib, "createTransaction")
      .mockResolvedValue({ id: "server-txn" } as never);

    await queueOfflineExpense("user-a", PAYLOAD);
    await queueOfflineExpense("user-b", PAYLOAD);

    await processQueue("user-a", "token-a");

    expect(createSpy).toHaveBeenCalledTimes(1);
    expect(createSpy).toHaveBeenCalledWith("token-a", PAYLOAD, expect.any(String));
    const bItems = await listQueue("user-b");
    expect(bItems).toHaveLength(1);
    expect(bItems[0].status).toBe("pending"); // untouched
  });

  it("User A's stale/needs_attention queue can never be synced by calling processQueue as User B", async () => {
    vi.spyOn(transactionsLib, "createTransaction").mockResolvedValue({ id: "x" } as never);
    await queueOfflineExpense("user-a", PAYLOAD);

    await processQueue("user-b", "token-b"); // B has an empty queue

    const aItems = await listQueue("user-a");
    expect(aItems).toHaveLength(1);
    expect(aItems[0].status).toBe("pending"); // never synced by B's call
  });
});
