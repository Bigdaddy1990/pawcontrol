"""Helper classes and functions for Paw Control integration.

OPTIMIZED VERSION with async performance improvements, batch operations,
and memory-efficient data management for Platinum quality ambitions.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sized
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from functools import wraps
from time import perf_counter
from typing import Any, Final, ParamSpec, TypedDict, TypeVar, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import storage
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry, HomeAssistantError
from .const import (
    CONF_DOG_OPTIONS,
    CONF_DOGS,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    DATA_FILE_FEEDINGS,
    DATA_FILE_HEALTH,
    DATA_FILE_ROUTES,
    DATA_FILE_STATS,
    DATA_FILE_WALKS,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    EVENT_HEALTH_LOGGED,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
)
from .data_manager import _deserialize_datetime
from .types import (
    VALID_NOTIFICATION_PRIORITIES,
    CacheDiagnosticsMetadata,
    DogConfigData,
    HealthEvent,
    HealthHistoryEntry,
    HealthNamespaceMutable,
    JSONDateMapping,
    JSONLikeMapping,
    JSONMutableMapping,
    JSONValue,
    NotificationPriority,
    NotificationQueueStats,
    PerformanceMonitorSnapshot,
    QueuedNotificationPayload,
    StorageCacheValue,
    StorageNamespaceKey,
    StorageNamespacePayload,
    StorageNamespaceState,
    WalkEvent,
    WalkHistoryEntry,
    WalkNamespaceMutable,
    WalkNamespaceMutableEntry,
    WalkNamespaceValue,
    WalkStartPayload,
)
from .utils import (
    async_call_hass_service_if_available,
    async_fire_event,
    ensure_utc_datetime,
)

_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

# Storage version for data persistence
STORAGE_VERSION = 1

# OPTIMIZATION: Performance constants
MAX_MEMORY_CACHE_MB = 50  # Memory limit for caching
BATCH_SAVE_DELAY = 2.0  # Batch save delay in seconds
MAX_NOTIFICATION_QUEUE = 100  # Max queued notifications
DATA_CLEANUP_INTERVAL = 3600  # 1 hour cleanup interval
MAX_HISTORY_ITEMS = 1000  # Max items per dog per category

DEFAULT_NOTIFICATION_PRIORITY: Final[NotificationPriority] = "normal"


@dataclass(slots=True)
class PerformanceCounters:
    """Snapshot of performance counters maintained by the monitor."""

    operations: int = 0
    errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_operation_time: float = 0.0
    last_cleanup: datetime | None = None


DEFAULT_DATA_KEYS: Final[tuple[StorageNamespaceKey, ...]] = (
    "walks",
    "feedings",
    "health",
    "routes",
    "statistics",
)


class QueuedEvent(TypedDict):
    """Typed structure representing a queued domain event."""

    type: str
    dog_id: str
    data: JSONMutableMapping
    timestamp: str


class PerformanceMetrics(TypedDict):
    """Runtime metrics tracked by the performance monitor."""

    operations: int
    errors: int
    cache_hits: int
    cache_misses: int
    avg_operation_time: float
    last_cleanup: str | None


class OptimizedCacheStats(TypedDict):
    """Primary statistics reported by :class:`OptimizedDataCache`."""

    entries: int
    memory_mb: float
    total_accesses: int
    avg_accesses: float
    hits: int
    misses: int
    hit_rate: float


class OptimizedCacheMetrics(OptimizedCacheStats):
    """Extended metrics payload including override bookkeeping."""

    default_ttl_seconds: int
    tracked_keys: int
    override_candidates: int


class OptimizedCacheSnapshot(TypedDict):
    """Combined snapshot returned to coordinator diagnostics."""

    stats: OptimizedCacheMetrics
    diagnostics: CacheDiagnosticsMetadata


class OptimizedDataCache[ValueT]:
    """High-performance in-memory cache with automatic cleanup."""

    def __init__(
        self,
        max_memory_mb: int = MAX_MEMORY_CACHE_MB,
        default_ttl_seconds: int = 300,
    ) -> None:
        """Initialize cache with memory limits and TTL management."""
        self._cache: dict[str, ValueT] = {}
        self._timestamps: dict[str, datetime] = {}
        self._access_count: dict[str, int] = {}
        self._ttls: dict[str, int] = {}
        self._default_ttl_seconds = max(default_ttl_seconds, 0)
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._current_memory = 0
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()
        self._override_flags: dict[str, bool] = {}
        self._pending_expired: dict[str, bool] = {}
        self._diagnostics: CacheDiagnosticsMetadata = {
            "cleanup_invocations": 0,
            "expired_entries": 0,
            "expired_via_override": 0,
            "last_cleanup": None,
            "last_override_ttl": None,
            "last_expired_count": 0,
        }

    async def get(self, key: str, default: ValueT | None = None) -> ValueT | None:
        """Get cached value with access tracking."""
        async with self._lock:
            if key in self._cache:
                now = dt_util.utcnow()
                self._normalize_future_timestamp_locked(key, now)
                if self._is_expired_locked(key, now=now):
                    self._remove_locked(key)
                    self._misses += 1
                    return default

                self._access_count[key] = self._access_count.get(key, 0) + 1
                self._timestamps[key] = now
                self._hits += 1
                return self._cache[key]

            self._misses += 1
            return default

    async def set(self, key: str, value: ValueT, ttl_seconds: int = 300) -> None:
        """Set cached value with TTL and memory management."""
        async with self._lock:
            # Estimate memory usage
            value_size = self._estimate_size(cast(Any, value))

            # Clean up if needed
            while (
                self._current_memory + value_size > self._max_memory_bytes
                and self._cache
            ):
                await self._evict_lru()

            # Store value
            if key in self._cache:
                # Update existing
                old_size = self._estimate_size(cast(Any, self._cache[key]))
                self._current_memory -= old_size

            now = dt_util.utcnow()
            self._cache[key] = value
            self._timestamps[key] = now
            self._access_count[key] = self._access_count.get(key, 0) + 1
            self._ttls[key] = self._normalize_ttl(ttl_seconds)
            self._current_memory += value_size

    async def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if not self._timestamps:
            return

        # Find LRU key
        lru_key = min(
            self._timestamps.keys(),
            key=lambda k: (self._timestamps[k], self._access_count.get(k, 0)),
        )

        # Remove from cache
        self._remove_locked(lru_key)

    async def cleanup_expired(self, ttl_seconds: int | None = None) -> int:
        """Remove expired entries based on their per-key TTL."""
        override_ttl = None if ttl_seconds is None else self._normalize_ttl(ttl_seconds)
        async with self._lock:
            now = dt_util.utcnow()
            expired_keys: list[str] = []
            for key in tuple(self._cache.keys()):
                self._normalize_future_timestamp_locked(key, now)
                if self._is_expired_locked(
                    key, now, override_ttl if override_ttl is not None else None
                ):
                    expired_keys.append(key)

            override_expired = 0
            for key in expired_keys:
                if self._pending_expired.pop(key, False):
                    override_expired += 1
                self._remove_locked(key, record_expiration=False)

            self._diagnostics["cleanup_invocations"] += 1
            self._diagnostics["last_cleanup"] = now
            self._diagnostics["last_override_ttl"] = override_ttl
            self._diagnostics["last_expired_count"] = len(expired_keys)
            self._diagnostics["expired_entries"] = int(
                self._diagnostics.get("expired_entries", 0)
            ) + len(expired_keys)
            self._diagnostics["expired_via_override"] = (
                int(self._diagnostics.get("expired_via_override", 0)) + override_expired
            )

        return len(expired_keys)

    def _normalize_future_timestamp_locked(
        self, key: str, now: datetime | None = None
    ) -> None:
        """Clamp cached timestamps that drift into the future.

        When ``dt_util.utcnow`` is repeatedly monkeypatched during the test suite,
        cache entries can end up with timestamps that are ahead of the restored
        runtime. Normalising them prevents stale data from persisting beyond the
        intended TTL once the clock moves backwards again.
        """

        timestamp = self._timestamps.get(key)
        if timestamp is None:
            return

        if now is None:
            now = dt_util.utcnow()

        if timestamp <= now:
            return

        tolerance = timedelta(seconds=1)
        if timestamp - now > tolerance:
            _LOGGER.debug(
                "Normalising future timestamp for cache key %s (delta=%s)",
                key,
                timestamp - now,
            )

        self._timestamps[key] = now

    def _remove_locked(self, key: str, *, record_expiration: bool = True) -> None:
        """Remove a key from the cache while holding the lock."""
        if key in self._cache:
            value_size = self._estimate_size(cast(Any, self._cache[key]))
            self._current_memory -= value_size
            del self._cache[key]

        self._timestamps.pop(key, None)
        self._access_count.pop(key, None)
        self._ttls.pop(key, None)
        self._override_flags.pop(key, None)

        if record_expiration:
            expired_flag = self._pending_expired.pop(key, None)
            if expired_flag is not None:
                self._diagnostics["expired_entries"] = (
                    int(self._diagnostics.get("expired_entries", 0)) + 1
                )
                if expired_flag:
                    self._diagnostics["expired_via_override"] = (
                        int(self._diagnostics.get("expired_via_override", 0)) + 1
                    )
                self._diagnostics["last_expired_count"] = 1

    def _is_expired_locked(
        self,
        key: str,
        now: datetime | None = None,
        override_ttl: int | None = None,
    ) -> bool:
        """Return if a cached key is expired using stored TTL information."""

        timestamp = self._timestamps.get(key)
        if timestamp is None:
            override_applied = override_ttl is not None
            self._override_flags[key] = override_applied
            self._pending_expired[key] = override_applied
            return True

        stored_ttl = self._ttls.get(key, self._default_ttl_seconds)
        ttl = stored_ttl
        override_applied = False

        if override_ttl is not None:
            if override_ttl <= 0:
                ttl = 0
            elif stored_ttl <= 0:
                ttl = override_ttl
            else:
                ttl = min(stored_ttl, override_ttl)
            override_applied = ttl != stored_ttl

        if ttl <= 0:
            self._override_flags[key] = override_applied
            self._pending_expired.pop(key, None)
            return False

        if now is None:
            now = dt_util.utcnow()

        expired = now >= timestamp + timedelta(seconds=ttl)
        self._override_flags[key] = override_applied
        if expired:
            self._pending_expired[key] = override_applied
        else:
            self._pending_expired.pop(key, None)
        return expired

    def _normalize_ttl(self, ttl_seconds: int) -> int:
        """Normalize TTL seconds to a non-negative integer."""

        if ttl_seconds <= 0:
            return 0

        return int(ttl_seconds)

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of value."""
        try:
            import sys

            return sys.getsizeof(value)
        except Exception:
            # Fallback estimate
            if isinstance(value, str):
                return len(value) * 2  # Unicode chars
            if isinstance(value, list | tuple):
                return len(value) * 100  # Rough estimate
            if isinstance(value, dict):
                return len(value) * 200  # Rough estimate
            return 1024  # Default 1KB

    def get_stats(self) -> OptimizedCacheStats:
        """Get cache performance statistics with hit/miss tracking.

        Returns a dictionary that includes size metrics, access frequency, and
        high-level effectiveness indicators (hits, misses, hit rate).
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests else 0.0

        stats: OptimizedCacheStats = {
            "entries": len(self._cache),
            "memory_mb": round(self._current_memory / (1024 * 1024), 2),
            "total_accesses": sum(self._access_count.values()),
            "avg_accesses": (
                sum(self._access_count.values()) / len(self._access_count)
                if self._access_count
                else 0
            ),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 1),
        }
        return stats

    def get_metrics(self) -> OptimizedCacheMetrics:
        """Return an extended metrics payload for coordinator diagnostics."""

        stats = self.get_stats()
        metrics: OptimizedCacheMetrics = {
            **stats,
            "default_ttl_seconds": self._default_ttl_seconds,
            "tracked_keys": len(self._timestamps),
            "override_candidates": sum(
                1 for flag in self._override_flags.values() if flag
            ),
        }
        return metrics

    def get_diagnostics(self) -> CacheDiagnosticsMetadata:
        """Return override-aware cleanup metrics for diagnostics panels."""

        snapshot = cast(CacheDiagnosticsMetadata, dict(self._diagnostics))
        last_cleanup = snapshot.get("last_cleanup")
        snapshot["last_cleanup"] = (
            last_cleanup.isoformat() if isinstance(last_cleanup, datetime) else None
        )
        snapshot["pending_expired_entries"] = len(self._pending_expired)
        snapshot["pending_override_candidates"] = sum(
            1 for pending in self._pending_expired.values() if pending
        )
        snapshot["active_override_flags"] = sum(
            1 for flag in self._override_flags.values() if flag
        )
        return snapshot

    def coordinator_snapshot(self) -> OptimizedCacheSnapshot:
        """Return a combined metrics/diagnostics payload for coordinators."""

        snapshot: OptimizedCacheSnapshot = {
            "stats": self.get_metrics(),
            "diagnostics": self.get_diagnostics(),
        }
        return snapshot


class PawControlDataStorage:
    """OPTIMIZED: Manages persistent data storage with batching and caching."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize optimized storage manager."""
        self.hass = hass
        self.config_entry = config_entry
        self._stores: dict[StorageNamespaceKey, storage.Store] = {}
        self._cache: OptimizedDataCache[StorageCacheValue] = OptimizedDataCache()

        # OPTIMIZATION: Batch save mechanism
        self._dirty_stores: set[StorageNamespaceKey] = set()
        self._save_task: asyncio.Task | None = None
        self._save_lock = asyncio.Lock()

        runtime_data = getattr(config_entry, "runtime_data", None)
        manager = getattr(runtime_data, "data_manager", None)
        register_monitor = getattr(manager, "register_cache_monitor", None)
        if callable(register_monitor):
            register_monitor("storage_cache", self._cache)

        # Initialize storage for each data type
        self._initialize_stores()

        # Start cleanup task with Home Assistant helper for lifecycle tracking
        self._cleanup_task = hass.async_create_task(self._periodic_cleanup())

    def _initialize_stores(self) -> None:
        """Initialize storage stores with atomic writes."""
        store_configs: tuple[tuple[str, StorageNamespaceKey], ...] = (
            (DATA_FILE_WALKS, "walks"),
            (DATA_FILE_FEEDINGS, "feedings"),
            (DATA_FILE_HEALTH, "health"),
            (DATA_FILE_ROUTES, "routes"),
            (DATA_FILE_STATS, "statistics"),
        )

        for filename, store_key in store_configs:
            self._stores[store_key] = storage.Store(
                self.hass,
                STORAGE_VERSION,
                f"{DOMAIN}_{self.config_entry.entry_id}_{filename}",
                encoder=_data_encoder,
                atomic_writes=True,  # OPTIMIZATION: Ensure atomic writes
                minor_version=1,
            )

    async def async_load_all_data(self) -> StorageNamespaceState:
        """OPTIMIZED: Load with caching and concurrent operations."""
        try:
            # Check cache first
            cache_key = "all_data"
            cached_data = await self._cache.get(cache_key)
            if isinstance(cached_data, dict):
                return cast(StorageNamespaceState, cached_data)

            # Load all data stores concurrently
            load_tasks = [
                self._load_store_data_cached(store_key) for store_key in self._stores
            ]

            results = await asyncio.gather(*load_tasks, return_exceptions=True)

            data: StorageNamespaceState = {}
            for store_key, result in zip(self._stores.keys(), results, strict=False):
                if isinstance(result, BaseException):
                    _LOGGER.error("Failed to load %s data: %s", store_key, result)
                    data[store_key] = cast(StorageNamespacePayload, {})
                else:
                    payload = result if isinstance(result, dict) else {}
                    data[store_key] = cast(StorageNamespacePayload, payload)

            # Cache the loaded data
            await self._cache.set(cache_key, data, ttl_seconds=300)

            _LOGGER.debug("Loaded data for %d stores", len(data))
            return data

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Failed to load integration data: %s", err)
            raise HomeAssistantError(f"Data loading failed: {err}") from err

    async def _load_store_data_cached(
        self, store_key: StorageNamespaceKey
    ) -> StorageNamespacePayload:
        """Load data from store with caching."""
        # Check cache first
        cached = await self._cache.get(f"store_{store_key}")
        if isinstance(cached, dict):
            return cast(StorageNamespacePayload, cached)

        # Load from storage
        store = self._stores.get(store_key)
        if not store:
            return cast(StorageNamespacePayload, {})

        try:
            data = await store.async_load()
            result = data or {}

            # Cache the result
            payload = result if isinstance(result, dict) else {}
            await self._cache.set(f"store_{store_key}", payload, ttl_seconds=600)
            return cast(StorageNamespacePayload, payload)

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Failed to load %s store: %s", store_key, err)
            return cast(StorageNamespacePayload, {})

    async def async_save_data(
        self, store_key: StorageNamespaceKey, data: StorageNamespacePayload
    ) -> None:
        """OPTIMIZED: Save with batching to reduce I/O operations."""
        # Update cache immediately
        await self._cache.set(f"store_{store_key}", data, ttl_seconds=600)
        await self._cache.set("all_data", None)  # Invalidate full cache

        # Mark store as dirty for batch save
        self._dirty_stores.add(store_key)

        # Schedule batch save
        await self._schedule_batch_save()

    async def _schedule_batch_save(self) -> None:
        """Schedule a batch save operation."""
        if self._save_task and not self._save_task.done():
            return  # Already scheduled

        self._save_task = self.hass.async_create_task(self._batch_save())

    async def _batch_save(self, *, delay: float | None = BATCH_SAVE_DELAY) -> None:
        """Perform batch save with optional delay."""
        try:
            if delay and delay > 0:
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        async with self._save_lock:
            if not self._dirty_stores:
                return

            # Get current dirty stores
            stores_to_save = self._dirty_stores.copy()
            self._dirty_stores.clear()

            # Save all dirty stores concurrently
            save_tasks: list[Awaitable[None]] = []
            task_store_keys: list[StorageNamespaceKey] = []
            for store_key in stores_to_save:
                cached_data = await self._cache.get(f"store_{store_key}")
                if not isinstance(cached_data, dict):
                    continue

                payload = cast(StorageNamespacePayload, cached_data)
                save_tasks.append(self._save_store_immediate(store_key, payload))
                task_store_keys.append(store_key)

            if save_tasks:
                results = await asyncio.gather(*save_tasks, return_exceptions=True)

                # Log any errors while maintaining alignment with the executed tasks.
                for store_key, result in zip(task_store_keys, results, strict=True):
                    if isinstance(result, BaseException):
                        _LOGGER.error("Failed to save %s: %s", store_key, result)
                    else:
                        _LOGGER.debug("Saved %s store in batch", store_key)

    async def _save_store_immediate(
        self, store_key: StorageNamespaceKey, data: StorageNamespacePayload
    ) -> None:
        """Save store data immediately."""
        store = self._stores.get(store_key)
        if not store:
            raise HomeAssistantError(f"Store {store_key} not found")

        await store.async_save(data)

    async def async_cleanup_old_data(self, retention_days: int = 90) -> None:
        """OPTIMIZED: Clean up with batching and size limits."""
        cutoff_date = dt_util.utcnow() - timedelta(days=retention_days)

        # Clean up each data store
        cleanup_tasks = [
            self._cleanup_store_optimized(store_key, cutoff_date)
            for store_key in self._stores
        ]

        # Run cleanup tasks concurrently
        results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        total_cleaned = 0
        for store_key, result in zip(self._stores.keys(), results, strict=False):
            if isinstance(result, BaseException):
                _LOGGER.error("Failed to cleanup %s data: %s", store_key, result)
            else:
                assert isinstance(result, int)
                total_cleaned += result

        _LOGGER.debug("Cleaned up %d old entries across all stores", total_cleaned)

    async def _cleanup_store_optimized(
        self, store_key: StorageNamespaceKey, cutoff_date: datetime
    ) -> int:
        """Clean up store with size limits and optimization."""
        try:
            data = await self._load_store_data_cached(store_key)
            original_size = self._count_entries(data)

            # Clean old entries AND enforce size limits
            cleaned_data = self._cleanup_store_data(data, cutoff_date)
            cleaned_data = self._enforce_size_limits(cleaned_data)

            cleaned_size = self._count_entries(cleaned_data)

            if original_size != cleaned_size:
                await self.async_save_data(store_key, cleaned_data)
                return original_size - cleaned_size

            return 0

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Failed to cleanup %s data: %s", store_key, err)
            return 0

    def _cleanup_store_data(
        self, data: StorageNamespacePayload, cutoff_date: datetime
    ) -> StorageNamespacePayload:
        """Remove entries older than cutoff date with optimization."""
        if not isinstance(data, dict):
            return cast(StorageNamespacePayload, {})

        cleaned: StorageNamespacePayload = {}
        for key, value in data.items():
            if isinstance(value, list):
                # Clean list of entries
                cleaned_list: list[JSONValue] = []
                for entry in value:
                    if isinstance(entry, dict) and "timestamp" in entry:
                        entry_date = ensure_utc_datetime(entry.get("timestamp"))
                        if entry_date is None or entry_date >= cutoff_date:
                            cleaned_list.append(entry)
                    else:
                        # Keep non-timestamped entries
                        cleaned_list.append(entry)
                cleaned[key] = cleaned_list
            elif isinstance(value, dict) and "timestamp" in value:
                entry_date = ensure_utc_datetime(value.get("timestamp"))
                if entry_date is None or entry_date >= cutoff_date:
                    cleaned[key] = value
            else:
                # Keep non-timestamped entries
                cleaned[key] = value

        return cleaned

    def _enforce_size_limits(
        self, data: StorageNamespacePayload
    ) -> StorageNamespacePayload:
        """OPTIMIZATION: Enforce size limits to prevent memory bloat."""
        limited_data: StorageNamespacePayload = {}

        for key, value in data.items():
            if isinstance(value, list):
                if len(value) > MAX_HISTORY_ITEMS:
                    # Sort by timestamp (newest first) and keep most recent
                    try:
                        sorted_value = sorted(
                            value, key=lambda x: x.get("timestamp", ""), reverse=True
                        )
                        before = len(value)
                        limited_slice = sorted_value[:MAX_HISTORY_ITEMS]
                        limited_data[key] = cast(JSONValue, limited_slice)
                        _LOGGER.debug(
                            "Limited %s entries from %d to %d",
                            key,
                            before,
                            len(limited_slice),
                        )
                    except (TypeError, KeyError):
                        # Fallback to simple truncation
                        before = len(value)
                        truncated = value[-MAX_HISTORY_ITEMS:]
                        limited_data[key] = cast(JSONValue, truncated)
                        _LOGGER.debug(
                            "Limited %s entries from %d to %d",
                            key,
                            before,
                            len(truncated),
                        )
                else:
                    limited_data[key] = value
                continue

            limited_data[key] = value

        return limited_data

    def _count_entries(self, data: StorageNamespacePayload) -> int:
        """Count total entries in data structure."""
        count = 0
        for value in data.values():
            if isinstance(value, list | dict):
                sized_value = cast(Sized, value)
                count += len(sized_value)
            else:
                count += 1
        return count

    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup task."""
        while True:
            try:
                await asyncio.sleep(DATA_CLEANUP_INTERVAL)

                # Clean expired cache entries
                cleaned = await self._cache.cleanup_expired(ttl_seconds=600)
                if cleaned > 0:
                    _LOGGER.debug("Cleaned %d expired cache entries", cleaned)

                # Optional: Clean old data periodically
                # await self.async_cleanup_old_data()

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Periodic cleanup error: %s", err)

    async def async_shutdown(self) -> None:
        """Shutdown with final save."""
        # Cancel cleanup task
        if hasattr(self, "_cleanup_task") and self._cleanup_task:
            self._cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._save_task
            self._save_task = None

        # Final batch save
        if self._dirty_stores:
            await self._batch_save(delay=0)


class PawControlData:
    """OPTIMIZED: Main data management with performance improvements."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize optimized data manager."""
        self.hass = hass
        self.config_entry = config_entry
        self.storage = PawControlDataStorage(hass, config_entry)
        self._data: StorageNamespaceState = self._create_empty_data()
        self._dogs: list[DogConfigData] = self._coerce_dog_configs(
            config_entry.data.get(CONF_DOGS, [])
        )

        # OPTIMIZATION: Event queue for batch processing
        self._event_queue: deque[QueuedEvent] = deque(maxlen=1000)
        self._event_task: asyncio.Task | None = None
        self._valid_dog_ids: set[str] | None = None

    async def async_load_data(self) -> None:
        """Load data with performance monitoring."""
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        load_failed = False
        loaded_data: StorageNamespaceState

        try:
            loaded_data = await self.storage.async_load_all_data()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            load_failed = True
            _LOGGER.error("Failed to initialize data manager: %s", err)
            loaded_data = cast(StorageNamespaceState, self._create_empty_data())

        self._data = self._ensure_data_structure(loaded_data)
        self._hydrate_event_models()

        load_time = loop.time() - start_time
        if load_failed:
            _LOGGER.debug(
                "Initialized data manager with fallback data in %.2fs",
                load_time,
            )
        else:
            _LOGGER.debug(
                "Data manager initialized with %d data namespaces in %.2fs",
                len(self._data),
                load_time,
            )

        if self._event_task is None or self._event_task.done():
            event_coro = self._process_events()
            task: asyncio.Task[Any] | None = None

            hass_task_factory = getattr(self.hass, "async_create_task", None)
            if callable(hass_task_factory):
                try:
                    maybe_task = hass_task_factory(event_coro)
                except Exception:
                    event_coro.close()
                    raise

                if (
                    isinstance(maybe_task, asyncio.Task)
                    and type(maybe_task) is asyncio.Task
                ):
                    task = maybe_task
                    try:
                        scheduled_coro = task.get_coro()
                    except AttributeError:
                        scheduled_coro = None
                    if scheduled_coro is not event_coro:
                        event_coro.close()
                elif self._is_task_like(maybe_task):
                    # Test environments sometimes return task sentinels. Keep
                    # a reference to them so assertions can verify scheduling
                    # behaviour, but close the coroutine to avoid resource
                    # warnings as the sentinel will never execute it.
                    event_coro.close()
                    task = cast(asyncio.Task[Any], maybe_task)
                else:
                    # Some test harnesses return sentinel objects instead of
                    # real asyncio tasks. Close the coroutine to avoid a
                    # "coroutine was never awaited" warning and track the
                    # returned handle so callers can assert that scheduling
                    # occurred.
                    event_coro.close()
                    task = cast(asyncio.Task[Any], maybe_task)

            if task is None:
                event_coro = self._process_events()
                task = asyncio.create_task(event_coro)
                if not (isinstance(task, asyncio.Task) and type(task) is asyncio.Task):
                    event_coro.close()

            self._event_task = task

    @staticmethod
    def _is_task_like(candidate: Any) -> bool:
        """Return True if *candidate* behaves like an asyncio.Task."""

        return all(
            callable(getattr(candidate, attr, None))
            for attr in ("cancel", "done", "__await__")
        )

    @staticmethod
    def _coerce_dog_configs(raw: Any) -> list[DogConfigData]:
        """Return dog configuration entries as ``DogConfigData`` payloads."""

        if not isinstance(raw, list):
            return []

        return [
            cast(DogConfigData, dict(entry))
            for entry in raw
            if isinstance(entry, Mapping)
        ]

    @staticmethod
    def _empty_namespace_payload() -> StorageNamespacePayload:
        """Return an empty storage namespace mapping."""

        return cast(StorageNamespacePayload, {})

    @classmethod
    def _create_empty_data(cls) -> StorageNamespaceState:
        """Return a fresh default data structure for runtime use."""

        return {key: cls._empty_namespace_payload() for key in DEFAULT_DATA_KEYS}

    @staticmethod
    def _coerce_namespace_payload(value: Any, key: str) -> StorageNamespacePayload:
        """Return a storage namespace mapping, logging if payloads are invalid."""

        if isinstance(value, dict):
            return cast(StorageNamespacePayload, dict(value))

        if value not in (None, {}):
            _LOGGER.warning("Invalid data structure for '%s'; resetting namespace", key)
        return PawControlData._empty_namespace_payload()

    def _ensure_namespace(self, key: StorageNamespaceKey) -> StorageNamespacePayload:
        """Return the namespace payload for ``key``, creating a default if needed."""

        namespace = self._data.get(key)
        if isinstance(namespace, dict):
            return cast(StorageNamespacePayload, namespace)

        payload = self._empty_namespace_payload()
        self._data[key] = payload
        return payload

    def _ensure_data_structure(self, data: Any) -> StorageNamespaceState:
        """Normalize stored data to the expected namespace layout.

        The storage backend may return malformed payloads if the underlying
        file was manually edited or partially written. We rebuild the
        namespaces here so later operations can rely on their presence.
        """

        sanitized = self._create_empty_data()

        if not isinstance(data, Mapping):
            if data not in (None, {}):
                _LOGGER.warning(
                    "Unexpected data payload type %s; using default layout",
                    type(data).__name__,
                )
            return sanitized

        for key in DEFAULT_DATA_KEYS:
            sanitized[key] = self._coerce_namespace_payload(data.get(key), key)

        for key, value in data.items():
            if key not in sanitized:
                _LOGGER.debug(
                    "Skipping unsupported storage namespace '%s' with %s payload",
                    key,
                    type(value).__name__,
                )

        return sanitized

    def _hydrate_event_models(self) -> None:
        """Ensure stored history entries use structured dataclasses."""

        health_namespace_payload = self._ensure_namespace("health")
        health_namespace = cast(HealthNamespaceMutable, health_namespace_payload)
        for dog_id, history in list(health_namespace.items()):
            if not isinstance(history, list):
                health_namespace[dog_id] = cast(JSONValue, [])
                continue

            normalized_health_history: list[HealthHistoryEntry] = []
            for entry in history:
                normalized_entry = self._normalize_health_history_entry(dog_id, entry)
                if normalized_entry is not None:
                    normalized_health_history.append(normalized_entry)

            health_namespace[dog_id] = cast(JSONValue, normalized_health_history)

        walk_namespace_payload = self._ensure_namespace("walks")
        walk_namespace = cast(WalkNamespaceMutable, walk_namespace_payload)
        for dog_id, walk_data_any in list(walk_namespace.items()):
            if not isinstance(walk_data_any, dict):
                walk_namespace[dog_id] = cast(
                    WalkNamespaceMutableEntry,
                    {
                        "active": None,
                        "history": cast(list[WalkHistoryEntry], []),
                    },
                )
                continue

            walk_data = cast(WalkNamespaceMutableEntry, walk_data_any)

            history_value = walk_data.get("history")
            normalized_history: list[WalkHistoryEntry] = []
            if isinstance(history_value, list):
                for entry in history_value:
                    normalized_entry = self._normalize_walk_event_entry(dog_id, entry)
                    if normalized_entry is not None:
                        normalized_history.append(
                            cast(WalkHistoryEntry, normalized_entry)
                        )

            walk_data["history"] = cast(
                list[WalkHistoryEntry],
                self._sort_walk_history_payloads(normalized_history),
            )

            normalized_active = self._normalize_walk_event_entry(
                dog_id, walk_data.get("active")
            )
            walk_data["active"] = cast(WalkNamespaceValue, normalized_active)

    @staticmethod
    def _serialize_health_namespace(
        namespace: Mapping[str, object],
    ) -> StorageNamespacePayload:
        """Convert health namespace to storage-safe data."""

        serialized: StorageNamespacePayload = cast(StorageNamespacePayload, {})
        for dog_id, history in namespace.items():
            if not isinstance(history, list):
                normalized_entry = PawControlData._normalize_health_history_entry(
                    dog_id, history
                )
                if normalized_entry is None:
                    serialized[dog_id] = cast(JSONValue, history)
                    continue

                serialized[dog_id] = cast(JSONValue, [normalized_entry])
                continue

            serialized_history: list[JSONValue] = []
            for entry in history:
                normalized_entry = PawControlData._normalize_health_history_entry(
                    dog_id, entry
                )
                if normalized_entry is not None:
                    serialized_history.append(cast(JSONValue, normalized_entry))

            serialized[dog_id] = cast(JSONValue, serialized_history)
        return serialized

    @staticmethod
    def _serialize_walk_namespace(
        namespace: Mapping[str, object],
    ) -> StorageNamespacePayload:
        """Convert walk namespace to storage-safe data."""

        serialized: StorageNamespacePayload = cast(StorageNamespacePayload, {})
        for dog_id, walk_data in namespace.items():
            if not isinstance(walk_data, Mapping):
                serialized[dog_id] = cast(JSONValue, walk_data)
                continue

            walk_mapping = cast(Mapping[str, object], walk_data)

            serialized_walk: dict[str, JSONValue] = {
                key: cast(JSONValue, value)
                for key, value in walk_mapping.items()
                if key not in {"active", "history"}
            }

            normalized_active = PawControlData._normalize_walk_event_entry(
                dog_id, walk_mapping.get("active")
            )
            serialized_walk["active"] = cast(JSONValue, normalized_active)

            history_payload: list[WalkHistoryEntry] = []
            history_value = walk_mapping.get("history")
            if isinstance(history_value, list):
                for entry in history_value:
                    normalized_entry = PawControlData._normalize_walk_event_entry(
                        dog_id, entry
                    )
                    if normalized_entry is not None:
                        history_payload.append(cast(WalkHistoryEntry, normalized_entry))

            serialized_walk["history"] = cast(
                JSONValue,
                PawControlData._sort_walk_history_payloads(history_payload),
            )
            serialized[dog_id] = cast(JSONValue, serialized_walk)

        return serialized

    @staticmethod
    def _coerce_event_payload(payload: Mapping[str, object]) -> JSONMutableMapping:
        """Return a JSON-compatible mutable payload for queued events."""

        return cast(
            JSONMutableMapping,
            {str(key): cast(JSONValue, value) for key, value in payload.items()},
        )

    @staticmethod
    def _normalize_health_history_entry(
        dog_id: str,
        entry: object,
    ) -> JSONMutableMapping | None:
        """Return a storage-safe health history entry or ``None`` if invalid."""

        if isinstance(entry, HealthEvent):
            return cast(JSONMutableMapping, entry.as_dict())

        if isinstance(entry, Mapping):
            try:
                normalized = HealthEvent.from_raw(dog_id, cast(JSONDateMapping, entry))
            except Exception as err:
                _LOGGER.debug(
                    "Unable to normalize health history for %s: %s",
                    dog_id,
                    err,
                )
                sanitized = PawControlData._coerce_event_payload(entry)
                timestamp = sanitized.get("timestamp")
                if isinstance(timestamp, datetime):
                    sanitized["timestamp"] = timestamp.isoformat()
                return sanitized

            return cast(JSONMutableMapping, normalized.as_dict())

        _LOGGER.debug(
            "Skipping unsupported health history entry type: %s",
            type(entry).__name__,
        )
        return None

    @staticmethod
    def _normalize_walk_event_entry(
        dog_id: str,
        entry: object,
    ) -> JSONMutableMapping | None:
        """Return a storage-safe walk event entry or ``None`` if invalid."""

        if isinstance(entry, WalkEvent):
            return cast(JSONMutableMapping, entry.as_dict())

        if isinstance(entry, Mapping):
            try:
                normalized = WalkEvent.from_raw(
                    dog_id,
                    cast(JSONDateMapping, entry),
                )
            except Exception as err:
                _LOGGER.debug(
                    "Unable to normalize walk history for %s: %s",
                    dog_id,
                    err,
                )
                sanitized = PawControlData._coerce_event_payload(entry)
                timestamp = sanitized.get("timestamp")
                if isinstance(timestamp, datetime):
                    sanitized["timestamp"] = timestamp.isoformat()
                return sanitized

            return cast(JSONMutableMapping, normalized.as_dict())

        if entry is not None:
            _LOGGER.debug(
                "Skipping unsupported walk history entry type: %s",
                type(entry).__name__,
            )

        return None

    @staticmethod
    def _walk_history_sort_key(entry: Mapping[str, object]) -> tuple[int, str]:
        """Return sort key ensuring entries with timestamps come first."""

        timestamp = entry.get("timestamp")
        if isinstance(timestamp, str):
            return (1, timestamp)
        return (0, "")

    @staticmethod
    def _sort_walk_history_payloads(
        entries: list[WalkHistoryEntry],
    ) -> list[WalkHistoryEntry]:
        """Sort walk history newest first and enforce the history limit."""

        if not entries:
            return []

        sorted_entries = sorted(
            entries,
            key=PawControlData._walk_history_sort_key,
            reverse=True,
        )
        if len(sorted_entries) > MAX_HISTORY_ITEMS:
            return sorted_entries[:MAX_HISTORY_ITEMS]
        return sorted_entries

    async def async_log_feeding(
        self, dog_id: str, feeding_data: Mapping[str, object]
    ) -> None:
        """OPTIMIZED: Log feeding with event queue."""
        if not self._is_valid_dog_id(dog_id):
            raise HomeAssistantError(f"Invalid dog ID: {dog_id}")

        # Add to event queue for batch processing
        event_payload = self._coerce_event_payload(feeding_data)
        event: QueuedEvent = {
            "type": "feeding",
            "dog_id": dog_id,
            "data": event_payload,
            "timestamp": dt_util.utcnow().isoformat(),
        }

        self._event_queue.append(event)

    async def _process_events(self) -> None:
        """Process events in batches for better performance."""
        while True:
            try:
                if not self._event_queue:
                    await asyncio.sleep(1.0)  # Wait for events
                    continue

                # Process batch of events
                batch: list[QueuedEvent] = [
                    self._event_queue.popleft()
                    for _ in range(min(10, len(self._event_queue)))
                ]

                if batch:
                    await self._process_event_batch(batch)

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Event processing error: %s", err)
                await asyncio.sleep(5.0)  # Error recovery delay

    async def _process_event_batch(self, events: list[QueuedEvent]) -> None:
        """Process a batch of events efficiently."""
        # Group events by type and dog for efficient processing
        grouped_events: dict[str, list[QueuedEvent]] = {}

        for event in events:
            event_type = event["type"]
            dog_id = event["dog_id"]

            key = f"{event_type}_{dog_id}"
            group = grouped_events.get(key)
            if group is None:
                group = []
                grouped_events[key] = group
            group.append(event)

        # Process each group
        for group_events in grouped_events.values():
            event_type = group_events[0]["type"]

            if event_type == "feeding":
                await self._process_feeding_batch(group_events)
            elif event_type == "health":
                await self._process_health_batch(group_events)
            elif event_type == "walk":
                await self._process_walk_batch(group_events)

    async def _process_feeding_batch(self, events: list[QueuedEvent]) -> None:
        """Process feeding events in batch."""
        try:
            dog_id = events[0]["dog_id"]

            # Ensure data structure exists
            feedings_namespace = self._ensure_namespace("feedings")
            existing_history = feedings_namespace.get(dog_id)
            if isinstance(existing_history, list):
                dog_history = cast(list[JSONMutableMapping], existing_history)
            else:
                dog_history = []
                feedings_namespace[dog_id] = cast(JSONValue, dog_history)

            # Add all feeding entries
            for event in events:
                feeding_data = event["data"]
                if "timestamp" not in feeding_data:
                    feeding_data["timestamp"] = event["timestamp"]

                dog_history.append(feeding_data)

            # Enforce size limits
            if len(dog_history) > MAX_HISTORY_ITEMS:
                # Keep most recent entries
                dog_history[:] = dog_history[-MAX_HISTORY_ITEMS:]

            # Save to storage (will be batched)
            await self.storage.async_save_data("feedings", feedings_namespace)

            # Fire events for each feeding
            for event in events:
                await async_fire_event(
                    self.hass,
                    EVENT_FEEDING_LOGGED,
                    {
                        "dog_id": event["dog_id"],
                        **event["data"],
                    },
                )

            _LOGGER.debug("Processed %d feeding events for %s", len(events), dog_id)

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Failed to process feeding batch: %s", err)

    # Similar optimized methods for other event types...
    async def _process_health_batch(self, events: list[QueuedEvent]) -> None:
        """Process health events in batch."""
        if not events:
            return

        try:
            dog_id = events[0]["dog_id"]
        except (IndexError, KeyError):
            _LOGGER.error("Health event batch missing dog identifier")
            return

        try:
            health_namespace_payload = self._ensure_namespace("health")
            health_namespace = cast(HealthNamespaceMutable, health_namespace_payload)
            history_value = health_namespace.get(dog_id)
            if isinstance(history_value, list):
                dog_history = cast(list[HealthHistoryEntry], history_value)
            else:
                dog_history = []

            if dog_history:
                normalized_history: list[HealthHistoryEntry] = []
                for entry in dog_history:
                    normalized_entry = self._normalize_health_history_entry(
                        dog_id, entry
                    )
                    if normalized_entry is not None:
                        normalized_history.append(normalized_entry)
                dog_history = normalized_history

            health_namespace[dog_id] = cast(JSONValue, dog_history)

            new_events: list[JSONMutableMapping] = []

            for event in events:
                event_data: JSONMutableMapping = cast(
                    JSONMutableMapping, event.get("data", {})
                )
                timestamp = event.get("timestamp")
                health_event = HealthEvent.from_raw(dog_id, event_data, timestamp)
                event_payload = cast(JSONMutableMapping, health_event.as_dict())
                dog_history.append(event_payload)
                new_events.append(event_payload)

            if len(dog_history) > MAX_HISTORY_ITEMS:
                dog_history = dog_history[-MAX_HISTORY_ITEMS:]

            health_namespace[dog_id] = cast(JSONValue, dog_history)

            await self.storage.async_save_data(
                "health", self._serialize_health_namespace(health_namespace)
            )

            for payload in new_events:
                await async_fire_event(
                    self.hass,
                    EVENT_HEALTH_LOGGED,
                    {"dog_id": dog_id, **payload},
                )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Failed to process health event batch: %s", err)

    async def _process_walk_batch(self, events: list[QueuedEvent]) -> None:
        """Process walk events in batch."""
        if not events:
            return

        try:
            dog_id = events[0]["dog_id"]
        except (IndexError, KeyError):
            _LOGGER.error("Walk event batch missing dog identifier")
            return

        try:
            walk_namespace_payload = self._ensure_namespace("walks")
            walk_namespace = cast(WalkNamespaceMutable, walk_namespace_payload)
            walk_entry = walk_namespace.setdefault(
                dog_id,
                cast(
                    WalkNamespaceMutableEntry,
                    {
                        "active": None,
                        "history": cast(list[WalkHistoryEntry], []),
                    },
                ),
            )
            dog_walks = cast(WalkNamespaceMutableEntry, walk_entry)

            history_models: list[WalkEvent] = []
            history_value = dog_walks.get("history")
            if isinstance(history_value, list):
                for entry in history_value:
                    normalized_entry = self._normalize_walk_event_entry(dog_id, entry)
                    if normalized_entry is None:
                        continue
                    try:
                        history_models.append(
                            WalkEvent.from_raw(dog_id, normalized_entry)
                        )
                    except Exception as err:
                        _LOGGER.debug(
                            "Unable to hydrate walk history for %s: %s",
                            dog_id,
                            err,
                        )

            active_session: WalkEvent | None = None
            normalized_active = self._normalize_walk_event_entry(
                dog_id, dog_walks.get("active")
            )
            if normalized_active is not None:
                try:
                    active_session = WalkEvent.from_raw(dog_id, normalized_active)
                except Exception as err:
                    _LOGGER.debug(
                        "Unable to hydrate active walk session for %s: %s",
                        dog_id,
                        err,
                    )
                    normalized_active = None

            dog_walks["active"] = cast(WalkNamespaceValue, normalized_active)
            updated = False

            for event in events:
                event_data: JSONMutableMapping = cast(
                    JSONMutableMapping, event.get("data", {})
                )
                timestamp = event.get("timestamp")
                walk_event = WalkEvent.from_raw(dog_id, event_data, timestamp)
                walk_payload = cast(JSONMutableMapping, walk_event.as_dict())

                if walk_event.action == "start":
                    active_session = walk_event
                    dog_walks["active"] = cast(WalkNamespaceValue, walk_payload)
                    updated = True
                    await async_fire_event(
                        self.hass,
                        EVENT_WALK_STARTED,
                        {"dog_id": dog_id, **walk_payload},
                    )
                    continue

                if walk_event.action == "end":
                    if active_session is not None and (
                        walk_event.session_id is None
                        or walk_event.session_id == active_session.session_id
                    ):
                        merged_payload = {
                            **active_session.as_dict(),
                            **walk_event.as_dict(),
                        }
                        completed_walk = WalkEvent.from_raw(
                            dog_id,
                            cast(JSONMutableMapping, merged_payload),
                        )
                        history_models.append(completed_walk)
                        active_session = None
                        dog_walks["active"] = cast(WalkNamespaceValue, None)
                    else:
                        history_models.append(walk_event)

                    updated = True
                    await async_fire_event(
                        self.hass,
                        EVENT_WALK_ENDED,
                        {"dog_id": dog_id, **walk_payload},
                    )
                    continue

                if (
                    active_session is not None
                    and walk_event.session_id
                    and walk_event.session_id == active_session.session_id
                ):
                    active_session.merge(walk_event.as_dict(), walk_event.timestamp)
                    dog_walks["active"] = cast(
                        WalkNamespaceValue,
                        cast(JSONMutableMapping, active_session.as_dict()),
                    )
                    updated = True
                    continue

                history_models.append(walk_event)
                updated = True

            history_payloads: list[WalkHistoryEntry] = [
                cast(WalkHistoryEntry, model.as_dict()) for model in history_models
            ]
            dog_walks["history"] = cast(
                list[WalkHistoryEntry],
                self._sort_walk_history_payloads(history_payloads),
            )

            active_payload = (
                cast(JSONMutableMapping, active_session.as_dict())
                if active_session is not None
                else None
            )
            dog_walks["active"] = cast(WalkNamespaceValue, active_payload)

            if updated:
                await self.storage.async_save_data(
                    "walks", self._serialize_walk_namespace(walk_namespace)
                )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Failed to process walk event batch: %s", err)

    # Keep existing methods but add async optimizations where needed
    async def async_start_walk(
        self, dog_id: str, walk_data: WalkStartPayload | None = None
    ) -> None:
        """Start walk with immediate processing for real-time needs."""
        if not self._is_valid_dog_id(dog_id):
            raise HomeAssistantError(f"Invalid dog ID: {dog_id}")

        try:
            # Ensure walks data structure exists
            walk_namespace_payload = self._ensure_namespace("walks")
            walk_namespace = cast(WalkNamespaceMutable, walk_namespace_payload)
            walk_entry = walk_namespace.setdefault(
                dog_id,
                cast(
                    WalkNamespaceMutableEntry,
                    {
                        "active": None,
                        "history": cast(list[WalkHistoryEntry], []),
                    },
                ),
            )
            dog_walks = cast(WalkNamespaceMutableEntry, walk_entry)
            if not isinstance(dog_walks.get("history"), list):
                dog_walks["history"] = cast(list[WalkHistoryEntry], [])

            # Check if a walk is already active
            active_payload = self._normalize_walk_event_entry(
                dog_id, dog_walks.get("active")
            )
            active_entry: WalkEvent | None = None
            if active_payload is not None:
                try:
                    active_entry = WalkEvent.from_raw(dog_id, active_payload)
                except Exception:
                    active_payload = None
                    active_entry = None

            dog_walks["active"] = cast(WalkNamespaceValue, active_payload)

            if active_entry is not None:
                raise HomeAssistantError(f"Walk already active for {dog_id}")

            walk_payload: JSONMutableMapping
            if walk_data is None:
                walk_payload = cast(JSONMutableMapping, {})
            else:
                walk_payload = cast(JSONMutableMapping, dict(walk_data))

            # Set active walk
            timestamp_raw = walk_payload.get("timestamp")
            timestamp_override = (
                timestamp_raw if isinstance(timestamp_raw, str) else None
            )

            active_walk = WalkEvent.from_raw(
                dog_id,
                walk_payload,
                timestamp_override,
            )
            dog_walks["active"] = cast(
                WalkNamespaceValue, cast(JSONMutableMapping, active_walk.as_dict())
            )

            # Save immediately for real-time operations
            await self.storage.async_save_data(
                "walks", self._serialize_walk_namespace(walk_namespace)
            )

            # Fire event
            await async_fire_event(
                self.hass,
                EVENT_WALK_STARTED,
                {"dog_id": dog_id, **active_walk.as_dict()},
            )

            _LOGGER.debug("Started walk for %s", dog_id)

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Failed to start walk for %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to start walk: {err}") from err

    def _is_valid_dog_id(self, dog_id: str) -> bool:
        """Validate dog ID with caching."""
        # Cache valid dog IDs for performance
        if self._valid_dog_ids is None:
            self._valid_dog_ids = {dog["dog_id"] for dog in self._dogs}

        return dog_id in self._valid_dog_ids

    async def async_shutdown(self) -> None:
        """Shutdown with cleanup."""
        # Cancel event processing
        if self._event_task:
            self._event_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._event_task
            self._event_task = None

        # Process remaining events
        if self._event_queue:
            remaining = list(self._event_queue)
            if remaining:
                await self._process_event_batch(remaining)

        # Shutdown storage
        await self.storage.async_shutdown()


