"""System health support for the PawControl integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks for PawControl."""

    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return basic system health information."""

    entry = next(iter(hass.config_entries.async_entries(DOMAIN)), None)
    runtime = getattr(entry, "runtime_data", None) if entry else None
    api = getattr(runtime, "api", None) if runtime else None
    base_url = getattr(api, "base_url", "https://example.invalid")
    can_reach_backend = await system_health.async_check_can_reach_url(hass, base_url)
    return {
        "can_reach_backend": can_reach_backend,
        "remaining_quota": getattr(runtime, "remaining_quota", "unknown"),
    }
