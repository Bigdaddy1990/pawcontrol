"""Ultra-optimized data management for PawControl with adaptive caching.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import deque
from contextlib import suppress
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DEFAULT_DATA_RETENTION_DAYS, DOMAIN, STORAGE_VERSION
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

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of value."""
        try:
            # Serialize to estimate size
            return len(json.dumps(value, default=str).encode())
        except:  # noqa: E722
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
                    except:  # noqa: E722
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

        except Exception as err:
            _LOGGER.error("Shutdown error: %s", err)

    async def _load_initial_data(self) -> None:
        """Load data with optimized caching."""
        async with self._lock:
            try:
                # Load from storage
                all_data = await self._storage.load()

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

            except Exception as err:
                _LOGGER.error("Load failed: %s", err)
                # Initialize empty
                for namespace in self._namespaces:
                    await self._cache.set(namespace, {}, 60)

    async def _initialize_statistics(self) -> None:
        """Initialize statistics if needed."""
        stats, hit = await self._cache.get("statistics")
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
            all_data = await self._storage.load()
            namespace_data = all_data.get(namespace, {})

            # Cache with adaptive TTL
            await self._cache.set(namespace, namespace_data)

            return namespace_data

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
                all_data = await self._storage.load()

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

    # Core operations
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

    async def async_delete_dog_data(self, dog_id: str) -> None:
        """Delete dog data from all namespaces."""
        async with self._lock:
            try:
                # Delete from all namespaces
                for namespace in self._namespaces:
                    namespace_data = await self._get_namespace_data(namespace)

                    if (namespace == "dogs" and dog_id in namespace_data) or isinstance(
                        namespace_data.get(dog_id), list | dict
                    ):
                        del namespace_data[dog_id]

                    await self._save_namespace(namespace, namespace_data)

                self._metrics["operations"] += 1
                _LOGGER.info("Deleted all data for dog %s", dog_id)

            except Exception as err:
                _LOGGER.error("Delete failed for %s: %s", dog_id, err)
                self._metrics["errors"] += 1
                raise

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
            index_info = self._storage.query_index(module, dog_id)

            # Get module data
            module_data = await self._get_namespace_data(module)
            entries = module_data.get(dog_id, [])

            if not entries:
                return []

            # OPTIMIZATION: Use index to skip unnecessary filtering
            if index_info and start_date:
                first_timestamp = index_info.get("first")
                if first_timestamp:
                    with suppress(ValueError, TypeError):
                        first_time = datetime.fromisoformat(first_timestamp)
                        if first_time > start_date:
                            # All entries are after start_date
                            start_date = None

            # Filter if needed
            if start_date or end_date:
                entries = await self._filter_by_date(entries, start_date, end_date)

            # Sort and limit
            entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

            if limit and limit > 0:
                entries = entries[:limit]

            self._metrics["operations"] += 1
            return entries

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

        # Process in batches for better performance
        for i in range(0, len(entries), CLEANUP_BATCH_SIZE):
            batch = entries[i : i + CLEANUP_BATCH_SIZE]

            for entry in batch:
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

                except:  # noqa: E722
                    filtered.append(entry)

        return filtered

    async def async_cleanup_old_data(
        self, retention_days: int | None = None
    ) -> dict[str, int]:
        """Cleanup with batch processing."""
        if retention_days is None:
            retention_days = DEFAULT_DATA_RETENTION_DAYS

        cutoff = dt_util.utcnow() - timedelta(days=retention_days)
        cleanup_stats = {}

        for module in ["feeding", "walks", "health", "gps", "grooming"]:
            try:
                module_data = await self._get_namespace_data(module)
                total_deleted = 0

                # Process each dog's data
                for dog_id, entries in module_data.items():
                    if not isinstance(entries, list):
                        continue

                    # OPTIMIZATION: Binary search for cutoff point
                    if entries and len(entries) > 10:
                        # Entries are sorted, find cutoff index
                        cutoff_index = await self._find_cutoff_index(entries, cutoff)

                        if cutoff_index > 0:
                            original_count = len(entries)
                            module_data[dog_id] = entries[cutoff_index:]
                            total_deleted += original_count - len(module_data[dog_id])
                    else:
                        # Small list, filter normally
                        original_count = len(entries)
                        module_data[dog_id] = await self._filter_by_date(
                            entries, cutoff, None
                        )
                        total_deleted += original_count - len(module_data[dog_id])

                if total_deleted > 0:
                    await self._save_namespace(module, module_data)

                cleanup_stats[module] = total_deleted

            except Exception as err:
                _LOGGER.error("Cleanup %s failed: %s", module, err)
                cleanup_stats[module] = 0

        self._metrics["last_cleanup"] = dt_util.utcnow().isoformat()
        return cleanup_stats

    async def _find_cutoff_index(
        self, entries: list[dict[str, Any]], cutoff: datetime
    ) -> int:
        """Binary search for cutoff index."""
        left, right = 0, len(entries) - 1

        while left <= right:
            mid = (left + right) // 2

            try:
                timestamp = entries[mid].get("timestamp")
                if isinstance(timestamp, str):
                    entry_time = datetime.fromisoformat(timestamp)
                elif isinstance(timestamp, datetime):
                    entry_time = timestamp
                else:
                    # Skip invalid entries
                    right = mid - 1
                    continue

                if entry_time < cutoff:
                    left = mid + 1
                else:
                    right = mid - 1

            except:  # noqa: E722
                right = mid - 1

        return left

    async def _flush_all(self) -> None:
        """Flush all cached data to storage."""
        try:
            all_data = await self._storage.load()

            for namespace in self._namespaces:
                data, _ = await self._cache.get(namespace)
                if data is not None:
                    all_data[namespace] = data

            await self._storage.save(all_data)
            self._dirty_namespaces.clear()

        except Exception as err:
            _LOGGER.error("Flush failed: %s", err)

    # Module-specific operations (simplified for space)
    async def async_feed_dog(self, dog_id: str, amount: float) -> None:
        """Record feeding."""
        timestamp = dt_util.utcnow().isoformat()
        await self.async_update_dog_data(
            dog_id,
            {
                "feeding": {
                    "last_feeding": timestamp,
                    "last_feeding_amount": amount,
                    "last_feeding_hours": 0,
                }
            },
        )
        self._metrics["operations"] += 1

    async def async_start_walk(self, dog_id: str, walk_data: dict[str, Any]) -> str:
        """Start walk session."""
        timestamp = dt_util.utcnow()
        walk_id = f"walk_{dog_id}_{int(timestamp.timestamp())}"

        walk_entry = {
            "walk_id": walk_id,
            "dog_id": dog_id,
            "start_time": timestamp.isoformat(),
            "status": "in_progress",
            **walk_data,
        }

        await self._append_module_data("walks", dog_id, walk_entry)

        await self.async_update_dog_data(
            dog_id,
            {
                "walk": {
                    "walk_in_progress": True,
                    "current_walk_id": walk_id,
                    "current_walk_start": timestamp.isoformat(),
                }
            },
        )

        return walk_id

    async def async_end_walk(
        self, dog_id: str, walk_data: dict[str, Any] | None = None
    ) -> None:
        """End walk session."""
        dog_data = await self.async_get_dog_data(dog_id)
        if not dog_data or not dog_data.get("walk", {}).get("walk_in_progress"):
            return

        walk_id = dog_data["walk"].get("current_walk_id")
        if not walk_id:
            return

        timestamp = dt_util.utcnow()

        # Calculate duration
        start_str = dog_data["walk"].get("current_walk_start")
        duration_minutes = 0

        if start_str:
            with suppress(ValueError, TypeError):
                start_time = datetime.fromisoformat(start_str)
                duration_minutes = int((timestamp - start_time).total_seconds() / 60)

        # Update walk entry
        walk_updates = {
            "end_time": timestamp.isoformat(),
            "status": "completed",
            "duration_minutes": duration_minutes,
            **(walk_data or {}),
        }

        await self._update_module_entry("walks", dog_id, walk_id, walk_updates)

        # Update dog status
        await self.async_update_dog_data(
            dog_id,
            {
                "walk": {
                    "walk_in_progress": False,
                    "current_walk_id": None,
                    "current_walk_start": None,
                    "last_walk": timestamp.isoformat(),
                    "last_walk_duration": duration_minutes,
                }
            },
        )

    async def async_get_current_walk(self, dog_id: str) -> dict[str, Any] | None:
        """Get current walk if active."""
        dog_data = await self.async_get_dog_data(dog_id)
        if not dog_data or not dog_data.get("walk", {}).get("walk_in_progress"):
            return None

        walk_id = dog_data["walk"].get("current_walk_id")
        if not walk_id:
            return None

        walks = await self.async_get_module_data("walks", dog_id, limit=10)
        for walk in walks:
            if walk.get("walk_id") == walk_id:
                return walk

        return None

    async def async_get_current_gps_data(self, dog_id: str) -> dict[str, Any] | None:
        """Get current GPS data."""
        dog_data = await self.async_get_dog_data(dog_id)
        return dog_data.get("gps") if dog_data else None

    async def async_reset_dog_daily_stats(self, dog_id: str) -> None:
        """Reset daily statistics."""
        reset_data = {
            "feeding": {
                "daily_food_consumed": 0,
                "daily_calories": 0,
                "meals_today": 0,
            },
            "walk": {
                "walks_today": 0,
                "daily_walk_time": 0,
                "daily_walk_distance": 0,
            },
            "last_reset": dt_util.utcnow().isoformat(),
        }

        if dog_id == "all":
            dogs = await self._get_namespace_data("dogs")
            for single_id in dogs:
                await self.async_update_dog_data(single_id, reset_data)
        else:
            await self.async_update_dog_data(dog_id, reset_data)

    async def _append_module_data(
        self, module: str, dog_id: str, entry: dict[str, Any]
    ) -> None:
        """Append entry to module data."""
        module_data = await self._get_namespace_data(module)

        if dog_id not in module_data:
            module_data[dog_id] = []

        module_data[dog_id].append(entry)
        await self._save_namespace(module, module_data)

    async def _update_module_entry(
        self, module: str, dog_id: str, entry_id: str, updates: dict[str, Any]
    ) -> None:
        """Update module entry."""
        module_data = await self._get_namespace_data(module)

        if dog_id in module_data:
            id_field = f"{module[:-1]}_id"

            for entry in module_data[dog_id]:
                if entry.get(id_field) == entry_id:
                    entry.update(updates)
                    break

            await self._save_namespace(module, module_data)

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
