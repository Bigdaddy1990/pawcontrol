"""Coverage tests for ``DoorSensorOptionsMixin`` flow branches."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, cast

import pytest
import voluptuous as vol

from custom_components.pawcontrol import options_flow_door_sensor as module
from custom_components.pawcontrol.const import (
    CONF_DOG_NAME,
    CONF_DOOR_SENSOR,
    CONF_DOOR_SENSOR_SETTINGS,
)
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD


class _DoorSensorHost(module.DoorSensorOptionsMixin):
    """Minimal host that exercises the door sensor options mixin."""

    def __init__(self, dogs: list[dict[str, Any]]) -> None:
        self._dogs = dogs
        self._current_dog: dict[str, Any] | None = dogs[0] if dogs else None
        self.manage_calls = 0
        self.last_form: dict[str, Any] | None = None
        self.invalidated = False
        self._entry = SimpleNamespace(entry_id="entry-1", data={"dogs": dogs})
        self.hass = SimpleNamespace(
            config_entries=SimpleNamespace(async_update_entry=self._async_update_entry)
        )
        self.updated_entry_data: Mapping[str, Any] | None = None
        self.configure_calls = 0

    async def async_step_manage_dogs(self) -> dict[str, Any]:
        self.manage_calls += 1
        return {"type": "menu", "step_id": "manage_dogs"}

    async def async_step_configure_door_sensor(
        self,
        user_input: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.configure_calls += 1
        return await super().async_step_configure_door_sensor(user_input)

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: vol.Schema,
        errors: dict[str, str] | None = None,
        description_placeholders: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.last_form = {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
            "description_placeholders": description_placeholders,
        }
        return self.last_form

    def _get_available_door_sensors(self) -> list[str]:
        return ["binary_sensor.front_door"]

    def _get_door_sensor_settings_schema(
        self,
        _available_sensors: list[str],
        *,
        current_sensor: str | None,
        defaults: Any,
        user_input: Mapping[str, Any] | None,
    ) -> vol.Schema:
        del current_sensor, defaults, user_input
        return vol.Schema({vol.Optional(CONF_DOOR_SENSOR): str})

    def _normalise_entry_dogs(self, dogs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return dogs

    def _invalidate_profile_caches(self) -> None:
        self.invalidated = True

    def _async_update_entry(self, _entry: Any, *, data: Mapping[str, Any]) -> None:
        self.updated_entry_data = data


@pytest.mark.asyncio
async def test_select_dog_step_routes_to_manage_when_empty() -> None:
    """No dogs should route directly to the manage dogs step."""
    host = _DoorSensorHost([])

    result = await host.async_step_select_dog_for_door_sensor()

    assert result["step_id"] == "manage_dogs"
    assert host.manage_calls == 1


@pytest.mark.asyncio
async def test_select_dog_step_routes_to_configure_for_valid_selection() -> None:
    """Selecting a known dog should continue to the configuration step."""
    host = _DoorSensorHost([
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_DOG_NAME: "Buddy",
        }
    ])

    result = await host.async_step_select_dog_for_door_sensor({"dog_id": "buddy"})

    assert result["type"] == "form"
    assert result["step_id"] == "configure_door_sensor"
    assert host.configure_calls == 1


@pytest.mark.asyncio
async def test_configure_door_sensor_returns_field_error_for_invalid_sensor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid entity IDs should keep the form open with a field error."""
    host = _DoorSensorHost([
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_DOG_NAME: "Buddy"}
    ])

    def _raise_validation(*_: Any, **__: Any) -> str:
        raise module.ValidationError(field=CONF_DOOR_SENSOR)

    monkeypatch.setattr(module, "validate_sensor_entity_id", _raise_validation)

    result = await host.async_step_configure_door_sensor({
        CONF_DOOR_SENSOR: "binary_sensor.missing",
        "walk_duration": 12,
        "door_closed_delay": 20,
    })

    assert result["type"] == "form"
    assert result["errors"][CONF_DOOR_SENSOR] == "door_sensor_not_found"


@pytest.mark.asyncio
async def test_configure_door_sensor_routes_to_manage_when_current_dog_missing() -> (
    None
):
    """A missing selected dog should return to the manage dogs step."""
    host = _DoorSensorHost([
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_DOG_NAME: "Buddy"}
    ])
    host._current_dog = None

    result = await host.async_step_configure_door_sensor()

    assert result["step_id"] == "manage_dogs"
    assert host.manage_calls == 1


@pytest.mark.asyncio
async def test_configure_door_sensor_routes_to_manage_when_dog_id_invalid() -> None:
    """A non-string dog identifier should abort the step safely."""
    host = _DoorSensorHost([{DOG_ID_FIELD: 7, DOG_NAME_FIELD: "Buddy"}])

    result = await host.async_step_configure_door_sensor()

    assert result["step_id"] == "manage_dogs"
    assert host.manage_calls == 1


