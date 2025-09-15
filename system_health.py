# custom_components/pawcontrol/system_health.py
"""System health checks for the PawControl integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

DOMAIN = "pawcontrol"


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""

    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return integration health information."""

    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return {"info": "No PawControl config entries found"}

    entry = entries[0]
    runtime = getattr(entry, "runtime_data", None)
    api = getattr(runtime, "api", None)
    if runtime is None or api is None:
        return {
            "can_reach_backend": {"type": "failed", "error": "api_unavailable"},
            "remaining_quota": "unknown",
        }

    base_url = getattr(api, "base_url", None)
    if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
        can_reach = {"type": "failed", "error": "invalid_base_url"}
    else:
        can_reach = system_health.async_check_can_reach_url(hass, base_url)

    return {
        "can_reach_backend": can_reach,
        "remaining_quota": getattr(runtime, "remaining_quota", "unknown"),
    }
    return {
        "can_reach_backend": system_health.async_check_can_reach_url(
            hass, getattr(api, "base_url", "https://example.invalid")
        ),
        "remaining_quota": getattr(runtime, "remaining_quota", "unknown"),
    }
