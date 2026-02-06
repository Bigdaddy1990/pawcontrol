"""Webhook endpoints for PawControl push updates.

Standard Home Assistant webhook implementation.
"""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.webhook import (
  async_generate_url,
  async_register,
  async_unregister,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_flow

from .const import (
  CONF_DOGS,
  CONF_GPS_SOURCE,
  CONF_WEBHOOK_ENABLED,
  CONF_WEBHOOK_ID,
  DEFAULT_WEBHOOK_ENABLED,
  DOMAIN,
)
from .push_router import async_process_gps_push

_LOGGER = logging.getLogger(__name__)

WEBHOOK_NAME = "PawControl Push Endpoint"


def _any_dog_expects_webhook(entry: ConfigEntry) -> bool:
  dogs = entry.data.get(CONF_DOGS, [])
  if not isinstance(dogs, list):
    return False

  for dog in dogs:
    if isinstance(dog, dict):
      gps_cfg = dog.get("gps_config")
      if isinstance(gps_cfg, dict) and gps_cfg.get(CONF_GPS_SOURCE) == "webhook":
        return True

  return False


async def async_ensure_webhook_config(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Ensure config entry has a webhook ID."""
  if entry.options.get(CONF_WEBHOOK_ID):
    return

  webhook_id = config_entry_flow.webhook.async_generate_id()
  new_options = dict(entry.options)
  new_options[CONF_WEBHOOK_ID] = webhook_id
  hass.config_entries.async_update_entry(entry, options=new_options)


async def async_register_entry_webhook(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Register the webhook if enabled."""
  await async_ensure_webhook_config(hass, entry)

  enabled = entry.options.get(CONF_WEBHOOK_ENABLED, DEFAULT_WEBHOOK_ENABLED)
  webhook_id = entry.options.get(CONF_WEBHOOK_ID)

  if not enabled or not webhook_id or not _any_dog_expects_webhook(entry):
    return

  async_register(hass, DOMAIN, WEBHOOK_NAME, webhook_id, _handle_webhook)
  entry.async_on_unload(lambda: async_unregister(hass, webhook_id))

  _LOGGER.debug(
    "Registered PawControl webhook: %s", async_generate_url(hass, webhook_id)
  )


async def async_unregister_entry_webhook(
  hass: HomeAssistant, entry: ConfigEntry
) -> None:
  """Unregister the webhook."""
  webhook_id = entry.options.get(CONF_WEBHOOK_ID)
  if webhook_id:
    async_unregister(hass, webhook_id)


async def _handle_webhook(
  hass: HomeAssistant,
  webhook_id: str,
  request: web.Request,
) -> web.Response:
  """Handle incoming webhook data."""
  try:
    data = await request.json()
  except ValueError:
    return web.json_response({"error": "Invalid JSON"}, status=400)

  if not isinstance(data, dict):
    return web.json_response({"error": "Payload must be a dictionary"}, status=400)

  entry = next(
    (
      config_entry
      for config_entry in hass.config_entries.async_entries(DOMAIN)
      if config_entry.options.get(CONF_WEBHOOK_ID) == webhook_id
    ),
    None,
  )

  if not entry:
    return web.json_response({"error": "Config entry not found"}, status=404)

  result = await async_process_gps_push(
    hass,
    entry,
    data,
    source="webhook",
    raw_size=request.content_length or 0,
  )

  if result.get("ok"):
    return web.json_response({"status": "ok", "dog_id": result.get("dog_id")})

  return web.json_response(
    {"error": result.get("error", "Unknown error")},
    status=result.get("status", 400),
  )


def get_entry_webhook_url(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
  """Get the public URL for the webhook."""
  webhook_id = entry.options.get(CONF_WEBHOOK_ID)
  if webhook_id:
    return async_generate_url(hass, webhook_id)

  return None
