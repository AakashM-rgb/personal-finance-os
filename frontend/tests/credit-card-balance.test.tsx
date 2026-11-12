import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountCard } from "@/components/accounts/account-card";
import { AccountForm } from "@/components/accounts/account-form";
import { NetWorthReportView } from "@/components/reports/net-worth-report-view";
import {
  describeCardBalance,
  utilizationBarPercent,
  type Account,
  type AccountCreateInput,
  type AccountUpdateInput,
} from "@/lib/accounts";
import type { NetWorthReport } from "@/lib/reports";

vi.mock("@/components/reports/net-worth-trend-chart", () => ({
  NetWorthTrendChart: () => null,
}));

function card(balanceMinor: number, utilizationPercent: number): Account {
  return {
    id: "card-1",
    name: "Travel Card",
    type: "credit_card",
    balance_minor: balanceMinor,
    currency: "INR",
    institution_name: null,
    is_active: true,
    credit_card: {
      credit_limit_minor: 10000000,
      statement_day: 5,
      payment_due_day: 25,
      minimum_payment_minor: null,
      available_credit_minor: 10000000 - balanceMinor,
      utilization_percent: utilizationPercent,
    },
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function renderCard(account: Account) {
  render(<AccountCard account={account} onEdit={vi.fn()} onDelete={vi.fn()} />);
}

describe("describeCardBalance", () => {
  it("treats a positive balance as owed", () => {
    expect(describeCardBalance(250000)).toEqual({ amountMinor: 250000, label: "owed" });
  });

  it("treats zero as nothing owed", () => {
    expect(describeCardBalance(0)).toEqual({ amountMinor: 0, label: "owed" });
  });

  it("shows a negative balance as a positive credit balance", () => {
    expect(describeCardBalance(-5000)).toEqual({ amountMinor: 5000, label: "credit balance" });
  });
});

describe("utilizationBarPercent", () => {
  it.each([
    [-12.5, 0],
    [0, 0],
    [42.25, 42.25],
    [100, 100],
    [135, 100],
    [Number.NaN, 0],
  ])("clamps %s to %s", (input, expected) => {
    expect(utilizationBarPercent(input)).toBe(expected);
  });
});

describe("AccountCard credit-card balance", () => {
  it("shows a positive balance as the amount owed", () => {
    renderCard(card(3245000, 32.45));

    expect(screen.getByText("owed")).toBeInTheDocument();
    expect(screen.getByText(/₹32,450\.00/)).toBeInTheDocument();
    expect(screen.queryByText("credit balance")).not.toBeInTheDocument();
  });

  it("shows a negative balance as a credit balance, without a minus sign", () => {
    renderCard(card(-5000, 0));

    expect(screen.getByText("credit balance")).toBeInTheDocument();
    expect(screen.queryByText("owed")).not.toBeInTheDocument();
    expect(screen.getByText(/^₹50\.00/)).toBeInTheDocument();
    expect(screen.queryByText(/-₹50\.00/)).not.toBeInTheDocument();
  });

  it("never renders a negative utilization bar width", () => {
    renderCard(card(-5000, -0.05));

    const bar = screen.getByRole("progressbar", { name: "Credit utilization" });
    expect(bar).toHaveStyle({ width: "0%" });
    expect(bar).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText(/0\.00% utilized/)).toBeInTheDocument();
  });

  it("caps the bar at 100% when the card is over its limit", () => {
    renderCard(card(12000000, 120));

    const bar = screen.getByRole("progressbar", { name: "Credit utilization" });
    expect(bar).toHaveStyle({ width: "100%" });
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText(/120\.00% utilized/)).toBeInTheDocument();
  });

  it("labels a non-card account balance as a balance", () => {
    renderCard({ ...card(500000, 0), type: "bank_account", credit_card: null });

    expect(screen.getByText("balance")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});

describe("AccountForm credit-card balance field", () => {
  it("labels the card balance as the amount owed and explains credit balances", () => {
    render(<AccountForm account={card(250000, 2.5)} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    const input = screen.getByLabelText("Amount owed");
    expect(screen.queryByLabelText("Current usage")).not.toBeInTheDocument();
    expect(input).toHaveAccessibleDescription(
      "Enter a negative amount if the card has a credit balance."
    );
  });

  it("keeps the plain balance label for other account types", () => {
    render(<AccountForm onSubmit={vi.fn()} onCancel={vi.fn()} />);

    const input = screen.getByLabelText("Current balance");
    expect(input).not.toHaveAccessibleDescription();
  });

  it("submits a credit balance as a negative amount owed", async () => {
    const onSubmit = vi.fn<(input: AccountCreateInput | AccountUpdateInput) => Promise<void>>(
      () => Promise.resolve()
    );
    render(<AccountForm account={card(250000, 2.5)} onSubmit={onSubmit} onCancel={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Amount owed"), { target: { value: "-50.00" } });
    fireEvent.submit(screen.getByLabelText("Amount owed").closest("form") as HTMLFormElement);

    await vi.waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ balance_minor: -5000 });
  });
});

describe("NetWorthReportView liabilities", () => {
  const report: NetWorthReport = {
    currency: "INR",
    total_assets_minor: 1000000,
    total_liabilities_minor: 245000,
    net_worth_minor: 755000,
    accounts: [
      {
        account_id: "bank",
        name: "Savings",
        type: "bank_account",
        balance_minor: 1000000,
        currency: "INR",
        is_liability: false,
      },
      {
        account_id: "owed",
        name: "Travel Card",
        type: "credit_card",
        balance_minor: 250000,
        currency: "INR",
        is_liability: true,
      },
      {
        account_id: "credit",
        name: "Overpaid Card",
        type: "credit_card",
        balance_minor: -5000,
        currency: "INR",
        is_liability: true,
      },
    ],
    trend: [],
  };

  it("shows each card as owed or as a credit balance", () => {
    render(<NetWorthReportView report={report} />);

    const owedRow = screen.getByText("Travel Card").closest("li") as HTMLElement;
    expect(within(owedRow).getByText("owed")).toBeInTheDocument();
    expect(within(owedRow).getByText(/₹2,500\.00/)).toBeInTheDocument();

    const creditRow = screen.getByText("Overpaid Card").closest("li") as HTMLElement;
    expect(within(creditRow).getByText("credit balance")).toBeInTheDocument();
    expect(within(creditRow).queryByText(/-₹50\.00/)).not.toBeInTheDocument();
    expect(within(creditRow).getByText(/₹50\.00/)).toBeInTheDocument();
  });
});
