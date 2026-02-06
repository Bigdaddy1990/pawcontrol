"""Router for external push updates (Webhook/MQTT)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .runtime_data import get_runtime_data
from .schemas import validate_gps_push_payload

_LOGGER = logging.getLogger(__name__)


async def async_process_gps_push(
  hass: HomeAssistant,
  entry: ConfigEntry,
  payload: dict[str, Any],
  source: str,
  raw_size: int = 0,
) -> dict[str, Any]:
  """Process incoming GPS data."""

  try:
    data = validate_gps_push_payload(payload)
  except ValueError as err:
    _LOGGER.warning("Invalid %s push payload: %s", source, err)
    return {"ok": False, "error": str(err), "status": 400}

  dog_id = data["dog_id"]

  runtime_data = get_runtime_data(hass, entry)
  if not runtime_data or not runtime_data.coordinator:
    return {"ok": False, "error": "Integration not ready", "status": 503}

  if not any(dog.get("dog_id") == dog_id for dog in runtime_data.dogs):
    return {"ok": False, "error": "Unknown dog_id", "status": 404}

  if runtime_data.gps_geofence_manager:
    await runtime_data.gps_geofence_manager.async_update_location(
      dog_id,
      latitude=data["latitude"],
      longitude=data["longitude"],
      battery=data.get("battery"),
      accuracy=data.get("accuracy"),
      source=source,
    )

  return {"ok": True, "dog_id": dog_id}
