"""MQTT transport for PawControl GPS push updates.

This module subscribes to an MQTT topic and forwards JSON payloads to the
unified push router. It is intentionally transport-only: validation and
strict per-dog source matching happens in push_router.py.
"""

import json
import logging
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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
    store = hass.data.setdefault(DOMAIN, {})  # noqa: E111
    if not isinstance(store, dict):  # noqa: E111
        hass.data[DOMAIN] = {}
        store = hass.data[DOMAIN]
    return cast(dict[str, Any], store)  # noqa: E111


def _any_dog_expects_mqtt(entry: ConfigEntry) -> bool:
    dogs = entry.data.get(CONF_DOGS, [])  # noqa: E111
    if not isinstance(dogs, list):  # noqa: E111
        return False
    for dog in dogs:  # noqa: E111
        if not isinstance(dog, dict):
            continue  # noqa: E111
        gps_cfg = dog.get("gps_config")
        if isinstance(gps_cfg, dict) and gps_cfg.get(CONF_GPS_SOURCE) == "mqtt":
            return True  # noqa: E111
    return False  # noqa: E111


async def async_register_entry_mqtt(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Subscribe to MQTT topic for this entry when enabled and needed."""  # noqa: E111
    enabled = bool(entry.options.get(CONF_MQTT_ENABLED, DEFAULT_MQTT_ENABLED))  # noqa: E111
    if not enabled:  # noqa: E111
        return
    if not _any_dog_expects_mqtt(entry):  # noqa: E111
        return

    topic_raw = entry.options.get(CONF_MQTT_TOPIC, DEFAULT_MQTT_TOPIC)  # noqa: E111
    topic = (  # noqa: E111
        topic_raw.strip()
        if isinstance(topic_raw, str) and topic_raw.strip()
        else DEFAULT_MQTT_TOPIC
    )

    try:  # noqa: E111
        from homeassistant.components import mqtt as ha_mqtt
    except Exception:  # noqa: E111
        _LOGGER.debug("MQTT integration not available; skipping MQTT push subscribe")
        return

    store = _domain_store(hass)  # noqa: E111
    mqtt_store = store.setdefault(_MQTT_STORE_KEY, {})  # noqa: E111
    if not isinstance(mqtt_store, dict):  # noqa: E111
        store[_MQTT_STORE_KEY] = {}
        mqtt_store = store[_MQTT_STORE_KEY]

    # Unsubscribe existing (idempotent)  # noqa: E114
    await async_unregister_entry_mqtt(hass, entry)  # noqa: E111

    async def _callback(msg: Any) -> None:  # noqa: E111
        try:
            payload_bytes = msg.payload if hasattr(msg, "payload") else None  # noqa: E111
            if isinstance(payload_bytes, (bytes, bytearray)):  # noqa: E111
                raw = bytes(payload_bytes)
            elif isinstance(msg.payload, str):  # noqa: E111
                raw = msg.payload.encode("utf-8")
            else:  # noqa: E111
                raw = b""

            payload_obj = json.loads(raw.decode("utf-8"))  # noqa: E111
            if not isinstance(payload_obj, dict):  # noqa: E111
                return
        except Exception as err:
            _LOGGER.debug("Invalid MQTT payload on %s: %s", topic, err)  # noqa: E111
            return  # noqa: E111

        nonce = None
        if isinstance(payload_obj.get("nonce"), str):
            nonce = payload_obj["nonce"]  # noqa: E111

        await async_process_gps_push(
            hass,
            entry,
            cast(dict[str, Any], payload_obj),
            source="mqtt",
            raw_size=len(raw),
            nonce=nonce,
        )

    try:  # noqa: E111
        unsub = await ha_mqtt.async_subscribe(hass, topic, _callback, qos=0)
    except Exception as err:  # noqa: E111
        _LOGGER.warning("Failed to subscribe MQTT topic %s: %s", topic, err)
        return

    mqtt_store[entry.entry_id] = unsub  # noqa: E111
    _LOGGER.debug("Subscribed MQTT push topic %s for entry %s", topic, entry.entry_id)  # noqa: E111


async def async_unregister_entry_mqtt(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Unsubscribe MQTT push topic for this entry."""  # noqa: E111
    store = _domain_store(hass)  # noqa: E111
    mqtt_store = store.get(_MQTT_STORE_KEY)  # noqa: E111
    if not isinstance(mqtt_store, dict):  # noqa: E111
        return
    unsub = mqtt_store.pop(entry.entry_id, None)  # noqa: E111
    if callable(unsub):  # noqa: E111
        try:
            result = unsub()  # noqa: E111
            # Some HA versions return awaitable  # noqa: E114
            if hasattr(result, "__await__"):  # noqa: E111
                await result
        except Exception:  # pragma: no cover
            _LOGGER.debug("MQTT unsubscribe failed for entry %s", entry.entry_id)  # noqa: E111
