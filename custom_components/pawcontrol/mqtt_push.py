"""MQTT transport for PawControl GPS push updates.

Simplified to use standard HA MQTT subscription helpers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .config_entry_helpers import get_entry_dogs
from .const import (
  CONF_GPS_SOURCE,
  CONF_MQTT_ENABLED,
  CONF_MQTT_TOPIC,
  DEFAULT_MQTT_ENABLED,
  DEFAULT_MQTT_TOPIC,
)
from .push_router import async_process_gps_push

_LOGGER = logging.getLogger(__name__)


def _any_dog_expects_mqtt(entry: ConfigEntry) -> bool:
  dogs = get_entry_dogs(entry)
  if not isinstance(dogs, list):
    return False

  for dog in dogs:
    if isinstance(dog, dict):
      gps_cfg = dog.get("gps_config")
      if isinstance(gps_cfg, dict) and gps_cfg.get(CONF_GPS_SOURCE) == "mqtt":
        return True

  return False


async def async_register_entry_mqtt(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Subscribe to MQTT if enabled."""
  if not entry.options.get(CONF_MQTT_ENABLED, DEFAULT_MQTT_ENABLED):
    return

  if not _any_dog_expects_mqtt(entry):
    return

  topic = entry.options.get(CONF_MQTT_TOPIC, DEFAULT_MQTT_TOPIC)

  if not await mqtt.async_wait_for_mqtt_client(hass):
    _LOGGER.debug("MQTT integration not available/ready")
    return

  @callback
  async def _mqtt_callback(msg: Any) -> None:
    try:
      payload = json.loads(msg.payload)
      if not isinstance(payload, dict):
        return
    except (ValueError, TypeError):
      _LOGGER.warning("Received invalid JSON on PawControl MQTT topic")
      return

    await async_process_gps_push(
      hass,
      entry,
      payload,
      source="mqtt",
      raw_size=len(msg.payload),
    )

  try:
    unsub = await mqtt.async_subscribe(hass, topic, _mqtt_callback)
    entry.async_on_unload(unsub)
    _LOGGER.debug("Subscribed to PawControl MQTT topic: %s", topic)
  except Exception as err:
    _LOGGER.error("Failed to subscribe to MQTT topic %s: %s", topic, err)


async def async_unregister_entry_mqtt(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """No-op: Unsubscription is handled by async_on_unload."""
  return None
