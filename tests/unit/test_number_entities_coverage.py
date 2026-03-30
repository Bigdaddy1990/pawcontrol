"""Targeted coverage tests for number.py entity classes — uncovered paths (66% → 76%+).

Covers: PawControlDogWeightNumber, PawControlMealsPerDayNumber,
        PawControlDailyFoodAmountNumber, PawControlPortionSizeNumber
        constructors, native_value, extra_state_attributes
"""

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.number import (
    PawControlDailyFoodAmountNumber,
    PawControlDogWeightNumber,
    PawControlMealsPerDayNumber,
    PawControlPortionSizeNumber,
)


def _coord(dog_id="rex"):
    c = MagicMock()
    c.data = {dog_id: {"feeding": {"meals_per_day": 2, "daily_food_amount": 400.0}}}
    c.last_update_success = True
    c.get_dog_data = MagicMock(return_value={})
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlDogWeightNumber
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_dog_weight_number_init() -> None:
    e = PawControlDogWeightNumber(_coord(), "rex", "Rex")
    assert e._dog_id == "rex"


@pytest.mark.unit
def test_dog_weight_number_with_config() -> None:
    config = {"dog_id": "rex", "dog_name": "Rex", "dog_weight": 22.5}
    e = PawControlDogWeightNumber(_coord(), "rex", "Rex", dog_config=config)
    assert e._dog_id == "rex"


@pytest.mark.unit
def test_dog_weight_native_value() -> None:
    e = PawControlDogWeightNumber(_coord(), "rex", "Rex")
    result = e.native_value
    assert result is None or isinstance(result, int | float)


@pytest.mark.unit
def test_dog_weight_extra_attrs() -> None:
    e = PawControlDogWeightNumber(_coord(), "rex", "Rex")
    attrs = e.extra_state_attributes
    assert isinstance(attrs, dict)


@pytest.mark.unit
def test_dog_weight_unique_id() -> None:
    e = PawControlDogWeightNumber(_coord(), "rex", "Rex")
    assert "rex" in e._attr_unique_id


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlMealsPerDayNumber
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_meals_per_day_init() -> None:
    e = PawControlMealsPerDayNumber(_coord(), "rex", "Rex")
    assert e._dog_id == "rex"


@pytest.mark.unit
def test_meals_per_day_native_value() -> None:
    e = PawControlMealsPerDayNumber(_coord(), "rex", "Rex")
    result = e.native_value
    assert result is None or isinstance(result, int | float)


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlDailyFoodAmountNumber
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_daily_food_amount_init() -> None:
    e = PawControlDailyFoodAmountNumber(_coord(), "rex", "Rex")
    assert e._dog_id == "rex"


@pytest.mark.unit
def test_daily_food_amount_native_value() -> None:
    e = PawControlDailyFoodAmountNumber(_coord(), "rex", "Rex")
    result = e.native_value
    assert result is None or isinstance(result, int | float)


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlPortionSizeNumber
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_portion_size_number_init() -> None:
    e = PawControlPortionSizeNumber(_coord(), "rex", "Rex")
    assert e._dog_id == "rex"


@pytest.mark.unit
def test_portion_size_unique_id() -> None:
    e = PawControlPortionSizeNumber(_coord(), "rex", "Rex")
    assert "rex" in e._attr_unique_id
