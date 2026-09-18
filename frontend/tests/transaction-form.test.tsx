import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TransactionForm } from "@/components/transactions/transaction-form";
import type { Account } from "@/lib/accounts";
import type { Category } from "@/lib/categories";
import type { Transaction } from "@/lib/transactions";

const account: Account = {
  id: "acc-1",
  name: "Checking",
  type: "bank_account",
  balance_minor: 100000,
  currency: "INR",
  institution_name: null,
  is_active: true,
  credit_card: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const shopping: Category = {
  id: "cat-shopping",
  name: "Shopping",
  icon: "🛍️",
  color: "#EC4899",
  budget_minor: null,
  parent_id: null,
  is_system: true,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const education: Category = {
  ...shopping,
  id: "cat-education",
  name: "Education",
  icon: "🎓",
};

function buildTransaction(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: "txn-1",
    account_id: account.id,
    transfer_account_id: null,
    category_id: shopping.id,
    type: "expense",
    amount_minor: 150000,
    currency: "INR",
    merchant: "ABC Education",
    description: null,
    notes: null,
    payment_method: null,
    tags: [],
    occurred_at: "2026-09-10T14:30:00Z",
    is_recurring: false,
    recurring_transaction_id: null,
    linked_account_id: null,
    needs_review: false,
    created_at: "2026-09-10T14:30:00Z",
    updated_at: "2026-09-10T14:30:00Z",
    ...overrides,
  };
}

describe("TransactionForm remember-category checkbox", () => {
  it("does not show the checkbox when creating a new transaction", () => {
    render(
      <TransactionForm
        accounts={[account]}
        categories={[shopping, education]}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.queryByText(/Remember this category/)).not.toBeInTheDocument();
  });

  it("does not show the checkbox when editing a transaction with no merchant", () => {
    render(
      <TransactionForm
        accounts={[account]}
        categories={[shopping, education]}
        transaction={buildTransaction({ merchant: null })}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.queryByText(/Remember this category/)).not.toBeInTheDocument();
  });

  it("shows the checkbox when editing a transaction with a merchant and category", () => {
    render(
      <TransactionForm
        accounts={[account]}
        categories={[shopping, education]}
        transaction={buildTransaction()}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByText('Remember this category for "ABC Education"')).toBeInTheDocument();
  });

  it("submits remember_category_for_merchant=false by default", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <TransactionForm
        accounts={[account]}
        categories={[shopping, education]}
        transaction={buildTransaction()}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ remember_category_for_merchant: false })
    );
  });

  it("submits remember_category_for_merchant=true when checked", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <TransactionForm
        accounts={[account]}
        categories={[shopping, education]}
        transaction={buildTransaction()}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText('Remember this category for "ABC Education"'));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ remember_category_for_merchant: true, category_id: shopping.id })
    );
  });

  it("hides the checkbox again once the category is cleared", () => {
    render(
      <TransactionForm
        accounts={[account]}
        categories={[shopping, education]}
        transaction={buildTransaction()}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    fireEvent.change(screen.getByLabelText("Category (optional)"), { target: { value: "" } });
    expect(screen.queryByText(/Remember this category/)).not.toBeInTheDocument();
  });
});
