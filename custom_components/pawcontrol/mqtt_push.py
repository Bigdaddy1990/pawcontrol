"""MQTT push receiver for PawControl GPS updates.

Expects JSON payload with at least:
{
  "dog_id": "...",
  "latitude": 51.1,
  "longitude": 6.9
}

Processing is routed through :mod:`pawcontrol.push_router`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
  CONF_GPS_SOURCE,
  CONF_MQTT_ENABLED,
  CONF_MQTT_TOPIC,
  DEFAULT_MQTT_ENABLED,
  DEFAULT_MQTT_TOPIC,
  DOMAIN,
)
from .push_router import async_process_gps_push
import contextlib

_LOGGER = logging.getLogger(__name__)

_MQTT_STORE_KEY = "_mqtt"


def _store(hass: HomeAssistant) -> dict[str, Any]:
  root = hass.data.setdefault(DOMAIN, {})
  if not isinstance(root, dict):
    root = {}
    hass.data[DOMAIN] = root
  mqtt_root = root.setdefault(_MQTT_STORE_KEY, {})
  if not isinstance(mqtt_root, dict):
    mqtt_root = {}
    root[_MQTT_STORE_KEY] = mqtt_root
  return mqtt_root


async def async_register_entry_mqtt(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Register MQTT subscription for a config entry (idempotent)."""

  gps_source = entry.options.get(CONF_GPS_SOURCE)
  enabled = bool(entry.options.get(CONF_MQTT_ENABLED, DEFAULT_MQTT_ENABLED))
  if gps_source != "mqtt" or not enabled:
    await async_unregister_entry_mqtt(hass, entry)
    return

  topic = entry.options.get(CONF_MQTT_TOPIC, DEFAULT_MQTT_TOPIC)
  if not isinstance(topic, str) or not topic.strip():
    _LOGGER.warning("MQTT topic invalid for entry %s", entry.entry_id)
    return

  # Import mqtt lazily so the integration doesn't hard-require it.
  try:
    from homeassistant.components import mqtt
  except Exception:  # pragma: no cover
    _LOGGER.debug("MQTT integration not available; skipping subscription")
    return

  mqtt_store = _store(hass)

  # Unsubscribe previous subscription if present.
  prev = mqtt_store.get(entry.entry_id)
  if callable(prev):
    with contextlib.suppress(Exception):
      prev()
    mqtt_store.pop(entry.entry_id, None)

  async def _message_received(msg: Any) -> None:
    try:
      payload_raw = msg.payload
      if isinstance(payload_raw, bytes):
        raw_bytes = payload_raw
        payload_str = payload_raw.decode("utf-8")
      else:
        payload_str = str(payload_raw)
        raw_bytes = payload_str.encode("utf-8", errors="replace")

      data = json.loads(payload_str)
      if not isinstance(data, Mapping):
        return
      nonce = None
      if isinstance(data, dict):
        maybe = data.get("nonce")
        if isinstance(maybe, str) and maybe:
          nonce = maybe

      result = await async_process_gps_push(
        hass,
        entry,
        data,
        source="mqtt",
        raw_size=len(raw_bytes),
        nonce=nonce,
      )
      if not result.get("ok"):
        _LOGGER.debug("MQTT push rejected for entry %s: %s", entry.entry_id, result.get("error"))
    except Exception as err:  # pragma: no cover
      _LOGGER.debug("MQTT push payload error: %s", err)

  unsub = await mqtt.async_subscribe(hass, topic, _message_received, qos=0)
  mqtt_store[entry.entry_id] = unsub
  _LOGGER.info("MQTT GPS push subscribed for entry %s on topic %s", entry.entry_id, topic)


async def async_unregister_entry_mqtt(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Unregister MQTT subscription for a config entry (idempotent)."""
  mqtt_store = _store(hass)
  prev = mqtt_store.get(entry.entry_id)
  if callable(prev):
    with contextlib.suppress(Exception):
      prev()
  mqtt_store.pop(entry.entry_id, None)
