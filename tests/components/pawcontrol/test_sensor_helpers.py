"""Targeted unit tests for sensor helper utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.pawcontrol import sensor


class _IntervalRaisesValueError:
    """Update interval stub that raises ValueError."""

    def total_seconds(self) -> float:
        raise ValueError("bad interval")


class _IntervalRaisesTypeError:
    """Update interval stub that raises TypeError."""

    def total_seconds(self) -> float:
        raise TypeError("bad interval")


@dataclass
class _CoordinatorStub:
    """Coordinator stub exposing only the update interval."""

    update_interval: object | None


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        (None, None),
        (sensor.PERCENTAGE, 0),
        (sensor.UnitOfTime.MINUTES, 0),
        (sensor.UnitOfTime.HOURS, 1),
        (sensor.UnitOfLength.METERS, 1),
        (sensor.UnitOfLength.KILOMETERS, 2),
        (sensor.MASS_KILOGRAMS, 1),
        (sensor.MASS_GRAMS, 0),
        ("unknown_unit", None),
    ],
)
def test_suggested_precision_from_unit(unit: str | None, expected: int | None) -> None:
    assert sensor._suggested_precision_from_unit(unit) == expected


@pytest.mark.parametrize(
    ("update_interval", "expected"),
    [
        (None, 300),
        (timedelta(seconds=0), 300),
        (timedelta(seconds=10), 60),
        (timedelta(seconds=120), 300),
        (timedelta(seconds=600), 600),
        (10, 60),
        (300, 600),
        ("25", 62),
        ("0", 300),
        (_IntervalRaisesValueError(), 300),
        (_IntervalRaisesTypeError(), 300),
    ],
)
def test_get_activity_score_cache_ttl(update_interval: object, expected: int) -> None:
    coordinator = _CoordinatorStub(update_interval)

    assert sensor.get_activity_score_cache_ttl(coordinator) == expected


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        (True, 1.0, 1.0),
        (10, 0.0, 10.0),
        (10.5, 0.0, 10.5),
        ("7.5", 0.0, 7.5),
        ("bad", 2.5, 2.5),
        (object(), 1.2, 1.2),
    ],
)
def test_coerce_float(value: object, default: float, expected: float) -> None:
    assert sensor.PawControlSensorBase._coerce_float(value, default) == expected


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        (True, 9, 1),
        (10, 0, 10),
        (10.8, 0, 10),
        ("7.9", 0, 7),
        ("bad", 2, 2),
        (object(), 3, 3),
    ],
)
def test_coerce_int(value: object, default: int, expected: int) -> None:
    assert sensor.PawControlSensorBase._coerce_int(value, default) == expected


@pytest.mark.parametrize(
    ("value", "is_none"),
    [
        (None, True),
        (datetime(2025, 1, 1, tzinfo=UTC), False),
        (date(2025, 1, 1), False),
        ("2025-01-01T10:00:00+00:00", False),
        (1700000000, False),
        (object(), True),
    ],
)
def test_coerce_utc_datetime(value: object, is_none: bool) -> None:
    result = sensor.PawControlSensorBase._coerce_utc_datetime(value)

    assert (result is None) is is_none


class _DocBase:
    @property
    def test_property(self) -> str:
        """Property docs."""
        return "value"


class _DocChild(_DocBase):
    @property
    def test_property(self) -> str:
        return "value"


def test_copy_base_docstring_to_property() -> None:
    assert _DocChild.test_property.__doc__ is None

    sensor._copy_base_docstring(
        attribute_name="test_property",
        cls=_DocChild,
        attribute=_DocChild.test_property,
    )

    assert _DocChild.test_property.__doc__ == "Property docs."


class _RegisteredSensor(sensor.PawControlSensorBase):
    """Simple class used to validate sensor registration."""

    @property
    def native_value(self) -> str:
        return "ok"


def test_register_sensor_decorator_adds_mapping_entry() -> None:
    marker = "pytest_registered_sensor"
    sensor.SENSOR_MAPPING.pop(marker, None)

    decorator = sensor.register_sensor(marker)
    registered = decorator(_RegisteredSensor)

    assert registered is _RegisteredSensor
    assert sensor.SENSOR_MAPPING[marker] is _RegisteredSensor
