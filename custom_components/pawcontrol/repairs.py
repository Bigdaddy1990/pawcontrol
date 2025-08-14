"""Repairs support for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class InvalidGeofenceRepairFlow(RepairsFlow):
    """Repair flow for invalid geofence options."""

    def __init__(self, hass: HomeAssistant | None = None, entry_id: str | None = None) -> None:
        """Initialize the repair flow."""
        self.hass = hass
        self.entry_id = entry_id or ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """First step: choose repair action."""
        schema = vol.Schema(
            {
                vol.Required("action"): vol.In(
                    {
                        "reset": "Reset to defaults (clear home, set 150m radius)",
                        "disable_alerts": "Disable geofence alerts (keep current center)",
                        "manual": "Manually enter coordinates",
                    }
                )
            }
        )

        if user_input is not None:
            action = user_input["action"]

            if action == "manual":
                return await self.async_step_manual_coordinates()

            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if not entry:
                # Entry vanished -> just delete the issue
                ir.async_delete_issue(self.hass, DOMAIN, "invalid_geofence")
                return self.async_create_entry(title="Geofence Fixed", data={})

            opts = dict(entry.options or {})
            geo = dict(opts.get("geofence") or {})

            if action == "reset":
                geo = {"lat": None, "lon": None, "radius_m": 150, "enable_alerts": True}
            elif action == "disable_alerts":
                geo["enable_alerts"] = False

            opts["geofence"] = geo
            self.hass.config_entries.async_update_entry(entry, options=opts)
            ir.async_delete_issue(self.hass, DOMAIN, "invalid_geofence")
            return self.async_create_entry(title="Geofence Fixed", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "entry_id": self.entry_id[:8],
            },
        )

    async def async_step_manual_coordinates(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Step for manual coordinate entry."""
        errors = {}

        if user_input is not None:
            # Validate coordinates
            try:
                lat = float(user_input["latitude"])
                lon = float(user_input["longitude"])
                radius = int(user_input["radius_m"])

                if not (-90 <= lat <= 90):
                    errors["latitude"] = "invalid_latitude"
                elif not (-180 <= lon <= 180):
                    errors["longitude"] = "invalid_longitude"
                elif not (10 <= radius <= 5000):
                    errors["radius_m"] = "invalid_radius"

                if not errors:
                    entry = self.hass.config_entries.async_get_entry(self.entry_id)
                    if entry:
                        opts = dict(entry.options or {})
                        opts["geofence"] = {
                            "lat": lat,
                            "lon": lon,
                            "radius_m": radius,
                            "enable_alerts": user_input.get("enable_alerts", True),
                        }
                        self.hass.config_entries.async_update_entry(entry, options=opts)

                    ir.async_delete_issue(self.hass, DOMAIN, "invalid_geofence")
                    return self.async_create_entry(title="Geofence Configured", data={})

            except (ValueError, TypeError):
                errors["base"] = "invalid_input"

        schema = vol.Schema(
            {
                vol.Required("latitude", default=52.52): vol.Coerce(float),
                vol.Required("longitude", default=13.405): vol.Coerce(float),
                vol.Required("radius_m", default=150): vol.All(
                    vol.Coerce(int), vol.Range(min=10, max=5000)
                ),
                vol.Optional("enable_alerts", default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="manual_coordinates",
            data_schema=schema,
            errors=errors,
        )


class MissingNotificationServiceRepairFlow(RepairsFlow):
    """Repair flow for missing notification service."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the repair flow."""
        self.hass = hass
        self.entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Configure notification service."""
        errors = {}

        if user_input is not None:
            service = user_input.get("notify_service")

            # Validate service exists
            if service and self.hass.services.has_service("notify", service):
                entry = self.hass.config_entries.async_get_entry(self.entry_id)
                if entry:
                    opts = dict(entry.options or {})
                    opts.setdefault("notifications", {})["notify_fallback"] = (
                        f"notify.{service}"
                    )
                    self.hass.config_entries.async_update_entry(entry, options=opts)

                ir.async_delete_issue(self.hass, DOMAIN, "missing_notification_service")
                return self.async_create_entry(
                    title="Notifications Configured", data={}
                )
            else:
                errors["notify_service"] = "service_not_found"

        # Get available notification services
        services = []
        for service in self.hass.services.async_services().get("notify", {}):
            if service not in ["notify", "persistent_notification"]:
                services.append(service)

        if not services:
            # No services available
            return self.async_abort(reason="no_notification_services")

        schema = vol.Schema(
            {
                vol.Required("notify_service"): vol.In(services),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )


class StaleDevicesRepairFlow(RepairsFlow):
    """Repair flow for stale devices."""

    def __init__(self, hass: HomeAssistant, entry_id: str, devices: list[str]) -> None:
        """Initialize the repair flow."""
        self.hass = hass
        self.entry_id = entry_id
        self.devices = devices

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle stale devices."""
        if user_input is not None and user_input.get("confirm_removal"):
            # Call the prune service
            await self.hass.services.async_call(
                DOMAIN,
                "prune_stale_devices",
                {"auto": True},
                blocking=True,
            )

            ir.async_delete_issue(self.hass, DOMAIN, "stale_devices")
            return self.async_create_entry(
                title="Stale Devices Removed", data={"removed": len(self.devices)}
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm_removal", default=False): bool,
                }
            ),
            description_placeholders={
                "count": str(len(self.devices)),
                "devices": ", ".join(self.devices[:5]),  # Show first 5 device names
            },
        )


