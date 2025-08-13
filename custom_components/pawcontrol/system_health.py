from __future__ import annotations

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    register.async_register_info(DOMAIN, async_system_health_info)


async def async_system_health_info(hass: HomeAssistant):
    data = hass.data.get(DOMAIN) or {}
    version = data.get("version") if isinstance(data, dict) else None
    return {
        "version": version or "unknown",
        "entries": len((data or {}).keys()) if isinstance(data, dict) else 0,
    }
