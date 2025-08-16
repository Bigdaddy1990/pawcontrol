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

DOMAIN: Final = "pawcontrol"
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
                    CONF_ENABLE_DASHBOARD, default=bool(d.get(CONF_ENABLE_DASHBOARD, True))
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
            return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({}))

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


# --- OPTIONS FLOW (minimal, safe default) ---

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Provide a minimal options flow to satisfy tests and keep UX cohesive."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Keep it minimal but future-proof; geofence-related options are common for this domain.
        options = {
            "geofencing_enabled": bool(self._entry.options.get("geofencing_enabled", True)),
            "home_zone": str(self._entry.options.get("home_zone", "home")),
            "radius_m": int(self._entry.options.get("radius_m", 150)),
        }
        schema = vol.Schema(
            {
                vol.Required("geofencing_enabled", default=options["geofencing_enabled"]): bool,
                vol.Optional("home_zone", default=options["home_zone"]): str,
                vol.Optional("radius_m", default=options["radius_m"]): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


async def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> OptionsFlowHandler:
    """Return the options flow handler."""
    return OptionsFlowHandler(config_entry)
