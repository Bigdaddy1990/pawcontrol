from __future__ import annotations

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN


async def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    register.async_register_info(DOMAIN, async_system_health_info)


async def async_system_health_info(hass: HomeAssistant):
    integration = await async_get_integration(hass, DOMAIN)
    entries = hass.config_entries.async_entries(DOMAIN)

    return {
        "version": integration.version or "unknown",
        "entries": len(entries),
    }
