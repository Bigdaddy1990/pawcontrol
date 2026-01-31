"""Unified push ingestion for PawControl.

Centralizes processing of push-style GPS updates coming from webhooks, MQTT,
or other entity-driven sources. It validates payloads, enforces strict per-dog
source matching, rate-limits bursty senders, and records telemetry suitable
for diagnostics and repairs.

Telemetry is intentionally non-sensitive (no coordinates).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, TypedDict, cast

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry
from .const import (
  CONF_DOGS,
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
from .runtime_data import require_runtime_data

_LOGGER = logging.getLogger(__name__)

PushSource = Literal["webhook", "mqtt", "entity"]

_PUSH_STORE_KEY: Final[str] = "_push_router"
_MAX_REASONS: Final[int] = 25


class PushResult(TypedDict, total=False):
  ok: bool
  status: int
  error: str
  dog_id: str


@dataclass(slots=True)
class _RateLimiter:
  window_seconds: int
  max_events: int
  events: deque[float]

  def allow(self, now: float) -> bool:
    cutoff = now - self.window_seconds
    while self.events and self.events[0] < cutoff:
      self.events.popleft()
    if len(self.events) >= self.max_events:
      return False
    self.events.append(now)
    return True


def _store(hass: HomeAssistant) -> dict[str, Any]:
  store = hass.data.setdefault(DOMAIN, {})
  if not isinstance(store, dict):
    hass.data[DOMAIN] = {}
    store = hass.data[DOMAIN]
  return cast(dict[str, Any], store)


def _entry_store(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
  domain_store = _store(hass)
  router_store = domain_store.setdefault(_PUSH_STORE_KEY, {})
  if not isinstance(router_store, dict):
    domain_store[_PUSH_STORE_KEY] = {}
    router_store = domain_store[_PUSH_STORE_KEY]

  entry = router_store.setdefault(entry_id, {})
  if not isinstance(entry, dict):
    router_store[entry_id] = {}
    entry = router_store[entry_id]

  telemetry = entry.setdefault("telemetry", {})
  if not isinstance(telemetry, dict):
    entry["telemetry"] = {}
    telemetry = entry["telemetry"]

  if "created_at" not in telemetry:
    telemetry["created_at"] = dt_util.utcnow().isoformat()
    telemetry["dogs"] = {}
    telemetry["accepted_total"] = 0
    telemetry["rejected_total"] = 0

  entry.setdefault("nonces", {})
  entry.setdefault("limiters", {})
  return entry


def _dog_telemetry(telemetry: dict[str, Any], dog_id: str) -> dict[str, Any]:
  dogs = telemetry.setdefault("dogs", {})
  if not isinstance(dogs, dict):
    telemetry["dogs"] = {}
    dogs = telemetry["dogs"]
  dog = dogs.setdefault(dog_id, {})
  if not isinstance(dog, dict):
    dogs[dog_id] = {}
    dog = dogs[dog_id]

  dog.setdefault("accepted_total", 0)
  dog.setdefault("rejected_total", 0)
  dog.setdefault("last_accepted", None)
  dog.setdefault("last_rejected", None)
  dog.setdefault("last_rejection_reason", None)
  dog.setdefault("by_reason", {})
  dog.setdefault("by_source_accepted", {})
  dog.setdefault("by_source_rejected", {})
  return dog


def _bump_reason(dog_tel: dict[str, Any], reason: str) -> None:
  by_reason = dog_tel.get("by_reason")
  if not isinstance(by_reason, dict):
    by_reason = {}
    dog_tel["by_reason"] = by_reason
  by_reason[reason] = int(by_reason.get(reason, 0)) + 1

  if len(by_reason) > _MAX_REASONS:
    items = sorted(by_reason.items(), key=lambda kv: kv[1])
    for key, _ in items[: len(by_reason) - _MAX_REASONS]:
      by_reason.pop(key, None)


def get_entry_push_telemetry_snapshot(
  hass: HomeAssistant, entry_id: str
) -> dict[str, Any]:
  """Return a JSON-safe snapshot of push telemetry for diagnostics and sensors."""
  entry = _entry_store(hass, entry_id)
  telemetry = entry.get("telemetry")
  if not isinstance(telemetry, dict):
    return {}
  # shallow copy (nested dicts intentionally shared but non-sensitive)
  return {
    "created_at": telemetry.get("created_at"),
    "accepted_total": telemetry.get("accepted_total", 0),
    "rejected_total": telemetry.get("rejected_total", 0),
    "dogs": telemetry.get("dogs", {}),
  }


def _dog_expected_source(entry: ConfigEntry, dog_id: str) -> str | None:
  dogs = entry.data.get(CONF_DOGS, [])
  if not isinstance(dogs, list):
    return None
  for item in dogs:
    if not isinstance(item, Mapping):
      continue
    if item.get("dog_id") != dog_id:
      continue
    gps_cfg = item.get("gps_config")
    if isinstance(gps_cfg, Mapping):
      raw = gps_cfg.get(CONF_GPS_SOURCE)
      return raw.strip() if isinstance(raw, str) else None
    raw = item.get(CONF_GPS_SOURCE)
    return raw.strip() if isinstance(raw, str) else None
  return None


def _payload_limit(entry: ConfigEntry) -> int:
  raw = entry.options.get(CONF_PUSH_PAYLOAD_MAX_BYTES, DEFAULT_PUSH_PAYLOAD_MAX_BYTES)
  try:
    value = int(raw)
  except Exception:
    return DEFAULT_PUSH_PAYLOAD_MAX_BYTES
  return max(1024, min(256 * 1024, value))


def _nonce_ttl(entry: ConfigEntry) -> int:
  raw = entry.options.get(CONF_PUSH_NONCE_TTL_SECONDS, DEFAULT_PUSH_NONCE_TTL_SECONDS)
  try:
    value = int(raw)
  except Exception:
    return DEFAULT_PUSH_NONCE_TTL_SECONDS
  return max(60, min(24 * 3600, value))


def _rate_limit(entry: ConfigEntry, source: PushSource) -> int:
  if source == "webhook":
    raw = entry.options.get(
      CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
      DEFAULT_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
    )
  elif source == "mqtt":
    raw = entry.options.get(
      CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE, DEFAULT_PUSH_RATE_LIMIT_MQTT_PER_MINUTE
    )
  else:
    raw = entry.options.get(
      CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE, DEFAULT_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE
    )
  try:
    value = int(raw)
  except Exception:
    value = 60
  return max(1, min(600, value))


def _check_nonce(
  entry_store: dict[str, Any], entry: ConfigEntry, nonce: str, now: float
) -> bool:
  nonces = entry_store.get("nonces")
  if not isinstance(nonces, dict):
    entry_store["nonces"] = {}
    nonces = entry_store["nonces"]
  ttl = _nonce_ttl(entry)
  cutoff = now - ttl
  for key, ts in list(nonces.items()):
    if not isinstance(ts, (int, float)) or ts < cutoff:
      nonces.pop(key, None)
  if nonce in nonces:
    return False
  nonces[nonce] = now
  return True


def _limiter(
  entry_store: dict[str, Any], dog_id: str, source: PushSource, max_per_minute: int
) -> _RateLimiter:
  limiters = entry_store.get("limiters")
  if not isinstance(limiters, dict):
    entry_store["limiters"] = {}
    limiters = entry_store["limiters"]
  key = f"{dog_id}:{source}"
  existing = limiters.get(key)
  if isinstance(existing, _RateLimiter) and existing.max_events == max_per_minute:
    return existing
  limiter = _RateLimiter(window_seconds=60, max_events=max_per_minute, events=deque())
  limiters[key] = limiter
  return limiter


def _accept(
  telemetry: dict[str, Any], dog_id: str, source: PushSource, now_iso: str
) -> None:
  telemetry["accepted_total"] = int(telemetry.get("accepted_total", 0)) + 1
  dog_tel = _dog_telemetry(telemetry, dog_id)
  dog_tel["accepted_total"] = int(dog_tel.get("accepted_total", 0)) + 1
  dog_tel["last_accepted"] = now_iso
  by_src = dog_tel.get("by_source_accepted")
  if not isinstance(by_src, dict):
    by_src = {}
    dog_tel["by_source_accepted"] = by_src
  by_src[source] = int(by_src.get(source, 0)) + 1


def _reject(
  telemetry: dict[str, Any],
  dog_id: str,
  source: PushSource,
  now_iso: str,
  reason: str,
  status: int,
) -> PushResult:
  telemetry["rejected_total"] = int(telemetry.get("rejected_total", 0)) + 1
  dog_tel = _dog_telemetry(telemetry, dog_id or "unknown")
  dog_tel["rejected_total"] = int(dog_tel.get("rejected_total", 0)) + 1
  dog_tel["last_rejected"] = now_iso
  dog_tel["last_rejection_reason"] = reason
  _bump_reason(dog_tel, reason)
  by_src = dog_tel.get("by_source_rejected")
  if not isinstance(by_src, dict):
    by_src = {}
    dog_tel["by_source_rejected"] = by_src
  by_src[source] = int(by_src.get(source, 0)) + 1
  return PushResult(ok=False, status=status, error=reason, dog_id=dog_id)


async def async_process_gps_push(
  hass: HomeAssistant,
  entry: ConfigEntry,
  payload: Mapping[str, Any],
  *,
  source: PushSource,
  raw_size: int | None = None,
  nonce: str | None = None,
) -> PushResult:
  """Validate and apply a GPS push update (strict per-dog source)."""
  entry_store = _entry_store(hass, entry.entry_id)
  telemetry = cast(dict[str, Any], entry_store.get("telemetry", {}))
  now_mono = time.monotonic()
  now_iso = dt_util.utcnow().isoformat()

  if raw_size is not None and raw_size > _payload_limit(entry):
    return _reject(telemetry, "unknown", source, now_iso, "payload_too_large", 413)

  if not isinstance(payload, Mapping):
    return _reject(telemetry, "unknown", source, now_iso, "invalid_payload", 400)

  dog_id_raw = payload.get("dog_id")
  if not isinstance(dog_id_raw, str) or not dog_id_raw.strip():
    return _reject(telemetry, "unknown", source, now_iso, "missing_dog_id", 400)
  dog_id = dog_id_raw.strip()

  expected = _dog_expected_source(entry, dog_id)
  if expected is None:
    return _reject(telemetry, dog_id, source, now_iso, "unknown_dog_id", 404)
  if expected != source:
    return _reject(telemetry, dog_id, source, now_iso, "gps_source_mismatch", 409)

  if nonce and not _check_nonce(entry_store, entry, nonce, now_mono):
    return _reject(telemetry, dog_id, source, now_iso, "replay_nonce", 409)

  max_per_minute = _rate_limit(entry, source)
  limiter = _limiter(entry_store, dog_id, source, max_per_minute)
  if not limiter.allow(now_mono):
    return _reject(telemetry, dog_id, source, now_iso, "rate_limited", 429)

  lat = payload.get("latitude")
  lon = payload.get("longitude")
  if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
    return _reject(telemetry, dog_id, source, now_iso, "missing_coordinates", 400)

  latitude = float(lat)
  longitude = float(lon)
  if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
    return _reject(telemetry, dog_id, source, now_iso, "coordinates_out_of_range", 400)

  altitude = payload.get("altitude")
  accuracy = payload.get("accuracy")
  timestamp_raw = payload.get("timestamp")
  timestamp = dt_util.utcnow()
  if isinstance(timestamp_raw, str) and timestamp_raw:
    parsed = dt_util.parse_datetime(timestamp_raw)
    if parsed is not None:
      timestamp = parsed

  runtime_data = require_runtime_data(hass, entry)
  coordinator = runtime_data.coordinator
  gps_manager = runtime_data.gps_geofence_manager or coordinator.gps_geofence_manager
  if gps_manager is None:
    return _reject(telemetry, dog_id, source, now_iso, "gps_manager_unavailable", 503)

  try:
    from .gps_manager import LocationSource

    src_enum = (
      LocationSource.WEBHOOK
      if source == "webhook"
      else (LocationSource.MQTT if source == "mqtt" else LocationSource.ENTITY)
    )

    ok = await gps_manager.async_add_gps_point(
      dog_id=dog_id,
      latitude=latitude,
      longitude=longitude,
      altitude=float(altitude) if isinstance(altitude, (int, float)) else None,
      accuracy=float(accuracy) if isinstance(accuracy, (int, float)) else None,
      timestamp=timestamp,
      source=src_enum,
    )
  except Exception as err:
    _LOGGER.exception("Push GPS update failed for %s (%s): %s", dog_id, source, err)
    return _reject(telemetry, dog_id, source, now_iso, "gps_update_failed", 500)

  if not ok:
    return _reject(telemetry, dog_id, source, now_iso, "gps_rejected", 400)

  _accept(telemetry, dog_id, source, now_iso)

  try:
    await coordinator.async_patch_gps_update(dog_id)
  except Exception as err:  # pragma: no cover
    _LOGGER.debug("GPS patch update failed for %s: %s", dog_id, err)
    await coordinator.async_refresh_dog(dog_id)

  return PushResult(ok=True, status=200, dog_id=dog_id)
