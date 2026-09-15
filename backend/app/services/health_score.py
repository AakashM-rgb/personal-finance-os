"""Financial Health Score: a deterministic 0-100 score computed from real
account/transaction data - never randomly generated (see CLAUDE.md
"Financial Calculation Rules"). Pure and DB-free by design, like
app.services.quick_add_parser, so every branch can be unit-tested with
plain numbers.

Only factors that can be computed from data this app actually has today are
included - budget adherence and emergency-fund coverage are deliberately
left out until the Budgets and Emergency Fund modules exist, rather than
faked from data that doesn't exist yet:

- Savings rate (35%): (income - expense) / income this month.
- Debt burden (25%): the highest credit-card utilization across the user's
  cards (the single worst card is more informative of real risk than an
  average across cards); 100 (no burden) when there are no credit cards.
- Recurring expense ratio (20%): the share of this month's spending flagged
  `is_recurring`; lower is scored higher (more flexibility).
- Spending consistency (20%): 100 minus the coefficient of variation
  (stddev / mean, as a percent) of daily expense totals so far this month;
  lower day-to-day variance scores higher.

A factor is left out of the weighted average entirely (not scored as 0)
when there isn't enough data to say anything meaningful about it - e.g. no
income and no expenses at all, or fewer than 5 days elapsed this month for
the consistency factor. If every factor is inapplicable, the overall score
is `None` rather than a fabricated number, and the caller should show an
empty state instead of a score.
"""

import statistics
from dataclasses import dataclass, field

_MIN_DAYS_FOR_CONSISTENCY = 5


@dataclass(frozen=True)
class HealthFactor:
    key: str
    label: str
    weight: float
    score: float | None
    detail: str
    is_positive: bool | None = None


@dataclass(frozen=True)
class HealthScoreResult:
    score: int | None
    label: str | None
    factors: list[HealthFactor] = field(default_factory=list)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _score_label(score: int) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Fair"
    return "Needs Attention"


def _savings_factor(total_income_minor: int, total_expense_minor: int) -> HealthFactor:
    if total_income_minor == 0 and total_expense_minor == 0:
        return HealthFactor(
            "savings_rate", "Savings rate", 0.35, None,
            "No income or expenses recorded yet this month.",
        )
    if total_income_minor == 0:
        return HealthFactor(
            "savings_rate", "Savings rate", 0.35, 0.0,
            "You've recorded spending but no income this month.",
        )
    savings_rate = (total_income_minor - total_expense_minor) / total_income_minor * 100
    score = _clamp(savings_rate / 30 * 100)
    detail = f"You saved {savings_rate:.0f}% of your income this month."
    return HealthFactor("savings_rate", "Savings rate", 0.35, score, detail)


def _debt_factor(credit_card_utilizations_percent: list[float]) -> HealthFactor:
    if not credit_card_utilizations_percent:
        return HealthFactor("debt_burden", "Debt burden", 0.25, 100.0, "No credit card debt.")
    worst = max(credit_card_utilizations_percent)
    score = _clamp(100 - worst)
    detail = f"Your highest credit card utilization is {worst:.0f}%."
    return HealthFactor("debt_burden", "Debt burden", 0.25, score, detail)


def _recurring_factor(recurring_expense_minor: int, total_expense_minor: int) -> HealthFactor:
    if total_expense_minor == 0:
        return HealthFactor(
            "recurring_ratio", "Recurring expense ratio", 0.20, None,
            "No expenses recorded yet this month.",
        )
    ratio_percent = recurring_expense_minor / total_expense_minor * 100
    score = _clamp(100 - ratio_percent)
    detail = f"Recurring expenses are {ratio_percent:.0f}% of your spending this month."
    return HealthFactor("recurring_ratio", "Recurring expense ratio", 0.20, score, detail)


def _consistency_factor(daily_expense_series: list[int], days_elapsed: int) -> HealthFactor:
    total = sum(daily_expense_series)
    if total == 0 or days_elapsed < _MIN_DAYS_FOR_CONSISTENCY:
        return HealthFactor(
            "spending_consistency", "Spending consistency", 0.20, None,
            "Not enough data yet this month.",
        )
    mean = statistics.fmean(daily_expense_series)
    stddev = statistics.pstdev(daily_expense_series)
    coefficient_of_variation = (stddev / mean) if mean > 0 else 0.0
    score = _clamp(100 - coefficient_of_variation * 100)
    detail = (
        "Your daily spending has been fairly consistent."
        if score >= 60
        else "Your daily spending varies a lot day to day."
    )
    return HealthFactor("spending_consistency", "Spending consistency", 0.20, score, detail)


def calculate_health_score(
    *,
    total_income_minor: int,
    total_expense_minor: int,
    credit_card_utilizations_percent: list[float],
    recurring_expense_minor: int,
    daily_expense_series: list[int],
    days_elapsed: int,
) -> HealthScoreResult:
    factors = [
        _savings_factor(total_income_minor, total_expense_minor),
        _debt_factor(credit_card_utilizations_percent),
        _recurring_factor(recurring_expense_minor, total_expense_minor),
        _consistency_factor(daily_expense_series, days_elapsed),
    ]

    # Debt burden defaults to a trivial 100 ("no cards, no debt") even with
    # zero activity - that default must never be the *sole* basis for a
    # score. A score requires actual income or expense activity this month;
    # otherwise "no debt" alone would misleadingly read as "Excellent".
    has_any_activity = total_income_minor > 0 or total_expense_minor > 0
    applicable = [f for f in factors if f.score is not None] if has_any_activity else []
    if not applicable:
        return HealthScoreResult(score=None, label=None, factors=factors)

    total_weight = sum(f.weight for f in applicable)
    weighted_scores = (f.weight / total_weight * f.score for f in applicable if f.score is not None)
    overall = round(sum(weighted_scores))

    resolved_factors = [
        f
        if f.score is None
        else HealthFactor(f.key, f.label, f.weight, f.score, f.detail, f.score >= 60)
        for f in factors
    ]
    return HealthScoreResult(score=overall, label=_score_label(overall), factors=resolved_factors)
