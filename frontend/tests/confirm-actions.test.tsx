import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountCard } from "@/components/accounts/account-card";
import { MerchantRuleRow } from "@/components/merchant-rules/merchant-rule-row";
import { SubscriptionCard } from "@/components/subscriptions/subscription-card";
import type { Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import type { MerchantRule } from "@/lib/merchant-rules";
import type { Subscription } from "@/lib/subscriptions";

const account: Account = {
  id: "acc-1",
  name: "Checking",
  type: "bank_account",
  balance_minor: 1250050,
  currency: "INR",
  institution_name: null,
  is_active: true,
  credit_card: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const rule: MerchantRule = {
  id: "rule-1",
  merchant_key: "swiggy",
  category_id: "cat-1",
  category_name: "Food",
  category_icon: "🍔",
  category_color: "#F97316",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const subscription: Subscription = {
  id: "sub-1",
  recurring_transaction_id: "rec-1",
  name: "Netflix",
  account_id: "acc-1",
  account_name: "Checking",
  category_id: null,
  category_name: null,
  category_icon: null,
  category_color: null,
  amount_minor: 64900,
  currency: "INR",
  frequency: "monthly",
  monthly_cost_minor: 64900,
  yearly_cost_minor: 778800,
  next_renewal_date: "2026-11-01",
  is_active: true,
  is_possibly_unused: null,
  unused_reason: "Not enough data.",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const networkFailure = () => Promise.reject(new TypeError("Failed to fetch"));

describe("destructive actions never fail silently", () => {
  it("account card: shows the failure and keeps the confirmation open", async () => {
    render(<AccountCard account={account} onEdit={vi.fn()} onDelete={networkFailure} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't delete this account. Please try again."
    );
    expect(screen.getByRole("button", { name: "Confirm delete" })).toBeInTheDocument();
  });

  it("merchant rule row: shows the backend's own message", async () => {
    const onDelete = () =>
      Promise.reject(
        new ApiError(404, { code: "not_found", message: "Merchant rule not found.", field_errors: null })
      );
    render(<MerchantRuleRow rule={rule} onDelete={onDelete} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Merchant rule not found.");
  });

  it("subscription card: shows a deactivate failure", async () => {
    render(
      <SubscriptionCard subscription={subscription} onEdit={vi.fn()} onDeactivate={networkFailure} />
    );

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't deactivate this subscription. Please try again."
    );
  });

  it("closes the confirmation on success with no error", async () => {
    const onDelete = vi.fn().mockResolvedValue(undefined);
    render(<AccountCard account={account} onEdit={vi.fn()} onDelete={onDelete} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

    expect(await screen.findByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});
