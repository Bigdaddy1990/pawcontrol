"""Router for external push updates (Webhook/MQTT)."""

from __future__ import annotations

from collections import deque
import json
import logging
import time
from collections.abc import Mapping, MutableMapping
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .config_entry_helpers import get_entry_dogs
from .const import (
  CONF_DOG_ID,
  CONF_GPS_SOURCE,
  CONF_PUSH_NONCE_TTL_SECONDS,
  CONF_PUSH_PAYLOAD_MAX_BYTES,
  CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
  CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
  CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
  DEFAULT_PUSH_NONCE_TTL_SECONDS,
  DEFAULT_PUSH_PAYLOAD_MAX_BYTES,
  DEFAULT_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
  DEFAULT_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
  DEFAULT_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
  DOMAIN,
)
from .runtime_data import get_runtime_data
from .schemas import validate_gps_push_payload

_LOGGER = logging.getLogger(__name__)

_ROUTER_STORE_KEY = "push_router"


class _RateLimiter:
  """Simple per-minute rate limiter."""

  def __init__(self, limit_per_minute: int) -> None:
    self.limit_per_minute = max(limit_per_minute, 0)
    self._timestamps: deque[float] = deque()

  def update_limit(self, limit_per_minute: int) -> None:
    self.limit_per_minute = max(limit_per_minute, 0)

  def allow(self, now: float) -> bool:
    if self.limit_per_minute <= 0:
      return True

    window_start = now - 60.0
    while self._timestamps and self._timestamps[0] <= window_start:
      self._timestamps.popleft()

    if len(self._timestamps) >= self.limit_per_minute:
      return False

    self._timestamps.append(now)
    return True


def _get_router_store(hass: HomeAssistant) -> MutableMapping[str, dict[str, Any]]:
  domain_store = hass.data.setdefault(DOMAIN, {})
  router_store = domain_store.setdefault(_ROUTER_STORE_KEY, {})
  return router_store


