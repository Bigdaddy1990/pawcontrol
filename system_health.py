"""System health callbacks for the PawControl integration."""

from __future__ import annotations

from typing import Any

from custom_components.pawcontrol.const import DOMAIN
from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks for PawControl."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return system health information for PawControl."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return {
            "can_reach_backend": False,
            "remaining_quota": "unknown",
        }

    entry = entries[0]
    runtime = getattr(entry, "runtime_data", None)
    api = getattr(runtime, "api", None)
    base_url = getattr(api, "base_url", "https://example.invalid")
    remaining_quota = getattr(runtime, "remaining_quota", "unknown")

    return {
        "can_reach_backend": await system_health.async_check_can_reach_url(
            hass, base_url
        ),
        "remaining_quota": remaining_quota,
    }
