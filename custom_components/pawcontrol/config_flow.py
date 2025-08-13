"""Config flow for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlowWithReload
from homeassistant.core import callback
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

from .const import (  # noqa: E402
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
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

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
                            translation_key="dog_size",
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


class PawControlOptionsFlow(
    PawControlOptionsFlowMedicationMixin,  # noqa: F821
    PawControlOptionsFlowRemindersMixin,  # noqa: F821
    PawControlOptionsFlowSafeZonesMixin,  # noqa: F821
    PawControlOptionsFlowAdvancedMixin,  # noqa: F821
    PawControlOptionsFlowScheduleMixin,  # noqa: F821
    PawControlOptionsFlowModulesMixin,  # noqa: F821
    PawControlOptionsFlowMedMixin,  # noqa: F821
    config_entries.OptionsFlow,
):
    """Handle options flow for Paw Control."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._options = dict(config_entry.options)

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


def _dog_key(d):
    return d.get("dog_id") or d.get("name")


def _build_med_mapping_schema(dogs, current):
    import voluptuous as vol
    from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

    meals = ["breakfast", "lunch", "dinner"]
    schema_dict = {}
    for d in dogs:
        did = _dog_key(d)
        dm = (current or {}).get(did, {})
        for idx in (1, 2, 3):
            key = f"medmap_{did}_slot{idx}"
            default = dm.get(f"slot{idx}", [])
            schema_dict[vol.Optional(key, default=default)] = SelectSelector(
                SelectSelectorConfig(options=meals, multiple=True)
            )
    return vol.Schema(schema_dict)


class PawControlOptionsFlowMedMixin:
    async def async_step_medication_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        dogs = self._options.get(CONF_DOGS, [])
        current = self._options.get("medication_mapping", {})
        if user_input is not None:
            new_map = {}
            for d in dogs:
                did = _dog_key(d)
                new_map[did] = {}
                for idx in (1, 2, 3):
                    key = f"medmap_{did}_slot{idx}"
                    vals = user_input.get(key) or []
                    if isinstance(vals, str):
                        vals = [v.strip() for v in vals.split(",") if v.strip()]
                    new_map[did][f"slot{idx}"] = vals
            self._options["medication_mapping"] = new_map
            return self.async_create_entry(title="", data=self._options)

        schema = _build_med_mapping_schema(dogs, current)
        return self.async_show_form(step_id="medication_mapping", data_schema=schema)


class PawControlOptionsFlowModulesMixin:
    async def async_step_modules(self, user_input=None):
        import voluptuous as vol

        opts = (
            self._options if hasattr(self, "_options") else (self.entry.options or {})
        )
        modules = (
            opts.get("modules", {}) if isinstance(opts.get("modules"), dict) else {}
        )
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
            modules = {
                "gps": bool(user_input.get("gps")),
                "feeding": bool(user_input.get("feeding")),
                "health": bool(user_input.get("health")),
                "walk": bool(user_input.get("walk")),
                "grooming": bool(user_input.get("grooming")),
                "training": bool(user_input.get("training")),
                "notifications": bool(user_input.get("notifications")),
            }
            new_opts = dict(opts)
            new_opts["modules"] = modules
            return self.async_create_entry(title="", data=new_opts)

        schema = vol.Schema(
            {
                vol.Optional("gps", default=defaults["gps"]): bool,
                vol.Optional("feeding", default=defaults["feeding"]): bool,
                vol.Optional("health", default=defaults["health"]): bool,
                vol.Optional("walk", default=defaults["walk"]): bool,
                vol.Optional("grooming", default=defaults["grooming"]): bool,
                vol.Optional("training", default=defaults["training"]): bool,
                vol.Optional("notifications", default=defaults["notifications"]): bool,
            }
        )
        return self.async_show_form(step_id="modules", data_schema=schema)


