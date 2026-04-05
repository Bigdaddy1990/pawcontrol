"""Targeted unit tests for sensor helper utilities."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

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


class _ClassmethodDocBase:
    @classmethod
    def documented_classmethod(cls) -> str:
        """Class method docs."""
        return "ok"


class _ClassmethodDocChild(_ClassmethodDocBase):
    @classmethod
    def documented_classmethod(cls) -> str:
        return "ok"


def test_copy_base_docstring_to_classmethod() -> None:
    assert _ClassmethodDocChild.documented_classmethod.__doc__ is None

    sensor._copy_base_docstring(
        attribute_name="documented_classmethod",
        cls=_ClassmethodDocChild,
        attribute=_ClassmethodDocChild.__dict__["documented_classmethod"],
    )

    assert _ClassmethodDocChild.documented_classmethod.__doc__ == "Class method docs."


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


@pytest.mark.asyncio
async def test_async_setup_entry_returns_when_runtime_data_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sensor, "get_runtime_data", lambda _hass, _entry: None)

    calls: list[list[object]] = []

    def add_entities(entities: list[object]) -> None:
        calls.append(entities)

    await sensor.async_setup_entry(
        hass=SimpleNamespace(),
        entry=SimpleNamespace(entry_id="entry-missing"),
        async_add_entities=add_entities,
    )

    assert calls == []


def test_create_module_entities_respects_enabled_modules_and_budget() -> None:
    class _BudgetStub:
        remaining = 0

    class _FactoryStub:
        def __init__(self) -> None:
            self.config_calls: list[dict[str, Any]] = []

        def get_budget(self, _dog_id: str, _profile: str) -> _BudgetStub:
            return _BudgetStub()

        def create_entity_config(self, **kwargs: Any) -> dict[str, object] | None:
            self.config_calls.append(kwargs)
            return {"enabled": True}

    def _entity_builder(*_args: Any) -> object:
        return object()

    factory = _FactoryStub()
    rules = {
        "health": {
            "standard": [("activity", _entity_builder, 1)],
        },
    }

    original_rules = sensor._MODULE_ENTITY_RULES
    try:
        sensor._MODULE_ENTITY_RULES = rules
        entities = sensor._create_module_entities(
            coordinator=SimpleNamespace(),
            entity_factory=factory,
            dog_id="dog-1",
            dog_name="Rex",
            modules={"health": True, "walk": True},
            profile="standard",
        )
    finally:
        sensor._MODULE_ENTITY_RULES = original_rules

    assert entities == []
    assert factory.config_calls == []


@pytest.mark.asyncio
async def test_async_setup_entry_finalizes_budget_and_awaits_add_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    begin_calls: list[tuple[str, str, int]] = []
    finalize_calls: list[tuple[str, str]] = []

    class _EntityFactoryStub:
        def begin_budget(self, dog_id: str, profile: str, base_allocation: int) -> None:
            begin_calls.append((dog_id, profile, base_allocation))

        def finalize_budget(self, dog_id: str, profile: str) -> None:
            finalize_calls.append((dog_id, profile))

    runtime_data = SimpleNamespace(
        coordinator=object(),
        dogs=[{sensor.DOG_ID_FIELD: "dog-1", sensor.DOG_NAME_FIELD: "Luna"}],
        entity_factory=_EntityFactoryStub(),
        entity_profile="standard",
    )
    monkeypatch.setattr(sensor, "get_runtime_data", lambda _hass, _entry: runtime_data)
    monkeypatch.setattr(sensor, "_create_core_entities", lambda *_: ["core-entity"])

    def _raise_during_module_creation(*_: object) -> list[str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        sensor, "_create_module_entities", _raise_during_module_creation
    )

    async_add_entities = AsyncMock(return_value=None)

    with pytest.raises(RuntimeError, match="boom"):
        await sensor.async_setup_entry(
            hass=object(),
            entry=SimpleNamespace(entry_id="entry-1"),
            async_add_entities=async_add_entities,
        )

    assert begin_calls == [("dog-1", "standard", 1)]
    assert finalize_calls == [("dog-1", "standard")]


@pytest.mark.asyncio
async def test_async_setup_entry_adds_entities_from_core_and_module_and_awaits_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_data = SimpleNamespace(
        coordinator=object(),
        dogs=[{sensor.DOG_ID_FIELD: "dog-1", sensor.DOG_NAME_FIELD: "Luna"}],
        entity_factory=SimpleNamespace(
            begin_budget=lambda *_args, **_kwargs: None,
            finalize_budget=lambda *_args, **_kwargs: None,
        ),
        entity_profile="standard",
    )
    monkeypatch.setattr(sensor, "get_runtime_data", lambda _hass, _entry: runtime_data)
    monkeypatch.setattr(sensor, "_create_core_entities", lambda *_: ["core"])
    monkeypatch.setattr(sensor, "_create_module_entities", lambda *_: ["module"])

    async_add_entities = AsyncMock(return_value=None)

    await sensor.async_setup_entry(
        hass=object(),
        entry=SimpleNamespace(entry_id="entry-1"),
        async_add_entities=async_add_entities,
    )

    async_add_entities.assert_awaited_once_with(["core", "module"])


@pytest.mark.asyncio
async def test_async_setup_entry_skips_add_entities_when_no_dogs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_data = SimpleNamespace(
        coordinator=object(),
        dogs=[],
        entity_factory=SimpleNamespace(),
        entity_profile="standard",
    )
    monkeypatch.setattr(sensor, "get_runtime_data", lambda _hass, _entry: runtime_data)
    async_add_entities = AsyncMock(return_value=None)

    await sensor.async_setup_entry(
        hass=object(),
        entry=SimpleNamespace(entry_id="entry-no-dogs"),
        async_add_entities=async_add_entities,
    )

    async_add_entities.assert_not_awaited()


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
