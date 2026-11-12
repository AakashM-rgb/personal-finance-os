import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TransactionDetails } from "@/components/transactions/transaction-details";
import { TransactionRow } from "@/components/transactions/transaction-row";
import type { Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import type { Category } from "@/lib/categories";
import type { Transaction } from "@/lib/transactions";

const account: Account = {
  id: "acc-1",
  name: "Checking",
  type: "bank_account",
  balance_minor: 0,
  currency: "INR",
  institution_name: null,
  is_active: true,
  credit_card: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const category: Category = {
  id: "cat-1",
  name: "Food",
  icon: "🍔",
  color: "#F97316",
  budget_minor: null,
  parent_id: null,
  is_system: true,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function buildTransaction(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: "txn-1",
    account_id: account.id,
    transfer_account_id: null,
    category_id: category.id,
    type: "expense",
    amount_minor: 39900,
    currency: "INR",
    merchant: "Swiggy",
    description: null,
    notes: null,
    payment_method: "upi",
    tags: [],
    occurred_at: "2026-09-01T00:00:00Z",
    is_recurring: false,
    recurring_transaction_id: null,
    linked_account_id: null,
    needs_review: false,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

const noop = () => Promise.resolve();

describe("TransactionRow source indicator", () => {
  it("shows no synced badge for a manually-created transaction", () => {
    render(
      <TransactionRow
        transaction={buildTransaction({ linked_account_id: null })}
        account={account}
        transferAccount={undefined}
        category={category}
        onView={vi.fn()}
        onEdit={vi.fn()}
        onDuplicate={noop}
        onDelete={noop}
      />
    );

    expect(screen.queryByText("🔄 Auto-synced")).not.toBeInTheDocument();
    expect(screen.queryByText("Needs review")).not.toBeInTheDocument();
  });

  it("shows the auto-synced badge for a transaction imported by sync", () => {
    render(
      <TransactionRow
        transaction={buildTransaction({ linked_account_id: "link-1", needs_review: false })}
        account={account}
        transferAccount={undefined}
        category={category}
        onView={vi.fn()}
        onEdit={vi.fn()}
        onDuplicate={noop}
        onDelete={noop}
      />
    );

    expect(screen.getByText("🔄 Auto-synced")).toBeInTheDocument();
    expect(screen.queryByText("Needs review")).not.toBeInTheDocument();
  });

  it("shows a needs-review badge for a low-confidence synced transaction", () => {
    render(
      <TransactionRow
        transaction={buildTransaction({ linked_account_id: "link-1", needs_review: true, category_id: null })}
        account={account}
        transferAccount={undefined}
        category={undefined}
        onView={vi.fn()}
        onEdit={vi.fn()}
        onDuplicate={noop}
        onDelete={noop}
      />
    );

    expect(screen.getByText("🔄 Auto-synced")).toBeInTheDocument();
    expect(screen.getByText("Needs review")).toBeInTheDocument();
  });
});

describe("TransactionDetails source field", () => {
  it("shows 'Manual' for a manually-created transaction", () => {
    render(
      <TransactionDetails
        transaction={buildTransaction({ linked_account_id: null })}
        account={account}
        transferAccount={undefined}
        category={category}
        onEdit={vi.fn()}
        onDuplicate={noop}
        onDelete={noop}
      />
    );

    expect(screen.getByText("Manual")).toBeInTheDocument();
    expect(screen.queryByText("Review")).not.toBeInTheDocument();
  });

  it("shows 'Automatically synced' and a review note for a low-confidence synced transaction", () => {
    render(
      <TransactionDetails
        transaction={buildTransaction({ linked_account_id: "link-1", needs_review: true })}
        account={account}
        transferAccount={undefined}
        category={category}
        onEdit={vi.fn()}
        onDuplicate={noop}
        onDelete={noop}
      />
    );

    expect(screen.getByText("🔄 Automatically synced")).toBeInTheDocument();
    expect(screen.getByText("Needs review - category not auto-assigned")).toBeInTheDocument();
  });
});

describe("TransactionRow actions surface failures instead of swallowing them", () => {
  function renderRow(overrides: {
    onDelete?: () => Promise<void>;
    onDuplicate?: () => Promise<void>;
  }) {
    render(
      <TransactionRow
        transaction={buildTransaction()}
        account={account}
        transferAccount={undefined}
        category={category}
        onView={vi.fn()}
        onEdit={vi.fn()}
        onDuplicate={overrides.onDuplicate ?? noop}
        onDelete={overrides.onDelete ?? noop}
      />
    );
  }

  it("shows the backend's message and keeps the confirmation open when a delete fails", async () => {
    const onDelete = vi
      .fn()
      .mockRejectedValue(
        new ApiError(404, { code: "not_found", message: "Transaction not found.", field_errors: null })
      );
    renderRow({ onDelete });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Transaction not found.");
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("never shows a raw network error - uses a friendly fallback", async () => {
    renderRow({ onDelete: vi.fn().mockRejectedValue(new TypeError("Failed to fetch")) });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't delete this transaction. Please try again.");
    expect(alert).not.toHaveTextContent("Failed to fetch");
  });

  it("clears the error when the confirmation is cancelled", async () => {
    renderRow({ onDelete: vi.fn().mockRejectedValue(new TypeError("Failed to fetch")) });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a message when duplicating fails", async () => {
    renderRow({ onDuplicate: vi.fn().mockRejectedValue(new TypeError("Failed to fetch")) });

    fireEvent.click(screen.getByRole("button", { name: "Duplicate" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't duplicate this transaction. Please try again."
    );
  });
});

describe("TransactionDetails actions surface failures", () => {
  it("shows a delete failure inside the details dialog", async () => {
    render(
      <TransactionDetails
        transaction={buildTransaction()}
        account={account}
        transferAccount={undefined}
        category={category}
        onEdit={vi.fn()}
        onDuplicate={noop}
        onDelete={vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't delete this transaction. Please try again."
    );
  });
});
