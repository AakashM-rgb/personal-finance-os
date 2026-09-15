import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DayDetailModal } from "@/components/calendar/day-detail-modal";
import type { Account } from "@/lib/accounts";
import type { CalendarDay } from "@/lib/calendar";
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
  name: "Groceries",
  icon: "🛒",
  color: "#059669",
  budget_minor: null,
  parent_id: null,
  is_system: true,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function buildTransaction(overrides: Partial<Transaction>): Transaction {
  return {
    id: "txn-1",
    account_id: account.id,
    transfer_account_id: null,
    category_id: category.id,
    type: "expense",
    amount_minor: 45000,
    currency: "INR",
    merchant: null,
    description: "Supermarket run",
    notes: null,
    payment_method: null,
    tags: [],
    occurred_at: "2026-09-10T14:30:00Z",
    is_recurring: false,
    recurring_transaction_id: null,
    created_at: "2026-09-10T14:30:00Z",
    updated_at: "2026-09-10T14:30:00Z",
    ...overrides,
  };
}

function buildDay(overrides: Partial<CalendarDay> = {}): CalendarDay {
  return {
    date: "2026-09-10",
    income_minor: 0,
    expense_minor: 45000,
    net_minor: -45000,
    transactions: [],
    bills: [],
    ...overrides,
  };
}

describe("DayDetailModal", () => {
  it("shows a clean empty state when there are no transactions", () => {
    render(
      <DayDetailModal
        day={buildDay()}
        currency="INR"
        accounts={[account]}
        categories={[category]}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText("No transactions recorded on this day.")).toBeInTheDocument();
  });

  it("shows real transaction details: description, account, category, and amount", () => {
    render(
      <DayDetailModal
        day={buildDay({ transactions: [buildTransaction({})] })}
        currency="INR"
        accounts={[account]}
        categories={[category]}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText("Supermarket run")).toBeInTheDocument();
    expect(screen.getByText(/Checking/)).toBeInTheDocument();
    expect(screen.getByText(/Groceries/)).toBeInTheDocument();
    expect(screen.getByText("-₹450.00")).toBeInTheDocument();
  });

  it("labels a transfer transaction explicitly and never as income or expense", () => {
    render(
      <DayDetailModal
        day={buildDay({
          transactions: [
            buildTransaction({ type: "transfer", transfer_account_id: "acc-2", amount_minor: 200000 }),
          ],
        })}
        currency="INR"
        accounts={[account]}
        categories={[category]}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText(/Transfer/)).toBeInTheDocument();
    // A transfer's amount is shown without a +/- sign, unlike income/expense.
    expect(screen.getByText("₹2,000.00")).toBeInTheDocument();
  });

  it("shows a scheduled bill as not-yet-paid, distinct from real transactions", () => {
    render(
      <DayDetailModal
        day={buildDay({
          bills: [
            {
              recurring_transaction_id: "rt-1",
              name: "Netflix",
              type: "expense",
              amount_minor: 65000,
              currency: "INR",
              frequency: "monthly",
              is_subscription: true,
            },
          ],
        })}
        currency="INR"
        accounts={[account]}
        categories={[category]}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText("Scheduled (not yet paid)")).toBeInTheDocument();
    expect(screen.getByText("Netflix")).toBeInTheDocument();
    expect(screen.getByText("Subscription")).toBeInTheDocument();
    expect(screen.getByText("₹650.00")).toBeInTheDocument();
  });
});
