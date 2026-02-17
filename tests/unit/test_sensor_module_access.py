"""Tests for PawControl sensor module data access helpers."""

from typing import Any, cast

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.sensor import PawControlSensorBase
from custom_components.pawcontrol.types import (
    CoordinatorDogData,
    CoordinatorModuleLookupResult,
    CoordinatorModuleState,
)


class _CoordinatorStub:
    """Minimal coordinator stub exposing typed module accessors."""  # noqa: E111

    def __init__(self, payload: dict[str, CoordinatorDogData]) -> None:  # noqa: E111
        self.available = True
        self._data = payload
        self.last_update_success_time = None

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:  # noqa: E111
        """Return coordinator dog payload for ``dog_id``."""

        return self._data.get(dog_id)

    def get_module_data(
        self, dog_id: str, module: str
    ) -> CoordinatorModuleLookupResult:  # noqa: E111
        """Return module data for ``dog_id`` and ``module``."""

        dog_payload = self._data.get(dog_id, cast(CoordinatorDogData, {}))
        return cast(CoordinatorModuleLookupResult, dog_payload.get(module, {}))


class _DummySensor(PawControlSensorBase):
    """Concrete PawControl sensor used for module access tests."""  # noqa: E111

    def __init__(self, coordinator: _CoordinatorStub) -> None:  # noqa: E111
        super().__init__(
            coordinator=cast(PawControlCoordinator, coordinator),
            dog_id="alpha",
            dog_name="Alpha",
            sensor_type="dummy",
        )

    @property  # noqa: E111
    def native_value(self) -> int | None:  # noqa: E111
        """Return a static value; not relevant for module tests."""

        return 0


def _build_sensor(payload: dict[str, CoordinatorDogData]) -> _DummySensor:
    """Helper to instantiate a sensor against ``payload``."""  # noqa: E111

    coordinator = _CoordinatorStub(payload)  # noqa: E111
    return _DummySensor(coordinator)  # noqa: E111


def test_get_module_data_preserves_typed_payload() -> None:
    """Typed modules should pass through coordinator payloads unchanged."""  # noqa: E111

    sensor = _build_sensor({  # noqa: E111
        "alpha": cast(
            CoordinatorDogData,
            {"gps": {"status": "active", "last_fix": "2025-01-01T12:00:00"}},
        )
    })

    payload = sensor._get_module_data("gps")  # noqa: E111

    assert payload["status"] == "active"  # noqa: E111
    assert payload["last_fix"] == "2025-01-01T12:00:00"  # noqa: E111


def test_get_module_data_returns_empty_mapping_for_unknown_module() -> None:
    """Unknown modules should yield empty payloads."""  # noqa: E111

    sensor = _build_sensor({"alpha": cast(CoordinatorDogData, {})})  # noqa: E111

    payload = sensor._get_module_data("notifications")  # noqa: E111

    assert payload == {}  # noqa: E111


def test_get_module_data_filters_invalid_payload_types() -> None:
    """Non-mapping payloads from the coordinator fall back to empty mappings."""  # noqa: E111

    class _InvalidCoordinator(_CoordinatorStub):  # noqa: E111
        def get_module_data(self, dog_id: str, module: str) -> CoordinatorModuleState:
            return cast(CoordinatorModuleState, cast(Any, "invalid"))  # noqa: E111

    coordinator = _InvalidCoordinator({"alpha": cast(CoordinatorDogData, {})})  # noqa: E111
    sensor = _DummySensor(coordinator)  # noqa: E111

    payload = sensor._get_module_data("gps")  # noqa: E111

    assert payload == {}  # noqa: E111
