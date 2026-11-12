import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LinkedAccountCard } from "@/components/sync/linked-account-card";
import { ApiError } from "@/lib/api-client";
import type { LinkedAccount, SyncRun } from "@/lib/sync";

function buildLinkedAccount(overrides: Partial<LinkedAccount> = {}): LinkedAccount {
  return {
    id: "link-1",
    account_id: "acc-1",
    provider: "mock",
    external_institution_name: "Mock Bank",
    fip_reference: "MOCKBANK-FIP-001",
    consent_status: "active",
    consent_expires_at: "2027-01-01T00:00:00Z",
    masked_account_ref: "XX4321",
    last_synced_at: null,
    last_sync_status: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

describe("LinkedAccountCard", () => {
  it("shows a loading state while a sync is in progress", async () => {
    let resolveSync: (run: SyncRun) => void = () => {};
    const onSync = vi.fn(
      () =>
        new Promise<SyncRun>((resolve) => {
          resolveSync = resolve;
        })
    );

    render(
      <LinkedAccountCard
        linkedAccount={buildLinkedAccount()}
        onSync={onSync}
        onRequestDisconnect={vi.fn()}
        onViewHistory={vi.fn()}
      />
    );

    const syncButton = screen.getByRole("button", { name: "Sync Now" });
    fireEvent.click(syncButton);

    expect(onSync).toHaveBeenCalledWith("link-1");
    await waitFor(() => expect(screen.getByRole("button", { name: "Please wait…" })).toBeDisabled());

    resolveSync({
      id: "run-1",
      linked_account_id: "link-1",
      started_at: "2026-09-18T10:00:00Z",
      completed_at: "2026-09-18T10:00:02Z",
      status: "success",
      transactions_fetched: 3,
      transactions_created: 3,
      transactions_skipped_duplicate: 0,
      error_message: null,
    });

    await waitFor(() => expect(screen.getByRole("button", { name: "Sync Now" })).toBeInTheDocument());
  });

  it("shows the real sync result (found/imported/skipped) without fabricating data", async () => {
    const onSync = vi.fn().mockResolvedValue({
      id: "run-1",
      linked_account_id: "link-1",
      started_at: "2026-09-18T10:00:00Z",
      completed_at: "2026-09-18T10:00:02Z",
      status: "success",
      transactions_fetched: 5,
      transactions_created: 4,
      transactions_skipped_duplicate: 1,
      error_message: null,
    } satisfies SyncRun);

    render(
      <LinkedAccountCard
        linkedAccount={buildLinkedAccount()}
        onSync={onSync}
        onRequestDisconnect={vi.fn()}
        onViewHistory={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Sync Now" }));

    expect(await screen.findByText("Sync completed")).toBeInTheDocument();
    expect(screen.getByText("5 found · 4 imported · 1 already synced")).toBeInTheDocument();
  });

  it("shows a failed sync result with the backend's own error message", async () => {
    const onSync = vi.fn().mockResolvedValue({
      id: "run-1",
      linked_account_id: "link-1",
      started_at: "2026-09-18T10:00:00Z",
      completed_at: "2026-09-18T10:00:02Z",
      status: "failed",
      transactions_fetched: 0,
      transactions_created: 0,
      transactions_skipped_duplicate: 0,
      error_message: "Provider fetch failed: provider unreachable",
    } satisfies SyncRun);

    render(
      <LinkedAccountCard
        linkedAccount={buildLinkedAccount()}
        onSync={onSync}
        onRequestDisconnect={vi.fn()}
        onViewHistory={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Sync Now" }));

    expect(await screen.findByText("Sync failed")).toBeInTheDocument();
    expect(screen.getByText("Provider fetch failed: provider unreachable")).toBeInTheDocument();
  });

  it("shows a request-level error when the sync call itself fails", async () => {
    const onSync = vi
      .fn()
      .mockRejectedValue(
        new ApiError(422, { code: "validation_error", message: "consent not active", field_errors: null })
      );

    render(
      <LinkedAccountCard
        linkedAccount={buildLinkedAccount()}
        onSync={onSync}
        onRequestDisconnect={vi.fn()}
        onViewHistory={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Sync Now" }));

    expect(await screen.findByText("consent not active")).toBeInTheDocument();
  });

  it("hides the Sync Now button for a revoked (disconnected) link", () => {
    render(
      <LinkedAccountCard
        linkedAccount={buildLinkedAccount({ consent_status: "revoked" })}
        onSync={vi.fn()}
        onRequestDisconnect={vi.fn()}
        onViewHistory={vi.fn()}
      />
    );

    expect(screen.queryByRole("button", { name: "Sync Now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
  });
});
