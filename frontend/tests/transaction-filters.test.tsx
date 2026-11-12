import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { TransactionFiltersBar } from "@/components/transactions/transaction-filters";
import type { Account } from "@/lib/accounts";
import type { TransactionFilters } from "@/lib/transactions";

const inr: Account = {
  id: "acc-inr",
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

const jpy: Account = { ...inr, id: "acc-jpy", name: "Tokyo", currency: "JPY" };

const BASE: TransactionFilters = { sort_by: "occurred_at", sort_dir: "desc", limit: 25, offset: 0 };

/** Renders the bar with real state, recording every filter change it applies. */
function renderBar(initial: TransactionFilters = BASE, accounts: Account[] = [inr]) {
  const changes: TransactionFilters[] = [];
  function Harness() {
    const [filters, setFilters] = useState(initial);
    return (
      <TransactionFiltersBar
        accounts={accounts}
        categories={[]}
        filters={filters}
        onChange={(next) => {
          changes.push(next);
          setFilters(next);
        }}
      />
    );
  }
  render(<Harness />);
  return { changes, last: () => changes[changes.length - 1] };
}

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("TransactionFiltersBar amount range", () => {
  it("lets the user type a decimal amount and applies it in paise", () => {
    const { last } = renderBar();

    type("Min amount", "12.");
    expect(screen.getByLabelText("Min amount")).toHaveValue("12.");
    expect(last().amount_min).toBe(1200);

    type("Min amount", "12.5");
    type("Min amount", "12.50");
    expect(screen.getByLabelText("Min amount")).toHaveValue("12.50");
    expect(last().amount_min).toBe(1250);
  });

  it("parses without floating-point error (0.29 is 29 paise, not 28.999…)", () => {
    const { last } = renderBar();
    type("Max amount", "0.29");
    expect(last().amount_max).toBe(29);
    type("Max amount", "1,00,000.10");
    expect(last().amount_max).toBe(10000010);
  });

  it("never sends NaN - invalid text shows a hint and drops that bound", () => {
    const { changes, last } = renderBar({ ...BASE, amount_min: 5000 });

    type("Min amount", "abc");

    expect(screen.getByText("Enter an amount like 250 or 99.50.")).toBeInTheDocument();
    expect(screen.getByLabelText("Min amount")).toHaveAttribute("aria-invalid", "true");
    expect(last().amount_min).toBeUndefined();
    expect(changes.every((f) => !Number.isNaN(f.amount_min))).toBe(true);
  });

  it("rejects more decimals than the currency has", () => {
    renderBar();
    type("Min amount", "10.505");
    expect(screen.getByText("Enter an amount like 250 or 99.50.")).toBeInTheDocument();
  });

  it("uses the filtered account's currency (JPY has no minor unit)", () => {
    const { last } = renderBar({ ...BASE, account_id: "acc-jpy" }, [inr, jpy]);
    type("Min amount", "1500");
    expect(last().amount_min).toBe(1500);
  });

  it("shows an existing applied bound as editable text", () => {
    renderBar({ ...BASE, amount_max: 99950 });
    expect(screen.getByLabelText("Max amount")).toHaveValue("999.50");
  });

  it("warns when min is greater than max", () => {
    renderBar({ ...BASE, amount_min: 50000, amount_max: 1000 });
    expect(screen.getByRole("alert")).toHaveTextContent(/min amount is greater than max/i);
  });

  it("resets to page 1 whenever the amount changes", () => {
    const { last } = renderBar({ ...BASE, offset: 50 });
    type("Min amount", "100");
    expect(last().offset).toBe(0);
  });
});

describe("TransactionFiltersBar clear filters", () => {
  it("is hidden when nothing is filtered", () => {
    renderBar();
    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
  });

  it("clears every filter, including amount text, but keeps the sort order", () => {
    const { last } = renderBar({
      ...BASE,
      sort_by: "amount_minor",
      sort_dir: "asc",
      q: "swiggy",
      amount_min: 10000,
      is_recurring: true,
    });
    type("Max amount", "oops");

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(last()).toEqual({ sort_by: "amount_minor", sort_dir: "asc", limit: 25, offset: 0 });
    expect(screen.getByLabelText("Min amount")).toHaveValue("");
    expect(screen.getByLabelText("Max amount")).toHaveValue("");
    expect(screen.queryByText("Enter an amount like 250 or 99.50.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
  });

  it("calls onChange exactly once per clear", () => {
    const onChange = vi.fn();
    render(
      <TransactionFiltersBar
        accounts={[inr]}
        categories={[]}
        filters={{ ...BASE, q: "rent" }}
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