def _ensure_entry_state(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
  store = _get_router_store(hass)
  state = store.get(entry_id)
  if not isinstance(state, dict):
    state = {}
    store[entry_id] = state

  if "telemetry" not in state:
    state["telemetry"] = {
      "created_at": dt_util.utcnow().isoformat(),
      "dogs": {},
    }
  state.setdefault("nonces", {})
  state.setdefault("rate_limits", {})
  return state


def _get_entry_settings(entry: ConfigEntry) -> Mapping[str, Any]:
  options = entry.options
  if isinstance(options, Mapping):
    push_settings = options.get("push_settings")
    if isinstance(push_settings, Mapping):
      merged = dict(options)
      merged.update(push_settings)
      return merged
    return options
  return {}


def _coerce_int(value: object | None, default: int, *, allow_zero: bool) -> int:
  if value is None or isinstance(value, bool):
    return default
  try:
    parsed = int(value)
  except (TypeError, ValueError):
    return default
  if parsed < 0 or (parsed == 0 and not allow_zero):
    return default
  return parsed


def _payload_size(payload: Mapping[str, Any], raw_size: int) -> int:
  if raw_size > 0:
    return raw_size
  try:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
  except (TypeError, ValueError):  # pragma: no cover - defensive guard
    return 0


def _lookup_dog_source(entry: ConfigEntry, dog_id: str) -> str | None:
  dogs = get_entry_dogs(entry)
  if not isinstance(dogs, list):
    return None
  for dog in dogs:
    if not isinstance(dog, Mapping):
      continue
    if dog.get(CONF_DOG_ID) != dog_id:
      continue
    gps_cfg = dog.get("gps_config")
    if isinstance(gps_cfg, Mapping):
      return cast(str | None, gps_cfg.get(CONF_GPS_SOURCE))
    return None
  return None


def _get_rate_limiter(
  state: dict[str, Any],
  key: str,
  limit_per_minute: int,
) -> _RateLimiter:
  rate_limits = state.setdefault("rate_limits", {})
  limiter = rate_limits.get(key)
  if not isinstance(limiter, _RateLimiter):
    limiter = _RateLimiter(limit_per_minute)
    rate_limits[key] = limiter
  else:
    limiter.update_limit(limit_per_minute)
  return limiter


def _record_rejection(
  state: dict[str, Any],
  dog_id: str | None,
  reason: str,
  *,
  source: str,
) -> None:
  telemetry = state.get("telemetry", {})
  dogs = telemetry.get("dogs")
  if not isinstance(dogs, MutableMapping) or not dog_id:
    return
  dog_entry = dogs.setdefault(dog_id, {})
  rejected_total = int(dog_entry.get("rejected_total", 0)) + 1
  dog_entry["rejected_total"] = rejected_total
  dog_entry["last_rejection"] = dt_util.utcnow().isoformat()
  dog_entry["last_rejection_reason"] = reason
  dog_entry["last_rejection_source"] = source


def _record_accept(
  state: dict[str, Any],
  dog_id: str,
  *,
  source: str,
) -> None:
  telemetry = state.get("telemetry", {})
  dogs = telemetry.get("dogs")
  if not isinstance(dogs, MutableMapping):
    return
  dog_entry = dogs.setdefault(dog_id, {})
  accepted_total = int(dog_entry.get("accepted_total", 0)) + 1
  dog_entry["accepted_total"] = accepted_total
  dog_entry["last_accepted"] = dt_util.utcnow().isoformat()
  dog_entry["last_source"] = source


def get_entry_push_telemetry_snapshot(
  hass: HomeAssistant,
  entry_id: str,
) -> dict[str, Any]:
  """Return a copy of the push telemetry snapshot for an entry."""

  state = _ensure_entry_state(hass, entry_id)
  telemetry = state.get("telemetry")
  if not isinstance(telemetry, Mapping):
    return {"created_at": None, "dogs": {}}

  dogs = telemetry.get("dogs")
  return {
    "created_at": telemetry.get("created_at"),
    "dogs": dict(dogs) if isinstance(dogs, Mapping) else {},
  }


async def async_process_gps_push(
  hass: HomeAssistant,
  entry: ConfigEntry,
  payload: dict[str, Any],
  source: str,
  raw_size: int = 0,
) -> dict[str, Any]:
  """Process incoming GPS data."""

  state = _ensure_entry_state(hass, entry.entry_id)
  settings = _get_entry_settings(entry)

  payload_limit = _coerce_int(
    settings.get(CONF_PUSH_PAYLOAD_MAX_BYTES),
    DEFAULT_PUSH_PAYLOAD_MAX_BYTES,
    allow_zero=True,
  )
  size = _payload_size(payload, raw_size)
  if payload_limit > 0 and size > payload_limit:
    _record_rejection(state, None, "payload_too_large", source=source)
    return {
      "ok": False,
      "error": "Payload too large",
      "status": 413,
    }

  try:
    data = validate_gps_push_payload(payload)
  except ValueError as err:
    _LOGGER.warning("Invalid %s push payload: %s", source, err)
    _record_rejection(state, None, "invalid_payload", source=source)
    return {"ok": False, "error": str(err), "status": 400}

  dog_id = data["dog_id"]
  expected_source = _lookup_dog_source(entry, dog_id)
  if expected_source and expected_source != source:
    _record_rejection(state, dog_id, "source_mismatch", source=source)
    return {"ok": False, "error": "Source mismatch", "status": 403}

  runtime_data = get_runtime_data(hass, entry)
  if not runtime_data or not runtime_data.coordinator:
    _record_rejection(state, dog_id, "integration_not_ready", source=source)
    return {"ok": False, "error": "Integration not ready", "status": 503}

  if not any(dog.get(CONF_DOG_ID) == dog_id for dog in runtime_data.dogs):
    _record_rejection(state, dog_id, "unknown_dog_id", source=source)
    return {"ok": False, "error": "Unknown dog_id", "status": 404}

  nonce_ttl = _coerce_int(
    settings.get(CONF_PUSH_NONCE_TTL_SECONDS),
    DEFAULT_PUSH_NONCE_TTL_SECONDS,
    allow_zero=True,
  )
  if nonce_ttl > 0:
    nonce = data.get("nonce")
    if not nonce:
      _record_rejection(state, dog_id, "missing_nonce", source=source)
      return {"ok": False, "error": "Missing nonce", "status": 400}

    nonces = state.setdefault("nonces", {})
    if not isinstance(nonces, MutableMapping):
      nonces = {}
      state["nonces"] = nonces
    now = time.monotonic()
    expired_before = now - float(nonce_ttl)
    for key, ts in list(nonces.items()):
      if not isinstance(ts, (int, float)) or ts <= expired_before:
        nonces.pop(key, None)
    if nonce in nonces:
      _record_rejection(state, dog_id, "replay_nonce", source=source)
      return {"ok": False, "error": "Nonce already used", "status": 409}
    nonces[str(nonce)] = now

  now = time.monotonic()
  per_entity_limit = _coerce_int(
    settings.get(CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE),
    DEFAULT_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
    allow_zero=True,
  )
  per_source_limit = _coerce_int(
    settings.get(
      CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE
      if source == "webhook"
      else CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE
    ),
    DEFAULT_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE
    if source == "webhook"
    else DEFAULT_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
    allow_zero=True,
  )

  if per_source_limit > 0:
    limiter = _get_rate_limiter(state, f"source:{source}", per_source_limit)
    if not limiter.allow(now):
      _record_rejection(state, dog_id, "rate_limited_source", source=source)
      return {"ok": False, "error": "Rate limit exceeded", "status": 429}

  if per_entity_limit > 0:
    limiter = _get_rate_limiter(state, f"dog:{dog_id}", per_entity_limit)
    if not limiter.allow(now):
      _record_rejection(state, dog_id, "rate_limited_dog", source=source)
      return {"ok": False, "error": "Rate limit exceeded", "status": 429}

  if runtime_data.gps_geofence_manager:
    await runtime_data.gps_geofence_manager.async_update_location(
      dog_id,
      latitude=data["latitude"],
      longitude=data["longitude"],
      battery=data.get("battery"),
      accuracy=data.get("accuracy"),
      source=source,
    )

  _record_accept(state, dog_id, source=source)
  return {"ok": True, "dog_id": dog_id}
