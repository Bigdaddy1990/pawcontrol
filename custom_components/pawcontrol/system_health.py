"""System health support for PawControl."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .runtime_data import get_runtime_data


@callback
def async_register(
  hass: HomeAssistant,
  register: system_health.SystemHealthRegistration,
) -> None:
  """Register system health callbacks."""
  register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
  """Get info for the info page."""
  entry = next(iter(hass.config_entries.async_entries(DOMAIN)), None)

  status: dict[str, Any] = {
    "integration_loaded": entry is not None,
  }

  if entry:
    runtime_data = get_runtime_data(hass, entry)
    coordinator = runtime_data.coordinator if runtime_data else None

    status["coordinator_active"] = coordinator is not None
    status["api_connected"] = coordinator.last_update_success if coordinator else False

    if coordinator and coordinator.last_exception:
      status["last_error"] = str(coordinator.last_exception)

  return status
