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
        return {
            "info": "No PawControl config entries found",
            "can_reach_backend": system_health.async_check_can_reach_url(hass, "http://invalid.invalid"),
            "remaining_quota": "unknown",
        }

    # Prefer an entry that has initialized runtime data
    entry = next((e for e in entries if getattr(e, "runtime_data", None)), entries[0])

    runtime = getattr(entry, "runtime_data", None)
    api = getattr(runtime, "api", None)
    if runtime is None or api is None:
        return {
            "info": "PawControl runtime data not initialized",
            "can_reach_backend": {"type": "failed", "error": "api_unavailable"},
            "remaining_quota": "unknown",
        }

    raw_base_url = getattr(api, "base_url", None)
    base_url = raw_base_url.strip().rstrip("/") if isinstance(raw_base_url, str) else None
    if not base_url or not base_url.startswith(("http://", "https://")):
        can_reach = {"type": "failed", "error": "invalid_base_url"}
    else:
        can_reach = system_health.async_check_can_reach_url(hass, base_url)

    return {
        "can_reach_backend": can_reach,
        "remaining_quota": getattr(runtime, "remaining_quota", "unknown"),
    }
