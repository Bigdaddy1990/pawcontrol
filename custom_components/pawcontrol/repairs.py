from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN


class InvalidGeofenceRepairFlow(RepairsFlow):
    """Repair flow for invalid geofence options."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """First step: choose repair action."""
        schema = vol.Schema(
            {
                vol.Required("action"): vol.In(
                    {
                        "reset": "reset",
                        "disable_alerts": "disable_alerts",
                    }
                )
            }
        )
        if user_input is not None:
            action = user_input["action"]
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if not entry:
                # Entry vanished -> just delete the issue
                ir.async_delete_issue(self.hass, DOMAIN, "invalid_geofence")
                return self.async_create_entry(title="", data={})

            opts = dict(entry.options or {})
            geo = dict(opts.get("geofence") or {})
            if action == "reset":
                geo = {"lat": None, "lon": None, "radius_m": 150, "enable_alerts": True}
            elif action == "disable_alerts":
                geo["enable_alerts"] = False

            opts["geofence"] = geo
            self.hass.config_entries.async_update_entry(entry, options=opts)
            # Drop the issue once fixed
            ir.async_delete_issue(self.hass, DOMAIN, "invalid_geofence")
            return self.async_create_entry(title="", data={})

        return self.async_show_form(step_id="init", data_schema=schema)


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create a fix flow instance for our issues."""
    if issue_id == "invalid_geofence" and data and "entry_id" in data:
        return InvalidGeofenceRepairFlow(hass, data["entry_id"])
    # fallback dummy (shouldn't happen)
    return InvalidGeofenceRepairFlow(hass, "")
