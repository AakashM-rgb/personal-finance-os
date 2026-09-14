from app.services.quick_add_parser import parse_quick_add_text

SYSTEM_CATEGORIES = [
    "Food", "Transport", "Shopping", "Bills", "Entertainment", "Education",
    "Health", "Travel", "Subscriptions", "Rent", "Utilities", "Insurance",
    "Investment", "Other",
]


def _parse(text: str, custom: list[str] | None = None, system: list[str] | None = None):
    system_names = system if system is not None else SYSTEM_CATEGORIES
    return parse_quick_add_text(text, custom or [], system_names)


def test_exact_category_name_is_high_confidence_and_stripped_from_description() -> None:
    result = _parse("120 food lunch")
    assert result.amount_minor == 12000
    assert result.category_name == "Food"
    assert result.description == "Lunch"
    assert result.confidence == "high"
    assert result.error is None


def test_associated_keyword_is_medium_confidence_and_kept_in_description() -> None:
    result = _parse("450 uber college")
    assert result.amount_minor == 45000
    assert result.category_name == "Transport"
    assert result.description == "Uber college"
    assert result.confidence == "medium"


def test_rupee_symbol_prefix_is_supported() -> None:
    result = _parse("₹250 dinner")
    assert result.amount_minor == 25000
    assert result.category_name == "Food"
    assert result.confidence == "medium"


def test_rs_prefix_variants_are_supported() -> None:
    for text in ["Rs 300 groceries", "Rs. 300 groceries", "rs300 groceries", "INR 300 groceries"]:
        result = _parse(text)
        assert result.amount_minor == 30000, text
        assert result.category_name == "Food", text


def test_decimal_amount_is_parsed_without_floating_point_error() -> None:
    result = _parse("99.99 shopping")
    assert result.amount_minor == 9999


def test_single_decimal_digit_is_padded() -> None:
    result = _parse("10.5 food")
    assert result.amount_minor == 1050


def test_amount_only_with_no_remainder() -> None:
    result = _parse("500")
    assert result.amount_minor == 50000
    assert result.category_name is None
    assert result.description is None
    assert result.confidence == "low"
    assert result.error is None


def test_unmatched_words_leave_category_unset_rather_than_guessed() -> None:
    result = _parse("500 xyz nonsense")
    assert result.amount_minor == 50000
    assert result.category_name is None
    assert result.description == "Xyz nonsense"
    assert result.confidence == "low"


def test_no_leading_amount_is_reported_as_an_error_not_guessed() -> None:
    result = _parse("lunch with friends")
    assert result.amount_minor is None
    assert result.category_name is None
    assert result.error is not None


def test_zero_amount_is_rejected() -> None:
    result = _parse("0 food")
    assert result.amount_minor is None
    assert result.error is not None


def test_category_match_is_case_insensitive() -> None:
    result = _parse("120 FOOD lunch")
    assert result.category_name == "Food"
    assert result.description == "Lunch"


def test_empty_text_reports_an_error() -> None:
    result = _parse("")
    assert result.amount_minor is None
    assert result.error is not None


# --- custom category recognition (multi-word, tiered, ambiguity) --------------


def test_custom_category_name_matches_by_exact_single_word() -> None:
    result = _parse("200 petcare vet visit", custom=["PetCare"])
    assert result.category_name == "PetCare"
    assert result.description == "Vet visit"
    assert result.confidence == "high"


def test_custom_category_matches_multi_word_phrase() -> None:
    result = _parse("250 college snacks", custom=["College Snacks"])
    assert result.category_name == "College Snacks"
    assert result.confidence == "high"
    assert result.error is None


def test_custom_category_leaves_remaining_words_as_description() -> None:
    result = _parse("500 groceries weekly shopping", custom=["Groceries"])
    assert result.category_name == "Groceries"
    assert result.description == "Weekly shopping"
    assert result.confidence == "high"


def test_custom_category_preferred_over_incidental_default_category_word() -> None:
    # "shopping" is a default category name and appears in the text too, but
    # the custom category "Groceries" is the far more specific, deliberate
    # signal and must win.
    result = _parse("500 groceries weekly shopping", custom=["Groceries"], system=SYSTEM_CATEGORIES)
    assert result.category_name == "Groceries"


def test_keyword_ignored_if_category_not_visible_to_user() -> None:
    # "uber" implies Transport, but if the user doesn't have that category
    # (edge case - shouldn't happen with seeded defaults, but the parser
    # must never invent a category_id for a category that doesn't exist).
    result = _parse("450 uber college", system=["Food", "Other"])
    assert result.category_name is None
    assert result.description == "Uber college"
    assert result.confidence == "low"


def test_exact_match_preferred_over_keyword_match() -> None:
    # "Food" would also match via keyword ("lunch"), but the exact category
    # name "Lunch Club" should win since it's more specific.
    result = _parse("300 lunch club with friends", custom=["Lunch Club"])
    assert result.category_name == "Lunch Club"
    assert result.confidence == "high"


def test_longer_custom_category_wins_over_shorter_nested_match() -> None:
    result = _parse("500 gym membership fee", custom=["Gym", "Gym Membership"])
    assert result.category_name == "Gym Membership"
    assert result.confidence == "high"


def test_genuinely_ambiguous_categories_are_left_unset_for_confirmation() -> None:
    result = _parse("500 gym and groceries", custom=["Gym", "Groceries"])
    assert result.category_name is None
    assert result.confidence == "low"
    assert result.error is not None


def test_custom_categories_from_one_user_never_leak_matching_for_another() -> None:
    # Simulates: user A has no "Groceries" category, so it must fall through
    # to (no match), never matching against some other user's category -
    # the parser only ever sees the categories it's explicitly given.
    result = _parse("500 groceries weekly shopping", custom=[], system=SYSTEM_CATEGORIES)
    assert result.category_name == "Shopping"  # falls through to the default category only
    assert result.confidence == "high"