@pytest.mark.asyncio
async def test_configure_door_sensor_updates_entry_without_runtime_data_when_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings-only local update should skip runtime persistence when unchanged."""
    host = _DoorSensorHost([
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_DOG_NAME: "Buddy",
        }
    ])

    monkeypatch.setattr(module, "ensure_dog_config_data", lambda payload: payload)
    monkeypatch.setattr(
        module,
        "validate_sensor_entity_id",
        lambda _hass, entity_id, **_kwargs: entity_id,
    )

    result = await host.async_step_configure_door_sensor({
        CONF_DOOR_SENSOR: "   ",
        "walk_duration": 30,
    })

    assert result["step_id"] == "manage_dogs"
    assert host.updated_entry_data is not None
    updated_dog = cast(list[dict[str, Any]], host.updated_entry_data["dogs"])[0]
    assert CONF_DOOR_SENSOR not in updated_dog
    assert CONF_DOOR_SENSOR_SETTINGS not in updated_dog
    assert host.invalidated is True


@pytest.mark.asyncio
async def test_configure_door_sensor_reports_base_error_when_normalization_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `None` normalisation result should keep the form open with a base error."""
    host = _DoorSensorHost([
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_DOG_NAME: "Buddy",
            CONF_DOOR_SENSOR: "binary_sensor.front_door",
        }
    ])

    monkeypatch.setattr(
        module,
        "validate_sensor_entity_id",
        lambda _hass, entity_id, **_kwargs: entity_id,
    )
    monkeypatch.setattr(module, "ensure_dog_config_data", lambda _payload: None)

    result = await host.async_step_configure_door_sensor({
        CONF_DOOR_SENSOR: "binary_sensor.front_door",
        "walk_duration": 22,
        "require_confirmation": True,
    })

    assert result["type"] == "form"
    assert result["errors"]["base"] == "door_sensor_not_found"


@pytest.mark.asyncio
async def test_configure_door_sensor_reports_base_error_on_normalization_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normalisation `ValueError` should map to the expected base error."""
    host = _DoorSensorHost([
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_DOG_NAME: "Buddy",
            CONF_DOOR_SENSOR: "binary_sensor.front_door",
        }
    ])

    monkeypatch.setattr(
        module,
        "validate_sensor_entity_id",
        lambda _hass, entity_id, **_kwargs: entity_id,
    )

    def _raise_value_error(_payload: Mapping[str, Any]) -> None:
        raise ValueError("invalid payload")

    monkeypatch.setattr(module, "ensure_dog_config_data", _raise_value_error)

    result = await host.async_step_configure_door_sensor({
        CONF_DOOR_SENSOR: "binary_sensor.front_door",
        "walk_duration": 22,
        "require_confirmation": True,
    })

    assert result["type"] == "form"
    assert result["errors"]["base"] == "door_sensor_not_found"


@pytest.mark.asyncio
async def test_configure_door_sensor_sets_runtime_error_when_runtime_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime data failures should surface a base error in the form."""
    host = _DoorSensorHost([
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_DOG_NAME: "Buddy",
            CONF_DOOR_SENSOR: "binary_sensor.front_door",
        }
    ])

    monkeypatch.setattr(module, "ensure_dog_config_data", lambda payload: payload)
    monkeypatch.setattr(
        module,
        "validate_sensor_entity_id",
        lambda _hass, entity_id, **_kwargs: entity_id,
    )
    monkeypatch.setattr(
        module,
        "_resolve_require_runtime_data",
        lambda: (
            lambda _hass, _entry: (_ for _ in ()).throw(
                module.RuntimeDataUnavailableError("missing runtime")
            )
        ),
    )

    result = await host.async_step_configure_door_sensor({
        CONF_DOOR_SENSOR: "binary_sensor.side_door",
        "walk_duration": 20,
    })

    assert result["type"] == "form"
    assert result["errors"]["base"] == "runtime_cache_unavailable"


@pytest.mark.asyncio
async def test_configure_door_sensor_sets_runtime_error_when_data_manager_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime payloads without a data manager should return a cache error."""
    host = _DoorSensorHost([
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_DOG_NAME: "Buddy",
            CONF_DOOR_SENSOR: "binary_sensor.front_door",
        }
    ])

    monkeypatch.setattr(module, "ensure_dog_config_data", lambda payload: payload)
    monkeypatch.setattr(
        module,
        "validate_sensor_entity_id",
        lambda _hass, entity_id, **_kwargs: entity_id,
    )
    monkeypatch.setattr(
        module,
        "_resolve_require_runtime_data",
        lambda: lambda _hass, _entry: SimpleNamespace(data_manager=None),
    )

    result = await host.async_step_configure_door_sensor({
        CONF_DOOR_SENSOR: "binary_sensor.side_door",
        "walk_duration": 20,
        "require_confirmation": True,
    })

    assert result["type"] == "form"
    assert result["errors"]["base"] == "runtime_cache_unavailable"
