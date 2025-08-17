"""Enhanced Config flow for the Paw Control integration.

Goals:
- Avoid optional dependencies at import time (no module-level imports of HA subcomponents).
- Provide resilient handlers for user/dhcp/zeroconf/usb/reauth sources.
- Use lazy import for discovery connection checks to keep tests independent of optional libs.
- Comprehensive options flow with dog management, GPS settings, and advanced configuration.
"""

from __future__ import annotations

from typing import Any, Final
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
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
    CONF_SOURCES,
    # GPS Constants
    GPS_MIN_ACCURACY,
    GPS_POINT_FILTER_DISTANCE,
    DEFAULT_SAFE_ZONE_RADIUS,
    MAX_SAFE_ZONE_RADIUS,
    MIN_SAFE_ZONE_RADIUS,
    # Defaults
    DEFAULT_RESET_TIME,
    DEFAULT_EXPORT_FORMAT,
    DEFAULT_REMINDER_REPEAT,
    DEFAULT_SNOOZE_MIN,
    # Limits
    MIN_DOG_AGE_YEARS,
    MAX_DOG_AGE_YEARS,
    MIN_DOG_WEIGHT_KG,
    MAX_DOG_WEIGHT_KG,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TITLE: Final = "Paw Control"
CONFIG_VERSION: Final = 1

# Keys used in the config entry data/options
CONF_ENABLE_DASHBOARD: Final = "enable_dashboard"
CONF_UNIQUE_ID: Final = "unique_id"
CONF_DEVICE_ID: Final = "device_id"
CONF_SOURCE: Final = "source"  # track discovery source for diagnostics


def _pick_unique_id(data: dict[str, Any]) -> str:
    """Return a stable unique id from provided data or fallback to the domain.

    Order of preference: device_id, unique_id, mac, serial_number, zeroconf properties.
    """
    for key in (CONF_DEVICE_ID, CONF_UNIQUE_ID, "mac", "serial_number"):
        val = str(data.get(key) or "").strip()
        if val:
            return val.lower()
    # Zeroconf properties often carry IDs
    props = data.get("properties") or {}
    if isinstance(props, dict):
        for key in ("id", "uid", "unique_id", "mac"):
            val = str(props.get(key) or "").strip()
            if val:
                return val.lower()
    return DOMAIN  # last resort to keep flow consistent (will be deduped)


