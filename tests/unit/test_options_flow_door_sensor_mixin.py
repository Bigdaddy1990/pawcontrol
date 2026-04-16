"""Coverage tests for ``DoorSensorOptionsMixin`` flow branches."""

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

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

    async def async_step_manage_dogs(self) -> dict[str, Any]:
        self.manage_calls += 1
        return {"type": "menu", "step_id": "manage_dogs"}

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
async def test_select_dog_step_returns_manage_when_selected_dog_is_missing() -> None:
    """Unknown dog selections should route back to the manage dogs menu."""
    host = _DoorSensorHost([
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_DOG_NAME: "Buddy"}
    ])

    result = await host.async_step_select_dog_for_door_sensor({"dog_id": "missing"})

    assert result["step_id"] == "manage_dogs"
    assert host.manage_calls == 1


@pytest.mark.asyncio
async def test_select_dog_step_shows_form_when_waiting_for_selection() -> None:
    """When dogs exist and no input is provided, a selector form should be shown."""
    host = _DoorSensorHost([
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_DOG_NAME: "Buddy"}
    ])

    result = await host.async_step_select_dog_for_door_sensor()

    assert result["type"] == "form"
    assert result["step_id"] == "select_dog_for_door_sensor"


@pytest.mark.asyncio
async def test_select_dog_step_routes_to_configure_when_dog_exists() -> None:
    """Known dog selections should route into the configure step."""
    host = _DoorSensorHost([
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_DOG_NAME: "Buddy"}
    ])
    host.async_step_configure_door_sensor = AsyncMock(
        return_value={"type": "form", "step_id": "configure_door_sensor"}
    )

    result = await host.async_step_select_dog_for_door_sensor({"dog_id": "buddy"})

    assert result["step_id"] == "configure_door_sensor"
    host.async_step_configure_door_sensor.assert_awaited_once()


@pytest.mark.asyncio
async def test_configure_door_sensor_routes_to_manage_without_valid_current_dog() -> (
    None
):
    """Missing current dog payloads should return to the dog-management step."""
    host = _DoorSensorHost([])
    host._current_dog = None

    result = await host.async_step_configure_door_sensor()
    assert result["step_id"] == "manage_dogs"

    host_with_invalid_id = _DoorSensorHost([
        {DOG_ID_FIELD: "", DOG_NAME_FIELD: "Buddy", CONF_DOG_NAME: "Buddy"}
    ])
    host_with_invalid_id._current_dog = {
        DOG_ID_FIELD: "",
        DOG_NAME_FIELD: "Buddy",
        CONF_DOG_NAME: "Buddy",
    }

    invalid_result = await host_with_invalid_id.async_step_configure_door_sensor()
    assert invalid_result["step_id"] == "manage_dogs"


@pytest.mark.asyncio
async def test_configure_door_sensor_shows_form_for_none_input_and_fallback_name() -> (
    None
):
    """No input should render the form and tolerate mixed existing settings payloads."""
    host = _DoorSensorHost([
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_DOG_NAME: 123,
            CONF_DOOR_SENSOR_SETTINGS: {
                "door_closed_delay": 30,
                "invalid_list": ["skip-me"],
            },
        }
    ])

    result = await host.async_step_configure_door_sensor()

    assert result["type"] == "form"
    assert result["step_id"] == "configure_door_sensor"
    assert result["description_placeholders"]["dog_name"] == 123


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
@pytest.mark.parametrize("ensure_payload", [None, ValueError("invalid payload")])
async def test_configure_door_sensor_handles_invalid_normalized_dog_payload(
    monkeypatch: pytest.MonkeyPatch,
    ensure_payload: object,
) -> None:
    """Invalid normalization outcomes should surface a base form error."""
    host = _DoorSensorHost([
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_DOG_NAME: "Buddy"}
    ])

    monkeypatch.setattr(
        module,
        "validate_sensor_entity_id",
        lambda _hass, entity_id, **_kwargs: entity_id,
    )
    if isinstance(ensure_payload, Exception):
        monkeypatch.setattr(
            module,
            "ensure_dog_config_data",
            lambda _payload: (_ for _ in ()).throw(ensure_payload),
        )
    else:
        monkeypatch.setattr(module, "ensure_dog_config_data", lambda _payload: None)

    result = await host.async_step_configure_door_sensor({CONF_DOOR_SENSOR: ""})

    assert result["type"] == "form"
    assert result["errors"]["base"] == "door_sensor_not_found"


