import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AddExpenseSheet } from "@/components/expense-entry/add-expense-sheet";
import * as accountsLib from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import * as authContext from "@/lib/auth-context";
import * as categoriesLib from "@/lib/categories";
import { deleteDraft, getDraft, removeQueuedTransaction, saveDraft } from "@/lib/offline/db";
import { listQueue } from "@/lib/offline/sync-queue";
import * as transactionsLib from "@/lib/transactions";

vi.mock("@/lib/auth-context", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-context")>("@/lib/auth-context");
  return { ...actual, useAuth: vi.fn() };
});

const USER_ID = "user-add-sheet";

function mockAuthed() {
  vi.mocked(authContext.useAuth).mockReturnValue({
    user: {
      id: USER_ID,
      email: "a@b.com",
      full_name: "A B",
      is_active: true,
      email_verified_at: null,
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

const ACCOUNTS = [
  { id: "acc-1", name: "Main Bank", type: "bank_account", balance_minor: 0, currency: "INR", institution_name: null, is_active: true, credit_card: null, created_at: "", updated_at: "" },
] as unknown as accountsLib.Account[];

const CATEGORIES = [
  { id: "cat-1", name: "Food", icon: "🍔", color: "#f00", budget_minor: null, parent_id: null, is_system: true, is_active: true, created_at: "", updated_at: "" },
] as unknown as categoriesLib.Category[];

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, "onLine", { value, configurable: true });
}

function setup() {
  mockAuthed();
  vi.spyOn(accountsLib, "listAccounts").mockResolvedValue(ACCOUNTS);
  vi.spyOn(categoriesLib, "listCategories").mockResolvedValue(CATEGORIES);
  vi.spyOn(transactionsLib, "listTransactions").mockResolvedValue({ transactions: [], total: 0 });
}

afterEach(async () => {
  vi.restoreAllMocks();
  setOnline(true);
  await deleteDraft(USER_ID);
  const remaining = await listQueue(USER_ID);
  await Promise.all(remaining.map((item) => removeQueuedTransaction(USER_ID, item.id)));
});

describe("AddExpenseSheet - fast entry", () => {
  it("auto-focuses the amount field", async () => {
    setup();
    render(<AddExpenseSheet onClose={vi.fn()} onCreated={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText(/amount/i)).toHaveFocus());
  });

  it("lets the user pick a category via a one-tap chip", async () => {
    setup();
    render(<AddExpenseSheet onClose={vi.fn()} onCreated={vi.fn()} />);
    const chip = await screen.findByRole("button", { name: /food/i });
    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "true");
  });

  it("shows a validation error and preserves entered values when the amount is invalid", async () => {
    setup();
    render(<AddExpenseSheet onClose={vi.fn()} onCreated={vi.fn()} />);
    await screen.findByRole("button", { name: /food/i });

    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/valid amount/i);
    expect(screen.getByLabelText(/amount/i)).toHaveValue("0"); // never cleared on failure
  });
});

describe("AddExpenseSheet - online save", () => {
  it("saves directly via the transaction API when online", async () => {
    setup();
    const createSpy = vi
      .spyOn(transactionsLib, "createTransaction")
      .mockResolvedValue({ id: "server-1" } as never);
    const onCreated = vi.fn();

    render(<AddExpenseSheet onClose={vi.fn()} onCreated={onCreated} />);
    await screen.findByRole("button", { name: /food/i });

    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value: "250" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(createSpy).toHaveBeenCalledTimes(1);
    expect(createSpy.mock.calls[0][1]).toMatchObject({ amount_minor: 25000, account_id: "acc-1" });
    expect(typeof createSpy.mock.calls[0][2]).toBe("string"); // an idempotency key was sent
  });

  it("prevents a duplicate submission from a rapid double-click", async () => {
    setup();
    let resolveCreate: (value: transactionsLib.Transaction) => void = () => {};
    const createSpy = vi.spyOn(transactionsLib, "createTransaction").mockReturnValue(
      new Promise<transactionsLib.Transaction>((resolve) => {
        resolveCreate = resolve;
      })
    );

    render(<AddExpenseSheet onClose={vi.fn()} onCreated={vi.fn()} />);
    await screen.findByRole("button", { name: /food/i });
    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value: "99" } });

    const saveButton = screen.getByRole("button", { name: /^save$/i });
    fireEvent.click(saveButton);
    fireEvent.click(saveButton);
    fireEvent.click(saveButton);

    resolveCreate({ id: "server-1" } as transactionsLib.Transaction);
    await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
  });
});

