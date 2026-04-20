"""Additional branch coverage tests for ``options_flow_dogs_management``."""

from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol

from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.exceptions import FlowValidationError
import custom_components.pawcontrol.options_flow_dogs_management as dogs_module
from custom_components.pawcontrol.options_flow_dogs_management import (
    CONF_DOOR_SENSOR,
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DOG_OPTIONS_FIELD,
    DogManagementOptionsMixin,
)
from custom_components.pawcontrol.types import DoorSensorSettingsConfig


class _States:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def async_entity_ids(self, domain: str) -> list[str]:
        if domain != "binary_sensor":
            return []
        return list(self._payload)

    def get(self, entity_id: str) -> Any:
        return self._payload.get(entity_id)


class _ConfigEntries:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def async_update_entry(self, entry: object, **kwargs: Any) -> None:
        self.updates.append({"entry": entry, **kwargs})


class _DogManagementCoverageHost(DogManagementOptionsMixin):
    def __init__(self) -> None:
        self._entry = SimpleNamespace(data={CONF_DOGS: []}, options={})
        self._dogs: list[dict[str, Any]] = []
        self._current_dog: dict[str, Any] | None = None
        self.hass = SimpleNamespace(
            states=_States({}),
            config=SimpleNamespace(language="en"),
            config_entries=_ConfigEntries(),
        )
        self._entity_factory = SimpleNamespace(
            estimate_entity_count=lambda _profile, modules: sum(
                1 for value in modules.values() if bool(value)
            )
        )
        self.invalidations = 0
        self.init_calls = 0

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}

    async def async_step_init(self) -> dict[str, str]:
        self.init_calls += 1
        return {"step": "init"}

    def _current_dog_options(self) -> dict[str, Any]:
        value = self._entry.options.get(DOG_OPTIONS_FIELD, {})
        return dict(value) if isinstance(value, Mapping) else {}

    def _clone_options(self) -> dict[str, Any]:
        return dict(self._entry.options)

    def _invalidate_profile_caches(self) -> None:
        self.invalidations += 1

    def _normalise_entry_dogs(
        self,
        dogs: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        return [dict(dog) for dog in dogs]

    def _normalise_options_snapshot(self, options: Mapping[str, Any]) -> dict[str, Any]:
        return dict(options)


@pytest.mark.asyncio
async def test_select_dog_for_modules_handles_empty_found_missing_and_form(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()

    no_dogs = await host.async_step_select_dog_for_modules()
    assert no_dogs["step_id"] == "manage_dogs"

    host._dogs = [
        {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna", DOG_MODULES_FIELD: {}}
    ]
    configure_step = AsyncMock(return_value={"step": "configure"})
    monkeypatch.setattr(host, "async_step_configure_dog_modules", configure_step)

    selected = await host.async_step_select_dog_for_modules({"dog_id": "dog-1"})
    assert selected == {"step": "configure"}
    assert host._current_dog is not None
    assert host._current_dog[DOG_ID_FIELD] == "dog-1"

    missing = await host.async_step_select_dog_for_modules({"dog_id": "unknown"})
    assert missing["step_id"] == "manage_dogs"

    form = await host.async_step_select_dog_for_modules()
    assert form["step_id"] == "select_dog_for_modules"


@pytest.mark.asyncio
async def test_configure_dog_modules_handles_no_current_and_invalid_dog_id() -> None:  # noqa: D103
    host = _DogManagementCoverageHost()

    no_current = await host.async_step_configure_dog_modules({"module_feeding": True})
    assert no_current["step_id"] == "manage_dogs"

    host._current_dog = {DOG_ID_FIELD: 7, DOG_NAME_FIELD: "Luna", DOG_MODULES_FIELD: {}}
    invalid_dog = await host.async_step_configure_dog_modules({"module_feeding": True})
    assert invalid_dog["step_id"] == "configure_dog_modules"
    assert invalid_dog["errors"] == {"base": "invalid_dog"}


@pytest.mark.asyncio
async def test_configure_dog_modules_handles_validation_and_runtime_failures(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()
    host._current_dog = {
        DOG_ID_FIELD: "dog-1",
        DOG_NAME_FIELD: "Luna",
        DOG_MODULES_FIELD: {"feeding": True},
    }
    host._dogs = [dict(host._current_dog)]

    monkeypatch.setattr(dogs_module, "ensure_dog_config_data", lambda _dog: None)
    invalid = await host.async_step_configure_dog_modules({"module_feeding": True})
    assert invalid["errors"] == {"base": "invalid_dog_config"}

    monkeypatch.setattr(
        dogs_module,
        "ensure_dog_modules_config",
        lambda _modules: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    runtime_failed = await host.async_step_configure_dog_modules({
        "module_feeding": True
    })
    assert runtime_failed["errors"] == {"base": "module_config_failed"}


@pytest.mark.asyncio
async def test_configure_dog_modules_updates_options_when_selected_dog_not_in_list() -> (  # noqa: D103
    None
):
    host = _DogManagementCoverageHost()
    host._current_dog = {
        DOG_ID_FIELD: "ghost",
        DOG_NAME_FIELD: "Ghost",
        DOG_MODULES_FIELD: {"feeding": False},
    }
    host._dogs = [
        {DOG_ID_FIELD: "other", DOG_NAME_FIELD: "Other", DOG_MODULES_FIELD: {}}
    ]
    host._entry.options = {DOG_OPTIONS_FIELD: {}}

    saved = await host.async_step_configure_dog_modules({"module_feeding": False})
    assert saved["type"] == "create_entry"
    assert DOG_OPTIONS_FIELD in saved["data"]
    assert "ghost" in saved["data"][DOG_OPTIONS_FIELD]
    assert host.invalidations == 1

    rendered = await host.async_step_configure_dog_modules()
    assert rendered["step_id"] == "configure_dog_modules"


@pytest.mark.asyncio
async def test_configure_dog_modules_updates_entry_when_selected_dog_exists(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()
    host._current_dog = {
        DOG_ID_FIELD: "dog-1",
        DOG_NAME_FIELD: "Luna",
        DOG_MODULES_FIELD: {"feeding": False},
    }
    host._dogs = [dict(host._current_dog)]
    host._entry.data = {CONF_DOGS: [dict(host._current_dog)]}
    host._entry.options = {DOG_OPTIONS_FIELD: {}}

    monkeypatch.setattr(dogs_module, "ensure_dog_config_data", lambda dog: dict(dog))

    saved = await host.async_step_configure_dog_modules({"module_feeding": True})
    assert saved["type"] == "create_entry"
    assert host._current_dog is not None
    assert host._current_dog[DOG_ID_FIELD] == "dog-1"
    assert host._dogs[0][DOG_ID_FIELD] == "dog-1"
    assert bool(host._dogs[0][DOG_MODULES_FIELD]["feeding"]) is True
    assert host.hass.config_entries.updates[-1]["data"][CONF_DOGS][0][DOG_ID_FIELD] == (
        "dog-1"
    )


def test_door_sensor_schema_handles_text_input_fallback_and_module_schema_empty() -> (  # noqa: D103
    None
):
    host = _DogManagementCoverageHost()

    schema = host._get_door_sensor_settings_schema(
        {},
        current_sensor="binary_sensor.front",
        defaults=DoorSensorSettingsConfig(),
        user_input={CONF_DOOR_SENSOR: 42},
    )
    assert isinstance(schema, vol.Schema)

    host._current_dog = None
    empty_modules_schema = host._get_dog_modules_schema()
    assert isinstance(empty_modules_schema, vol.Schema)
    assert empty_modules_schema.schema == {}


def test_door_sensor_schema_builds_select_options_when_sensors_available() -> None:  # noqa: D103
    host = _DogManagementCoverageHost()

    schema = host._get_door_sensor_settings_schema(
        {"binary_sensor.front": "Front Door"},
        current_sensor=None,
        defaults=DoorSensorSettingsConfig(),
        user_input={CONF_DOOR_SENSOR: "binary_sensor.front"},
    )
    assert isinstance(schema, vol.Schema)


def test_available_door_sensors_skips_none_state_entries() -> None:  # noqa: D103
    host = _DogManagementCoverageHost()
    host.hass.states = _States({
        "binary_sensor.ghost": None,
        "binary_sensor.front": SimpleNamespace(attributes={"device_class": "door"}),
    })

    assert host._get_available_door_sensors() == {
        "binary_sensor.front": "binary_sensor.front"
    }


@pytest.mark.asyncio
async def test_module_description_helpers_cover_async_and_sync_language_branches(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()

    host._current_dog = None
    assert host._get_module_description_placeholders() == {}

    host._current_dog = {
        DOG_ID_FIELD: "dog-1",
        DOG_NAME_FIELD: "Luna",
        DOG_MODULES_FIELD: {"grooming": True, "feeding": True},
    }

    preload = AsyncMock()
    monkeypatch.setattr(dogs_module, "async_preload_component_translations", preload)
    monkeypatch.setattr(
        dogs_module,
        "translated_grooming_label",
        lambda _hass, _lang, key: f"grooming-{key}",
    )

    await host._async_get_module_description_placeholders()
    preload.assert_awaited_once()

    host.hass = None
    placeholders_no_hass = host._get_module_description_placeholders()
    assert placeholders_no_hass["dog_name"] == "Luna"

    host.hass = SimpleNamespace(
        config=None, states=_States({}), config_entries=_ConfigEntries()
    )
    placeholders_no_config = host._get_module_description_placeholders()
    assert placeholders_no_config["dog_name"] == "Luna"


@pytest.mark.asyncio
async def test_async_module_description_placeholders_skips_preload_without_hass() -> (  # noqa: D103
    None
):
    host = _DogManagementCoverageHost()
    host._current_dog = {
        DOG_ID_FIELD: "dog-1",
        DOG_NAME_FIELD: "Luna",
        DOG_MODULES_FIELD: {"feeding": True},
    }
    host.hass = None

    placeholders = await host._async_get_module_description_placeholders()
    assert placeholders["dog_name"] == "Luna"


@pytest.mark.asyncio
async def test_add_new_dog_error_paths_and_schema(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()
    user_input = {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}

    monkeypatch.setattr(
        dogs_module,
        "validate_dog_setup_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FlowValidationError(base_errors=["invalid_new_dog"])
        ),
    )
    validation_error = await host.async_step_add_new_dog(user_input)
    assert validation_error["step_id"] == "add_new_dog"
    assert validation_error["errors"] == {"base": "invalid_new_dog"}

    monkeypatch.setattr(
        dogs_module,
        "validate_dog_setup_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    generic_error = await host.async_step_add_new_dog(user_input)
    assert generic_error["errors"] == {"base": "add_dog_failed"}

    add_schema = host._get_add_dog_schema()
    assert isinstance(add_schema, vol.Schema)


@pytest.mark.asyncio
async def test_add_new_dog_success_updates_entry_and_resets_to_init(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()
    host._dogs = [{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}]
    host._entry.data = {CONF_DOGS: [dict(host._dogs[0])]}

    monkeypatch.setattr(
        dogs_module,
        "validate_dog_setup_input",
        lambda *_args, **_kwargs: {
            "dog_id": "dog-2",
            "dog_name": "Milo",
            "dog_weight": 18.5,
            "dog_size": "medium",
            "dog_age": 4,
            "dog_breed": "Beagle",
        },
    )

    result = await host.async_step_add_new_dog(
        {DOG_ID_FIELD: "dog-2", DOG_NAME_FIELD: "Milo"},
    )

    assert result == {"step": "init"}
    assert host._dogs[-1][DOG_ID_FIELD] == "dog-2"
    assert host._current_dog is not None
    assert host._current_dog[DOG_ID_FIELD] == "dog-2"
    assert host.hass.config_entries.updates[-1]["data"][CONF_DOGS][-1][
        DOG_ID_FIELD
    ] == ("dog-2")
    assert host.invalidations == 1


@pytest.mark.asyncio
async def test_add_new_dog_without_input_returns_form() -> None:  # noqa: D103
    host = _DogManagementCoverageHost()

    result = await host.async_step_add_new_dog()
    assert result["step_id"] == "add_new_dog"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_remove_schema_and_select_dog_to_edit_branches(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()

    remove_schema = host._get_remove_dog_schema(
        [
            {DOG_ID_FIELD: "", DOG_NAME_FIELD: "Skip"},
            {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: ""},
            {DOG_ID_FIELD: "dog-2", DOG_NAME_FIELD: "Luna"},
        ],
    )
    assert isinstance(remove_schema, vol.Schema)

    host._entry.data = {CONF_DOGS: []}
    no_dogs = await host.async_step_select_dog_to_edit()
    assert no_dogs == {"step": "init"}

    monkeypatch.setattr(
        dogs_module,
        "ensure_dog_config_data",
        lambda dog: None if dog.get("drop") else dog,
    )
    host._entry.data = {
        CONF_DOGS: [
            1,
            {DOG_ID_FIELD: "drop", DOG_NAME_FIELD: "Drop", "drop": True},
            {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"},
        ]
    }
    edit_step = AsyncMock(return_value={"step": "edit"})
    monkeypatch.setattr(host, "async_step_edit_dog", edit_step)

    selected = await host.async_step_select_dog_to_edit({"dog_id": "dog-1"})
    assert selected == {"step": "edit"}

    unknown = await host.async_step_select_dog_to_edit({"dog_id": "none"})
    assert unknown == {"step": "init"}

    select_form = await host.async_step_select_dog_to_edit()
    assert select_form["step_id"] == "select_dog_to_edit"

    host._entry.data = {CONF_DOGS: 123}
    non_sequence = await host.async_step_select_dog_to_edit()
    assert non_sequence == {"step": "init"}


@pytest.mark.asyncio
async def test_edit_dog_branches_and_edit_schema_empty(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()

    host._current_dog = None
    no_current = await host.async_step_edit_dog({"dog_name": "Luna"})
    assert no_current == {"step": "init"}

    host._current_dog = {DOG_ID_FIELD: "missing", DOG_NAME_FIELD: "Ghost"}
    host._dogs = [{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}]
    missing_index = await host.async_step_edit_dog({"dog_name": "Renamed"})
    assert missing_index == {"step": "init"}

    host._current_dog = {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}
    host._dogs = [{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}]
    monkeypatch.setattr(
        dogs_module,
        "validate_dog_update_input",
        lambda *_args, **_kwargs: {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna-2"},
    )
    monkeypatch.setattr(dogs_module, "ensure_dog_config_data", lambda _dog: None)
    invalid_config = await host.async_step_edit_dog({"dog_name": "Luna-2"})
    assert invalid_config["errors"] == {"base": "invalid_dog_config"}

    monkeypatch.setattr(
        dogs_module,
        "validate_dog_update_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    generic_error = await host.async_step_edit_dog({"dog_name": "Luna-3"})
    assert generic_error["errors"] == {"base": "edit_dog_failed"}

    no_input_form = await host.async_step_edit_dog()
    assert no_input_form["step_id"] == "edit_dog"

    host._current_dog = None
    empty_schema = host._get_edit_dog_schema()
    assert isinstance(empty_schema, vol.Schema)
    assert empty_schema.schema == {}


@pytest.mark.asyncio
async def test_edit_dog_success_updates_entry_and_invalidates_cache(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()
    host._current_dog = {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}
    host._dogs = [{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}]
    host._entry.data = {CONF_DOGS: [dict(host._dogs[0])]}

    monkeypatch.setattr(
        dogs_module,
        "validate_dog_update_input",
        lambda *_args, **_kwargs: {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna-2"},
    )
    monkeypatch.setattr(dogs_module, "ensure_dog_config_data", lambda dog: dict(dog))

    result = await host.async_step_edit_dog({"dog_name": "Luna-2"})
    assert result == {"step": "init"}
    assert host._dogs[0][DOG_NAME_FIELD] == "Luna-2"
    assert host._current_dog is not None
    assert host._current_dog[DOG_NAME_FIELD] == "Luna-2"
    assert host.hass.config_entries.updates[-1]["data"][CONF_DOGS][0][
        DOG_NAME_FIELD
    ] == ("Luna-2")
    assert host.invalidations == 1


@pytest.mark.asyncio
async def test_select_dog_to_remove_branches(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()

    host._dogs = []
    no_dogs = await host.async_step_select_dog_to_remove()
    assert no_dogs == {"step": "init"}

    host._dogs = [
        {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"},
        {DOG_ID_FIELD: "dog-2", DOG_NAME_FIELD: "Milo"},
    ]
    host._current_dog = {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}
    host._entry.options = {DOG_OPTIONS_FIELD: {"dog-2": {DOG_ID_FIELD: "dog-2"}}}
    monkeypatch.setattr(host, "_normalise_options_snapshot", lambda data: dict(data))

    removed = await host.async_step_select_dog_to_remove({
        "dog_id": "dog-1",
        "confirm_remove": True,
    })
    assert removed["type"] == "create_entry"
    assert host._current_dog == host._dogs[0]
    assert removed["data"][DOG_OPTIONS_FIELD] == {"dog-2": {DOG_ID_FIELD: "dog-2"}}

    cancel = await host.async_step_select_dog_to_remove({
        "dog_id": "dog-2",
        "confirm_remove": False,
    })
    assert cancel == {"step": "init"}

    confirm_form = await host.async_step_select_dog_to_remove()
    assert confirm_form["step_id"] == "select_dog_to_remove"


@pytest.mark.asyncio
async def test_select_dog_to_remove_removes_selected_dog_options_entry(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _DogManagementCoverageHost()
    host._dogs = [
        {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"},
        {DOG_ID_FIELD: "dog-2", DOG_NAME_FIELD: "Milo"},
    ]
    host._current_dog = {DOG_ID_FIELD: "dog-2", DOG_NAME_FIELD: "Milo"}
    host._entry.options = {
        DOG_OPTIONS_FIELD: {
            "dog-1": {DOG_ID_FIELD: "dog-1"},
            "dog-2": {DOG_ID_FIELD: "dog-2"},
        }
    }
    monkeypatch.setattr(host, "_normalise_options_snapshot", lambda data: dict(data))

    removed = await host.async_step_select_dog_to_remove(
        {"dog_id": "dog-1", "confirm_remove": True},
    )

    assert removed["type"] == "create_entry"
    assert host._current_dog is not None
    assert host._current_dog[DOG_ID_FIELD] == "dog-2"
    assert "dog-1" not in removed["data"][DOG_OPTIONS_FIELD]
    assert "dog-2" in removed["data"][DOG_OPTIONS_FIELD]
