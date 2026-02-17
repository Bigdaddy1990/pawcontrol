"""Tests for ``validate_portion_size`` helper."""

import pytest

from custom_components.pawcontrol.utils import validate_portion_size


def _find_message(messages: list[str], needle: str) -> bool:
    """Return True if any message contains the needle."""  # noqa: E111

    return any(needle in message for message in messages)  # noqa: E111


def test_validate_portion_size_rejects_non_numeric_portion() -> None:
    """Non numeric portions should be marked invalid with actionable feedback."""  # noqa: E111

    result = validate_portion_size("not-a-number", 500)  # noqa: E111

    assert not result["valid"]  # noqa: E111
    assert _find_message(result["warnings"], "real number")  # noqa: E111
    assert result["percentage_of_daily"] == pytest.approx(0.0)  # noqa: E111


def test_validate_portion_size_handles_zero_meals_per_day() -> None:
    """Zero meals per day must not trigger a division by zero."""  # noqa: E111

    result = validate_portion_size(125, 500, meals_per_day=0)  # noqa: E111

    assert result["valid"]  # noqa: E111
    assert result["percentage_of_daily"] == pytest.approx(25.0, rel=1e-6)  # noqa: E111
    assert _find_message(result["warnings"], "Meals per day is not positive")  # noqa: E111


def test_validate_portion_size_rejects_non_positive_daily_amount() -> None:
    """Daily amount must be positive for the validation to succeed."""  # noqa: E111

    result = validate_portion_size(100, 0)  # noqa: E111

    assert not result["valid"]  # noqa: E111
    assert _find_message(result["warnings"], "Daily food amount")  # noqa: E111


def test_validate_portion_size_detects_portion_larger_than_daily_amount() -> None:
    """A portion larger than the configured daily amount should be invalid."""  # noqa: E111

    result = validate_portion_size(600, 500, meals_per_day=2)  # noqa: E111

    assert not result["valid"]  # noqa: E111
    assert _find_message(result["warnings"], "exceeds the configured daily amount")  # noqa: E111


def test_validate_portion_size_rejects_non_finite_values() -> None:
    """Non finite values such as NaN need to be rejected."""  # noqa: E111

    result = validate_portion_size(float("nan"), 500)  # noqa: E111

    assert not result["valid"]  # noqa: E111
    assert _find_message(result["warnings"], "finite number")  # noqa: E111


def test_validate_portion_size_flags_high_percentage() -> None:
    """Portions above 70% of the daily amount should fail validation."""  # noqa: E111

    result = validate_portion_size(400, 500, meals_per_day=3)  # noqa: E111

    assert not result["valid"]  # noqa: E111
    assert result["percentage_of_daily"] == pytest.approx(80.0)  # noqa: E111
    assert _find_message(result["warnings"], "exceeds 70% of daily requirement")  # noqa: E111


def test_validate_portion_size_warns_on_small_servings() -> None:
    """Very small portions should produce advisory warnings."""  # noqa: E111

    result = validate_portion_size(5, 500, meals_per_day=3)  # noqa: E111

    assert result["valid"]  # noqa: E111
    assert result["percentage_of_daily"] == pytest.approx(1.0)  # noqa: E111
    assert _find_message(  # noqa: E111
        result["warnings"], "Portion is very small compared to daily requirement"
    )


def test_validate_portion_size_warns_on_large_meal_relative_to_frequency() -> None:
    """Meals moderately above the per-meal target should raise advisory warnings."""  # noqa: E111

    result = validate_portion_size(200, 500, meals_per_day=4)  # noqa: E111

    assert result["valid"]  # noqa: E111
    assert result["percentage_of_daily"] == pytest.approx(40.0)  # noqa: E111
    assert _find_message(  # noqa: E111
        result["warnings"], "Portion is larger than typical for meal frequency"
    )
