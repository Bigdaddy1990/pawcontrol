"""Enhanced Options Flow for Paw Control integration.

This extends the existing options flow with comprehensive configuration options
including dog-specific settings, GPS configuration, data sources management,
maintenance options, and advanced notification settings.

Follows Home Assistant Platinum quality standards with complete type annotations,
proper error handling, and extensive validation.
"""

from __future__ import annotations

from typing import Any
import logging
import inspect

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import (
    DOMAIN,
    # Module constants
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    MODULE_GROOMING,
    MODULE_TRAINING,
    MODULE_NOTIFICATIONS,
    MODULE_DASHBOARD,
    MODULE_MEDICATION,
    # Dog size constants
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_XLARGE,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_WEIGHT,
    CONF_DOG_SIZE,
    CONF_DOG_BREED,
    CONF_DOG_AGE,
    CONF_DOG_MODULES,
    CONF_DEVICE_TRACKERS,
    CONF_PERSON_ENTITIES,
    CONF_DOOR_SENSOR,
    CONF_WEATHER,
    CONF_CALENDAR,
    CONF_RESET_TIME,
    CONF_EXPORT_FORMAT,
    CONF_EXPORT_PATH,
    CONF_VISITOR_MODE,
    # Defaults
    DEFAULT_RESET_TIME,
    DEFAULT_EXPORT_FORMAT,
    DEFAULT_REMINDER_REPEAT,
    DEFAULT_SNOOZE_MIN,
    # GPS Constants
    GPS_MIN_ACCURACY,
    GPS_POINT_FILTER_DISTANCE,
    DEFAULT_SAFE_ZONE_RADIUS,
    MAX_SAFE_ZONE_RADIUS,
    MIN_SAFE_ZONE_RADIUS,
    # Limits
    MIN_DOG_AGE_YEARS,
    MAX_DOG_AGE_YEARS,
    MIN_DOG_WEIGHT_KG,
    MAX_DOG_WEIGHT_KG,
    DEFAULT_DOG_WEIGHT_KG,
)

