# custom_components/pawcontrol/system_health.py
from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Provide system health information."""
    entries = hass.config_entries.async_entries(DOMAIN)
    entry = entries[0] if entries else None
    runtime = getattr(entry, "runtime_data", None)
    api = getattr(runtime, "api", None)
    base_url = getattr(api, "base_url", "https://example.invalid")
    return {
        "can_reach_backend": system_health.async_check_can_reach_url(hass, base_url),
        "remaining_quota": getattr(runtime, "remaining_quota", "unknown"),
    }
