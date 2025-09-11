# custom_components/pawcontrol/system_health.py
from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import callback
from homeassistant.core import HomeAssistant

DOMAIN = "pawcontrol"


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Provide system health information for PawControl."""
    if not hass.config_entries.async_entries(DOMAIN):
        return {}

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    runtime = getattr(entry, "runtime_data", None)
    api = getattr(runtime, "api", None)
    return {
        "can_reach_backend": await system_health.async_check_can_reach_url(
            hass, getattr(api, "base_url", "https://example.invalid")
        ),
        "remaining_quota": getattr(runtime, "remaining_quota", "unknown"),
    }
