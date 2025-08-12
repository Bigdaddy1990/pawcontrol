"""Config flow for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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

    async def async_step_dog_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure individual dog."""
        errors = {}

        if user_input is not None:
            # Validate dog ID uniqueness
            dog_id = user_input.get(CONF_DOG_ID, "").lower().replace(" ", "_")

            # Check for duplicate dog IDs
            existing_ids = [
                d.get(CONF_DOG_ID) for d in self._dogs[: self._current_dog_index]
            ]
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
                        MODULE_FEEDING: user_input.get(
                            f"module_{MODULE_FEEDING}", True
                        ),
                        MODULE_HEALTH: user_input.get(f"module_{MODULE_HEALTH}", True),
                        MODULE_GPS: user_input.get(f"module_{MODULE_GPS}", False),
                        MODULE_NOTIFICATIONS: user_input.get(
                            f"module_{MODULE_NOTIFICATIONS}", True
                        ),
                        MODULE_DASHBOARD: user_input.get(
                            f"module_{MODULE_DASHBOARD}", True
                        ),
                        MODULE_GROOMING: user_input.get(
                            f"module_{MODULE_GROOMING}", True
                        ),
                        MODULE_MEDICATION: user_input.get(
                            f"module_{MODULE_MEDICATION}", False
                        ),
                        MODULE_TRAINING: user_input.get(
                            f"module_{MODULE_TRAINING}", False
                        ),
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
                            translation_key="size",
                        )
                    ),
                    vol.Optional(
                        f"module_{MODULE_WALK}", default=True
                    ): BooleanSelector(),
                    vol.Optional(
                        f"module_{MODULE_FEEDING}", default=True
                    ): BooleanSelector(),
                    vol.Optional(
                        f"module_{MODULE_HEALTH}", default=True
                    ): BooleanSelector(),
                    vol.Optional(
                        f"module_{MODULE_GPS}", default=False
                    ): BooleanSelector(),
                    vol.Optional(
                        f"module_{MODULE_NOTIFICATIONS}", default=True
                    ): BooleanSelector(),
                    vol.Optional(
                        f"module_{MODULE_DASHBOARD}", default=True
                    ): BooleanSelector(),
                    vol.Optional(
                        f"module_{MODULE_GROOMING}", default=True
                    ): BooleanSelector(),
                    vol.Optional(
                        f"module_{MODULE_MEDICATION}", default=False
                    ): BooleanSelector(),
                    vol.Optional(
                        f"module_{MODULE_TRAINING}", default=False
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
            description_placeholders={
                "dog_num": str(dog_num),
                "total_dogs": str(total_dogs),
            },
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure data sources."""
        if user_input is not None:
            # Store provided sources, dropping any values left unset
            self._sources = {k: v for k, v in user_input.items() if v is not None}
            return await self.async_step_notifications()

        # Check which modules need sources
        needs_door_sensor = any(
            dog.get(CONF_DOG_MODULES, {}).get(MODULE_WALK, False) for dog in self._dogs
        )
        needs_gps = any(
            dog.get(CONF_DOG_MODULES, {}).get(MODULE_GPS, False) for dog in self._dogs
        )

        # If no modules require external sources, skip this step entirely
        if not needs_door_sensor and not needs_gps:
            return await self.async_step_notifications()

        schema_dict = {}

        if needs_door_sensor:
            schema_dict[vol.Optional(CONF_DOOR_SENSOR)] = EntitySelector(
                EntitySelectorConfig(domain="binary_sensor")
            )

        if needs_gps:
            schema_dict[vol.Optional(CONF_PERSON_ENTITIES, default=[])] = (
                EntitySelector(EntitySelectorConfig(domain="person", multiple=True))
            )
            schema_dict[vol.Optional(CONF_DEVICE_TRACKERS, default=[])] = (
                EntitySelector(
                    EntitySelectorConfig(domain="device_tracker", multiple=True)
                )
            )

        # Optional calendar and weather integrations
        schema_dict[vol.Optional(CONF_CALENDAR, default=None)] = vol.Any(
            None,
            EntitySelector(EntitySelectorConfig(domain="calendar")),
        )
        schema_dict[vol.Optional(CONF_WEATHER, default=None)] = vol.Any(
            None,
            EntitySelector(EntitySelectorConfig(domain="weather")),
        )

        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema(schema_dict, extra=vol.ALLOW_EXTRA),
            description_placeholders={
                "info": "Configure optional data sources for enhanced functionality.",
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
            dog.get(CONF_DOG_MODULES, {}).get(MODULE_NOTIFICATIONS, False)
            for dog in self._dogs
        )

        if not needs_notifications:
            # Notifications not needed, skip to system
            return await self.async_step_system()

        return self.async_show_form(
            step_id="notifications",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NOTIFY_FALLBACK): TextSelector(),
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
                    vol.Optional(
                        CONF_SNOOZE_MIN, default=DEFAULT_SNOOZE_MIN
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
            description_placeholders={
                "info": "Configure how and when you want to receive notifications."
            },
        )

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
                    vol.Optional(
                        CONF_RESET_TIME, default=DEFAULT_RESET_TIME
                    ): TimeSelector(),
                    vol.Optional(CONF_EXPORT_PATH, default=""): TextSelector(),
                    vol.Optional(
                        CONF_EXPORT_FORMAT, default=DEFAULT_EXPORT_FORMAT
                    ): SelectSelector(
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
        self.config_entry = config_entry
        self._options = dict(config_entry.options)
        self._med_dog: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "medications", 
                "reminders", 
                "safe_zones", 
                "advanced", 
                "schedule", 
                "modules", 
                "dogs",
                "medication_mapping",
                "sources",
                "notifications",
                "system",
            ],
        )

    async def async_step_dogs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage dogs configuration."""
        if user_input is not None:
            # Update dogs configuration
            self._options[CONF_DOGS] = user_input.get(
                CONF_DOGS, self._options.get(CONF_DOGS, [])
            )
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

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
                    ): EntitySelector(
                        EntitySelectorConfig(domain="person", multiple=True)
                    ),
                    vol.Optional(
                        CONF_DEVICE_TRACKERS,
                        default=sources.get(CONF_DEVICE_TRACKERS, []),
                    ): EntitySelector(
                        EntitySelectorConfig(domain="device_tracker", multiple=True)
                    ),
                    vol.Optional(
                        CONF_CALENDAR, default=sources.get(CONF_CALENDAR)
                    ): EntitySelector(EntitySelectorConfig(domain="calendar")),
                    vol.Optional(
                        CONF_WEATHER, default=sources.get(CONF_WEATHER)
                    ): EntitySelector(EntitySelectorConfig(domain="weather")),
                }
            ),
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage notification settings."""
        if user_input is not None:
            quiet_hours = self._options.get(CONF_NOTIFICATIONS, {}).get(
                CONF_QUIET_HOURS, {}
            )

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
                CONF_REMINDER_REPEAT: user_input.get(
                    CONF_REMINDER_REPEAT, DEFAULT_REMINDER_REPEAT
                ),
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
                    ): TextSelector(),
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
                        default=notifications.get(
                            CONF_REMINDER_REPEAT, DEFAULT_REMINDER_REPEAT
                        ),
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

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage system settings."""
        if user_input is not None:
            self._options[CONF_RESET_TIME] = user_input.get(
                CONF_RESET_TIME, DEFAULT_RESET_TIME
            )
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
                        default=self._options.get(
                            CONF_EXPORT_FORMAT, DEFAULT_EXPORT_FORMAT
                        ),
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

    # Medication mapping methods
    async def async_step_medication_mapping(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure medication mapping for all dogs."""
        dogs = self._options.get(CONF_DOGS, [])
        current = self._options.get("medication_mapping", {})
        
        if user_input is not None:
            new_map = {}
            for d in dogs:
                dog_id = d.get("dog_id") or d.get("name")
                if not dog_id:
                    continue
                new_map[dog_id] = {}
                for idx in (1, 2, 3):
                    key = f"medmap_{dog_id}_slot{idx}"
                    vals = user_input.get(key) or []
                    if isinstance(vals, str):
                        vals = [v.strip() for v in vals.split(",") if v.strip()]
                    new_map[dog_id][f"slot{idx}"] = vals
            self._options["medication_mapping"] = new_map
            return self.async_create_entry(title="", data=self._options)

        schema_dict = {}
        meals = ["breakfast", "lunch", "dinner"]
        
        for d in dogs:
            dog_id = d.get("dog_id") or d.get("name")
            if not dog_id:
                continue
            dog_map = current.get(dog_id, {})
            for idx in (1, 2, 3):
                key = f"medmap_{dog_id}_slot{idx}"
                default = dog_map.get(f"slot{idx}", [])
                schema_dict[vol.Optional(key, default=default)] = SelectSelector(
                    SelectSelectorConfig(options=meals, multiple=True)
                )

        schema = vol.Schema(schema_dict)
        return self.async_show_form(step_id="medication_mapping", data_schema=schema)

    # Module management
    async def async_step_modules(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure enabled modules."""
        modules = self._options.get("modules", {})
        defaults = {
            "gps": modules.get("gps", True),
            "feeding": modules.get("feeding", True),
            "health": modules.get("health", True),
            "walk": modules.get("walk", True),
            "grooming": modules.get("grooming", False),
            "training": modules.get("training", False),
            "notifications": modules.get("notifications", True),
        }
        
        if user_input is not None:
            new_modules = {
                "gps": bool(user_input.get("gps")),
                "feeding": bool(user_input.get("feeding")),
                "health": bool(user_input.get("health")),
                "walk": bool(user_input.get("walk")),
                "grooming": bool(user_input.get("grooming")),
                "training": bool(user_input.get("training")),
                "notifications": bool(user_input.get("notifications")),
            }
            self._options["modules"] = new_modules
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema({
            vol.Optional("gps", default=defaults["gps"]): BooleanSelector(),
            vol.Optional("feeding", default=defaults["feeding"]): BooleanSelector(),
            vol.Optional("health", default=defaults["health"]): BooleanSelector(),
            vol.Optional("walk", default=defaults["walk"]): BooleanSelector(),
            vol.Optional("grooming", default=defaults["grooming"]): BooleanSelector(),
            vol.Optional("training", default=defaults["training"]): BooleanSelector(),
            vol.Optional("notifications", default=defaults["notifications"]): BooleanSelector(),
        })
        return self.async_show_form(step_id="modules", data_schema=schema)

    # Schedule management
    async def async_step_schedule(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure scheduling settings."""
        default_reset = self._options.get("reset_time", "23:59:00")
        quiet_hours = self._options.get("quiet_hours", {})
        default_qs = quiet_hours.get("start", "22:00:00")
        default_qe = quiet_hours.get("end", "07:00:00")
        default_repeat = int(self._options.get("reminder_repeat", 30))
        default_snooze = int(self._options.get("snooze_min", 15))

        if user_input is not None:
            self._options["reset_time"] = user_input.get("reset_time", default_reset)
            self._options["quiet_hours"] = {
                "start": user_input.get("quiet_start", default_qs),
                "end": user_input.get("quiet_end", default_qe)
            }
            self._options["reminder_repeat"] = int(user_input.get("reminder_repeat", default_repeat))
            self._options["snooze_min"] = int(user_input.get("snooze_min", default_snooze))
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema({
            vol.Optional("reset_time", default=default_reset): TimeSelector(),
            vol.Optional("quiet_start", default=default_qs): TimeSelector(),
            vol.Optional("quiet_end", default=default_qe): TimeSelector(),
            vol.Optional("reminder_repeat", default=default_repeat): NumberSelector(
                NumberSelectorConfig(min=5, max=180, step=5, mode="box")
            ),
            vol.Optional("snooze_min", default=default_snooze): NumberSelector(
                NumberSelectorConfig(min=5, max=120, step=5, mode="box")
            ),
        })
        return self.async_show_form(step_id="schedule", data_schema=schema)

    # Advanced settings
    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure advanced settings."""
        advanced = self._options.get("advanced", {})
        defaults = {
            "route_history_limit": int(advanced.get("route_history_limit", 500)),
            "enable_pawtracker_alias": bool(advanced.get("enable_pawtracker_alias", True)),
            "diagnostic_sensors": bool(advanced.get("diagnostic_sensors", False)),
        }
        
        if user_input is not None:
            self._options["advanced"] = {
                "route_history_limit": int(user_input.get("route_history_limit", defaults["route_history_limit"])),
                "enable_pawtracker_alias": bool(user_input.get("enable_pawtracker_alias", defaults["enable_pawtracker_alias"])),
                "diagnostic_sensors": bool(user_input.get("diagnostic_sensors", defaults["diagnostic_sensors"])),
            }
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema({
            vol.Optional("route_history_limit", default=defaults["route_history_limit"]): NumberSelector(
                NumberSelectorConfig(min=50, max=2000, step=50, mode="box")
            ),
            vol.Optional("enable_pawtracker_alias", default=defaults["enable_pawtracker_alias"]): BooleanSelector(),
            vol.Optional("diagnostic_sensors", default=defaults["diagnostic_sensors"]): BooleanSelector(),
        })
        return self.async_show_form(step_id="advanced", data_schema=schema)

    # Safe zones management
    async def async_step_safe_zones(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure safe zones for dogs."""
        dogs = self._options.get(CONF_DOGS, [])
        safe_zones = self._options.get("safe_zones", {})
        
        if not dogs:
            return self.async_show_form(
                step_id="safe_zones", 
                data_schema=vol.Schema({}),
                description_placeholders={"info": "No dogs configured."}
            )

        if user_input is not None:
            new_zones = {}
            for d in dogs:
                dog_id = d.get("dog_id") or d.get("name")
                if not dog_id:
                    continue
                new_zones[dog_id] = {
                    "latitude": float(user_input.get(f"{dog_id}__lat", 0.0)),
                    "longitude": float(user_input.get(f"{dog_id}__lon", 0.0)),
                    "radius": float(user_input.get(f"{dog_id}__radius", 50)),
                    "enable_alerts": bool(user_input.get(f"{dog_id}__enable", True)),
                }
            self._options["safe_zones"] = new_zones
            return self.async_create_entry(title="", data=self._options)

        schema_dict = {}
        for d in dogs:
            dog_id = d.get("dog_id") or d.get("name")
            if not dog_id:
                continue
            current = safe_zones.get(dog_id, {})
            
            schema_dict[vol.Optional(f"{dog_id}__lat", default=current.get("latitude", 0.0))] = NumberSelector(
                NumberSelectorConfig(min=-90, max=90, step=0.000001, mode="box")
            )
            schema_dict[vol.Optional(f"{dog_id}__lon", default=current.get("longitude", 0.0))] = NumberSelector(
                NumberSelectorConfig(min=-180, max=180, step=0.000001, mode="box")
            )
            schema_dict[vol.Optional(f"{dog_id}__radius", default=current.get("radius", 50))] = NumberSelector(
                NumberSelectorConfig(min=5, max=2000, step=1, mode="box")
            )
            schema_dict[vol.Optional(f"{dog_id}__enable", default=current.get("enable_alerts", True))] = BooleanSelector()

        return self.async_show_form(step_id="safe_zones", data_schema=vol.Schema(schema_dict))

    # Reminders management
    async def async_step_reminders(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure reminder settings."""
        reminders = self._options.get("reminders", {})
        target = reminders.get("notify_target", "notify.notify")
        interval_min = int(reminders.get("interval_minutes", 0) or 0)
        snooze_min = int(reminders.get("snooze_minutes", 0) or 0)
        enable_auto = bool(reminders.get("enable_auto", False))

        if user_input is not None:
            self._options["reminders"] = {
                "notify_target": user_input.get("notify_target") or "notify.notify",
                "interval_minutes": int(user_input.get("interval_minutes") or 0),
                "snooze_minutes": int(user_input.get("snooze_minutes") or 0),
                "enable_auto": bool(user_input.get("enable_auto") or False),
            }
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema({
            vol.Optional("notify_target", default=target): TextSelector(),
            vol.Optional("interval_minutes", default=interval_min): NumberSelector(
                NumberSelectorConfig(min=0, max=1440, step=5, mode="box")
            ),
            vol.Optional("snooze_minutes", default=snooze_min): NumberSelector(
                NumberSelectorConfig(min=0, max=360, step=5, mode="box")
            ),
            vol.Optional("enable_auto", default=enable_auto): BooleanSelector(),
        })
        return self.async_show_form(step_id="reminders", data_schema=schema)

    # Medications management
    async def async_step_medications(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure medications per dog."""
        dogs = self._options.get("dogs", [])
        choices = []
        for d in dogs:
            dog_id = d.get("dog_id") or d.get("name")
            name = d.get("name") or dog_id
            if dog_id:
                choices.append({"value": dog_id, "label": name})
        
        if not choices:
            return self.async_abort(reason="no_dogs")
            
        if user_input is not None:
            self._med_dog = user_input.get("dog_id")
            return await self.async_step_medications_configure()
            
        schema = vol.Schema({
            vol.Required("dog_id"): SelectSelector(SelectSelectorConfig(options=choices))
        })
        return self.async_show_form(step_id="medications", data_schema=schema)

    async def async_step_medications_configure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure medication slots for specific dog."""
        dog = self._med_dog
        if not dog:
            return await self.async_step_medications()
            
        mapping = self._options.get("medication_mapping", {})
        dog_mapping = mapping.get(dog, {})
        
        def _get_default(slot): 
            return list(dog_mapping.get(slot, []))
            
        if user_input is not None:
            if "medication_mapping" not in self._options:
                self._options["medication_mapping"] = {}
            self._options["medication_mapping"][dog] = {
                "slot1": list(user_input.get("slot1") or []),
                "slot2": list(user_input.get("slot2") or []),
                "slot3": list(user_input.get("slot3") or []),
            }
            return self.async_create_entry(title="", data=self._options)
            
        meal_options = ["breakfast", "lunch", "dinner"]
        schema = vol.Schema({
            vol.Optional("slot1", default=_get_default("slot1")): SelectSelector(
                SelectSelectorConfig(options=meal_options, multiple=True)
            ),
            vol.Optional("slot2", default=_get_default("slot2")): SelectSelector(
                SelectSelectorConfig(options=meal_options, multiple=True)
            ),
            vol.Optional("slot3", default=_get_default("slot3")): SelectSelector(
                SelectSelectorConfig(options=meal_options, multiple=True)
            ),
        })
        return self.async_show_form(step_id="medications_configure", data_schema=schema)
