"""Targeted coverage tests for binary_sensor.py — uncovered paths (43% → 56%+).

Covers: PawControlWalkInProgressBinarySensor, PawControlFeedingDueBinarySensor,
        PawControlActivityLevelConcernBinarySensor constructors,
        is_on property, extra_state_attributes
"""

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.binary_sensor import (
    PawControlActivityLevelConcernBinarySensor,
    PawControlFeedingDueBinarySensor,
    PawControlWalkInProgressBinarySensor,
)


def _coord(dog_id="rex"):
    c = MagicMock()
    c.data = {dog_id: {"walk": {"walk_in_progress": False}, "feeding": {}}}
    c.last_update_success = True
    c.get_dog_data = MagicMock(return_value={})
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlWalkInProgressBinarySensor
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_walk_in_progress_sensor_init() -> None:
    s = PawControlWalkInProgressBinarySensor(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_walk_in_progress_is_on_false() -> None:
    s = PawControlWalkInProgressBinarySensor(_coord(), "rex", "Rex")
    result = s.is_on
    assert isinstance(result, bool)


@pytest.mark.unit
def test_walk_in_progress_extra_attrs() -> None:
    s = PawControlWalkInProgressBinarySensor(_coord(), "rex", "Rex")
    attrs = s.extra_state_attributes
    assert isinstance(attrs, dict)


@pytest.mark.unit
def test_walk_in_progress_unique_id() -> None:
    s = PawControlWalkInProgressBinarySensor(_coord(), "rex", "Rex")
    assert "rex" in s._attr_unique_id


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlFeedingDueBinarySensor
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_feeding_due_sensor_init() -> None:
    s = PawControlFeedingDueBinarySensor(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_feeding_due_is_on_type() -> None:
    s = PawControlFeedingDueBinarySensor(_coord(), "rex", "Rex")
    result = s.is_on
    assert isinstance(result, bool)


@pytest.mark.unit
def test_feeding_due_extra_attrs() -> None:
    s = PawControlFeedingDueBinarySensor(_coord(), "rex", "Rex")
    attrs = s.extra_state_attributes
    assert isinstance(attrs, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlActivityLevelConcernBinarySensor
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_activity_concern_sensor_init() -> None:
    s = PawControlActivityLevelConcernBinarySensor(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_activity_concern_is_on_type() -> None:
    s = PawControlActivityLevelConcernBinarySensor(_coord(), "rex", "Rex")
    result = s.is_on
    assert isinstance(result, bool)


@pytest.mark.unit
def test_activity_concern_unique_id() -> None:
    s = PawControlActivityLevelConcernBinarySensor(_coord(), "rex", "Rex")
    assert "rex" in s._attr_unique_id
