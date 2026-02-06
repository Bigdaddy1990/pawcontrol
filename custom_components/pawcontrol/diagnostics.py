"""Diagnostics support for PawControl."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant

from homeassistant.config_entries import ConfigEntry
from .const import CONF_API_ENDPOINT, CONF_API_TOKEN, CONF_DOGS
from .runtime_data import get_runtime_data

TO_REDACT = {
  CONF_API_KEY,
  CONF_PASSWORD,
  CONF_TOKEN,
  CONF_USERNAME,
  CONF_API_ENDPOINT,
  CONF_API_TOKEN,
  "unique_id",
  "serial_number",
  "latitude",
  "longitude",
  "mac_address",
  "webhook_id",
  "webhook_secret",
}


async def async_get_config_entry_diagnostics(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> dict[str, Any]:
  """Return diagnostics for a config entry."""
  runtime_data = get_runtime_data(hass, entry)
  coordinator = runtime_data.coordinator if runtime_data else None

  diagnostics_data: dict[str, Any] = {
    "entry": {
      "title": entry.title,
      "domain": entry.domain,
      "version": entry.version,
      "data": dict(entry.data),
      "options": dict(entry.options),
    },
    "coordinator": {
      "available": coordinator.available if coordinator else False,
      "last_update_success": coordinator.last_update_success if coordinator else False,
      "last_update_time": (
        coordinator.last_update_time.isoformat()
        if coordinator and coordinator.last_update_time
        else None
      ),
    },
    "dogs": _get_dogs_diagnostics(entry),
  }

  if runtime_data:
    diagnostics_data["runtime"] = {
      "profile": runtime_data.entity_profile,
      "dog_count": len(runtime_data.dogs),
    }

  return async_redact_data(diagnostics_data, TO_REDACT)


def _get_dogs_diagnostics(entry: ConfigEntry) -> list[dict[str, Any]]:
  """Extract dog configuration summary."""
  dogs = entry.data.get(CONF_DOGS, [])
  if not isinstance(dogs, list):
    return []

  summary: list[dict[str, Any]] = []
  for dog in dogs:
    if not isinstance(dog, dict):
      continue
    summary.append(
      {
        "has_gps": bool(dog.get("gps_config")),
        "modules": dog.get("modules", {}),
      },
    )
  return summary
