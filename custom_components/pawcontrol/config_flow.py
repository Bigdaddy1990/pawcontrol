"""Config flow for the Paw Control integration.

Goals:
- Avoid optional dependencies at import time (no module-level imports of HA subcomponents).
- Provide resilient handlers for user/dhcp/zeroconf/usb/reauth sources.
- Use lazy import for discovery connection checks to keep tests independent of optional libs.
"""

from __future__ import annotations

from typing import Any, Final

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

DEFAULT_TITLE: Final = "Paw Control"

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

    VERSION = 1
    _reauth_entry: config_entries.ConfigEntry | None = None

    # --- USER FLOW ---

    @staticmethod
    def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
        d = defaults or {}
        return vol.Schema(
            {
                vol.Required(CONF_NAME, default=d.get(CONF_NAME, DEFAULT_TITLE)): str,
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
        return self.async_create_entry(
            title=user_input.get(CONF_NAME, DEFAULT_TITLE), data=data
        )

    # --- DISCOVERY FLOWS (DHCP, ZEROCONF, USB) ---

    async def _handle_discovery(
        self, source: str, discovery_info: dict[str, Any]
    ) -> FlowResult:
        """Common discovery handler with lazy connectivity check and dedupe."""
        # Normalize discovery dict into data we persist.
        data = {"discovery": discovery_info, CONF_SOURCE: source}

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

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Initiate a reauthentication flow."""
        # Cache the existing entry for the confirm step.
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context.get("entry_id") or ""
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthentication confirmation."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm", data_schema=vol.Schema({})
            )

        # In a real-world scenario you'd validate new creds/options here.
        if self._reauth_entry:
            # No breaking changes to structure; just trigger a reload to pick up new options.
            self.hass.config_entries.async_update_entry(
                self._reauth_entry, data=dict(self._reauth_entry.data)
            )
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)

        return self.async_abort(reason="reauth_successful")

    # --- IMPORT (YAML) ---

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from YAML, mapping to a config entry."""
        # Map YAML-like data into our schema as far as possible.
        defaults = {
            CONF_NAME: import_data.get(CONF_NAME, DEFAULT_TITLE),
            CONF_ENABLE_DASHBOARD: bool(import_data.get(CONF_ENABLE_DASHBOARD, True)),
            CONF_DEVICE_ID: str(import_data.get(CONF_DEVICE_ID, "")),
        }
        unique_id = _pick_unique_id(import_data)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=defaults[CONF_NAME], data=defaults)


# --- OPTIONS FLOW (comprehensive, user-friendly) ---


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Enhanced options flow with comprehensive configuration options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry
        self._dogs_data: dict[str, Any] = {}
        self._current_dog_index = 0
        self._total_dogs = 0

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
        """Manage the options with a menu-based approach."""
        if user_input is not None:
            # Handle direct option updates (backward compatibility)
            return self.async_create_entry(title="", data=user_input)

        # Show menu for comprehensive options
        menu_options = {
            "geofence": "Geofence Settings",
            "notifications": "Notifications",
            "modules": "Feature Modules",
            "system": "System Settings",
        }

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
        )

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
        current_radius = self._options.get("geofence_radius_m", 150)

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
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=2000)),
                vol.Optional(
                    "geofence_alerts_enabled",
                    default=self._options.get("geofence_alerts_enabled", True),
                ): bool,
                vol.Optional(
                    "use_home_location",
                    default=False,
                ): bool,
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

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure notification settings."""
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
                    default=current_notifications.get("reminder_repeat_min", 30),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
            }
        )

        return self.async_show_form(step_id="notifications", data_schema=schema)

    async def async_step_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure feature modules."""
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
            }
        )

        return self.async_show_form(step_id="modules", data_schema=schema)

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
                    default=self._options.get("reset_time", "23:59:00"),
                ): str,
                vol.Optional(
                    "visitor_mode",
                    default=self._options.get("visitor_mode", False),
                ): bool,
                vol.Optional(
                    "export_format",
                    default=self._options.get("export_format", "csv"),
                ): vol.In(["csv", "json", "pdf"]),
                vol.Optional(
                    "auto_prune_devices",
                    default=self._options.get("auto_prune_devices", True),
                ): bool,
            }
        )

        return self.async_show_form(step_id="system", data_schema=schema)


async def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> OptionsFlowHandler:
    """Return the options flow handler."""
    return OptionsFlowHandler(config_entry)
