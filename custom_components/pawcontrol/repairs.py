from __future__ import annotations

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# We reuse helpers defined in __init__.py via module import
# - _get_valid_entry_from_call (pattern), but here we need the loaded entry per DOMAIN
# - _auto_prune_devices, _check_geofence_options if available

async def _get_loaded_entry(hass: HomeAssistant):
    """Pick a loaded entry for our domain (best-effort)."""
    from homeassistant.config_entries import ConfigEntryState
    for e in hass.config_entries.async_entries(DOMAIN):
        if e.state is ConfigEntryState.LOADED:
            return e
    return None



class InvalidGeofenceRepairFlow(RepairsFlow):
    """Fix flow that delegates to the Options Flow."""

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        # Single confirm step that launches the options flow for the loaded entry
        if user_input is not None:
            entry = await _get_loaded_entry(self.hass)
            if entry:
                await self.hass.config_entries.options.async_init(entry.entry_id, context={"source": "repair"})
            return self.async_create_entry(title="", data={})
        return self.async_show_form(step_id="init", data_schema=None, description_placeholders={})
class StaleDevicesRepairFlow(ConfirmRepairFlow):
(ConfirmRepairFlow):
    """Confirm flow that prunes stale devices."""

    def __init__(self) -> None:
        super().__init__(DOMAIN)

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            entry = await _get_loaded_entry(self.hass)
            if entry:
                try:
                    from . import _auto_prune_devices  # type: ignore[attr-defined]
                    await _auto_prune_devices(self.hass, entry, auto=True)
                except Exception:
                    pass
            return self.async_create_entry(title="", data={})

        return await super().async_step_confirm(user_input)


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    """Create fix flow for pawcontrol issues."""
    if issue_id == "invalid_geofence":
        return InvalidGeofenceRepairFlow()
    if issue_id == "stale_devices":
        return StaleDevicesRepairFlow()
    # Fallback: confirm-only
    return ConfirmRepairFlow(DOMAIN)
