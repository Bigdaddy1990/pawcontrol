"""Targeted coverage tests for select.py — uncovered paths (62% → 73%+).

Covers: PawControlFeedingModeSelect, PawControlFoodTypeSelect,
        PawControlDogSizeSelect, PawControlFeedingScheduleSelect
        constructors, current_option, options, extra_state_attributes
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.select import (
    PawControlDogSizeSelect,
    PawControlFeedingModeSelect,
    PawControlFeedingScheduleSelect,
    PawControlFoodTypeSelect,
)


def _coord(dog_id="rex"):
    c = MagicMock()
    c.data = {dog_id: {"feeding": {}, "walk": {}}}
    c.last_update_success = True
    c.get_dog_data = MagicMock(return_value={})
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlFeedingModeSelect
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_feeding_mode_select_init() -> None:
    s = PawControlFeedingModeSelect(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_feeding_mode_select_has_options() -> None:
    s = PawControlFeedingModeSelect(_coord(), "rex", "Rex")
    assert isinstance(s.options, list)
    assert len(s.options) > 0


@pytest.mark.unit
def test_feeding_mode_current_option_default() -> None:
    s = PawControlFeedingModeSelect(_coord(), "rex", "Rex")
    result = s.current_option
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_feeding_mode_extra_attrs() -> None:
    s = PawControlFeedingModeSelect(_coord(), "rex", "Rex")
    attrs = s.extra_state_attributes
    assert isinstance(attrs, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlFoodTypeSelect
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_food_type_select_init() -> None:
    s = PawControlFoodTypeSelect(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_food_type_select_options_non_empty() -> None:
    s = PawControlFoodTypeSelect(_coord(), "rex", "Rex")
    assert len(s.options) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlDogSizeSelect
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_dog_size_select_init() -> None:
    s = PawControlDogSizeSelect(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_dog_size_select_with_config() -> None:
    config = {"dog_id": "rex", "dog_name": "Rex", "dog_size": "large"}
    s = PawControlDogSizeSelect(_coord(), "rex", "Rex", dog_config=config)
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_dog_size_select_has_size_options() -> None:
    s = PawControlDogSizeSelect(_coord(), "rex", "Rex")
    opts = s.options
    assert isinstance(opts, list)
    assert len(opts) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlFeedingScheduleSelect
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_feeding_schedule_select_init() -> None:
    s = PawControlFeedingScheduleSelect(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_feeding_schedule_select_unique_id() -> None:
    s = PawControlFeedingScheduleSelect(_coord(), "rex", "Rex")
    assert "rex" in s._attr_unique_id
