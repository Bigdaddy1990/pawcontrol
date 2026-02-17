"""Unified push ingestion for PawControl.

Centralizes processing of push-style GPS updates coming from webhooks, MQTT,
or other entity-driven sources. It validates payloads, enforces strict per-dog
source matching, rate-limits bursty senders, and records telemetry suitable
for diagnostics and repairs.

Telemetry is intentionally non-sensitive (no coordinates).
"""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import logging
import time
from typing import Any, Final, Literal, TypedDict, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

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
    ok: bool  # noqa: E111
    status: int  # noqa: E111
    error: str  # noqa: E111
    dog_id: str  # noqa: E111


@dataclass(slots=True)
class _RateLimiter:
    window_seconds: int  # noqa: E111
    max_events: int  # noqa: E111
    events: deque[float]  # noqa: E111

    def allow(self, now: float) -> bool:  # noqa: E111
        cutoff = now - self.window_seconds
        while self.events and self.events[0] < cutoff:
            self.events.popleft()  # noqa: E111
        if len(self.events) >= self.max_events:
            return False  # noqa: E111
        self.events.append(now)
        return True


def _store(hass: HomeAssistant) -> dict[str, Any]:
    store = hass.data.setdefault(DOMAIN, {})  # noqa: E111
    if not isinstance(store, dict):  # noqa: E111
        hass.data[DOMAIN] = {}
        store = hass.data[DOMAIN]
    return cast(dict[str, Any], store)  # noqa: E111


