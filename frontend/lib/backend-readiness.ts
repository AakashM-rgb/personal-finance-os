import { apiRequest } from "@/lib/api-client";

/** Long enough for a sleeping free-tier backend to boot (typically 30-60s),
 * short enough that a genuinely unreachable one is reported, not waited on. */
export const BACKEND_WAKE_BUDGET_MS = 60_000;
const PROBE_TIMEOUT_MS = 10_000;
const PROBE_BACKOFF_MS = [1_000, 2_000, 4_000, 8_000];

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function probeOnce(timeoutMs: number): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    // Health is side-effect free, so aborting or repeating it is always safe -
    // unlike /auth/refresh, whose rotation makes every attempt count.
    await apiRequest("/api/v1/health", { signal: controller.signal });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Resolves true as soon as the backend answers its health check, or false
 * once the time budget runs out. A probe that is aborted still wakes a
 * sleeping backend, so later probes find it ready.
 */
export async function waitForBackend(budgetMs: number = BACKEND_WAKE_BUDGET_MS): Promise<boolean> {
  const deadline = Date.now() + budgetMs;
  for (let attempt = 0; ; attempt += 1) {
    const remaining = deadline - Date.now();
    if (remaining <= 0) return false;
    if (await probeOnce(Math.min(PROBE_TIMEOUT_MS, remaining))) return true;

    const backoff = PROBE_BACKOFF_MS[Math.min(attempt, PROBE_BACKOFF_MS.length - 1)];
    const wait = Math.min(backoff, deadline - Date.now());
    if (wait <= 0) return false;
    await sleep(wait);
  }
}
