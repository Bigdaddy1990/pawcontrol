"""External entity configuration steps for Paw Control configuration flow.

This module handles the configuration of external Home Assistant entities
that the integration depends on, including GPS sources, door sensors,
and notification services with comprehensive validation.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector

from .const import CONF_DOOR_SENSOR, CONF_GPS_SOURCE, CONF_NOTIFY_FALLBACK

_LOGGER = logging.getLogger(__name__)


class ExternalEntityConfigurationMixin:
    """Mixin for external entity configuration functionality.

    This mixin provides methods for configuring external Home Assistant
    entities that the integration depends on during setup. This is critical
    for Platinum quality scale compliance and ensures proper integration
    with the broader Home Assistant ecosystem.
    """

    async def async_step_configure_external_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure external entities required for enabled modules.

        This critical step configures external Home Assistant entities that
        the integration depends on. Required for Platinum quality scale compliance.

        Args:
            user_input: External entity configuration

        Returns:
            Configuration flow result for final setup
        """
        if user_input is not None:
            # Validate and store external entity selections
            try:
                validated_entities = await self._async_validate_external_entities(
                    user_input
                )
                self._external_entities.update(validated_entities)
                return await self.async_step_final_setup()
            except ValueError as err:
                return self.async_show_form(
                    step_id="configure_external_entities",
                    data_schema=self._get_external_entities_schema(),
                    errors={"base": str(err)},
                )

        return self.async_show_form(
            step_id="configure_external_entities",
            data_schema=self._get_external_entities_schema(),
            description_placeholders={
                "gps_enabled": self._enabled_modules.get("gps", False),
                "visitor_enabled": self._enabled_modules.get("visitor", False),
                "dog_count": len(self._dogs),
            },
        )

    def _get_external_entities_schema(self) -> vol.Schema:
        """Get schema for external entities configuration."""
        schema: dict[Any, Any] = {}

        if self._enabled_modules.get("gps", False):
            schema.update(self._build_gps_source_selector())

        if self._enabled_modules.get("visitor", False):
            schema.update(self._build_door_sensor_selector())

        if self._enabled_modules.get("advanced", False):
            schema.update(self._build_notify_service_selector())

        return vol.Schema(schema)

    def _build_gps_source_selector(self) -> dict[Any, Any]:
        """Build selector schema for GPS source."""
        device_trackers = self._get_available_device_trackers()
        person_entities = self._get_available_person_entities()

        options: list[dict[str, str]] = []
        if device_trackers:
            options.extend(
                {
                    "value": entity_id,
                    "label": f"📍 {name} (Device Tracker)",
                }
                for entity_id, name in device_trackers.items()
            )
        if person_entities:
            options.extend(
                {
                    "value": entity_id,
                    "label": f"👤 {name} (Person)",
                }
                for entity_id, name in person_entities.items()
            )

        if options:
            selector_config = selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
            return {
                vol.Required(CONF_GPS_SOURCE): selector.SelectSelector(selector_config)
            }

        selector_config = selector.SelectSelectorConfig(
            options=[{"value": "manual", "label": "📝 Manual GPS (configure later)"}],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
        return {
            vol.Required(CONF_GPS_SOURCE, default="manual"): selector.SelectSelector(
                selector_config
            )
        }

    def _build_door_sensor_selector(self) -> dict[Any, Any]:
        """Build selector schema for door sensor."""
        door_sensors = self._get_available_door_sensors()
        if not door_sensors:
            return {}

        options = [{"value": "", "label": "None (optional)"}]
        options.extend(
            {"value": entity_id, "label": f"🚪 {name}"}
            for entity_id, name in door_sensors.items()
        )

        selector_config = selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN
        )
        return {
            vol.Optional(CONF_DOOR_SENSOR, default=""): selector.SelectSelector(
                selector_config
            )
        }

    def _build_notify_service_selector(self) -> dict[Any, Any]:
        """Build selector schema for notification fallback service."""
        notify_services = self._get_available_notify_services()
        if not notify_services:
            return {}

        options = [{"value": "", "label": "Default (persistent_notification)"}]
        options.extend(
            {"value": service_id, "label": f"🔔 {name}"}
            for service_id, name in notify_services.items()
        )

        selector_config = selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN
        )
        return {
            vol.Optional(CONF_NOTIFY_FALLBACK, default=""): selector.SelectSelector(
                selector_config
            )
        }

    async def _async_validate_external_entities(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Validate external entity selections.

        Args:
            user_input: User selections to validate

        Returns:
            Validated entity configuration

        Raises:
            ValueError: If validation fails
        """
        validated = {}

        validated.update(self._validate_gps_source(user_input.get(CONF_GPS_SOURCE)))
        validated.update(self._validate_door_sensor(user_input.get(CONF_DOOR_SENSOR)))
        validated.update(
            self._validate_notify_service(user_input.get(CONF_NOTIFY_FALLBACK))
        )

        return validated

    def _validate_gps_source(self, gps_source: str | None) -> dict[str, str]:
        """Validate GPS source selection."""
        if not gps_source:
            return {}
        if gps_source == "manual":
            return {CONF_GPS_SOURCE: "manual"}

        state = self.hass.states.get(gps_source)
        if not state:
            raise ValueError(f"GPS source entity {gps_source} not found")
        if state.state in ["unknown", "unavailable"]:
            raise ValueError(f"GPS source entity {gps_source} is unavailable")
        return {CONF_GPS_SOURCE: gps_source}

    def _validate_door_sensor(self, door_sensor: str | None) -> dict[str, str]:
        """Validate door sensor selection."""
        if not door_sensor:
            return {}
        state = self.hass.states.get(door_sensor)
        if not state:
            raise ValueError(f"Door sensor entity {door_sensor} not found")
        return {CONF_DOOR_SENSOR: door_sensor}

    def _validate_notify_service(self, notify_service: str | None) -> dict[str, str]:
        """Validate notification service selection."""
        if not notify_service:
            return {}
        service_parts = notify_service.split(".", 1)
        if len(service_parts) != 2 or service_parts[0] != "notify":
            raise ValueError(f"Invalid notification service: {notify_service}")

        services = self.hass.services.async_services().get("notify", {})
        if service_parts[1] not in services:
            raise ValueError(f"Notification service {service_parts[1]} not found")

        return {CONF_NOTIFY_FALLBACK: notify_service}
