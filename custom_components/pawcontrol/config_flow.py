"""Config flow for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TimeSelector,
)

from .const import (
    CONF_CALENDAR,
    CONF_DEVICE_TRACKERS,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_DOOR_SENSOR,
    CONF_EXPORT_FORMAT,
    CONF_EXPORT_PATH,
    CONF_NOTIFICATIONS,
    CONF_NOTIFY_FALLBACK,
    CONF_PERSON_ENTITIES,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT,
    CONF_RESET_TIME,
    CONF_SNOOZE_MIN,
    CONF_SOURCES,
    CONF_VISITOR_MODE,
    CONF_WEATHER,
    DEFAULT_EXPORT_FORMAT,
    DEFAULT_REMINDER_REPEAT,
    DEFAULT_RESET_TIME,
    DEFAULT_SNOOZE_MIN,
    DOMAIN,
    MODULE_DASHBOARD,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_MEDICATION,
    MODULE_NOTIFICATIONS,
    MODULE_TRAINING,
    MODULE_WALK,
)

_LOGGER = logging.getLogger(__name__)


class PawControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Paw Control."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._dogs: list[dict] = []
        self._current_dog_index = 0
        self._sources: dict = {}
        self._notifications: dict = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            # Store number of dogs and proceed to dog configuration
            num_dogs = int(user_input.get("num_dogs", 1))
            self._dogs = [{} for _ in range(num_dogs)]
            self._current_dog_index = 0
            return await self.async_step_dog_config()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("num_dogs", default=1): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=10,
                            mode="box",
                        )
                    ),
                }
            ),
            description_placeholders={
                "intro": "Welcome to Paw Control! Let's set up your smart dog management system."
            },
        )

    async def async_step_dog_config(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure individual dog."""
        errors = {}

        if user_input is not None:
            # Validate dog ID uniqueness
            dog_id = user_input.get(CONF_DOG_ID, "").lower().replace(" ", "_")

            # Check for duplicate dog IDs
            existing_ids = [d.get(CONF_DOG_ID) for d in self._dogs[: self._current_dog_index]]
            if dog_id in existing_ids:
                errors["base"] = "duplicate_dog_id"

            if not errors:
                # Store dog configuration
                self._dogs[self._current_dog_index] = {
                    CONF_DOG_ID: dog_id,
                    CONF_DOG_NAME: user_input.get(CONF_DOG_NAME, dog_id),
                    CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, "Mixed"),
                    CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 1),
                    CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20),
                    CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, "medium"),
                    CONF_DOG_MODULES: {
                        MODULE_WALK: user_input.get(f"module_{MODULE_WALK}", True),
                        MODULE_FEEDING: user_input.get(f"module_{MODULE_FEEDING}", True),
                        MODULE_HEALTH: user_input.get(f"module_{MODULE_HEALTH}", True),
                        MODULE_GPS: user_input.get(f"module_{MODULE_GPS}", False),
                        MODULE_NOTIFICATIONS: user_input.get(f"module_{MODULE_NOTIFICATIONS}", True),
                        MODULE_DASHBOARD: user_input.get(f"module_{MODULE_DASHBOARD}", True),
                        MODULE_GROOMING: user_input.get(f"module_{MODULE_GROOMING}", True),
                        MODULE_MEDICATION: user_input.get(f"module_{MODULE_MEDICATION}", False),
                        MODULE_TRAINING: user_input.get(f"module_{MODULE_TRAINING}", False),
                    },
                }

                self._current_dog_index += 1

                # Check if more dogs to configure
                if self._current_dog_index < len(self._dogs):
                    return await self.async_step_dog_config()
                else:
                    # All dogs configured, proceed to sources
                    return await self.async_step_sources()

        # Show dog configuration form
        dog_num = self._current_dog_index + 1
        total_dogs = len(self._dogs)

        return self.async_show_form(
            step_id="dog_config",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DOG_ID): TextSelector(),
                    vol.Required(CONF_DOG_NAME): TextSelector(),
                    vol.Optional(CONF_DOG_BREED, default="Mixed"): TextSelector(),
                    vol.Optional(CONF_DOG_AGE, default=1): NumberSelector(
                        NumberSelectorConfig(min=0, max=30, mode="box")
                    ),
                    vol.Optional(CONF_DOG_WEIGHT, default=20): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=200,
                            step=0.1,
                            mode="box",
                            unit_of_measurement="kg",
                        )
                    ),
                    vol.Optional(CONF_DOG_SIZE, default="medium"): SelectSelector(
                        SelectSelectorConfig(
                            options=["small", "medium", "large", "xlarge"],
                            translation_key="dog_size",
                        )
                    ),
                    vol.Optional(f"module_{MODULE_WALK}", default=True): BooleanSelector(),
                    vol.Optional(f"module_{MODULE_FEEDING}", default=True): BooleanSelector(),
                    vol.Optional(f"module_{MODULE_HEALTH}", default=True): BooleanSelector(),
                    vol.Optional(f"module_{MODULE_GPS}", default=False): BooleanSelector(),
                    vol.Optional(f"module_{MODULE_NOTIFICATIONS}", default=True): BooleanSelector(),
                    vol.Optional(f"module_{MODULE_DASHBOARD}", default=True): BooleanSelector(),
                    vol.Optional(f"module_{MODULE_GROOMING}", default=True): BooleanSelector(),
                    vol.Optional(f"module_{MODULE_MEDICATION}", default=False): BooleanSelector(),
                    vol.Optional(f"module_{MODULE_TRAINING}", default=False): BooleanSelector(),
                }
            ),
            errors=errors,
            description_placeholders={
                "dog_num": str(dog_num),
                "total_dogs": str(total_dogs),
            },
        )

    async def async_step_sources(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure data sources."""
        if user_input is not None:
            self._sources = user_input
            return await self.async_step_notifications()

        # Check which modules need sources
        needs_door_sensor = any(
            dog.get(CONF_DOG_MODULES, {}).get(MODULE_WALK, False) for dog in self._dogs
        )
        needs_gps = any(dog.get(CONF_DOG_MODULES, {}).get(MODULE_GPS, False) for dog in self._dogs)

        schema_dict = {}

        if needs_door_sensor:
            schema_dict[vol.Optional(CONF_DOOR_SENSOR)] = EntitySelector(
                EntitySelectorConfig(domain="binary_sensor")
            )

        if needs_gps:
            schema_dict[vol.Optional(CONF_PERSON_ENTITIES, default=[])] = EntitySelector(
                EntitySelectorConfig(domain="person", multiple=True)
            )
            schema_dict[vol.Optional(CONF_DEVICE_TRACKERS, default=[])] = EntitySelector(
                EntitySelectorConfig(domain="device_tracker", multiple=True)
            )

        schema_dict[vol.Optional(CONF_CALENDAR)] = EntitySelector(
            EntitySelectorConfig(domain="calendar")
        )
        schema_dict[vol.Optional(CONF_WEATHER)] = EntitySelector(
            EntitySelectorConfig(domain="weather")
        )

        if not schema_dict:
            # No sources needed, skip to notifications
            return await self.async_step_notifications()

        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "info": "Configure optional data sources for enhanced functionality."
            },
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure notification settings."""
        if user_input is not None:
            self._notifications = user_input
            return await self.async_step_system()

        # Check if notifications module is enabled
        needs_notifications = any(
            dog.get(CONF_DOG_MODULES, {}).get(MODULE_NOTIFICATIONS, False) for dog in self._dogs
        )

        if not needs_notifications:
            # Notifications not needed, skip to system
            return await self.async_step_system()

        return self.async_show_form(
            step_id="notifications",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NOTIFY_FALLBACK): EntitySelector(
                        EntitySelectorConfig(domain="notify")
                    ),
                    vol.Optional(
                        f"{CONF_QUIET_HOURS}_{CONF_QUIET_START}", default="22:00:00"
                    ): TimeSelector(),
                    vol.Optional(
                        f"{CONF_QUIET_HOURS}_{CONF_QUIET_END}", default="07:00:00"
                    ): TimeSelector(),
                    vol.Optional(
                        CONF_REMINDER_REPEAT, default=DEFAULT_REMINDER_REPEAT
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=5,
                            max=120,
                            step=5,
                            mode="slider",
                            unit_of_measurement="min",
                        )
                    ),
                    vol.Optional(CONF_SNOOZE_MIN, default=DEFAULT_SNOOZE_MIN): NumberSelector(
                        NumberSelectorConfig(
                            min=5,
                            max=60,
                            step=5,
                            mode="slider",
                            unit_of_measurement="min",
                        )
                    ),
                }
            ),
            description_placeholders={
                "info": "Configure how and when you want to receive notifications."
            },
        )

    async def async_step_system(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure system settings."""
        if user_input is not None:
            # Compile all configuration
            notifications_data = {
                CONF_QUIET_HOURS: {
                    CONF_QUIET_START: self._notifications.get(
                        f"{CONF_QUIET_HOURS}_{CONF_QUIET_START}", "22:00:00"
                    ),
                    CONF_QUIET_END: self._notifications.get(
                        f"{CONF_QUIET_HOURS}_{CONF_QUIET_END}", "07:00:00"
                    ),
                },
                CONF_REMINDER_REPEAT: self._notifications.get(
                    CONF_REMINDER_REPEAT, DEFAULT_REMINDER_REPEAT
                ),
                CONF_SNOOZE_MIN: self._notifications.get(
                    CONF_SNOOZE_MIN, DEFAULT_SNOOZE_MIN
                ),
            }

            notify_fallback = self._notifications.get(CONF_NOTIFY_FALLBACK)
            if notify_fallback is not None:
                notifications_data[CONF_NOTIFY_FALLBACK] = notify_fallback

            config_data = {
                CONF_DOGS: self._dogs,
                CONF_SOURCES: self._sources,
                CONF_NOTIFICATIONS: notifications_data,
                CONF_RESET_TIME: user_input.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
                CONF_EXPORT_PATH: user_input.get(CONF_EXPORT_PATH, ""),
                CONF_EXPORT_FORMAT: user_input.get(
                    CONF_EXPORT_FORMAT, DEFAULT_EXPORT_FORMAT
                ),
                CONF_VISITOR_MODE: user_input.get(CONF_VISITOR_MODE, False),
            }

            # Create the config entry
            return self.async_create_entry(
                title="Paw Control",
                data={},
                options=config_data,
            )

        return self.async_show_form(
            step_id="system",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_RESET_TIME, default=DEFAULT_RESET_TIME): TimeSelector(),
                    vol.Optional(CONF_EXPORT_PATH, default=""): TextSelector(),
                    vol.Optional(CONF_EXPORT_FORMAT, default=DEFAULT_EXPORT_FORMAT): SelectSelector(
                        SelectSelectorConfig(
                            options=["csv", "json", "pdf"],
                            translation_key="export_format",
                        )
                    ),
                    vol.Optional(CONF_VISITOR_MODE, default=False): BooleanSelector(),
                }
            ),
            description_placeholders={
                "info": "Configure system-wide settings and maintenance options."
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PawControlOptionsFlow:
        """Get the options flow for this handler."""
        return PawControlOptionsFlow(config_entry)


class PawControlOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Paw Control."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)
        self._options = dict(config_entry.options)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "dogs",
                "sources",
                "notifications",
                "system",
            ],
        )

    async def async_step_dogs(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage dogs configuration."""
        if user_input is not None:
            # Update dogs configuration
            self._options[CONF_DOGS] = user_input.get(CONF_DOGS, self._options.get(CONF_DOGS, []))
            return self.async_create_entry(title="", data=self._options)

        # For simplicity, we'll just show a message here
        # In a real implementation, this would allow editing the dogs list
        return self.async_show_form(
            step_id="dogs",
            data_schema=vol.Schema({}),
            description_placeholders={
                "info": "Dog management requires reconfiguration. Please remove and re-add the integration to change dogs."
            },
        )

    async def async_step_sources(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage data sources."""
        if user_input is not None:
            self._options[CONF_SOURCES] = user_input
            return self.async_create_entry(title="", data=self._options)

        sources = self._options.get(CONF_SOURCES, {})

        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DOOR_SENSOR, default=sources.get(CONF_DOOR_SENSOR)
                    ): EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
                    vol.Optional(
                        CONF_PERSON_ENTITIES,
                        default=sources.get(CONF_PERSON_ENTITIES, []),
                    ): EntitySelector(EntitySelectorConfig(domain="person", multiple=True)),
                    vol.Optional(
                        CONF_DEVICE_TRACKERS,
                        default=sources.get(CONF_DEVICE_TRACKERS, []),
                    ): EntitySelector(EntitySelectorConfig(domain="device_tracker", multiple=True)),
                    vol.Optional(CONF_CALENDAR, default=sources.get(CONF_CALENDAR)): EntitySelector(
                        EntitySelectorConfig(domain="calendar")
                    ),
                    vol.Optional(CONF_WEATHER, default=sources.get(CONF_WEATHER)): EntitySelector(
                        EntitySelectorConfig(domain="weather")
                    ),
                }
            ),
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage notification settings."""
        if user_input is not None:
            quiet_hours = self._options.get(CONF_NOTIFICATIONS, {}).get(CONF_QUIET_HOURS, {})

            self._options[CONF_NOTIFICATIONS] = {
                CONF_NOTIFY_FALLBACK: user_input.get(CONF_NOTIFY_FALLBACK),
                CONF_QUIET_HOURS: {
                    CONF_QUIET_START: user_input.get(
                        f"{CONF_QUIET_HOURS}_{CONF_QUIET_START}",
                        quiet_hours.get(CONF_QUIET_START, "22:00:00"),
                    ),
                    CONF_QUIET_END: user_input.get(
                        f"{CONF_QUIET_HOURS}_{CONF_QUIET_END}",
                        quiet_hours.get(CONF_QUIET_END, "07:00:00"),
                    ),
                },
                CONF_REMINDER_REPEAT: user_input.get(CONF_REMINDER_REPEAT, DEFAULT_REMINDER_REPEAT),
                CONF_SNOOZE_MIN: user_input.get(CONF_SNOOZE_MIN, DEFAULT_SNOOZE_MIN),
            }
            return self.async_create_entry(title="", data=self._options)

        notifications = self._options.get(CONF_NOTIFICATIONS, {})
        quiet_hours = notifications.get(CONF_QUIET_HOURS, {})

        return self.async_show_form(
            step_id="notifications",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NOTIFY_FALLBACK,
                        default=notifications.get(CONF_NOTIFY_FALLBACK),
                    ): EntitySelector(EntitySelectorConfig(domain="notify")),
                    vol.Optional(
                        f"{CONF_QUIET_HOURS}_{CONF_QUIET_START}",
                        default=quiet_hours.get(CONF_QUIET_START, "22:00:00"),
                    ): TimeSelector(),
                    vol.Optional(
                        f"{CONF_QUIET_HOURS}_{CONF_QUIET_END}",
                        default=quiet_hours.get(CONF_QUIET_END, "07:00:00"),
                    ): TimeSelector(),
                    vol.Optional(
                        CONF_REMINDER_REPEAT,
                        default=notifications.get(CONF_REMINDER_REPEAT, DEFAULT_REMINDER_REPEAT),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=5,
                            max=120,
                            step=5,
                            mode="slider",
                            unit_of_measurement="min",
                        )
                    ),
                    vol.Optional(
                        CONF_SNOOZE_MIN,
                        default=notifications.get(CONF_SNOOZE_MIN, DEFAULT_SNOOZE_MIN),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=5,
                            max=60,
                            step=5,
                            mode="slider",
                            unit_of_measurement="min",
                        )
                    ),
                }
            ),
        )

    async def async_step_system(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage system settings."""
        if user_input is not None:
            self._options[CONF_RESET_TIME] = user_input.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)
            self._options[CONF_EXPORT_PATH] = user_input.get(CONF_EXPORT_PATH, "")
            self._options[CONF_EXPORT_FORMAT] = user_input.get(
                CONF_EXPORT_FORMAT, DEFAULT_EXPORT_FORMAT
            )
            self._options[CONF_VISITOR_MODE] = user_input.get(CONF_VISITOR_MODE, False)
            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="system",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_RESET_TIME,
                        default=self._options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
                    ): TimeSelector(),
                    vol.Optional(
                        CONF_EXPORT_PATH,
                        default=self._options.get(CONF_EXPORT_PATH, ""),
                    ): TextSelector(),
                    vol.Optional(
                        CONF_EXPORT_FORMAT,
                        default=self._options.get(CONF_EXPORT_FORMAT, DEFAULT_EXPORT_FORMAT),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=["csv", "json", "pdf"],
                            translation_key="export_format",
                        )
                    ),
                    vol.Optional(
                        CONF_VISITOR_MODE,
                        default=self._options.get(CONF_VISITOR_MODE, False),
                    ): BooleanSelector(),
                }
            ),
        )
