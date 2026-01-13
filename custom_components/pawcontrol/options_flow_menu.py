"""Main menu step for the PawControl options flow."""

from __future__ import annotations

from homeassistant.config_entries import ConfigFlowResult

from .types import OptionsMainMenuInput


class MenuOptionsMixin:
    async def async_step_init(
        self, user_input: OptionsMainMenuInput | None = None
    ) -> ConfigFlowResult:
        """Show the main options menu with enhanced navigation.

        Provides organized access to all configuration categories
        with clear descriptions and intelligent suggestions.

        Args:
            user_input: User menu selection

        Returns:
            Configuration flow result for selected option
        """
        return self.async_show_menu(
            step_id='init',
            menu_options=[
                'entity_profiles',  # NEW: Profile management
                'manage_dogs',
                'performance_settings',  # NEW: Performance & profiles
                'gps_settings',
                'geofence_settings',  # NEW: Geofencing configuration
                'weather_settings',  # NEW: Weather configuration
                'notifications',
                'feeding_settings',
                'health_settings',
                'system_settings',
                'dashboard_settings',
                'advanced_settings',
                'import_export',
            ],
        )

    # NEW: Geofencing configuration step per requirements
