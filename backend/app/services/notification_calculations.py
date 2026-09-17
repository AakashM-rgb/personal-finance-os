"""Pure, deterministic notification-detection rules. DB-free (same pattern
as app.services.budget_calculations / app.services.subscription_calculations)
so every rule is unit-testable with plain numbers and dates.

PRODUCT_SPEC.md §35 lists the notification categories to support but does
not define exact thresholds or reminder windows for most of them (unlike
budgets, which already have documented thresholds - see below). Where the
spec is silent, this module documents the exact deterministic rule chosen,
per category:

- Budget warnings: reuses the EXISTING, already-documented thresholds from
  app.services.budget_calculations (_WARNING_THRESHOLD=70%,
  _EXCEEDED_THRESHOLD=100%) - not a new, second set of numbers for the same
  concept.
- Subscription / credit-card payment reminders: fires once a due date
  (a subscription's next_renewal_date, or a credit card's payment_due_day
  for the current/next cycle) is within REMINDER_WINDOW_DAYS days.
- Recurring expense reminders: fires once an active expense recurring
  transaction's next occurrence is within REMINDER_WINDOW_DAYS days -
  the same window as payment reminders, since both answer the same
  question ("something is about to charge me soon").
- Savings goal milestones: fires once when progress_percent first reaches
  each value in GOAL_MILESTONES (25/50/75/100), never re-fires for a
  milestone already passed.
- Unusual spending: an expense transaction is flagged if its amount is at
  least UNUSUAL_SPENDING_MULTIPLIER times the user's own trailing
  UNUSUAL_SPENDING_LOOKBACK_DAYS-day average expense amount in that same
  category, and that category has at least
  UNUSUAL_SPENDING_MIN_SAMPLE_SIZE prior expense transactions in the
  window to establish a meaningful baseline. Absent enough history, no
  claim is made - the same "insufficient evidence -> no claim, never a
  guessed anomaly" policy app.services.subscription_calculations already
  uses for unused-subscription detection, applied to the same problem
  shape (personal spending patterns vary too much to guess a universal
  threshold).
"""

REMINDER_WINDOW_DAYS = 3

GOAL_MILESTONES: tuple[int, ...] = (25, 50, 75, 100)

UNUSUAL_SPENDING_MULTIPLIER = 3.0
UNUSUAL_SPENDING_LOOKBACK_DAYS = 90
UNUSUAL_SPENDING_MIN_SAMPLE_SIZE = 5


def is_within_reminder_window(days_until_due: int) -> bool:
    """True from REMINDER_WINDOW_DAYS out through the due date itself
    (inclusive of 0), never for a date already in the past - a reminder
    for something that already happened isn't useful (PRODUCT_SPEC.md
    §35's "useful notifications only")."""
    return 0 <= days_until_due <= REMINDER_WINDOW_DAYS


def milestones_reached(progress_percent: float) -> list[int]:
    """Every milestone in GOAL_MILESTONES that progress_percent has reached
    so far, not just the highest - each has its own permanent dedupe_key
    (see app.services.notification_service), so generation naturally
    backfills any milestone a big single deposit jumped straight past
    (e.g. 10% -> 60% in one update still notifies 25% AND 50%, not just
    50%) without ever re-notifying one already sent."""
    return [m for m in GOAL_MILESTONES if progress_percent >= m]


def milestone_amount_minor(target_minor: int, milestone_percent: int) -> int:
    """The amount (integer minor units) that `milestone_percent` of
    `target_minor` represents - e.g. the 25% notification for a
    ₹1,00,000 target reports ₹25,000, not whatever the goal's current
    balance happens to be by generation time. Integer floor division only
    (never a float) per CLAUDE.md's money rules; for the milestones this
    module defines (25/50/75/100) this is exact whenever target_minor is
    a multiple of 4, and off by at most a few paise otherwise."""
    return (target_minor * milestone_percent) // 100


def is_unusual_expense(*, amount_minor: int, historical_amounts_minor: list[int]) -> bool:
    """`historical_amounts_minor` is the category's own prior expense
    amounts within UNUSUAL_SPENDING_LOOKBACK_DAYS, NOT including the
    transaction being evaluated. Returns False (never a guess) when there
    isn't enough history yet."""
    if len(historical_amounts_minor) < UNUSUAL_SPENDING_MIN_SAMPLE_SIZE:
        return False
    average = sum(historical_amounts_minor) / len(historical_amounts_minor)
    if average <= 0:
        return False
    return amount_minor >= average * UNUSUAL_SPENDING_MULTIPLIER
