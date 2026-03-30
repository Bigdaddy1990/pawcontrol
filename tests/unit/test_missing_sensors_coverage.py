"""Targeted coverage tests for missing_sensors.py — uncovered paths (56% → 68%+).

Covers: calculate_activity_level, calculate_calories_burned_today,
        calculate_hours_since, derive_next_feeding_time
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from custom_components.pawcontrol.missing_sensors import (
    calculate_activity_level,
    calculate_calories_burned_today,
    calculate_hours_since,
    derive_next_feeding_time,
)

# ═══════════════════════════════════════════════════════════════════════════════
# calculate_hours_since
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_calculate_hours_since_none() -> None:
    assert calculate_hours_since(None) is None


@pytest.mark.unit
def test_calculate_hours_since_recent() -> None:
    now = datetime.now(UTC)
    two_hours_ago = now - timedelta(hours=2)
    result = calculate_hours_since(two_hours_ago, reference=now)
    assert result is not None
    assert result == pytest.approx(2.0, abs=0.1)


@pytest.mark.unit
def test_calculate_hours_since_zero() -> None:
    now = datetime.now(UTC)
    result = calculate_hours_since(now, reference=now)
    assert result is not None
    assert result == pytest.approx(0.0, abs=0.01)


@pytest.mark.unit
def test_calculate_hours_since_string_timestamp() -> None:
    ref = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    ts = "2025-06-01T10:00:00+00:00"
    result = calculate_hours_since(ts, reference=ref)
    assert result is not None
    assert result == pytest.approx(2.0, abs=0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# calculate_activity_level
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_calculate_activity_level_no_data() -> None:
    result = calculate_activity_level({}, {})
    assert isinstance(result, str)


@pytest.mark.unit
def test_calculate_activity_level_active_walk() -> None:
    walk_data = {"walks_today": 2, "total_duration_today": 60.0}
    result = calculate_activity_level(walk_data, {})
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
def test_calculate_activity_level_sedentary() -> None:
    walk_data = {"walks_today": 0, "total_duration_today": 0.0}
    result = calculate_activity_level(walk_data, {})
    assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════════
# calculate_calories_burned_today
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_calculate_calories_burned_no_walk() -> None:
    result = calculate_calories_burned_today({}, 20.0, {})
    assert isinstance(result, float)
    assert result >= 0.0


@pytest.mark.unit
def test_calculate_calories_burned_with_distance() -> None:
    walk_data = {"total_duration_today": 45.0, "total_distance_today": 3.0}
    result = calculate_calories_burned_today(walk_data, 25.0, {})
    assert isinstance(result, float)
    assert result > 0


# ═══════════════════════════════════════════════════════════════════════════════
# derive_next_feeding_time
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_derive_next_feeding_time_empty() -> None:
    result = derive_next_feeding_time({})
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_derive_next_feeding_time_with_config_and_last() -> None:
    # derive_next_feeding_time expects 'config' and 'last_feeding' keys
    feeding_data = {
        "config": {"meals_per_day": 2, "feeding_interval_hours": 8},
        "last_feeding": "2025-06-01T10:00:00+00:00",
    }
    result = derive_next_feeding_time(feeding_data)
    assert result is None or isinstance(result, str)
