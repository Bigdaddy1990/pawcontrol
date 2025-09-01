"""Options flow for Paw Control integration.

This module provides comprehensive post-setup configuration options for the
Paw Control integration. It allows users to modify all aspects of their
configuration after initial setup with organized menu-driven navigation.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.helpers import selector

from .const import (
    CONF_DASHBOARD_MODE,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
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
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_GPS_UPDATE_INTERVAL,
    DEFAULT_REMINDER_REPEAT_MIN,
    DEFAULT_RESET_TIME,
)
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)


class PawControlOptionsFlow(OptionsFlow):
    """Handle options flow for Paw Control integration with Platinum UX.

    This comprehensive options flow allows users to modify all aspects
    of their Paw Control configuration after initial setup. It provides
    organized menu-driven navigation and extensive customization options
    with modern UI patterns and enhanced validation.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow with enhanced state management.

        Args:
            config_entry: Configuration entry to modify
        """
        self._config_entry = config_entry
        self._current_dog: DogConfigData | None = None
        self._dogs: list[DogConfigData] = [
            d.copy() for d in self._config_entry.data.get(CONF_DOGS, [])
        ]
        self._navigation_stack: list[str] = []
        self._unsaved_changes: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
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
            step_id="init",
            menu_options=[
                "manage_dogs",
                "gps_settings",
                "notifications",
                "feeding_settings",
                "health_settings",
                "system_settings",
                "dashboard_settings",
                "advanced_settings",
                "import_export",
            ],
        )

    async def async_step_manage_dogs(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage dogs - add, edit, or remove dogs."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_dog":
                return await self.async_step_add_new_dog()
            elif action == "edit_dog":
                return await self.async_step_select_dog_to_edit()
            elif action == "remove_dog":
                return await self.async_step_select_dog_to_remove()
            else:
                return await self.async_step_init()

        # Show dog management menu
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        return self.async_show_form(
            step_id="manage_dogs",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="add_dog"): vol.In(
                        {
                            "add_dog": "Add new dog",
                            "edit_dog": "Edit existing dog"
                            if current_dogs
                            else "No dogs to edit",
                            "remove_dog": "Remove dog"
                            if current_dogs
                            else "No dogs to remove",
                            "back": "Back to main menu",
                        }
                    )
                }
            ),
            description_placeholders={
                "current_dogs_count": str(len(current_dogs)),
                "dogs_list": "\n".join(
                    [
                        f"• {dog.get(CONF_DOG_NAME, 'Unknown')} ({dog.get(CONF_DOG_ID, 'unknown')})"
                        for dog in current_dogs
                    ]
                )
                if current_dogs
                else "No dogs configured",
            },
        )

    async def async_step_add_new_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new dog to the configuration."""
        if user_input is not None:
            try:
                # Create the new dog config
                new_dog = {
                    CONF_DOG_ID: user_input[CONF_DOG_ID]
                    .lower()
                    .strip()
                    .replace(" ", "_"),
                    CONF_DOG_NAME: user_input[CONF_DOG_NAME].strip(),
                    CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, "").strip()
                    or "Mixed Breed",
                    CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 3),
                    CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
                    CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, "medium"),
                    "modules": {
                        "feeding": True,
                        "walk": True,
                        "health": True,
                        "notifications": True,
                        "dashboard": True,
                        "gps": False,
                        "visitor": False,
                    },
                    "created_at": asyncio.get_event_loop().time(),
                }

                # Add to existing dogs
                current_dogs = list(self._config_entry.data.get(CONF_DOGS, []))
                current_dogs.append(new_dog)

                # Update the config entry data
                new_data = {**self._config_entry.data}
                new_data[CONF_DOGS] = current_dogs

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )

                return await self.async_step_init()
            except Exception as err:
                _LOGGER.error("Error adding new dog: %s", err)
                return self.async_show_form(
                    step_id="add_new_dog",
                    data_schema=self._get_add_dog_schema(),
                    errors={"base": "add_dog_failed"},
                )

        return self.async_show_form(
            step_id="add_new_dog", data_schema=self._get_add_dog_schema()
        )

    def _get_add_dog_schema(self) -> vol.Schema:
        """Get schema for adding a new dog."""
        return vol.Schema(
            {
                vol.Required(CONF_DOG_ID): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="off",
                    )
                ),
                vol.Required(CONF_DOG_NAME): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="name",
                    )
                ),
                vol.Optional(CONF_DOG_BREED, default=""): selector.TextSelector(),
                vol.Optional(CONF_DOG_AGE, default=3): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=30, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(CONF_DOG_WEIGHT, default=20.0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=200.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kg",
                    )
                ),
                vol.Optional(CONF_DOG_SIZE, default="medium"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "toy", "label": "Toy (1-6kg)"},
                            {"value": "small", "label": "Small (6-12kg)"},
                            {"value": "medium", "label": "Medium (12-27kg)"},
                            {"value": "large", "label": "Large (27-45kg)"},
                            {"value": "giant", "label": "Giant (45-90kg)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_select_dog_to_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which dog to edit."""
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        if not current_dogs:
            return await self.async_step_init()

        if user_input is not None:
            selected_dog_id = user_input.get("dog_id")
            self._current_dog = next(
                (
                    dog
                    for dog in current_dogs
                    if dog.get(CONF_DOG_ID) == selected_dog_id
                ),
                None,
            )
            if self._current_dog:
                return await self.async_step_edit_dog()
            else:
                return await self.async_step_init()

        # Create selection options
        dog_options = [
            {
                "value": dog.get(CONF_DOG_ID),
                "label": f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})",
            }
            for dog in current_dogs
        ]

        return self.async_show_form(
            step_id="select_dog_to_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=dog_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected dog."""
        if not self._current_dog:
            return await self.async_step_init()

        if user_input is not None:
            try:
                # Update the dog in the config entry
                current_dogs = list(self._config_entry.data.get(CONF_DOGS, []))
                dog_index = next(
                    (
                        i
                        for i, dog in enumerate(current_dogs)
                        if dog.get(CONF_DOG_ID) == self._current_dog.get(CONF_DOG_ID)
                    ),
                    -1,
                )

                if dog_index >= 0:
                    # Update the dog with new values
                    updated_dog = {**current_dogs[dog_index]}
                    updated_dog.update(user_input)
                    current_dogs[dog_index] = updated_dog

                    # Update config entry
                    new_data = {**self._config_entry.data}
                    new_data[CONF_DOGS] = current_dogs

                    self.hass.config_entries.async_update_entry(
                        self._config_entry, data=new_data
                    )

                return await self.async_step_init()
            except Exception as err:
                _LOGGER.error("Error editing dog: %s", err)
                return self.async_show_form(
                    step_id="edit_dog",
                    data_schema=self._get_edit_dog_schema(),
                    errors={"base": "edit_dog_failed"},
                )

        return self.async_show_form(
            step_id="edit_dog", data_schema=self._get_edit_dog_schema()
        )

    def _get_edit_dog_schema(self) -> vol.Schema:
        """Get schema for editing a dog with current values pre-filled."""
        if not self._current_dog:
            return vol.Schema({})

        return vol.Schema(
            {
                vol.Optional(
                    CONF_DOG_NAME, default=self._current_dog.get(CONF_DOG_NAME, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DOG_BREED, default=self._current_dog.get(CONF_DOG_BREED, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DOG_AGE, default=self._current_dog.get(CONF_DOG_AGE, 3)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=30, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_DOG_WEIGHT,
                    default=self._current_dog.get(CONF_DOG_WEIGHT, 20.0),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=200.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kg",
                    )
                ),
                vol.Optional(
                    CONF_DOG_SIZE,
                    default=self._current_dog.get(CONF_DOG_SIZE, "medium"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "toy", "label": "Toy (1-6kg)"},
                            {"value": "small", "label": "Small (6-12kg)"},
                            {"value": "medium", "label": "Medium (12-27kg)"},
                            {"value": "large", "label": "Large (27-45kg)"},
                            {"value": "giant", "label": "Giant (45-90kg)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_select_dog_to_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which dog to remove."""
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        if not current_dogs:
            return await self.async_step_init()

        if user_input is not None:
            if user_input.get("confirm_remove"):
                selected_dog_id = user_input.get("dog_id")
                # Remove the selected dog
                updated_dogs = [
                    dog
                    for dog in current_dogs
                    if dog.get(CONF_DOG_ID) != selected_dog_id
                ]

                # Update config entry
                new_data = {**self._config_entry.data}
                new_data[CONF_DOGS] = updated_dogs

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )

            return await self.async_step_init()

        # Create removal confirmation form
        dog_options = [
            {
                "value": dog.get(CONF_DOG_ID),
                "label": f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})",
            }
            for dog in current_dogs
        ]

        return self.async_show_form(
            step_id="select_dog_to_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=dog_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        "confirm_remove", default=False
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={
                "warning": "This will permanently remove the selected dog and all associated data!"
            },
        )

    async def async_step_gps_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure GPS and location settings."""
        if user_input is not None:
            try:
                # Update GPS settings in options
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_GPS_UPDATE_INTERVAL: user_input.get(
                            "gps_update_interval", DEFAULT_GPS_UPDATE_INTERVAL
                        ),
                        CONF_GPS_ACCURACY_FILTER: user_input.get(
                            "gps_accuracy_filter", DEFAULT_GPS_ACCURACY_FILTER
                        ),
                        CONF_GPS_DISTANCE_FILTER: user_input.get(
                            "gps_distance_filter", DEFAULT_GPS_DISTANCE_FILTER
                        ),
                        "gps_enabled": user_input.get("gps_enabled", True),
                    }
                )

                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="gps_settings",
                    data_schema=self._get_gps_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="gps_settings", data_schema=self._get_gps_settings_schema()
        )

    def _get_gps_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get GPS settings schema with current values."""
        current_options = self._config_entry.options
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "gps_enabled",
                    default=current_values.get(
                        "gps_enabled", current_options.get("gps_enabled", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "gps_update_interval",
                    default=current_values.get(
                        "gps_update_interval",
                        current_options.get(
                            CONF_GPS_UPDATE_INTERVAL, DEFAULT_GPS_UPDATE_INTERVAL
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=600,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
                vol.Optional(
                    "gps_accuracy_filter",
                    default=current_values.get(
                        "gps_accuracy_filter",
                        current_options.get(
                            CONF_GPS_ACCURACY_FILTER, DEFAULT_GPS_ACCURACY_FILTER
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=500,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="meters",
                    )
                ),
                vol.Optional(
                    "gps_distance_filter",
                    default=current_values.get(
                        "gps_distance_filter",
                        current_options.get(
                            CONF_GPS_DISTANCE_FILTER, DEFAULT_GPS_DISTANCE_FILTER
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=100,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="meters",
                    )
                ),
            }
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure notification settings."""
        if user_input is not None:
            try:
                # Update notification settings
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_NOTIFICATIONS: {
                            CONF_QUIET_HOURS: user_input.get("quiet_hours", True),
                            CONF_QUIET_START: user_input.get("quiet_start", "22:00:00"),
                            CONF_QUIET_END: user_input.get("quiet_end", "07:00:00"),
                            CONF_REMINDER_REPEAT_MIN: user_input.get(
                                "reminder_repeat_min", DEFAULT_REMINDER_REPEAT_MIN
                            ),
                            "priority_notifications": user_input.get(
                                "priority_notifications", True
                            ),
                            "mobile_notifications": user_input.get(
                                "mobile_notifications", True
                            ),
                        }
                    }
                )

                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="notifications",
                    data_schema=self._get_notifications_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="notifications", data_schema=self._get_notifications_schema()
        )

    def _get_notifications_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get notifications settings schema."""
        current_options = self._config_entry.options
        current_notifications = current_options.get(CONF_NOTIFICATIONS, {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "quiet_hours",
                    default=current_values.get(
                        "quiet_hours", current_notifications.get(CONF_QUIET_HOURS, True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "quiet_start",
                    default=current_values.get(
                        "quiet_start",
                        current_notifications.get(CONF_QUIET_START, "22:00:00"),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "quiet_end",
                    default=current_values.get(
                        "quiet_end",
                        current_notifications.get(CONF_QUIET_END, "07:00:00"),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "reminder_repeat_min",
                    default=current_values.get(
                        "reminder_repeat_min",
                        current_notifications.get(
                            CONF_REMINDER_REPEAT_MIN, DEFAULT_REMINDER_REPEAT_MIN
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=180,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="minutes",
                    )
                ),
                vol.Optional(
                    "priority_notifications",
                    default=current_values.get(
                        "priority_notifications",
                        current_notifications.get("priority_notifications", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "mobile_notifications",
                    default=current_values.get(
                        "mobile_notifications",
                        current_notifications.get("mobile_notifications", True),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_feeding_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure feeding and nutrition settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        "feeding_settings": {
                            "default_meals_per_day": user_input.get("meals_per_day", 2),
                            "feeding_reminders": user_input.get(
                                "feeding_reminders", True
                            ),
                            "portion_tracking": user_input.get(
                                "portion_tracking", True
                            ),
                            "calorie_tracking": user_input.get(
                                "calorie_tracking", True
                            ),
                            "auto_schedule": user_input.get("auto_schedule", False),
                        }
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="feeding_settings",
                    data_schema=self._get_feeding_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="feeding_settings", data_schema=self._get_feeding_settings_schema()
        )

    def _get_feeding_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get feeding settings schema."""
        current_options = self._config_entry.options
        current_feeding = current_options.get("feeding_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "meals_per_day",
                    default=current_values.get(
                        "meals_per_day", current_feeding.get("default_meals_per_day", 2)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=6, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    "feeding_reminders",
                    default=current_values.get(
                        "feeding_reminders",
                        current_feeding.get("feeding_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "portion_tracking",
                    default=current_values.get(
                        "portion_tracking",
                        current_feeding.get("portion_tracking", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "calorie_tracking",
                    default=current_values.get(
                        "calorie_tracking",
                        current_feeding.get("calorie_tracking", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "auto_schedule",
                    default=current_values.get(
                        "auto_schedule", current_feeding.get("auto_schedule", False)
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_health_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure health monitoring settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        "health_settings": {
                            "weight_tracking": user_input.get("weight_tracking", True),
                            "medication_reminders": user_input.get(
                                "medication_reminders", True
                            ),
                            "vet_reminders": user_input.get("vet_reminders", True),
                            "grooming_reminders": user_input.get(
                                "grooming_reminders", True
                            ),
                            "health_alerts": user_input.get("health_alerts", True),
                        }
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="health_settings",
                    data_schema=self._get_health_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="health_settings", data_schema=self._get_health_settings_schema()
        )

    def _get_health_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get health settings schema."""
        current_options = self._config_entry.options
        current_health = current_options.get("health_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "weight_tracking",
                    default=current_values.get(
                        "weight_tracking", current_health.get("weight_tracking", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "medication_reminders",
                    default=current_values.get(
                        "medication_reminders",
                        current_health.get("medication_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "vet_reminders",
                    default=current_values.get(
                        "vet_reminders", current_health.get("vet_reminders", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "grooming_reminders",
                    default=current_values.get(
                        "grooming_reminders",
                        current_health.get("grooming_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "health_alerts",
                    default=current_values.get(
                        "health_alerts", current_health.get("health_alerts", True)
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_system_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure system and performance settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_RESET_TIME: user_input.get(
                            "reset_time", DEFAULT_RESET_TIME
                        ),
                        "system_settings": {
                            "data_retention_days": user_input.get(
                                "data_retention_days", 90
                            ),
                            "auto_backup": user_input.get("auto_backup", False),
                            "performance_mode": user_input.get(
                                "performance_mode", "balanced"
                            ),
                        },
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="system_settings",
                    data_schema=self._get_system_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="system_settings", data_schema=self._get_system_settings_schema()
        )

    def _get_system_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get system settings schema."""
        current_options = self._config_entry.options
        current_system = current_options.get("system_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "reset_time",
                    default=current_values.get(
                        "reset_time",
                        current_options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "data_retention_days",
                    default=current_values.get(
                        "data_retention_days",
                        current_system.get("data_retention_days", 90),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "auto_backup",
                    default=current_values.get(
                        "auto_backup", current_system.get("auto_backup", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        current_system.get("performance_mode", "balanced"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "minimal",
                                "label": "Minimal - Lowest resource usage",
                            },
                            {
                                "value": "balanced",
                                "label": "Balanced - Good performance and efficiency",
                            },
                            {
                                "value": "full",
                                "label": "Full - Maximum features and responsiveness",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_dashboard_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure dashboard and display settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_DASHBOARD_MODE: user_input.get("dashboard_mode", "full"),
                        "dashboard_settings": {
                            "show_statistics": user_input.get("show_statistics", True),
                            "show_alerts": user_input.get("show_alerts", True),
                            "compact_mode": user_input.get("compact_mode", False),
                            "show_maps": user_input.get("show_maps", True),
                        },
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="dashboard_settings",
                    data_schema=self._get_dashboard_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="dashboard_settings",
            data_schema=self._get_dashboard_settings_schema(),
        )

    def _get_dashboard_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get dashboard settings schema."""
        current_options = self._config_entry.options
        current_dashboard = current_options.get("dashboard_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "dashboard_mode",
                    default=current_values.get(
                        "dashboard_mode",
                        current_options.get(CONF_DASHBOARD_MODE, "full"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "full",
                                "label": "Full - All information displayed",
                            },
                            {
                                "value": "cards",
                                "label": "Cards - Organized card layout",
                            },
                            {
                                "value": "minimal",
                                "label": "Minimal - Essential information only",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "show_statistics",
                    default=current_values.get(
                        "show_statistics",
                        current_dashboard.get("show_statistics", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_alerts",
                    default=current_values.get(
                        "show_alerts",
                        current_dashboard.get("show_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "compact_mode",
                    default=current_values.get(
                        "compact_mode",
                        current_dashboard.get("compact_mode", False),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_maps",
                    default=current_values.get(
                        "show_maps",
                        current_dashboard.get("show_maps", True),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_advanced_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle advanced settings configuration."""
        if user_input is not None:
            try:
                # Update options with advanced settings
                self._unsaved_changes.update(
                    {
                        "performance_mode": user_input.get(
                            "performance_mode", "balanced"
                        ),
                        "debug_logging": user_input.get("debug_logging", False),
                        "data_retention_days": user_input.get(
                            "data_retention_days", 90
                        ),
                        "auto_backup": user_input.get("auto_backup", False),
                        "experimental_features": user_input.get(
                            "experimental_features", False
                        ),
                    }
                )
                # Save changes and return to main menu
                return await self._async_save_options()
            except Exception as err:
                _LOGGER.error("Error saving advanced settings: %s", err)
                return self.async_show_form(
                    step_id="advanced_settings",
                    errors={"base": "save_failed"},
                    data_schema=self._get_advanced_settings_schema(user_input),
                )

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=self._get_advanced_settings_schema(),
        )

    def _get_advanced_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get schema for advanced settings form."""
        current_options = self._config_entry.options
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        current_options.get("performance_mode", "balanced"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "minimal",
                                "label": "Minimal - Lowest resource usage",
                            },
                            {
                                "value": "balanced",
                                "label": "Balanced - Good performance and efficiency",
                            },
                            {
                                "value": "full",
                                "label": "Full - Maximum features and responsiveness",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "debug_logging",
                    default=current_values.get(
                        "debug_logging", current_options.get("debug_logging", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "data_retention_days",
                    default=current_values.get(
                        "data_retention_days",
                        current_options.get("data_retention_days", 90),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "auto_backup",
                    default=current_values.get(
                        "auto_backup", current_options.get("auto_backup", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "experimental_features",
                    default=current_values.get(
                        "experimental_features",
                        current_options.get("experimental_features", False),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_import_export(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Placeholder handler for import/export settings.

        The import/export feature has not yet been implemented. Instead of
        raising an UnknownStep error when users navigate to this menu
        entry, we immediately redirect them back to the main options menu.

        Args:
            user_input: Not used.

        Returns:
            Flow result for the initial options step.
        """
        return await self.async_step_init()

    async def _async_save_options(self) -> ConfigFlowResult:
        """Save the current options changes.

        Returns:
            Configuration flow result indicating successful save
        """
        try:
            # Merge unsaved changes with existing options
            new_options = {**self._config_entry.options, **self._unsaved_changes}

            # Clear unsaved changes
            self._unsaved_changes.clear()

            # Update the config entry
            return self.async_create_entry(
                title="",  # Title is not used for options flow
                data=new_options,
            )
        except Exception as err:
            _LOGGER.error("Failed to save options: %s", err)
            return await self.async_step_init()
