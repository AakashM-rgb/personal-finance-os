import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "@/app/(app)/dashboard/page";
import * as accountsLib from "@/lib/accounts";
import * as authContext from "@/lib/auth-context";
import * as categoriesLib from "@/lib/categories";
import * as dashboardLib from "@/lib/dashboard";
import { notifyLedgerChanged, useLedgerVersion } from "@/lib/ledger-events";
import { listQueue, processQueue, queueOfflineExpense } from "@/lib/offline/sync-queue";
import * as transactionsLib from "@/lib/transactions";

vi.mock("@/lib/auth-context", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-context")>("@/lib/auth-context");
  return { ...actual, useAuth: vi.fn() };
});

afterEach(() => {
  vi.restoreAllMocks();
});

function VersionProbe() {
  return <p>version {useLedgerVersion()}</p>;
}

describe("ledger change signal", () => {
  it("re-renders subscribers every time the ledger changes", () => {
    render(<VersionProbe />);
    const before = Number(screen.getByText(/version/).textContent?.split(" ")[1]);

    act(() => notifyLedgerChanged());
    act(() => notifyLedgerChanged());

    expect(screen.getByText(`version ${before + 2}`)).toBeInTheDocument();
  });

  it("makes the open dashboard refetch, without flashing back to a skeleton", async () => {
    vi.mocked(authContext.useAuth).mockReturnValue({
      user: {
        id: "u1",
        email: "a@b.com",
        full_name: "Asha Rao",
        is_active: true,
        email_verified_at: null,
        created_at: "2026-01-01T00:00:00Z",
      },
      accessToken: "token",
      isLoading: false,
      sessionExpired: false,
      connectionIssue: null,
      retrySessionRestore: vi.fn(),
      register: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      logoutAll: vi.fn(),
      changePassword: vi.fn(),
    });
    const getDashboard = vi
      .spyOn(dashboardLib, "getDashboard")
      .mockResolvedValue({ currency: "INR" } as dashboardLib.Dashboard);
    vi.spyOn(accountsLib, "listAccounts").mockResolvedValue([]);
    vi.spyOn(categoriesLib, "listCategories").mockResolvedValue([]);

    render(<DashboardPage />);
    expect(await screen.findByText(/add your first account/i)).toBeInTheDocument();
    expect(getDashboard).toHaveBeenCalledTimes(1);

    act(() => notifyLedgerChanged());

    await waitFor(() => expect(getDashboard).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/add your first account/i)).toBeInTheDocument();
  });
});

describe("offline queue sync announces the new transaction", () => {
  it("notifies once a queued expense is confirmed by the server", async () => {
    const createSpy = vi
      .spyOn(transactionsLib, "createTransaction")
      .mockResolvedValue({ id: "server-1" } as transactionsLib.Transaction);
    await queueOfflineExpense(
      "user-ledger",
      { account_id: "acc-1", type: "expense", amount_minor: 5000 },
      "op-ledger-1"
    );

    render(<VersionProbe />);
    const before = Number(screen.getByText(/version/).textContent?.split(" ")[1]);

    await act(async () => {
      await processQueue("user-ledger", "token");
    });

    expect(createSpy).toHaveBeenCalledTimes(1);
    expect(await listQueue("user-ledger")).toHaveLength(0);
    expect(screen.getByText(`version ${before + 1}`)).toBeInTheDocument();
  });

  it("does not notify when the sync attempt fails", async () => {
    vi.spyOn(transactionsLib, "createTransaction").mockRejectedValue(new TypeError("Failed to fetch"));
    await queueOfflineExpense(
      "user-ledger-2",
      { account_id: "acc-1", type: "expense", amount_minor: 5000 },
      "op-ledger-2"
    );

    render(<VersionProbe />);
    const before = Number(screen.getByText(/version/).textContent?.split(" ")[1]);

    await act(async () => {
      await processQueue("user-ledger-2", "token");
    });

    expect(screen.getByText(`version ${before}`)).toBeInTheDocument();
    expect(await listQueue("user-ledger-2")).toHaveLength(1);
  });
});