class PawControlNotificationManager:
    """OPTIMIZED: Async notification manager with queue management."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize optimized notification manager."""
        self.hass = hass
        self.config_entry = config_entry

        # OPTIMIZATION: Use deque for efficient queue operations
        self._notification_queue: deque[QueuedNotificationPayload] = deque(
            maxlen=MAX_NOTIFICATION_QUEUE
        )
        self._high_priority_queue: deque[QueuedNotificationPayload] = deque(
            maxlen=50
        )  # Separate urgent queue

        # Async processing
        self._processor_task: asyncio.Task | None = None
        self._processing_lock = asyncio.Lock()
        self._quiet_hours_cache: dict[str, tuple[bool, datetime]] = {}

        self._setup_async_processor()

    def _setup_async_processor(self) -> None:
        """Set up async notification processor."""
        self._processor_task = self.hass.async_create_task(
            self._async_process_notifications()
        )

    async def _async_process_notifications(self) -> None:
        """OPTIMIZED: Async notification processor with prioritization."""
        while True:
            try:
                # Process high priority first
                if self._high_priority_queue:
                    notification = self._high_priority_queue.popleft()
                    await self._send_notification_now(notification)
                    continue

                # Process normal priority (with rate limiting)
                if self._notification_queue:
                    # Rate limit: max 3 notifications per 30 seconds
                    batch_size = min(3, len(self._notification_queue))
                    batch = [
                        self._notification_queue.popleft()
                        for _ in range(batch_size)
                        if self._notification_queue
                    ]

                    # Send batch concurrently
                    if batch:
                        await asyncio.gather(
                            *[self._send_notification_now(notif) for notif in batch],
                            return_exceptions=True,
                        )

                    await asyncio.sleep(30)  # Rate limiting delay
                else:
                    await asyncio.sleep(1)  # No notifications to process

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Notification processor error: %s", err)
                await asyncio.sleep(5)  # Error recovery

    @staticmethod
    def _coerce_notification_data(data: JSONLikeMapping) -> JSONMutableMapping:
        """Return JSON-compatible notification extras."""

        return cast(
            JSONMutableMapping,
            {str(key): cast(JSONValue, value) for key, value in data.items()},
        )

    async def async_send_notification(
        self,
        dog_id: str,
        title: str,
        message: str,
        priority: NotificationPriority = DEFAULT_NOTIFICATION_PRIORITY,
        data: JSONLikeMapping | None = None,
    ) -> None:
        """OPTIMIZED: Send notification with async queuing."""
        if priority not in VALID_NOTIFICATION_PRIORITIES:
            _LOGGER.warning(
                "Unknown notification priority '%s'; falling back to normal",
                priority,
            )
            priority_value: NotificationPriority = DEFAULT_NOTIFICATION_PRIORITY
        else:
            priority_value = priority

        if not self._should_send_notification(dog_id, priority_value):
            _LOGGER.debug("Notification suppressed due to quiet hours")
            return

        notification: QueuedNotificationPayload = {
            "dog_id": dog_id,
            "title": title,
            "message": message,
            "priority": priority_value,
            "timestamp": dt_util.utcnow().isoformat(),
        }

        if data:
            notification["data"] = self._coerce_notification_data(data)
        else:
            notification["data"] = cast(JSONMutableMapping, {})

        # Route to appropriate queue
        if priority_value in ("high", "urgent"):
            self._high_priority_queue.append(notification)
        else:
            self._notification_queue.append(notification)

    async def _send_notification_now(
        self, notification: QueuedNotificationPayload
    ) -> None:
        """OPTIMIZED: Send notification with error handling."""
        async with self._processing_lock:
            try:
                # Determine notification service
                service_data = {
                    "title": notification["title"],
                    "message": notification["message"],
                    "notification_id": f"pawcontrol_{notification['dog_id']}_{notification['timestamp']}",
                }

                # Add priority-specific styling
                if notification["priority"] == "urgent":
                    service_data["message"] = f"🚨 {service_data['message']}"
                elif notification["priority"] == "high":
                    service_data["message"] = f"⚠️ {service_data['message']}"

                # Send with timeout to prevent blocking
                executed = await asyncio.wait_for(
                    async_call_hass_service_if_available(
                        self.hass,
                        "persistent_notification",
                        "create",
                        service_data,
                        description=(
                            f"queued notification for {notification['dog_id']}"
                        ),
                        logger=_LOGGER,
                    ),
                    timeout=5.0,
                )

                if not executed:
                    _LOGGER.debug(
                        "Skipping persistent notification for %s because Home Assistant is not available",
                        notification["dog_id"],
                    )
                    return

                _LOGGER.debug(
                    "Sent %s priority notification for %s",
                    notification["priority"],
                    notification["dog_id"],
                )

            except TimeoutError:
                _LOGGER.warning(
                    "Notification send timeout for %s", notification["dog_id"]
                )
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.error("Failed to send notification: %s", err)

    def _should_send_notification(
        self, dog_id: str, priority: NotificationPriority
    ) -> bool:
        """OPTIMIZED: Check notification rules with caching."""
        # Cache quiet hours calculation for performance
        cache_key = f"quiet_hours_{dog_id}_{priority}"

        cached = self._quiet_hours_cache.get(cache_key)
        if cached is not None:
            cached_result, cache_time = cached
            if (dt_util.utcnow() - cache_time).total_seconds() < 60:
                return cached_result

        result = self._calculate_notification_allowed(dog_id, priority)

        # Cache result for 1 minute
        self._quiet_hours_cache[cache_key] = (result, dt_util.utcnow())

        return result

    @staticmethod
    def _coerce_quiet_hours_time(candidate: object, fallback: str) -> time | None:
        """Return a parsed quiet-hours time or ``None`` if invalid."""

        if (parsed_datetime := _deserialize_datetime(candidate)) is not None:
            return dt_util.as_local(parsed_datetime).time().replace(tzinfo=None)

        if isinstance(candidate, datetime):
            return dt_util.as_local(candidate).time().replace(tzinfo=None)

        try:
            time_input = fallback if candidate is None else str(candidate)
        except Exception:
            return None

        parsed_time = dt_util.parse_time(time_input)
        if parsed_time is not None:
            return parsed_time.replace(tzinfo=None)

        try:
            return datetime.strptime(time_input, "%H:%M:%S").time()
        except ValueError:
            return None

    def _calculate_notification_allowed(
        self, dog_id: str, priority: NotificationPriority
    ) -> bool:
        """Calculate if notification should be sent."""
        notification_config = self._get_notification_config(dog_id)

        # Always send urgent notifications
        if priority == "urgent":
            return True

        if not isinstance(notification_config, Mapping):
            return True

        # Check quiet hours
        if not notification_config.get(CONF_QUIET_HOURS, False):
            return True

        now = dt_util.now().time().replace(tzinfo=None)
        quiet_start_time = self._coerce_quiet_hours_time(
            notification_config.get(CONF_QUIET_START), "22:00:00"
        )
        quiet_end_time = self._coerce_quiet_hours_time(
            notification_config.get(CONF_QUIET_END), "07:00:00"
        )

        if quiet_start_time is None or quiet_end_time is None:
            return True

        # Handle quiet hours that span midnight
        if quiet_start_time > quiet_end_time:
            # Quiet hours span midnight (e.g., 22:00 to 07:00)
            return not (now >= quiet_start_time or now <= quiet_end_time)
        # Quiet hours within same day
        return not (quiet_start_time <= now <= quiet_end_time)

    def _get_notification_config(self, dog_id: str) -> Mapping[str, JSONValue] | None:
        """Return per-dog notification settings when available."""

        options = self.config_entry.options
        dog_options = options.get(CONF_DOG_OPTIONS)
        if isinstance(dog_options, Mapping):
            entry = dog_options.get(dog_id)
            if isinstance(entry, Mapping):
                notifications = entry.get(CONF_NOTIFICATIONS)
                if isinstance(notifications, Mapping):
                    return cast(Mapping[str, JSONValue], notifications)

        notification_config = options.get(CONF_NOTIFICATIONS)
        if isinstance(notification_config, Mapping):
            return cast(Mapping[str, JSONValue], notification_config)

        return None

    def get_queue_stats(self) -> NotificationQueueStats:
        """Get notification queue statistics."""
        stats: NotificationQueueStats = {
            "normal_queue_size": len(self._notification_queue),
            "high_priority_queue_size": len(self._high_priority_queue),
            "total_queued": len(self._notification_queue)
            + len(self._high_priority_queue),
            "max_queue_size": MAX_NOTIFICATION_QUEUE,
        }
        return stats

    async def async_shutdown(self) -> None:
        """Shutdown notification manager."""
        if self._processor_task:
            self._processor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._processor_task
            self._processor_task = None

        # Send any high priority notifications immediately
        while self._high_priority_queue:
            notification = self._high_priority_queue.popleft()
            try:
                await asyncio.wait_for(
                    self._send_notification_now(notification), timeout=2.0
                )
            except Exception:
                break  # Don't block shutdown


