"""Ultra-optimized data management for PawControl with adaptive caching.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
from collections import deque
from contextlib import suppress
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_VERSION
from .exceptions import StorageError
from .utils import deep_merge_dicts

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# OPTIMIZATION: Adaptive performance constants
MIN_CACHE_TTL = 60  # 1 minute minimum
MAX_CACHE_TTL = 3600  # 1 hour maximum
ADAPTIVE_CACHE_FACTOR = 0.8  # Cache hit rate threshold
BATCH_SAVE_MIN_DELAY = 0.5  # Minimum batch delay
BATCH_SAVE_MAX_DELAY = 10  # Maximum batch delay
CLEANUP_BATCH_SIZE = 100  # Process in chunks
MAX_MEMORY_MB = 100  # Memory limit for cache
COMPRESSION_THRESHOLD = 1000  # Compress data above this size


class AdaptiveCache:
    """Adaptive cache with dynamic TTL and memory management."""

    def __init__(self, max_memory_mb: int = MAX_MEMORY_MB) -> None:
        """Initialize adaptive cache.

        Args:
            max_memory_mb: Maximum memory usage in MB
        """
        self._data: dict[str, Any] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._access_history: deque[tuple[str, datetime]] = deque(maxlen=1000)
        self._hit_count = 0
        self._miss_count = 0
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._current_memory = 0
        self._ttl_multipliers: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> tuple[Any | None, bool]:
        """Get value with hit/miss tracking.

        Args:
            key: Cache key

        Returns:
            Tuple of (value, cache_hit)
        """
        async with self._lock:
            now = dt_util.utcnow()

            if key in self._data:
                metadata = self._metadata[key]

                # Check expiry with adaptive TTL
                if now > metadata["expiry"]:
                    await self._evict(key)
                    self._miss_count += 1
                    return None, False

                # Update access metadata
                metadata["access_count"] += 1
                metadata["last_access"] = now
                self._access_history.append((key, now))
                self._hit_count += 1

                # Adapt TTL based on access pattern
                await self._adapt_ttl(key)

                return self._data[key], True

            self._miss_count += 1
            return None, False

    async def set(self, key: str, value: Any, base_ttl: int = 300) -> None:
        """Set value with adaptive TTL.

        Args:
            key: Cache key
            value: Value to cache
            base_ttl: Base TTL in seconds
        """
        async with self._lock:
            # Calculate memory usage
            value_size = self._estimate_size(value)

            # Evict if needed to stay within memory limit
            while self._current_memory + value_size > self._max_memory_bytes:
                if not await self._evict_lru():
                    break  # Can't free more memory

            # Calculate adaptive TTL
            multiplier = self._ttl_multipliers.get(key, 1.0)
            adaptive_ttl = max(
                MIN_CACHE_TTL, min(MAX_CACHE_TTL, int(base_ttl * multiplier))
            )

            now = dt_util.utcnow()
            self._data[key] = value
            self._metadata[key] = {
                "expiry": now + timedelta(seconds=adaptive_ttl),
                "size": value_size,
                "access_count": 0,
                "last_access": now,
                "created": now,
                "base_ttl": base_ttl,
            }
            self._current_memory += value_size

    async def _adapt_ttl(self, key: str) -> None:
        """Adapt TTL based on access patterns."""
        metadata = self._metadata.get(key)
        if not metadata:
            return

        # Calculate access frequency
        age = (dt_util.utcnow() - metadata["created"]).total_seconds()
        if age > 0:
            access_rate = metadata["access_count"] / age

            # Adjust TTL multiplier based on access rate
            if access_rate > 1.0:  # More than 1 access per second
                self._ttl_multipliers[key] = min(
                    2.0, self._ttl_multipliers.get(key, 1.0) * 1.1
                )
            elif access_rate < 0.01:  # Less than 1 access per 100 seconds
                self._ttl_multipliers[key] = max(
                    0.5, self._ttl_multipliers.get(key, 1.0) * 0.9
                )

    async def _evict(self, key: str) -> None:
        """Evict entry from cache."""
        if key in self._data:
            self._current_memory -= self._metadata[key]["size"]
            del self._data[key]
            del self._metadata[key]
            self._ttl_multipliers.pop(key, None)

    async def _evict_lru(self) -> bool:
        """Evict least recently used entry.

        Returns:
            True if entry was evicted
        """
        if not self._metadata:
            return False

        # Find LRU entry
        lru_key = min(
            self._metadata.keys(), key=lambda k: self._metadata[k]["last_access"]
        )

        await self._evict(lru_key)
        return True

    async def cleanup_expired(self) -> int:
        """FIX: Cleanup expired entries to prevent memory leaks.

        Returns:
            Number of entries cleaned up
        """
        now = dt_util.utcnow()
        expired_keys = []

        for key, metadata in self._metadata.items():
            if now > metadata["expiry"]:
                expired_keys.append(key)

        for key in expired_keys:
            await self._evict(key)

        return len(expired_keys)

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of value."""
        try:
            # Serialize to estimate size
            return len(json.dumps(value, default=str).encode())
        except (TypeError, ValueError, OverflowError, RecursionError) as err:
            _LOGGER.debug("Using fallback size estimate for %s: %s", type(value), err)
            # Fallback to rough estimate
            return 1024  # 1KB default

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0

        return {
            "entries": len(self._data),
            "memory_mb": round(self._current_memory / (1024 * 1024), 2),
            "hit_rate": round(hit_rate, 1),
            "hits": self._hit_count,
            "misses": self._miss_count,
            "avg_ttl_multiplier": (
                sum(self._ttl_multipliers.values()) / len(self._ttl_multipliers)
                if self._ttl_multipliers
                else 1.0
            ),
        }


