"""Tests for PawControl sensor module data access helpers."""

from datetime import UTC, datetime
from typing import Any, cast

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.sensor import PawControlSensorBase
from custom_components.pawcontrol.types import (
    CoordinatorDogData,
    CoordinatorModuleLookupResult,
    CoordinatorModuleState,
)


class _CoordinatorStub:
    """Minimal coordinator stub exposing typed module accessors."""

    def __init__(self, payload: dict[str, CoordinatorDogData]) -> None:
        self.available = True
        self._data = payload
        self.last_update_success_time = None

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        """Return coordinator dog payload for ``dog_id``."""
        return self._data.get(dog_id)

    def get_module_data(
        self, dog_id: str, module: str
    ) -> CoordinatorModuleLookupResult:
        """Return module data for ``dog_id`` and ``module``."""
        dog_payload = self._data.get(dog_id, cast(CoordinatorDogData, {}))
        return cast(CoordinatorModuleLookupResult, dog_payload.get(module, {}))


class _DummySensor(PawControlSensorBase):
    """Concrete PawControl sensor used for module access tests."""

    def __init__(self, coordinator: _CoordinatorStub) -> None:
        super().__init__(
            coordinator=cast(PawControlCoordinator, coordinator),
            dog_id="alpha",
            dog_name="Alpha",
            sensor_type="dummy",
        )

    @property
    def native_value(self) -> int | None:
        """Return a static value; not relevant for module tests."""
        return 0


def _build_sensor(payload: dict[str, CoordinatorDogData]) -> _DummySensor:
    """Helper to instantiate a sensor against ``payload``."""
    coordinator = _CoordinatorStub(payload)
    return _DummySensor(coordinator)


def test_get_module_data_preserves_typed_payload() -> None:
    """Typed modules should pass through coordinator payloads unchanged."""
    sensor = _build_sensor({
        "alpha": cast(
            CoordinatorDogData,
            {"gps": {"status": "active", "last_fix": "2025-01-01T12:00:00"}},
        )
    })

    payload = sensor._get_module_data("gps")

    assert payload["status"] == "active"
    assert payload["last_fix"] == "2025-01-01T12:00:00"


def test_get_module_data_returns_empty_mapping_for_unknown_module() -> None:
    """Unknown modules should yield empty payloads."""
    sensor = _build_sensor({"alpha": cast(CoordinatorDogData, {})})

    payload = sensor._get_module_data("notifications")

    assert payload == {}


def test_get_module_data_falls_back_when_lookup_attribute_is_not_callable() -> None:
    """Non-callable lookup attributes should use ``get_dog_data`` fallback."""

    class _AttributeCoordinator(_CoordinatorStub):
        get_module_data = cast(Any, "not-callable")

    coordinator = _AttributeCoordinator({
        "alpha": cast(
            CoordinatorDogData,
            {"gps": {"status": "fallback", "last_fix": "2025-01-01T12:00:00"}},
        )
    })
    sensor = _DummySensor(coordinator)

    payload = sensor._get_module_data("gps")

    assert payload["status"] == "fallback"


def test_get_module_data_returns_empty_when_lookup_raises(caplog: Any) -> None:
    """Errors raised by coordinator lookup methods should return empty mappings."""

    class _ErrorCoordinator(_CoordinatorStub):
        def get_module_data(
            self,
            dog_id: str,
            module: str,
        ) -> CoordinatorModuleLookupResult:
            raise RuntimeError("boom")

    coordinator = _ErrorCoordinator({"alpha": cast(CoordinatorDogData, {})})
    sensor = _DummySensor(coordinator)

    with caplog.at_level("WARNING"):
        payload = sensor._get_module_data("gps")

    assert payload == {}
    assert "Error fetching module data" in caplog.text


def test_get_module_data_filters_invalid_payload_types() -> None:
    """Non-mapping payloads from the coordinator fall back to empty mappings."""

    class _InvalidCoordinator(_CoordinatorStub):
        def get_module_data(self, dog_id: str, module: str) -> CoordinatorModuleState:
            return cast(CoordinatorModuleState, cast(Any, "invalid"))

    coordinator = _InvalidCoordinator({"alpha": cast(CoordinatorDogData, {})})
    sensor = _DummySensor(coordinator)

    payload = sensor._get_module_data("gps")

    assert payload == {}


