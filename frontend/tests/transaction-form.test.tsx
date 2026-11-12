import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TransactionForm } from "@/components/transactions/transaction-form";
import type { Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
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

describe("TransactionForm shows every server validation failure", () => {
  const usdAccount: Account = { ...account, id: "acc-usd", name: "US Card", currency: "USD" };

  function renderForEditing(onSubmit: () => Promise<void>) {
    render(
      <TransactionForm
        accounts={[account, usdAccount]}
        categories={[shopping, education]}
        transaction={buildTransaction()}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  }

  it("shows an oversized merchant error next to the merchant field", async () => {
    renderForEditing(() =>
      Promise.reject(
        new ApiError(422, {
          code: "validation_error",
          message: "One or more fields are invalid.",
          field_errors: { merchant: "String should have at most 200 characters" },
        })
      )
    );

    expect(await screen.findByText("Must be 200 characters or fewer.")).toBeInTheDocument();
  });

  it("limits the merchant field to the backend's 200 characters", () => {
    renderForEditing(() => Promise.resolve());
    expect(screen.getByLabelText("Merchant (optional)")).toHaveAttribute("maxlength", "200");
  });

  it("shows the readable sentence for a missing transfer destination, not 'required'", async () => {
    renderForEditing(() =>
      Promise.reject(
        new ApiError(422, {
          code: "validation_error",
          message: "A destination account is required for transfers.",
          field_errors: { transfer_account_id: "required" },
        })
      )
    );
    // The transfer slot only renders for transfers, so the sentence must still
    // appear at form level rather than vanish.
    expect(
      await screen.findByText("A destination account is required for transfers.")
    ).toBeInTheDocument();
    expect(screen.queryByText("required")).not.toBeInTheDocument();
  });

  it("shows the currency-mismatch sentence under the destination for a transfer", async () => {
    const onSubmit = vi.fn().mockRejectedValue(
      new ApiError(422, {
        code: "validation_error",
        message: "Transfers between accounts in different currencies aren't supported yet.",
        field_errors: { transfer_account_id: "currency mismatch" },
      })
    );
    render(
      <TransactionForm
        accounts={[account, usdAccount]}
        categories={[shopping]}
        initial={{ type: "transfer" }}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />
    );
    fireEvent.change(screen.getByLabelText("Amount (INR)"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("To account"), { target: { value: "acc-usd" } });
    fireEvent.click(screen.getByRole("button", { name: "Add transaction" }));

    expect(
      await screen.findByText(
        "Transfers between accounts in different currencies aren't supported yet."
      )
    ).toBeInTheDocument();
    expect(screen.queryByText("currency mismatch")).not.toBeInTheDocument();
  });

  it("falls back to a friendly message when the request never reached the server", async () => {
    renderForEditing(() => Promise.reject(new TypeError("Failed to fetch")));
    expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
  });
});