@pytest.mark.asyncio
async def test_configure_door_sensor_persists_with_runtime_data_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changed settings should persist via runtime data manager when available."""
    host = _DoorSensorHost([
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_DOG_NAME: "Buddy",
            CONF_DOOR_SENSOR: "binary_sensor.front_door",
            CONF_DOOR_SENSOR_SETTINGS: {"door_closed_delay": 10},
        }
    ])
    data_manager = SimpleNamespace(async_update_dog_data=AsyncMock(return_value=True))
    runtime = SimpleNamespace(data_manager=data_manager)

    monkeypatch.setattr(module, "ensure_dog_config_data", lambda payload: payload)
    monkeypatch.setattr(
        module,
        "validate_sensor_entity_id",
        lambda _hass, entity_id, **_kwargs: entity_id,
    )
    monkeypatch.setattr(
        module,
        "_resolve_require_runtime_data",
        lambda: lambda _hass, _entry: runtime,
    )

    result = await host.async_step_configure_door_sensor({
        CONF_DOOR_SENSOR: "binary_sensor.front_door",
        "door_closed_delay": 99,
        "minimum_walk_duration": 120,
    })

    assert result["step_id"] == "manage_dogs"
    data_manager.async_update_dog_data.assert_awaited_once()


@pytest.mark.asyncio
async def test_configure_door_sensor_non_runtime_resolution_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected runtime resolver errors should be re-raised."""
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
    monkeypatch.setattr(
        module,
        "_resolve_require_runtime_data",
        lambda: lambda _hass, _entry: (_ for _ in ()).throw(ValueError("boom")),
    )

    with pytest.raises(ValueError, match="boom"):
        await host.async_step_configure_door_sensor({
            CONF_DOOR_SENSOR: "binary_sensor.front_door",
            "door_closed_delay": [],
        })


@pytest.mark.asyncio
async def test_configure_door_sensor_handles_non_string_sensor_and_falsey_data_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-string sensors and falsey non-None managers should still complete safely."""
    host = _DoorSensorHost([
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_DOG_NAME: "Buddy",
            CONF_DOOR_SENSOR: "binary_sensor.front_door",
        }
    ])
    runtime = SimpleNamespace(data_manager=False)

    monkeypatch.setattr(module, "ensure_dog_config_data", lambda payload: payload)
    monkeypatch.setattr(
        module,
        "_resolve_require_runtime_data",
        lambda: lambda _hass, _entry: runtime,
    )

    result = await host.async_step_configure_door_sensor({
        CONF_DOOR_SENSOR: object(),
        "minimum_walk_duration": 150,
    })

    assert result["step_id"] == "manage_dogs"


@pytest.mark.asyncio
async def test_configure_door_sensor_keeps_form_open_when_current_dog_missing_from_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the current dog cannot be found in the list, the form should stay open."""
    host = _DoorSensorHost([
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_DOG_NAME: "Buddy"}
    ])
    host._current_dog = {
        DOG_ID_FIELD: "ghost",
        DOG_NAME_FIELD: "Ghost",
        CONF_DOG_NAME: "Ghost",
    }
    host._dogs = []
    data_manager = SimpleNamespace(async_update_dog_data=AsyncMock(return_value=True))
    runtime = SimpleNamespace(data_manager=data_manager)

    monkeypatch.setattr(module, "ensure_dog_config_data", lambda payload: payload)
    monkeypatch.setattr(
        module,
        "validate_sensor_entity_id",
        lambda _hass, entity_id, **_kwargs: entity_id,
    )
    monkeypatch.setattr(
        module,
        "_resolve_require_runtime_data",
        lambda: lambda _hass, _entry: runtime,
    )

    result = await host.async_step_configure_door_sensor({
        CONF_DOOR_SENSOR: "binary_sensor.front_door",
        "door_closed_delay": 120,
    })

    assert result["step_id"] == "manage_dogs"


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
async def test_configure_door_sensor_skips_runtime_persistence_without_data_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing runtime data manager should return the runtime-cache error form."""
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
        "walk_duration": 25,
    })

    assert result["step_id"] == "configure_door_sensor"
    assert result["errors"]["base"] == "runtime_cache_unavailable"
    assert host.updated_entry_data is None
