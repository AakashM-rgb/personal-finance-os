from app.ai.tools.calculations import safe_percent_change, safe_percent_of


def test_safe_percent_change_normal_increase() -> None:
    assert safe_percent_change(1000, 1500) == 50.0


def test_safe_percent_change_normal_decrease() -> None:
    assert safe_percent_change(1000, 500) == -50.0


def test_safe_percent_change_zero_baseline_returns_none() -> None:
    assert safe_percent_change(0, 500) is None


def test_safe_percent_change_negative_baseline_returns_none() -> None:
    assert safe_percent_change(-100, 500) is None


def test_safe_percent_of_normal() -> None:
    assert safe_percent_of(250, 1000) == 25.0


def test_safe_percent_of_zero_whole_returns_none() -> None:
    assert safe_percent_of(100, 0) is None


def test_safe_percent_of_negative_whole_returns_none() -> None:
    assert safe_percent_of(100, -50) is None


def test_safe_percent_of_never_misrounds_due_to_floats() -> None:
    # 1/3 * 100 = 33.333...; rounding must be exact and deterministic.
    assert safe_percent_of(1, 3) == 33.3