def _entry_store(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    domain_store = _store(hass)  # noqa: E111
    router_store = domain_store.setdefault(_PUSH_STORE_KEY, {})  # noqa: E111
    if not isinstance(router_store, dict):  # noqa: E111
        domain_store[_PUSH_STORE_KEY] = {}
        router_store = domain_store[_PUSH_STORE_KEY]

    entry = router_store.setdefault(entry_id, {})  # noqa: E111
    if not isinstance(entry, dict):  # noqa: E111
        router_store[entry_id] = {}
        entry = router_store[entry_id]

    telemetry = entry.setdefault("telemetry", {})  # noqa: E111
    if not isinstance(telemetry, dict):  # noqa: E111
        entry["telemetry"] = {}
        telemetry = entry["telemetry"]

    if "created_at" not in telemetry:  # noqa: E111
        telemetry["created_at"] = dt_util.utcnow().isoformat()
        telemetry["dogs"] = {}
        telemetry["accepted_total"] = 0
        telemetry["rejected_total"] = 0

    entry.setdefault("nonces", {})  # noqa: E111
    entry.setdefault("limiters", {})  # noqa: E111
    return entry  # noqa: E111


def _dog_telemetry(telemetry: dict[str, Any], dog_id: str) -> dict[str, Any]:
    dogs = telemetry.setdefault("dogs", {})  # noqa: E111
    if not isinstance(dogs, dict):  # noqa: E111
        telemetry["dogs"] = {}
        dogs = telemetry["dogs"]
    dog = dogs.setdefault(dog_id, {})  # noqa: E111
    if not isinstance(dog, dict):  # noqa: E111
        dogs[dog_id] = {}
        dog = dogs[dog_id]

    dog.setdefault("accepted_total", 0)  # noqa: E111
    dog.setdefault("rejected_total", 0)  # noqa: E111
    dog.setdefault("last_accepted", None)  # noqa: E111
    dog.setdefault("last_rejected", None)  # noqa: E111
    dog.setdefault("last_rejection_reason", None)  # noqa: E111
    dog.setdefault("by_reason", {})  # noqa: E111
    dog.setdefault("by_source_accepted", {})  # noqa: E111
    dog.setdefault("by_source_rejected", {})  # noqa: E111
    return dog  # noqa: E111


def _bump_reason(dog_tel: dict[str, Any], reason: str) -> None:
    by_reason = dog_tel.get("by_reason")  # noqa: E111
    if not isinstance(by_reason, dict):  # noqa: E111
        by_reason = {}
        dog_tel["by_reason"] = by_reason
    by_reason[reason] = int(by_reason.get(reason, 0)) + 1  # noqa: E111

    if len(by_reason) > _MAX_REASONS:  # noqa: E111
        items = sorted(by_reason.items(), key=lambda kv: kv[1])
        for key, _ in items[: len(by_reason) - _MAX_REASONS]:
            by_reason.pop(key, None)  # noqa: E111


def get_entry_push_telemetry_snapshot(
    hass: HomeAssistant, entry_id: str
) -> dict[str, Any]:
    """Return a JSON-safe snapshot of push telemetry for diagnostics and sensors."""  # noqa: E111
    entry = _entry_store(hass, entry_id)  # noqa: E111
    telemetry = entry.get("telemetry")  # noqa: E111
    if not isinstance(telemetry, dict):  # noqa: E111
        return {}
    # shallow copy (nested dicts intentionally shared but non-sensitive)  # noqa: E114
    return {  # noqa: E111
        "created_at": telemetry.get("created_at"),
        "accepted_total": telemetry.get("accepted_total", 0),
        "rejected_total": telemetry.get("rejected_total", 0),
        "dogs": telemetry.get("dogs", {}),
    }


def _dog_expected_source(entry: ConfigEntry, dog_id: str) -> str | None:
    dogs = entry.data.get(CONF_DOGS, [])  # noqa: E111
    if not isinstance(dogs, list):  # noqa: E111
        return None
    for item in dogs:  # noqa: E111
        if not isinstance(item, Mapping):
            continue  # noqa: E111
        if item.get("dog_id") != dog_id:
            continue  # noqa: E111
        gps_cfg = item.get("gps_config")
        if isinstance(gps_cfg, Mapping):
            raw = gps_cfg.get(CONF_GPS_SOURCE)  # noqa: E111
            return raw.strip() if isinstance(raw, str) else None  # noqa: E111
        raw = item.get(CONF_GPS_SOURCE)
        return raw.strip() if isinstance(raw, str) else None
    return None  # noqa: E111


def _payload_limit(entry: ConfigEntry) -> int:
    raw = entry.options.get(CONF_PUSH_PAYLOAD_MAX_BYTES, DEFAULT_PUSH_PAYLOAD_MAX_BYTES)  # noqa: E111
    try:  # noqa: E111
        if isinstance(raw, bool):
            raise TypeError  # noqa: E111
        value = int(raw) if isinstance(raw, int | float | str) else None
    except Exception:  # noqa: E111
        return DEFAULT_PUSH_PAYLOAD_MAX_BYTES
    if value is None:  # noqa: E111
        return DEFAULT_PUSH_PAYLOAD_MAX_BYTES
    return max(1024, min(256 * 1024, value))  # noqa: E111


def _nonce_ttl(entry: ConfigEntry) -> int:
    raw = entry.options.get(CONF_PUSH_NONCE_TTL_SECONDS, DEFAULT_PUSH_NONCE_TTL_SECONDS)  # noqa: E111
    try:  # noqa: E111
        if isinstance(raw, bool):
            raise TypeError  # noqa: E111
        value = int(raw) if isinstance(raw, int | float | str) else None
    except Exception:  # noqa: E111
        return DEFAULT_PUSH_NONCE_TTL_SECONDS
    if value is None:  # noqa: E111
        return DEFAULT_PUSH_NONCE_TTL_SECONDS
    return max(60, min(24 * 3600, value))  # noqa: E111


def _rate_limit(entry: ConfigEntry, source: PushSource) -> int:
    if source == "webhook":  # noqa: E111
        raw = entry.options.get(
            CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
            DEFAULT_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
        )
    elif source == "mqtt":  # noqa: E111
        raw = entry.options.get(
            CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
            DEFAULT_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
        )
    else:  # noqa: E111
        raw = entry.options.get(
            CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
            DEFAULT_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
        )
    try:  # noqa: E111
        if isinstance(raw, bool):
            raise TypeError  # noqa: E111
        value = int(raw) if isinstance(raw, int | float | str) else None
    except Exception:  # noqa: E111
        value = 60
    if value is None:  # noqa: E111
        value = 60
    return max(1, min(600, value))  # noqa: E111


def _check_nonce(
    entry_store: dict[str, Any], entry: ConfigEntry, nonce: str, now: float
) -> bool:
    nonces = entry_store.get("nonces")  # noqa: E111
    if not isinstance(nonces, dict):  # noqa: E111
        entry_store["nonces"] = {}
        nonces = entry_store["nonces"]
    ttl = _nonce_ttl(entry)  # noqa: E111
    cutoff = now - ttl  # noqa: E111
    for key, ts in list(nonces.items()):  # noqa: E111
        if not isinstance(ts, (int, float)) or ts < cutoff:
            nonces.pop(key, None)  # noqa: E111
    if nonce in nonces:  # noqa: E111
        return False
    nonces[nonce] = now  # noqa: E111
    return True  # noqa: E111


def _limiter(
    entry_store: dict[str, Any], dog_id: str, source: PushSource, max_per_minute: int
) -> _RateLimiter:
    limiters = entry_store.get("limiters")  # noqa: E111
    if not isinstance(limiters, dict):  # noqa: E111
        entry_store["limiters"] = {}
        limiters = entry_store["limiters"]
    key = f"{dog_id}:{source}"  # noqa: E111
    existing = limiters.get(key)  # noqa: E111
    if isinstance(existing, _RateLimiter) and existing.max_events == max_per_minute:  # noqa: E111
        return existing
    limiter = _RateLimiter(window_seconds=60, max_events=max_per_minute, events=deque())  # noqa: E111
    limiters[key] = limiter  # noqa: E111
    return limiter  # noqa: E111


def _accept(
    telemetry: dict[str, Any], dog_id: str, source: PushSource, now_iso: str
) -> None:
    telemetry["accepted_total"] = int(telemetry.get("accepted_total", 0)) + 1  # noqa: E111
    dog_tel = _dog_telemetry(telemetry, dog_id)  # noqa: E111
    dog_tel["accepted_total"] = int(dog_tel.get("accepted_total", 0)) + 1  # noqa: E111
    dog_tel["last_accepted"] = now_iso  # noqa: E111
    by_src = dog_tel.get("by_source_accepted")  # noqa: E111
    if not isinstance(by_src, dict):  # noqa: E111
        by_src = {}
        dog_tel["by_source_accepted"] = by_src
    by_src[source] = int(by_src.get(source, 0)) + 1  # noqa: E111


def _reject(
    telemetry: dict[str, Any],
    dog_id: str,
    source: PushSource,
    now_iso: str,
    reason: str,
    status: int,
) -> PushResult:
    telemetry["rejected_total"] = int(telemetry.get("rejected_total", 0)) + 1  # noqa: E111
    dog_tel = _dog_telemetry(telemetry, dog_id or "unknown")  # noqa: E111
    dog_tel["rejected_total"] = int(dog_tel.get("rejected_total", 0)) + 1  # noqa: E111
    dog_tel["last_rejected"] = now_iso  # noqa: E111
    dog_tel["last_rejection_reason"] = reason  # noqa: E111
    _bump_reason(dog_tel, reason)  # noqa: E111
    by_src = dog_tel.get("by_source_rejected")  # noqa: E111
    if not isinstance(by_src, dict):  # noqa: E111
        by_src = {}
        dog_tel["by_source_rejected"] = by_src
    by_src[source] = int(by_src.get(source, 0)) + 1  # noqa: E111
    return PushResult(ok=False, status=status, error=reason, dog_id=dog_id)  # noqa: E111


async def async_process_gps_push(
    hass: HomeAssistant,
    entry: ConfigEntry,
    payload: Mapping[str, Any],
    *,
    source: PushSource,
    raw_size: int | None = None,
    nonce: str | None = None,
) -> PushResult:
    """Validate and apply a GPS push update (strict per-dog source)."""  # noqa: E111
    entry_store = _entry_store(hass, entry.entry_id)  # noqa: E111
    telemetry = cast(dict[str, Any], entry_store.get("telemetry", {}))  # noqa: E111
    now_mono = time.monotonic()  # noqa: E111
    now_iso = dt_util.utcnow().isoformat()  # noqa: E111

    if raw_size is not None and raw_size > _payload_limit(entry):  # noqa: E111
        return _reject(telemetry, "unknown", source, now_iso, "payload_too_large", 413)

    if not isinstance(payload, Mapping):  # noqa: E111
        return _reject(telemetry, "unknown", source, now_iso, "invalid_payload", 400)

    dog_id_raw = payload.get("dog_id")  # noqa: E111
    if not isinstance(dog_id_raw, str) or not dog_id_raw.strip():  # noqa: E111
        return _reject(telemetry, "unknown", source, now_iso, "missing_dog_id", 400)
    dog_id = dog_id_raw.strip()  # noqa: E111

    expected = _dog_expected_source(entry, dog_id)  # noqa: E111
    if expected is None:  # noqa: E111
        return _reject(telemetry, dog_id, source, now_iso, "unknown_dog_id", 404)
    if expected != source:  # noqa: E111
        return _reject(telemetry, dog_id, source, now_iso, "gps_source_mismatch", 409)

    if nonce and not _check_nonce(entry_store, entry, nonce, now_mono):  # noqa: E111
        return _reject(telemetry, dog_id, source, now_iso, "replay_nonce", 409)

    max_per_minute = _rate_limit(entry, source)  # noqa: E111
    limiter = _limiter(entry_store, dog_id, source, max_per_minute)  # noqa: E111
    if not limiter.allow(now_mono):  # noqa: E111
        return _reject(telemetry, dog_id, source, now_iso, "rate_limited", 429)

    lat = payload.get("latitude")  # noqa: E111
    lon = payload.get("longitude")  # noqa: E111
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):  # noqa: E111
        return _reject(telemetry, dog_id, source, now_iso, "missing_coordinates", 400)

    latitude = float(lat)  # noqa: E111
    longitude = float(lon)  # noqa: E111
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):  # noqa: E111
        return _reject(
            telemetry, dog_id, source, now_iso, "coordinates_out_of_range", 400
        )

    altitude = payload.get("altitude")  # noqa: E111
    accuracy = payload.get("accuracy")  # noqa: E111
    timestamp_raw = payload.get("timestamp")  # noqa: E111
    timestamp = dt_util.utcnow()  # noqa: E111
    if isinstance(timestamp_raw, str) and timestamp_raw:  # noqa: E111
        parsed = dt_util.parse_datetime(timestamp_raw)
        if parsed is not None:
            timestamp = parsed  # noqa: E111

    runtime_data = require_runtime_data(hass, entry)  # noqa: E111
    coordinator = runtime_data.coordinator  # noqa: E111
    gps_manager = runtime_data.gps_geofence_manager or coordinator.gps_geofence_manager  # noqa: E111
    if gps_manager is None:  # noqa: E111
        return _reject(
            telemetry, dog_id, source, now_iso, "gps_manager_unavailable", 503
        )

    try:  # noqa: E111
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
    except Exception as err:  # noqa: E111
        _LOGGER.exception("Push GPS update failed for %s (%s): %s", dog_id, source, err)
        return _reject(telemetry, dog_id, source, now_iso, "gps_update_failed", 500)

    if not ok:  # noqa: E111
        return _reject(telemetry, dog_id, source, now_iso, "gps_rejected", 400)

    _accept(telemetry, dog_id, source, now_iso)  # noqa: E111

    try:  # noqa: E111
        await coordinator.async_patch_gps_update(dog_id)
    except Exception as err:  # pragma: no cover  # noqa: E111
        _LOGGER.debug("GPS patch update failed for %s: %s", dog_id, err)
        await coordinator.async_refresh_dog(dog_id)

    return PushResult(ok=True, status=200, dog_id=dog_id)  # noqa: E111
