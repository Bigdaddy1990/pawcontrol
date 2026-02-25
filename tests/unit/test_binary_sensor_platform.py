"""Tests for binary_sensor platform helpers and sensor logic mixins.

Covers BinarySensorLogicMixin._calculate_time_based_status,
_evaluate_threshold, module-level helpers (_coerce_bool_flag,
_coerce_timestamp, _apply_standard_timing_attributes), and core
binary sensor class construction.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.binary_sensor import (
    BinarySensorLogicMixin,
    PawControlBinarySensorBase,
    _apply_standard_timing_attributes,
    _as_local,
    _coerce_bool_flag,
    _coerce_timestamp,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.types import CoordinatorDogData

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _CoordStub:
    """Minimal coordinator stub for binary sensor tests."""

    def __init__(self, dog_data: CoordinatorDogData | None = None) -> None:
        self.available = True
        self.last_update_success_time = None
        self._dog_data = dog_data or {}

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return cast(CoordinatorDogData, self._dog_data) if self._dog_data else None

    def get_module_data(self, dog_id: str, module: str) -> Mapping[str, Any]:
        return cast(Mapping[str, Any], self._dog_data.get(module, {}))

    def get_enabled_modules(self, dog_id: str) -> list[str]:
        return []


class _TestSensor(PawControlBinarySensorBase):
    """Minimal concrete sensor for testing base class behaviour."""

    def __init__(
        self, coordinator: _CoordStub, dog_id: str = "rex", dog_name: str = "Rex"
    ) -> None:  # noqa: E501
        super().__init__(
            cast(PawControlCoordinator, coordinator),
            dog_id,
            dog_name,
            "test_sensor",
        )

    def _get_is_on_state(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# _coerce_bool_flag
# ---------------------------------------------------------------------------


class TestCoerceBoolFlag:
    """Tests for the _coerce_bool_flag helper."""

    def test_true_returns_true(self) -> None:
        assert _coerce_bool_flag(True) is True

    def test_false_returns_false(self) -> None:
        assert _coerce_bool_flag(False) is False

    def test_int_one_returns_true(self) -> None:
        assert _coerce_bool_flag(1) is True

    def test_int_zero_returns_false(self) -> None:
        assert _coerce_bool_flag(0) is False

    def test_float_one_returns_true(self) -> None:
        assert _coerce_bool_flag(1.0) is True

    def test_float_zero_returns_false(self) -> None:
        assert _coerce_bool_flag(0.0) is False

    def test_string_returns_none(self) -> None:
        assert _coerce_bool_flag("true") is None

    def test_none_returns_none(self) -> None:
        assert _coerce_bool_flag(None) is None

    def test_arbitrary_int_returns_none(self) -> None:
        assert _coerce_bool_flag(5) is None


# ---------------------------------------------------------------------------
# _coerce_timestamp
# ---------------------------------------------------------------------------


class TestCoerceTimestamp:
    """Tests for the _coerce_timestamp helper."""

    def test_none_returns_none(self) -> None:
        assert _coerce_timestamp(None) is None

    def test_datetime_returns_datetime(self) -> None:
        dt = datetime.now(UTC)
        result = _coerce_timestamp(dt)
        assert isinstance(result, datetime)

    def test_iso_string_returns_datetime(self) -> None:
        result = _coerce_timestamp("2025-01-01T12:00:00+00:00")
        assert isinstance(result, datetime)

    def test_timestamp_int_returns_datetime(self) -> None:
        result = _coerce_timestamp(1700000000)
        assert isinstance(result, datetime)

    def test_unsupported_type_returns_none(self) -> None:
        assert _coerce_timestamp({"nested": "dict"}) is None


# ---------------------------------------------------------------------------
# _apply_standard_timing_attributes
# ---------------------------------------------------------------------------


class TestApplyStandardTimingAttributes:
    """Tests for _apply_standard_timing_attributes."""

    def test_populates_started_at_from_string(self) -> None:
        attrs: dict[str, Any] = {}
        _apply_standard_timing_attributes(
            attrs,
            started_at="2025-01-01T12:00:00+00:00",
            duration_minutes=30,
            last_seen=None,
        )
        assert isinstance(attrs.get("started_at"), datetime)

    def test_duration_minutes_set_for_numeric_values(self) -> None:
        attrs: dict[str, Any] = {}
        _apply_standard_timing_attributes(
            attrs,
            started_at=None,
            duration_minutes=45.0,
            last_seen=None,
        )
        assert attrs["duration_minutes"] == 45.0

    def test_duration_minutes_none_for_non_numeric(self) -> None:
        attrs: dict[str, Any] = {}
        _apply_standard_timing_attributes(
            attrs,
            started_at=None,
            duration_minutes="not-a-number",
            last_seen=None,
        )
        assert attrs["duration_minutes"] is None

    def test_last_seen_populated_from_datetime(self) -> None:
        attrs: dict[str, Any] = {}
        now = datetime.now(UTC)
        _apply_standard_timing_attributes(
            attrs,
            started_at=None,
            duration_minutes=None,
            last_seen=now,
        )
        assert isinstance(attrs.get("last_seen"), datetime)


# ---------------------------------------------------------------------------
# BinarySensorLogicMixin
# ---------------------------------------------------------------------------


class TestBinarySensorLogicMixin:
    """Tests for BinarySensorLogicMixin calculation helpers."""

    @pytest.fixture
    def mixin(self) -> BinarySensorLogicMixin:
        return BinarySensorLogicMixin()

    def test_time_based_status_true_within_threshold(
        self, mixin: BinarySensorLogicMixin
    ) -> None:  # noqa: E501
        recent = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        assert mixin._calculate_time_based_status(recent, 0.5) is True

    def test_time_based_status_false_outside_threshold(
        self, mixin: BinarySensorLogicMixin
    ) -> None:  # noqa: E501
        old_ts = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        assert mixin._calculate_time_based_status(old_ts, 0.5) is False

    def test_time_based_status_default_when_none(
        self, mixin: BinarySensorLogicMixin
    ) -> None:  # noqa: E501
        assert mixin._calculate_time_based_status(None, 1.0, True) is True
        assert mixin._calculate_time_based_status(None, 1.0, False) is False

    def test_time_based_status_false_on_empty_string(
        self, mixin: BinarySensorLogicMixin
    ) -> None:  # noqa: E501
        assert mixin._calculate_time_based_status("", 1.0) is False

    def test_evaluate_threshold_greater(self, mixin: BinarySensorLogicMixin) -> None:
        assert mixin._evaluate_threshold(10, 5, "greater") is True
        assert mixin._evaluate_threshold(4, 5, "greater") is False

    def test_evaluate_threshold_less(self, mixin: BinarySensorLogicMixin) -> None:
        assert mixin._evaluate_threshold(3, 5, "less") is True
        assert mixin._evaluate_threshold(6, 5, "less") is False

    def test_evaluate_threshold_greater_equal(
        self, mixin: BinarySensorLogicMixin
    ) -> None:  # noqa: E501
        assert mixin._evaluate_threshold(5, 5, "greater_equal") is True
        assert mixin._evaluate_threshold(4, 5, "greater_equal") is False

    def test_evaluate_threshold_less_equal(self, mixin: BinarySensorLogicMixin) -> None:
        assert mixin._evaluate_threshold(5, 5, "less_equal") is True
        assert mixin._evaluate_threshold(6, 5, "less_equal") is False

    def test_evaluate_threshold_none_returns_default(
        self, mixin: BinarySensorLogicMixin
    ) -> None:  # noqa: E501
        assert mixin._evaluate_threshold(None, 5, "greater", True) is True
        assert mixin._evaluate_threshold(None, 5, "greater", False) is False

    def test_evaluate_threshold_unknown_comparison(
        self, mixin: BinarySensorLogicMixin
    ) -> None:  # noqa: E501
        assert mixin._evaluate_threshold(10, 5, "unknown_op") is False


# ---------------------------------------------------------------------------
# PawControlBinarySensorBase
# ---------------------------------------------------------------------------


class TestPawControlBinarySensorBase:
    """Tests for PawControlBinarySensorBase core properties."""

    def _make_sensor(self, dog_data: CoordinatorDogData | None = None) -> _TestSensor:
        coord = _CoordStub(dog_data)
        return _TestSensor(coord)

    def test_unique_id_uses_dog_id_and_sensor_type(self) -> None:
        sensor = self._make_sensor()
        assert sensor._attr_unique_id == "pawcontrol_rex_test_sensor"

    def test_is_on_delegates_to_get_is_on_state(self) -> None:
        sensor = self._make_sensor()
        assert sensor.is_on is False

    def test_icon_returns_info_outline_when_no_icons_configured(self) -> None:
        sensor = self._make_sensor()
        assert sensor.icon == "mdi:information-outline"

    def test_icon_on_returned_when_sensor_active(self) -> None:
        coord = _CoordStub()
        sensor = PawControlBinarySensorBase(
            cast(PawControlCoordinator, coord),
            "rex",
            "Rex",
            "conn",
            icon_on="mdi:wifi",
            icon_off="mdi:wifi-off",
        )
        sensor._test_is_on = True
        assert sensor.icon == "mdi:wifi"

    def test_icon_off_returned_when_sensor_inactive(self) -> None:
        coord = _CoordStub()
        sensor = PawControlBinarySensorBase(
            cast(PawControlCoordinator, coord),
            "rex",
            "Rex",
            "conn",
            icon_on="mdi:wifi",
            icon_off="mdi:wifi-off",
        )
        assert sensor.icon == "mdi:wifi-off"

    def test_available_false_when_coordinator_unavailable(self) -> None:
        coord = _CoordStub()
        coord.available = False
        sensor = self._make_sensor()
        sensor.coordinator.available = False
        assert sensor.available is False

    def test_extra_state_attributes_contains_sensor_type(self) -> None:
        sensor = self._make_sensor(cast(CoordinatorDogData, {"status": "online"}))
        attrs = sensor.extra_state_attributes
        assert attrs.get("sensor_type") == "test_sensor"

    def test_translation_key_matches_sensor_type(self) -> None:
        sensor = self._make_sensor()
        assert sensor._attr_translation_key == "test_sensor"


# ---------------------------------------------------------------------------
# _as_local
# ---------------------------------------------------------------------------


class TestAsLocal:
    """Tests for the _as_local timezone conversion helper."""

    def test_aware_datetime_is_returned(self) -> None:
        dt = datetime.now(UTC)
        result = _as_local(dt)
        assert result.tzinfo is not None

    def test_naive_datetime_gets_utc_assigned(self) -> None:
        naive_dt = datetime(2025, 1, 1, 12, 0, 0)
        result = _as_local(naive_dt)
        assert result.tzinfo is not None
