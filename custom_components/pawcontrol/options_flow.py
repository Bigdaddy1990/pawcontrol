"""Enhanced Options Flow for the Paw Control integration.

This module provides a comprehensive options flow that allows users to configure
all aspects of their Paw Control integration after initial setup, including:
- Individual dog settings and module toggles
- GPS and geofencing configuration
- Notification settings and quiet hours
- System settings and maintenance options
- Data source connections
- Export and import preferences

The flow follows Home Assistant's Platinum standards with complete type annotations,
proper error handling, and excellent user experience.
"""

from __future__ import annotations

import logging
from typing import Any, Final

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from .const import (
    CONF_DOGS,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_ENABLE_DASHBOARD,
    CONF_EXPORT_FORMAT,
    CONF_EXPORT_PATH,
    CONF_NOTIFICATIONS,
    CONF_NOTIFY_FALLBACK,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT,
    CONF_RESET_TIME,
    CONF_SNOOZE_MIN,
    CONF_SOURCES,
    CONF_VISITOR_MODE,
    DEFAULT_MIN_WALK_DISTANCE_M,
    DEFAULT_MIN_WALK_DURATION_MIN,
    DEFAULT_NOTIFICATION_SERVICE,
    DEFAULT_REMINDER_REPEAT,
    DEFAULT_RESET_TIME,
    DEFAULT_SAFE_ZONE_RADIUS,
    DEFAULT_SNOOZE_MIN,
    DOMAIN,
    DOG_SIZES,
    MAX_DOG_AGE_YEARS,
    MAX_DOG_WEIGHT_KG,
    MAX_SAFE_ZONE_RADIUS,
    MIN_DOG_AGE_YEARS,
    MIN_DOG_WEIGHT_KG,
    MIN_SAFE_ZONE_RADIUS,
)

_LOGGER = logging.getLogger(__name__)

# Options flow menu structure
MENU_OPTIONS: Final[dict[str, str]] = {
    "dogs": "Dog Management",
    "gps_geofence": "GPS & Geofencing", 
    "notifications": "Notifications",
    "modules": "Feature Modules",
    "sources": "Data Sources",
    "system": "System Settings",
    "maintenance": "Maintenance",
}

# GPS and Geofencing options
GPS_MENU_OPTIONS: Final[dict[str, str]] = {
    "geofence": "Geofence Settings",
    "gps_tracking": "GPS Tracking",
    "walk_detection": "Walk Detection",
}

# System settings menu
SYSTEM_MENU_OPTIONS: Final[dict[str, str]] = {
    "general": "General Settings",
    "export_import": "Export/Import",
    "advanced": "Advanced Options",
}


class PawControlOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Paw Control integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._dogs_data: dict[str, Any] = {}
        self._current_dog_index = 0
        self._total_dogs = 0

    @property
    def _options(self) -> dict[str, Any]:
        """Return current options with defaults."""
        return self.config_entry.options

    @property
    def _data(self) -> dict[str, Any]:
        """Return current config data."""
        return self.config_entry.data

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=MENU_OPTIONS,
        )

    # ==========================================================================
    # DOG MANAGEMENT
    # ==========================================================================

    async def async_step_dogs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure individual dog settings."""
        if user_input is not None:
            # Save current dog data and check if we need to configure more dogs
            if self._current_dog_index < self._total_dogs:
                self._dogs_data[f"dog_{self._current_dog_index}"] = user_input
                self._current_dog_index += 1
                
                if self._current_dog_index < self._total_dogs:
                    return await self.async_step_dogs()
                
                # All dogs configured, save and finish
                new_options = dict(self._options)
                new_options[CONF_DOGS] = self._dogs_data
                return self.async_create_entry(title="", data=new_options)
            
            # Single dog update
            new_options = dict(self._options)
            dogs_config = new_options.get(CONF_DOGS, {})
            dog_id = user_input.get(CONF_DOG_ID, "default")
            dogs_config[dog_id] = user_input
            new_options[CONF_DOGS] = dogs_config
            return self.async_create_entry(title="", data=new_options)

        # Get existing dogs from config
        existing_dogs = self._data.get(CONF_DOGS, {})
        if not existing_dogs:
            # No dogs configured yet
            return self.async_show_form(
                step_id="dogs",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "message": "No dogs are configured. Please reconfigure the integration to add dogs."
                },
            )

        # For simplicity, let's configure the first dog found
        dog_data = list(existing_dogs.values())[0] if existing_dogs else {}
        
        return self.async_show_form(
            step_id="dogs",
            data_schema=self._build_dog_schema(dog_data),
            description_placeholders={
                "dog_name": dog_data.get(CONF_DOG_NAME, "your dog"),
            },
        )

    def _build_dog_schema(self, dog_data: dict[str, Any]) -> vol.Schema:
        """Build schema for dog configuration."""
        return vol.Schema({
            vol.Required(
                CONF_DOG_NAME,
                default=dog_data.get(CONF_DOG_NAME, ""),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            
            vol.Optional(
                CONF_DOG_BREED,
                default=dog_data.get(CONF_DOG_BREED, ""),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            
            vol.Optional(
                CONF_DOG_AGE,
                default=dog_data.get(CONF_DOG_AGE, 2),
            ): NumberSelector(NumberSelectorConfig(
                min=MIN_DOG_AGE_YEARS,
                max=MAX_DOG_AGE_YEARS,
                mode=NumberSelectorMode.SLIDER,
                unit_of_measurement="years",
            )),
            
            vol.Optional(
                CONF_DOG_WEIGHT,
                default=dog_data.get(CONF_DOG_WEIGHT, 20.0),
            ): NumberSelector(NumberSelectorConfig(
                min=MIN_DOG_WEIGHT_KG,
                max=MAX_DOG_WEIGHT_KG,
                step=0.1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="kg",
            )),
            
            vol.Optional(
                CONF_DOG_SIZE,
                default=dog_data.get(CONF_DOG_SIZE, "medium"),
            ): SelectSelector(SelectSelectorConfig(
                options=[{"value": k, "label": v["name"]} for k, v in DOG_SIZES.items()],
                mode=SelectSelectorMode.DROPDOWN,
            )),
        })

    # ==========================================================================
    # GPS & GEOFENCING
    # ==========================================================================

    async def async_step_gps_geofence(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure GPS and geofencing options."""
        return self.async_show_menu(
            step_id="gps_geofence",
            menu_options=GPS_MENU_OPTIONS,
        )

    async def async_step_geofence(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure geofence settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        # Get current geofence settings
        current_lat = self._options.get("geofence_lat", self.hass.config.latitude)
        current_lon = self._options.get("geofence_lon", self.hass.config.longitude)
        current_radius = self._options.get("geofence_radius_m", DEFAULT_SAFE_ZONE_RADIUS)
        
        return self.async_show_form(
            step_id="geofence",
            data_schema=vol.Schema({
                vol.Required(
                    "geofence_enabled",
                    default=self._options.get("geofence_enabled", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "geofence_lat",
                    default=current_lat,
                ): NumberSelector(NumberSelectorConfig(
                    min=-90,
                    max=90,
                    step=0.000001,
                    mode=NumberSelectorMode.BOX,
                )),
                
                vol.Optional(
                    "geofence_lon", 
                    default=current_lon,
                ): NumberSelector(NumberSelectorConfig(
                    min=-180,
                    max=180,
                    step=0.000001,
                    mode=NumberSelectorMode.BOX,
                )),
                
                vol.Optional(
                    "geofence_radius_m",
                    default=current_radius,
                ): NumberSelector(NumberSelectorConfig(
                    min=MIN_SAFE_ZONE_RADIUS,
                    max=MAX_SAFE_ZONE_RADIUS,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="m",
                )),
                
                vol.Optional(
                    "geofence_alerts_enabled",
                    default=self._options.get("geofence_alerts_enabled", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "use_home_location",
                    default=False,
                ): BooleanSelector(),
            }),
        )

    async def async_step_gps_tracking(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure GPS tracking settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="gps_tracking",
            data_schema=vol.Schema({
                vol.Optional(
                    "gps_enabled",
                    default=self._options.get("gps_enabled", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "gps_accuracy_threshold",
                    default=self._options.get("gps_accuracy_threshold", 50),
                ): NumberSelector(NumberSelectorConfig(
                    min=5,
                    max=200,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="m",
                )),
                
                vol.Optional(
                    "gps_update_interval",
                    default=self._options.get("gps_update_interval", 30),
                ): NumberSelector(NumberSelectorConfig(
                    min=10,
                    max=300,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="s",
                )),
                
                vol.Optional(
                    "store_route_history",
                    default=self._options.get("store_route_history", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "max_route_points",
                    default=self._options.get("max_route_points", 1000),
                ): NumberSelector(NumberSelectorConfig(
                    min=100,
                    max=10000,
                    mode=NumberSelectorMode.BOX,
                )),
            }),
        )

    async def async_step_walk_detection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure walk detection settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="walk_detection",
            data_schema=vol.Schema({
                vol.Optional(
                    "auto_walk_detection",
                    default=self._options.get("auto_walk_detection", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "min_walk_distance_m",
                    default=self._options.get("min_walk_distance_m", DEFAULT_MIN_WALK_DISTANCE_M),
                ): NumberSelector(NumberSelectorConfig(
                    min=50,
                    max=1000,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="m",
                )),
                
                vol.Optional(
                    "min_walk_duration_min",
                    default=self._options.get("min_walk_duration_min", DEFAULT_MIN_WALK_DURATION_MIN),
                ): NumberSelector(NumberSelectorConfig(
                    min=1,
                    max=60,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="min",
                )),
                
                vol.Optional(
                    "auto_end_walk_timeout",
                    default=self._options.get("auto_end_walk_timeout", 30),
                ): NumberSelector(NumberSelectorConfig(
                    min=5,
                    max=120,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="min",
                )),
            }),
        )

    # ==========================================================================
    # NOTIFICATIONS
    # ==========================================================================

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure notification settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options[CONF_NOTIFICATIONS] = user_input
            return self.async_create_entry(title="", data=new_options)

        # Get current notification settings
        current_notifications = self._options.get(CONF_NOTIFICATIONS, {})
        
        # Get available notification services
        notify_services = []
        for service in self.hass.services.async_services().get("notify", {}):
            notify_services.append({"value": f"notify.{service}", "label": service})
        
        if not notify_services:
            notify_services = [{"value": DEFAULT_NOTIFICATION_SERVICE, "label": "notify"}]

        return self.async_show_form(
            step_id="notifications",
            data_schema=vol.Schema({
                vol.Optional(
                    "notifications_enabled",
                    default=current_notifications.get("enabled", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    CONF_NOTIFY_FALLBACK,
                    default=current_notifications.get(CONF_NOTIFY_FALLBACK, DEFAULT_NOTIFICATION_SERVICE),
                ): SelectSelector(SelectSelectorConfig(
                    options=notify_services,
                    mode=SelectSelectorMode.DROPDOWN,
                )),
                
                vol.Optional(
                    "quiet_hours_enabled",
                    default=current_notifications.get("quiet_hours_enabled", False),
                ): BooleanSelector(),
                
                vol.Optional(
                    CONF_QUIET_START,
                    default=current_notifications.get(CONF_QUIET_START, "22:00"),
                ): TimeSelector(),
                
                vol.Optional(
                    CONF_QUIET_END,
                    default=current_notifications.get(CONF_QUIET_END, "07:00"),
                ): TimeSelector(),
                
                vol.Optional(
                    CONF_REMINDER_REPEAT,
                    default=current_notifications.get(CONF_REMINDER_REPEAT, DEFAULT_REMINDER_REPEAT),
                ): NumberSelector(NumberSelectorConfig(
                    min=5,
                    max=120,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="min",
                )),
                
                vol.Optional(
                    CONF_SNOOZE_MIN,
                    default=current_notifications.get(CONF_SNOOZE_MIN, DEFAULT_SNOOZE_MIN),
                ): NumberSelector(NumberSelectorConfig(
                    min=1,
                    max=60,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="min",
                )),
            }),
        )

    # ==========================================================================
    # FEATURE MODULES
    # ==========================================================================

    async def async_step_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure feature modules."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options["modules"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_modules = self._options.get("modules", {})

        return self.async_show_form(
            step_id="modules",
            data_schema=vol.Schema({
                vol.Optional(
                    "module_feeding",
                    default=current_modules.get("feeding", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "module_gps",
                    default=current_modules.get("gps", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "module_health",
                    default=current_modules.get("health", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "module_walk", 
                    default=current_modules.get("walk", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "module_grooming",
                    default=current_modules.get("grooming", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "module_training",
                    default=current_modules.get("training", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "module_medication",
                    default=current_modules.get("medication", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    CONF_ENABLE_DASHBOARD,
                    default=current_modules.get("dashboard", True),
                ): BooleanSelector(),
            }),
        )

    # ==========================================================================
    # DATA SOURCES
    # ==========================================================================

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure data sources."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options[CONF_SOURCES] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_sources = self._options.get(CONF_SOURCES, {})

        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema({
                vol.Optional(
                    "door_sensor",
                    default=current_sources.get("door_sensor", ""),
                ): EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
                
                vol.Optional(
                    "person_entities",
                    default=current_sources.get("person_entities", []),
                ): EntitySelector(EntitySelectorConfig(
                    domain="person",
                    multiple=True,
                )),
                
                vol.Optional(
                    "device_trackers",
                    default=current_sources.get("device_trackers", []),
                ): EntitySelector(EntitySelectorConfig(
                    domain="device_tracker",
                    multiple=True,
                )),
                
                vol.Optional(
                    "calendar",
                    default=current_sources.get("calendar", ""),
                ): EntitySelector(EntitySelectorConfig(domain="calendar")),
                
                vol.Optional(
                    "weather",
                    default=current_sources.get("weather", ""),
                ): EntitySelector(EntitySelectorConfig(domain="weather")),
            }),
        )

    # ==========================================================================
    # SYSTEM SETTINGS
    # ==========================================================================

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure system settings."""
        return self.async_show_menu(
            step_id="system",
            menu_options=SYSTEM_MENU_OPTIONS,
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure general system settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_RESET_TIME,
                    default=self._options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
                ): TimeSelector(),
                
                vol.Optional(
                    CONF_VISITOR_MODE,
                    default=self._options.get(CONF_VISITOR_MODE, False),
                ): BooleanSelector(),
                
                vol.Optional(
                    "emergency_mode_enabled", 
                    default=self._options.get("emergency_mode_enabled", False),
                ): BooleanSelector(),
                
                vol.Optional(
                    "auto_prune_devices",
                    default=self._options.get("auto_prune_devices", True),
                ): BooleanSelector(),
            }),
        )

    async def async_step_export_import(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure export and import settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="export_import",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_EXPORT_FORMAT,
                    default=self._options.get(CONF_EXPORT_FORMAT, "csv"),
                ): SelectSelector(SelectSelectorConfig(
                    options=[
                        {"value": "csv", "label": "CSV"},
                        {"value": "json", "label": "JSON"},
                        {"value": "pdf", "label": "PDF"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )),
                
                vol.Optional(
                    CONF_EXPORT_PATH,
                    default=self._options.get(CONF_EXPORT_PATH, ""),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                
                vol.Optional(
                    "auto_export_enabled",
                    default=self._options.get("auto_export_enabled", False),
                ): BooleanSelector(),
                
                vol.Optional(
                    "export_interval_days",
                    default=self._options.get("export_interval_days", 7),
                ): NumberSelector(NumberSelectorConfig(
                    min=1,
                    max=30,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="days",
                )),
            }),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure advanced system options."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema({
                vol.Optional(
                    "debug_logging",
                    default=self._options.get("debug_logging", False),
                ): BooleanSelector(),
                
                vol.Optional(
                    "performance_monitoring",
                    default=self._options.get("performance_monitoring", True),
                ): BooleanSelector(),
                
                vol.Optional(
                    "coordinator_update_interval",
                    default=self._options.get("coordinator_update_interval", 60),
                ): NumberSelector(NumberSelectorConfig(
                    min=30,
                    max=300,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="s",
                )),
                
                vol.Optional(
                    "max_history_days",
                    default=self._options.get("max_history_days", 30),
                ): NumberSelector(NumberSelectorConfig(
                    min=7,
                    max=365,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="days",
                )),
            }),
        )

    # ==========================================================================
    # MAINTENANCE
    # ==========================================================================

    async def async_step_maintenance(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure maintenance options."""
        if user_input is not None:
            # Handle maintenance actions
            if user_input.get("reset_statistics"):
                # Trigger reset statistics service
                await self.hass.services.async_call(
                    DOMAIN,
                    "daily_reset",
                    {"config_entry_id": self.config_entry.entry_id},
                )
            
            if user_input.get("purge_old_data"):
                # Trigger purge service
                await self.hass.services.async_call(
                    DOMAIN,
                    "route_history_purge",
                    {
                        "config_entry_id": self.config_entry.entry_id,
                        "older_than_days": user_input.get("purge_older_than_days", 30),
                    },
                )
            
            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="maintenance",
            data_schema=vol.Schema({
                vol.Optional("reset_statistics", default=False): BooleanSelector(),
                vol.Optional("purge_old_data", default=False): BooleanSelector(),
                vol.Optional(
                    "purge_older_than_days",
                    default=30,
                ): NumberSelector(NumberSelectorConfig(
                    min=7,
                    max=365,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="days",
                )),
            }),
        )


@callback
def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> PawControlOptionsFlowHandler:
    """Return the options flow handler for the component."""
    return PawControlOptionsFlowHandler(config_entry)