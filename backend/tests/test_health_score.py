from app.services.health_score import calculate_health_score


def test_score_is_none_when_there_is_no_data_at_all() -> None:
    result = calculate_health_score(
        total_income_minor=0,
        total_expense_minor=0,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[],
        days_elapsed=1,
    )
    assert result.score is None
    assert result.label is None
    # debt_burden legitimately reports 100 ("no cards, no debt") even here -
    # that's a true fact, it just must never be the *sole* basis for an
    # overall score (see the has_any_activity guard).
    non_debt_factors = [f for f in result.factors if f.key != "debt_burden"]
    assert all(f.score is None for f in non_debt_factors)


def test_strong_savings_and_no_debt_yields_a_high_score() -> None:
    result = calculate_health_score(
        total_income_minor=100000,
        total_expense_minor=60000,  # 40% savings rate
        credit_card_utilizations_percent=[],
        recurring_expense_minor=10000,  # ~17% of spending
        daily_expense_series=[2000] * 30,  # perfectly flat -> maximally consistent
        days_elapsed=30,
    )
    assert result.score is not None
    assert result.score >= 80
    assert result.label == "Excellent"


def test_overspending_with_no_income_yields_a_low_score() -> None:
    result = calculate_health_score(
        total_income_minor=0,
        total_expense_minor=50000,
        credit_card_utilizations_percent=[95.0],
        recurring_expense_minor=45000,
        daily_expense_series=[500, 5000, 100, 8000, 200],
        days_elapsed=5,
    )
    assert result.score is not None
    assert result.score < 40
    assert result.label == "Needs Attention"


def test_savings_rate_factor_scales_with_percentage() -> None:
    result = calculate_health_score(
        total_income_minor=100000,
        total_expense_minor=85000,  # 15% savings rate
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[],
        days_elapsed=1,
    )
    savings_factor = next(f for f in result.factors if f.key == "savings_rate")
    assert savings_factor.score is not None
    # 15% savings rate against a 30%-is-full-marks scale -> ~50
    assert 45 <= savings_factor.score <= 55


def test_savings_rate_is_inapplicable_with_zero_income_and_zero_expense() -> None:
    result = calculate_health_score(
        total_income_minor=0,
        total_expense_minor=0,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[],
        days_elapsed=1,
    )
    savings_factor = next(f for f in result.factors if f.key == "savings_rate")
    assert savings_factor.score is None


def test_spending_with_no_income_scores_savings_factor_at_zero() -> None:
    result = calculate_health_score(
        total_income_minor=0,
        total_expense_minor=50000,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[1000] * 30,
        days_elapsed=30,
    )
    savings_factor = next(f for f in result.factors if f.key == "savings_rate")
    assert savings_factor.score == 0.0


def test_debt_burden_uses_the_worst_credit_card_not_an_average() -> None:
    result = calculate_health_score(
        total_income_minor=100000,
        total_expense_minor=50000,
        credit_card_utilizations_percent=[10.0, 95.0],
        recurring_expense_minor=0,
        daily_expense_series=[1500] * 30,
        days_elapsed=30,
    )
    debt_factor = next(f for f in result.factors if f.key == "debt_burden")
    assert debt_factor.score is not None
    assert debt_factor.score == 5.0  # 100 - 95 (the worse of the two cards)


def test_no_credit_cards_means_full_marks_for_debt_burden() -> None:
    result = calculate_health_score(
        total_income_minor=100000,
        total_expense_minor=50000,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[1500] * 30,
        days_elapsed=30,
    )
    debt_factor = next(f for f in result.factors if f.key == "debt_burden")
    assert debt_factor.score == 100.0


def test_recurring_ratio_is_inapplicable_with_zero_expenses() -> None:
    result = calculate_health_score(
        total_income_minor=50000,
        total_expense_minor=0,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[],
        days_elapsed=1,
    )
    recurring_factor = next(f for f in result.factors if f.key == "recurring_ratio")
    assert recurring_factor.score is None


