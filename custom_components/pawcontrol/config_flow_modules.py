"""Module configuration steps for Paw Control configuration flow.

This module handles the configuration of functional modules including
GPS tracking, dashboard settings, and other feature-specific settings
with intelligent recommendations based on dog characteristics.

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
    CONF_DOG_AGE,
    CONF_DOG_SIZE,
    CONF_MODULES,
    DEFAULT_DASHBOARD_ENABLED,
    MODULE_DASHBOARD,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
)

_LOGGER = logging.getLogger(__name__)


class ModuleConfigurationMixin:
    """Mixin for module configuration functionality in configuration flow.

    This mixin provides methods for configuring functional modules during
    the initial setup process, including intelligent suggestions based on
    dog characteristics and user preferences.
    """

    async def async_step_configure_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure modules with enhanced guidance and validation.

        This step allows users to customize functionality for their dogs
        with intelligent suggestions and clear explanations.

        Args:
            user_input: Module configuration choices

        Returns:
            Configuration flow result for next step or completion
        """
        if user_input is not None:
            # Apply module configuration to all dogs with smart defaults
            gps_enabled = user_input.get("enable_gps", False)
            health_enabled = user_input.get("enable_health", True)
            visitor_enabled = user_input.get("enable_visitor_mode", False)
            dashboard_enabled = user_input.get(
                "enable_dashboard", DEFAULT_DASHBOARD_ENABLED
            )
            advanced_features = user_input.get("enable_advanced_features", False)

            for dog in self._dogs:
                dog[CONF_MODULES].update(
                    {
                        MODULE_GPS: gps_enabled,
                        MODULE_HEALTH: health_enabled,
                        MODULE_VISITOR: visitor_enabled,
                        MODULE_DASHBOARD: dashboard_enabled,
                    }
                )

                # Advanced features include additional modules
                if advanced_features:
                    dog[CONF_MODULES][MODULE_NOTIFICATIONS] = True

            # Store enabled modules for next step
            self._enabled_modules = {
                "gps": gps_enabled,
                "health": health_enabled,
                "visitor": visitor_enabled,
                "dashboard": dashboard_enabled,
                "advanced": advanced_features,
            }

            if dashboard_enabled:
                return await self.async_step_configure_dashboard()
            if gps_enabled:
                return await self.async_step_configure_external_entities()
            return await self.async_step_final_setup()

        # Only show this step if we have dogs configured
        if not self._dogs:
            return await self.async_step_final_setup()

        # Analyze dogs for intelligent suggestions
        large_dogs = [
            d for d in self._dogs if d.get(CONF_DOG_SIZE) in ("large", "giant")
        ]
        mature_dogs = [d for d in self._dogs if d.get(CONF_DOG_AGE, 0) >= 2]

        # Default suggestions based on dog characteristics
        default_gps = len(large_dogs) > 0
        default_visitor = len(mature_dogs) > 0

        schema = vol.Schema(
            {
                vol.Optional(
                    "enable_gps", default=default_gps
                ): selector.BooleanSelector(),
                vol.Optional("enable_health", default=True): selector.BooleanSelector(),
                vol.Optional(
                    "enable_visitor_mode", default=default_visitor
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_dashboard", default=DEFAULT_DASHBOARD_ENABLED
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_advanced_features", default=len(self._dogs) > 1
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="configure_modules",
            data_schema=schema,
            description_placeholders={
                "dog_count": len(self._dogs),
                "large_dog_count": len(large_dogs),
                "mature_dog_count": len(mature_dogs),
                "gps_suggestion": "recommended" if default_gps else "optional",
                "visitor_suggestion": "recommended" if default_visitor else "optional",
                "dogs_summary": self._get_dogs_module_summary(),
            },
        )

    async def async_step_configure_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure dashboard settings during setup.

        This step allows users to configure how the dashboard should be created
        and displayed, including per-dog dashboards and theme selection.

        Args:
            user_input: Dashboard configuration choices

        Returns:
            Configuration flow result for next step
        """
        if user_input is not None:
            # Store dashboard configuration
            has_multiple_dogs = len(self._dogs) > 1
            self._dashboard_config = {
                "dashboard_enabled": True,
                "dashboard_auto_create": user_input.get("auto_create_dashboard", True),
                "dashboard_per_dog": user_input.get(
                    "create_per_dog_dashboards", has_multiple_dogs
                ),
                "dashboard_theme": user_input.get("dashboard_theme", "default"),
                "dashboard_mode": user_input.get(
                    "dashboard_mode", "full" if has_multiple_dogs else "cards"
                ),
                "show_statistics": user_input.get("show_statistics", True),
                "show_maps": user_input.get(
                    "show_maps", self._enabled_modules.get("gps", False)
                ),
                "show_alerts": user_input.get("show_alerts", True),
                "compact_mode": user_input.get("compact_mode", False),
            }

            # Continue to next step based on enabled modules
            if self._enabled_modules.get("gps", False):
                return await self.async_step_configure_external_entities()
            return await self.async_step_final_setup()

        # Build dashboard configuration form
        has_multiple_dogs = len(self._dogs) > 1
        has_gps = self._enabled_modules.get("gps", False)

        schema = vol.Schema(
            {
                vol.Optional(
                    "auto_create_dashboard", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "create_per_dog_dashboards", default=has_multiple_dogs
                ): selector.BooleanSelector(),
                vol.Optional(
                    "dashboard_theme", default="default"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "default",
                                "label": "🎨 Default - Clean and modern",
                            },
                            {
                                "value": "dark",
                                "label": "🌙 Dark - Night-friendly theme",
                            },
                            {
                                "value": "playful",
                                "label": "🎉 Playful - Colorful and fun",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "dashboard_mode", default="full" if has_multiple_dogs else "cards"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "full",
                                "label": "📊 Full - Complete dashboard with all features",
                            },
                            {
                                "value": "cards",
                                "label": "🃏 Cards - Organized card-based layout",
                            },
                            {
                                "value": "minimal",
                                "label": "⚡ Minimal - Essential information only",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "show_statistics", default=True
                ): selector.BooleanSelector(),
                vol.Optional("show_maps", default=has_gps): selector.BooleanSelector(),
                vol.Optional("show_alerts", default=True): selector.BooleanSelector(),
                vol.Optional("compact_mode", default=False): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="configure_dashboard",
            data_schema=schema,
            description_placeholders={
                "dog_count": len(self._dogs),
                "dashboard_info": self._get_dashboard_setup_info(self._enabled_modules),
                "features": self._get_dashboard_features_string(has_gps),
            },
        )
