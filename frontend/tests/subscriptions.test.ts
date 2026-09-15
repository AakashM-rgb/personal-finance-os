import { describe, expect, it } from "vitest";

import { calculateActiveTotals, type Subscription } from "@/lib/subscriptions";

function makeSubscription(overrides: Partial<Subscription>): Subscription {
  return {
    id: "sub-1",
    recurring_transaction_id: "rec-1",
    name: "Netflix",
    account_id: "acc-1",
    account_name: "Main Bank",
    category_id: null,
    category_name: null,
    category_icon: null,
    category_color: null,
    amount_minor: 64900,
    currency: "INR",
    frequency: "monthly",
    monthly_cost_minor: 64900,
    yearly_cost_minor: 778800,
    next_renewal_date: "2026-10-01",
    is_active: true,
    is_possibly_unused: null,
    unused_reason: "This subscription hasn't been billed yet.",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("calculateActiveTotals", () => {
  it("returns zero totals for an empty list", () => {
    expect(calculateActiveTotals([])).toEqual({ monthlyTotal: 0, yearlyTotal: 0 });
  });

  it("sums monthly and yearly cost across active subscriptions", () => {
    const subscriptions = [
      makeSubscription({ monthly_cost_minor: 64900, yearly_cost_minor: 778800 }),
      makeSubscription({ monthly_cost_minor: 11900, yearly_cost_minor: 142800 }),
    ];
    expect(calculateActiveTotals(subscriptions)).toEqual({
      monthlyTotal: 76800,
      yearlyTotal: 921600,
    });
  });

  it("excludes inactive subscriptions from both totals", () => {
    const subscriptions = [
      makeSubscription({ monthly_cost_minor: 64900, yearly_cost_minor: 778800, is_active: true }),
      makeSubscription({ monthly_cost_minor: 99900, yearly_cost_minor: 1198800, is_active: false }),
    ];
    expect(calculateActiveTotals(subscriptions)).toEqual({
      monthlyTotal: 64900,
      yearlyTotal: 778800,
    });
  });
});
