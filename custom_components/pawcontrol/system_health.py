"""System health support for the PawControl integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .config_flow import config_flow_monitor
from .const import CONF_DOGS, CONF_DOG_NAME, DOMAIN


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
    remaining_quota = getattr(runtime, "remaining_quota", "unknown")

    dogs: list[dict[str, Any]] = []
    profile = "standard"
    if entry:
        dogs = list(entry.data.get(CONF_DOGS, []))
        profile = entry.options.get(
            "entity_profile", entry.data.get("entity_profile", "standard")
        )

    info: dict[str, Any] = {
        "can_reach_backend": False,
        "remaining_quota": remaining_quota,
        "configured_dogs": len(dogs),
        "entity_profile": profile,
        "config_flow_operations": config_flow_monitor.get_stats(),
    }

    if dogs:
        info["dog_names"] = [dog.get(CONF_DOG_NAME, "Unknown") for dog in dogs]

    if not api or not getattr(api, "base_url", None):
        return info

    can_reach_backend = await system_health.async_check_can_reach_url(
        hass, api.base_url
    )
    info["can_reach_backend"] = can_reach_backend
    return info
