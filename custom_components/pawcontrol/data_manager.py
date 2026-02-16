"""Data management helpers for the PawControl integration.

The previous optimisation-heavy data manager removed a number of behaviours
required by the tests in this repository.  This module intentionally favours a
clear and well documented implementation that focuses on correctness,
maintainability, and graceful error handling.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import islice
import json
import logging
from math import isfinite
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Final, NotRequired, TypedDict, TypeVar, cast

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
  CACHE_TIMESTAMP_FUTURE_THRESHOLD,
  CACHE_TIMESTAMP_STALE_THRESHOLD,
  DOMAIN,
  MODULE_FEEDING,
  MODULE_GARDEN,
  MODULE_GROOMING,
  MODULE_HEALTH,
  MODULE_MEDICATION,
  MODULE_WALK,
)
from .coordinator_support import (
  CacheMonitorTarget,
  CoordinatorMetrics,
  CoordinatorModuleAdapter,
)
from .module_adapters import (
  ModuleAdapterCacheError,
  ModuleAdapterCacheSnapshot,
  ModuleAdapterCacheStats,
)
from .notifications import NotificationPriority, NotificationType
from .types import (
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  CacheDiagnosticsMap,
  CacheDiagnosticsMetadata,
  CacheDiagnosticsSnapshot,
  CacheRepairAggregate,
  CacheRepairIssue,
  CacheRepairTotals,
  DailyStats,
  DataManagerMetricsSnapshot,
  DogConfigData,
  EntityBudgetDiagnostics,
  EntityBudgetSnapshotEntry,
  EntityBudgetStats,
  FeedingData,
  GPSLocation,
  HealthData,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONMutableSequence,
  JSONValue,
  ModuleCacheMetrics,
  PawControlRuntimeData,
  RawDogConfig,
  StorageNamespaceDogSummary,
  StorageNamespacePayload,
  StorageNamespaceSnapshot,
  StorageNamespaceStats,
  VisitorModeSettingsPayload,
  WalkData,
  WalkRoutePoint,
  ensure_dog_config_data,
)
from .utils import (
  JSONMappingLike,
  Number,
  _coerce_json_mutable,
  is_number,
  normalize_value,
)

_LOGGER = logging.getLogger(__name__)

_STORAGE_FILENAME = "data.json"

_MODULE_HISTORY_ATTRS: Final[dict[str, tuple[str, str]]] = {
  MODULE_FEEDING: ("feeding_history", "timestamp"),
  MODULE_WALK: ("walk_history", "end_time"),
  MODULE_HEALTH: ("health_history", "timestamp"),
  MODULE_MEDICATION: ("medication_history", "administration_time"),
  MODULE_GARDEN: ("poop_history", "timestamp"),
  MODULE_GROOMING: ("grooming_sessions", "started_at"),
}

if __name__ not in sys.modules and "pawcontrol_data_manager" in sys.modules:
  sys.modules[__name__] = sys.modules["pawcontrol_data_manager"]  # noqa: E111


class AdaptiveCacheEntry(TypedDict, total=False):
  """Metadata stored for each AdaptiveCache entry."""  # noqa: E111

  expiry: NotRequired[datetime | None]  # noqa: E111
  created_at: NotRequired[datetime]  # noqa: E111
  ttl: NotRequired[int]  # noqa: E111
  override_applied: NotRequired[bool]  # noqa: E111


class AdaptiveCacheStats(TypedDict):
  """Statistics payload returned by :meth:`AdaptiveCache.get_stats`."""  # noqa: E111

  size: int  # noqa: E111
  hits: int  # noqa: E111
  misses: int  # noqa: E111
  hit_rate: float  # noqa: E111
  memory_mb: float  # noqa: E111


ValueT = TypeVar("ValueT")


class AdaptiveCache[ValueT]:
  """Simple asynchronous cache used by legacy tests."""  # noqa: E111

  def __init__(self, default_ttl: int = 300) -> None:  # noqa: E111
    """Initialise the cache with the provided default TTL."""

    self._default_ttl = default_ttl
    self._data: dict[str, ValueT] = {}
    self._metadata: dict[str, AdaptiveCacheEntry] = {}
    self._lock = asyncio.Lock()
    self._hits = 0
    self._misses = 0
    self._diagnostics: CacheDiagnosticsMetadata = {
      "cleanup_invocations": 0,
      "expired_entries": 0,
      "expired_via_override": 0,
      "last_cleanup": None,
      "last_override_ttl": None,
      "last_expired_count": 0,
    }

  async def get(self, key: str) -> tuple[ValueT | None, bool]:  # noqa: E111
    """Return cached value for ``key`` and whether it was a cache hit."""

    async with self._lock:
      entry = self._metadata.get(key)  # noqa: E111
      if entry is None:  # noqa: E111
        self._misses += 1
        return None, False

      now = _utcnow()  # noqa: E111
      entry = self._normalize_entry_locked(key, entry, now)  # noqa: E111

      expiry = entry.get("expiry")  # noqa: E111
      if expiry is not None and now > expiry:  # noqa: E111
        self._data.pop(key, None)
        self._metadata.pop(key, None)
        self._diagnostics["expired_entries"] = (
          int(self._diagnostics.get("expired_entries", 0)) + 1
        )
        if bool(entry.get("override_applied")):
          self._diagnostics["expired_via_override"] = (  # noqa: E111
            int(self._diagnostics.get("expired_via_override", 0)) + 1
          )
        self._diagnostics["last_expired_count"] = 1
        self._misses += 1
        return None, False

      self._hits += 1  # noqa: E111
      return self._data[key], True  # noqa: E111

  async def set(self, key: str, value: ValueT, base_ttl: int = 300) -> None:  # noqa: E111
    """Store ``value`` for ``key`` honouring ``base_ttl`` when positive."""

    async with self._lock:
      ttl = base_ttl if base_ttl > 0 else self._default_ttl  # noqa: E111
      now = _utcnow()  # noqa: E111
      expiry = None if ttl <= 0 else now + timedelta(seconds=ttl)  # noqa: E111
      self._data[key] = value  # noqa: E111
      self._metadata[key] = {  # noqa: E111
        "expiry": expiry,
        "created_at": now,
        "ttl": ttl,
        "override_applied": False,
      }

  async def cleanup_expired(self, ttl_seconds: int | None = None) -> int:  # noqa: E111
    """Remove expired cache entries and return the number purged."""

    async with self._lock:
      now = _utcnow()  # noqa: E111
      override_ttl: int | None  # noqa: E111
      if ttl_seconds is None:  # noqa: E111
        override_ttl = None
      else:  # noqa: E111
        override_ttl = int(ttl_seconds)
        if override_ttl < 0:
          override_ttl = 0  # noqa: E111

      expired: list[str] = []  # noqa: E111
      expired_with_override = 0  # noqa: E111
      for key, meta in list(self._metadata.items()):  # noqa: E111
        meta = self._normalize_entry_locked(key, meta, now)
        created_at = meta.get("created_at")
        if not isinstance(created_at, datetime):
          created_at = now  # noqa: E111

        stored_ttl = int(meta.get("ttl", self._default_ttl))
        effective_ttl = stored_ttl
        override_applied = False

        if override_ttl is not None:
          if override_ttl <= 0:  # noqa: E111
            effective_ttl = 0
          elif stored_ttl <= 0:  # noqa: E111
            effective_ttl = override_ttl
          else:  # noqa: E111
            effective_ttl = min(stored_ttl, override_ttl)
          override_applied = effective_ttl != stored_ttl  # noqa: E111

        expiry: datetime | None
        if effective_ttl <= 0:
          expiry = None  # noqa: E111
        else:
          expiry = created_at + timedelta(seconds=effective_ttl)  # noqa: E111

        meta["expiry"] = expiry
        meta["override_applied"] = override_applied
        self._metadata[key] = meta

        if expiry is not None and now >= expiry:
          expired.append(key)  # noqa: E111
          if override_applied:  # noqa: E111
            expired_with_override += 1

      for key in expired:  # noqa: E111
        self._data.pop(key, None)
        self._metadata.pop(key, None)

      self._diagnostics["cleanup_invocations"] += 1  # noqa: E111
      self._diagnostics["last_cleanup"] = now  # noqa: E111
      self._diagnostics["last_override_ttl"] = override_ttl  # noqa: E111
      self._diagnostics["last_expired_count"] = len(expired)  # noqa: E111
      self._diagnostics["expired_entries"] = int(  # noqa: E111
        self._diagnostics.get("expired_entries", 0),
      ) + len(expired)
      self._diagnostics["expired_via_override"] = (  # noqa: E111
        int(self._diagnostics.get("expired_via_override", 0)) + expired_with_override
      )

      return len(expired)  # noqa: E111

  def get_stats(self) -> AdaptiveCacheStats:  # noqa: E111
    """Return basic cache statistics used by diagnostics."""

    total = self._hits + self._misses
    hit_rate = (self._hits / total * 100) if total else 0
    stats: AdaptiveCacheStats = {
      "size": len(self._data),
      "hits": self._hits,
      "misses": self._misses,
      "hit_rate": round(hit_rate, 2),
      "memory_mb": 0.0,
    }
    return stats

  def get_diagnostics(self) -> CacheDiagnosticsMetadata:  # noqa: E111
    """Return cleanup metrics to surface override activity in diagnostics."""

    snapshot = cast(CacheDiagnosticsMetadata, dict(self._diagnostics))
    last_cleanup = snapshot.get("last_cleanup")
    snapshot["last_cleanup"] = (
      last_cleanup.isoformat() if isinstance(last_cleanup, datetime) else None
    )
    snapshot["active_override_entries"] = sum(
      1 for meta in self._metadata.values() if bool(meta.get("override_applied"))
    )
    snapshot["tracked_entries"] = len(self._metadata)
    return snapshot

  def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:  # noqa: E111
    """Return a combined statistics/diagnostics payload for coordinators."""

    stats = self.get_stats()
    diagnostics = self.get_diagnostics()
    stats_payload = cast(JSONMutableMapping, dict(stats))
    return CacheDiagnosticsSnapshot(
      stats=stats_payload,
      diagnostics=diagnostics,
    )

  def _normalize_entry_locked(  # noqa: E111
    self,
    key: str,
    entry: AdaptiveCacheEntry,
    now: datetime,
  ) -> AdaptiveCacheEntry:
    """Clamp metadata when cached entries originate from the future."""

    ttl = int(entry.get("ttl", self._default_ttl))
    created_at = entry.get("created_at")
    if not isinstance(created_at, datetime):
      created_at = now  # noqa: E111
    elif created_at > now:
      _LOGGER.debug(  # noqa: E111
        "Normalising future AdaptiveCache entry for %s (delta=%s)",
        key,
        created_at - now,
      )
      created_at = now  # noqa: E111

    entry["created_at"] = created_at
    entry["ttl"] = ttl
    entry["override_applied"] = bool(entry.get("override_applied", False))

    if ttl <= 0:
      entry["expiry"] = None  # noqa: E111
    else:
      expiry = entry.get("expiry")  # noqa: E111
      if not isinstance(expiry, datetime) or expiry <= created_at:  # noqa: E111
        expiry = created_at + timedelta(seconds=ttl)
      entry["expiry"] = expiry  # noqa: E111

    self._metadata[key] = entry
    return entry


class _EntityBudgetMonitor:
  """Expose entity budget tracker internals to the data manager monitor."""  # noqa: E111

  __slots__ = ("_tracker",)  # noqa: E111

  def __init__(self, tracker: Any) -> None:  # noqa: E111
    self._tracker = tracker

  def _build_payload(self) -> tuple[EntityBudgetStats, EntityBudgetDiagnostics]:  # noqa: E111
    tracker = self._tracker
    summary_payload: JSONMutableMapping

    try:
      raw_snapshots = tracker.snapshots()  # noqa: E111
    except Exception as err:  # pragma: no cover - diagnostics guard
      snapshots: Iterable[Any] = ()  # noqa: E111
      summary_payload = _coerce_json_mutable({"error": str(err)})  # noqa: E111
    else:
      snapshots = (  # noqa: E111
        raw_snapshots if isinstance(raw_snapshots, Iterable) else (raw_snapshots,)
      )
      try:  # noqa: E111
        summary = tracker.summary()
      except Exception as err:  # pragma: no cover - defensive guard  # noqa: E111
        summary_payload = _coerce_json_mutable({"error": str(err)})
      else:  # noqa: E111
        summary_payload = (
          _coerce_json_mutable(summary)
          if isinstance(summary, Mapping)
          else _coerce_json_mutable({"value": summary})
        )

    serialised: list[EntityBudgetSnapshotEntry] = []
    for snapshot in snapshots:
      recorded_at = getattr(snapshot, "recorded_at", None)  # noqa: E111
      entry: EntityBudgetSnapshotEntry = {  # noqa: E111
        "dog_id": str(getattr(snapshot, "dog_id", "")),
        "profile": str(getattr(snapshot, "profile", "")),
        "requested_entities": tuple(
          str(entity) for entity in getattr(snapshot, "requested_entities", ())
        ),
        "denied_requests": tuple(
          str(entity) for entity in getattr(snapshot, "denied_requests", ())
        ),
      }

      capacity = getattr(snapshot, "capacity", None)  # noqa: E111
      if is_number(capacity):  # noqa: E111
        entry["capacity"] = float(cast(Number, capacity))

      base_allocation = getattr(snapshot, "base_allocation", None)  # noqa: E111
      if is_number(base_allocation):  # noqa: E111
        entry["base_allocation"] = float(cast(Number, base_allocation))

      dynamic_allocation = getattr(snapshot, "dynamic_allocation", None)  # noqa: E111
      if is_number(dynamic_allocation):  # noqa: E111
        entry["dynamic_allocation"] = float(
          cast(Number, dynamic_allocation),
        )

      if isinstance(recorded_at, datetime):  # noqa: E111
        entry["recorded_at"] = recorded_at.isoformat()
      else:  # noqa: E111
        parsed = (
          None if recorded_at is None else dt_util.parse_datetime(str(recorded_at))
        )
        if isinstance(parsed, datetime):
          entry["recorded_at"] = dt_util.as_utc(parsed).isoformat()  # noqa: E111
        else:
          entry["recorded_at"] = None  # noqa: E111

      serialised.append(entry)  # noqa: E111

    try:
      saturation = float(tracker.saturation())  # noqa: E111
    except Exception:  # pragma: no cover - defensive fallback
      saturation = 0.0  # noqa: E111

    stats: EntityBudgetStats = {
      "tracked_dogs": len(serialised),
      "saturation_percent": round(max(0.0, min(saturation, 1.0)) * 100.0, 2),
    }

    diagnostics: EntityBudgetDiagnostics = {
      "summary": summary_payload,
      "snapshots": serialised,
    }
    return stats, diagnostics

  def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:  # noqa: E111
    stats, diagnostics = self._build_payload()
    diagnostics_payload = cast(CacheDiagnosticsMetadata, diagnostics)
    return CacheDiagnosticsSnapshot(
      stats=cast(JSONMutableMapping, dict(stats)),
      diagnostics=diagnostics_payload,
    )

  def get_stats(self) -> JSONMutableMapping:  # noqa: E111
    stats, _diagnostics = self._build_payload()
    return cast(JSONMutableMapping, dict(stats))

  def get_diagnostics(self) -> CacheDiagnosticsMetadata:  # noqa: E111
    _stats, diagnostics = self._build_payload()
    return cast(CacheDiagnosticsMetadata, diagnostics)


class _CoordinatorModuleCacheMonitor:
  """Wrap coordinator module caches for diagnostics consumption."""  # noqa: E111

  __slots__ = ("_modules",)  # noqa: E111

  def __init__(self, modules: CoordinatorModuleAdapter) -> None:  # noqa: E111
    self._modules: CoordinatorModuleAdapter = modules

  @staticmethod  # noqa: E111
  def _metrics_to_stats(  # noqa: E111
    metrics: ModuleCacheMetrics | None,
  ) -> ModuleAdapterCacheStats:
    if metrics is None:
      return {  # noqa: E111
        "entries": 0,
        "hits": 0,
        "misses": 0,
        "hit_rate": 0.0,
      }

    entries = int(metrics.entries)
    hits = int(metrics.hits)
    misses = int(metrics.misses)
    hit_rate = round(float(metrics.hit_rate), 2)
    return {
      "entries": entries,
      "hits": hits,
      "misses": misses,
      "hit_rate": hit_rate,
    }

  def _aggregate_metrics(self) -> tuple[ModuleAdapterCacheStats, list[str]]:  # noqa: E111
    errors: list[str] = []
    try:
      metrics = self._modules.cache_metrics()  # noqa: E111
    except Exception as err:  # pragma: no cover - diagnostics guard
      errors.append(str(err))  # noqa: E111
      metrics = None  # noqa: E111
    return self._metrics_to_stats(metrics), errors

  def _per_module_snapshots(  # noqa: E111
    self,
  ) -> dict[
    str,
    ModuleAdapterCacheSnapshot | ModuleAdapterCacheError | ModuleAdapterCacheStats,
  ]:
    payload: dict[
      str,
      ModuleAdapterCacheSnapshot | ModuleAdapterCacheError | ModuleAdapterCacheStats,
    ] = {}
    for name in ("feeding", "walk", "geofencing", "health", "weather", "garden"):
      adapter = getattr(self._modules, name, None)  # noqa: E111
      if adapter is None:  # noqa: E111
        continue
      snapshot_fn = getattr(adapter, "cache_snapshot", None)  # noqa: E111
      if callable(snapshot_fn):  # noqa: E111
        try:
          snapshot = cast(ModuleAdapterCacheSnapshot, snapshot_fn())  # noqa: E111
        except Exception as err:  # pragma: no cover - defensive guard
          payload[name] = ModuleAdapterCacheError(error=str(err))  # noqa: E111
          continue  # noqa: E111
        payload[name] = snapshot
        continue

      metrics_fn = getattr(adapter, "cache_metrics", None)  # noqa: E111
      if callable(metrics_fn):  # noqa: E111
        try:
          metrics = metrics_fn()  # noqa: E111
        except Exception as err:  # pragma: no cover - defensive guard
          payload[name] = ModuleAdapterCacheError(error=str(err))  # noqa: E111
          continue  # noqa: E111
        payload[name] = self._metrics_to_stats(metrics)
    return payload

  def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:  # noqa: E111
    stats, errors = self._aggregate_metrics()
    diagnostics_payload: CacheDiagnosticsMetadata = cast(
      CacheDiagnosticsMetadata,
      {"per_module": self._per_module_snapshots()},
    )
    if errors:
      diagnostics_payload["errors"] = errors  # noqa: E111
    return CacheDiagnosticsSnapshot(
      stats=cast(JSONMutableMapping, dict(stats)),
      diagnostics=diagnostics_payload,
    )

  def get_stats(self) -> ModuleAdapterCacheStats:  # noqa: E111
    stats, _errors = self._aggregate_metrics()
    return stats

  def get_diagnostics(self) -> CacheDiagnosticsMetadata:  # noqa: E111
    diagnostics_payload: CacheDiagnosticsMetadata = cast(
      CacheDiagnosticsMetadata,
      {"per_module": self._per_module_snapshots()},
    )
    _, errors = self._aggregate_metrics()
    if errors:
      diagnostics_payload["errors"] = errors  # noqa: E111
    return diagnostics_payload


def _estimate_namespace_entries(payload: Any) -> int:
  """Return a best-effort entry count for namespace payloads."""  # noqa: E111

  if isinstance(payload, Mapping):  # noqa: E111
    total = 0
    for value in payload.values():
      total += _estimate_namespace_entries(value)  # noqa: E111
    return total or len(payload)

  if isinstance(payload, Sequence) and not isinstance(  # noqa: E111
    payload,
    str | bytes | bytearray,
  ):
    return len(payload)

  return 1 if payload not in (None, "", (), [], {}) else 0  # noqa: E111


def _find_namespace_timestamp(payload: Any) -> str | None:
  """Return the first ISO timestamp discovered in ``payload``."""  # noqa: E111

  if isinstance(payload, Mapping):  # noqa: E111
    for key in ("updated_at", "timestamp", "generated_at", "recorded_at"):
      candidate = payload.get(key)  # noqa: E111
      if isinstance(candidate, str):  # noqa: E111
        return candidate
    for value in payload.values():
      found = _find_namespace_timestamp(value)  # noqa: E111
      if found is not None:  # noqa: E111
        return found
  elif isinstance(payload, Sequence) and not isinstance(  # noqa: E111
    payload,
    str | bytes | bytearray,
  ):
    for item in payload:
      found = _find_namespace_timestamp(item)  # noqa: E111
      if found is not None:  # noqa: E111
        return found
  return None  # noqa: E111


def _namespace_has_timestamp_field(payload: Any) -> bool:
  """Return ``True`` if ``payload`` exposes a timestamp-like field."""  # noqa: E111

  if isinstance(payload, Mapping):  # noqa: E111
    for key in ("updated_at", "timestamp", "generated_at", "recorded_at"):
      if key in payload:  # noqa: E111
        return True
    return any(_namespace_has_timestamp_field(value) for value in payload.values())
  if isinstance(payload, Sequence) and not isinstance(  # noqa: E111
    payload,
    str | bytes | bytearray,
  ):
    return any(_namespace_has_timestamp_field(item) for item in payload)
  return False  # noqa: E111


class _StorageNamespaceCacheMonitor:
  """Expose persisted namespace state for coordinator diagnostics."""  # noqa: E111

  __slots__ = ("_label", "_manager", "_namespace")  # noqa: E111

  def __init__(  # noqa: E111
    self,
    manager: PawControlDataManager,
    namespace: str,
    label: str,
  ) -> None:
    self._manager = manager
    self._namespace = namespace
    self._label = label

  def _build_payload(  # noqa: E111
    self,
  ) -> tuple[
    StorageNamespaceStats,
    StorageNamespaceSnapshot,
    CacheDiagnosticsMetadata,
  ]:
    state = self._manager._namespace_state.get(self._namespace, {})
    per_dog: dict[str, StorageNamespaceDogSummary] = {}
    timestamp_anomalies: dict[str, str] = {}
    total_entries = 0

    for key, value in state.items():
      dog_id = str(key)  # noqa: E111
      entry_count = _estimate_namespace_entries(value)  # noqa: E111
      total_entries += entry_count  # noqa: E111

      summary: StorageNamespaceDogSummary = {  # noqa: E111
        "entries": entry_count,
        "payload_type": type(value).__name__,
      }

      timestamp = _find_namespace_timestamp(value)  # noqa: E111
      if timestamp is not None:  # noqa: E111
        summary["timestamp"] = timestamp
        parsed = dt_util.parse_datetime(timestamp)
        if parsed is None:
          timestamp_anomalies[dog_id] = "unparseable"  # noqa: E111
          summary["timestamp_issue"] = "unparseable"  # noqa: E111
        else:
          parsed_utc = dt_util.as_utc(parsed)  # noqa: E111
          delta = _utcnow() - parsed_utc  # noqa: E111
          summary["timestamp_age_seconds"] = int(  # noqa: E111
            delta.total_seconds(),
          )
          if delta < -CACHE_TIMESTAMP_FUTURE_THRESHOLD:  # noqa: E111
            timestamp_anomalies[dog_id] = "future"
            summary["timestamp_issue"] = "future"
          elif delta > CACHE_TIMESTAMP_STALE_THRESHOLD:  # noqa: E111
            timestamp_anomalies[dog_id] = "stale"
            summary["timestamp_issue"] = "stale"
      elif _namespace_has_timestamp_field(value):  # noqa: E111
        timestamp_anomalies[dog_id] = "missing"
        summary["timestamp_issue"] = "missing"

      per_dog[dog_id] = summary  # noqa: E111

    stats: StorageNamespaceStats = {
      "namespace": self._label,
      "dogs": len(per_dog),
      "entries": total_entries,
    }

    snapshot: StorageNamespaceSnapshot = {
      "namespace": self._label,
      "per_dog": per_dog,
    }

    per_dog_payload = cast(JSONMutableMapping, per_dog)
    diagnostics: CacheDiagnosticsMetadata = {
      "namespace": self._namespace,
      "storage_path": str(self._manager._namespace_path(self._namespace)),
      "per_dog": per_dog_payload,
    }

    if timestamp_anomalies:
      diagnostics["timestamp_anomalies"] = timestamp_anomalies  # noqa: E111

    return stats, snapshot, diagnostics

  def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:  # noqa: E111
    stats, snapshot, diagnostics = self._build_payload()
    diagnostics_payload = cast(CacheDiagnosticsMetadata, diagnostics)
    return CacheDiagnosticsSnapshot(
      stats=cast(JSONMutableMapping, dict(stats)),
      snapshot=cast(JSONMutableMapping, dict(snapshot)),
      diagnostics=diagnostics_payload,
    )

  def get_stats(self) -> JSONMutableMapping:  # noqa: E111
    stats, _snapshot, _diagnostics = self._build_payload()
    return cast(JSONMutableMapping, dict(stats))

  def get_diagnostics(self) -> CacheDiagnosticsMetadata:  # noqa: E111
    _stats, _snapshot, diagnostics = self._build_payload()
    return cast(CacheDiagnosticsMetadata, diagnostics)


def _serialize_datetime(value: datetime | None) -> str | None:
  """Convert a datetime into ISO format."""  # noqa: E111

  if value is None:  # noqa: E111
    return None
  return dt_util.as_utc(value).isoformat()  # noqa: E111


def _deserialize_datetime(value: Any) -> datetime | None:
  """Decode ISO formatted datetimes from JSON payloads."""  # noqa: E111

  if value is None:  # noqa: E111
    return None
  if isinstance(value, datetime):  # noqa: E111
    return dt_util.as_utc(value)
  parsed = dt_util.parse_datetime(str(value))  # noqa: E111
  if parsed is None:  # noqa: E111
    return None
  return dt_util.as_utc(parsed)  # noqa: E111


def _utcnow() -> datetime:
  """Return the current UTC time honoring patched Home Assistant helpers."""  # noqa: E111

  module = sys.modules.get("homeassistant.util.dt")  # noqa: E111
  if module is not None:  # noqa: E111
    candidate = getattr(module, "utcnow", None)
    if callable(candidate):
      result = candidate()  # noqa: E111
      if isinstance(result, datetime):  # noqa: E111
        return result
  return dt_util.utcnow()  # noqa: E111


def _serialize_timestamp(value: Any | None) -> str:
  """Return an ISO timestamp for ``value`` or ``utcnow`` when missing."""  # noqa: E111

  if isinstance(value, datetime):  # noqa: E111
    return dt_util.as_utc(value).isoformat()
  if value:  # noqa: E111
    parsed = _deserialize_datetime(value)
    if parsed:
      return parsed.isoformat()  # noqa: E111
  return _utcnow().isoformat()  # noqa: E111


def _coerce_mapping(value: JSONLikeMapping | None) -> JSONMutableMapping:
  """Return a shallow copy of ``value`` ensuring a mutable mapping."""  # noqa: E111

  if value is None:  # noqa: E111
    return {}
  if isinstance(value, dict):  # noqa: E111
    return cast(JSONMutableMapping, dict(value))
  return {key: cast(JSONValue, item) for key, item in value.items()}  # noqa: E111


def _merge_dicts(
  base: JSONLikeMapping | None,
  updates: JSONLikeMapping | None,
) -> JSONMutableMapping:
  """Deep merge ``updates`` into ``base`` using Home Assistant semantics."""  # noqa: E111

  merged = _coerce_mapping(base)  # noqa: E111
  if updates is None:  # noqa: E111
    return merged

  for key, value in updates.items():  # noqa: E111
    existing = merged.get(key)
    if isinstance(value, Mapping) and isinstance(existing, Mapping):
      merged[key] = cast(  # noqa: E111
        JSONValue,
        _merge_dicts(
          cast(JSONLikeMapping, existing),
          cast(JSONLikeMapping, value),
        ),
      )
    else:
      merged[key] = cast(JSONValue, value)  # noqa: E111
  return merged  # noqa: E111


def _limit_entries(
  entries: list[JSONMutableMapping],
  *,
  limit: int | None,
) -> list[JSONMutableMapping]:
  """Return ``entries`` optionally constrained to the most recent ``limit``."""  # noqa: E111

  if limit is None or limit <= 0:  # noqa: E111
    return entries
  return list(islice(entries, max(len(entries) - limit, 0), None))  # noqa: E111


def _coerce_health_payload(data: HealthData | JSONLikeMapping) -> JSONMutableMapping:
  """Return a dict payload from ``data`` regardless of the input type."""  # noqa: E111

  if isinstance(data, HealthData):  # noqa: E111
    raw_payload: dict[str, object] = {
      "timestamp": data.timestamp,
      "weight": data.weight,
      "temperature": data.temperature,
      "mood": data.mood,
      "activity_level": data.activity_level,
      "health_status": data.health_status,
      "symptoms": data.symptoms,
      "medication": data.medication,
      "note": data.note,
      "logged_by": data.logged_by,
      "heart_rate": data.heart_rate,
      "respiratory_rate": data.respiratory_rate,
    }
    payload = _coerce_json_mutable(
      cast(JSONMappingLike | JSONMutableMapping, raw_payload),
    )
  elif isinstance(data, Mapping):  # noqa: E111
    payload = _coerce_json_mutable(
      cast(JSONMappingLike | JSONMutableMapping, data),
    )
  else:  # pragma: no cover - guard for unexpected input  # noqa: E111
    raise TypeError("health data must be a mapping or HealthData instance")

  payload["timestamp"] = _serialize_timestamp(payload.get("timestamp"))  # noqa: E111
  return payload  # noqa: E111


def _coerce_medication_payload(data: JSONLikeMapping) -> JSONMutableMapping:
  """Return normalised medication data for persistence."""  # noqa: E111

  payload = _coerce_json_mutable(  # noqa: E111
    cast(JSONMappingLike | JSONMutableMapping, data),
  )
  payload["administration_time"] = _serialize_timestamp(  # noqa: E111
    payload.get("administration_time"),
  )
  payload.setdefault("logged_at", _utcnow().isoformat())  # noqa: E111
  return payload  # noqa: E111


def _normalise_history_entries(entries: object) -> list[JSONMutableMapping]:
  """Convert ``entries`` into JSON-compatible mutable mappings."""  # noqa: E111

  if not isinstance(entries, Iterable) or isinstance(entries, bytes | str):  # noqa: E111
    return []

  return [  # noqa: E111
    cast(
      JSONMutableMapping,
      normalize_value(
        _coerce_json_mutable(
          cast(JSONMappingLike | JSONMutableMapping, entry),
        ),
      ),
    )
    for entry in entries
    if isinstance(entry, Mapping)
  ]


def _default_session_id_generator() -> str:
  """Generate a unique identifier for grooming sessions."""  # noqa: E111

  from uuid import uuid4  # noqa: E111

  return uuid4().hex  # noqa: E111


@dataclass
class DogProfile:
  """Representation of all stored data for a single dog."""  # noqa: E111

  config: DogConfigData  # noqa: E111
  daily_stats: DailyStats  # noqa: E111
  feeding_history: list[JSONMutableMapping] = field(default_factory=list)  # noqa: E111
  walk_history: list[JSONMutableMapping] = field(default_factory=list)  # noqa: E111
  health_history: list[JSONMutableMapping] = field(default_factory=list)  # noqa: E111
  medication_history: list[JSONMutableMapping] = field(default_factory=list)  # noqa: E111
  poop_history: list[JSONMutableMapping] = field(default_factory=list)  # noqa: E111
  grooming_sessions: list[JSONMutableMapping] = field(default_factory=list)  # noqa: E111
  current_walk: WalkData | None = None  # noqa: E111

  @classmethod  # noqa: E111
  def from_storage(  # noqa: E111
    cls,
    config: JSONLikeMapping,
    stored: JSONLikeMapping | None,
  ) -> DogProfile:
    """Restore a profile from persisted JSON data."""

    daily_stats_payload: JSONMappingLike | JSONMutableMapping | None = None
    if stored:
      raw_daily_stats = stored.get("daily_stats")  # noqa: E111
      if isinstance(raw_daily_stats, Mapping):  # noqa: E111
        daily_stats_payload = cast(
          JSONMappingLike | JSONMutableMapping,
          raw_daily_stats,
        )
    feeding_history = (
      _normalise_history_entries(stored.get("feeding_history", ())) if stored else []
    )
    walk_history = (
      _normalise_history_entries(
        stored.get(
          "walk_history",
          (),
        ),
      )
      if stored
      else []
    )
    health_history = (
      _normalise_history_entries(stored.get("health_history", ())) if stored else []
    )
    medication_history = (
      _normalise_history_entries(stored.get("medication_history", ())) if stored else []
    )
    poop_history = (
      _normalise_history_entries(
        stored.get(
          "poop_history",
          (),
        ),
      )
      if stored
      else []
    )
    grooming_sessions = (
      _normalise_history_entries(stored.get("grooming_sessions", ())) if stored else []
    )

    try:
      daily_stats = DailyStats.from_dict(  # noqa: E111
        cast(
          JSONMappingLike | JSONMutableMapping,
          daily_stats_payload or {},
        ),
      )
    except Exception:  # pragma: no cover - only triggered by corrupt files
      daily_stats = DailyStats(date=_utcnow())  # noqa: E111

    typed_config = ensure_dog_config_data(
      cast(JSONMappingLike | JSONMutableMapping, config),
    )
    if typed_config is None:
      raise HomeAssistantError("Invalid dog configuration in storage")  # noqa: E111

    return cls(
      config=typed_config,
      daily_stats=daily_stats,
      feeding_history=feeding_history,
      walk_history=walk_history,
      health_history=health_history,
      medication_history=medication_history,
      poop_history=poop_history,
      grooming_sessions=grooming_sessions,
    )

  def as_dict(self) -> JSONMutableMapping:  # noqa: E111
    """Return a serialisable representation of the profile."""

    data: JSONMutableMapping = {
      "config": cast(JSONValue, self.config),
      "daily_stats": cast(JSONValue, self.daily_stats.as_dict()),
      "feeding_history": list(self.feeding_history),
      "walk_history": list(self.walk_history),
      "health_history": list(self.health_history),
      "medication_history": list(self.medication_history),
      "poop_history": list(self.poop_history),
      "grooming_sessions": list(self.grooming_sessions),
    }

    if self.current_walk is not None:
      data["current_walk"] = _serialize_walk(self.current_walk)  # noqa: E111

    return data


def _serialize_walk(walk: WalkData) -> JSONMutableMapping:
  """Serialise a :class:`WalkData` instance into JSON friendly data."""  # noqa: E111

  return {  # noqa: E111
    "start_time": _serialize_datetime(walk.start_time),
    "end_time": _serialize_datetime(walk.end_time),
    "duration": walk.duration,
    "distance": walk.distance,
    "route": [cast(JSONValue, point) for point in walk.route],
    "label": walk.label,
    "location": walk.location,
    "notes": walk.notes,
    "rating": walk.rating,
    "started_by": walk.started_by,
    "ended_by": walk.ended_by,
    "weather": walk.weather,
    "temperature": walk.temperature,
  }


def _history_sort_key(entry: Mapping[str, JSONValue], field: str) -> str:
  """Return a sortable key for history entries based on ``field``."""  # noqa: E111

  value = entry.get(field)  # noqa: E111
  return value if isinstance(value, str) else ""  # noqa: E111


class PawControlDataManager:
  """Store and retrieve dog related data for the integration."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    hass: HomeAssistant,
    entry_id: str | None = None,
    *,
    coordinator: Any | None = None,
    dogs_config: Sequence[RawDogConfig] | None = None,
  ) -> None:
    """Create a new data manager tied to ``entry_id`` and configuration."""

    self.hass = hass
    self._coordinator = coordinator
    typed_configs: dict[str, DogConfigData] = {}
    for config in dogs_config or []:
      if not isinstance(config, Mapping):  # noqa: E111
        continue
      candidate = cast(dict[str, JSONValue], dict(config))  # noqa: E111
      dog_id = candidate.get(DOG_ID_FIELD)  # noqa: E111
      if not isinstance(dog_id, str) or not dog_id:  # noqa: E111
        continue
      if not isinstance(candidate.get(DOG_NAME_FIELD), str):  # noqa: E111
        candidate[DOG_NAME_FIELD] = dog_id
      typed = ensure_dog_config_data(candidate)  # noqa: E111
      if typed is None:  # noqa: E111
        continue
      typed_configs[typed[DOG_ID_FIELD]] = typed  # noqa: E111

    self._dogs_config: dict[str, DogConfigData] = typed_configs

    if entry_id is None and coordinator is not None:
      entry = getattr(coordinator, "config_entry", None)  # noqa: E111
      entry_id_candidate = getattr(entry, "entry_id", None)  # noqa: E111
      if isinstance(entry_id_candidate, str):  # noqa: E111
        entry_id = entry_id_candidate

    self.entry_id = entry_id or "default"
    config_dir = Path(getattr(hass.config, "config_dir", "."))
    self._storage_dir = config_dir / DOMAIN
    self._storage_path = self._storage_dir / f"{self.entry_id}_{_STORAGE_FILENAME}"
    self._backup_path = self._storage_path.with_suffix(
      self._storage_path.suffix + ".backup",
    )

    self._dog_profiles: dict[str, DogProfile] = {}
    self._data_lock = asyncio.Lock()
    self._save_lock = asyncio.Lock()
    self._initialised = False
    self._namespace_locks: dict[str, asyncio.Lock] = {}
    self._namespace_state: dict[str, StorageNamespacePayload] = {}
    self._session_id_factory: Callable[
      [],
      str,
    ] = _default_session_id_generator

    self._ensure_metrics_containers()
    self._cache_monitors: dict[
      str,
      Callable[[], CacheDiagnosticsSnapshot],
    ] = {}
    self._cache_registrar_ids: set[int] = set()
    self._auto_register_cache_monitors()

  def _get_runtime_data(self) -> PawControlRuntimeData | None:  # noqa: E111
    """Return the runtime data container when available."""

    entry_id = getattr(self, "entry_id", None)
    if not entry_id:
      return None  # noqa: E111
    try:
      from .runtime_data import get_runtime_data  # noqa: E111
    except ImportError:  # pragma: no cover - defensive
      return None  # noqa: E111

    try:
      return get_runtime_data(self.hass, entry_id)  # noqa: E111
    except Exception:  # pragma: no cover - runtime retrieval errors
      return None  # noqa: E111

  def _get_namespace_lock(self, namespace: str) -> asyncio.Lock:  # noqa: E111
    """Return a lock used to guard namespace updates."""

    locks = getattr(self, "_namespace_locks", None)
    if locks is None:
      locks = {}  # noqa: E111
      self._namespace_locks = locks  # noqa: E111

    lock = locks.get(namespace)
    if lock is None:
      lock = asyncio.Lock()  # noqa: E111
      locks[namespace] = lock  # noqa: E111
    return lock

  async def _update_namespace_for_dog(  # noqa: E111
    self,
    namespace: str,
    dog_id: str,
    updater: Callable[[Any | None], Any | None],
  ) -> Any | None:
    """Update ``namespace`` payload for ``dog_id`` using ``updater``."""

    lock = self._get_namespace_lock(namespace)
    async with lock:
      data = await self._get_namespace_data(namespace)  # noqa: E111
      current = data.get(dog_id)  # noqa: E111
      updated = updater(current)  # noqa: E111
      if updated is None:  # noqa: E111
        data.pop(dog_id, None)
      else:  # noqa: E111
        data[dog_id] = updated
      await self._save_namespace(namespace, data)  # noqa: E111
      return updated  # noqa: E111

  def _ensure_profile(self, dog_id: str) -> DogProfile:  # noqa: E111
    """Return the profile for ``dog_id`` or raise ``HomeAssistantError``."""

    profile = self._dog_profiles.get(dog_id)
    if profile is None:
      raise HomeAssistantError(f"Unknown PawControl dog: {dog_id}")  # noqa: E111
    return profile

  async def _async_save_profile(self, dog_id: str, profile: DogProfile) -> None:  # noqa: E111
    """Persist ``profile`` for ``dog_id`` and update cached config."""

    self._dog_profiles[dog_id] = profile
    typed_config = ensure_dog_config_data(
      cast(Mapping[str, JSONValue], profile.config),
    )
    if typed_config is None:
      raise HomeAssistantError(f"Invalid PawControl profile for {dog_id}")  # noqa: E111

    raw_config = cast(JSONMutableMapping, _coerce_json_mutable(profile.config))
    for section, payload in raw_config.items():
      if section not in typed_config:  # noqa: E111
        typed_config[section] = payload

    profile.config = typed_config
    self._dogs_config[dog_id] = typed_config
    await self._async_save_dog_data(dog_id)

  def _ensure_metrics_containers(self) -> None:  # noqa: E111
    """Initialise in-memory metrics containers if missing."""

    if not hasattr(self, "_metrics"):
      self._metrics: JSONMutableMapping = {  # noqa: E111
        "operations": 0,
        "saves": 0,
        "errors": 0,
        "visitor_mode_last_runtime_ms": 0.0,
        "visitor_mode_avg_runtime_ms": 0.0,
      }
    if not hasattr(self, "_visitor_timings"):
      self._visitor_timings: deque[float] = deque(maxlen=50)  # noqa: E111
    if not hasattr(self, "_metrics_sink"):
      self._metrics_sink: CoordinatorMetrics | None = None  # noqa: E111

  def _increment_metric(self, key: str, *, increment: int = 1) -> None:  # noqa: E111
    """Increment a numeric metric stored in ``_metrics`` safely."""

    self._ensure_metrics_containers()
    current = self._metrics.get(key)
    base = current if isinstance(current, int | float) else 0
    self._metrics[key] = base + increment

  async def async_initialize(self) -> None:  # noqa: E111
    """Create storage folders and load persisted data."""

    try:
      self._storage_dir.mkdir(parents=True, exist_ok=True)  # noqa: E111
    except OSError as err:
      raise HomeAssistantError(  # noqa: E111
        f"Unable to prepare PawControl storage at {self._storage_dir}: {err}",
      ) from err

    stored = await self._async_load_storage()
    for dog_id, config in self._dogs_config.items():
      stored_payload = stored.get(dog_id)  # noqa: E111
      stored_mapping: JSONMappingLike | JSONMutableMapping | None  # noqa: E111
      if isinstance(stored_payload, Mapping):  # noqa: E111
        stored_mapping = cast(
          JSONMappingLike | JSONMutableMapping,
          stored_payload,
        )
      else:  # noqa: E111
        stored_mapping = None
      self._dog_profiles[dog_id] = DogProfile.from_storage(  # noqa: E111
        cast(JSONMappingLike | JSONMutableMapping, dict(config)),
        stored_mapping,
      )

    for namespace in (
      "visitor_mode",
      "module_state",
      "analysis_cache",
      "reports",
      "health_reports",
    ):
      try:  # noqa: E111
        await self._get_namespace_data(namespace)
      except HomeAssistantError:  # noqa: E111
        _LOGGER.debug(
          "Failed to preload namespace %s during initialization",
          namespace,
        )

    self._initialised = True

  async def async_shutdown(self) -> None:  # noqa: E111
    """Persist pending data on shutdown."""

    if not self._initialised:
      return  # noqa: E111

    for dog_id in list(self._dog_profiles):
      try:  # noqa: E111
        await self._async_save_dog_data(dog_id)
      except HomeAssistantError:  # noqa: E111
        _LOGGER.exception(
          "Failed to persist PawControl data for %s",
          dog_id,
        )

  async def async_log_feeding(self, dog_id: str, feeding: FeedingData) -> bool:  # noqa: E111
    """Record a feeding event."""

    if dog_id not in self._dog_profiles:
      return False  # noqa: E111

    async with self._data_lock:
      profile = self._dog_profiles[dog_id]  # noqa: E111
      self._maybe_roll_daily_stats(profile, feeding.timestamp)  # noqa: E111

      entry = _coerce_json_mutable(  # noqa: E111
        cast(
          JSONMappingLike | JSONMutableMapping,
          {
            "meal_type": feeding.meal_type,
            "portion_size": feeding.portion_size,
            "food_type": feeding.food_type,
            "timestamp": feeding.timestamp.isoformat(),
            "notes": feeding.notes,
            "logged_by": feeding.logged_by,
            "calories": feeding.calories,
            "automatic": feeding.automatic,
          },
        ),
      )
      profile.feeding_history.append(entry)  # noqa: E111
      profile.daily_stats.register_feeding(  # noqa: E111
        feeding.portion_size,
        feeding.timestamp,
      )

    try:
      await self._async_save_dog_data(dog_id)  # noqa: E111
    except HomeAssistantError:
      return False  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.error(  # noqa: E111
        "Failed to persist feeding data for %s: %s",
        dog_id,
        err,
      )
      return False  # noqa: E111
    return True

  async def async_set_visitor_mode(  # noqa: E111
    self,
    dog_id: str,
    settings: VisitorModeSettingsPayload | JSONLikeMapping | None = None,
    **kwargs: Any,
  ) -> bool:
    """Persist visitor mode configuration for ``dog_id``."""

    if not dog_id:
      raise ValueError("dog_id is required")  # noqa: E111

    payload: VisitorModeSettingsPayload | JSONLikeMapping | None = settings
    if payload is None and "visitor_data" in kwargs:
      payload = cast(VisitorModeSettingsPayload, kwargs["visitor_data"])  # noqa: E111
    elif payload is None and kwargs:
      payload = cast(VisitorModeSettingsPayload, kwargs)  # noqa: E111

    if payload is None:
      raise ValueError("Visitor mode payload is required")  # noqa: E111

    payload = _coerce_json_mutable(
      cast(JSONMappingLike | JSONMutableMapping, payload),
    )
    raw_timestamp = payload.pop("timestamp", None)
    timestamp_value: Any
    timestamp_value = _utcnow() if raw_timestamp is None else raw_timestamp
    serialized_timestamp = _serialize_timestamp(timestamp_value)

    namespace = "visitor_mode"
    self._ensure_metrics_containers()
    started = perf_counter()
    try:
      await self._update_namespace_for_dog(  # noqa: E111
        namespace,
        dog_id,
        lambda current: _merge_dicts(
          _coerce_mapping(
            current
            if isinstance(
              current,
              Mapping,
            )
            else {},
          ),
          payload,
        ),
      )
    except HomeAssistantError:
      self._increment_metric("errors")  # noqa: E111
      raise  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive guard
      self._increment_metric("errors")  # noqa: E111
      raise HomeAssistantError(  # noqa: E111
        f"Failed to update visitor mode for {dog_id}: {err}",
      ) from err
    else:
      self._record_visitor_metrics(perf_counter() - started)  # noqa: E111
      self._metrics["visitor_mode_last_updated"] = serialized_timestamp  # noqa: E111
    return True

  async def async_get_visitor_mode_status(  # noqa: E111
    self,
    dog_id: str,
  ) -> VisitorModeSettingsPayload:
    """Return the visitor mode status for ``dog_id``."""

    namespace = "visitor_mode"
    data = await self._get_namespace_data(namespace)
    entry = data.get(dog_id)
    if isinstance(entry, Mapping):
      return cast(VisitorModeSettingsPayload, dict(entry))  # noqa: E111
    return cast(VisitorModeSettingsPayload, {"enabled": False})

  def set_metrics_sink(self, metrics: CoordinatorMetrics | None) -> None:  # noqa: E111
    """Register a metrics sink used for coordinator diagnostics."""

    self._ensure_metrics_containers()
    self._metrics_sink = metrics

  def _auto_register_cache_monitors(self) -> None:  # noqa: E111
    """Register known coordinator caches for diagnostics snapshots."""

    coordinator = self._coordinator

    def _try_register(name: str, cache: Any) -> None:
      try:  # noqa: E111
        self.register_cache_monitor(name, cache)
      except (
        ValueError
      ):  # pragma: no cover - invalid names guarded earlier  # noqa: E111
        _LOGGER.debug(
          "Rejected cache monitor %s due to invalid name",
          name,
        )
      except Exception as err:  # pragma: no cover - diagnostics guard  # noqa: E111
        _LOGGER.debug(
          "Failed to register cache monitor %s: %s",
          name,
          err,
        )

    runtime = self._get_runtime_data()
    self._register_runtime_cache_monitors_internal(runtime)
    self._register_coordinator_cache_monitors(coordinator)

    storage_monitors = {
      "storage_visitor_mode": _StorageNamespaceCacheMonitor(
        self,
        "visitor_mode",
        "visitor_mode",
      ),
      "storage_module_state": _StorageNamespaceCacheMonitor(
        self,
        "module_state",
        "module_state",
      ),
      "storage_analysis_cache": _StorageNamespaceCacheMonitor(
        self,
        "analysis_cache",
        "analysis",
      ),
      "storage_reports": _StorageNamespaceCacheMonitor(
        self,
        "reports",
        "reports",
      ),
      "storage_health_reports": _StorageNamespaceCacheMonitor(
        self,
        "health_reports",
        "health_reports",
      ),
    }

    for name, monitor in storage_monitors.items():
      _try_register(name, monitor)  # noqa: E111

  def _register_manager_cache_monitors(  # noqa: E111
    self,
    manager: Any,
    *,
    prefix: str | None,
    label: str,
  ) -> None:
    """Register cache monitors exposed by ``manager`` if available."""

    if manager is None:
      _LOGGER.debug(  # noqa: E111
        "Skipping cache monitor registration for %s: manager missing",
        label,
      )
      return  # noqa: E111

    registrar = getattr(manager, "register_cache_monitors", None)
    if not callable(registrar):
      _LOGGER.debug(  # noqa: E111
        "Skipping cache monitor registration for %s: registrar unavailable",
        label,
      )
      return  # noqa: E111

    registrar_id = id(registrar)
    if registrar_id in self._cache_registrar_ids:
      _LOGGER.debug("Cache monitors for %s already registered", label)  # noqa: E111
      return  # noqa: E111

    try:
      if prefix is None:  # noqa: E111
        registrar(self)
      else:  # noqa: E111
        registrar(self, prefix=prefix)
    except Exception as err:  # pragma: no cover - diagnostics guard
      _LOGGER.debug("%s cache registration failed: %s", label, err)  # noqa: E111
    else:
      self._cache_registrar_ids.add(registrar_id)  # noqa: E111
      _LOGGER.debug("Registered cache monitors for %s", label)  # noqa: E111

  def _register_runtime_cache_monitors_internal(self, runtime: Any | None) -> None:  # noqa: E111
    """Register cache monitors exposed by runtime data containers."""

    if runtime is None:
      return  # noqa: E111

    self._register_manager_cache_monitors(
      getattr(runtime, "notification_manager", None),
      prefix=None,
      label="Notification",
    )
    self._register_manager_cache_monitors(
      getattr(runtime, "person_manager", None),
      prefix="person_entity",
      label="Person",
    )
    self._register_manager_cache_monitors(
      getattr(runtime, "helper_manager", None),
      prefix="helper_manager",
      label="Helper",
    )
    self._register_manager_cache_monitors(
      getattr(runtime, "script_manager", None),
      prefix="script_manager",
      label="Script",
    )
    self._register_manager_cache_monitors(
      getattr(runtime, "door_sensor_manager", None),
      prefix="door_sensor",
      label="Door sensor",
    )

  def _register_coordinator_cache_monitors(self, coordinator: Any | None) -> None:  # noqa: E111
    """Register cache monitors exposed directly on the coordinator."""

    if coordinator is None:
      return  # noqa: E111

    modules = getattr(coordinator, "_modules", None)
    if modules is not None:
      try:  # noqa: E111
        self.register_cache_monitor(
          "coordinator_modules",
          _CoordinatorModuleCacheMonitor(
            modules,
          ),
        )
      except Exception as err:  # pragma: no cover - diagnostics guard  # noqa: E111
        _LOGGER.debug(
          "Failed to register coordinator module cache monitor: %s",
          err,
        )

    tracker = getattr(coordinator, "_entity_budget", None)
    if tracker is not None:
      try:  # noqa: E111
        self.register_cache_monitor(
          "entity_budget_tracker",
          _EntityBudgetMonitor(tracker),
        )
      except Exception as err:  # pragma: no cover - diagnostics guard  # noqa: E111
        _LOGGER.debug(
          "Failed to register entity budget cache monitor: %s",
          err,
        )

    self._register_manager_cache_monitors(
      getattr(coordinator, "notification_manager", None),
      prefix=None,
      label="Notification",
    )
    self._register_manager_cache_monitors(
      getattr(coordinator, "person_manager", None),
      prefix="person_entity",
      label="Person",
    )
    self._register_manager_cache_monitors(
      getattr(coordinator, "helper_manager", None),
      prefix="helper_manager",
      label="Helper",
    )
    self._register_manager_cache_monitors(
      getattr(coordinator, "script_manager", None),
      prefix="script_manager",
      label="Script",
    )
    self._register_manager_cache_monitors(
      getattr(coordinator, "door_sensor_manager", None),
      prefix="door_sensor",
      label="Door sensor",
    )

  def register_runtime_cache_monitors(self, runtime: Any | None = None) -> None:  # noqa: E111
    """Register cache monitors from ``runtime`` or the stored runtime data."""

    if runtime is None:
      runtime = self._get_runtime_data()  # noqa: E111

    self._register_runtime_cache_monitors_internal(runtime)

  def register_cache_monitor(self, name: str, cache: CacheMonitorTarget) -> None:  # noqa: E111
    """Expose cache diagnostics in the format consumed by coordinator snapshots.

    Coordinators expect monitors to provide a structured payload containing a
    ``stats`` section (hit/miss counters), an optional ``snapshot`` describing
    the live cache state, and ``diagnostics`` metadata used by Home Assistant
    repairs. This helper normalises the callable surface offered by legacy
    caches so all registered providers deliver a consistent structure.
    """

    if not isinstance(name, str) or not name:
      raise ValueError("Cache monitor name must be a non-empty string")  # noqa: E111

    _LOGGER.debug("Registering cache monitor: %s", name)
    snapshot_method = getattr(cache, "coordinator_snapshot", None)
    stats_method = getattr(cache, "get_stats", None)
    if not callable(stats_method):
      stats_method = getattr(cache, "get_metrics", None)  # noqa: E111
    diagnostics_method = getattr(cache, "get_diagnostics", None)

    def _snapshot() -> CacheDiagnosticsSnapshot:
      try:  # noqa: E111
        if callable(snapshot_method):
          payload = snapshot_method()  # noqa: E111
          if isinstance(payload, CacheDiagnosticsSnapshot):  # noqa: E111
            return payload
          if isinstance(payload, Mapping):  # noqa: E111
            return CacheDiagnosticsSnapshot.from_mapping(payload)

        stats_payload: JSONMutableMapping | None = None
        if callable(stats_method):
          raw_stats = stats_method()  # noqa: E111
          if isinstance(raw_stats, Mapping):  # noqa: E111
            stats_payload = cast(
              JSONMutableMapping,
              dict(raw_stats),
            )
          elif raw_stats is not None:  # noqa: E111
            stats_payload = cast(JSONMutableMapping, raw_stats)

        diagnostics_payload: CacheDiagnosticsMetadata | None = None
        if callable(diagnostics_method):
          raw_diagnostics = diagnostics_method()  # noqa: E111
          if isinstance(raw_diagnostics, Mapping):  # noqa: E111
            diagnostics_payload = cast(
              CacheDiagnosticsMetadata,
              dict(raw_diagnostics),
            )
          elif raw_diagnostics is not None:  # noqa: E111
            diagnostics_payload = cast(
              CacheDiagnosticsMetadata,
              raw_diagnostics,
            )

        return CacheDiagnosticsSnapshot(
          stats=stats_payload,
          diagnostics=diagnostics_payload,
        )
      except Exception as err:  # pragma: no cover - diagnostics guard  # noqa: E111
        return CacheDiagnosticsSnapshot(error=str(err))

    self._cache_monitors[name] = _snapshot

  def cache_snapshots(self) -> CacheDiagnosticsMap:  # noqa: E111
    """Return registered cache diagnostics for coordinator use."""

    snapshots: CacheDiagnosticsMap = {}
    for name, provider in self._cache_monitors.items():
      try:  # noqa: E111
        snapshots[name] = provider()
      except Exception as err:  # pragma: no cover - defensive fallback  # noqa: E111
        snapshots[name] = CacheDiagnosticsSnapshot(error=str(err))
    return snapshots

  def cache_repair_summary(  # noqa: E111
    self,
    snapshots: CacheDiagnosticsMap | None = None,
  ) -> CacheRepairAggregate | None:
    """Return aggregated cache metrics suitable for Home Assistant repairs."""

    if snapshots is None:
      snapshots = self.cache_snapshots()  # noqa: E111

    if not snapshots:
      return None  # noqa: E111

    totals = CacheRepairTotals()

    caches_with_errors: list[str] = []
    caches_with_expired: list[str] = []
    caches_with_pending: list[str] = []
    caches_with_override_flags: list[str] = []
    caches_with_low_hit_rate: list[str] = []
    caches_with_timestamp_anomalies: list[str] = []
    anomalies: set[str] = set()
    issues: list[CacheRepairIssue] = []

    def _as_int(value: Any) -> int:
      number: float | None  # noqa: E111
      if is_number(value):  # noqa: E111
        number = float(value)
      elif isinstance(value, str):  # noqa: E111
        try:
          number = float(value.strip())  # noqa: E111
        except ValueError:
          number = None  # noqa: E111
      else:  # noqa: E111
        number = None

      if number is None or not isfinite(number):  # noqa: E111
        return 0

      return int(number)  # noqa: E111

    def _as_float(value: Any) -> float:
      number: float | None  # noqa: E111
      if is_number(value):  # noqa: E111
        number = float(value)
      elif isinstance(value, str):  # noqa: E111
        try:
          number = float(value.strip())  # noqa: E111
        except ValueError:
          number = None  # noqa: E111
      else:  # noqa: E111
        number = None

      if number is None or not isfinite(number):  # noqa: E111
        return 0.0

      return number  # noqa: E111

    for name, payload in snapshots.items():
      if not isinstance(name, str) or not name:  # noqa: E111
        continue

      if isinstance(payload, CacheDiagnosticsSnapshot):  # noqa: E111
        snapshot_payload = payload
      elif isinstance(payload, Mapping):  # noqa: E111
        snapshot_payload = CacheDiagnosticsSnapshot.from_mapping(
          payload,
        )
      else:  # noqa: E111
        snapshot_payload = CacheDiagnosticsSnapshot()

      stats_payload = snapshot_payload.stats  # noqa: E111
      if isinstance(stats_payload, Mapping):  # noqa: E111
        entries = _as_int(stats_payload.get("entries"))
        hits = _as_int(stats_payload.get("hits"))
        misses = _as_int(stats_payload.get("misses"))
        hit_rate = _as_float(stats_payload.get("hit_rate"))
      else:  # noqa: E111
        entries = hits = misses = 0
        hit_rate = 0.0

      if stats_payload is None or "hit_rate" not in stats_payload:  # noqa: E111
        loop_total_requests = hits + misses
        if loop_total_requests:
          hit_rate = round(hits / loop_total_requests * 100.0, 2)  # noqa: E111

      diagnostics_payload = snapshot_payload.diagnostics  # noqa: E111
      diagnostics_map = (  # noqa: E111
        diagnostics_payload
        if isinstance(
          diagnostics_payload,
          Mapping,
        )
        else {}
      )

      expired_entries = _as_int(diagnostics_map.get("expired_entries"))  # noqa: E111
      expired_override = _as_int(  # noqa: E111
        diagnostics_map.get("expired_via_override"),
      )
      pending_expired = _as_int(  # noqa: E111
        diagnostics_map.get("pending_expired_entries"),
      )
      pending_overrides = _as_int(  # noqa: E111
        diagnostics_map.get("pending_override_candidates"),
      )
      override_flags = _as_int(  # noqa: E111
        diagnostics_map.get("active_override_flags"),
      )

      timestamp_anomalies_payload = diagnostics_map.get(  # noqa: E111
        "timestamp_anomalies",
      )
      timestamp_anomaly_map: dict[str, str] = {}  # noqa: E111
      if isinstance(timestamp_anomalies_payload, Mapping):  # noqa: E111
        timestamp_anomaly_map = {
          str(dog_id): str(reason)
          for dog_id, reason in timestamp_anomalies_payload.items()
          if reason is not None
        }

      errors_payload = diagnostics_map.get("errors")  # noqa: E111
      if isinstance(errors_payload, Sequence) and not isinstance(  # noqa: E111
        errors_payload,
        str | bytes | bytearray,
      ):
        error_list = [str(item) for item in errors_payload if item is not None]
      elif isinstance(errors_payload, str):  # noqa: E111
        error_list = [errors_payload]
      elif errors_payload is None:  # noqa: E111
        error_list = []
      else:  # noqa: E111
        error_list = [str(errors_payload)]

      totals.entries += entries  # noqa: E111
      totals.hits += hits  # noqa: E111
      totals.misses += misses  # noqa: E111
      totals.expired_entries += expired_entries  # noqa: E111
      totals.expired_via_override += expired_override  # noqa: E111
      totals.pending_expired_entries += pending_expired  # noqa: E111
      totals.pending_override_candidates += pending_overrides  # noqa: E111
      totals.active_override_flags += override_flags  # noqa: E111

      low_hit_rate = False  # noqa: E111
      if hits + misses >= 5 and hit_rate < 60.0:  # noqa: E111
        low_hit_rate = True

      if error_list:  # noqa: E111
        caches_with_errors.append(name)
        anomalies.add(name)
      if expired_entries > 0:  # noqa: E111
        caches_with_expired.append(name)
        anomalies.add(name)
      if pending_expired > 0:  # noqa: E111
        caches_with_pending.append(name)
        anomalies.add(name)
      if override_flags > 0:  # noqa: E111
        caches_with_override_flags.append(name)
        anomalies.add(name)
      if low_hit_rate:  # noqa: E111
        caches_with_low_hit_rate.append(name)
        anomalies.add(name)
      if timestamp_anomaly_map:  # noqa: E111
        caches_with_timestamp_anomalies.append(name)
        anomalies.add(name)

      if (  # noqa: E111
        error_list
        or expired_entries
        or pending_expired
        or override_flags
        or low_hit_rate
        or timestamp_anomaly_map
      ):
        issue: CacheRepairIssue = {
          "cache": name,
          "entries": entries,
          "hits": hits,
          "misses": misses,
          "hit_rate": round(hit_rate, 2),
          "expired_entries": expired_entries,
          "expired_via_override": expired_override,
          "pending_expired_entries": pending_expired,
          "pending_override_candidates": pending_overrides,
          "active_override_flags": override_flags,
        }
        if error_list:
          issue["errors"] = error_list  # noqa: E111
        if timestamp_anomaly_map:
          issue["timestamp_anomalies"] = timestamp_anomaly_map  # noqa: E111
        issues.append(issue)

    total_requests: float = float(totals.hits) + float(totals.misses)
    if total_requests:
      totals.overall_hit_rate = round(  # noqa: E111
        float(totals.hits) / total_requests * 100.0,
        2,
      )

    severity = "info"
    if caches_with_errors:
      severity = "error"  # noqa: E111
    elif anomalies:
      severity = "warning"  # noqa: E111

    return CacheRepairAggregate(
      total_caches=len(snapshots),
      anomaly_count=len(anomalies),
      severity=severity,
      generated_at=_utcnow().isoformat(),
      totals=totals,
      caches_with_errors=caches_with_errors or None,
      caches_with_expired_entries=caches_with_expired or None,
      caches_with_pending_expired_entries=caches_with_pending or None,
      caches_with_override_flags=caches_with_override_flags or None,
      caches_with_low_hit_rate=caches_with_low_hit_rate or None,
      issues=issues or None,
    )

  def _record_visitor_metrics(self, duration: float) -> None:  # noqa: E111
    """Capture visitor-mode runtime metrics and forward to sinks."""

    self._ensure_metrics_containers()

    duration_ms = max(duration, 0.0) * 1000.0
    self._metrics["visitor_mode_last_runtime_ms"] = round(duration_ms, 3)

    self._visitor_timings.append(max(duration, 0.0))
    average_ms = (
      sum(self._visitor_timings) / len(self._visitor_timings) * 1000.0
      if self._visitor_timings
      else 0.0
    )
    self._metrics["visitor_mode_avg_runtime_ms"] = round(average_ms, 3)
    self._increment_metric("operations")

    sink = getattr(self, "_metrics_sink", None)
    if sink is not None:
      sink.record_visitor_timing(max(duration, 0.0))  # noqa: E111

  def get_daily_feeding_stats(self, dog_id: str) -> JSONMutableMapping | None:  # noqa: E111
    """Return aggregated feeding information for today."""

    profile = self._dog_profiles.get(dog_id)
    if profile is None:
      return None  # noqa: E111

    today = profile.daily_stats.date.date()
    feedings_today: list[JSONMutableMapping] = []
    total_calories = 0.0
    feeding_times: JSONMutableSequence = []
    for entry in profile.feeding_history:
      timestamp = _deserialize_datetime(entry.get("timestamp"))  # noqa: E111
      if not timestamp or timestamp.date() != today:  # noqa: E111
        continue
      feedings_today.append(entry)  # noqa: E111
      calories = entry.get("calories")  # noqa: E111
      if isinstance(calories, int | float):  # noqa: E111
        total_calories += float(calories)
      raw_timestamp = entry.get("timestamp")  # noqa: E111
      if isinstance(raw_timestamp, str):  # noqa: E111
        feeding_times.append(cast(JSONValue, raw_timestamp))

    return {
      "total_feedings": profile.daily_stats.feedings_count,
      "total_food_amount": round(profile.daily_stats.total_food_amount, 2),
      "total_calories": round(total_calories, 2),
      "feeding_times": feeding_times,
    }

  def get_feeding_history(  # noqa: E111
    self,
    dog_id: str,
    *,
    limit: int | None = None,
  ) -> list[JSONMutableMapping]:
    """Return historical feeding entries."""

    profile = self._dog_profiles.get(dog_id)
    if profile is None:
      return []  # noqa: E111

    history = list(profile.feeding_history)
    history.sort(
      key=lambda item: _history_sort_key(item, "timestamp"),
      reverse=True,
    )
    if limit is not None:
      return history[:limit]  # noqa: E111
    return history

  async def async_reset_dog_daily_stats(self, dog_id: str) -> None:  # noqa: E111
    """Reset the daily statistics for ``dog_id``."""

    profile = self._ensure_profile(dog_id)
    async with self._data_lock:
      profile.daily_stats = DailyStats(date=_utcnow())  # noqa: E111
    await self._async_save_profile(dog_id, profile)

  async def async_get_module_data(self, dog_id: str) -> JSONMutableMapping:  # noqa: E111
    """Return merged module configuration for ``dog_id``."""

    profile = self._ensure_profile(dog_id)
    namespace = await self._get_namespace_data("module_state")
    raw_overrides = namespace.get(dog_id)
    overrides = _coerce_mapping(
      raw_overrides if isinstance(raw_overrides, Mapping) else None,
    )
    modules_payload = (
      cast(JSONLikeMapping, profile.config["modules"])
      if isinstance(profile.config.get("modules"), Mapping)
      else None
    )
    modules = _coerce_mapping(modules_payload)
    return _merge_dicts(modules, overrides)

  async def async_get_module_history(  # noqa: E111
    self,
    module: str,
    dog_id: str,
    *,
    limit: int | None = None,
    since: datetime | str | None = None,
    until: datetime | str | None = None,
  ) -> list[JSONMutableMapping]:
    """Return stored history entries for ``module`` and ``dog_id``.

    The entries are normalised dictionaries sorted in reverse chronological
    order. Optional ``since``/``until`` bounds allow callers to apply window
    filtering without duplicating the timestamp parsing performed here.
    """

    module_key = module.lower()
    attr_info = _MODULE_HISTORY_ATTRS.get(module_key)
    if attr_info is None:
      return []  # noqa: E111

    attribute, timestamp_key = attr_info
    profile = self._dog_profiles.get(dog_id)
    if profile is None:
      return []  # noqa: E111

    entries = getattr(profile, attribute, None)
    if not isinstance(entries, list):
      return []  # noqa: E111

    since_bound = (
      _deserialize_datetime(
        since,
      )
      if since is not None
      else None
    )
    until_bound = (
      _deserialize_datetime(
        until,
      )
      if until is not None
      else None
    )

    prepared: list[tuple[datetime | None, JSONMutableMapping]] = []
    for entry in entries:
      if not isinstance(entry, Mapping):  # noqa: E111
        continue

      payload = _coerce_json_mutable(  # noqa: E111
        cast(JSONMappingLike | JSONMutableMapping, entry),
      )
      timestamp = _deserialize_datetime(payload.get(timestamp_key))  # noqa: E111
      normalised_payload = cast(  # noqa: E111
        JSONMutableMapping,
        normalize_value(payload),
      )

      if since_bound is not None and (timestamp is None or timestamp < since_bound):  # noqa: E111
        continue
      if until_bound is not None and (timestamp is None or timestamp > until_bound):  # noqa: E111
        continue

      prepared.append((timestamp, normalised_payload))  # noqa: E111

    def _sort_key(
      item: tuple[datetime | None, JSONMutableMapping],
    ) -> tuple[int, str]:
      timestamp, payload = item  # noqa: E111
      if timestamp is not None:  # noqa: E111
        return (1, timestamp.isoformat())

      raw_value = payload.get(timestamp_key)  # noqa: E111
      if isinstance(raw_value, datetime):  # noqa: E111
        return (1, raw_value.isoformat())
      if isinstance(raw_value, int | float):  # noqa: E111
        try:
          iso = datetime.fromtimestamp(float(raw_value)).isoformat()  # noqa: E111
        except OverflowError, ValueError:
          iso = ""  # noqa: E111
        return (0, iso)
      if isinstance(raw_value, str):  # noqa: E111
        return (0, raw_value)
      return (0, "")  # noqa: E111

    prepared.sort(key=_sort_key, reverse=True)

    ordered = [payload for _timestamp, payload in prepared]

    if limit is not None:
      return ordered[:limit]  # noqa: E111
    return ordered

  async def async_set_dog_power_state(self, dog_id: str, enabled: bool) -> None:  # noqa: E111
    """Persist the main power state for ``dog_id``."""

    def updater(current: Any | None) -> JSONMutableMapping:
      payload = _coerce_mapping(current)  # noqa: E111
      payload["main_power"] = bool(enabled)  # noqa: E111
      payload.setdefault("updated_at", _utcnow().isoformat())  # noqa: E111
      return payload  # noqa: E111

    await self._update_namespace_for_dog("module_state", dog_id, updater)

  async def async_set_gps_tracking(self, dog_id: str, enabled: bool) -> None:  # noqa: E111
    """Persist GPS tracking preference for ``dog_id``."""

    def updater(current: Any | None) -> JSONMutableMapping:
      payload = _coerce_mapping(current)  # noqa: E111
      gps_state_source = (  # noqa: E111
        cast(JSONLikeMapping, payload["gps"])
        if isinstance(payload.get("gps"), Mapping)
        else None
      )
      gps_state = _coerce_mapping(gps_state_source)  # noqa: E111
      gps_state["enabled"] = bool(enabled)  # noqa: E111
      gps_state["updated_at"] = _utcnow().isoformat()  # noqa: E111
      payload["gps"] = gps_state  # noqa: E111
      return payload  # noqa: E111

    await self._update_namespace_for_dog("module_state", dog_id, updater)

  async def async_log_poop_data(  # noqa: E111
    self,
    dog_id: str,
    poop_data: JSONLikeMapping,
    *,
    limit: int = 100,
  ) -> bool:
    """Store poop events for ``dog_id`` with optional history limit."""

    if dog_id not in self._dog_profiles:
      return False  # noqa: E111

    payload = _coerce_json_mutable(
      cast(JSONMappingLike | JSONMutableMapping, poop_data),
    )
    payload.setdefault("timestamp", _utcnow().isoformat())
    payload["timestamp"] = _serialize_timestamp(payload.get("timestamp"))

    async with self._data_lock:
      profile = self._dog_profiles[dog_id]  # noqa: E111
      profile.poop_history.append(payload)  # noqa: E111
      profile.poop_history[:] = _limit_entries(  # noqa: E111
        profile.poop_history,
        limit=limit,
      )

    try:
      await self._async_save_profile(dog_id, profile)  # noqa: E111
    except HomeAssistantError:
      return False  # noqa: E111
    return True

  async def async_start_grooming_session(  # noqa: E111
    self,
    dog_id: str,
    session_data: JSONLikeMapping,
    *,
    session_id: str | None = None,
  ) -> str:
    """Record the start of a grooming session and return the session id."""

    profile = self._ensure_profile(dog_id)
    payload = _coerce_json_mutable(
      cast(JSONMappingLike | JSONMutableMapping, session_data),
    )
    session_identifier = session_id or self._session_id_factory()
    payload.setdefault("session_id", session_identifier)
    payload.setdefault("started_at", _utcnow().isoformat())
    payload["started_at"] = _serialize_timestamp(payload.get("started_at"))

    async with self._data_lock:
      profile.grooming_sessions.append(payload)  # noqa: E111
      profile.grooming_sessions[:] = _limit_entries(  # noqa: E111
        profile.grooming_sessions,
        limit=50,
      )

    await self._async_save_profile(dog_id, profile)
    return session_identifier

  async def async_analyze_patterns(  # noqa: E111
    self,
    dog_id: str,
    analysis_type: str,
    *,
    days: int = 30,
  ) -> JSONMutableMapping:
    """Analyze historic data for ``dog_id``."""

    self._ensure_profile(dog_id)

    now = _utcnow()
    cutoff = now - timedelta(days=max(days, 1))
    tolerance = timedelta(seconds=1)

    result: JSONMutableMapping = {
      "dog_id": dog_id,
      "analysis_type": analysis_type,
      "days": days,
      "generated_at": now.isoformat(),
    }

    window_start = cutoff - tolerance

    if analysis_type in {"feeding", "comprehensive"}:
      feedings_raw = await self.async_get_module_history(  # noqa: E111
        MODULE_FEEDING,
        dog_id,
        since=window_start,
      )
      feedings: list[tuple[datetime, JSONMutableMapping]] = []  # noqa: E111
      for entry in feedings_raw:  # noqa: E111
        ts = _deserialize_datetime(entry.get("timestamp"))
        if ts:
          feedings.append((ts, entry))  # noqa: E111
      feedings.sort(key=lambda item: item[0])  # noqa: E111
      total = 0.0  # noqa: E111
      for _, entry in feedings:  # noqa: E111
        portion = entry.get("portion_size")
        if isinstance(portion, int | float):
          total += float(portion)  # noqa: E111
      result["feeding"] = {  # noqa: E111
        "entries": len(feedings),
        "total_portion_size": round(total, 2),
        "first_entry": feedings[0][1] if feedings else None,
        "last_entry": feedings[-1][1] if feedings else None,
      }

    if analysis_type in {"walking", "comprehensive"}:
      walks_raw = await self.async_get_module_history(  # noqa: E111
        MODULE_WALK,
        dog_id,
        since=window_start,
      )
      walks: list[tuple[datetime, JSONMutableMapping]] = []  # noqa: E111
      for entry in walks_raw:  # noqa: E111
        ts = _deserialize_datetime(entry.get("end_time"))
        if ts:
          walks.append((ts, entry))  # noqa: E111
      walks.sort(key=lambda item: item[0])  # noqa: E111
      total_distance = 0.0  # noqa: E111
      for _, entry in walks:  # noqa: E111
        distance = entry.get("distance")
        if isinstance(distance, int | float):
          total_distance += float(distance)  # noqa: E111
      result["walking"] = {  # noqa: E111
        "entries": len(walks),
        "total_distance": round(total_distance, 2),
      }

    if analysis_type in {"health", "comprehensive"}:
      health_raw = await self.async_get_module_history(  # noqa: E111
        MODULE_HEALTH,
        dog_id,
        since=window_start,
      )
      health_entries = [  # noqa: E111
        entry
        for entry in health_raw
        if _deserialize_datetime(entry.get("timestamp")) is not None
      ]
      result["health"] = {  # noqa: E111
        "entries": len(health_entries),
        "latest": health_entries[0] if health_entries else None,
      }

    await self._update_namespace_for_dog(
      "analysis_cache",
      dog_id,
      lambda current: _merge_dicts(
        _coerce_mapping(
          current
          if isinstance(
            current,
            Mapping,
          )
          else {},
        ),
        {analysis_type: result},
      ),
    )

    runtime = self._get_runtime_data()
    feeding_manager = getattr(runtime, "feeding_manager", None)
    if (
      feeding_manager
      and analysis_type in {"feeding", "comprehensive"}
      and hasattr(feeding_manager, "async_analyze_feeding_health")
    ):
      try:  # noqa: E111
        advanced = await feeding_manager.async_analyze_feeding_health(
          dog_id,
          days,
        )
      except Exception:  # pragma: no cover - non-critical fallback  # noqa: E111
        advanced = None
      if advanced:  # noqa: E111
        feeding_section = cast(
          JSONMutableMapping,
          result.setdefault("feeding", {}),
        )
        feeding_section["health_analysis"] = advanced

    return result

  async def async_generate_report(  # noqa: E111
    self,
    dog_id: str,
    report_type: str,
    *,
    include_recommendations: bool = True,
    days: int = 30,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
    include_sections: list[str] | None = None,
    format: str = "json",
    send_notification: bool | None = None,
  ) -> JSONMutableMapping:
    """Generate a summary report for ``dog_id``."""

    profile = self._ensure_profile(dog_id)
    now = _utcnow()
    report_window_start = (
      _deserialize_datetime(
        start_date,
      )
      if start_date
      else None
    )
    report_window_end = (
      _deserialize_datetime(
        end_date,
      )
      if end_date
      else None
    )
    if report_window_start is None:
      report_window_start = now - timedelta(days=max(days, 1))  # noqa: E111
    if report_window_end is None:
      report_window_end = now  # noqa: E111

    sections = set(include_sections or [])
    if not sections:
      sections = {"feeding", "walks", "health"}  # noqa: E111

    report: JSONMutableMapping = {
      "dog_id": dog_id,
      "report_type": report_type,
      "generated_at": now.isoformat(),
      "range": {
        "start": report_window_start.isoformat(),
        "end": report_window_end.isoformat(),
      },
      "sections": sorted(sections),
    }

    feeding_section: JSONMutableMapping | None = None
    walks_section: JSONMutableMapping | None = None

    def _within_window(timestamp: Any) -> bool:
      ts = _deserialize_datetime(timestamp)  # noqa: E111
      if ts is None:  # noqa: E111
        return False
      return report_window_start <= ts <= report_window_end  # noqa: E111

    if "feeding" in sections:
      feedings: list[JSONMutableMapping] = []  # noqa: E111
      total_portion = 0.0  # noqa: E111
      for entry in profile.feeding_history:  # noqa: E111
        if not _within_window(entry.get("timestamp")):
          continue  # noqa: E111
        feedings.append(entry)
        portion = entry.get("portion_size")
        if isinstance(portion, int | float):
          total_portion += float(portion)  # noqa: E111

      feeding_section = {  # noqa: E111
        "entries": len(feedings),
        "total_portion_size": round(total_portion, 2),
      }
      report["feeding"] = feeding_section  # noqa: E111

    if "walks" in sections:
      walks: list[JSONMutableMapping] = []  # noqa: E111
      total_distance = 0.0  # noqa: E111
      for entry in profile.walk_history:  # noqa: E111
        if not _within_window(entry.get("end_time")):
          continue  # noqa: E111
        walks.append(entry)
        distance = entry.get("distance")
        if isinstance(distance, int | float):
          total_distance += float(distance)  # noqa: E111

      walks_section = {  # noqa: E111
        "entries": len(walks),
        "total_distance": round(total_distance, 2),
      }
      report["walks"] = walks_section  # noqa: E111

    if "health" in sections:
      health_entries = [  # noqa: E111
        entry
        for entry in profile.health_history
        if _within_window(entry.get("timestamp"))
      ]
      report["health"] = {  # noqa: E111
        "entries": len(health_entries),
        "latest": health_entries[-1] if health_entries else None,
      }

    if include_recommendations:
      recommendations: list[str] = []  # noqa: E111
      if feeding_section is not None and feeding_section.get("entries") == 0:  # noqa: E111
        recommendations.append(
          "Log feeding events to improve analysis accuracy.",
        )
      if walks_section is not None and walks_section.get("entries") == 0:  # noqa: E111
        recommendations.append(
          "Schedule regular walks to maintain activity levels.",
        )
      report["recommendations"] = recommendations  # noqa: E111

    runtime = self._get_runtime_data()
    feeding_manager = getattr(runtime, "feeding_manager", None)
    if feeding_manager and hasattr(feeding_manager, "async_generate_health_report"):
      try:  # noqa: E111
        health_report = await feeding_manager.async_generate_health_report(
          dog_id,
        )
      except Exception:  # pragma: no cover - optional enhancement  # noqa: E111
        health_report = None
      if health_report:  # noqa: E111
        health_section = cast(
          JSONMutableMapping,
          report.setdefault("health", {}),
        )
        health_section["detailed_report"] = health_report

    await self._update_namespace_for_dog(
      "reports",
      dog_id,
      lambda current: _merge_dicts(
        _coerce_mapping(
          current
          if isinstance(
            current,
            Mapping,
          )
          else {},
        ),
        {report_type: report},
      ),
    )

    if send_notification:
      runtime = runtime or self._get_runtime_data()  # noqa: E111
      notification_manager = getattr(  # noqa: E111
        runtime,
        "notification_manager",
        None,
      )
      if notification_manager and hasattr(  # noqa: E111
        notification_manager,
        "async_send_notification",
      ):
        try:
          await notification_manager.async_send_notification(  # noqa: E111
            notification_type=NotificationType.REPORT_READY,
            title=(f"{profile.config.get('dog_name', dog_id)} {report_type} report"),
            message="Your PawControl report is ready for review.",
            priority=NotificationPriority.NORMAL,
          )
        except Exception:  # pragma: no cover - notification best-effort
          _LOGGER.debug(  # noqa: E111
            "Notification dispatch for report failed",
            exc_info=True,
          )

    return report

  async def async_generate_weekly_health_report(  # noqa: E111
    self,
    dog_id: str,
    *,
    include_medication: bool = True,
  ) -> JSONMutableMapping:
    """Generate a weekly health overview for ``dog_id``."""

    self._ensure_profile(dog_id)
    now = _utcnow()
    cutoff = now - timedelta(days=7)

    health_entries = await self.async_get_module_history(
      MODULE_HEALTH,
      dog_id,
      since=cutoff,
    )

    report: JSONMutableMapping = {
      "dog_id": dog_id,
      "generated_at": now.isoformat(),
      "entries": len(health_entries),
      "recent_weights": [
        entry.get("weight")
        for entry in health_entries
        if entry.get("weight") is not None
      ],
      "recent_temperatures": [
        entry.get("temperature") for entry in health_entries if entry.get("temperature")
      ],
    }

    if include_medication:
      medications = await self.async_get_module_history(  # noqa: E111
        MODULE_MEDICATION,
        dog_id,
        since=cutoff,
      )
      report["medication"] = {  # noqa: E111
        "entries": len(medications),
        "latest": medications[0] if medications else None,
      }

    await self._update_namespace_for_dog(
      "health_reports",
      dog_id,
      lambda current: _merge_dicts(
        _coerce_mapping(
          current
          if isinstance(
            current,
            Mapping,
          )
          else {},
        ),
        {"weekly": report},
      ),
    )

    return report

  async def async_export_data(  # noqa: E111
    self,
    dog_id: str,
    data_type: str,
    *,
    format: str = "json",
    days: int | None = None,
    date_from: datetime | str | None = None,
    date_to: datetime | str | None = None,
  ) -> Path:
    """Export stored data for ``dog_id`` leveraging the shared history helper."""

    _ = self._ensure_profile(dog_id)

    normalized_type = data_type.lower()

    async def _export_garden_sessions() -> Path:
      runtime_data = self._get_runtime_data()  # noqa: E111
      garden_manager = getattr(runtime_data, "garden_manager", None)  # noqa: E111
      if garden_manager is None:  # noqa: E111
        raise HomeAssistantError("Garden manager not available for export")
      return await garden_manager.async_export_sessions(  # noqa: E111
        dog_id,
        format=format,
        days=days,
        date_from=date_from,
        date_to=date_to,
      )

    async def _export_routes() -> Path:
      runtime_data = self._get_runtime_data()  # noqa: E111
      gps_manager = getattr(runtime_data, "gps_geofence_manager", None)  # noqa: E111
      if gps_manager is None:  # noqa: E111
        raise HomeAssistantError("GPS manager not available for route export")

      start = _deserialize_datetime(date_from) if date_from else None  # noqa: E111
      end = _deserialize_datetime(date_to) if date_to else None  # noqa: E111
      if start is None and days is not None:  # noqa: E111
        start = _utcnow() - timedelta(days=max(days, 0))
      if end is None:  # noqa: E111
        end = _utcnow()

      export_format = format.lower()  # noqa: E111
      if export_format not in {"gpx", "json", "csv"}:  # noqa: E111
        export_format = "gpx"

      export_payload = await gps_manager.async_export_routes(  # noqa: E111
        dog_id=dog_id,
        export_format=export_format,
        last_n_routes=0,
        date_from=start,
        date_to=end,
      )

      if export_payload is None:  # noqa: E111
        raise HomeAssistantError("No GPS routes available for export")

      export_dir = self._storage_dir / "exports"  # noqa: E111
      export_dir.mkdir(parents=True, exist_ok=True)  # noqa: E111
      filename = export_payload.get("filename")  # noqa: E111
      if not filename:  # noqa: E111
        timestamp = _utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"{self.entry_id}_{dog_id}_routes_{timestamp}.{export_format}"
      export_path = export_dir / filename  # noqa: E111

      def _route_payload_from_content(content: object) -> JSONValue:  # noqa: E111
        if isinstance(content, Mapping):
          return content  # noqa: E111
        if isinstance(content, Sequence) and not isinstance(
          content,
          str | bytes | bytearray,
        ):
          return list(content)  # noqa: E111
        if content is None:
          return {"raw_content": None}  # noqa: E111
        try:
          return cast(JSONValue, json.loads(str(content)))  # noqa: E111
        except json.JSONDecodeError:
          return {"raw_content": str(content)}  # noqa: E111

      def _write_route_export() -> None:  # noqa: E111
        content = export_payload.get("content")
        if export_format == "json":
          payload = _route_payload_from_content(content)  # noqa: E111
          export_path.write_text(  # noqa: E111
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
          )
        else:
          export_path.write_text(  # noqa: E111
            str(content or ""),
            encoding="utf-8",
          )

      await self._async_add_executor_job(_write_route_export)  # noqa: E111
      return export_path  # noqa: E111

    async def _export_single(export_type: str) -> Path:
      if export_type == "garden":  # noqa: E111
        return await _export_garden_sessions()
      if export_type == "routes":  # noqa: E111
        return await _export_routes()

      module_map: dict[str, tuple[str, str]] = {  # noqa: E111
        "feeding": (MODULE_FEEDING, "timestamp"),
        "walks": (MODULE_WALK, "end_time"),
        "walking": (MODULE_WALK, "end_time"),
        "health": (MODULE_HEALTH, "timestamp"),
        "medication": (MODULE_MEDICATION, "administration_time"),
      }

      module_info = module_map.get(export_type)  # noqa: E111
      if module_info is None:  # noqa: E111
        raise HomeAssistantError(f"Unsupported export data type: {data_type}")

      module_name, timestamp_key = module_info  # noqa: E111

      start = _deserialize_datetime(date_from) if date_from else None  # noqa: E111
      end = _deserialize_datetime(date_to) if date_to else None  # noqa: E111
      if start is None and days is not None:  # noqa: E111
        start = _utcnow() - timedelta(days=max(days, 0))
      if end is None:  # noqa: E111
        end = _utcnow()

      history = await self.async_get_module_history(  # noqa: E111
        module_name,
        dog_id,
        since=start,
        until=end,
      )

      def _sort_key(payload: JSONLikeMapping) -> tuple[int, str]:  # noqa: E111
        timestamp = _deserialize_datetime(payload.get(timestamp_key))
        if timestamp is not None:
          return (1, timestamp.isoformat())  # noqa: E111
        raw_value = payload.get(timestamp_key)
        if isinstance(raw_value, datetime):
          return (1, raw_value.isoformat())  # noqa: E111
        return (0, str(raw_value))

      entries: list[JSONMutableMapping] = [  # noqa: E111
        cast(
          JSONMutableMapping,
          normalize_value(
            _coerce_json_mutable(
              cast(JSONMappingLike | JSONMutableMapping, item),
            ),
          ),
        )
        for item in sorted(history, key=_sort_key)
      ]

      export_dir = self._storage_dir / "exports"  # noqa: E111
      export_dir.mkdir(parents=True, exist_ok=True)  # noqa: E111

      timestamp = _utcnow().strftime("%Y%m%d%H%M%S")  # noqa: E111
      normalized_format = format.lower()  # noqa: E111
      if normalized_format not in {"json", "csv", "markdown", "md", "txt"}:  # noqa: E111
        normalized_format = "json"

      extension = "md" if normalized_format == "markdown" else normalized_format  # noqa: E111
      filename = (  # noqa: E111
        f"{self.entry_id}_{dog_id}_{export_type}_{timestamp}.{extension}".replace(
          " ",
          "_",
        )
      )
      export_path = export_dir / filename  # noqa: E111

      if normalized_format == "csv":  # noqa: E111
        if entries:
          fieldnames = sorted(  # noqa: E111
            {key for entry in entries for key in entry},
          )
        else:
          fieldnames = []  # noqa: E111

        def _write_csv() -> None:
          with open(export_path, "w", newline="", encoding="utf-8") as handle:  # noqa: E111
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if fieldnames:
              writer.writeheader()  # noqa: E111
            writer.writerows(entries)

        await self._async_add_executor_job(_write_csv)
      elif normalized_format in {"markdown", "md", "txt"}:  # noqa: E111

        def _write_markdown() -> None:
          lines = [  # noqa: E111
            f"# {export_type.title()} export for {dog_id}",
            "",
          ]
          lines.extend(  # noqa: E111
            "- " + ", ".join(f"{k}: {v}" for k, v in entry.items()) for entry in entries
          )
          export_path.write_text("\n".join(lines), encoding="utf-8")  # noqa: E111

        await self._async_add_executor_job(_write_markdown)
      else:  # noqa: E111

        def _write_json() -> None:
          payload = cast(  # noqa: E111
            JSONMutableMapping,
            normalize_value(
              {
                "dog_id": dog_id,
                "data_type": export_type,
                "generated_at": _utcnow().isoformat(),
                "entries": entries,
              },
            ),
          )
          export_path.write_text(  # noqa: E111
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
          )

        await self._async_add_executor_job(_write_json)

      return export_path  # noqa: E111

    if normalized_type == "garden":
      return await _export_garden_sessions()  # noqa: E111

    if normalized_type == "routes":
      return await _export_routes()  # noqa: E111

    if normalized_type == "all":
      export_dir = self._storage_dir / "exports"  # noqa: E111
      export_dir.mkdir(parents=True, exist_ok=True)  # noqa: E111
      timestamp = _utcnow().strftime("%Y%m%d%H%M%S")  # noqa: E111
      export_path = export_dir / (f"{self.entry_id}_{dog_id}_all_{timestamp}.json")  # noqa: E111

      export_types = [  # noqa: E111
        "feeding",
        "walks",
        "health",
        "medication",
        "garden",
        "routes",
      ]
      exports: dict[str, str] = {}  # noqa: E111
      export_manifest = {  # noqa: E111
        "dog_id": dog_id,
        "data_type": "all",
        "generated_at": _utcnow().isoformat(),
        "exports": exports,
      }

      for export_type in export_types:  # noqa: E111
        exports[export_type] = str(await _export_single(export_type))

      await self._async_add_executor_job(  # noqa: E111
        export_path.write_text,
        json.dumps(export_manifest, ensure_ascii=False, indent=2),
        "utf-8",
      )
      return export_path  # noqa: E111

    return await _export_single(normalized_type)

  async def async_start_walk(  # noqa: E111
    self,
    dog_id: str,
    *,
    started_by: str = "",
    location: str = "",
    label: str = "",
    notes: str = "",
  ) -> bool:
    """Begin a walk for the provided dog."""

    if dog_id not in self._dog_profiles:
      return False  # noqa: E111

    async with self._data_lock:
      profile = self._dog_profiles[dog_id]  # noqa: E111
      if profile.current_walk is not None:  # noqa: E111
        return False

      profile.current_walk = WalkData(  # noqa: E111
        start_time=_utcnow(),
        location=location,
        label=label,
        started_by=started_by,
        notes=notes,
      )

    try:
      await self._async_save_dog_data(dog_id)  # noqa: E111
    except HomeAssistantError:
      return False  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.error(  # noqa: E111
        "Failed to persist walk data for %s: %s",
        dog_id,
        err,
      )
      return False  # noqa: E111
    return True

  async def async_end_walk(  # noqa: E111
    self,
    dog_id: str,
    *,
    ended_by: str = "",
    distance: float | None = None,
    rating: int | None = None,
    notes: str = "",
  ) -> bool:
    """Complete the current walk for ``dog_id``."""

    if dog_id not in self._dog_profiles:
      return False  # noqa: E111

    async with self._data_lock:
      profile = self._dog_profiles[dog_id]  # noqa: E111
      walk = profile.current_walk  # noqa: E111
      if walk is None:  # noqa: E111
        return False

      end_time = _utcnow()  # noqa: E111
      walk.end_time = end_time  # noqa: E111
      walk.ended_by = ended_by  # noqa: E111
      walk.notes = notes  # noqa: E111
      if rating is not None:  # noqa: E111
        walk.rating = rating
      if distance is not None:  # noqa: E111
        walk.distance = distance
      if walk.duration is None:  # noqa: E111
        duration = (end_time - walk.start_time).total_seconds()
        walk.duration = max(0, round(duration))

      profile.walk_history.append(_serialize_walk(walk))  # noqa: E111
      profile.current_walk = None  # noqa: E111
      profile.daily_stats.register_walk(  # noqa: E111
        walk.duration,
        walk.distance,
        end_time,
      )

    try:
      await self._async_save_dog_data(dog_id)  # noqa: E111
    except HomeAssistantError:
      return False  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.error(  # noqa: E111
        "Failed to persist walk route for %s: %s",
        dog_id,
        err,
      )
      return False  # noqa: E111
    return True

  def get_walk_history(  # noqa: E111
    self,
    dog_id: str,
    *,
    limit: int | None = None,
  ) -> list[JSONMutableMapping]:
    """Return stored walk history."""

    profile = self._dog_profiles.get(dog_id)
    if profile is None:
      return []  # noqa: E111

    history = list(profile.walk_history)
    history.sort(
      key=lambda item: _history_sort_key(
        item,
        "end_time",
      ),
      reverse=True,
    )
    if limit is not None:
      return history[:limit]  # noqa: E111
    return history

  async def async_update_walk_route(self, dog_id: str, location: GPSLocation) -> bool:  # noqa: E111
    """Add GPS information to the active walk."""

    profile = self._dog_profiles.get(dog_id)
    if profile is None or profile.current_walk is None:
      return False  # noqa: E111

    async with self._data_lock:
      walk = profile.current_walk  # noqa: E111
      if walk is None:  # noqa: E111
        return False
      route_point: WalkRoutePoint = {  # noqa: E111
        "latitude": location.latitude,
        "longitude": location.longitude,
        "timestamp": location.timestamp.isoformat(),
        "source": location.source,
      }
      if location.accuracy is not None:  # noqa: E111
        route_point["accuracy"] = location.accuracy
      if location.altitude is not None:  # noqa: E111
        route_point["altitude"] = location.altitude
      if location.battery_level is not None:  # noqa: E111
        route_point["battery_level"] = location.battery_level
      if location.signal_strength is not None:  # noqa: E111
        route_point["signal_strength"] = location.signal_strength

      walk.route.append(route_point)  # noqa: E111
      profile.daily_stats.register_gps_update()  # noqa: E111

    try:
      await self._async_save_dog_data(dog_id)  # noqa: E111
    except HomeAssistantError:
      return False  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.error(  # noqa: E111
        "Failed to persist health data for %s: %s",
        dog_id,
        err,
      )
      return False  # noqa: E111
    return True

  async def async_log_health_data(  # noqa: E111
    self,
    dog_id: str,
    health: HealthData | JSONLikeMapping,
  ) -> bool:
    """Record a health measurement."""

    if dog_id not in self._dog_profiles:
      return False  # noqa: E111

    payload = _coerce_health_payload(health)
    timestamp = (
      _deserialize_datetime(
        payload.get("timestamp"),
      )
      or _utcnow()
    )

    async with self._data_lock:
      profile = self._dog_profiles[dog_id]  # noqa: E111
      self._maybe_roll_daily_stats(profile, timestamp)  # noqa: E111

      entry = _coerce_json_mutable(payload)  # noqa: E111
      entry["timestamp"] = _serialize_timestamp(timestamp)  # noqa: E111

      profile.health_history.append(entry)  # noqa: E111
      profile.daily_stats.register_health_event(timestamp)  # noqa: E111

    try:
      await self._async_save_dog_data(dog_id)  # noqa: E111
    except HomeAssistantError:
      return False  # noqa: E111
    return True

  async def async_log_medication(  # noqa: E111
    self,
    dog_id: str,
    medication_data: JSONLikeMapping,
  ) -> bool:
    """Persist medication information for ``dog_id``."""

    if dog_id not in self._dog_profiles:
      return False  # noqa: E111

    payload = _coerce_medication_payload(medication_data)

    async with self._data_lock:
      profile = self._dog_profiles[dog_id]  # noqa: E111
      profile.medication_history.append(payload)  # noqa: E111

    try:
      await self._async_save_dog_data(dog_id)  # noqa: E111
    except HomeAssistantError:
      return False  # noqa: E111
    return True

  async def async_update_dog_data(  # noqa: E111
    self,
    dog_id: str,
    updates: JSONLikeMapping,
    *,
    persist: bool = True,
  ) -> bool:
    """Merge ``updates`` into the stored dog configuration."""

    if dog_id not in self._dog_profiles:
      return False  # noqa: E111

    async with self._data_lock:
      profile = self._dog_profiles[dog_id]  # noqa: E111
      config = _coerce_json_mutable(  # noqa: E111
        cast(JSONMappingLike | JSONMutableMapping, profile.config),
      )
      for section, payload in updates.items():  # noqa: E111
        if isinstance(payload, Mapping):
          existing = config.get(section)  # noqa: E111
          current = _coerce_mapping(  # noqa: E111
            cast(JSONLikeMapping | None, existing)
            if isinstance(existing, Mapping)
            else None,
          )
          config[section] = _merge_dicts(  # noqa: E111
            current,
            cast(JSONLikeMapping, payload),
          )
        else:
          config[section] = cast(JSONValue, payload)  # noqa: E111
      typed_config = ensure_dog_config_data(  # noqa: E111
        cast(JSONMappingLike | JSONMutableMapping, config),
      )
      if typed_config is None:  # noqa: E111
        raise HomeAssistantError(f"Invalid PawControl update for {dog_id}")

      for section, payload in config.items():  # noqa: E111
        if section not in typed_config:
          typed_config[section] = payload  # noqa: E111

      profile.config = typed_config  # noqa: E111
      self._dogs_config[dog_id] = typed_config  # noqa: E111

    if persist:
      try:  # noqa: E111
        await self._async_save_profile(dog_id, profile)
      except HomeAssistantError:  # noqa: E111
        return False
    else:
      self._dog_profiles[dog_id] = profile  # noqa: E111
      self._dogs_config[dog_id] = profile.config  # noqa: E111

    return True

  async def async_update_dog_profile(  # noqa: E111
    self,
    dog_id: str,
    profile_updates: JSONLikeMapping,
    *,
    persist: bool = True,
  ) -> bool:
    """Persist profile-specific updates for ``dog_id``."""

    return await self.async_update_dog_data(
      dog_id,
      {"profile": profile_updates},
      persist=persist,
    )

  def get_health_history(  # noqa: E111
    self,
    dog_id: str,
    *,
    limit: int | None = None,
  ) -> list[JSONMutableMapping]:
    """Return stored health entries."""

    profile = self._dog_profiles.get(dog_id)
    if profile is None:
      return []  # noqa: E111

    history = list(profile.health_history)
    history.sort(
      key=lambda item: _history_sort_key(item, "timestamp"),
      reverse=True,
    )
    if limit is not None:
      return history[:limit]  # noqa: E111
    return history

  def get_health_trends(  # noqa: E111
    self,
    dog_id: str,
    *,
    days: int = 7,
  ) -> JSONMutableMapping | None:
    """Analyse health entries recorded within ``days``."""

    profile = self._dog_profiles.get(dog_id)
    if profile is None:
      return None  # noqa: E111

    cutoff = _utcnow() - timedelta(days=days)
    tolerance = timedelta(seconds=1)
    relevant = [
      entry
      for entry in profile.health_history
      if (timestamp := _deserialize_datetime(entry.get("timestamp")))
      and timestamp >= cutoff - tolerance
    ]

    if not relevant:
      return cast(  # noqa: E111
        JSONMutableMapping,
        {
          "entries": 0,
          "weight_trend": None,
          "mood_distribution": {},
        },
      )

    weights: list[float] = []
    data_points: list[JSONMutableMapping] = []
    for entry in relevant:
      weight_value = entry.get("weight")  # noqa: E111
      if not isinstance(weight_value, int | float):  # noqa: E111
        continue
      weights.append(float(weight_value))  # noqa: E111
      data_points.append(  # noqa: E111
        cast(
          JSONMutableMapping,
          {
            "timestamp": entry.get("timestamp"),
            "weight": weight_value,
          },
        ),
      )
    if weights:
      change = weights[-1] - weights[0]  # noqa: E111
      if change > 0:  # noqa: E111
        direction = "increasing"
      elif change < 0:  # noqa: E111
        direction = "decreasing"
      else:  # noqa: E111
        direction = "stable"
      weight_trend: JSONMutableMapping | None = cast(  # noqa: E111
        JSONMutableMapping,
        {
          "start": weights[0],
          "end": weights[-1],
          "change": round(change, 2),
          "direction": direction,
          "data_points": data_points,
        },
      )
    else:
      weight_trend = None  # noqa: E111

    mood_distribution: dict[str, int] = {}
    for entry in relevant:
      raw_mood = entry.get("mood")  # noqa: E111
      mood = str(raw_mood if raw_mood is not None else "unknown")  # noqa: E111
      mood_distribution[mood] = mood_distribution.get(mood, 0) + 1  # noqa: E111

    status_progression = [
      str(status)
      for status in (entry.get("health_status") for entry in relevant)
      if isinstance(status, str)
    ]

    return cast(
      JSONMutableMapping,
      {
        "entries": len(relevant),
        "weight_trend": weight_trend,
        "mood_distribution": mood_distribution,
        "health_status_progression": status_progression,
      },
    )

  def get_metrics(self) -> DataManagerMetricsSnapshot:  # noqa: E111
    """Expose lightweight metrics for diagnostics tests."""

    metrics: DataManagerMetricsSnapshot = {
      "dogs": len(self._dog_profiles),
      "storage_path": str(self._storage_path),
      "cache_diagnostics": self.cache_snapshots(),
    }
    return metrics

  async def async_get_registered_dogs(self) -> list[str]:  # noqa: E111
    """Return the list of configured dog identifiers."""

    return list(self._dog_profiles)

  def _namespace_path(self, namespace: str) -> Path:  # noqa: E111
    """Return the file path used to persist a namespace payload."""

    safe_namespace = namespace.replace("/", "_")
    return self._storage_dir / f"{self.entry_id}_{safe_namespace}.json"

  async def _get_namespace_data(self, namespace: str) -> StorageNamespacePayload:  # noqa: E111
    """Read a JSON payload for ``namespace`` from disk."""

    path = self._namespace_path(namespace)
    try:
      if not Path.exists(path):  # noqa: E111
        self._namespace_state[namespace] = {}
        return {}
      contents = await self._async_add_executor_job(path.read_text, "utf-8")  # noqa: E111
    except FileNotFoundError:
      self._namespace_state[namespace] = {}  # noqa: E111
      return {}  # noqa: E111
    except OSError as err:
      raise HomeAssistantError(  # noqa: E111
        f"Unable to read PawControl {namespace} data: {err}",
      ) from err

    if not contents:
      self._namespace_state[namespace] = {}  # noqa: E111
      return {}  # noqa: E111

    try:
      payload = json.loads(contents)  # noqa: E111
    except json.JSONDecodeError:
      _LOGGER.warning(  # noqa: E111
        "Corrupted PawControl %s data detected at %s",
        namespace,
        path,
      )
      self._namespace_state[namespace] = {}  # noqa: E111
      return {}  # noqa: E111

    if isinstance(payload, dict):
      snapshot = cast(StorageNamespacePayload, dict(payload))  # noqa: E111
      self._namespace_state[namespace] = snapshot  # noqa: E111
      return snapshot  # noqa: E111

    self._namespace_state[namespace] = {}
    return {}

  async def _save_namespace(  # noqa: E111
    self,
    namespace: str,
    data: StorageNamespacePayload,
  ) -> None:
    """Persist a JSON payload for ``namespace`` to disk."""

    path = self._namespace_path(namespace)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    try:
      await self._async_add_executor_job(path.write_text, payload, "utf-8")  # noqa: E111
    except OSError as err:
      raise HomeAssistantError(  # noqa: E111
        f"Unable to persist PawControl {namespace} data: {err}",
      ) from err

    self._ensure_metrics_containers()
    self._increment_metric("saves")
    self._namespace_state[namespace] = cast(
      StorageNamespacePayload,
      dict(data),
    )

  async def _async_add_executor_job(  # noqa: E111
    self,
    func: Callable[..., ValueT],
    *args: Any,
  ) -> ValueT:
    """Run a sync function in the Home Assistant executor."""

    async_add_executor_job = getattr(self.hass, "async_add_executor_job", None)
    if callable(async_add_executor_job):
      return await async_add_executor_job(func, *args)  # noqa: E111
    return func(*args)

  async def _async_load_storage(self) -> JSONMutableMapping:  # noqa: E111
    """Load stored JSON data, falling back to the backup if required."""

    try:
      data = await self._async_add_executor_job(  # noqa: E111
        self._read_storage_payload,
        self._storage_path,
      )
      if data is None:  # noqa: E111
        return {}
      if isinstance(data, Mapping):  # noqa: E111
        return _coerce_json_mutable(
          cast(JSONMappingLike | JSONMutableMapping, data),
        )
      return {}  # noqa: E111
    except FileNotFoundError:
      return {}  # noqa: E111
    except json.JSONDecodeError:
      _LOGGER.warning(  # noqa: E111
        "Corrupted PawControl data detected at %s",
        self._storage_path,
      )
    except OSError as err:
      raise HomeAssistantError(f"Unable to read PawControl data: {err}") from err  # noqa: E111

    try:
      data = await self._async_add_executor_job(  # noqa: E111
        self._read_storage_payload,
        self._backup_path,
      )
      if data is None:  # noqa: E111
        return {}
      if isinstance(data, Mapping):  # noqa: E111
        return _coerce_json_mutable(
          cast(JSONMappingLike | JSONMutableMapping, data),
        )
      return {}  # noqa: E111
    except FileNotFoundError:
      return {}  # noqa: E111
    except json.JSONDecodeError:
      _LOGGER.warning(  # noqa: E111
        "Backup PawControl data is corrupted at %s",
        self._backup_path,
      )
    except OSError as err:
      raise HomeAssistantError(  # noqa: E111
        f"Unable to read PawControl backup: {err}",
      ) from err

    return {}

  async def _async_save_dog_data(self, dog_id: str) -> None:  # noqa: E111
    """Persist all dog data to disk."""

    async with self._save_lock:
      payload: JSONMutableMapping = {  # noqa: E111
        k: cast(JSONValue, profile.as_dict())
        for k, profile in self._dog_profiles.items()
      }
      try:  # noqa: E111
        await self._async_add_executor_job(
          self._write_storage,
          payload,
        )
      except OSError as err:  # noqa: E111
        raise HomeAssistantError(
          f"Failed to persist PawControl data: {err}",
        ) from err

  @staticmethod  # noqa: E111
  def _read_storage_payload(path: Path) -> Mapping[str, Any] | None:  # noqa: E111
    """Read a JSON payload from ``path`` when it exists."""

    if not path.exists():
      return None  # noqa: E111
    with path.open(encoding="utf-8") as handle:
      return json.load(handle)  # noqa: E111

  def _write_storage(self, payload: JSONMutableMapping) -> None:  # noqa: E111
    """Write data to the JSON storage file."""

    if self._storage_path.exists():
      self._create_backup()  # noqa: E111

    with open(self._storage_path, "w", encoding="utf-8") as handle:
      json.dump(payload, handle, ensure_ascii=False, indent=2)  # noqa: E111

  def _create_backup(self) -> None:  # noqa: E111
    """Create a best-effort backup copy of the current data file."""

    try:
      data = self._storage_path.read_bytes()  # noqa: E111
    except FileNotFoundError:
      return  # noqa: E111
    self._backup_path.write_bytes(data)

  @staticmethod  # noqa: E111
  def _maybe_roll_daily_stats(profile: DogProfile, timestamp: datetime) -> None:  # noqa: E111
    """Reset daily statistics when the day changes."""

    current_day = dt_util.as_utc(timestamp).date()
    if profile.daily_stats.date.date() != current_day:
      profile.daily_stats = DailyStats(date=dt_util.as_utc(timestamp))  # noqa: E111
