import { describe, expect, it } from "vitest";

import { getGoalStatus, type SavingsGoal } from "@/lib/goals";

function makeGoal(overrides: Partial<SavingsGoal>): SavingsGoal {
  return {
    id: "goal-1",
    name: "Test Goal",
    target_amount_minor: 100000,
    current_amount_minor: 50000,
    currency: "INR",
    target_date: "2027-01-01",
    progress_percent: 50.0,
    remaining_minor: 50000,
    is_completed: false,
    days_remaining: 30,
    required_monthly_savings_minor: 5000,
    required_weekly_savings_minor: 1200,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("getGoalStatus", () => {
  it("is completed when is_completed is true, even with a past target date", () => {
    const goal = makeGoal({ is_completed: true, days_remaining: -10 });
    expect(getGoalStatus(goal)).toBe("completed");
  });

  it("is overdue when the target date has passed and the goal isn't complete", () => {
    const goal = makeGoal({ is_completed: false, days_remaining: -1 });
    expect(getGoalStatus(goal)).toBe("overdue");
  });

  it("is due_today when the target date is exactly today", () => {
    const goal = makeGoal({ is_completed: false, days_remaining: 0 });
    expect(getGoalStatus(goal)).toBe("due_today");
  });

  it("is on_track when the target date is in the future and not complete", () => {
    const goal = makeGoal({ is_completed: false, days_remaining: 1 });
    expect(getGoalStatus(goal)).toBe("on_track");
  });
});
