"""Dashboard configuration extension for the config flow.

This module provides a mixin with additional steps for configuring the
dashboard during the integration setup. It can be mixed into the main
``PawControlConfigFlow`` class to keep the core config flow file concise.

Quality Scale: Bronze target
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .const import (
    CONF_MODULES,
    DASHBOARD_MODE_SELECTOR_OPTIONS,
    DEFAULT_DASHBOARD_AUTO_CREATE,
    DEFAULT_DASHBOARD_MODE,
    DEFAULT_DASHBOARD_THEME,
    MODULE_GPS,
)
from .selector_shim import selector
from .types import (
    DASHBOARD_AUTO_CREATE_FIELD,
    DASHBOARD_ENABLED_FIELD,
    DASHBOARD_MODE_FIELD,
    DASHBOARD_PER_DOG_FIELD,
    DASHBOARD_SHOW_MAPS_FIELD,
    DASHBOARD_SHOW_STATISTICS_FIELD,
    DASHBOARD_THEME_FIELD,
    DashboardSetupConfig,
    DogConfigData,
    DogModulesConfig,
)


class DashboardFlowMixin:
    """Mixin adding dashboard configuration steps to the config flow."""

    if TYPE_CHECKING:
        _dogs: list[DogConfigData]
        _enabled_modules: DogModulesConfig
        _dashboard_config: DashboardSetupConfig

        async def async_step_configure_external_entities(
            self, user_input: dict[str, Any] | None = None
        ) -> ConfigFlowResult:
            """Type-checking stub for the GPS entity configuration step."""
            ...

        async def async_step_final_setup(
            self, user_input: dict[str, Any] | None = None
        ) -> ConfigFlowResult:
            """Type-checking stub for the concluding config flow step."""
            ...

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: vol.Schema,
            description_placeholders: dict[str, Any] | None = None,
            errors: dict[str, str] | None = None,
        ) -> ConfigFlowResult:
            """Type-checking stub for Home Assistant form rendering."""
            ...

    async def async_step_configure_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure dashboard settings.

        This step allows users to configure how the dashboard should be created
        and displayed, including per-dog dashboards and theme selection.
        """

        has_multiple_dogs = len(self._dogs) > 1

        if user_input is not None:
            has_gps_enabled = self._enabled_modules.get(MODULE_GPS, False) or any(
                cast(DogModulesConfig, dog.get(CONF_MODULES, {})).get(MODULE_GPS, False)
                for dog in self._dogs
            )
            dashboard_mode = str(
                user_input.get(
                    "dashboard_mode",
                    DEFAULT_DASHBOARD_MODE if has_multiple_dogs else "cards",
                )
            )
            dashboard_config: DashboardSetupConfig = {
                DASHBOARD_ENABLED_FIELD: True,
                DASHBOARD_AUTO_CREATE_FIELD: bool(
                    user_input.get(
                        "auto_create_dashboard", DEFAULT_DASHBOARD_AUTO_CREATE
                    )
                ),
                DASHBOARD_PER_DOG_FIELD: bool(
                    user_input.get("create_per_dog_dashboards", False)
                ),
                DASHBOARD_THEME_FIELD: str(
                    user_input.get("dashboard_theme", DEFAULT_DASHBOARD_THEME)
                ),
                DASHBOARD_MODE_FIELD: dashboard_mode,
                DASHBOARD_SHOW_STATISTICS_FIELD: bool(
                    user_input.get("show_statistics", True)
                ),
                DASHBOARD_SHOW_MAPS_FIELD: bool(
                    user_input.get("show_maps", True)
                ),
            }
            self._dashboard_config = dashboard_config

            if bool(has_gps_enabled):
                return await self.async_step_configure_external_entities()
            return await self.async_step_final_setup()

        has_gps_enabled = self._enabled_modules.get(MODULE_GPS, False) or any(
            cast(DogModulesConfig, dog.get(CONF_MODULES, {})).get(MODULE_GPS, False)
            for dog in self._dogs
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    "auto_create_dashboard", default=DEFAULT_DASHBOARD_AUTO_CREATE
                ): selector.BooleanSelector(),
                vol.Optional(
                    "create_per_dog_dashboards", default=has_multiple_dogs
                ): selector.BooleanSelector(),
                vol.Optional(
                    "dashboard_theme", default=DEFAULT_DASHBOARD_THEME
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "default",
                                "label": "Default - Clean and modern",
                            },
                            {
                                "value": "dark",
                                "label": "Dark - Night-friendly theme",
                            },
                            {
                                "value": "playful",
                                "label": "Playful - Colorful and fun",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "dashboard_mode",
                    default=DEFAULT_DASHBOARD_MODE if has_multiple_dogs else "cards",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=DASHBOARD_MODE_SELECTOR_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "show_statistics", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_maps", default=has_gps_enabled
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="configure_dashboard",
            data_schema=schema,
            description_placeholders={
                "dog_count": len(self._dogs),
                "dashboard_info": self._get_dashboard_info(),
            },
        )

    def _get_dashboard_info(self) -> str:
        """Get dashboard information for display."""

        info = [
            "🎨 The dashboard will be automatically created after setup",
            "📊 It will include cards for each dog and their activities",
            "🗺️ GPS maps will be shown if GPS module is enabled",
            "📱 Dashboards are mobile-friendly and responsive",
        ]

        if len(self._dogs) > 1:
            info.append(
                f"🐕 Individual dashboards for {len(self._dogs)} dogs recommended"
            )

        return "\n".join(info)


__all__ = ["DashboardFlowMixin"]