class PawControlOptionsFlowScheduleMixin:
    async def async_step_schedule(self, user_input=None):
        import voluptuous as vol
        from homeassistant.helpers.selector import (
            NumberSelector,
            NumberSelectorConfig,
            TimeSelector,
            TimeSelectorConfig,
        )

        opts = (
            self._options if hasattr(self, "_options") else (self.entry.options or {})
        )
        default_reset = opts.get("reset_time", "23:59:00")
        qh = opts.get("quiet_hours", {})
        default_qs = qh.get("start", "22:00:00")
        default_qe = qh.get("end", "07:00:00")
        default_repeat = int(opts.get("reminder_repeat", 30))
        default_snooze = int(opts.get("snooze_min", 15))

        if user_input is not None:
            new = dict(opts)
            new["reset_time"] = user_input.get("reset_time", default_reset)
            new["quiet_hours"] = {
                "start": user_input.get("quiet_start", default_qs),
                "end": user_input.get("quiet_end", default_qe),
            }
            new["reminder_repeat"] = int(
                user_input.get("reminder_repeat", default_repeat)
            )
            new["snooze_min"] = int(user_input.get("snooze_min", default_snooze))
            return self.async_create_entry(title="", data=new)

        schema = vol.Schema(
            {
                vol.Optional("reset_time", default=default_reset): TimeSelector(
                    TimeSelectorConfig()
                ),
                vol.Optional("quiet_start", default=default_qs): TimeSelector(
                    TimeSelectorConfig()
                ),
                vol.Optional("quiet_end", default=default_qe): TimeSelector(
                    TimeSelectorConfig()
                ),
                vol.Optional("reminder_repeat", default=default_repeat): NumberSelector(
                    NumberSelectorConfig(min=5, max=180, step=5, mode="box")
                ),
                vol.Optional("snooze_min", default=default_snooze): NumberSelector(
                    NumberSelectorConfig(min=5, max=120, step=5, mode="box")
                ),
            }
        )
        return self.async_show_form(step_id="schedule", data_schema=schema)


class PawControlOptionsFlowAdvancedMixin:
    async def async_step_advanced(self, user_input=None):
        import voluptuous as vol

        opts = (
            self._options if hasattr(self, "_options") else (self.entry.options or {})
        )
        defaults = {
            "route_history_limit": int(
                (opts.get("advanced") or {}).get("route_history_limit", 500)
            ),
            "enable_pawtracker_alias": bool(
                (opts.get("advanced") or {}).get("enable_pawtracker_alias", True)
            ),
            "diagnostic_sensors": bool(
                (opts.get("advanced") or {}).get("diagnostic_sensors", False)
            ),
        }
        if user_input is not None:
            new = dict(opts)
            new["advanced"] = {
                "route_history_limit": int(
                    user_input.get(
                        "route_history_limit", defaults["route_history_limit"]
                    )
                ),
                "enable_pawtracker_alias": bool(
                    user_input.get(
                        "enable_pawtracker_alias", defaults["enable_pawtracker_alias"]
                    )
                ),
                "diagnostic_sensors": bool(
                    user_input.get("diagnostic_sensors", defaults["diagnostic_sensors"])
                ),
            }
            return self.async_create_entry(title="", data=new)

        schema = vol.Schema(
            {
                vol.Optional(
                    "route_history_limit", default=defaults["route_history_limit"]
                ): int,
                vol.Optional(
                    "enable_pawtracker_alias",
                    default=defaults["enable_pawtracker_alias"],
                ): bool,
                vol.Optional(
                    "diagnostic_sensors", default=defaults["diagnostic_sensors"]
                ): bool,
            }
        )
        return self.async_show_form(step_id="advanced", data_schema=schema)


class PawControlOptionsFlowSafeZonesMixin:
    async def async_step_safe_zones(self, user_input=None):
        import voluptuous as vol
        from homeassistant.helpers.selector import (
            BooleanSelector,
            NumberSelector,
            NumberSelectorConfig,
        )

        opts = (
            self._options if hasattr(self, "_options") else (self.entry.options or {})
        )
        dogs = opts.get(CONF_DOGS, [])
        sz = dict(opts.get("safe_zones") or {})
        if not dogs:
            return self.async_show_form(
                step_id="safe_zones", data_schema=vol.Schema({})
            )

        schema = {}
        defaults = {}
        for d in dogs:
            dog_id = d.get("dog_id") or d.get("name")
            if not dog_id:
                continue
            cur = sz.get(dog_id, {})
            defaults[dog_id] = {
                "lat": cur.get("latitude", 0.0),
                "lon": cur.get("longitude", 0.0),
                "radius": cur.get("radius", 50),
                "enable": bool(cur.get("enable_alerts", True)),
            }
            schema[vol.Optional(f"{dog_id}__lat", default=defaults[dog_id]["lat"])] = (
                NumberSelector(
                    NumberSelectorConfig(min=-90, max=90, step=0.000001, mode="box")
                )
            )
            schema[vol.Optional(f"{dog_id}__lon", default=defaults[dog_id]["lon"])] = (
                NumberSelector(
                    NumberSelectorConfig(min=-180, max=180, step=0.000001, mode="box")
                )
            )
            schema[
                vol.Optional(f"{dog_id}__radius", default=defaults[dog_id]["radius"])
            ] = NumberSelector(
                NumberSelectorConfig(min=5, max=2000, step=1, mode="box")
            )
            schema[
                vol.Optional(f"{dog_id}__enable", default=defaults[dog_id]["enable"])
            ] = BooleanSelector()

        if user_input is not None:
            new = dict(opts)
            out = {}
            for d in dogs:
                dog_id = d.get("dog_id") or d.get("name")
                if not dog_id:
                    continue
                out[dog_id] = {
                    "latitude": float(user_input.get(f"{dog_id}__lat", 0.0)),
                    "longitude": float(user_input.get(f"{dog_id}__lon", 0.0)),
                    "radius": float(user_input.get(f"{dog_id}__radius", 50)),
                    "enable_alerts": bool(user_input.get(f"{dog_id}__enable", True)),
                }
            new["safe_zones"] = out
            return self.async_create_entry(title="", data=new)

        return self.async_show_form(
            step_id="safe_zones", data_schema=vol.Schema(schema)
        )


