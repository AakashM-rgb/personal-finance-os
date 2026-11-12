"""Deterministic category suggestion shared by every feature that infers a
category from evidence it didn't get from the user directly: receipt OCR
evidence (merchant name, item descriptions - see app.services.receipt_service)
and automatic-sync evidence (a normalized merchant name from
app.services.merchant_normalization - see app.services.sync_service). Both
callers use this SAME module rather than maintaining their own copy, so a
category-matching rule is never defined twice and can never quietly diverge
between the two features.

Every suggestion here is a SUGGESTION only - callers decide for themselves
whether to auto-apply it (see each caller's own confidence rules) or hold it
for the user to confirm; this module has no opinion on that. Keywords/merchant
names are matched against real evidence, never randomly - if nothing
matches, a function returns None ("no reasonable suggestion"), never a
guess. Only category names actually present in the caller's `category_names`
are ever suggested, so this can never point at a category that doesn't
exist for that user.
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


# A small, curated map of well-known CANONICAL merchant names (as produced
# by app.services.merchant_normalization, never raw narration text) to the
# category they belong to - a stronger, higher-confidence signal than the
# generic keyword match above, since it depends on the merchant's identity
# already having been confidently recognized rather than a substring
# appearing somewhere in free text.
_CATEGORY_BY_KNOWN_MERCHANT: dict[str, str] = {
    "Swiggy": "Food",
    "Zomato": "Food",
    "Amazon": "Shopping",
    "Flipkart": "Shopping",
    "Netflix": "Subscriptions",
    "Spotify": "Subscriptions",
    "Uber": "Transport",
    "Ola": "Transport",
}


def suggest_category_for_known_merchant(
    *, canonical_merchant: str, category_names: list[str]
) -> str | None:
    category_name = _CATEGORY_BY_KNOWN_MERCHANT.get(canonical_merchant)
    if category_name is None:
        return None
    available = {name.lower(): name for name in category_names}
    return available.get(category_name.lower())