def _data_encoder(obj: Any) -> Any:
    """OPTIMIZED: Custom JSON encoder with better performance."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    if hasattr(obj, "isoformat"):  # Handle date objects
        return obj.isoformat()
    return str(obj)


# OPTIMIZATION: Add performance monitoring utilities
class PerformanceMonitor:
    """Monitor performance metrics for the integration."""

    def __init__(self) -> None:
        """Initialize performance monitor."""
        self._metrics: PerformanceCounters = PerformanceCounters()
        self._operation_times: deque[float] = deque(maxlen=100)

    def record_operation(self, operation_time: float, success: bool = True) -> None:
        """Record an operation."""
        self._metrics.operations += 1
        if not success:
            self._metrics.errors += 1

        self._operation_times.append(operation_time)

        # Calculate rolling average
        if self._operation_times:
            self._metrics.avg_operation_time = sum(self._operation_times) / len(
                self._operation_times
            )

    def record_cache_hit(self) -> None:
        """Record cache hit."""
        self._metrics.cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record cache miss."""
        self._metrics.cache_misses += 1

    def __call__(
        self,
        *,
        timeout: float | None = None,
        label: str | None = None,
    ) -> Callable[[Callable[P, Awaitable[R] | R]], Callable[P, Awaitable[R] | R]]:
        """Return a decorator that measures the wrapped function.

        Args:
            timeout: Optional timeout in seconds for async functions. When
                provided, the wrapped coroutine is guarded with
                ``asyncio.wait_for``.
            label: Optional human readable label used in debug logging.

        Returns:
            A decorator that records execution metrics through the monitor.
        """

        def decorator(
            func: Callable[P, Awaitable[R] | R],
        ) -> Callable[P, Awaitable[R] | R]:
            func_label = label or getattr(func, "__qualname__", func.__name__)

            if asyncio.iscoroutinefunction(func):

                @wraps(func)
                async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                    loop = asyncio.get_running_loop()
                    start = loop.time()
                    try:
                        if timeout is not None:
                            result = await asyncio.wait_for(
                                func(*args, **kwargs), timeout
                            )
                        else:
                            result = await func(*args, **kwargs)
                    except TimeoutError:
                        duration = loop.time() - start
                        self.record_operation(duration, success=False)
                        _LOGGER.warning(
                            "Operation %s timed out after %.2fs", func_label, timeout
                        )
                        raise
                    except asyncio.CancelledError:
                        duration = loop.time() - start
                        self.record_operation(duration, success=False)
                        raise
                    except Exception:
                        duration = loop.time() - start
                        self.record_operation(duration, success=False)
                        _LOGGER.exception(
                            "Operation %s raised an unexpected error", func_label
                        )
                        raise
                    else:
                        duration = loop.time() - start
                        self.record_operation(duration, success=True)
                        return result

                return async_wrapper

            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                start = perf_counter()
                try:
                    result = cast(R, func(*args, **kwargs))
                except Exception:
                    duration = perf_counter() - start
                    self.record_operation(duration, success=False)
                    _LOGGER.exception(
                        "Operation %s raised an unexpected error", func_label
                    )
                    raise
                else:
                    duration = perf_counter() - start
                    self.record_operation(duration, success=True)
                    if timeout is not None:
                        _LOGGER.debug(
                            "Timeout %.2fs for synchronous operation %s is ignored",
                            timeout,
                            func_label,
                        )
                    return result

            return sync_wrapper

        return decorator

    def get_metrics(self) -> PerformanceMonitorSnapshot:
        """Get performance metrics."""

        total_cache_operations = self._metrics.cache_hits + self._metrics.cache_misses
        cache_hit_rate = (
            (self._metrics.cache_hits / total_cache_operations * 100)
            if total_cache_operations > 0
            else 0
        )

        error_rate = (
            (self._metrics.errors / self._metrics.operations * 100)
            if self._metrics.operations > 0
            else 0
        )

        last_cleanup_value = self._metrics.last_cleanup
        last_cleanup_iso: str | None = None
        if isinstance(last_cleanup_value, datetime):
            last_cleanup_iso = dt_util.as_utc(last_cleanup_value).isoformat()

        metrics: PerformanceMonitorSnapshot = {
            "operations": self._metrics.operations,
            "errors": self._metrics.errors,
            "cache_hits": self._metrics.cache_hits,
            "cache_misses": self._metrics.cache_misses,
            "avg_operation_time": self._metrics.avg_operation_time,
            "last_cleanup": last_cleanup_iso,
            "cache_hit_rate": round(cache_hit_rate, 1),
            "error_rate": round(error_rate, 1),
            "recent_operations": len(self._operation_times),
        }
        return metrics

    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self._metrics = PerformanceCounters(last_cleanup=dt_util.utcnow())
        self._operation_times.clear()


# Global performance monitor instance
performance_monitor = PerformanceMonitor()
