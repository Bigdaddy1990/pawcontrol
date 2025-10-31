"""Tests for ``validate_portion_size`` helper."""

from __future__ import annotations

import pytest
from custom_components.pawcontrol.utils import validate_portion_size


def _find_message(messages: list[str], needle: str) -> bool:
    """Return True if any message contains the needle."""

    return any(needle in message for message in messages)


def test_validate_portion_size_rejects_non_numeric_portion() -> None:
    """Non numeric portions should be marked invalid with actionable feedback."""

    result = validate_portion_size("not-a-number", 500)

    assert not result["valid"]
    assert _find_message(result["warnings"], "real number")
    assert result["percentage_of_daily"] == pytest.approx(0.0)


def test_validate_portion_size_handles_zero_meals_per_day() -> None:
    """Zero meals per day must not trigger a division by zero."""

    result = validate_portion_size(125, 500, meals_per_day=0)

    assert result["valid"]
    assert result["percentage_of_daily"] == pytest.approx(25.0, rel=1e-6)
    assert _find_message(result["warnings"], "Meals per day is not positive")


def test_validate_portion_size_rejects_non_positive_daily_amount() -> None:
    """Daily amount must be positive for the validation to succeed."""

    result = validate_portion_size(100, 0)

    assert not result["valid"]
    assert _find_message(result["warnings"], "Daily food amount")


def test_validate_portion_size_detects_portion_larger_than_daily_amount() -> None:
    """A portion larger than the configured daily amount should be invalid."""

    result = validate_portion_size(600, 500, meals_per_day=2)

    assert not result["valid"]
    assert _find_message(result["warnings"], "exceeds the configured daily amount")


def test_validate_portion_size_rejects_non_finite_values() -> None:
    """Non finite values such as NaN need to be rejected."""

    result = validate_portion_size(float("nan"), 500)

    assert not result["valid"]
    assert _find_message(result["warnings"], "finite number")


def test_validate_portion_size_flags_high_percentage() -> None:
    """Portions above 70% of the daily amount should fail validation."""

    result = validate_portion_size(400, 500, meals_per_day=3)

    assert not result["valid"]
    assert result["percentage_of_daily"] == pytest.approx(80.0)
    assert _find_message(result["warnings"], "exceeds 70% of daily requirement")


def test_validate_portion_size_warns_on_small_servings() -> None:
    """Very small portions should produce advisory warnings."""

    result = validate_portion_size(5, 500, meals_per_day=3)

    assert result["valid"]
    assert result["percentage_of_daily"] == pytest.approx(1.0)
    assert _find_message(
        result["warnings"], "Portion is very small compared to daily requirement"
    )
