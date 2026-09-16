"""Deterministic resolution of a natural-language category phrase against
the authenticated user's REAL categories (system-seeded + their own
custom ones) - never a guess, never an invented category name.
"""

from dataclasses import dataclass, field

from app.schemas.category import CategoryRead


@dataclass(frozen=True)
class CategoryResolution:
    matched: CategoryRead | None
    ambiguous_candidates: list[CategoryRead] = field(default_factory=list)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def resolve_category_phrase(phrase: str, categories: list[CategoryRead]) -> CategoryResolution:
    """Exact (case/whitespace-insensitive) match wins outright, even if a
    looser substring match also exists elsewhere - an unambiguous "food"
    match against a "Food" category is never flagged as ambiguous just
    because some other category name happens to also contain "food".
    Substring matching is only tried when there is no exact match, and
    only counts as genuinely ambiguous when 2+ categories match that way;
    a single substring match is still a confident result."""
    normalized_phrase = _normalize(phrase)
    if not normalized_phrase:
        return CategoryResolution(matched=None)

    active = [c for c in categories if c.is_active]

    exact = [c for c in active if _normalize(c.name) == normalized_phrase]
    if len(exact) == 1:
        return CategoryResolution(matched=exact[0])
    if len(exact) > 1:
        # Two categories should never legitimately share an exact
        # (normalized) name for the same user - treat defensively as
        # ambiguous rather than picking one arbitrarily.
        return CategoryResolution(matched=None, ambiguous_candidates=exact)

    substring_matches = [
        c
        for c in active
        if normalized_phrase in _normalize(c.name) or _normalize(c.name) in normalized_phrase
    ]
    if len(substring_matches) == 1:
        return CategoryResolution(matched=substring_matches[0])
    if len(substring_matches) > 1:
        return CategoryResolution(matched=None, ambiguous_candidates=substring_matches)

    return CategoryResolution(matched=None)