class PawControlOptionsFlowRemindersMixin:
    async def async_step_reminders(self, user_input=None):
        import voluptuous as vol
        from homeassistant.helpers.selector import (
            BooleanSelector,
            NumberSelector,
            NumberSelectorConfig,
            TextSelector,
            TextSelectorConfig,
        )

        opts = (
            self._options if hasattr(self, "_options") else (self.entry.options or {})
        )
        reminders = dict((opts.get("reminders") or {}))
        target = reminders.get("notify_target", "notify.notify")
        interval_min = int(reminders.get("interval_minutes", 0) or 0)
        snooze_min = int(reminders.get("snooze_minutes", 0) or 0)
        enable_auto = bool(reminders.get("enable_auto", False))

        if user_input is not None:
            new = dict(opts)
            new["reminders"] = {
                "notify_target": user_input.get("notify_target") or "notify.notify",
                "interval_minutes": int(user_input.get("interval_minutes") or 0),
                "snooze_minutes": int(user_input.get("snooze_minutes") or 0),
                "enable_auto": bool(user_input.get("enable_auto") or False),
            }
            return self.async_create_entry(title="", data=new)

        schema = vol.Schema(
            {
                vol.Optional("notify_target", default=target): TextSelector(
                    TextSelectorConfig(type="text")
                ),
                vol.Optional("interval_minutes", default=interval_min): NumberSelector(
                    NumberSelectorConfig(min=0, max=1440, step=5, mode="box")
                ),
                vol.Optional("snooze_minutes", default=snooze_min): NumberSelector(
                    NumberSelectorConfig(min=0, max=360, step=5, mode="box")
                ),
                vol.Optional("enable_auto", default=enable_auto): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="reminders", data_schema=schema)


class PawControlOptionsFlowMedicationMixin:
    MEALS = ["breakfast", "lunch", "dinner"]

    async def async_step_medications(self, user_input=None):
        import voluptuous as vol
        from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

        opts = (
            self._options if hasattr(self, "_options") else (self.entry.options or {})
        )
        dogs = opts.get("dogs") or []
        choices = []
        for d in dogs:
            did = d.get("dog_id") or d.get("name")
            name = d.get("name") or did
            if did:
                choices.append({"value": did, "label": name})
        if not choices:
            return self.async_abort(reason="no_dogs")
        if user_input is not None:
            self._med_dog = user_input.get("dog_id")
            return await self.async_step_medications_configure()
        schema = vol.Schema(
            {
                vol.Required("dog_id"): SelectSelector(
                    SelectSelectorConfig(options=choices)
                )
            }
        )
        return self.async_show_form(step_id="medications", data_schema=schema)

    async def async_step_medications_configure(self, user_input=None):
        import voluptuous as vol
        from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

        opts = (
            self._options if hasattr(self, "_options") else (self.entry.options or {})
        )
        dog = getattr(self, "_med_dog", None)
        if not dog:
            return await self.async_step_medications()
        mapping = dict((opts.get("medication_mapping") or {}))
        dm = dict(mapping.get(dog) or {})

        def _def(slot):
            return list(dm.get(slot) or [])

        if user_input is not None:
            new = dict(opts)
            m = dict(new.get("medication_mapping") or {})
            m[dog] = {
                "slot1": list(user_input.get("slot1") or []),
                "slot2": list(user_input.get("slot2") or []),
                "slot3": list(user_input.get("slot3") or []),
            }
            new["medication_mapping"] = m
            return self.async_create_entry(title="", data=new)
        meal_opts = self.MEALS
        schema = vol.Schema(
            {
                vol.Optional("slot1", default=_def("slot1")): SelectSelector(
                    SelectSelectorConfig(options=meal_opts, multiple=True)
                ),
                vol.Optional("slot2", default=_def("slot2")): SelectSelector(
                    SelectSelectorConfig(options=meal_opts, multiple=True)
                ),
                vol.Optional("slot3", default=_def("slot3")): SelectSelector(
                    SelectSelectorConfig(options=meal_opts, multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="medications_configure", data_schema=schema)


async def async_step_reconfigure(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Handle reconfiguration of the integration (Gold rule)."""
    errors: dict[str, str] = {}
    # Defaults from existing entry if available
    entry = (
        self._get_reconfigure_entry()
        if hasattr(self, "_get_reconfigure_entry")
        else None
    )
    opts = entry.options if entry else {}
    schema = vol.Schema(
        {
            vol.Optional(
                "history_days", default=opts.get("history_days", 30)
            ): vol.Coerce(int),
            vol.Optional(
                "geofence_radius_m", default=opts.get("geofence_radius_m", 75)
            ): vol.Coerce(int),
            vol.Optional("notify_target", default=opts.get("notify_target", "")): str,
        }
    )
    if user_input is None:
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )
    # Save as options
    if entry:
        new_opts = dict(opts)
        new_opts.update(user_input)
        self.hass.config_entries.async_update_entry(entry, options=new_opts)
    return self.async_create_entry(title="Reconfigure", data={})


async def async_step_reauth(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Handle reauthentication flow (update credentials and reload)."""
    errors: dict[str, str] = {}
    schema = vol.Schema({vol.Required("api_key"): str})
    if user_input is None:
        return self.async_show_form(step_id="reauth", data_schema=schema, errors=errors)
    api_key = user_input["api_key"]
    if not api_key or len(api_key) < 6:
        errors["base"] = "invalid_auth"
        return self.async_show_form(step_id="reauth", data_schema=schema, errors=errors)
    entry = None
    if hasattr(self, "context") and self.context.get("entry_id"):
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
    if entry:
        new_data = dict(entry.data)
        new_data["api_key"] = api_key
        return self.async_update_reload_and_abort(
            entry, data=new_data, reason="reauth_successful"
        )
    return self.async_abort(reason="reauth_successful")


class OptionsFlowHandler(OptionsFlowWithReload):
    """Options flow with automatic reload after save."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        return await self.async_step_geofence()

    async def async_step_geofence(self, user_input: dict | None = None):
        import voluptuous as vol

        errors: dict[str, str] = {}
        opts = (
            dict(self._options or {})
            if hasattr(self, "_options")
            else dict(self.config_entry.options or {})
        )
        geo = dict(opts.get("geofence") or {})

        default_lat = geo.get("lat", None)
        default_lon = geo.get("lon", None)
        default_radius = geo.get("radius_m", 150)
        default_alerts = bool(geo.get("enable_alerts", True))

        schema = vol.Schema(
            {
                vol.Optional("lat", default=default_lat): vol.Any(float, int, None),
                vol.Optional("lon", default=default_lon): vol.Any(float, int, None),
                vol.Optional("radius_m", default=default_radius): vol.All(
                    int, vol.Range(min=10, max=5000)
                ),
                vol.Optional("enable_alerts", default=default_alerts): bool,
                vol.Optional("home_from_entity"): EntitySelector(
                    EntitySelectorConfig(domain=["device_tracker", "person"])
                ),
                vol.Optional("use_current_state", default=False): BooleanSelector(),
            }
        )

        if user_input is not None:
            lat = user_input.get("lat")
            lon = user_input.get("lon")
            radius = user_input.get("radius_m")
            use_state = bool(user_input.get("use_current_state"))
            entity_id = user_input.get("home_from_entity")

            # If user provided entity & wants current state -> resolve coordinates
            if entity_id and use_state:
                st = self.hass.states.get(entity_id)
                la = st and st.attributes.get("latitude")
                lo = st and st.attributes.get("longitude")
                if isinstance(la, (float, int)) and isinstance(lo, (float, int)):
                    lat, lon = float(la), float(lo)
                else:
                    errors["base"] = "invalid_geofence"

            # basic validation
            if (lat is None) ^ (lon is None):
                errors["base"] = "invalid_geofence"
            if radius is not None and radius <= 0:
                errors["base"] = "invalid_geofence"

            if not errors:
                new_opts = dict(opts)
                new_opts["geofence"] = {
                    "lat": None if lat is None else float(lat),
                    "lon": None if lon is None else float(lon),
                    "radius_m": int(radius) if radius is not None else 150,
                    "enable_alerts": bool(user_input.get("enable_alerts", True)),
                }
                return self.async_create_entry(title="", data=new_opts)

        return self.async_show_form(
            step_id="geofence", data_schema=schema, errors=errors
        )
