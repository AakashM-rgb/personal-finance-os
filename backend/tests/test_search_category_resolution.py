import uuid
from datetime import UTC, datetime

from app.schemas.category import CategoryRead
from app.search.category_resolution import resolve_category_phrase


def _category(name: str, *, is_active: bool = True) -> CategoryRead:
    now = datetime.now(UTC)
    return CategoryRead(
        id=uuid.uuid4(),
        name=name,
        icon="X",
        color="#000000",
        budget_minor=None,
        parent_id=None,
        is_system=True,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def test_exact_match_case_insensitive() -> None:
    food = _category("Food")
    result = resolve_category_phrase("food", [food, _category("Transport")])
    assert result.matched is food
    assert result.ambiguous_candidates == []


def test_exact_match_with_whitespace_normalization() -> None:
    food = _category("Food")
    result = resolve_category_phrase("  food  ", [food])
    assert result.matched is food


def test_exact_match_wins_over_substring_matches() -> None:
    travel = _category("Travel")
    travel_insurance = _category("Travel Insurance")
    result = resolve_category_phrase("travel", [travel, travel_insurance])
    assert result.matched is travel
    assert result.ambiguous_candidates == []


def test_single_substring_match_is_unambiguous() -> None:
    transport = _category("Transport")
    result = resolve_category_phrase("transport", [transport, _category("Food")])
    assert result.matched is transport


def test_multiple_substring_matches_are_ambiguous() -> None:
    car_insurance = _category("Car Insurance")
    car_rental = _category("Car Rental")
    result = resolve_category_phrase("car", [car_insurance, car_rental, _category("Food")])
    assert result.matched is None
    assert len(result.ambiguous_candidates) == 2
    assert car_insurance in result.ambiguous_candidates
    assert car_rental in result.ambiguous_candidates


def test_no_match_returns_none_without_guessing() -> None:
    result = resolve_category_phrase(
        "zzz-not-a-category", [_category("Food"), _category("Transport")]
    )
    assert result.matched is None
    assert result.ambiguous_candidates == []


def test_empty_phrase_returns_no_match() -> None:
    result = resolve_category_phrase("   ", [_category("Food")])
    assert result.matched is None


def test_inactive_categories_are_never_matched() -> None:
    archived = _category("Old Category", is_active=False)
    result = resolve_category_phrase("old category", [archived])
    assert result.matched is None
    assert result.ambiguous_candidates == []