def test_all_recurring_expenses_score_the_recurring_factor_at_zero() -> None:
    result = calculate_health_score(
        total_income_minor=100000,
        total_expense_minor=40000,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=40000,
        daily_expense_series=[1300] * 30,
        days_elapsed=30,
    )
    recurring_factor = next(f for f in result.factors if f.key == "recurring_ratio")
    assert recurring_factor.score == 0.0


def test_consistency_factor_is_inapplicable_before_five_days_elapsed() -> None:
    result = calculate_health_score(
        total_income_minor=50000,
        total_expense_minor=5000,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[1000, 2000, 2000],
        days_elapsed=3,
    )
    consistency_factor = next(f for f in result.factors if f.key == "spending_consistency")
    assert consistency_factor.score is None


def test_perfectly_flat_daily_spending_scores_consistency_at_100() -> None:
    result = calculate_health_score(
        total_income_minor=50000,
        total_expense_minor=30000,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[1000] * 30,
        days_elapsed=30,
    )
    consistency_factor = next(f for f in result.factors if f.key == "spending_consistency")
    assert consistency_factor.score == 100.0


def test_highly_variable_daily_spending_scores_consistency_low() -> None:
    result = calculate_health_score(
        total_income_minor=50000,
        total_expense_minor=30000,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[0, 0, 0, 0, 30000],
        days_elapsed=5,
    )
    consistency_factor = next(f for f in result.factors if f.key == "spending_consistency")
    assert consistency_factor.score is not None
    assert consistency_factor.score < 30


def test_weights_are_redistributed_when_a_factor_is_inapplicable() -> None:
    # Only 3 days elapsed -> consistency factor drops out; the overall score
    # must still be computable from the remaining 3 factors, not crash or
    # silently zero out.
    result = calculate_health_score(
        total_income_minor=100000,
        total_expense_minor=50000,
        credit_card_utilizations_percent=[],
        recurring_expense_minor=0,
        daily_expense_series=[10000, 20000, 20000],
        days_elapsed=3,
    )
    assert result.score is not None
    assert 0 <= result.score <= 100


def test_score_is_always_between_zero_and_hundred() -> None:
    cases = [
        (0, 0, [], 0, [], 1),
        (1000000, 1, [0.0], 0, [1] * 30, 30),
        (1, 1000000, [100.0], 1000000, [50000] * 30, 30),
        (50000, 50000, [50.0], 25000, [1000, 3000, 500], 30),
    ]
    for income, expense, utilizations, recurring, series, days in cases:
        result = calculate_health_score(
            total_income_minor=income,
            total_expense_minor=expense,
            credit_card_utilizations_percent=utilizations,
            recurring_expense_minor=recurring,
            daily_expense_series=series,
            days_elapsed=days,
        )
        if result.score is not None:
            assert 0 <= result.score <= 100


def test_is_positive_flag_matches_the_sixty_point_threshold() -> None:
    result = calculate_health_score(
        total_income_minor=100000,
        total_expense_minor=60000,
        credit_card_utilizations_percent=[10.0],
        recurring_expense_minor=50000,
        daily_expense_series=[0, 0, 0, 0, 60000],
        days_elapsed=5,
    )
    for factor in result.factors:
        if factor.score is not None:
            assert factor.is_positive == (factor.score >= 60)
        else:
            assert factor.is_positive is None


def test_label_bands_match_the_documented_thresholds() -> None:
    assert calculate_health_score(
        total_income_minor=100000, total_expense_minor=50000,
        credit_card_utilizations_percent=[], recurring_expense_minor=0,
        daily_expense_series=[1600] * 30, days_elapsed=30,
    ).label == "Excellent"

    assert calculate_health_score(
        total_income_minor=100000, total_expense_minor=88000,
        credit_card_utilizations_percent=[30.0], recurring_expense_minor=40000,
        daily_expense_series=[2900] * 30, days_elapsed=30,
    ).label in {"Fair", "Good"}
