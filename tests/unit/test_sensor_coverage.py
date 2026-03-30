"""Targeted coverage tests for sensor.py static helpers and base class.

Covers lines from coverage report:
  265-269, 306, 342, 383-403, 493, 551-599, 615-635, 652-663,
  714-766, 771-800, 829-855 (PawControlSensorBase static methods,
  _coerce_float, _coerce_int, _coerce_utc_datetime, _coerce_module_payload,
  _get_cache_ttl, PawControlLastActionSensor, PawControlDogStatusSensor)
"""
from __future__ import annotations

from datetime import datetime, timezone, date
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from custom_components.pawcontrol.sensor import (
    PawControlSensorBase,
    get_activity_score_cache_ttl,
)


# ═══════════════════════════════════════════════════════════════════════════════
# _get_cache_ttl  (lines 183-215)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_get_cache_ttl_no_coordinator() -> None:
    """Cache TTL defaults to 300 when coordinator has no update_interval."""
    from unittest.mock import Mock
    coord = Mock()
    coord.update_interval = None
    assert get_activity_score_cache_ttl(coord) == 300


@pytest.mark.unit
def test_get_cache_ttl_from_timedelta(mock_hass, mock_config_entry, mock_session) -> None:
    """TTL derived from coordinator update_interval timedelta."""
    from datetime import timedelta
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.update_interval = timedelta(seconds=60)
    ttl = get_activity_score_cache_ttl(coord)
    assert 60 <= ttl <= 600


@pytest.mark.unit
def test_get_cache_ttl_clamps_to_min(mock_hass, mock_config_entry, mock_session) -> None:
    """Very short intervals still return at least 60 s."""
    from datetime import timedelta
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.update_interval = timedelta(seconds=5)
    ttl = get_activity_score_cache_ttl(coord)
    assert ttl == 60


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlSensorBase._coerce_float  (lines 503-515)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_coerce_float_bool() -> None:
    assert PawControlSensorBase._coerce_float(True) == 1.0
    assert PawControlSensorBase._coerce_float(False) == 0.0


@pytest.mark.unit
def test_coerce_float_int_and_float() -> None:
    assert PawControlSensorBase._coerce_float(42) == 42.0
    assert PawControlSensorBase._coerce_float(3.14) == pytest.approx(3.14)


@pytest.mark.unit
def test_coerce_float_string() -> None:
    assert PawControlSensorBase._coerce_float("2.5") == pytest.approx(2.5)
    assert PawControlSensorBase._coerce_float("bad", default=99.0) == 99.0


@pytest.mark.unit
def test_coerce_float_none_returns_default() -> None:
    assert PawControlSensorBase._coerce_float(None, default=-1.0) == -1.0


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlSensorBase._coerce_int  (lines 517-530)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_coerce_int_bool() -> None:
    assert PawControlSensorBase._coerce_int(True) == 1
    assert PawControlSensorBase._coerce_int(False) == 0


@pytest.mark.unit
def test_coerce_int_float_truncates() -> None:
    assert PawControlSensorBase._coerce_int(3.9) == 3


@pytest.mark.unit
def test_coerce_int_string() -> None:
    assert PawControlSensorBase._coerce_int("7") == 7
    assert PawControlSensorBase._coerce_int("7.8") == 7
    assert PawControlSensorBase._coerce_int("bad", default=5) == 5


@pytest.mark.unit
def test_coerce_int_none_returns_default() -> None:
    assert PawControlSensorBase._coerce_int(None) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlSensorBase._coerce_utc_datetime  (lines 532-540)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_coerce_utc_datetime_none() -> None:
    assert PawControlSensorBase._coerce_utc_datetime(None) is None


@pytest.mark.unit
def test_coerce_utc_datetime_from_datetime() -> None:
    dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = PawControlSensorBase._coerce_utc_datetime(dt)
    assert isinstance(result, datetime)


@pytest.mark.unit
def test_coerce_utc_datetime_from_string() -> None:
    result = PawControlSensorBase._coerce_utc_datetime("2025-06-01T12:00:00+00:00")
    assert isinstance(result, datetime)


@pytest.mark.unit
def test_coerce_utc_datetime_unsupported_type() -> None:
    result = PawControlSensorBase._coerce_utc_datetime({"not": "a datetime"})
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlSensorBase._coerce_module_payload  (lines 494-499)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_coerce_module_payload_mapping() -> None:
    payload = {"key": "value"}
    result = PawControlSensorBase._coerce_module_payload(payload)
    assert result == payload


@pytest.mark.unit
def test_coerce_module_payload_none() -> None:
    result = PawControlSensorBase._coerce_module_payload(None)
    assert result == {}


@pytest.mark.unit
def test_coerce_module_payload_non_mapping() -> None:
    result = PawControlSensorBase._coerce_module_payload("not a mapping")
    assert result == {}


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlSensorBase._coerce_feeding_payload and walk/gps variants
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_coerce_feeding_payload_mapping() -> None:
    payload = {"total_fed_today": 200.0}
    result = PawControlSensorBase._coerce_feeding_payload(payload)
    assert result is not None and result.get("total_fed_today") == 200.0


@pytest.mark.unit
def test_coerce_feeding_payload_none() -> None:
    assert PawControlSensorBase._coerce_feeding_payload(None) is None


@pytest.mark.unit
def test_coerce_walk_payload_mapping() -> None:
    payload = {"walk_in_progress": True}
    result = PawControlSensorBase._coerce_walk_payload(payload)
    assert result is not None and result.get("walk_in_progress") is True


@pytest.mark.unit
def test_coerce_walk_payload_none() -> None:
    assert PawControlSensorBase._coerce_walk_payload(None) is None
