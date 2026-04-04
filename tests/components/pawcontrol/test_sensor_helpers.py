"""Targeted unit tests for sensor helper utilities."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

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


def test_suggested_precision_handles_dynamic_speed_and_calorie_units() -> None:
    assert sensor._suggested_precision_from_unit(sensor._SPEED_UNIT) == 1
    assert sensor._suggested_precision_from_unit(sensor._CALORIE_UNIT) == 0


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


class _MethodDocBase:
    def documented_method(self) -> str:
        """Method docs."""
        return "ok"


class _MethodDocChild(_MethodDocBase):
    def documented_method(self) -> str:
        return "ok"


def test_copy_base_docstring_to_method() -> None:
    assert _MethodDocChild.documented_method.__doc__ is None

    sensor._copy_base_docstring(
        attribute_name="documented_method",
        cls=_MethodDocChild,
        attribute=_MethodDocChild.documented_method,
    )

    assert _MethodDocChild.documented_method.__doc__ == "Method docs."


def test_normalise_attributes_returns_json_serialisable_mapping() -> None:
    attrs = {
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "today": date(2026, 1, 1),
        "nested": {"raw": object(), "status": "ok"},
    }

    result = sensor._normalise_attributes(attrs)

    assert result["timestamp"] == "2026-01-01T00:00:00+00:00"
    assert result["today"] == "2026-01-01"
    assert isinstance(result["nested"]["raw"], str)
    assert result["nested"]["status"] == "ok"


@pytest.mark.parametrize(
    "payload",
    [
        {"key": "value"},
        None,
        "invalid",
    ],
)
def test_module_payload_coercion_helpers(payload: object) -> None:
    module_payload = sensor.PawControlSensorBase._coerce_module_payload(payload)
    feeding_payload = sensor.PawControlSensorBase._coerce_feeding_payload(
        module_payload
    )
    walk_payload = sensor.PawControlSensorBase._coerce_walk_payload(module_payload)
    health_payload = sensor.PawControlSensorBase._coerce_health_payload(module_payload)

    assert isinstance(module_payload, dict)
    assert feeding_payload is not None
    assert walk_payload is not None
    assert health_payload is not None


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


@pytest.mark.parametrize(
    ("remaining", "expected"),
    [
        (None, None),
        (4, 4),
        (4.9, 4),
        ("7", 7),
        ("bad", None),
        (object(), None),
    ],
)
def test_coerce_budget_remaining(remaining: object, expected: int | None) -> None:
    budget = SimpleNamespace(remaining=remaining)

    assert sensor._coerce_budget_remaining(budget) == expected


def test_coerce_budget_remaining_without_remaining_attribute() -> None:
    assert sensor._coerce_budget_remaining(object()) is None


@pytest.mark.parametrize(
    ("remaining", "expected"),
    [
        (None, False),
        (3, False),
        (0, True),
        (-1, True),
        ("5", False),
        ("0", True),
        ("bad", False),
    ],
)
def test_is_budget_exhausted(remaining: object, expected: bool) -> None:
    budget = SimpleNamespace(remaining=remaining)

    assert sensor._is_budget_exhausted(budget) is expected


@pytest.mark.asyncio
async def test_async_setup_entry_skips_when_runtime_data_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sensor, "get_runtime_data", lambda hass, entry: None)

    add_entities = pytest.fail
    await sensor.async_setup_entry(
        SimpleNamespace(), SimpleNamespace(entry_id="id"), add_entities
    )  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_async_setup_entry_adds_entities_and_awaits_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[object]] = []

    class _Factory:
        def begin_budget(self, dog_id: str, profile: str, base_allocation: int) -> None:
            return None

        def finalize_budget(self, dog_id: str, profile: str) -> None:
            return None

    async def _add_entities(entities: list[object]) -> None:
        calls.append(entities)

    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(),
        dogs=[{"dog_id": "dog-1", "dog_name": "Milo", "modules": {"gps": True}}],
        entity_factory=_Factory(),
        entity_profile="standard",
    )
    monkeypatch.setattr(sensor, "get_runtime_data", lambda hass, entry: runtime_data)
    monkeypatch.setattr(
        sensor,
        "coerce_dog_modules_config",
        lambda dog: {"gps": True},
    )
    monkeypatch.setattr(sensor, "_create_core_entities", lambda *args: ["core"])
    monkeypatch.setattr(sensor, "_create_module_entities", lambda *args: ["module"])

    await sensor.async_setup_entry(
        SimpleNamespace(), SimpleNamespace(entry_id="entry-1"), _add_entities
    )  # type: ignore[arg-type]

    assert calls == [["core", "module"]]
