"""Safe percentage math shared by the AI tools that report a period-over-
period or share-of-total change. Pure and DB-free, same pattern as
app.services.analytics_calculations.determine_trend: a percentage is only
ever returned when the denominator is a genuine positive baseline to
express a share of - otherwise None, never a fabricated or divide-by-zero
value.
"""


def safe_percent_change(old_value: int, new_value: int) -> float | None:
    """Percent change from `old_value` to `new_value`, or None when
    `old_value` is not a positive baseline (zero or negative) - the same
    guard used throughout the app (e.g. dashboard_service, analytics_service)
    for a month-over-month delta."""
    if old_value <= 0:
        return None
    return round((new_value - old_value) / old_value * 100, 1)


def safe_percent_of(part: int, whole: int) -> float | None:
    """`part` as a percentage of `whole`, or None when `whole` is not a
    positive baseline."""
    if whole <= 0:
        return None
    return round(part / whole * 100, 1)
