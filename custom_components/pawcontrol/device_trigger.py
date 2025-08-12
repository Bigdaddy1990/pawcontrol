
from __future__ import annotations
from typing import Any, Dict, List
import voluptuous as vol

from homeassistant.core import HomeAssistant, CALLBACK_TYPE, callback
from homeassistant.const import CONF_DEVICE_ID, CONF_TYPE
from homeassistant.components.device_automation import TRIGGER_BASE_SCHEMA
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

EVENT_MAP = {
    "walk_started": "pawcontrol_walk_started",
    "walk_finished": "pawcontrol_walk_finished",
    "safe_zone_entered": "pawcontrol_safe_zone_entered",
    "safe_zone_left": "pawcontrol_safe_zone_left",
}

TRIGGER_SCHEMA = TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(list(EVENT_MAP.keys())),
    }
)

async def async_get_triggers(hass: HomeAssistant, device_id: str) -> List[Dict[str, Any]]:
    """Return a list of triggers for a device (per dog)."""
    triggers: list[dict] = []
    devreg = dr.async_get(hass)
    device = devreg.async_get(device_id)
    if not device:
        return triggers
    # Find dog_id from identifiers
    dog_id: str | None = None
    for domain, ident in device.identifiers:
        if domain == DOMAIN:
            dog_id = ident
            break
    if not dog_id:
        return triggers
    for t in EVENT_MAP.keys():
        triggers.append({CONF_DEVICE_ID: device_id, CONF_TYPE: t, "domain": DOMAIN})
    return triggers

async def async_attach_trigger(
    hass: HomeAssistant, config: ConfigType, action, trigger_info
) -> CALLBACK_TYPE:
    """Attach a trigger for the given device event."""
    devreg = dr.async_get(hass)
    device = devreg.async_get(config[CONF_DEVICE_ID])
    dog_id: str | None = None
    if device:
        for domain, ident in device.identifiers:
            if domain == DOMAIN:
                dog_id = ident
                break
    event_type = EVENT_MAP[config[CONF_TYPE]]

    @callback
    def _handle_event(ev):
        if dog_id and ev.data.get("dog_id") != dog_id:
            return
        hass.async_run_job(action, {"trigger": {"platform": "device", "type": config[CONF_TYPE], "event": ev.as_dict()}})

    remove = hass.bus.async_listen(event_type, _handle_event)
    return remove