class CorruptedDataRepairFlow(RepairsFlow):
    """Repair flow for corrupted data."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the repair flow."""
        self.hass = hass
        self.entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle corrupted data repair."""
        if user_input is not None:
            action = user_input.get("action")

            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if not entry:
                ir.async_delete_issue(self.hass, DOMAIN, "corrupted_data")
                return self.async_create_entry(title="Issue Resolved", data={})

            if action == "reset_daily":
                # Trigger daily reset
                await self.hass.services.async_call(
                    DOMAIN,
                    "daily_reset",
                    {},
                    blocking=True,
                )
                ir.async_delete_issue(self.hass, DOMAIN, "corrupted_data")
                return self.async_create_entry(title="Data Reset", data={})

            elif action == "reload":
                # Reload the integration
                await self.hass.config_entries.async_reload(self.entry_id)
                ir.async_delete_issue(self.hass, DOMAIN, "corrupted_data")
                return self.async_create_entry(title="Integration Reloaded", data={})

            elif action == "export_backup":
                # Export current data as backup
                await self.hass.services.async_call(
                    DOMAIN,
                    "export_data",
                    {"format": "json"},
                    blocking=True,
                )
                return await self.async_step_confirm_reset()

        schema = vol.Schema(
            {
                vol.Required("action"): vol.In(
                    {
                        "reset_daily": "Reset daily counters only",
                        "reload": "Reload the integration",
                        "export_backup": "Export backup and reset all data",
                    }
                )
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )

    async def async_step_confirm_reset(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Confirm full data reset."""
        if user_input is not None and user_input.get("confirm") == "DELETE":
            # Purge all storage
            await self.hass.services.async_call(
                DOMAIN,
                "purge_all_storage",
                {"confirm": "DELETE"},
                blocking=True,
            )

            # Reload integration
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if entry:
                await self.hass.config_entries.async_reload(self.entry_id)

            ir.async_delete_issue(self.hass, DOMAIN, "corrupted_data")
            return self.async_create_entry(title="Data Reset Complete", data={})

        return self.async_show_form(
            step_id="confirm_reset",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm"): str,
                }
            ),
            description_placeholders={
                "warning": "This will delete ALL Paw Control data. Type 'DELETE' to confirm.",
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create a fix flow instance for our issues."""
    entry_id = data.get("entry_id", "") if data else ""

    if issue_id == "invalid_geofence":
        return InvalidGeofenceRepairFlow(hass, entry_id)
    elif issue_id == "missing_notification_service":
        return MissingNotificationServiceRepairFlow(hass, entry_id)
    elif issue_id == "stale_devices":
        devices = data.get("devices", []) if data else []
        return StaleDevicesRepairFlow(hass, entry_id, devices)
    elif issue_id == "corrupted_data":
        return CorruptedDataRepairFlow(hass, entry_id)

    # Fallback to geofence repair
    return InvalidGeofenceRepairFlow(hass, entry_id)


def create_repair_issue(
    hass: HomeAssistant,
    issue_id: str,
    entry: ConfigEntry,
    severity: ir.IssueSeverity = ir.IssueSeverity.WARNING,
    data: dict[str, Any] | None = None,
) -> None:
    """Register a repair issue for a config entry."""
    issue_data = {"entry_id": entry.entry_id}
    if data:
        issue_data.update(data)

    try:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id=issue_id,
            is_fixable=True,
            severity=severity,
            translation_key=issue_id,
            data=issue_data,
        )
        _LOGGER.info(f"Created repair issue: {issue_id}")
    except Exception as err:
        _LOGGER.error(f"Failed to create repair issue {issue_id}: {err}")


def delete_repair_issue(hass: HomeAssistant, issue_id: str) -> None:
    """Delete a repair issue."""
    try:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        _LOGGER.debug(f"Deleted repair issue: {issue_id}")
    except Exception as err:
        _LOGGER.error(f"Failed to delete repair issue {issue_id}: {err}")
