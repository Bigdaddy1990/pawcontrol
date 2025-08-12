
from __future__ import annotations

from typing import Mapping

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant

from .const import DOMAIN

async def async_register(
    hass: HomeAssistant,
    register: system_health.SystemHealthRegistration,
) -> None:
    register.async_register_info(DOMAIN, async_system_health_info)

async def async_system_health_info(
    hass: HomeAssistant,
) -> dict[str, str | int]:
    data: Mapping[str, object] | None = hass.data.get(DOMAIN)  # type: ignore[assignment]
    version = data.get("version") if isinstance(data, Mapping) else None
    return {
        "version": version or "unknown",
        "entries": len((data or {}).keys()) if isinstance(data, dict) else 0,
    }
