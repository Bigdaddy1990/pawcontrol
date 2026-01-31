"""Webhook endpoints for PawControl push updates (e.g., GPS tracker push).

This enables a real push path without relying on periodic polling.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, cast

from homeassistant.components.webhook import async_register, async_unregister
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import (
  CONF_DOGS,
  CONF_GPS_SOURCE,
  CONF_WEBHOOK_ENABLED,
  CONF_WEBHOOK_ID,
  CONF_WEBHOOK_REQUIRE_SIGNATURE,
  CONF_WEBHOOK_SECRET,
  DEFAULT_WEBHOOK_ENABLED,
  DEFAULT_WEBHOOK_REQUIRE_SIGNATURE,
  DOMAIN,
)
from .push_router import async_process_gps_push
from .webhook_security import WebhookSecurityManager

_LOGGER = logging.getLogger(__name__)


def _any_dog_expects_webhook(entry: ConfigEntry) -> bool:
  dogs = entry.data.get(CONF_DOGS, [])
  if not isinstance(dogs, list):
    return False
  for dog in dogs:
    if not isinstance(dog, dict):
      continue
    gps_cfg = dog.get("gps_config")
    if isinstance(gps_cfg, dict) and gps_cfg.get(CONF_GPS_SOURCE) == "webhook":
      return True
  return False

WEBHOOK_NAME = "PawControl Push Endpoint"


def _new_webhook_id() -> str:
  # Home Assistant webhook_id is opaque; keep it URL-safe.
  import secrets

  return secrets.token_urlsafe(24)


def _new_webhook_secret() -> str:
  import secrets

  # This is used for HMAC signing/verification in WebhookSecurityManager.
  return secrets.token_urlsafe(32)


async def async_ensure_webhook_config(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Ensure the config entry has webhook credentials when push is enabled."""
  enabled = bool(entry.options.get(CONF_WEBHOOK_ENABLED, DEFAULT_WEBHOOK_ENABLED))

  # Only create/maintain webhook credentials when at least one dog uses webhook AND webhook is enabled.
  if not enabled or not _any_dog_expects_webhook(entry):
    return

  webhook_id = entry.options.get(CONF_WEBHOOK_ID)
  secret = entry.options.get(CONF_WEBHOOK_SECRET)

  if isinstance(webhook_id, str) and webhook_id and isinstance(secret, str) and secret:
    return

  new_options = dict(entry.options)
  new_options[CONF_WEBHOOK_ID] = webhook_id if isinstance(webhook_id, str) and webhook_id else _new_webhook_id()
  new_options[CONF_WEBHOOK_SECRET] = secret if isinstance(secret, str) and secret else _new_webhook_secret()
  new_options.setdefault(CONF_WEBHOOK_REQUIRE_SIGNATURE, DEFAULT_WEBHOOK_REQUIRE_SIGNATURE)

  hass.config_entries.async_update_entry(entry, options=new_options)
  _LOGGER.info("Generated webhook credentials for PawControl entry %s", entry.entry_id)