def test_get_module_data_uses_dog_payload_when_accessor_is_missing() -> None:
    """Fallback path should use ``get_dog_data`` when accessor is absent."""

    class _MissingAccessorCoordinator:
        """Coordinator stub exposing only ``get_dog_data`` accessor."""

        def __init__(self, payload: dict[str, CoordinatorDogData]) -> None:
            self.available = True
            self._data = payload
            self.last_update_success_time = None

        def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
            """Return coordinator dog payload for ``dog_id``."""
            return self._data.get(dog_id)

    coordinator = _MissingAccessorCoordinator({
        "alpha": cast(CoordinatorDogData, {"gps": {"status": "active"}})
    })
    sensor = _DummySensor(coordinator)

    payload = sensor._get_module_data("gps")

    assert payload["status"] == "active"


def test_get_module_data_rejects_invalid_module_name() -> None:
    """Invalid module names should always produce empty mappings."""
    sensor = _build_sensor(
        {"alpha": cast(CoordinatorDogData, {"gps": {"status": "ok"}})}
    )

    assert sensor._get_module_data("") == {}
    assert sensor._get_module_data(cast(Any, None)) == {}


def test_get_module_data_handles_specific_lookup_exceptions(caplog: Any) -> None:
    """Specialized coordinator lookup failures should return empty payloads."""

    class _AttributeErrorCoordinator(_CoordinatorStub):
        def get_module_data(
            self,
            dog_id: str,
            module: str,
        ) -> CoordinatorModuleLookupResult:
            raise AttributeError("missing")

    class _LookupErrorCoordinator(_CoordinatorStub):
        def get_module_data(
            self,
            dog_id: str,
            module: str,
        ) -> CoordinatorModuleLookupResult:
            raise LookupError("missing")

    class _TypeErrorCoordinator(_CoordinatorStub):
        def get_module_data(
            self,
            dog_id: str,
            module: str,
        ) -> CoordinatorModuleLookupResult:
            raise TypeError("wrong type")

    class _ValueErrorCoordinator(_CoordinatorStub):
        def get_module_data(
            self,
            dog_id: str,
            module: str,
        ) -> CoordinatorModuleLookupResult:
            raise ValueError("bad value")

    coordinator_types = (
        (_AttributeErrorCoordinator, "missing attribute"),
        (_LookupErrorCoordinator, "missing key/index"),
        (_TypeErrorCoordinator, "type mismatch"),
        (_ValueErrorCoordinator, "invalid value"),
    )

    with caplog.at_level("WARNING"):
        for coordinator_type, expected_message in coordinator_types:
            sensor = _DummySensor(
                coordinator_type({"alpha": cast(CoordinatorDogData, {})})
            )
            assert sensor._get_module_data("gps") == {}
            assert expected_message in caplog.text


def test_sensor_base_coercion_helpers() -> None:
    """Sensor coercion helpers should normalize supported payload values."""
    sensor = _build_sensor({"alpha": cast(CoordinatorDogData, {})})

    assert sensor._coerce_module_payload({"x": 1}) == {"x": 1}
    assert sensor._coerce_module_payload("invalid") == {}

    assert sensor._coerce_float(True) == 1.0
    assert sensor._coerce_float(2) == 2.0
    assert sensor._coerce_float("2.5") == 2.5
    assert sensor._coerce_float("bad", default=3.0) == 3.0

    assert sensor._coerce_int(True) == 1
    assert sensor._coerce_int(4.2) == 4
    assert sensor._coerce_int("5") == 5
    assert sensor._coerce_int("bad", default=8) == 8

    dt_value = datetime(2025, 1, 1, tzinfo=UTC)
    assert sensor._coerce_utc_datetime(dt_value) == dt_value
    assert sensor._coerce_utc_datetime("2025-01-01T00:00:00Z") is not None
    assert sensor._coerce_utc_datetime(object()) is None

    assert sensor._coerce_feeding_payload({"diet": "ok"}) == {"diet": "ok"}
    assert sensor._coerce_walk_payload({"distance_km": 2.0}) == {"distance_km": 2.0}
    assert sensor._coerce_gps_payload({"status": "active"}) is not None
    assert sensor._coerce_health_payload({"score": 80}) == {"score": 80}


def test_sensor_module_accessor_helpers_delegate_to_module_lookup() -> None:
    """Module accessor helpers should delegate through ``_get_module_data``."""
    sensor = _build_sensor(
        {
            "alpha": cast(
                CoordinatorDogData,
                {
                    "feeding": {"diet": "balanced"},
                    "walk": {"distance_km": 1.2},
                    "gps": {"status": "tracking"},
                    "health": {"activity": "normal"},
                },
            )
        }
    )

    assert sensor._get_feeding_module() == {"diet": "balanced"}
    assert sensor._get_walk_module() == {"distance_km": 1.2}
    assert sensor._get_gps_module() is not None
    assert sensor._get_health_module() == {"activity": "normal"}
