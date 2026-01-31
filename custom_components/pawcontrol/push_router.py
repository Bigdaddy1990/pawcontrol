"""Unified push ingress for PawControl.

Routes inbound GPS updates from multiple sources (webhook, MQTT, entity listeners)
through a single validation, rate limiting, replay protection and patch-refresh path.

Design goals:
- No secrets or raw coordinates in telemetry
- Per-dog protection against flooding
- Strict source matching (only accept payloads for dogs configured for that source)
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Final, TypedDict, cast
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
  CONF_GPS_SOURCE,
  CONF_PUSH_NONCE_TTL_SECONDS,
  CONF_PUSH_PAYLOAD_MAX_BYTES,
  CONF_PUSH_RATE_LIMIT_PER_MINUTE,
  DEFAULT_PUSH_NONCE_TTL_SECONDS,
  DEFAULT_PUSH_PAYLOAD_MAX_BYTES,
  DEFAULT_PUSH_RATE_LIMIT_PER_MINUTE,
  DOMAIN,
)
from .runtime_data import require_runtime_data

_LOGGER = logging.getLogger(__name__)

PUSH_STORE_KEY: Final[str] = "_push"


class PushResult(TypedDict, total=False):
  ok: bool
  error: str
  status: int


@dataclass
class _RateLimiter:
  """Sliding-window rate limiter (per dog, per source)."""

  limit_per_minute: int
  window_seconds: int = 60

  def __post_init__(self) -> None:
    self._events: MutableMapping[tuple[str, str], deque[float]] = defaultdict(deque)

  def allow(self, dog_id: str, source: str, now: float) -> bool:
    key = (dog_id, source)
    q = self._events[key]
    cutoff = now - self.window_seconds
    while q and q[0] < cutoff:
      q.popleft()
    if len(q) >= max(0, int(self.limit_per_minute)):
      return False
    q.append(now)
    return True


def _store_for_entry(hass: HomeAssistant, entry_id: str) -> MutableMapping[str, Any]:
  root = hass.data.setdefault(DOMAIN, {})
  if not isinstance(root, dict):
    # extremely defensive: HA guarantees dict, but don't crash diagnostics
    root = {}
    hass.data[DOMAIN] = root
  push_root = root.setdefault(PUSH_STORE_KEY, {})
  if not isinstance(push_root, dict):
    push_root = {}
    root[PUSH_STORE_KEY] = push_root
  entry_store = push_root.setdefault(entry_id, {})
  if not isinstance(entry_store, dict):
    entry_store = {}
    push_root[entry_id] = entry_store
  entry_store.setdefault("created_at", dt_util.utcnow().isoformat())
  return cast(MutableMapping[str, Any], entry_store)


def _telemetry(entry_store: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
  tel = entry_store.setdefault("telemetry", {})
  if not isinstance(tel, dict):
    tel = {}
    entry_store["telemetry"] = tel
  # normalize basic fields
  tel.setdefault("accepted_total", 0)
  tel.setdefault("rejected_total", 0)
  tel.setdefault("by_source", {})
  tel.setdefault("by_error", {})
  tel.setdefault("per_dog", {})
  return cast(MutableMapping[str, Any], tel)


def _inc_map(counter_map: MutableMapping[str, Any], key: str, amount: int = 1) -> None:
  try:
    counter_map[key] = int(counter_map.get(key, 0)) + amount
  except Exception:
    counter_map[key] = amount


def _record_reject(tel: MutableMapping[str, Any], dog_id: str | None, source: str, error: str) -> None:
  tel["rejected_total"] = int(tel.get("rejected_total", 0)) + 1
  by_source = tel.setdefault("by_source", {})
  by_error = tel.setdefault("by_error", {})
  if isinstance(by_source, dict):
    _inc_map(by_source, source)
  if isinstance(by_error, dict):
    _inc_map(by_error, error)
  tel["last_rejected"] = dt_util.utcnow().isoformat()
  tel["last_error"] = error
  tel["last_source"] = source
  if dog_id:
    per_dog = tel.setdefault("per_dog", {})
    if isinstance(per_dog, dict):
      dog_tel = per_dog.setdefault(dog_id, {})
      if isinstance(dog_tel, dict):
        dog_tel["rejected_total"] = int(dog_tel.get("rejected_total", 0)) + 1
        dog_tel["last_rejected"] = tel["last_rejected"]
        dog_tel["last_error"] = error
        dog_tel["last_source"] = source


def _record_accept(tel: MutableMapping[str, Any], dog_id: str, source: str) -> None:
  tel["accepted_total"] = int(tel.get("accepted_total", 0)) + 1
  by_source = tel.setdefault("by_source", {})
  if isinstance(by_source, dict):
    _inc_map(by_source, source)
  tel["last_accepted"] = dt_util.utcnow().isoformat()
  tel["last_source"] = source
  per_dog = tel.setdefault("per_dog", {})
  if isinstance(per_dog, dict):
    dog_tel = per_dog.setdefault(dog_id, {})
    if isinstance(dog_tel, dict):
      dog_tel["accepted_total"] = int(dog_tel.get("accepted_total", 0)) + 1
      dog_tel["last_accepted"] = tel["last_accepted"]
      dog_tel["last_source"] = source


def _get_rate_limiter(entry_store: MutableMapping[str, Any], limit: int) -> _RateLimiter:
  rl = entry_store.get("rate_limiter")
  if isinstance(rl, _RateLimiter) and rl.limit_per_minute == limit:
    return rl
  rl = _RateLimiter(limit_per_minute=limit)
  entry_store["rate_limiter"] = rl
  return rl


def _nonce_seen(entry_store: MutableMapping[str, Any], nonce: str, ttl: int, now: float) -> bool:
  cache = entry_store.setdefault("nonce_cache", {})
  if not isinstance(cache, dict):
    cache = {}
    entry_store["nonce_cache"] = cache

  # prune old
  cutoff = now - float(ttl)
  for k, ts in list(cache.items()):
    try:
      if float(ts) < cutoff:
        cache.pop(k, None)
    except Exception:
      cache.pop(k, None)

  if nonce in cache:
    return True
  cache[nonce] = now
  return False


def _parse_timestamp(value: Any) -> Any:
  if isinstance(value, (int, float)):
    # epoch seconds
    try:
      return dt_util.utc_from_timestamp(float(value))
    except Exception:
      return dt_util.utcnow()
  if isinstance(value, str) and value.strip():
    parsed = dt_util.parse_datetime(value)
    return parsed or dt_util.utcnow()
  return dt_util.utcnow()


def _is_number(value: Any) -> bool:
  return isinstance(value, (int, float)) and not isinstance(value, bool)


async def async_process_gps_push(
  hass: HomeAssistant,
  entry: ConfigEntry,
  payload: Mapping[str, Any],
  *,
  source: str,
  raw_size: int | None = None,
  nonce: str | None = None,
) -> PushResult:
  """Process an inbound GPS push payload.

  Strict mode:
  - Only accept events for a dog whose gps_config.gps_source matches ``source``.
  """
  entry_store = _store_for_entry(hass, entry.entry_id)
  tel = _telemetry(entry_store)

  # payload size guard (only when raw_size known)
  max_bytes = int(entry.options.get(CONF_PUSH_PAYLOAD_MAX_BYTES, DEFAULT_PUSH_PAYLOAD_MAX_BYTES))
  if raw_size is not None and raw_size > max_bytes:
    _record_reject(tel, None, source, "payload_too_large")
    return {"ok": False, "error": "payload_too_large", "status": 413}

  if not isinstance(payload, Mapping):
    _record_reject(tel, None, source, "invalid_payload")
    return {"ok": False, "error": "invalid_payload", "status": 400}

  dog_id = payload.get("dog_id")
  if not isinstance(dog_id, str) or not dog_id.strip():
    _record_reject(tel, None, source, "missing_dog_id")
    return {"ok": False, "error": "missing_dog_id", "status": 400}
  dog_id = dog_id.strip()

  latitude = payload.get("latitude")
  longitude = payload.get("longitude")
  if not _is_number(latitude) or not _is_number(longitude):
    _record_reject(tel, dog_id, source, "missing_coordinates")
    return {"ok": False, "error": "missing_coordinates", "status": 400}

  lat = float(latitude)
  lon = float(longitude)
  if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
    _record_reject(tel, dog_id, source, "coordinate_out_of_range")
    return {"ok": False, "error": "coordinate_out_of_range", "status": 400}

  # Strict source matching against dog configuration
  runtime_data = require_runtime_data(hass, entry)
  coordinator = runtime_data.coordinator
  dog_config = coordinator.get_dog_config(dog_id)
  if not isinstance(dog_config, dict):
    _record_reject(tel, dog_id, source, "unknown_dog")
    return {"ok": False, "error": "unknown_dog", "status": 404}
  gps_cfg = dog_config.get("gps_config") if isinstance(dog_config, dict) else None
  gps_source = None
  if isinstance(gps_cfg, dict):
    gps_source = gps_cfg.get(CONF_GPS_SOURCE)
  if gps_source != source:
    _record_reject(tel, dog_id, source, "gps_source_mismatch")
    return {"ok": False, "error": "gps_source_mismatch", "status": 409}

  # Nonce replay protection (optional)
  ttl = int(entry.options.get(CONF_PUSH_NONCE_TTL_SECONDS, DEFAULT_PUSH_NONCE_TTL_SECONDS))
  if nonce:
    now = time.monotonic()
    if _nonce_seen(entry_store, nonce, ttl, now):
      _record_reject(tel, dog_id, source, "replay")
      return {"ok": False, "error": "replay", "status": 409}

  # Rate limiting per dog/source
  limit = int(entry.options.get(CONF_PUSH_RATE_LIMIT_PER_MINUTE, DEFAULT_PUSH_RATE_LIMIT_PER_MINUTE))
  now2 = time.monotonic()
  limiter = _get_rate_limiter(entry_store, limit)
  if not limiter.allow(dog_id, source, now2):
    _record_reject(tel, dog_id, source, "rate_limited")
    return {"ok": False, "error": "rate_limited", "status": 429}

  # Optional metadata
  altitude = payload.get("altitude")
  accuracy = payload.get("accuracy")
  timestamp = _parse_timestamp(payload.get("timestamp"))

  try:
    from .gps_manager import LocationSource

    source_enum = {
      "webhook": LocationSource.WEBHOOK,
      "mqtt": LocationSource.MQTT,
      "entity": LocationSource.ENTITY,
    }.get(source, LocationSource.WEBHOOK)

    gps_manager = runtime_data.gps_geofence_manager or coordinator.gps_geofence_manager
    if gps_manager is None:
      _record_reject(tel, dog_id, source, "gps_manager_unavailable")
      return {"ok": False, "error": "gps_manager_unavailable", "status": 503}

    ok = await gps_manager.async_add_gps_point(
      dog_id=dog_id,
      latitude=lat,
      longitude=lon,
      altitude=float(altitude) if _is_number(altitude) else None,
      accuracy=float(accuracy) if _is_number(accuracy) else None,
      timestamp=timestamp,
      source=source_enum,
    )
  except Exception as err:  # pragma: no cover - defensive
    _LOGGER.exception("Push GPS update failed (%s): %s", source, err)
    _record_reject(tel, dog_id, source, "gps_update_failed")
    return {"ok": False, "error": "gps_update_failed", "status": 500}

  if not ok:
    _record_reject(tel, dog_id, source, "gps_rejected")
    return {"ok": False, "error": "gps_rejected", "status": 400}

  _record_accept(tel, dog_id, source)

  # Patch-refresh only affected dog
  try:
    await coordinator.async_patch_gps_update(dog_id)
  except Exception as err:  # pragma: no cover
    _LOGGER.debug("GPS patch update failed for %s: %s", dog_id, err)
    await coordinator.async_refresh_dog(dog_id)

  return {"ok": True, "status": 200}


def get_entry_push_telemetry_snapshot(hass: HomeAssistant, entry_id: str) -> Mapping[str, Any]:
  """Return a JSON-safe telemetry snapshot for diagnostics."""
  entry_store = _store_for_entry(hass, entry_id)
  tel = _telemetry(entry_store)
  # return a shallow copy without non-JSON objects
  snapshot: dict[str, Any] = {}
  if "created_at" in entry_store:
    snapshot["created_at"] = entry_store.get("created_at")
  for key in ("accepted_total", "rejected_total", "last_accepted", "last_rejected", "last_error", "last_source"):
    if key in tel:
      snapshot[key] = tel.get(key)
  snapshot["by_source"] = dict(tel.get("by_source", {}) or {})
  snapshot["by_error"] = dict(tel.get("by_error", {}) or {})
  snapshot["per_dog"] = dict(tel.get("per_dog", {}) or {})
  return snapshot