async def async_register_entry_webhook(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Register the push webhook endpoint for a config entry when enabled."""
  await async_ensure_webhook_config(hass, entry)  enabled = bool(entry.options.get(CONF_WEBHOOK_ENABLED, DEFAULT_WEBHOOK_ENABLED))
  webhook_id = entry.options.get(CONF_WEBHOOK_ID)  if not enabled or not _any_dog_expects_webhook(entry):
    return
  if not isinstance(webhook_id, str) or not webhook_id:
    return

  # Idempotency: unregister first if it exists (safe no-op if not registered).
  try:
    async_unregister(hass, webhook_id)
  except Exception:  # pragma: no cover
    # Older HA versions or differing behavior: ignore.
    pass

  async_register(hass, DOMAIN, WEBHOOK_NAME, webhook_id, _handle_webhook)
  url = get_entry_webhook_url(hass, entry)
  if url:
    _LOGGER.info("PawControl webhook URL for entry %s: %s", entry.entry_id, url)
  _LOGGER.debug("Registered PawControl webhook %s for entry %s", webhook_id, entry.entry_id)


async def async_unregister_entry_webhook(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Unregister the push webhook endpoint for a config entry."""
  webhook_id = entry.options.get(CONF_WEBHOOK_ID)
  if not isinstance(webhook_id, str) or not webhook_id:
    return

  try:
    async_unregister(hass, webhook_id)
  except Exception:  # pragma: no cover
    _LOGGER.debug("Webhook %s was not registered (or already removed)", webhook_id)


def get_entry_webhook_url(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
  """Return the full webhook URL for this entry when available."""
  webhook_id = entry.options.get(CONF_WEBHOOK_ID)
  if not isinstance(webhook_id, str) or not webhook_id:
    return None

  # This helper exists in the webhook component.
  from homeassistant.components.webhook import async_generate_url

  return async_generate_url(hass, webhook_id)


async def _handle_webhook(hass: HomeAssistant, webhook_id: str, request: Any) -> Any:
  """Handle inbound webhook requests.

  Expected JSON payload:
    {
      "dog_id": "dino",
      "latitude": 52.52,
      "longitude": 13.405,
      "altitude": 34.0,
      "accuracy": 15.2,
      "timestamp": "2026-01-29T12:34:56Z"
    }
  """
  # Read raw body once (we need it for HMAC verification and JSON parse)
  raw = await request.read()
  headers: Mapping[str, str] = request.headers

  # Resolve which entry owns this webhook_id
  entry = _resolve_entry_for_webhook_id(hass, webhook_id)
  if entry is None:
    return _json_response({"ok": False, "error": "unknown_webhook"}, status=404)

  require_sig = bool(entry.options.get(CONF_WEBHOOK_REQUIRE_SIGNATURE, DEFAULT_WEBHOOK_REQUIRE_SIGNATURE))
  secret = entry.options.get(CONF_WEBHOOK_SECRET)

  if require_sig:
    if not isinstance(secret, str) or not secret:
      return _json_response({"ok": False, "error": "webhook_not_configured"}, status=400)

    manager = WebhookSecurityManager(secret)
    signature = manager.extract_signature(headers)
    if signature is None:
      return _json_response({"ok": False, "error": "missing_signature"}, status=401)

    if not manager.verify(raw, signature):
      return _json_response({"ok": False, "error": "invalid_signature"}, status=401)

  try:
    payload = json.loads(raw.decode("utf-8"))
  except Exception:
    return _json_response({"ok": False, "error": "invalid_json"}, status=400)

  if not isinstance(payload, dict):
    return _json_response({"ok": False, "error": "invalid_payload"}, status=400)

  nonce = None
  if isinstance(payload.get("nonce"), str) and payload.get("nonce"):
    nonce = cast(str, payload.get("nonce"))

  result = await async_process_gps_push(
    hass,
    entry,
    cast(Mapping[str, Any], payload),
    source="webhook",
    raw_size=len(raw),
    nonce=nonce,
  )

  if result.get("ok"):
    return _json_response({"ok": True, "dog_id": result.get("dog_id")})

  status = int(result.get("status", 400))
  error = result.get("error") or "rejected"
  body: dict[str, Any] = {"ok": False, "error": error}
  if "dog_id" in result:
    body["dog_id"] = result["dog_id"]
  return _json_response(body, status=status)



def _resolve_entry_for_webhook_id(hass: HomeAssistant, webhook_id: str) -> ConfigEntry | None:
  """Resolve a config entry by webhook id using config entries registry."""
  for entry in hass.config_entries.async_entries(DOMAIN):
    if entry.options.get(CONF_WEBHOOK_ID) == webhook_id:
      return entry
  return None



def _json_response(payload: dict[str, Any], *, status: int = 200) -> Any:
  # Avoid importing aiohttp at import-time for type-checkers; Home Assistant already uses it.
  from aiohttp import web

  return web.json_response(payload, status=status)
