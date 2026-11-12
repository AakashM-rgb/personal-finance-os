import { describe, expect, it } from "vitest";

import { demoHealthScore } from "@/components/marketing/demo-data";

// The real score's factors (backend/app/services/health_score.py). The demo
// may use illustrative numbers, but never a factor the product doesn't compute.
const REAL_FACTORS: Record<string, { label: string; weight: number }> = {
  savings_rate: { label: "Savings rate", weight: 0.35 },
  debt_burden: { label: "Debt burden", weight: 0.25 },
  recurring_ratio: { label: "Recurring expense ratio", weight: 0.2 },
  spending_consistency: { label: "Spending consistency", weight: 0.2 },
};

describe("landing page demo health score", () => {
  it("only shows factors the real score actually uses, with their real labels and weights", () => {
    for (const factor of demoHealthScore.factors) {
      expect(REAL_FACTORS[factor.key]).toEqual({ label: factor.label, weight: factor.weight });
    }
  });

  it("shows a score that is the real weighted average of its own factors", () => {
    const scored = demoHealthScore.factors.filter((f) => f.score !== null);
    const totalWeight = scored.reduce((sum, f) => sum + f.weight, 0);
    const expected = Math.round(
      scored.reduce((sum, f) => sum + (f.weight / totalWeight) * (f.score ?? 0), 0)
    );
    expect(demoHealthScore.score).toBe(expected);
  });

  it("marks factors positive exactly as the real score does (score >= 60)", () => {
    for (const factor of demoHealthScore.factors) {
      expect(factor.is_positive).toBe((factor.score ?? 0) >= 60);
    }
  });
});
