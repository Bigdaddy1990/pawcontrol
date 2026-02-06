"""MQTT transport for PawControl GPS push updates.

This module subscribes to an MQTT topic and forwards JSON payloads to the
unified push router. It is intentionally transport-only: validation and
strict per-dog source matching happens in push_router.py.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant

from .compat import ConfigEntry
from .const import (
  CONF_DOGS,
  CONF_GPS_SOURCE,
  CONF_MQTT_ENABLED,
  CONF_MQTT_TOPIC,
  DEFAULT_MQTT_ENABLED,
  DEFAULT_MQTT_TOPIC,
  DOMAIN,
)
from .push_router import async_process_gps_push

_LOGGER = logging.getLogger(__name__)

_MQTT_STORE_KEY = "_mqtt_push"


def _domain_store(hass: HomeAssistant) -> dict[str, Any]:
  store = hass.data.setdefault(DOMAIN, {})
  if not isinstance(store, dict):
    hass.data[DOMAIN] = {}
    store = hass.data[DOMAIN]
  return cast(dict[str, Any], store)


def _any_dog_expects_mqtt(entry: ConfigEntry) -> bool:
  dogs = entry.data.get(CONF_DOGS, [])
  if not isinstance(dogs, list):
    return False
  for dog in dogs:
    if not isinstance(dog, dict):
      continue
    gps_cfg = dog.get("gps_config")
    if isinstance(gps_cfg, dict) and gps_cfg.get(CONF_GPS_SOURCE) == "mqtt":
      return True
  return False


async def async_register_entry_mqtt(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Subscribe to MQTT topic for this entry when enabled and needed."""
  enabled = bool(entry.options.get(CONF_MQTT_ENABLED, DEFAULT_MQTT_ENABLED))
  if not enabled:
    return
  if not _any_dog_expects_mqtt(entry):
    return

  topic_raw = entry.options.get(CONF_MQTT_TOPIC, DEFAULT_MQTT_TOPIC)
  topic = (
    topic_raw.strip()
    if isinstance(topic_raw, str) and topic_raw.strip()
    else DEFAULT_MQTT_TOPIC
  )

  try:
    from homeassistant.components import mqtt as ha_mqtt
  except Exception:
    _LOGGER.debug("MQTT integration not available; skipping MQTT push subscribe")
    return

  store = _domain_store(hass)
  mqtt_store = store.setdefault(_MQTT_STORE_KEY, {})
  if not isinstance(mqtt_store, dict):
    store[_MQTT_STORE_KEY] = {}
    mqtt_store = store[_MQTT_STORE_KEY]

  # Unsubscribe existing (idempotent)
  await async_unregister_entry_mqtt(hass, entry)

  async def _callback(msg: Any) -> None:
    try:
      payload_bytes = msg.payload if hasattr(msg, "payload") else None
      if isinstance(payload_bytes, (bytes, bytearray)):
        raw = bytes(payload_bytes)
      elif isinstance(msg.payload, str):
        raw = msg.payload.encode("utf-8")
      else:
        raw = b""

      payload_obj = json.loads(raw.decode("utf-8"))
      if not isinstance(payload_obj, dict):
        return
    except Exception as err:
      _LOGGER.debug("Invalid MQTT payload on %s: %s", topic, err)
      return

    nonce = None
    if isinstance(payload_obj.get("nonce"), str):
      nonce = payload_obj["nonce"]

    await async_process_gps_push(
      hass,
      entry,
      cast(dict[str, Any], payload_obj),
      source="mqtt",
      raw_size=len(raw),
      nonce=nonce,
    )

  try:
    unsub = await ha_mqtt.async_subscribe(hass, topic, _callback, qos=0)
  except Exception as err:
    _LOGGER.warning("Failed to subscribe MQTT topic %s: %s", topic, err)
    return

  mqtt_store[entry.entry_id] = unsub
  _LOGGER.debug("Subscribed MQTT push topic %s for entry %s", topic, entry.entry_id)


async def async_unregister_entry_mqtt(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Unsubscribe MQTT push topic for this entry."""
  store = _domain_store(hass)
  mqtt_store = store.get(_MQTT_STORE_KEY)
  if not isinstance(mqtt_store, dict):
    return
  unsub = mqtt_store.pop(entry.entry_id, None)
  if callable(unsub):
    try:
      result = unsub()
      # Some HA versions return awaitable
      if hasattr(result, "__await__"):
        await result
    except Exception:  # pragma: no cover
      _LOGGER.debug("MQTT unsubscribe failed for entry %s", entry.entry_id)
