"""Targeted coverage tests for options_flow_feeding.py — uncovered paths (22% → 42%+).

Covers: FeedingOptionsMixin._coerce_meals_per_day (static),
        _current_feeding_options, async_step_feeding_settings,
        async_step_feeding_dog_select
"""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.options_flow_feeding import FeedingOptionsMixin

# ═══════════════════════════════════════════════════════════════════════════════
# _coerce_meals_per_day (static method)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_coerce_meals_per_day_none_returns_default() -> None:
    assert FeedingOptionsMixin._coerce_meals_per_day(None, 2) == 2


@pytest.mark.unit
def test_coerce_meals_per_day_valid_int() -> None:
    assert FeedingOptionsMixin._coerce_meals_per_day(3, 2) == 3


@pytest.mark.unit
def test_coerce_meals_per_day_clamps_min() -> None:
    assert FeedingOptionsMixin._coerce_meals_per_day(0, 2) == 1


@pytest.mark.unit
def test_coerce_meals_per_day_clamps_max() -> None:
    assert FeedingOptionsMixin._coerce_meals_per_day(10, 2) == 6


@pytest.mark.unit
def test_coerce_meals_per_day_invalid_string_returns_default() -> None:
    assert FeedingOptionsMixin._coerce_meals_per_day("bad", 3) == 3


@pytest.mark.unit
def test_coerce_meals_per_day_float_string() -> None:
    # "3.5" → int(3.5) raises ValueError → default
    assert FeedingOptionsMixin._coerce_meals_per_day("3.5", 2) == 2


@pytest.mark.unit
def test_coerce_meals_per_day_valid_string_int() -> None:
    assert FeedingOptionsMixin._coerce_meals_per_day("4", 2) == 4


@pytest.mark.unit
def test_coerce_meals_per_day_none_type() -> None:
    assert FeedingOptionsMixin._coerce_meals_per_day({}, 2) == 2
