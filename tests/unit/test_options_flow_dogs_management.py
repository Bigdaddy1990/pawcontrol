"""Tests for dog management options flow helpers."""

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.options_flow_dogs_management import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DogManagementOptionsMixin,
)


class _States:
    def __init__(self, payload: dict[str, SimpleNamespace]) -> None:
        self._payload = payload

    def async_entity_ids(self, domain: str) -> list[str]:
        if domain != "binary_sensor":
            return []
        return list(self._payload)

    def get(self, entity_id: str) -> SimpleNamespace | None:
        return self._payload.get(entity_id)


class _DogManagementHost(DogManagementOptionsMixin):
    def __init__(self) -> None:
        self._entry = SimpleNamespace(data={CONF_DOGS: []}, options={})
        self._dogs: list[dict[str, Any]] = []
        self._current_dog: dict[str, Any] | None = None
        self.hass = SimpleNamespace(
            states=_States({}), config=SimpleNamespace(language="en")
        )
        self._entity_factory = SimpleNamespace(
            estimate_entity_count=lambda _profile, modules: sum(
                bool(v) for v in modules.values()
            )
        )
        self.calls: list[str] = []

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    async def async_step_add_new_dog(self) -> dict[str, str]:
        self.calls.append("add")
        return {"step": "add"}

    async def async_step_select_dog_to_edit(self) -> dict[str, str]:
        self.calls.append("edit")
        return {"step": "edit"}

    async def async_step_select_dog_to_remove(self) -> dict[str, str]:
        self.calls.append("remove")
        return {"step": "remove"}

    async def async_step_select_dog_for_modules(self) -> dict[str, str]:
        self.calls.append("modules")
        return {"step": "modules"}

    async def async_step_select_dog_for_door_sensor(self) -> dict[str, str]:
        self.calls.append("door")
        return {"step": "door"}

    async def async_step_init(self) -> dict[str, str]:
        self.calls.append("init")
        return {"step": "init"}


@pytest.mark.asyncio
async def test_async_step_manage_dogs_routes_actions() -> None:
    host = _DogManagementHost()

    assert await host.async_step_manage_dogs({"action": "add_dog"}) == {"step": "add"}
    assert await host.async_step_manage_dogs({"action": "edit_dog"}) == {"step": "edit"}
    assert await host.async_step_manage_dogs({"action": "remove_dog"}) == {
        "step": "remove"
    }
    assert await host.async_step_manage_dogs({"action": "configure_modules"}) == {
        "step": "modules"
    }
    assert await host.async_step_manage_dogs({"action": "configure_door_sensor"}) == {
        "step": "door"
    }
    assert await host.async_step_manage_dogs({"action": "unknown"}) == {"step": "init"}

    assert host.calls == ["add", "edit", "remove", "modules", "door", "init"]


@pytest.mark.asyncio
async def test_async_step_manage_dogs_builds_placeholders_from_entry_data() -> None:
    host = _DogManagementHost()
    host._entry.data[CONF_DOGS] = [{DOG_NAME_FIELD: "Luna", DOG_ID_FIELD: "dog-1"}]

    result = await host.async_step_manage_dogs()

    assert result["step_id"] == "manage_dogs"
    placeholders = result["description_placeholders"]
    assert placeholders["current_dogs_count"] == "1"
    assert "Luna (dog-1)" in placeholders["dogs_list"]


def test_get_available_door_sensors_filters_non_door_classes() -> None:
    host = _DogManagementHost()
    host.hass.states = _States({
        "binary_sensor.front_door": SimpleNamespace(
            attributes={"device_class": "door", "friendly_name": "Front Door"}
        ),
        "binary_sensor.motion": SimpleNamespace(
            attributes={"device_class": "motion", "friendly_name": "Hall Motion"}
        ),
        "binary_sensor.window": SimpleNamespace(attributes={"device_class": "window"}),
    })

    assert host._get_available_door_sensors() == {
        "binary_sensor.front_door": "Front Door",
        "binary_sensor.window": "binary_sensor.window",
    }


def test_get_module_description_placeholders_uses_profile_and_modules() -> None:
    host = _DogManagementHost()
    host._entry.options["entity_profile"] = 123
    host._current_dog = {
        DOG_ID_FIELD: "dog-1",
        DOG_NAME_FIELD: "Luna",
        DOG_MODULES_FIELD: {"feeding": True, "walk": False, "gps": True},
    }

    placeholders = host._get_module_description_placeholders()

    assert placeholders["dog_name"] == "Luna"
    assert placeholders["current_profile"] == "123"
    assert placeholders["current_entities"] == "2"
    assert "feeding" in placeholders["enabled_modules"]
    assert "gps" in placeholders["enabled_modules"]