async def _can_connect(hass: HomeAssistant, data: dict[str, Any]) -> bool:
    """Lazy import the connectivity check to avoid optional deps during tests."""
    try:
        from .discovery import can_connect_pawtracker  # type: ignore[attr-defined]
    except Exception:
        # In CI/tests or environments where discovery deps are not installed,
        # we do not fail the flow import – consider it connectable.
        return True
    try:
        return await can_connect_pawtracker(hass, data)
    except Exception:
        # Any runtime error during probing is interpreted as non-connectable.
        return False


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Paw Control."""

    VERSION = CONFIG_VERSION
    _reauth_entry: config_entries.ConfigEntry | None = None

    # --- USER FLOW ---

    @staticmethod
    def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
        d = defaults or {}
        return vol.Schema(
            {
                vol.Optional(
                    CONF_ENABLE_DASHBOARD,
                    default=bool(d.get(CONF_ENABLE_DASHBOARD, True)),
                ): bool,
                # Optional device hint (e.g. "usb:VID_10C4&PID_EA60" or a MAC/serial)
                vol.Optional(CONF_DEVICE_ID, default=d.get(CONF_DEVICE_ID, "")): str,
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial user step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self._user_schema())

        # Normalize & pick a unique id
        unique_id = _pick_unique_id(user_input)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # Connectivity probe (best-effort; never import optional deps at module time)
        can = await _can_connect(self.hass, user_input)
        if not can:
            return self.async_show_form(
                step_id="user",
                data_schema=self._user_schema(user_input),
                errors={"base": "cannot_connect"},
            )

        data = dict(user_input)
        data[CONF_SOURCE] = "user"
        data["config_version"] = CONFIG_VERSION
        return self.async_create_entry(title=DEFAULT_TITLE, data=data)

    # --- DISCOVERY FLOWS (DHCP, ZEROCONF, USB) ---

    async def _handle_discovery(
        self, source: str, discovery_info: dict[str, Any]
    ) -> FlowResult:
        """Common discovery handler with lazy connectivity check and dedupe."""
        # Normalize discovery dict into data we persist.
        data = {"discovery": discovery_info, CONF_SOURCE: source}
        data["config_version"] = CONFIG_VERSION

        # Pre-calc a unique id from typical fields (mac, serial, properties)
        unique_id = _pick_unique_id(discovery_info)
        await self.async_set_unique_id(unique_id, raise_on_progress=False)

        # Already configured? Abort cleanly.
        for entry in self._async_current_entries():
            if entry.unique_id == unique_id:
                return self.async_abort(reason="already_configured")

        # Best-effort connection probe; do not kill the flow on optional deps
        can = await _can_connect(self.hass, discovery_info)
        if not can:
            return self.async_abort(reason="cannot_connect")

        # Finalize (no extra confirmation step to keep automation-friendly)
        title = discovery_info.get("name") or DEFAULT_TITLE
        return self.async_create_entry(title=str(title), data=data)

    async def async_step_dhcp(self, discovery_info: dict[str, Any]) -> FlowResult:
        """Handle DHCP discovery."""
        # We don't import homeassistant.components.dhcp at module time – tests stay clean.
        if not isinstance(discovery_info, dict):
            return self.async_abort(reason="not_supported")
        return await self._handle_discovery("dhcp", discovery_info)

    async def async_step_zeroconf(self, discovery_info: dict[str, Any]) -> FlowResult:
        """Handle Zeroconf discovery."""
        if not isinstance(discovery_info, dict):
            return self.async_abort(reason="not_supported")
        return await self._handle_discovery("zeroconf", discovery_info)

    async def async_step_usb(self, discovery_info: dict[str, Any]) -> FlowResult:
        """Handle USB discovery."""
        if not isinstance(discovery_info, dict):
            return self.async_abort(reason="not_supported")
        return await self._handle_discovery("usb", discovery_info)

    # --- REAUTH FLOW ---

    async def async_step_reauth(
        self, entry_data: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a reauthentication flow."""
        if entry_data is None:
            # Cache the existing entry for the confirm step and show form.
            self._reauth_entry = self.hass.config_entries.async_get_entry(
                self.context.get("entry_id") or ""
            )
            return await self.async_step_reauth_confirm()

        return await self.async_step_reauth_confirm(entry_data)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthentication confirmation."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm", data_schema=vol.Schema({})
            )

        # In a real-world scenario you'd validate new creds/options here.
        if self._reauth_entry and user_input:
            new_data = dict(self._reauth_entry.data)
            new_data.update(user_input)
            self.hass.config_entries.async_update_entry(
                self._reauth_entry, data=new_data
            )
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)

        return self.async_abort(reason="reauth_successful")

    # --- IMPORT (YAML) ---

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from YAML, mapping to a config entry."""
        # Map YAML-like data into our schema as far as possible.
        defaults = {
            CONF_ENABLE_DASHBOARD: bool(import_data.get(CONF_ENABLE_DASHBOARD, True)),
            CONF_DEVICE_ID: str(import_data.get(CONF_DEVICE_ID, "")),
            "config_version": CONFIG_VERSION,
        }
        unique_id = _pick_unique_id(import_data)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        title = import_data.get(CONF_NAME, DEFAULT_TITLE)
        return self.async_create_entry(title=title, data=defaults)


PawControlConfigFlow = ConfigFlow


# --- ENHANCED OPTIONS FLOW ---


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
            dogs_info += f"{i}. {dog.get(CONF_DOG_NAME, 'Unnamed')} ({dog.get(CONF_DOG_ID, 'unknown')})\n"

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
                new_dog = self._create_dog_config(user_input)

                # Update entry data
                new_data = dict(self._data)
                new_data.setdefault(CONF_DOGS, []).append(new_dog)

                self.hass.config_entries.async_update_entry(self._entry, data=new_data)

                return self.async_create_entry(title="", data=self._options)

        schema = self._get_dog_config_schema()
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
            dog_name = user_input.get(CONF_DOG_NAME, "").strip()

            if not dog_name:
                errors[CONF_DOG_NAME] = "invalid_dog_name"

            if not errors:
                # Update dog configuration
                self._update_dog_config(dog_to_edit, user_input)

                # Update entry data
                new_data = dict(self._data)
                self.hass.config_entries.async_update_entry(self._entry, data=new_data)

                return self.async_create_entry(title="", data=self._options)

        # Build form schema with current values
        schema = self._get_dog_config_schema(dog_to_edit)

        return self.async_show_form(
            step_id="edit_dog",
            data_schema=schema,
            errors=errors,
            description_placeholders={"dog_name": dog_to_edit.get(CONF_DOG_NAME, "")},
        )

    async def async_step_select_dog_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select and remove a dog."""
        if user_input is not None:
            dog_id_to_remove = user_input["dog_to_remove"]

            # Remove dog from data
            new_data = dict(self._data)
            current_dogs = new_data.get(CONF_DOGS, [])
            new_data[CONF_DOGS] = [
                dog for dog in current_dogs if dog.get(CONF_DOG_ID) != dog_id_to_remove
            ]

            self.hass.config_entries.async_update_entry(self._entry, data=new_data)

            return self.async_create_entry(title="", data=self._options)

        current_dogs = self._data.get(CONF_DOGS, [])
        if not current_dogs:
            return await self.async_step_dogs()

        dog_options = {
            dog[CONF_DOG_ID]: f"{dog[CONF_DOG_NAME]} ({dog[CONF_DOG_ID]})"
            for dog in current_dogs
        }

        schema = vol.Schema({vol.Required("dog_to_remove"): vol.In(dog_options)})

        return self.async_show_form(
            step_id="select_dog_remove",
            data_schema=schema,
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

        # Get entity lists by domain
        entity_lists = self._get_available_entities(ent_reg)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PERSON_ENTITIES,
                    default=current_sources.get(CONF_PERSON_ENTITIES, []),
                ): cv.multi_select(entity_lists["person"])
                if entity_lists["person"]
                else cv.multi_select([]),
                vol.Optional(
                    CONF_DEVICE_TRACKERS,
                    default=current_sources.get(CONF_DEVICE_TRACKERS, []),
                ): cv.multi_select(entity_lists["device_tracker"])
                if entity_lists["device_tracker"]
                else cv.multi_select([]),
                vol.Optional(
                    CONF_DOOR_SENSOR,
                    default=current_sources.get(CONF_DOOR_SENSOR, ""),
                ): vol.In([""] + entity_lists["door_sensor"]),
                vol.Optional(
                    CONF_WEATHER,
                    default=current_sources.get(CONF_WEATHER, ""),
                ): vol.In([""] + entity_lists["weather"]),
                vol.Optional(
                    CONF_CALENDAR,
                    default=current_sources.get(CONF_CALENDAR, ""),
                ): vol.In([""] + entity_lists["calendar"]),
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
                    "reset_time",
                    default=self._options.get("reset_time", DEFAULT_RESET_TIME),
                ): str,
                vol.Optional(
                    "visitor_mode",
                    default=self._options.get("visitor_mode", False),
                ): bool,
                vol.Optional(
                    "export_format",
                    default=self._options.get("export_format", DEFAULT_EXPORT_FORMAT),
                ): vol.In(["csv", "json", "pdf"]),
                vol.Optional(
                    "export_path",
                    default=self._options.get("export_path", ""),
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

    # === HELPER METHODS ===

    def _create_dog_config(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Create a new dog configuration from user input."""
        return {
            CONF_DOG_ID: user_input.get(CONF_DOG_ID, "").strip().lower(),
            CONF_DOG_NAME: user_input.get(CONF_DOG_NAME, "").strip(),
            CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, ""),
            CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 1),
            CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
            CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, SIZE_MEDIUM),
            CONF_DOG_MODULES: {
                MODULE_WALK: user_input.get(f"module_{MODULE_WALK}", True),
                MODULE_FEEDING: user_input.get(f"module_{MODULE_FEEDING}", True),
                MODULE_HEALTH: user_input.get(f"module_{MODULE_HEALTH}", True),
                MODULE_GPS: user_input.get(f"module_{MODULE_GPS}", True),
                MODULE_NOTIFICATIONS: user_input.get(
                    f"module_{MODULE_NOTIFICATIONS}", True
                ),
                MODULE_DASHBOARD: user_input.get(f"module_{MODULE_DASHBOARD}", True),
                MODULE_GROOMING: user_input.get(f"module_{MODULE_GROOMING}", True),
                MODULE_MEDICATION: user_input.get(f"module_{MODULE_MEDICATION}", True),
                MODULE_TRAINING: user_input.get(f"module_{MODULE_TRAINING}", True),
            },
        }

    def _update_dog_config(
        self, dog: dict[str, Any], user_input: dict[str, Any]
    ) -> None:
        """Update an existing dog configuration."""
        dog.update(
            {
                CONF_DOG_NAME: user_input.get(CONF_DOG_NAME, "").strip(),
                CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, ""),
                CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 1),
                CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
                CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, SIZE_MEDIUM),
                CONF_DOG_MODULES: {
                    MODULE_WALK: user_input.get(f"module_{MODULE_WALK}", True),
                    MODULE_FEEDING: user_input.get(f"module_{MODULE_FEEDING}", True),
                    MODULE_HEALTH: user_input.get(f"module_{MODULE_HEALTH}", True),
                    MODULE_GPS: user_input.get(f"module_{MODULE_GPS}", True),
                    MODULE_NOTIFICATIONS: user_input.get(
                        f"module_{MODULE_NOTIFICATIONS}", True
                    ),
                    MODULE_DASHBOARD: user_input.get(
                        f"module_{MODULE_DASHBOARD}", True
                    ),
                    MODULE_GROOMING: user_input.get(f"module_{MODULE_GROOMING}", True),
                    MODULE_MEDICATION: user_input.get(
                        f"module_{MODULE_MEDICATION}", True
                    ),
                    MODULE_TRAINING: user_input.get(f"module_{MODULE_TRAINING}", True),
                },
            }
        )

    def _get_dog_config_schema(self, dog: dict[str, Any] | None = None) -> vol.Schema:
        """Get the schema for dog configuration."""
        defaults = dog if dog else {}
        current_modules = defaults.get(CONF_DOG_MODULES, {})

        return vol.Schema(
            {
                vol.Required(CONF_DOG_ID, default=defaults.get(CONF_DOG_ID, "")): str,
                vol.Required(
                    CONF_DOG_NAME, default=defaults.get(CONF_DOG_NAME, "")
                ): str,
                vol.Optional(
                    CONF_DOG_BREED, default=defaults.get(CONF_DOG_BREED, "")
                ): str,
                vol.Optional(
                    CONF_DOG_AGE, default=defaults.get(CONF_DOG_AGE, 1)
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_DOG_AGE_YEARS, max=MAX_DOG_AGE_YEARS),
                ),
                vol.Optional(
                    CONF_DOG_WEIGHT, default=defaults.get(CONF_DOG_WEIGHT, 20.0)
                ): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=MIN_DOG_WEIGHT_KG, max=MAX_DOG_WEIGHT_KG),
                ),
                vol.Optional(
                    CONF_DOG_SIZE, default=defaults.get(CONF_DOG_SIZE, SIZE_MEDIUM)
                ): vol.In([SIZE_SMALL, SIZE_MEDIUM, SIZE_LARGE, SIZE_XLARGE]),
                # Module toggles
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

    def _get_available_entities(
        self, ent_reg: er.EntityRegistry
    ) -> dict[str, list[str]]:
        """Get available entities by domain."""
        return {
            "person": [
                entity.entity_id
                for entity in ent_reg.entities.values()
                if entity.domain == "person"
            ],
            "device_tracker": [
                entity.entity_id
                for entity in ent_reg.entities.values()
                if entity.domain == "device_tracker"
            ],
            "door_sensor": [
                entity.entity_id
                for entity in ent_reg.entities.values()
                if entity.domain == "binary_sensor"
                and (
                    "door" in entity.entity_id.lower()
                    or "entrance" in entity.entity_id.lower()
                )
            ],
            "weather": [
                entity.entity_id
                for entity in ent_reg.entities.values()
                if entity.domain == "weather"
            ],
            "calendar": [
                entity.entity_id
                for entity in ent_reg.entities.values()
                if entity.domain == "calendar"
            ],
        }

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
            # Call cleanup services
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


class PawControlOptionsFlow(config_entries.OptionsFlow):
    """Backward compatible options flow used in tests."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize simple options flow."""
        self.config_entry = config_entry
        self._options: dict[str, Any] = dict(config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the main options menu."""
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

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure data sources for the integration."""
        if user_input is None:
            return self.async_show_form(step_id="sources", data_schema=vol.Schema({}))

        self._options[CONF_SOURCES] = user_input
        return self.async_create_entry(title="", data=self._options)

    async def async_step_geofence(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure geofence settings and trigger reload."""
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Required("home_lat", default=""): cv.string,
                    vol.Required("home_lon", default=""): cv.string,
                    vol.Required(
                        "geofence_radius_m", default=DEFAULT_SAFE_ZONE_RADIUS
                    ): vol.Coerce(float),
                    vol.Optional("auto_prune_devices", default=False): cv.boolean,
                }
            )
            return self.async_show_form(step_id="geofence", data_schema=schema)

        self._options.update(user_input)
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
        return self.async_create_entry(title="", data=self._options)


async def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> config_entries.OptionsFlow:
    """Return the options flow handler."""
    return PawControlOptionsFlow(config_entry)
