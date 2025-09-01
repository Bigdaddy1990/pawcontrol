"""Configuration flow for Paw Control integration.

This module provides a comprehensive configuration flow that meets Home Assistant's
Platinum quality standards. It uses a modular architecture with separate mixins
for different functionality areas to maintain code organization and readability.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import callback

from .const import (
    CONF_DOGS,
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT_MIN,
    CONF_RESET_TIME,
    CONF_SOURCES,
    DEFAULT_DASHBOARD_MODE,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_REMINDER_REPEAT_MIN,
    DEFAULT_RESET_TIME,
    DOMAIN,
    MODULE_GPS,
)
from .config_flow_base import INTEGRATION_SCHEMA, PawControlBaseConfigFlow
from .config_flow_dogs import DogManagementMixin
from .config_flow_external import ExternalEntityConfigurationMixin
from .config_flow_modules import ModuleConfigurationMixin
from .config_flow_dashboard_extension import DashboardFlowMixin
from .options_flow import PawControlOptionsFlow
from .types import is_dog_config_valid

_LOGGER = logging.getLogger(__name__)


class PawControlConfigFlow(
    DashboardFlowMixin,
    ExternalEntityConfigurationMixin,
    ModuleConfigurationMixin,
    DogManagementMixin,
    PawControlBaseConfigFlow,
):
    """Handle configuration flow for Paw Control integration.

    This config flow provides a comprehensive setup experience that guides
    users through configuring their dogs and initial settings. It uses a
    modular architecture with separate mixins for different functionality
    areas while maintaining extensive validation and user-friendly interface.
    Designed for Home Assistant 2025.8.2+ with Platinum quality standards.
    """

    def __init__(self) -> None:
        """Initialize the configuration flow with enhanced state management."""
        super().__init__()
        self._step_stack: list[str] = []
        self._enabled_modules: dict[str, bool] = {}
        self._external_entities: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step with enhanced validation.

        This is the entry point for the configuration flow. It collects
        basic integration information and validates uniqueness.

        Args:
            user_input: User-provided configuration data

        Returns:
            Configuration flow result for next step or completion
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                integration_name = user_input["name"].strip()

                # Enhanced validation with async checking
                validation_result = await self._async_validate_integration_name(
                    integration_name
                )

                if validation_result["valid"]:
                    # Set unique ID with enhanced collision detection
                    unique_id = self._generate_unique_id(integration_name)
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    self._integration_name = integration_name
                    return await self.async_step_add_dog()
                else:
                    errors = validation_result["errors"]

            except Exception as err:
                _LOGGER.error("Error processing user input: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=INTEGRATION_SCHEMA,
            errors=errors,
            description_placeholders={
                "integration_name": "Paw Control",
                "docs_url": "https://github.com/BigDaddy1990/pawcontrol",
                "version": "1.0.0",
                "ha_version": "2025.8.2+",
                "features": self._get_feature_summary(),
            },
        )

    async def async_step_final_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete the configuration setup with comprehensive validation.

        This final step creates the config entry with all collected
        data and sets up intelligent default options.

        Args:
            user_input: Final confirmation from user

        Returns:
            Configuration entry creation result
        """
        # Validate that we have at least one dog
        if not self._dogs:
            _LOGGER.error("No dogs configured during setup")
            return self.async_abort(reason="no_dogs_configured")

        try:
            # Create comprehensive configuration data
            config_data = {
                "name": self._integration_name,
                CONF_DOGS: self._dogs,
                "setup_version": self.VERSION,
                "setup_timestamp": asyncio.get_event_loop().time(),
            }

            # Add external entities configuration if configured
            if self._external_entities:
                config_data[CONF_SOURCES] = self._external_entities

            # Create intelligent default options based on configuration
            options_data = await self._create_intelligent_options(config_data)
            if hasattr(self, "_dashboard_config"):
                options_data.update(self._dashboard_config)

            # Validate configuration integrity
            if not is_dog_config_valid(self._dogs[0]) if self._dogs else False:
                raise ValueError("Invalid dog configuration detected")

            _LOGGER.info(
                "Creating Paw Control config entry '%s' with %d dogs",
                self._integration_name,
                len(self._dogs),
            )

            return self.async_create_entry(
                title=self._integration_name,
                data=config_data,
                options=options_data,
            )

        except Exception as err:
            _LOGGER.error("Failed to create config entry: %s", err)
            return self.async_abort(reason="setup_failed")

    async def _create_intelligent_options(
        self, config_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create intelligent default options based on configuration.

        Args:
            config_data: Complete configuration data

        Returns:
            Optimized options dictionary
        """
        dogs = config_data[CONF_DOGS]

        # Analyze configuration for intelligent defaults
        has_gps = any(dog.get("modules", {}).get(MODULE_GPS, False) for dog in dogs)
        has_multiple_dogs = len(dogs) > 1
        has_large_dogs = any(
            dog.get("dog_size") in ("large", "giant") for dog in dogs
        )

        # Performance mode based on complexity
        if has_multiple_dogs and has_gps:
            performance_mode = "balanced"
        elif has_gps or has_multiple_dogs:
            performance_mode = "balanced"
        else:
            performance_mode = "minimal"

        # Update interval based on features
        if has_gps:
            update_interval = 60 if has_multiple_dogs else 45
        else:
            update_interval = 120

        return {
            CONF_RESET_TIME: DEFAULT_RESET_TIME,
            CONF_NOTIFICATIONS: {
                CONF_QUIET_HOURS: True,
                CONF_QUIET_START: "22:00:00",
                CONF_QUIET_END: "07:00:00",
                CONF_REMINDER_REPEAT_MIN: DEFAULT_REMINDER_REPEAT_MIN,
                "priority_notifications": has_large_dogs,
                "summary_notifications": has_multiple_dogs,
            },
            CONF_GPS_UPDATE_INTERVAL: update_interval,
            CONF_GPS_ACCURACY_FILTER: DEFAULT_GPS_ACCURACY_FILTER,
            CONF_GPS_DISTANCE_FILTER: DEFAULT_GPS_DISTANCE_FILTER,
            "dashboard_mode": DEFAULT_DASHBOARD_MODE
            if has_multiple_dogs
            else "cards",
            "performance_mode": performance_mode,
            "data_retention_days": 90,
            "auto_backup": has_multiple_dogs,
            "debug_logging": False,
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PawControlOptionsFlow:
        """Create the options flow for post-setup configuration.

        Args:
            config_entry: The config entry to create options flow for

        Returns:
            Enhanced options flow instance for advanced configuration
        """
        return PawControlOptionsFlow(config_entry)
