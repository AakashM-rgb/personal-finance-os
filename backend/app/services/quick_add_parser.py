"""Fast expense-entry text parser: "120 food lunch" -> amount/category/description.

Pure and DB-free by design so it can be unit-tested exhaustively without a
database. It never fabricates a category or amount it isn't reasonably
confident about - an unmatched or ambiguous category is left `None`
(confidence "low") rather than guessed, and an unparseable amount is
reported as an error rather than defaulting to zero or any other made-up
value.

Matching rule, in order:

1. Custom (user-created) category names are checked FIRST, as whole-word
   phrases, case-insensitively - this covers multi-word names too
   ("College Snacks" matches "250 college snacks" as one phrase, not two
   separate word lookups). A custom-category match wins even if a generic
   default category name (e.g. "Shopping") also happens to appear
   incidentally in the same text, since a name the user deliberately
   created is far more likely to be the intended signal than an ordinary
   English word that happens to double as a default category's name.
2. If no custom category matches, default/system category names are
   checked the same way.
3. If more than one *equally specific* name matches within the same tier
   (a genuine tie, not one name nested inside a longer one), the category
   is left unset at "low" confidence with an explanatory `error` instead
   of guessing - ambiguous input must be confirmed by the user, never
   silently resolved.
4. Only once no exact name match exists at all does a static
   associated-keyword table (e.g. "uber" -> Transport) apply, at "medium"
   confidence, with the keyword word kept in the description since it
   also names the merchant ("450 uber college" -> Transport, "Uber
   college").

An exact category-name match strips that phrase out of the description
("120 food lunch" -> Food, "Lunch"); a keyword-association match keeps the
whole remainder as the description.
"""

import re
from dataclasses import dataclass

_AMOUNT_PATTERN = re.compile(r"^\s*(?:₹|[Rr][Ss]\.?|INR)?\s*(\d+(?:\.\d{1,2})?)\s*(.*)$")

# Associated keywords per default category - medium-confidence hints only,
# never used unless the category is actually visible to the user, and only
# once no exact category-name match (custom or default) was found at all.
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Food": [
        "food", "lunch", "dinner", "breakfast", "brunch", "snack",
        "restaurant", "cafe", "meal", "zomato", "swiggy", "grocery", "groceries",
    ],
    "Transport": [
        "transport", "uber", "ola", "taxi", "cab", "bus", "train", "metro",
        "fuel", "petrol", "diesel", "rapido", "auto",
    ],
    "Shopping": ["shopping", "amazon", "flipkart", "myntra", "mall", "store"],
    "Entertainment": ["entertainment", "movie", "concert", "game", "bookmyshow"],
    "Bills": ["bills", "bill", "recharge"],
    "Education": ["education", "course", "tuition", "fees", "class", "school"],
    "Health": ["health", "doctor", "medicine", "pharmacy", "hospital", "clinic"],
    "Travel": ["travel", "flight", "hotel", "airbnb", "trip", "vacation"],
    "Subscriptions": ["subscriptions", "subscription", "netflix", "spotify", "prime"],
    "Rent": ["rent", "landlord"],
    "Utilities": ["utilities", "electricity", "water", "gas", "wifi", "broadband", "internet"],
    "Insurance": ["insurance", "premium"],
    "Investment": ["investment", "mutual", "sip", "stock", "stocks"],
}

_AMBIGUOUS_ERROR = "More than one category could match - please choose one."


@dataclass(frozen=True)
class ParsedQuickAdd:
    amount_minor: int | None
    category_name: str | None
    description: str | None
    confidence: str  # "high" | "medium" | "low"
    error: str | None


def _parse_amount_to_minor(amount_str: str) -> int | None:
    if "." in amount_str:
        whole, frac = amount_str.split(".", 1)
        frac = frac.ljust(2, "0")[:2]
    else:
        whole, frac = amount_str, "00"
    try:
        return int(whole) * 100 + int(frac)
    except ValueError:
        return None


def _capitalize(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    return text[0].upper() + text[1:]


def _name_pattern(name: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(name.lower()) + r"\b", re.IGNORECASE)


def _best_exact_match(lower_remainder: str, names: list[str]) -> tuple[str | None, bool]:
    """Returns (matched_category_name, is_ambiguous) for the given tier of
    category names. A single match wins outright. Among several matches,
    one whose matched span fully contains every other match's span wins
    (e.g. "Gym Membership" textually contains "Gym" - one name nested
    inside a more specific one, not two different signals). If the matches
    occupy genuinely separate, non-overlapping parts of the text (e.g.
    "Gym" and "Groceries" both appearing in "gym and groceries"), that is
    real ambiguity - never guessed."""
    seen: dict[str, tuple[int, int]] = {}
    for name in names:
        found = _name_pattern(name).search(lower_remainder)
        if found and name not in seen:
            seen[name] = (found.start(), found.end())

    if not seen:
        return None, False
    if len(seen) == 1:
        return next(iter(seen)), False

    by_span_length = sorted(seen.items(), key=lambda item: item[1][1] - item[1][0], reverse=True)
    longest_name, (longest_start, longest_end) = by_span_length[0]
    all_nested = all(
        start >= longest_start and end <= longest_end
        for _, (start, end) in by_span_length[1:]
    )
    if all_nested:
        return longest_name, False
    return None, True


def parse_quick_add_text(
    text: str, custom_category_names: list[str], system_category_names: list[str]
) -> ParsedQuickAdd:
    match = _AMOUNT_PATTERN.match(text.strip())
    if not match:
        return ParsedQuickAdd(
            amount_minor=None,
            category_name=None,
            description=None,
            confidence="low",
            error="Couldn't find an amount at the start of the text.",
        )

    amount_minor = _parse_amount_to_minor(match.group(1))
    if amount_minor is None or amount_minor <= 0:
        return ParsedQuickAdd(
            amount_minor=None,
            category_name=None,
            description=None,
            confidence="low",
            error="Enter an amount greater than zero.",
        )

    remainder = match.group(2).strip()
    if not remainder:
        return ParsedQuickAdd(amount_minor, None, None, "low", None)

    lower_remainder = remainder.lower()

    for tier in (custom_category_names, system_category_names):
        matched_name, is_ambiguous = _best_exact_match(lower_remainder, tier)
        if is_ambiguous:
            return ParsedQuickAdd(
                amount_minor, None, _capitalize(remainder), "low", _AMBIGUOUS_ERROR
            )
        if matched_name is not None:
            remaining_text = _name_pattern(matched_name).sub("", remainder, count=1)
            remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
            return ParsedQuickAdd(
                amount_minor, matched_name, _capitalize(remaining_text), "high", None
            )

    lower_words = [w.lower().strip(".,!?") for w in remainder.split()]
    visible_names = {*custom_category_names, *system_category_names}
    for category_name, keywords in _CATEGORY_KEYWORDS.items():
        if category_name not in visible_names:
            continue
        if any(word in keywords for word in lower_words):
            return ParsedQuickAdd(
                amount_minor, category_name, _capitalize(remainder), "medium", None
            )

    return ParsedQuickAdd(amount_minor, None, _capitalize(remainder), "low", None)
