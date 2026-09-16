"""Deterministic, keyword-based category suggestion from receipt evidence
(merchant name, item descriptions). This is a SUGGESTION only - see
app.services.receipt_service, which never persists it as the confirmed
category; the user always has the final say.

Keywords are matched against real extracted text, never randomly - if
nothing matches, the function returns None ("no reasonable suggestion"),
never a guess. Only category names actually present in the caller's
`category_names` are ever suggested, so this can never point at a
category that doesn't exist for that user.
"""

# Ordered so a more specific match (e.g. "Subscriptions") is checked before
# a more generic one that could also apply.
_KEYWORDS_BY_CATEGORY: list[tuple[str, tuple[str, ...]]] = [
    ("Subscriptions", ("subscription", "spotify", "netflix", "prime membership")),
    ("Entertainment", ("cinema", "movie", "theatre", "concert", "multiplex")),
    (
        "Food",
        ("restaurant", "cafe", "grocery", "supermarket", "bakery", "kitchen", "diner", "pizza"),
    ),
    ("Transport", ("uber", "ola", "taxi", "petrol", "diesel", "fuel", "metro", "parking", "cab")),
    ("Health", ("pharmacy", "hospital", "clinic", "medical", "medicine", "diagnostic")),
    ("Shopping", ("mall", "store", "mart", "electronics", "apparel", "clothing", "boutique")),
    ("Travel", ("airlines", "airline", "hotel", "flight", "resort", "airbnb")),
    ("Utilities", ("electricity", "water bill", "broadband", "internet bill", "gas bill")),
    ("Insurance", ("insurance", "premium payment")),
    ("Education", ("school", "college", "tuition", "university", "course fee")),
    ("Rent", ("rent payment", "landlord")),
]


def suggest_category_name(
    *, merchant: str | None, item_descriptions: list[str], category_names: list[str]
) -> str | None:
    haystack = " ".join([merchant or "", *item_descriptions]).lower()
    if not haystack.strip():
        return None

    available = {name.lower(): name for name in category_names}
    for category_name, keywords in _KEYWORDS_BY_CATEGORY:
        if category_name.lower() not in available:
            continue
        if any(keyword in haystack for keyword in keywords):
            return available[category_name.lower()]
    return None