_LOGGER = logging.getLogger(__name__)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Enhanced options flow with comprehensive configuration options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry
        self._dogs_data: dict[str, Any] = {}
        self._current_dog_index = 0
        self._total_dogs = 0
        self._editing_dog_id: str | None = None
        self._temp_options: dict[str, Any] = {}

    @property
    def _options(self) -> dict[str, Any]:
        """Return current options with defaults."""
        return self._entry.options

    @property
    def _data(self) -> dict[str, Any]:
        """Return current config data."""
        return self._entry.data

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options with a comprehensive menu."""
        if user_input is not None:
            # Handle direct option updates for backward compatibility
            if "geofencing_enabled" in user_input or "modules" in user_input:
                return self.async_create_entry(title="", data=user_input)

        # Show comprehensive configuration menu
        menu_options = {
            "dogs": "Dog Management",
            "gps": "GPS & Tracking",
            "geofence": "Geofence Settings",
            "notifications": "Notifications",
            "data_sources": "Data Sources",
            "modules": "Feature Modules",
            "system": "System Settings",
            "maintenance": "Maintenance & Backup",
        }

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
        )

    # === DOG MANAGEMENT ===

    async def async_step_dogs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage individual dogs and their settings."""
        if user_input is not None:
            if user_input.get("action") == "add_dog":
                return await self.async_step_add_dog()
            elif user_input.get("action") == "edit_dog":
                return await self.async_step_select_dog_edit()
            elif user_input.get("action") == "remove_dog":
                return await self.async_step_select_dog_remove()
            else:
                return await self.async_step_init()

        # Get current dogs from data
        current_dogs = self._data.get(CONF_DOGS, [])
        dogs_info = f"Currently configured dogs: {len(current_dogs)}\n"

        for i, dog in enumerate(current_dogs, 1):
            dogs_info += (
                f"{i}. {dog.get(CONF_DOG_NAME, 'Unnamed')} "
                f"({dog.get(CONF_DOG_ID, 'unknown')})\n"
            )

        schema = vol.Schema(
            {
                vol.Required("action"): vol.In(
                    {
                        "add_dog": "Add New Dog",
                        "edit_dog": "Edit Existing Dog",
                        "remove_dog": "Remove Dog",
                        "back": "Back to Main Menu",
                    }
                )
            }
        )

        return self.async_show_form(
            step_id="dogs",
            data_schema=schema,
            description_placeholders={"dogs_info": dogs_info},
        )

    async def async_step_add_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new dog to the configuration."""
        errors = {}

        if user_input is not None:
            # Validate dog data
            dog_id = user_input.get(CONF_DOG_ID, "").strip().lower()
            dog_name = user_input.get(CONF_DOG_NAME, "").strip()

            # Check for duplicate dog ID
            current_dogs = self._data.get(CONF_DOGS, [])
            if any(dog.get(CONF_DOG_ID) == dog_id for dog in current_dogs):
                errors[CONF_DOG_ID] = "duplicate_dog_id"
            elif not dog_id:
                errors[CONF_DOG_ID] = "invalid_dog_id"
            elif not dog_name:
                errors[CONF_DOG_NAME] = "invalid_dog_name"

            if not errors:
                # Create new dog configuration
                new_dog = {
                    CONF_DOG_ID: dog_id,
                    CONF_DOG_NAME: dog_name,
                    CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, ""),
                    CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 1),
                    CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
                    CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, SIZE_MEDIUM),
                    CONF_DOG_MODULES: {
                        MODULE_WALK: user_input.get(f"module_{MODULE_WALK}", True),
                        MODULE_FEEDING: user_input.get(
                            f"module_{MODULE_FEEDING}", True
                        ),
                        MODULE_HEALTH: user_input.get(f"module_{MODULE_HEALTH}", True),
                        MODULE_GPS: user_input.get(f"module_{MODULE_GPS}", True),
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
                            f"module_{MODULE_MEDICATION}", True
                        ),
                        MODULE_TRAINING: user_input.get(
                            f"module_{MODULE_TRAINING}", True
                        ),
                    },
                }

                # Update entry data
                new_data = dict(self._data)
                new_data.setdefault(CONF_DOGS, []).append(new_dog)

                self.hass.config_entries.async_update_entry(self._entry, data=new_data)

                return self.async_create_entry(title="", data=self._options)

        # Build form schema
        schema = vol.Schema(
            {
                vol.Required(CONF_DOG_ID): str,
                vol.Required(CONF_DOG_NAME): str,
                vol.Optional(CONF_DOG_BREED, default=""): str,
                vol.Optional(CONF_DOG_AGE, default=1): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_DOG_AGE_YEARS, max=MAX_DOG_AGE_YEARS),
                ),
                vol.Optional(CONF_DOG_WEIGHT, default=20.0): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=MIN_DOG_WEIGHT_KG, max=MAX_DOG_WEIGHT_KG),
                ),
                vol.Optional(CONF_DOG_SIZE, default=SIZE_MEDIUM): vol.In(
                    [SIZE_SMALL, SIZE_MEDIUM, SIZE_LARGE, SIZE_XLARGE]
                ),
                # Module toggles
                vol.Optional(f"module_{MODULE_WALK}", default=True): bool,
                vol.Optional(f"module_{MODULE_FEEDING}", default=True): bool,
                vol.Optional(f"module_{MODULE_HEALTH}", default=True): bool,
                vol.Optional(f"module_{MODULE_GPS}", default=True): bool,
                vol.Optional(f"module_{MODULE_NOTIFICATIONS}", default=True): bool,
                vol.Optional(f"module_{MODULE_DASHBOARD}", default=True): bool,
                vol.Optional(f"module_{MODULE_GROOMING}", default=True): bool,
                vol.Optional(f"module_{MODULE_MEDICATION}", default=True): bool,
                vol.Optional(f"module_{MODULE_TRAINING}", default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="add_dog",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_select_dog_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a dog to edit."""
        if user_input is not None:
            self._editing_dog_id = user_input["dog_to_edit"]
            return await self.async_step_edit_dog()

        current_dogs = self._data.get(CONF_DOGS, [])
        if not current_dogs:
            return await self.async_step_dogs()

        dog_options = {
            dog[CONF_DOG_ID]: f"{dog[CONF_DOG_NAME]} ({dog[CONF_DOG_ID]})"
            for dog in current_dogs
        }

        schema = vol.Schema({vol.Required("dog_to_edit"): vol.In(dog_options)})

        return self.async_show_form(
            step_id="select_dog_edit",
            data_schema=schema,
        )

    async def async_step_select_dog_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select and remove a dog from the configuration."""
        current_dogs = self._data.get(CONF_DOGS, [])

        if user_input is not None:
            dog_id = user_input.get("dog_to_remove")
            new_dogs = [d for d in current_dogs if d.get(CONF_DOG_ID) != dog_id]
            new_data = dict(self._data)
            new_data[CONF_DOGS] = new_dogs
            await self.hass.config_entries.async_update_entry(
                self._entry, data=new_data
            )
            return self.async_create_entry(title="", data=new_data)

        if not current_dogs:
            return await self.async_step_dogs()

        dog_options = {
            dog[CONF_DOG_ID]: f"{dog[CONF_DOG_NAME]} ({dog[CONF_DOG_ID]})"
            for dog in current_dogs
        }
        schema = vol.Schema({vol.Required("dog_to_remove"): vol.In(dog_options)})
        return self.async_show_form(
            step_id="select_dog_remove", data_schema=schema
        )

    async def async_step_edit_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit an existing dog's configuration."""
        current_dogs = self._data.get(CONF_DOGS, [])
        dog_to_edit = None

        for dog in current_dogs:
            if dog[CONF_DOG_ID] == self._editing_dog_id:
                dog_to_edit = dog
                break

        if not dog_to_edit:
            return await self.async_step_dogs()

        errors = {}

        if user_input is not None:
            # Validate and update dog data
            dog_name = user_input.get(CONF_DOG_NAME, "").strip()

            if not dog_name:
                errors[CONF_DOG_NAME] = "invalid_dog_name"

            if not errors:
                # Update dog configuration
                dog_to_edit.update(
                    {
                        CONF_DOG_NAME: dog_name,
                        CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, ""),
                        CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 1),
                        CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
                        CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, SIZE_MEDIUM),
                        CONF_DOG_MODULES: {
                            MODULE_WALK: user_input.get(f"module_{MODULE_WALK}", True),
                            MODULE_FEEDING: user_input.get(
                                f"module_{MODULE_FEEDING}", True
                            ),
                            MODULE_HEALTH: user_input.get(
                                f"module_{MODULE_HEALTH}", True
                            ),
                            MODULE_GPS: user_input.get(f"module_{MODULE_GPS}", True),
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
                                f"module_{MODULE_MEDICATION}", True
                            ),
                            MODULE_TRAINING: user_input.get(
                                f"module_{MODULE_TRAINING}", True
                            ),
                        },
                    }
                )

                # Update entry data
                new_data = dict(self._data)
                self.hass.config_entries.async_update_entry(self._entry, data=new_data)

                return self.async_create_entry(title="", data=self._options)

        # Get current dog modules
        current_modules = dog_to_edit.get(CONF_DOG_MODULES, {})

        # Build form schema with current values
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DOG_NAME, default=dog_to_edit.get(CONF_DOG_NAME, "")
                ): str,
                vol.Optional(
                    CONF_DOG_BREED, default=dog_to_edit.get(CONF_DOG_BREED, "")
                ): str,
                vol.Optional(
                    CONF_DOG_AGE, default=dog_to_edit.get(CONF_DOG_AGE, 1)
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_DOG_AGE_YEARS, max=MAX_DOG_AGE_YEARS),
                ),
                vol.Optional(
                    CONF_DOG_WEIGHT, default=dog_to_edit.get(CONF_DOG_WEIGHT, 20.0)
                ): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=MIN_DOG_WEIGHT_KG, max=MAX_DOG_WEIGHT_KG),
                ),
                vol.Optional(
                    CONF_DOG_SIZE, default=dog_to_edit.get(CONF_DOG_SIZE, SIZE_MEDIUM)
                ): vol.In([SIZE_SMALL, SIZE_MEDIUM, SIZE_LARGE, SIZE_XLARGE]),
                # Module toggles with current values
                vol.Optional(
                    f"module_{MODULE_WALK}",
                    default=current_modules.get(MODULE_WALK, True),
                ): bool,
                vol.Optional(
                    f"module_{MODULE_FEEDING}",
                    default=current_modules.get(MODULE_FEEDING, True),
                ): bool,
                vol.Optional(
                    f"module_{MODULE_HEALTH}",
                    default=current_modules.get(MODULE_HEALTH, True),
                ): bool,
                vol.Optional(
                    f"module_{MODULE_GPS}",
                    default=current_modules.get(MODULE_GPS, True),
                ): bool,
                vol.Optional(
                    f"module_{MODULE_NOTIFICATIONS}",
                    default=current_modules.get(MODULE_NOTIFICATIONS, True),
                ): bool,
                vol.Optional(
                    f"module_{MODULE_DASHBOARD}",
                    default=current_modules.get(MODULE_DASHBOARD, True),
                ): bool,
                vol.Optional(
                    f"module_{MODULE_GROOMING}",
                    default=current_modules.get(MODULE_GROOMING, True),
                ): bool,
                vol.Optional(
                    f"module_{MODULE_MEDICATION}",
                    default=current_modules.get(MODULE_MEDICATION, True),
                ): bool,
                vol.Optional(
                    f"module_{MODULE_TRAINING}",
                    default=current_modules.get(MODULE_TRAINING, True),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="edit_dog",
            data_schema=schema,
            errors=errors,
            description_placeholders={"dog_name": dog_to_edit.get(CONF_DOG_NAME, "")},
        )

    # === GPS & TRACKING ===

    async def async_step_gps(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure GPS and tracking settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options["gps"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_gps = self._options.get("gps", {})

        schema = vol.Schema(
            {
                vol.Optional(
                    "gps_enabled",
                    default=current_gps.get("enabled", True),
                ): bool,
                vol.Optional(
                    "gps_accuracy_filter",
                    default=current_gps.get("accuracy_filter", GPS_MIN_ACCURACY),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1000)),
                vol.Optional(
                    "gps_distance_filter",
                    default=current_gps.get(
                        "distance_filter", GPS_POINT_FILTER_DISTANCE
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Optional(
                    "gps_update_interval",
                    default=current_gps.get("update_interval", 30),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                vol.Optional(
                    "auto_start_walk",
                    default=current_gps.get("auto_start_walk", False),
                ): bool,
                vol.Optional(
                    "auto_end_walk",
                    default=current_gps.get("auto_end_walk", True),
                ): bool,
                vol.Optional(
                    "route_recording",
                    default=current_gps.get("route_recording", True),
                ): bool,
                vol.Optional(
                    "route_history_days",
                    default=current_gps.get("route_history_days", 90),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
            }
        )

        return self.async_show_form(step_id="gps", data_schema=schema)

    # === GEOFENCE SETTINGS ===

    async def async_step_geofence(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure geofence settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options.update(user_input)
            reload_fn = getattr(getattr(self, "hass", None), "config_entries", None)
            if reload_fn is not None:
                async_reload = getattr(reload_fn, "async_reload", None)
                if async_reload is not None:
                    result = async_reload(self._entry.entry_id)
                    if inspect.isawaitable(result):
                        await result
            return self.async_create_entry(title="", data=new_options)

        # Enhanced geofence options
        current_lat = self._options.get("geofence_lat", self.hass.config.latitude)
        current_lon = self._options.get("geofence_lon", self.hass.config.longitude)
        current_radius = self._options.get(
            "geofence_radius_m", DEFAULT_SAFE_ZONE_RADIUS
        )

        schema = vol.Schema(
            {
                vol.Required(
                    "geofencing_enabled",
                    default=self._options.get("geofencing_enabled", True),
                ): bool,
                vol.Optional(
                    "geofence_lat",
                    default=current_lat,
                ): vol.Coerce(float),
                vol.Optional(
                    "geofence_lon",
                    default=current_lon,
                ): vol.Coerce(float),
                vol.Optional(
                    "geofence_radius_m",
                    default=current_radius,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SAFE_ZONE_RADIUS, max=MAX_SAFE_ZONE_RADIUS),
                ),
                vol.Optional(
                    "geofence_alerts_enabled",
                    default=self._options.get("geofence_alerts_enabled", True),
                ): bool,
                vol.Optional(
                    "use_home_location",
                    default=False,
                ): bool,
                vol.Optional(
                    "multiple_zones",
                    default=self._options.get("multiple_zones", False),
                ): bool,
                vol.Optional(
                    "zone_detection_mode",
                    default=self._options.get("zone_detection_mode", "home_assistant"),
                ): vol.In(["home_assistant", "custom", "both"]),
            }
        )

        return self.async_show_form(
            step_id="geofence",
            data_schema=schema,
            description_placeholders={
                "current_lat": str(current_lat),
                "current_lon": str(current_lon),
            },
        )

    # === NOTIFICATIONS ===

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure comprehensive notification settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options["notifications"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_notifications = self._options.get("notifications", {})

        schema = vol.Schema(
            {
                vol.Optional(
                    "notifications_enabled",
                    default=current_notifications.get("enabled", True),
                ): bool,
                vol.Optional(
                    "quiet_hours_enabled",
                    default=current_notifications.get("quiet_hours_enabled", False),
                ): bool,
                vol.Optional(
                    "quiet_start",
                    default=current_notifications.get("quiet_start", "22:00"),
                ): str,
                vol.Optional(
                    "quiet_end",
                    default=current_notifications.get("quiet_end", "07:00"),
                ): str,
                vol.Optional(
                    "reminder_repeat_min",
                    default=current_notifications.get(
                        "reminder_repeat_min", DEFAULT_REMINDER_REPEAT
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
                vol.Optional(
                    "snooze_min",
                    default=current_notifications.get("snooze_min", DEFAULT_SNOOZE_MIN),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
                vol.Optional(
                    "priority_notifications",
                    default=current_notifications.get("priority_notifications", True),
                ): bool,
                vol.Optional(
                    "summary_notifications",
                    default=current_notifications.get("summary_notifications", True),
                ): bool,
                vol.Optional(
                    "notification_channels",
                    default=current_notifications.get(
                        "notification_channels", ["mobile", "persistent"]
                    ),
                ): cv.multi_select(
                    {
                        "mobile": "Mobile App",
                        "persistent": "Persistent Notification",
                        "email": "Email",
                        "slack": "Slack",
                        "discord": "Discord",
                    }
                ),
            }
        )

        return self.async_show_form(step_id="notifications", data_schema=schema)

    # === DATA SOURCES ===

    async def async_step_data_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure data source connections."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options["data_sources"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_sources = self._options.get("data_sources", {})

        # Get available entities for selection
        ent_reg = er.async_get(self.hass)

        # Get person entities
        person_entities = [
            entity.entity_id
            for entity in ent_reg.entities.values()
            if entity.domain == "person"
        ]

        # Get device tracker entities
        device_tracker_entities = [
            entity.entity_id
            for entity in ent_reg.entities.values()
            if entity.domain == "device_tracker"
        ]

        # Get binary sensor entities (for door sensors)
        door_sensor_entities = [
            entity.entity_id
            for entity in ent_reg.entities.values()
            if entity.domain == "binary_sensor"
            and (
                "door" in entity.entity_id.lower()
                or "entrance" in entity.entity_id.lower()
            )
        ]

        # Get weather entities
        weather_entities = [
            entity.entity_id
            for entity in ent_reg.entities.values()
            if entity.domain == "weather"
        ]

        # Get calendar entities
        calendar_entities = [
            entity.entity_id
            for entity in ent_reg.entities.values()
            if entity.domain == "calendar"
        ]

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PERSON_ENTITIES,
                    default=current_sources.get(CONF_PERSON_ENTITIES, []),
                ): cv.multi_select(person_entities)
                if person_entities
                else cv.multi_select([]),
                vol.Optional(
                    CONF_DEVICE_TRACKERS,
                    default=current_sources.get(CONF_DEVICE_TRACKERS, []),
                ): cv.multi_select(device_tracker_entities)
                if device_tracker_entities
                else cv.multi_select([]),
                vol.Optional(
                    CONF_DOOR_SENSOR,
                    default=current_sources.get(CONF_DOOR_SENSOR, ""),
                ): vol.In([""] + door_sensor_entities),
                vol.Optional(
                    CONF_WEATHER,
                    default=current_sources.get(CONF_WEATHER, ""),
                ): vol.In([""] + weather_entities),
                vol.Optional(
                    CONF_CALENDAR,
                    default=current_sources.get(CONF_CALENDAR, ""),
                ): vol.In([""] + calendar_entities),
                vol.Optional(
                    "auto_discovery",
                    default=current_sources.get("auto_discovery", True),
                ): bool,
                vol.Optional(
                    "fallback_tracking",
                    default=current_sources.get("fallback_tracking", True),
                ): bool,
            }
        )

        return self.async_show_form(step_id="data_sources", data_schema=schema)

    # === FEATURE MODULES ===

    async def async_step_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure global feature modules."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options["modules"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_modules = self._options.get("modules", {})

        schema = vol.Schema(
            {
                vol.Optional(
                    "module_feeding",
                    default=current_modules.get("feeding", True),
                ): bool,
                vol.Optional(
                    "module_gps",
                    default=current_modules.get("gps", True),
                ): bool,
                vol.Optional(
                    "module_health",
                    default=current_modules.get("health", True),
                ): bool,
                vol.Optional(
                    "module_walk",
                    default=current_modules.get("walk", True),
                ): bool,
                vol.Optional(
                    "module_grooming",
                    default=current_modules.get("grooming", True),
                ): bool,
                vol.Optional(
                    "module_training",
                    default=current_modules.get("training", True),
                ): bool,
                vol.Optional(
                    "module_medication",
                    default=current_modules.get("medication", True),
                ): bool,
                vol.Optional(
                    "module_analytics",
                    default=current_modules.get("analytics", True),
                ): bool,
                vol.Optional(
                    "module_automation",
                    default=current_modules.get("automation", True),
                ): bool,
            }
        )

        return self.async_show_form(step_id="modules", data_schema=schema)

    # === SYSTEM SETTINGS ===

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure system settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_RESET_TIME,
                    default=self._options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
                ): str,
                vol.Optional(
                    CONF_VISITOR_MODE,
                    default=self._options.get(CONF_VISITOR_MODE, False),
                ): bool,
                vol.Optional(
                    CONF_EXPORT_FORMAT,
                    default=self._options.get(
                        CONF_EXPORT_FORMAT, DEFAULT_EXPORT_FORMAT
                    ),
                ): vol.In(["csv", "json", "pdf"]),
                vol.Optional(
                    CONF_EXPORT_PATH,
                    default=self._options.get(CONF_EXPORT_PATH, ""),
                ): str,
                vol.Optional(
                    "auto_prune_devices",
                    default=self._options.get("auto_prune_devices", True),
                ): bool,
                vol.Optional(
                    "performance_mode",
                    default=self._options.get("performance_mode", "balanced"),
                ): vol.In(["minimal", "balanced", "full"]),
                vol.Optional(
                    "log_level",
                    default=self._options.get("log_level", "info"),
                ): vol.In(["debug", "info", "warning", "error"]),
                vol.Optional(
                    "data_retention_days",
                    default=self._options.get("data_retention_days", 365),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=1095)),
            }
        )

        return self.async_show_form(step_id="system", data_schema=schema)

    # === MAINTENANCE & BACKUP ===

    async def async_step_maintenance(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure maintenance and backup options."""
        if user_input is not None:
            if user_input.get("action") == "backup_config":
                return await self._async_backup_configuration()
            elif user_input.get("action") == "restore_config":
                return await self.async_step_restore_config()
            elif user_input.get("action") == "reset_config":
                return await self.async_step_reset_confirm()
            elif user_input.get("action") == "cleanup":
                return await self._async_cleanup_data()
            else:
                new_options = dict(self._options)
                new_options["maintenance"] = {
                    k: v for k, v in user_input.items() if k != "action"
                }
                return self.async_create_entry(title="", data=new_options)

        current_maintenance = self._options.get("maintenance", {})

        schema = vol.Schema(
            {
                vol.Optional(
                    "auto_backup_enabled",
                    default=current_maintenance.get("auto_backup_enabled", True),
                ): bool,
                vol.Optional(
                    "backup_interval_days",
                    default=current_maintenance.get("backup_interval_days", 7),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
                vol.Optional(
                    "auto_cleanup_enabled",
                    default=current_maintenance.get("auto_cleanup_enabled", True),
                ): bool,
                vol.Optional(
                    "cleanup_interval_days",
                    default=current_maintenance.get("cleanup_interval_days", 30),
                ): vol.All(vol.Coerce(int), vol.Range(min=7, max=90)),
                vol.Optional(
                    "action",
                    default="save_settings",
                ): vol.In(
                    {
                        "save_settings": "Save Settings",
                        "backup_config": "Backup Configuration Now",
                        "restore_config": "Restore Configuration",
                        "reset_config": "Reset to Defaults",
                        "cleanup": "Cleanup Old Data",
                    }
                ),
            }
        )

        return self.async_show_form(step_id="maintenance", data_schema=schema)

    async def _async_backup_configuration(self) -> FlowResult:
        """Backup current configuration."""
        try:
            import json
            from datetime import datetime

            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "version": "1.0",
                "data": self._data,
                "options": self._options,
            }

            # Store backup in Home Assistant config directory
            backup_path = self.hass.config.path(
                f"pawcontrol_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

            with open(backup_path, "w") as f:
                json.dump(backup_data, f, indent=2)

            return self.async_show_form(
                step_id="backup_success",
                data_schema=vol.Schema({}),
                description_placeholders={"backup_path": backup_path},
            )

        except Exception as err:
            _LOGGER.error("Failed to backup configuration: %s", err)
            return self.async_show_form(
                step_id="backup_error",
                data_schema=vol.Schema({}),
                errors={"base": "backup_failed"},
            )

    async def _async_cleanup_data(self) -> FlowResult:
        """Cleanup old data and optimize storage."""
        try:
            # This would call cleanup services
            await self.hass.services.async_call(
                DOMAIN,
                "purge_all_storage",
                {"config_entry_id": self._entry.entry_id},
            )

            return self.async_show_form(
                step_id="cleanup_success",
                data_schema=vol.Schema({}),
            )

        except Exception as err:
            _LOGGER.error("Failed to cleanup data: %s", err)
            return self.async_show_form(
                step_id="cleanup_error",
                data_schema=vol.Schema({}),
                errors={"base": "cleanup_failed"},
            )

    # ------------------------------------------------------------------
    # Helper methods used by the test-suite
    # ------------------------------------------------------------------
    def _create_dog_config(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Create a normalized dog configuration from user input."""
        modules = {
            MODULE_WALK: user_input.get(f"module_{MODULE_WALK}", True),
            MODULE_FEEDING: user_input.get(f"module_{MODULE_FEEDING}", True),
        }
        return {
            CONF_DOG_ID: user_input[CONF_DOG_ID],
            CONF_DOG_NAME: user_input.get(CONF_DOG_NAME, ""),
            CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, ""),
            CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 0),
            CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 0.0),
            CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, SIZE_MEDIUM),
            CONF_DOG_MODULES: modules,
        }

    def _update_dog_config(
        self, dog: dict[str, Any], user_input: dict[str, Any]
    ) -> None:
        """Update an existing dog configuration in place."""
        dog[CONF_DOG_NAME] = user_input.get(CONF_DOG_NAME, dog.get(CONF_DOG_NAME, ""))
        if CONF_DOG_AGE in user_input:
            dog[CONF_DOG_AGE] = user_input[CONF_DOG_AGE]
        modules = dog.setdefault(CONF_DOG_MODULES, {})
        if f"module_{MODULE_WALK}" in user_input:
            modules[MODULE_WALK] = user_input[f"module_{MODULE_WALK}"]
        if f"module_{MODULE_FEEDING}" in user_input:
            modules[MODULE_FEEDING] = user_input[f"module_{MODULE_FEEDING}"]

    def _get_available_entities(self, registry) -> dict[str, list[str]]:
        """Return available entities grouped by domain."""
        entities: dict[str, list[str]] = {
            "person": [],
            "device_tracker": [],
            "door_sensor": [],
            "weather": [],
            "calendar": [],
        }
        for ent in registry.entities.values():
            domain = getattr(ent, "domain", ent.entity_id.split(".")[0])
            if domain == "binary_sensor":
                entities["door_sensor"].append(ent.entity_id)
            elif domain in entities:
                entities[domain].append(ent.entity_id)
        return entities

    def _get_dog_config_schema(self) -> vol.Schema:
        """Return schema for validating dog configuration."""
        return vol.Schema(
            {
                vol.Required(CONF_DOG_ID): str,
                vol.Required(CONF_DOG_NAME): str,
                vol.Optional(CONF_DOG_BREED, default=""): str,
                vol.Optional(CONF_DOG_AGE, default=1): vol.Coerce(int),
                vol.Optional(CONF_DOG_WEIGHT, default=DEFAULT_DOG_WEIGHT_KG): vol.Coerce(float),
                vol.Optional(
                    CONF_DOG_SIZE, default=SIZE_MEDIUM
                ): vol.In([SIZE_SMALL, SIZE_MEDIUM, SIZE_LARGE, SIZE_XLARGE]),
            }
        )


# Register the options flow handler
async def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> OptionsFlowHandler:
    """Return the options flow handler."""
    return OptionsFlowHandler(config_entry)