describe("AddExpenseSheet - offline save", () => {
  it("queues the expense locally when the device is offline, never attempting the API", async () => {
    setup();
    setOnline(false);
    const createSpy = vi.spyOn(transactionsLib, "createTransaction");
    const onCreated = vi.fn();

    render(<AddExpenseSheet onClose={vi.fn()} onCreated={onCreated} />);
    await screen.findByRole("button", { name: /food/i });
    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value: "600" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(createSpy).not.toHaveBeenCalled();
    expect(await screen.findByRole("status")).toHaveTextContent(/saved offline/i);

    const queued = await listQueue(USER_ID);
    expect(queued).toHaveLength(1);
    expect(queued[0].payload.amount_minor).toBe(60000);
    expect(queued[0].status).toBe("pending");
  });

  it("falls back to the offline queue when a network error interrupts an online attempt, using the SAME idempotency key", async () => {
    setup();
    const createSpy = vi
      .spyOn(transactionsLib, "createTransaction")
      .mockRejectedValue(new TypeError("Failed to fetch"));

    render(<AddExpenseSheet onClose={vi.fn()} onCreated={vi.fn()} />);
    await screen.findByRole("button", { name: /food/i });
    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value: "300" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(async () => expect(await listQueue(USER_ID)).toHaveLength(1));
    const queued = await listQueue(USER_ID);
    const attemptedKey = createSpy.mock.calls[0][2];
    expect(queued[0].id).toBe(attemptedKey);
  });

  it("shows a real validation error from the server without queuing it (online, definitive rejection)", async () => {
    setup();
    vi.spyOn(transactionsLib, "createTransaction").mockRejectedValue(
      new ApiError(422, { code: "validation_error", message: "Amount must be greater than ₹0.", field_errors: null })
    );

    render(<AddExpenseSheet onClose={vi.fn()} onCreated={vi.fn()} />);
    await screen.findByRole("button", { name: /food/i });
    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/amount must be greater/i);
    expect(await listQueue(USER_ID)).toHaveLength(0); // a definitive rejection is never queued
  });
});

describe("AddExpenseSheet - draft persistence", () => {
  it("restores a previously saved draft on open", async () => {
    setup();
    await saveDraft({
      userId: USER_ID,
      amountInput: "888",
      categoryId: "cat-1",
      accountId: "acc-1",
      merchant: "Corner Store",
      note: "Snacks",
      date: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });

    render(<AddExpenseSheet onClose={vi.fn()} onCreated={vi.fn()} />);

    await waitFor(() => expect(screen.getByLabelText(/amount/i)).toHaveValue("888"));
    expect(screen.getByText(/continuing your unsaved draft/i)).toBeInTheDocument();
  });

  it("autosaves an in-progress entry so it survives an unexpected close", async () => {
    setup();
    render(<AddExpenseSheet onClose={vi.fn()} onCreated={vi.fn()} />);
    await screen.findByRole("button", { name: /food/i });

    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value: "42" } });

    await waitFor(async () => {
      const draft = await getDraft(USER_ID);
      expect(draft?.amountInput).toBe("42");
    });
  });

  it("discarding the draft clears it from storage and the form", async () => {
    setup();
    await saveDraft({
      userId: USER_ID,
      amountInput: "555",
      categoryId: null,
      accountId: null,
      merchant: "",
      note: "",
      date: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });

    render(<AddExpenseSheet onClose={vi.fn()} onCreated={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText(/amount/i)).toHaveValue("555"));

    fireEvent.click(screen.getByRole("button", { name: /discard/i }));

    await waitFor(() => expect(screen.getByLabelText(/amount/i)).toHaveValue(""));
    expect(await getDraft(USER_ID)).toBeNull();
  });
});
