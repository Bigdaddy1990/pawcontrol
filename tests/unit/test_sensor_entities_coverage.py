"""Targeted coverage tests for sensor.py entity classes — uncovered paths (38% → 50%+).

Covers: PawControlActivityLevelSensor, PawControlCaloriesBurnedTodaySensor,
        PawControlCurrentWalkDurationSensor, PawControlAverageWalkDurationSensor,
        PawControlBodyConditionScoreSensor
        constructors, native_value, extra_state_attributes
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.sensor import (
    PawControlActivityLevelSensor,
    PawControlAverageWalkDurationSensor,
    PawControlBodyConditionScoreSensor,
    PawControlCaloriesBurnedTodaySensor,
    PawControlCurrentWalkDurationSensor,
)


def _coord(dog_id="rex"):
    c = MagicMock()
    c.data = {
        dog_id: {
            "walk": {
                "walk_in_progress": False,
                "walks_today": 0,
                "total_duration_today": 0.0,
                "total_distance_today": 0.0,
            },
            "feeding": {},
            "health": {},
        }
    }
    c.last_update_success = True
    c.get_dog_data = MagicMock(return_value={})
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlActivityLevelSensor
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_activity_level_sensor_init() -> None:
    s = PawControlActivityLevelSensor(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_activity_level_native_value() -> None:
    s = PawControlActivityLevelSensor(_coord(), "rex", "Rex")
    result = s.native_value
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_activity_level_extra_attrs() -> None:
    s = PawControlActivityLevelSensor(_coord(), "rex", "Rex")
    attrs = s.extra_state_attributes
    assert isinstance(attrs, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlCaloriesBurnedTodaySensor
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_calories_burned_sensor_init() -> None:
    s = PawControlCaloriesBurnedTodaySensor(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_calories_burned_native_value() -> None:
    s = PawControlCaloriesBurnedTodaySensor(_coord(), "rex", "Rex")
    result = s.native_value
    assert result is None or isinstance(result, int | float)


@pytest.mark.unit
def test_calories_burned_unique_id() -> None:
    s = PawControlCaloriesBurnedTodaySensor(_coord(), "rex", "Rex")
    assert "rex" in s._attr_unique_id


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlCurrentWalkDurationSensor
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_current_walk_duration_sensor_init() -> None:
    s = PawControlCurrentWalkDurationSensor(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_current_walk_duration_native_value() -> None:
    s = PawControlCurrentWalkDurationSensor(_coord(), "rex", "Rex")
    result = s.native_value
    assert result is None or isinstance(result, int | float)


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlAverageWalkDurationSensor
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_average_walk_duration_sensor_init() -> None:
    s = PawControlAverageWalkDurationSensor(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_average_walk_duration_native_value() -> None:
    s = PawControlAverageWalkDurationSensor(_coord(), "rex", "Rex")
    result = s.native_value
    assert result is None or isinstance(result, int | float)


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlBodyConditionScoreSensor
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_body_condition_score_sensor_init() -> None:
    s = PawControlBodyConditionScoreSensor(_coord(), "rex", "Rex")
    assert s._dog_id == "rex"


@pytest.mark.unit
def test_body_condition_score_native_value() -> None:
    s = PawControlBodyConditionScoreSensor(_coord(), "rex", "Rex")
    result = s.native_value
    assert result is None or isinstance(result, int | float | str)


@pytest.mark.unit
def test_body_condition_score_unique_id() -> None:
    s = PawControlBodyConditionScoreSensor(_coord(), "rex", "Rex")
    assert "rex" in s._attr_unique_id