class OptimizedStorage:
    """Optimized storage with compression and indexing."""

    def __init__(self, store: Store) -> None:
        """Initialize optimized storage.

        Args:
            store: Home Assistant storage
        """
        self._store = store
        self._index: dict[str, dict[str, Any]] = {}
        self._checksum: str | None = None

    async def load(self) -> dict[str, Any]:
        """Load data with integrity check."""
        data = await self._store.async_load() or {}

        # Build index for fast lookups
        await self._build_index(data)

        # Calculate checksum
        self._checksum = self._calculate_checksum(data)

        return data

    async def save(self, data: dict[str, Any]) -> None:
        """Save data with compression if needed."""
        # Check if data changed
        new_checksum = self._calculate_checksum(data)
        if new_checksum == self._checksum:
            return  # No changes

        # Compress large data
        if self._should_compress(data):
            data = await self._compress_data(data)

        await self._store.async_save(data)
        self._checksum = new_checksum

        # Rebuild index
        await self._build_index(data)

    async def _build_index(self, data: dict[str, Any]) -> None:
        """Build index for fast lookups."""
        self._index.clear()

        for namespace, namespace_data in data.items():
            if isinstance(namespace_data, dict):
                for key, entries in namespace_data.items():
                    if isinstance(entries, list):
                        # Index by timestamp for fast date queries
                        self._index[f"{namespace}:{key}"] = {
                            "count": len(entries),
                            "first": entries[0].get("timestamp") if entries else None,
                            "last": entries[-1].get("timestamp") if entries else None,
                        }

    def _calculate_checksum(self, data: dict[str, Any]) -> str:
        """Calculate data checksum for integrity verification (non-security use)."""
        data_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(data_str.encode(), usedforsecurity=False).hexdigest()

    def _should_compress(self, data: dict[str, Any]) -> bool:
        """Check if data should be compressed."""
        # Count total entries
        total_entries = sum(
            len(entries) if isinstance(entries, list) else 1
            for namespace_data in data.values()
            if isinstance(namespace_data, dict)
            for entries in namespace_data.values()
        )
        return total_entries > COMPRESSION_THRESHOLD

    async def _compress_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compress old data entries."""
        compressed = data.copy()
        cutoff = dt_util.utcnow() - timedelta(days=30)

        for namespace, namespace_data in compressed.items():
            if not isinstance(namespace_data, dict):
                continue

            for key, entries in namespace_data.items():
                if not isinstance(entries, list):
                    continue

                # Keep only summary for old entries
                new_entries = []
                daily_summary = {}

                for entry in entries:
                    try:
                        timestamp = entry.get("timestamp")
                        if isinstance(timestamp, str):
                            entry_time = datetime.fromisoformat(timestamp)
                        else:
                            new_entries.append(entry)
                            continue

                        if entry_time >= cutoff:
                            new_entries.append(entry)
                        else:
                            # Aggregate old entries by day
                            day_key = entry_time.date().isoformat()
                            if day_key not in daily_summary:
                                daily_summary[day_key] = {
                                    "date": day_key,
                                    "count": 0,
                                    "timestamp": entry_time.replace(
                                        hour=12
                                    ).isoformat(),
                                }
                            daily_summary[day_key]["count"] += 1
                    except (ValueError, TypeError, AttributeError, KeyError) as err:
                        _LOGGER.debug(
                            "Failed to compress %s entry for %s: %s",
                            namespace,
                            key,
                            err,
                        )
                        new_entries.append(entry)

                # Add summaries
                new_entries.extend(daily_summary.values())
                compressed[namespace][key] = new_entries

        return compressed

    def query_index(self, namespace: str, key: str) -> dict[str, Any] | None:
        """Query index for quick metadata."""
        return self._index.get(f"{namespace}:{key}")


class PawControlDataManager:
    """Ultra-optimized data manager with adaptive performance."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize ultra-optimized data manager.

        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id

        # Storage with optimization
        store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_data", encoder=json.JSONEncoder
        )
        self._storage = OptimizedStorage(store)

        # Namespaces
        self._namespaces = [
            "dogs",
            "feeding",
            "walks",
            "health",
            "gps",
            "grooming",
            "medication",
            "visitor_mode",
            "statistics",
        ]

        # Adaptive cache
        self._cache = AdaptiveCache()

        # Adaptive batch save
        self._dirty_namespaces: set[str] = set()
        self._save_task: asyncio.Task | None = None
        self._save_delay = BATCH_SAVE_MIN_DELAY
        self._consecutive_saves = 0

        # Background tasks
        self._maintenance_task: asyncio.Task | None = None

        # Locks
        self._lock = asyncio.Lock()
        self._save_lock = asyncio.Lock()

        # Metrics
        self._metrics = {
            "operations": 0,
            "saves": 0,
            "errors": 0,
            "last_cleanup": None,
            "performance_score": 100.0,
        }

    async def async_initialize(self) -> None:
        """Initialize with optimized loading."""
        _LOGGER.debug("Initializing ultra-optimized data manager")

        try:
            # Load and cache data
            await self._load_initial_data()

            # Start maintenance with adaptive interval
            self._maintenance_task = asyncio.create_task(self._adaptive_maintenance())

            # Initialize statistics
            await self._initialize_statistics()

            _LOGGER.info(
                "Data manager initialized (adaptive cache, dynamic batch save)"
            )

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Initialization failed: %s", err)
            raise StorageError("initialize", str(err)) from err

    async def async_shutdown(self) -> None:
        """Clean shutdown with final optimization."""
        _LOGGER.debug("Shutting down data manager")

        try:
            # Cancel tasks
            for task in [self._maintenance_task, self._save_task]:
                if task and not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

            # Final save
            await self._flush_all()

            _LOGGER.info("Data manager shutdown complete")

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Shutdown error: %s", err)

    async def _load_initial_data(self) -> None:
        """Load data with optimized caching."""
        async with self._lock:
            try:
                # Load from storage using helper that normalizes data structure
                all_data = await self._load_storage_data()

                # Initialize missing namespaces
                for namespace in self._namespaces:
                    if namespace not in all_data:
                        all_data[namespace] = {}

                # Cache with adaptive TTL
                for namespace in self._namespaces:
                    namespace_data = all_data.get(namespace, {})

                    # Calculate initial TTL based on namespace
                    if namespace in ["dogs", "statistics"]:
                        ttl = 1800  # 30 minutes for slow-changing
                    elif namespace in ["feeding", "walks"]:
                        ttl = 300  # 5 minutes for moderate
                    else:
                        ttl = 120  # 2 minutes for fast-changing

                    await self._cache.set(namespace, namespace_data, ttl)

                _LOGGER.debug(
                    "Loaded %d dogs, index: %d entries",
                    len(all_data.get("dogs", {})),
                    len(self._storage._index),
                )

            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.error("Load failed: %s", err)
                # Initialize empty
                for namespace in self._namespaces:
                    await self._cache.set(namespace, {}, 60)

    async def _initialize_statistics(self) -> None:
        """Initialize statistics if needed."""
        stats, _hit = await self._cache.get("statistics")
        if not stats:
            stats = {
                "created": dt_util.utcnow().isoformat(),
                "total_operations": 0,
                "dogs_count": 0,
            }
            await self._save_namespace("statistics", stats)

    async def _get_namespace_data(self, namespace: str) -> dict[str, Any]:
        """Get namespace data with adaptive caching."""
        # Try cache first
        data, cache_hit = await self._cache.get(namespace)

        if cache_hit:
            return data

        # Load from storage
        async with self._lock:
            all_data = await self._load_storage_data()
            namespace_data = all_data.get(namespace, {})

            # Cache with adaptive TTL
            await self._cache.set(namespace, namespace_data)

            return namespace_data

    async def _load_storage_data(self) -> dict[str, Any]:
        """Load raw storage data and ensure a dictionary is returned."""

        data = await self._storage.load()
        if data is None:
            return {}
        if not isinstance(data, dict):
            _LOGGER.warning(
                "Unexpected storage payload type: %s. Resetting to empty dict.",
                type(data).__name__,
            )
            return {}
        return data

    async def _save_namespace(self, namespace: str, data: dict[str, Any]) -> None:
        """Save namespace with adaptive batching."""
        async with self._lock:
            # Update cache
            await self._cache.set(namespace, data)

            # Mark dirty
            self._dirty_namespaces.add(namespace)

            # Adaptive batch scheduling
            await self._schedule_adaptive_save()

    async def _schedule_adaptive_save(self) -> None:
        """Schedule save with adaptive delay."""
        if self._save_task and not self._save_task.done():
            return  # Already scheduled

        # Calculate adaptive delay
        cache_stats = self._cache.get_stats()

        if cache_stats["hit_rate"] > 80:
            # High cache hit rate = less urgent
            delay = min(BATCH_SAVE_MAX_DELAY, self._save_delay * 1.5)
        elif len(self._dirty_namespaces) > 3:
            # Many dirty namespaces = more urgent
            delay = max(BATCH_SAVE_MIN_DELAY, self._save_delay * 0.5)
        else:
            delay = self._save_delay

        self._save_delay = delay
        self._save_task = asyncio.create_task(self._batch_save(delay))

    async def _batch_save(self, delay: float) -> None:
        """Perform batch save with delay."""
        try:
            await asyncio.sleep(delay)

            async with self._save_lock:
                if not self._dirty_namespaces:
                    return

                # Load current data
                all_data = await self._load_storage_data()

                # Update dirty namespaces
                for namespace in self._dirty_namespaces:
                    data, _ = await self._cache.get(namespace)
                    if data is not None:
                        all_data[namespace] = data

                # Save with optimization
                await self._storage.save(all_data)

                # Clear and update metrics
                saved_count = len(self._dirty_namespaces)
                self._dirty_namespaces.clear()
                self._metrics["saves"] += 1
                self._consecutive_saves += 1

                _LOGGER.debug(
                    "Batch saved %d namespaces (delay: %.1fs)", saved_count, delay
                )

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Batch save failed: %s", err)
            self._metrics["errors"] += 1

    async def _adaptive_maintenance(self) -> None:
        """Adaptive maintenance based on system load."""
        base_interval = 300  # 5 minutes base

        while True:
            try:
                # Calculate adaptive interval
                cache_stats = self._cache.get_stats()

                if cache_stats["memory_mb"] > MAX_MEMORY_MB * 0.8:
                    # High memory usage = more frequent cleanup
                    interval = base_interval * 0.5
                elif cache_stats["hit_rate"] > 90:
                    # Very efficient = less frequent
                    interval = base_interval * 2
                else:
                    interval = base_interval

                await asyncio.sleep(interval)

                # Perform maintenance
                await self._perform_maintenance()

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Maintenance error: %s", err)
                await asyncio.sleep(60)

    async def _perform_maintenance(self) -> None:
        """Perform maintenance tasks."""
        # FIX: Clean up expired cache entries to prevent memory leaks
        cleaned_entries = await self._cache.cleanup_expired()
        if cleaned_entries > 0:
            _LOGGER.debug("Cleaned up %d expired cache entries", cleaned_entries)

        # Update performance score
        cache_stats = self._cache.get_stats()
        self._metrics["performance_score"] = (
            cache_stats["hit_rate"] * 0.5
            + (100 - cache_stats["memory_mb"] / MAX_MEMORY_MB * 100) * 0.3
            + (
                100
                - self._metrics["errors"] / max(self._metrics["operations"], 1) * 100
            )
            * 0.2
        )

        # Log if interesting
        if self._metrics["performance_score"] < 70:
            _LOGGER.info(
                "Performance: %.1f%% (cache: %.1f%%, mem: %.1fMB)",
                self._metrics["performance_score"],
                cache_stats["hit_rate"],
                cache_stats["memory_mb"],
            )

    # Core operations with simplified implementation for brevity
    async def async_get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        """Get dog data with caching."""
        dogs_data = await self._get_namespace_data("dogs")
        self._metrics["operations"] += 1
        return dogs_data.get(dog_id)

    async def async_set_dog_data(self, dog_id: str, data: dict[str, Any]) -> None:
        """Set dog data."""
        dogs_data = await self._get_namespace_data("dogs")
        dogs_data[dog_id] = data
        await self._save_namespace("dogs", dogs_data)
        self._metrics["operations"] += 1

    async def async_update_dog_data(self, dog_id: str, updates: dict[str, Any]) -> None:
        """Update dog data with merge."""
        current = await self.async_get_dog_data(dog_id) or {}
        updated = deep_merge_dicts(current, updates)
        await self.async_set_dog_data(dog_id, updated)

    async def async_get_module_data(
        self,
        module: str,
        dog_id: str,
        limit: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get module data with optimized filtering."""
        try:
            # Check index for quick stats
            self._storage.query_index(module, dog_id)

            # Get module data
            module_data = await self._get_namespace_data(module)
            entries = module_data.get(dog_id, [])

            if not entries:
                return []

            # Filter if needed
            if start_date or end_date:
                entries = await self._filter_by_date(entries, start_date, end_date)

            # Sort and limit
            entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

            if limit and limit > 0:
                entries = entries[:limit]

            self._metrics["operations"] += 1
            return entries

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Get module data failed: %s", err)
            self._metrics["errors"] += 1
            return []

    async def _filter_by_date(
        self,
        entries: list[dict[str, Any]],
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> list[dict[str, Any]]:
        """Filter entries by date with batch processing."""
        if not start_date and not end_date:
            return entries

        filtered = []
        for entry in entries:
            try:
                timestamp = entry.get("timestamp")
                if not timestamp:
                    filtered.append(entry)
                    continue

                if isinstance(timestamp, str):
                    entry_time = datetime.fromisoformat(timestamp)
                elif isinstance(timestamp, datetime):
                    entry_time = timestamp
                else:
                    filtered.append(entry)
                    continue

                # Check date range
                if start_date and entry_time < start_date:
                    continue
                if end_date and entry_time > end_date:
                    continue

                filtered.append(entry)

            except (ValueError, TypeError, AttributeError) as err:
                _LOGGER.debug("Failed to parse timestamp for %s: %s", entry, err)
                filtered.append(entry)

        return filtered

    async def _flush_all(self) -> None:
        """Flush all cached data to storage."""
        try:
            all_data = await self._load_storage_data()

            for namespace in self._namespaces:
                data, _ = await self._cache.get(namespace)
                if data is not None:
                    all_data[namespace] = data

            await self._storage.save(all_data)
            self._dirty_namespaces.clear()

        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Flush failed: %s", err)

    def get_metrics(self) -> dict[str, Any]:
        """Get performance metrics."""
        cache_stats = self._cache.get_stats()

        return {
            **self._metrics,
            **cache_stats,
            "save_delay": round(self._save_delay, 1),
            "dirty_namespaces": len(self._dirty_namespaces),
        }

    async def async_get_registered_dogs(self) -> list[str]:
        """Get registered dog IDs."""
        dogs_data = await self._get_namespace_data("dogs")
        return list(dogs_data.keys())

    async def async_get_all_dogs(self) -> dict[str, dict[str, Any]]:
        """Get all dogs data."""
        dogs_data = await self._get_namespace_data("dogs")
        return dogs_data.copy()

    # NEW METHODS: Health and medication logging for services

    async def async_log_health_data(
        self, dog_id: str, health_data: dict[str, Any]
    ) -> None:
        """Log health data for a dog.

        Args:
            dog_id: Dog identifier
            health_data: Health data to log
        """
        try:
            health_namespace = await self._get_namespace_data("health")

            if dog_id not in health_namespace:
                health_namespace[dog_id] = []

            # Add timestamp if not present
            if "timestamp" not in health_data:
                health_data["timestamp"] = dt_util.utcnow().isoformat()

            # Add entry
            health_namespace[dog_id].append(health_data.copy())

            # Keep only last 1000 entries per dog to prevent unlimited growth
            if len(health_namespace[dog_id]) > 1000:
                health_namespace[dog_id] = health_namespace[dog_id][-1000:]

            await self._save_namespace("health", health_namespace)

            _LOGGER.debug("Logged health data for %s: %s", dog_id, health_data)

        except Exception as err:
            _LOGGER.error("Failed to log health data for %s: %s", dog_id, err)
            self._metrics["errors"] += 1
            raise

    async def async_log_medication(
        self, dog_id: str, medication_data: dict[str, Any]
    ) -> None:
        """Log medication administration for a dog.

        Args:
            dog_id: Dog identifier
            medication_data: Medication data to log
        """
        try:
            medication_namespace = await self._get_namespace_data("medication")

            if dog_id not in medication_namespace:
                medication_namespace[dog_id] = []

            # Add timestamp if not present
            if "administration_time" not in medication_data:
                medication_data["administration_time"] = dt_util.utcnow().isoformat()

            # Add entry
            medication_namespace[dog_id].append(medication_data.copy())

            # Keep only last 500 entries per dog
            if len(medication_namespace[dog_id]) > 500:
                medication_namespace[dog_id] = medication_namespace[dog_id][-500:]

            await self._save_namespace("medication", medication_namespace)

            _LOGGER.debug(
                "Logged medication for %s: %s",
                dog_id,
                medication_data.get("medication_name"),
            )

        except Exception as err:
            _LOGGER.error("Failed to log medication for %s: %s", dog_id, err)
            self._metrics["errors"] += 1
            raise

    async def async_get_visitor_mode_status(self, dog_id: str) -> dict[str, Any]:
        """Get visitor mode status for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Visitor mode status data
        """
        try:
            visitor_namespace = await self._get_namespace_data("visitor_mode")
            return visitor_namespace.get(dog_id, {"enabled": False})

        except Exception as err:
            _LOGGER.error("Failed to get visitor mode status for %s: %s", dog_id, err)
            self._metrics["errors"] += 1
            return {"enabled": False}

    async def async_set_visitor_mode(
        self, dog_id: str, visitor_data: dict[str, Any]
    ) -> None:
        """Set visitor mode for a dog.

        Args:
            dog_id: Dog identifier
            visitor_data: Visitor mode configuration
        """
        try:
            visitor_namespace = await self._get_namespace_data("visitor_mode")
            visitor_namespace[dog_id] = visitor_data.copy()

            await self._save_namespace("visitor_mode", visitor_namespace)

            _LOGGER.debug(
                "Set visitor mode for %s: %s", dog_id, visitor_data.get("enabled")
            )

        except Exception as err:
            _LOGGER.error("Failed to set visitor mode for %s: %s", dog_id, err)
            self._metrics["errors"] += 1
            raise

    async def async_export_data(
        self,
        dog_id: str,
        data_type: str,
        format: str = "json",
        days: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        """Export data for a dog in specified format.

        Args:
            dog_id: Dog identifier
            data_type: Type of data to export (feeding, walks, health, medication, routes, all)
            format: Export format (json, csv, gpx)
            days: Number of days to export (from now backwards)
            date_from: Start date for export
            date_to: End date for export

        Returns:
            Export result with data or file path
        """
        try:
            # Calculate date range
            end_date = date_to or dt_util.utcnow()
            start_date = end_date - timedelta(days=days) if days else date_from

            export_data = {}

            # Collect data based on type
            if data_type == "all":
                data_types = ["feeding", "walks", "health", "medication", "gps"]
            else:
                data_types = [data_type]

            for dtype in data_types:
                if dtype == "routes":
                    dtype = "gps"  # Map routes to gps data

                entries = await self.async_get_module_data(
                    dtype, dog_id, start_date=start_date, end_date=end_date
                )
                export_data[dtype] = entries

            # Format data
            if format == "csv":
                return await self._export_as_csv(dog_id, export_data, data_type)
            elif format == "gpx" and data_type in ["routes", "walks", "gps", "all"]:
                return await self._export_as_gpx(dog_id, export_data.get("gps", []))
            else:
                return {
                    "format": format,
                    "dog_id": dog_id,
                    "data_type": data_type,
                    "date_range": {
                        "from": start_date.isoformat() if start_date else None,
                        "to": end_date.isoformat(),
                    },
                    "data": export_data,
                    "total_entries": sum(
                        len(entries) for entries in export_data.values()
                    ),
                }

        except Exception as err:
            _LOGGER.error("Failed to export data for %s: %s", dog_id, err)
            self._metrics["errors"] += 1
            raise

    async def _export_as_csv(
        self, dog_id: str, data: dict[str, Any], data_type: str
    ) -> dict[str, Any]:
        """Export data as CSV format.

        Args:
            dog_id: Dog identifier
            data: Data to export
            data_type: Type of data

        Returns:
            CSV export result
        """
        try:
            csv_data = {}

            for dtype, entries in data.items():
                if not entries:
                    continue

                # Create CSV content
                output = io.StringIO()

                if entries:
                    # Get all possible fields
                    fields = set()
                    for entry in entries:
                        fields.update(entry.keys())

                    writer = csv.DictWriter(output, fieldnames=sorted(fields))
                    writer.writeheader()
                    writer.writerows(entries)

                csv_data[dtype] = output.getvalue()
                output.close()

            return {
                "format": "csv",
                "dog_id": dog_id,
                "data_type": data_type,
                "csv_data": csv_data,
                "total_entries": sum(len(entries) for entries in data.values()),
            }

        except Exception as err:
            _LOGGER.error("Failed to export CSV for %s: %s", dog_id, err)
            raise

    async def _export_as_gpx(
        self, dog_id: str, gps_entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Export GPS data as GPX format.

        Args:
            dog_id: Dog identifier
            gps_entries: GPS entries to export

        Returns:
            GPX export result
        """
        try:
            if not gps_entries:
                return {
                    "format": "gpx",
                    "dog_id": dog_id,
                    "gpx_data": "",
                    "total_points": 0,
                }

            # Generate GPX content
            gpx_lines = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<gpx version="1.1" creator="PawControl" xmlns="http://www.topografix.com/GPX/1/1">',
                "  <trk>",
                f"    <name>{dog_id} Walk Track</name>",
                "    <trkseg>",
            ]

            for entry in gps_entries:
                lat = entry.get("latitude")
                lon = entry.get("longitude")
                timestamp = entry.get("timestamp")

                if lat is not None and lon is not None:
                    line = f'      <trkpt lat="{lat}" lon="{lon}">'
                    if timestamp:
                        line += f"<time>{timestamp}</time>"
                    line += "</trkpt>"
                    gpx_lines.append(line)

            gpx_lines.extend(
                [
                    "    </trkseg>",
                    "  </trk>",
                    "</gpx>",
                ]
            )

            gpx_content = "\n".join(gpx_lines)

            return {
                "format": "gpx",
                "dog_id": dog_id,
                "gpx_data": gpx_content,
                "total_points": len(
                    [e for e in gps_entries if e.get("latitude") and e.get("longitude")]
                ),
            }

        except Exception as err:
            _LOGGER.error("Failed to export GPX for %s: %s", dog_id, err)
            raise

    async def async_analyze_patterns(
        self, dog_id: str, analysis_type: str, days: int = 30
    ) -> dict[str, Any]:
        """Analyze patterns in dog data.

        Args:
            dog_id: Dog identifier
            analysis_type: Type of analysis (feeding, walking, health, comprehensive)
            days: Number of days to analyze

        Returns:
            Analysis results
        """
        try:
            end_date = dt_util.utcnow()
            start_date = end_date - timedelta(days=days)

            analysis = {
                "dog_id": dog_id,
                "analysis_type": analysis_type,
                "period": {
                    "days": days,
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                },
                "patterns": {},
            }

            if analysis_type in ["feeding", "comprehensive"]:
                feeding_data = await self.async_get_module_data(
                    "feeding", dog_id, start_date=start_date, end_date=end_date
                )
                analysis["patterns"]["feeding"] = await self._analyze_feeding_patterns(
                    feeding_data
                )

            if analysis_type in ["walking", "comprehensive"]:
                walk_data = await self.async_get_module_data(
                    "walks", dog_id, start_date=start_date, end_date=end_date
                )
                analysis["patterns"]["walking"] = await self._analyze_walking_patterns(
                    walk_data
                )

            if analysis_type in ["health", "comprehensive"]:
                health_data = await self.async_get_module_data(
                    "health", dog_id, start_date=start_date, end_date=end_date
                )
                analysis["patterns"]["health"] = await self._analyze_health_patterns(
                    health_data
                )

            return analysis

        except Exception as err:
            _LOGGER.error("Failed to analyze patterns for %s: %s", dog_id, err)
            self._metrics["errors"] += 1
            raise

    async def _analyze_feeding_patterns(
        self, feeding_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze feeding patterns."""
        if not feeding_data:
            return {"meals_per_day": 0, "average_portion": 0, "patterns": []}

        # Group by day
        daily_meals = {}
        total_portions = 0

        for entry in feeding_data:
            timestamp = entry.get("timestamp", "")
            try:
                date_key = timestamp[:10] if timestamp else ""
                if date_key:
                    if date_key not in daily_meals:
                        daily_meals[date_key] = []
                    daily_meals[date_key].append(entry)
                    total_portions += float(entry.get("amount", 0))
            except (ValueError, TypeError):
                continue

        avg_meals_per_day = len(feeding_data) / len(daily_meals) if daily_meals else 0
        avg_portion = total_portions / len(feeding_data) if feeding_data else 0

        return {
            "total_meals": len(feeding_data),
            "days_with_data": len(daily_meals),
            "meals_per_day": round(avg_meals_per_day, 1),
            "average_portion": round(avg_portion, 1),
            "total_food": round(total_portions, 1),
        }

    async def _analyze_walking_patterns(
        self, walk_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze walking patterns."""
        if not walk_data:
            return {"walks_per_day": 0, "average_duration": 0, "patterns": []}

        total_duration = 0
        total_distance = 0

        for entry in walk_data:
            duration = float(entry.get("duration", 0))
            distance = float(entry.get("distance", 0))
            total_duration += duration
            total_distance += distance

        avg_duration = total_duration / len(walk_data) if walk_data else 0
        avg_distance = total_distance / len(walk_data) if walk_data else 0

        return {
            "total_walks": len(walk_data),
            "average_duration_minutes": round(avg_duration / 60, 1)
            if avg_duration
            else 0,
            "average_distance_km": round(avg_distance / 1000, 2) if avg_distance else 0,
            "total_distance_km": round(total_distance / 1000, 2),
            "total_duration_hours": round(total_duration / 3600, 1),
        }

    async def _analyze_health_patterns(
        self, health_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze health patterns."""
        if not health_data:
            return {"entries": 0, "trends": {}}

        weights = []
        activity_levels = []

        for entry in health_data:
            if entry.get("weight"):
                with suppress(ValueError, TypeError):
                    weights.append(float(entry["weight"]))

            if "activity_level" in entry:
                activity_levels.append(entry["activity_level"])

        analysis = {
            "total_entries": len(health_data),
            "weight_entries": len(weights),
        }

        if weights:
            analysis["weight"] = {
                "current": weights[-1],
                "min": min(weights),
                "max": max(weights),
                "average": round(sum(weights) / len(weights), 1),
                "trend": "stable",  # Simplified
            }

        if activity_levels:
            from collections import Counter

            activity_counts = Counter(activity_levels)
            analysis["activity"] = {
                "most_common": activity_counts.most_common(1)[0][0],
                "distribution": dict(activity_counts),
            }

        return analysis

    async def async_generate_weekly_health_report(
        self,
        dog_id: str,
        include_recommendations: bool = True,
        include_charts: bool = True,
        format: str = "pdf",
    ) -> dict[str, Any]:
        """Generate comprehensive weekly health report for a dog.

        Args:
            dog_id: Dog identifier
            include_recommendations: Include AI-generated recommendations
            include_charts: Include visual charts and graphs
            format: Report format (pdf, json, markdown)

        Returns:
            Comprehensive weekly health report
        """
        try:
            # Get dog data
            dog_data = await self.async_get_dog_data(dog_id)
            if not dog_data:
                raise ValueError(f"Dog {dog_id} not found")

            # Get 7 days of health data
            end_date = dt_util.utcnow()
            start_date = end_date - timedelta(days=7)

            # Collect health data
            health_data = await self.async_get_module_data(
                "health", dog_id, start_date=start_date, end_date=end_date
            )

            # Collect feeding data
            feeding_data = await self.async_get_module_data(
                "feeding", dog_id, start_date=start_date, end_date=end_date
            )

            # Collect walk data
            walk_data = await self.async_get_module_data(
                "walks", dog_id, start_date=start_date, end_date=end_date
            )

            # Collect medication data
            medication_data = await self.async_get_module_data(
                "medication", dog_id, start_date=start_date, end_date=end_date
            )

            # Generate comprehensive analysis
            health_analysis = await self._analyze_weekly_health(
                health_data, feeding_data, walk_data, medication_data
            )

            # Create report structure
            report = {
                "dog_id": dog_id,
                "dog_name": dog_data.get("name", dog_id),
                "report_type": "weekly_health",
                "format": format,
                "generated_at": dt_util.utcnow().isoformat(),
                "week_period": {
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                    "days": 7,
                },
                "dog_profile": {
                    "age_months": dog_data.get("age_months"),
                    "weight_kg": dog_data.get("weight"),
                    "breed": dog_data.get("breed"),
                    "size": dog_data.get("size"),
                },
                "health_analysis": health_analysis,
                "summary": await self._generate_weekly_health_summary(health_analysis),
                "metrics": await self._calculate_weekly_health_metrics(health_analysis),
            }

            if include_recommendations:
                report[
                    "recommendations"
                ] = await self._generate_weekly_health_recommendations(
                    dog_data, health_analysis
                )

            if include_charts and format != "pdf":
                # For non-PDF formats, include chart data
                report["chart_data"] = await self._generate_weekly_chart_data(
                    health_analysis
                )

            # Format-specific processing
            if format == "pdf":
                report["pdf_sections"] = await self._generate_pdf_sections(report)
            elif format == "markdown":
                report["markdown_content"] = await self._generate_markdown_report(
                    report
                )

            _LOGGER.info(
                "Generated weekly health report for %s in %s format",
                dog_id,
                format,
            )

            return report

        except Exception as err:
            _LOGGER.error(
                "Failed to generate weekly health report for %s: %s", dog_id, err
            )
            self._metrics["errors"] += 1
            raise

    async def _analyze_weekly_health(
        self,
        health_data: list[dict[str, Any]],
        feeding_data: list[dict[str, Any]],
        walk_data: list[dict[str, Any]],
        medication_data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Perform comprehensive weekly health analysis.

        Args:
            health_data: Health log entries
            feeding_data: Feeding log entries
            walk_data: Walk log entries
            medication_data: Medication log entries

        Returns:
            Comprehensive health analysis
        """
        analysis = {
            "data_availability": {
                "health_entries": len(health_data),
                "feeding_entries": len(feeding_data),
                "walk_entries": len(walk_data),
                "medication_entries": len(medication_data),
            },
            "health_trends": {},
            "feeding_analysis": {},
            "activity_analysis": {},
            "medication_compliance": {},
            "alerts": [],
        }

        # Analyze health trends
        if health_data:
            weights = []
            temperatures = []
            moods = []

            for entry in health_data:
                if entry.get("weight"):
                    with suppress(ValueError, TypeError):
                        weights.append(
                            {
                                "value": float(entry["weight"]),
                                "timestamp": entry.get("timestamp"),
                            }
                        )

                if entry.get("temperature"):
                    with suppress(ValueError, TypeError):
                        temperatures.append(
                            {
                                "value": float(entry["temperature"]),
                                "timestamp": entry.get("timestamp"),
                            }
                        )

                if entry.get("mood"):
                    moods.append(
                        {
                            "value": entry["mood"],
                            "timestamp": entry.get("timestamp"),
                        }
                    )

            analysis["health_trends"] = {
                "weight": await self._analyze_weight_trend(weights),
                "temperature": await self._analyze_temperature_trend(temperatures),
                "mood": await self._analyze_mood_trend(moods),
            }

        # Analyze feeding patterns
        if feeding_data:
            daily_amounts = {}
            meal_times = []

            for entry in feeding_data:
                timestamp = entry.get("timestamp")
                amount = entry.get("amount", 0)

                if timestamp:
                    try:
                        date_key = timestamp[:10]
                        daily_amounts[date_key] = daily_amounts.get(
                            date_key, 0
                        ) + float(amount)

                        # Extract hour for meal timing analysis
                        hour = int(timestamp[11:13])
                        meal_times.append(hour)
                    except (ValueError, TypeError, IndexError):
                        pass

            analysis["feeding_analysis"] = {
                "daily_amounts": daily_amounts,
                "average_daily": sum(daily_amounts.values())
                / max(len(daily_amounts), 1),
                "feeding_regularity": await self._analyze_feeding_regularity(
                    meal_times
                ),
                "portion_consistency": await self._analyze_portion_consistency(
                    feeding_data
                ),
            }

        # Analyze activity patterns
        if walk_data:
            daily_exercise = {}
            durations = []
            distances = []

            for entry in walk_data:
                timestamp = entry.get("timestamp")
                duration = entry.get("duration", 0)
                distance = entry.get("distance", 0)

                if timestamp:
                    try:
                        date_key = timestamp[:10]
                        if date_key not in daily_exercise:
                            daily_exercise[date_key] = {
                                "duration": 0,
                                "distance": 0,
                                "walks": 0,
                            }

                        daily_exercise[date_key]["duration"] += float(duration)
                        daily_exercise[date_key]["distance"] += float(distance)
                        daily_exercise[date_key]["walks"] += 1

                        if duration > 0:
                            durations.append(float(duration))
                        if distance > 0:
                            distances.append(float(distance))

                    except (ValueError, TypeError, IndexError):
                        pass

            analysis["activity_analysis"] = {
                "daily_exercise": daily_exercise,
                "average_duration_minutes": sum(durations)
                / 60
                / max(len(durations), 1),
                "average_distance_km": sum(distances) / 1000 / max(len(distances), 1),
                "consistency_score": await self._calculate_exercise_consistency(
                    daily_exercise
                ),
            }

        # Analyze medication compliance
        if medication_data:
            medications = {}
            compliance_issues = []

            for entry in medication_data:
                med_name = entry.get("medication_name", "Unknown")
                timestamp = entry.get("administration_time")

                if med_name not in medications:
                    medications[med_name] = []

                medications[med_name].append(
                    {
                        "timestamp": timestamp,
                        "dose": entry.get("dose"),
                        "with_meal": entry.get("with_meal", False),
                    }
                )

            analysis["medication_compliance"] = {
                "medications": medications,
                "total_administrations": len(medication_data),
                "unique_medications": len(medications),
                "compliance_issues": compliance_issues,  # Would analyze timing consistency
            }

        return analysis

    async def _analyze_weight_trend(
        self, weights: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze weight trend over the week."""
        if not weights:
            return {"status": "no_data"}

        # Sort by timestamp
        sorted_weights = sorted(weights, key=lambda x: x["timestamp"] or "")
        values = [w["value"] for w in sorted_weights]

        if len(values) < 2:
            return {
                "status": "insufficient_data",
                "current_weight": values[0] if values else None,
            }

        # Calculate trend
        first_weight = values[0]
        last_weight = values[-1]
        weight_change = last_weight - first_weight
        percent_change = (weight_change / first_weight) * 100

        # Determine trend status
        if abs(percent_change) < 1:
            trend = "stable"
        elif percent_change > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        return {
            "status": "analyzed",
            "first_weight": first_weight,
            "last_weight": last_weight,
            "weight_change": round(weight_change, 2),
            "percent_change": round(percent_change, 2),
            "trend": trend,
            "data_points": len(values),
        }

    async def _analyze_temperature_trend(
        self, temperatures: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze temperature trend."""
        if not temperatures:
            return {"status": "no_data"}

        values = [t["value"] for t in temperatures]
        avg_temp = sum(values) / len(values)

        # Normal dog temperature range: 101-102.5°F (38.3-39.2°C)
        alerts = []
        for temp in values:
            if temp < 38.0 or temp > 39.5:  # Assuming Celsius
                alerts.append(f"Temperature {temp}°C outside normal range")  # noqa: PERF401

        return {
            "status": "analyzed",
            "average_temp": round(avg_temp, 1),
            "min_temp": min(values),
            "max_temp": max(values),
            "data_points": len(values),
            "alerts": alerts,
        }

    async def _analyze_mood_trend(self, moods: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze mood trend."""
        if not moods:
            return {"status": "no_data"}

        from collections import Counter

        mood_values = [m["value"] for m in moods]
        mood_counts = Counter(mood_values)

        return {
            "status": "analyzed",
            "most_common_mood": mood_counts.most_common(1)[0][0],
            "mood_distribution": dict(mood_counts),
            "data_points": len(mood_values),
        }

    async def _analyze_feeding_regularity(
        self, meal_times: list[int]
    ) -> dict[str, Any]:
        """Analyze feeding time regularity."""
        if not meal_times:
            return {"score": 0, "status": "no_data"}

        from collections import Counter

        time_counts = Counter(meal_times)

        # Calculate regularity score based on consistency
        total_meals = len(meal_times)
        unique_hours = len(time_counts)

        # More consistent timing = higher score
        regularity_score = max(0, 100 - (unique_hours / total_meals * 100))

        return {
            "score": round(regularity_score, 1),
            "common_feeding_hours": time_counts.most_common(3),
            "unique_hours": unique_hours,
            "total_meals": total_meals,
        }

    async def _analyze_portion_consistency(
        self, feeding_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze portion size consistency."""
        amounts = []
        for entry in feeding_data:
            try:
                amount = float(entry.get("amount", 0))
                if amount > 0:
                    amounts.append(amount)
            except (ValueError, TypeError):
                pass

        if not amounts:
            return {"score": 0, "status": "no_data"}

        avg_amount = sum(amounts) / len(amounts)
        variance = sum((x - avg_amount) ** 2 for x in amounts) / len(amounts)
        std_dev = variance**0.5

        # Consistency score - lower variance = higher consistency
        consistency_score = max(0, 100 - (std_dev / avg_amount * 100))

        return {
            "score": round(consistency_score, 1),
            "average_portion": round(avg_amount, 1),
            "standard_deviation": round(std_dev, 1),
            "min_portion": min(amounts),
            "max_portion": max(amounts),
        }

    async def _calculate_exercise_consistency(
        self, daily_exercise: dict[str, Any]
    ) -> float:
        """Calculate exercise consistency score."""
        if not daily_exercise:
            return 0.0

        durations = [day["duration"] for day in daily_exercise.values()]
        if not durations:
            return 0.0

        avg_duration = sum(durations) / len(durations)
        if avg_duration == 0:
            return 0.0

        variance = sum((d - avg_duration) ** 2 for d in durations) / len(durations)
        coefficient_of_variation = (variance**0.5) / avg_duration

        # Lower coefficient of variation = higher consistency
        consistency_score = max(0, 100 - (coefficient_of_variation * 100))

        return round(consistency_score, 1)

    async def _generate_weekly_health_summary(
        self, health_analysis: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate executive summary of weekly health analysis."""
        summary = {
            "overall_status": "good",  # Default
            "key_findings": [],
            "areas_of_concern": [],
            "positive_trends": [],
            "data_completeness": "good",  # Default
        }

        # Assess data completeness
        availability = health_analysis.get("data_availability", {})
        total_entries = sum(availability.values())

        if total_entries < 5:
            summary["data_completeness"] = "limited"
            summary["areas_of_concern"].append("Limited health data logged this week")
        elif total_entries > 20:
            summary["data_completeness"] = "excellent"
            summary["positive_trends"].append("Comprehensive health monitoring")

        # Analyze weight trends
        weight_trend = health_analysis.get("health_trends", {}).get("weight", {})
        if weight_trend.get("status") == "analyzed":
            change = weight_trend.get("percent_change", 0)
            if abs(change) > 5:  # >5% weight change is significant
                summary["areas_of_concern"].append(
                    f"Significant weight change: {change:+.1f}%"
                )
                if summary["overall_status"] == "good":
                    summary["overall_status"] = "attention_needed"

        # Analyze feeding patterns
        feeding_analysis = health_analysis.get("feeding_analysis", {})
        if feeding_analysis:
            regularity = feeding_analysis.get("feeding_regularity", {}).get("score", 0)
            if regularity > 80:
                summary["positive_trends"].append("Consistent feeding schedule")
            elif regularity < 50:
                summary["areas_of_concern"].append("Irregular feeding times")

        # Analyze activity levels
        activity_analysis = health_analysis.get("activity_analysis", {})
        if activity_analysis:
            activity_analysis.get("consistency_score", 0)
            avg_duration = activity_analysis.get("average_duration_minutes", 0)

            if avg_duration < 30:
                summary["areas_of_concern"].append(
                    "Below recommended exercise duration"
                )
            elif avg_duration > 60:
                summary["positive_trends"].append("Good exercise routine")

        # Set overall status based on concerns
        if len(summary["areas_of_concern"]) > 2:
            summary["overall_status"] = "needs_attention"
        elif len(summary["areas_of_concern"]) == 0:
            summary["overall_status"] = "excellent"

        return summary

    async def _calculate_weekly_health_metrics(
        self, health_analysis: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate key weekly health metrics."""
        metrics = {}

        # Health tracking score
        availability = health_analysis.get("data_availability", {})
        total_entries = sum(availability.values())
        metrics["health_tracking_score"] = min(
            100, (total_entries / 10) * 100
        )  # Target: 10+ entries

        # Feeding consistency score
        feeding_analysis = health_analysis.get("feeding_analysis", {})
        regularity_score = feeding_analysis.get("feeding_regularity", {}).get(
            "score", 0
        )
        portion_consistency = feeding_analysis.get("portion_consistency", {}).get(
            "score", 0
        )
        metrics["feeding_consistency_score"] = (
            regularity_score + portion_consistency
        ) / 2

        # Activity score
        activity_analysis = health_analysis.get("activity_analysis", {})
        avg_duration = activity_analysis.get("average_duration_minutes", 0)
        consistency_score = activity_analysis.get("consistency_score", 0)

        # Target: 45 minutes average exercise
        duration_score = min(100, (avg_duration / 45) * 100)
        metrics["activity_score"] = (duration_score + consistency_score) / 2

        # Overall health score
        metrics["overall_health_score"] = (
            metrics["health_tracking_score"] * 0.3
            + metrics["feeding_consistency_score"] * 0.4
            + metrics["activity_score"] * 0.3
        )

        # Round all scores
        for key, value in metrics.items():
            metrics[key] = round(value, 1)

        return metrics

    async def _generate_weekly_health_recommendations(
        self, dog_data: dict[str, Any], health_analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate personalized weekly health recommendations."""
        recommendations = []

        # Data logging recommendations
        availability = health_analysis.get("data_availability", {})
        if availability.get("health_entries", 0) < 3:
            recommendations.append(
                {
                    "type": "health_tracking",
                    "priority": "medium",
                    "title": "Increase health monitoring frequency",
                    "description": "Log weight, mood, and general health status at least 3 times per week for better trend analysis.",
                    "action": "Set weekly reminders for health check-ins",
                }
            )

        # Weight management recommendations
        weight_trend = health_analysis.get("health_trends", {}).get("weight", {})
        if weight_trend.get("status") == "analyzed":
            change = weight_trend.get("percent_change", 0)
            if change > 3:
                recommendations.append(
                    {
                        "type": "weight_management",
                        "priority": "high",
                        "title": "Weight gain detected",
                        "description": f"Dog has gained {change:.1f}% weight this week. Consider portion control and increased exercise.",
                        "action": "Reduce daily portions by 10% and add 15 minutes to walks",
                    }
                )
            elif change < -3:
                recommendations.append(
                    {
                        "type": "weight_management",
                        "priority": "high",
                        "title": "Weight loss detected",
                        "description": f"Dog has lost {abs(change):.1f}% weight this week. Monitor appetite and consult vet if trend continues.",
                        "action": "Schedule vet check-up if weight loss continues",
                    }
                )

        # Exercise recommendations
        activity_analysis = health_analysis.get("activity_analysis", {})
        avg_duration = activity_analysis.get("average_duration_minutes", 0)

        if avg_duration < 30:
            recommendations.append(
                {
                    "type": "exercise",
                    "priority": "medium",
                    "title": "Increase exercise duration",
                    "description": f"Current average walk time is {avg_duration:.0f} minutes. Most dogs need at least 30-60 minutes daily.",
                    "action": "Gradually increase walk duration by 5-10 minutes per week",
                }
            )

        # Feeding consistency recommendations
        feeding_analysis = health_analysis.get("feeding_analysis", {})
        regularity_score = feeding_analysis.get("feeding_regularity", {}).get(
            "score", 0
        )

        if regularity_score < 60:
            recommendations.append(
                {
                    "type": "feeding",
                    "priority": "medium",
                    "title": "Improve feeding schedule consistency",
                    "description": "Inconsistent feeding times can affect digestion and behavior. Try to feed at the same times daily.",
                    "action": "Set feeding reminders for consistent meal times",
                }
            )

        return recommendations

    async def _generate_weekly_chart_data(
        self, health_analysis: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate chart data for visualization."""
        chart_data = {}

        # Weight trend chart
        weight_trend = health_analysis.get("health_trends", {}).get("weight", {})
        if weight_trend.get("status") == "analyzed":
            chart_data["weight_trend"] = {
                "type": "line",
                "title": "Weight Trend (7 days)",
                "data": {
                    "first_weight": weight_trend.get("first_weight"),
                    "last_weight": weight_trend.get("last_weight"),
                    "trend": weight_trend.get("trend"),
                },
            }

        # Daily feeding amounts
        feeding_analysis = health_analysis.get("feeding_analysis", {})
        daily_amounts = feeding_analysis.get("daily_amounts", {})
        if daily_amounts:
            chart_data["daily_feeding"] = {
                "type": "bar",
                "title": "Daily Food Intake (grams)",
                "data": daily_amounts,
            }

        # Exercise consistency
        activity_analysis = health_analysis.get("activity_analysis", {})
        daily_exercise = activity_analysis.get("daily_exercise", {})
        if daily_exercise:
            chart_data["daily_exercise"] = {
                "type": "bar",
                "title": "Daily Exercise (minutes)",
                "data": {
                    date: data["duration"] / 60 for date, data in daily_exercise.items()
                },
            }

        return chart_data

    async def _generate_pdf_sections(
        self, report: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate PDF-specific sections."""
        sections = [
            {
                "type": "title",
                "content": f"Weekly Health Report - {report['dog_name']}",
            },
            {
                "type": "summary",
                "title": "Executive Summary",
                "content": report["summary"],
            },
            {
                "type": "metrics",
                "title": "Key Health Metrics",
                "content": report["metrics"],
            },
        ]

        if "recommendations" in report:
            sections.append(
                {
                    "type": "recommendations",
                    "title": "Health Recommendations",
                    "content": report["recommendations"],
                }
            )

        return sections

    async def _generate_markdown_report(self, report: dict[str, Any]) -> str:
        """Generate markdown-formatted report."""
        lines = [
            f"# Weekly Health Report - {report['dog_name']}",
            f"**Generated:** {report['generated_at'][:19]} UTC",
            f"**Period:** {report['week_period']['from'][:10]} to {report['week_period']['to'][:10]}",
            "",
            "## Executive Summary",
        ]

        summary = report["summary"]
        lines.append(
            f"**Overall Status:** {summary['overall_status'].replace('_', ' ').title()}"
        )

        if summary.get("positive_trends"):
            lines.append("\n**Positive Trends:**")
            for trend in summary["positive_trends"]:
                lines.append(f"- {trend}")  # noqa: PERF401

        if summary.get("areas_of_concern"):
            lines.append("\n**Areas of Concern:**")
            for concern in summary["areas_of_concern"]:
                lines.append(f"- {concern}")  # noqa: PERF401

        # Add metrics
        lines.append("\n## Key Metrics")
        metrics = report["metrics"]
        for metric, value in metrics.items():
            metric_name = metric.replace("_", " ").title()
            lines.append(f"- **{metric_name}:** {value}%")

        # Add recommendations
        if "recommendations" in report:
            lines.append("\n## Recommendations")
            for rec in report["recommendations"]:
                lines.append(
                    f"\n### {rec['title']} ({rec['priority'].title()} Priority)"
                )
                lines.append(f"{rec['description']}")
                lines.append(f"**Action:** {rec['action']}")

        return "\n".join(lines)

    async def async_generate_report(
        self,
        dog_id: str,
        report_type: str,
        include_recommendations: bool = True,
        days: int = 30,
    ) -> dict[str, Any]:
        """Generate comprehensive report for a dog.

        Args:
            dog_id: Dog identifier
            report_type: Type of report (health, activity, nutrition, comprehensive)
            include_recommendations: Include AI-generated recommendations
            days: Number of days to analyze

        Returns:
            Comprehensive report
        """
        try:
            # Get dog data
            dog_data = await self.async_get_dog_data(dog_id)
            if not dog_data:
                raise ValueError(f"Dog {dog_id} not found")

            # Generate analysis
            analysis = await self.async_analyze_patterns(dog_id, report_type, days)

            # Create report
            report = {
                "dog_id": dog_id,
                "dog_name": dog_data.get("name", dog_id),
                "report_type": report_type,
                "generated_at": dt_util.utcnow().isoformat(),
                "period_days": days,
                "analysis": analysis["patterns"],
                "summary": await self._generate_report_summary(dog_data, analysis),
            }

            if include_recommendations:
                report["recommendations"] = await self._generate_recommendations(
                    dog_data, analysis
                )

            return report

        except Exception as err:
            _LOGGER.error("Failed to generate report for %s: %s", dog_id, err)
            self._metrics["errors"] += 1
            raise

    async def _generate_report_summary(
        self, dog_data: dict[str, Any], analysis: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate report summary."""
        summary = {
            "status": "healthy",  # Simplified
            "activity_level": "normal",
            "key_metrics": {},
        }

        patterns = analysis.get("patterns", {})

        if "feeding" in patterns:
            feeding = patterns["feeding"]
            summary["key_metrics"]["daily_meals"] = feeding.get("meals_per_day", 0)
            summary["key_metrics"]["avg_portion"] = feeding.get("average_portion", 0)

        if "walking" in patterns:
            walking = patterns["walking"]
            summary["key_metrics"]["daily_exercise"] = walking.get(
                "average_duration_minutes", 0
            )
            summary["key_metrics"]["distance_per_walk"] = walking.get(
                "average_distance_km", 0
            )

        return summary

    async def _generate_recommendations(
        self, dog_data: dict[str, Any], analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate simple recommendations based on data."""
        recommendations = []
        patterns = analysis.get("patterns", {})

        # Feeding recommendations
        if "feeding" in patterns:
            feeding = patterns["feeding"]
            meals_per_day = feeding.get("meals_per_day", 0)

            if meals_per_day < 2:
                recommendations.append(
                    {
                        "type": "feeding",
                        "priority": "medium",
                        "title": "Consider more frequent feeding",
                        "description": f"Currently averaging {meals_per_day} meals per day. Most dogs benefit from 2-3 meals daily.",
                    }
                )

        # Walking recommendations
        if "walking" in patterns:
            walking = patterns["walking"]
            avg_duration = walking.get("average_duration_minutes", 0)

            if avg_duration < 30:
                recommendations.append(
                    {
                        "type": "exercise",
                        "priority": "medium",
                        "title": "Increase exercise duration",
                        "description": f"Average walk duration is {avg_duration} minutes. Consider longer walks for better health.",
                    }
                )

        # Health recommendations
        if "health" in patterns:
            health = patterns["health"]
            entries = health.get("total_entries", 0)

            if entries < 5:  # Less than 5 health entries in the period
                recommendations.append(
                    {
                        "type": "health",
                        "priority": "low",
                        "title": "Regular health monitoring",
                        "description": "Consider logging health data more regularly to track trends.",
                    }
                )

        return recommendations
