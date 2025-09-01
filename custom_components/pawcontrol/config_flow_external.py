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

from .const import (
    CONF_DOOR_SENSOR,
    CONF_GPS_SOURCE,
    CONF_NOTIFY_FALLBACK,
)

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
        """Get schema for external entities configuration.

        Returns:
            Schema based on enabled modules
        """
        schema_dict = {}

        # GPS source selection - REQUIRED if GPS enabled
        if self._enabled_modules.get("gps", False):
            # Get available device trackers and person entities
            device_trackers = self._get_available_device_trackers()
            person_entities = self._get_available_person_entities()

            gps_options = []
            if device_trackers:
                gps_options.extend(
                    [
                        {"value": entity_id, "label": f"📍 {name} (Device Tracker)"}
                        for entity_id, name in device_trackers.items()
                    ]
                )
            if person_entities:
                gps_options.extend(
                    [
                        {"value": entity_id, "label": f"👤 {name} (Person)"}
                        for entity_id, name in person_entities.items()
                    ]
                )

            if gps_options:
                schema_dict[vol.Required(CONF_GPS_SOURCE)] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=gps_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            else:
                # No GPS entities available - offer manual setup
                schema_dict[vol.Required(CONF_GPS_SOURCE, default="manual")] = (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": "manual",
                                    "label": "📝 Manual GPS (configure later)",
                                }
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                )

        # Door sensor for visitor mode (optional)
        if self._enabled_modules.get("visitor", False):
            door_sensors = self._get_available_door_sensors()
            if door_sensors:
                door_options = [{"value": "", "label": "None (optional)"}]
                door_options.extend(
                    [
                        {"value": entity_id, "label": f"🚪 {name}"}
                        for entity_id, name in door_sensors.items()
                    ]
                )

                schema_dict[vol.Optional(CONF_DOOR_SENSOR, default="")] = (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=door_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                )

        # Notification services (always show if advanced features enabled)
        if self._enabled_modules.get("advanced", False):
            notify_services = self._get_available_notify_services()
            if notify_services:
                notify_options = [
                    {"value": "", "label": "Default (persistent_notification)"}
                ]
                notify_options.extend(
                    [
                        {"value": service_id, "label": f"🔔 {name}"}
                        for service_id, name in notify_services.items()
                    ]
                )

                schema_dict[vol.Optional(CONF_NOTIFY_FALLBACK, default="")] = (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=notify_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                )

        return vol.Schema(schema_dict)

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

        # Validate GPS source if provided
        gps_source = user_input.get(CONF_GPS_SOURCE)
        if gps_source and gps_source != "manual":
            state = self.hass.states.get(gps_source)
            if not state:
                raise ValueError(f"GPS source entity {gps_source} not found")
            if state.state in ["unknown", "unavailable"]:
                raise ValueError(f"GPS source entity {gps_source} is unavailable")
            validated[CONF_GPS_SOURCE] = gps_source
        elif gps_source == "manual":
            validated[CONF_GPS_SOURCE] = "manual"

        # Validate door sensor if provided
        door_sensor = user_input.get(CONF_DOOR_SENSOR)
        if door_sensor:
            state = self.hass.states.get(door_sensor)
            if not state:
                raise ValueError(f"Door sensor entity {door_sensor} not found")
            validated[CONF_DOOR_SENSOR] = door_sensor

        # Validate notification service if provided
        notify_service = user_input.get(CONF_NOTIFY_FALLBACK)
        if notify_service:
            # Check if service exists
            service_parts = notify_service.split(".", 1)
            if len(service_parts) != 2 or service_parts[0] != "notify":
                raise ValueError(f"Invalid notification service: {notify_service}")

            services = self.hass.services.async_services().get("notify", {})
            if service_parts[1] not in services:
                raise ValueError(f"Notification service {service_parts[1]} not found")

            validated[CONF_NOTIFY_FALLBACK] = notify_service

        return validated
