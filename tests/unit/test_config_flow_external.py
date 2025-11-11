"""Tests for the external entity configuration mixin."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from typing import Any, cast

import pytest
from custom_components.pawcontrol.config_flow_external import (
    ExternalEntityConfigurationMixin,
)
from custom_components.pawcontrol.const import (
    CONF_DOOR_SENSOR,
    CONF_GPS_SOURCE,
    CONF_NOTIFY_FALLBACK,
    MODULE_GPS,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
)
from custom_components.pawcontrol.types import (
    DogConfigData,
    DogModulesConfig,
    ExternalEntityConfig,
)


class _FakeStates(dict[str, SimpleNamespace]):
    """Minimal state registry used by the mixin while validating entities."""


class _FakeServices:
    """Minimal service registry used by the mixin while validating notify services."""

    def __init__(self, services: dict[str, dict[str, object]]) -> None:
        self._services = services

    def async_services(
        self,
    ) -> dict[str, dict[str, object]]:  # pragma: no cover - passthrough
        return self._services


class _FakeHomeAssistant:
    """Home Assistant stub exposing the state and service registries used in tests."""

    def __init__(self, *, states: _FakeStates, services: _FakeServices) -> None:
        self.states = states
        self.services = services


class _ExternalEntityFlow(ExternalEntityConfigurationMixin):
    """Harness exposing the protected helpers from the mixin for validation tests."""

    def __init__(
        self,
        hass: _FakeHomeAssistant,
        *,
        modules: DogModulesConfig,
        external_entities: ExternalEntityConfig | None = None,
    ) -> None:
        self.hass = hass
        self._enabled_modules = modules
        self._external_entities = external_entities or ExternalEntityConfig()
        self._dogs: list[DogConfigData] = []
        self.shown_forms: list[dict[str, Any]] = []
        self.finalised: list[ExternalEntityConfig | None] = []

    async def async_step_final_setup(
        self, user_input: ExternalEntityConfig | None = None
    ) -> dict[str, Any]:
        self.finalised.append(user_input)
        return {"type": "create_entry", "data": user_input}

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: Any,
        description_placeholders: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        form_record = {
            "step_id": step_id,
            "schema": data_schema,
            "description_placeholders": description_placeholders or {},
            "errors": errors or {},
        }
        self.shown_forms.append(form_record)
        return {"type": "form", **form_record}

    def _get_available_device_trackers(self) -> dict[str, str]:
        return {"device_tracker.main_phone": "Main phone"}

    def _get_available_person_entities(self) -> dict[str, str]:
        return {"person.dog_walker": "Dog Walker"}

    def _get_available_door_sensors(self) -> dict[str, str]:
        return {"binary_sensor.back_door": "Back door"}

    def _get_available_notify_services(self) -> dict[str, str]:
        return {"notify.mobile_app_main_phone": "Main phone"}


@pytest.mark.asyncio
async def test_async_step_configure_external_entities_accepts_valid_payload() -> None:
    """The mixin persists validated entity selections into the shared mapping."""

    hass = _FakeHomeAssistant(
        states=_FakeStates(
            {
                "device_tracker.main_phone": SimpleNamespace(state="home"),
                "binary_sensor.back_door": SimpleNamespace(state="on"),
            }
        ),
        services=_FakeServices({"notify": {"mobile_app_main_phone": object()}}),
    )
    modules = cast(
        DogModulesConfig,
        {MODULE_GPS: True, MODULE_VISITOR: True, MODULE_NOTIFICATIONS: True},
    )
    flow = _ExternalEntityFlow(hass, modules=modules)

    result = await flow.async_step_configure_external_entities(
        ExternalEntityConfig(
            gps_source="device_tracker.main_phone",
            door_sensor="binary_sensor.back_door",
            notify_fallback="notify.mobile_app_main_phone",
        )
    )

    assert result["type"] == "create_entry"
    assert flow._external_entities == {
        CONF_GPS_SOURCE: "device_tracker.main_phone",
        CONF_DOOR_SENSOR: "binary_sensor.back_door",
        CONF_NOTIFY_FALLBACK: "notify.mobile_app_main_phone",
    }
    assert flow.finalised == [None]


@pytest.mark.asyncio
async def test_async_step_configure_external_entities_rejects_unknown_notify_service() -> (
    None
):
    """Invalid notify service selections surface the validation error in the form."""

    hass = _FakeHomeAssistant(
        states=_FakeStates(
            {
                "device_tracker.main_phone": SimpleNamespace(state="home"),
                "binary_sensor.back_door": SimpleNamespace(state="on"),
            }
        ),
        services=_FakeServices({"notify": {"mobile_app_main_phone": object()}}),
    )
    modules = cast(
        DogModulesConfig,
        {MODULE_GPS: True, MODULE_VISITOR: True, MODULE_NOTIFICATIONS: True},
    )
    flow = _ExternalEntityFlow(hass, modules=modules)

    result = await flow.async_step_configure_external_entities(
        ExternalEntityConfig(notify_fallback="notify.unknown_service")
    )

    assert result["type"] == "form"
    assert flow.shown_forms[0]["errors"]["base"] == (
        "Notification service unknown_service not found"
    )
    assert flow._external_entities == {}


@pytest.mark.asyncio
async def test_async_step_configure_external_entities_exposes_placeholders() -> None:
    """The mixin should expose immutable placeholders for the configuration form."""

    hass = _FakeHomeAssistant(
        states=_FakeStates({}),
        services=_FakeServices({"notify": {}}),
    )
    modules = cast(
        DogModulesConfig,
        {MODULE_GPS: True, MODULE_VISITOR: False, MODULE_NOTIFICATIONS: False},
    )
    flow = _ExternalEntityFlow(hass, modules=modules)

    result = await flow.async_step_configure_external_entities()

    assert result["type"] == "form"
    placeholders = result["description_placeholders"]
    assert isinstance(placeholders, MappingProxyType)
    assert placeholders["gps_enabled"] is True
    assert placeholders["visitor_enabled"] is False
    assert placeholders["dog_count"] == 0
