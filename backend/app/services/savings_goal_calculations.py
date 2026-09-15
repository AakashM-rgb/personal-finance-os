"""Savings goal math: progress, remaining amount, and the required
monthly/weekly savings pace needed to hit the target date. Pure and
DB-free (same pattern as app.services.budget_calculations) so every
branch is unit-testable with plain numbers - nothing here is randomly
generated; a required-savings figure is either a real deterministic
rate or explicitly omitted (None) when the underlying math is undefined
(the target date has already arrived or passed and the goal is not yet
complete) rather than guessed.

Convention: a "month" is treated as exactly 30 days and a "week" as 7
days for the purposes of this pacing estimate - the same fixed divisor
everywhere in this module, so the monthly and weekly figures for a given
goal are always mutually consistent with each other.
"""

from datetime import date

_DAYS_PER_WEEK = 7
_DAYS_PER_MONTH = 30


def calculate_progress_percent(current_minor: int, target_minor: int) -> float:
    """0-100, rounded to one decimal place. `target_minor` is always > 0 by
    the time a goal is stored (enforced at creation), but the guard is kept
    here too since this is a pure function callable from anywhere."""
    if target_minor <= 0:
        return 0.0
    return round((current_minor / target_minor) * 100, 1)


def calculate_remaining_minor(current_minor: int, target_minor: int) -> int:
    """Never negative: current_minor can never exceed target_minor - the
    product does not support overfunded goals."""
    return max(target_minor - current_minor, 0)


def calculate_days_remaining(target_date: date, today: date) -> int:
    """Positive if the target date is in the future, 0 if it is today,
    negative if it has already passed."""
    return (target_date - today).days


def calculate_required_savings(
    remaining_minor: int, days_remaining: int
) -> tuple[int | None, int | None]:
    """Returns (required_monthly_minor, required_weekly_minor).

    - Goal already reached (remaining_minor <= 0): both are 0, regardless
      of the date - there is nothing left to save.
    - Otherwise, if the target date is today or has already passed
      (days_remaining <= 0): both are None - there is no future time
      window left to spread the remaining amount over, so a periodic rate
      is mathematically undefined rather than guessed.
    - Otherwise: a fixed-rate projection of
      remaining_minor * days_per_period / days_remaining, rounded to the
      nearest integer minor unit.
    """
    if remaining_minor <= 0:
        return 0, 0
    if days_remaining <= 0:
        return None, None

    monthly = round(remaining_minor * _DAYS_PER_MONTH / days_remaining)
    weekly = round(remaining_minor * _DAYS_PER_WEEK / days_remaining)
    return monthly, weekly
