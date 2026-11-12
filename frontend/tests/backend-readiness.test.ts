import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BACKEND_WAKE_BUDGET_MS, waitForBackend } from "@/lib/backend-readiness";

function healthy(): Response {
  return new Response(JSON.stringify({ data: { status: "ok" }, error: null, meta: null }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** What a proxy returns while the backend behind it is still booting. */
function gatewayTimeout(): Response {
  return new Response("<html>504 Gateway Timeout</html>", { status: 504 });
}

/** A request that never answers on its own - only an abort ends it. */
function hangUntilAborted(_input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("waitForBackend", () => {
  it("resolves at once, with a single probe, when the backend is already up", async () => {
    const fetchMock = vi.fn().mockResolvedValue(healthy());
    vi.stubGlobal("fetch", fetchMock);

    await expect(waitForBackend()).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/v1\/health$/);
  });

  it("keeps probing with backoff while the backend wakes up, then resolves", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(gatewayTimeout())
      .mockResolvedValue(healthy());
    vi.stubGlobal("fetch", fetchMock);

    const ready = waitForBackend();
    await vi.advanceTimersByTimeAsync(1_000 + 2_000);

    await expect(ready).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("gives up once the time budget is spent instead of waiting forever", async () => {
    const fetchMock = vi.fn().mockResolvedValue(gatewayTimeout());
    vi.stubGlobal("fetch", fetchMock);

    const ready = waitForBackend();
    await vi.advanceTimersByTimeAsync(BACKEND_WAKE_BUDGET_MS);

    await expect(ready).resolves.toBe(false);
    // Backoff caps at 8s, so the number of probes stays small and bounded.
    expect(fetchMock.mock.calls.length).toBeLessThanOrEqual(12);
  });

  it("aborts a probe that hangs and tries again", async () => {
    const fetchMock = vi.fn().mockImplementationOnce(hangUntilAborted).mockResolvedValue(healthy());
    vi.stubGlobal("fetch", fetchMock);

    const ready = waitForBackend();
    await vi.advanceTimersByTimeAsync(10_000 + 1_000);

    await expect(ready).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
