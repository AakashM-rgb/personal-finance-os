import { describe, expect, it } from "vitest";

import { isOverdue, type RecurringTransaction } from "@/lib/recurring-transactions";

function makeRecurring(overrides: Partial<RecurringTransaction>): RecurringTransaction {
  return {
    id: "rec-1",
    name: "Netflix",
    account_id: "acc-1",
    account_name: "Main Bank",
    category_id: null,
    category_name: null,
    category_icon: null,
    category_color: null,
    type: "expense",
    amount_minor: 64900,
    currency: "INR",
    frequency: "monthly",
    start_date: "2026-01-01",
    next_occurrence_date: "2026-02-01",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("isOverdue", () => {
  it("is false when the next occurrence is in the future", () => {
    const recurring = makeRecurring({ next_occurrence_date: "2026-03-01" });
    expect(isOverdue(recurring, "2026-02-15")).toBe(false);
  });

  it("is false when the next occurrence is exactly today", () => {
    const recurring = makeRecurring({ next_occurrence_date: "2026-02-15" });
    expect(isOverdue(recurring, "2026-02-15")).toBe(false);
  });

  it("is true when the next occurrence has already passed and the schedule is active", () => {
    const recurring = makeRecurring({ next_occurrence_date: "2026-02-01", is_active: true });
    expect(isOverdue(recurring, "2026-02-15")).toBe(true);
  });

  it("is false when inactive, even if the next occurrence has passed", () => {
    const recurring = makeRecurring({ next_occurrence_date: "2026-02-01", is_active: false });
    expect(isOverdue(recurring, "2026-02-15")).toBe(false);
  });
});
