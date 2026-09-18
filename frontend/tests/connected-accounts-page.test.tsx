import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ConnectedAccountsPage from "@/app/(app)/settings/connected-accounts/page";
import { ApiError } from "@/lib/api-client";
import * as authContext from "@/lib/auth-context";
import * as syncLib from "@/lib/sync";
import type { LinkedAccount, SyncRun } from "@/lib/sync";

vi.mock("@/lib/auth-context", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-context")>("@/lib/auth-context");
  return { ...actual, useAuth: vi.fn() };
});

function mockAuthed() {
  vi.mocked(authContext.useAuth).mockReturnValue({
    user: {
      id: "u1",
      email: "jane@example.com",
      full_name: "Jane Doe",
      is_active: true,
      email_verified_at: "2026-01-05T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    },
    accessToken: "token-123",
    isLoading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    logoutAll: vi.fn(),
  });
}

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

function buildSyncRun(overrides: Partial<SyncRun> = {}): SyncRun {
  return {
    id: "run-1",
    linked_account_id: "link-1",
    started_at: "2026-09-18T10:00:00Z",
    completed_at: "2026-09-18T10:00:05Z",
    status: "success",
    transactions_fetched: 5,
    transactions_created: 5,
    transactions_skipped_duplicate: 0,
    error_message: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ConnectedAccountsPage", () => {
  it("shows the empty state with a connect call-to-action", async () => {
    mockAuthed();
    vi.spyOn(syncLib, "listLinkedAccounts").mockResolvedValue([]);

    render(<ConnectedAccountsPage />);

    expect(await screen.findByText("No financial accounts connected.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ Connect Financial Account" })).toBeInTheDocument();
    expect(screen.getByText(/Read-only transaction access/)).toBeInTheDocument();
  });

  it("renders a connected account with its safe fields", async () => {
    mockAuthed();
    vi.spyOn(syncLib, "listLinkedAccounts").mockResolvedValue([
      buildLinkedAccount({ last_synced_at: "2026-09-17T08:00:00Z" }),
    ]);

    render(<ConnectedAccountsPage />);

    expect(await screen.findByText("Mock Bank")).toBeInTheDocument();
    expect(screen.getByText("XX4321")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText(/Last synced/)).toBeInTheDocument();
  });

  it("shows an error state with retry when the list fails to load", async () => {
    mockAuthed();
    vi.spyOn(syncLib, "listLinkedAccounts").mockRejectedValue(
      new ApiError(500, { code: "internal_error", message: "Something went wrong.", field_errors: null })
    );

    render(<ConnectedAccountsPage />);

    expect(await screen.findByText("Something went wrong.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("connects a mock account through initiateLink + completeLink and shows it in the list", async () => {
    mockAuthed();
    vi.spyOn(syncLib, "listLinkedAccounts")
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([buildLinkedAccount()]);
    const initiateSpy = vi.spyOn(syncLib, "initiateLink").mockResolvedValue({
      provider: "mock",
      consent_handle: "mock-consent-handle-u1",
      redirect_url: "https://mock-aa.invalid/consent/mock-consent-handle-u1",
      expires_at: "2027-01-01T00:00:00Z",
    });
    const completeSpy = vi.spyOn(syncLib, "completeLink").mockResolvedValue([buildLinkedAccount()]);

    render(<ConnectedAccountsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "+ Connect Financial Account" }));

    expect(await screen.findByText(/development\/demo connection/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Connect Mock Bank" }));

    await waitFor(() => expect(initiateSpy).toHaveBeenCalledWith("token-123"));
    await waitFor(() =>
      expect(completeSpy).toHaveBeenCalledWith("token-123", "mock-consent-handle-u1")
    );
    // Modal closes and the connected account now appears.
    await waitFor(() =>
      expect(screen.queryByText(/development\/demo connection/)).not.toBeInTheDocument()
    );
    expect(await screen.findByText("Mock Bank")).toBeInTheDocument();
  });

  it("shows a connection error and keeps the modal open for retry", async () => {
    mockAuthed();
    vi.spyOn(syncLib, "listLinkedAccounts").mockResolvedValue([]);
    vi.spyOn(syncLib, "initiateLink").mockRejectedValue(
      new ApiError(500, { code: "internal_error", message: "Provider unavailable.", field_errors: null })
    );

    render(<ConnectedAccountsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "+ Connect Financial Account" }));
    fireEvent.click(await screen.findByRole("button", { name: "Connect Mock Bank" }));

    expect(await screen.findByText("Provider unavailable.")).toBeInTheDocument();
    // Still open, so the user can retry or cancel.
    expect(screen.getByRole("button", { name: "Connect Mock Bank" })).toBeInTheDocument();
  });

  it("disconnects an account after confirmation and keeps it visible as disconnected", async () => {
    mockAuthed();
    vi.spyOn(syncLib, "listLinkedAccounts")
      .mockResolvedValueOnce([buildLinkedAccount()])
      .mockResolvedValueOnce([buildLinkedAccount({ consent_status: "revoked" })]);
    const revokeSpy = vi.spyOn(syncLib, "revokeLink").mockResolvedValue(
      buildLinkedAccount({ consent_status: "revoked" })
    );

    render(<ConnectedAccountsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Previously imported transactions remain/)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Disconnect" }));

    await waitFor(() => expect(revokeSpy).toHaveBeenCalledWith("token-123", "link-1"));
    expect(await screen.findByText("Disconnected")).toBeInTheDocument();
    // Confirmation dialog is gone.
    expect(screen.queryByText(/stops future synchronization/)).not.toBeInTheDocument();
  });

  it("never renders consent_handle, consent_id, or provider secrets", async () => {
    mockAuthed();
    vi.spyOn(syncLib, "listLinkedAccounts").mockResolvedValue([buildLinkedAccount()]);

    const { container } = render(<ConnectedAccountsPage />);
    await screen.findByText("Mock Bank");

    const rendered = container.textContent ?? "";
    expect(rendered).not.toMatch(/consent_handle/i);
    expect(rendered).not.toMatch(/consent_id/i);
    expect(rendered).not.toMatch(/mock-consent/i);
    expect(rendered).not.toMatch(/pin|cvv|otp/i);
  });

  it("triggers a sync and shows the real backend result without fabricating numbers", async () => {
    mockAuthed();
    vi.spyOn(syncLib, "listLinkedAccounts").mockResolvedValue([buildLinkedAccount()]);
    const syncSpy = vi.spyOn(syncLib, "triggerSync").mockResolvedValue(buildSyncRun());

    render(<ConnectedAccountsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Sync Now" }));

    await waitFor(() => expect(syncSpy).toHaveBeenCalledWith("token-123", "link-1"));
    expect(await screen.findByText("Sync completed")).toBeInTheDocument();
    expect(screen.getByText("5 found · 5 imported · 0 already synced")).toBeInTheDocument();
  });
});
