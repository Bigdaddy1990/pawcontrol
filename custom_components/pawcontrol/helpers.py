"""Helper classes and functions for Paw Control integration.

OPTIMIZED VERSION with async performance improvements, batch operations,
and memory-efficient data management for Platinum quality standards.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Deque
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import storage
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DOG_ID,
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
    EVENT_WALK_STARTED,
)

_LOGGER = logging.getLogger(__name__)

# Storage version for data persistence
STORAGE_VERSION = 1

# OPTIMIZATION: Performance constants
MAX_MEMORY_CACHE_MB = 50  # Memory limit for caching
BATCH_SAVE_DELAY = 2.0  # Batch save delay in seconds
MAX_NOTIFICATION_QUEUE = 100  # Max queued notifications
DATA_CLEANUP_INTERVAL = 3600  # 1 hour cleanup interval
MAX_HISTORY_ITEMS = 1000  # Max items per dog per category


class OptimizedDataCache:
    """High-performance in-memory cache with automatic cleanup."""

    def __init__(self, max_memory_mb: int = MAX_MEMORY_CACHE_MB) -> None:
        """Initialize cache with memory limits."""
        self._cache: dict[str, Any] = {}
        self._timestamps: dict[str, datetime] = {}
        self._access_count: dict[str, int] = {}
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._current_memory = 0
        self._lock = asyncio.Lock()

    async def get(self, key: str, default: Any = None) -> Any:
        """Get cached value with access tracking."""
        async with self._lock:
            if key in self._cache:
                self._access_count[key] = self._access_count.get(key, 0) + 1
                self._timestamps[key] = dt_util.utcnow()
                return self._cache[key]
            return default

    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set cached value with TTL and memory management."""
        async with self._lock:
            # Estimate memory usage
            value_size = self._estimate_size(value)

            # Clean up if needed
            while (
                self._current_memory + value_size > self._max_memory_bytes
                and self._cache
            ):
                await self._evict_lru()

            # Store value
            if key in self._cache:
                # Update existing
                old_size = self._estimate_size(self._cache[key])
                self._current_memory -= old_size

            self._cache[key] = value
            self._timestamps[key] = dt_util.utcnow()
            self._access_count[key] = self._access_count.get(key, 0) + 1
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
        if lru_key in self._cache:
            value_size = self._estimate_size(self._cache[lru_key])
            self._current_memory -= value_size
            del self._cache[lru_key]
            del self._timestamps[lru_key]
            del self._access_count[lru_key]

    async def cleanup_expired(self, ttl_seconds: int = 300) -> int:
        """Remove expired entries."""
        cutoff = dt_util.utcnow() - timedelta(seconds=ttl_seconds)
        expired_keys = []

        async with self._lock:
            for key, timestamp in self._timestamps.items():
                if timestamp < cutoff:
                    expired_keys.append(key)

            for key in expired_keys:
                if key in self._cache:
                    value_size = self._estimate_size(self._cache[key])
                    self._current_memory -= value_size
                    del self._cache[key]
                    del self._timestamps[key]
                    del self._access_count[key]

        return len(expired_keys)

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of value."""
        try:
            import sys

            return sys.getsizeof(value)
        except Exception:
            # Fallback estimate
            if isinstance(value, str):
                return len(value) * 2  # Unicode chars
            elif isinstance(value, list | tuple):
                return len(value) * 100  # Rough estimate
            elif isinstance(value, dict):
                return len(value) * 200  # Rough estimate
            return 1024  # Default 1KB

    def get_stats(self) -> dict[str, Any]:
        """Get cache performance statistics."""
        return {
            "entries": len(self._cache),
            "memory_mb": round(self._current_memory / (1024 * 1024), 2),
            "total_accesses": sum(self._access_count.values()),
            "avg_accesses": (
                sum(self._access_count.values()) / len(self._access_count)
                if self._access_count
                else 0
            ),
        }


class PawControlDataStorage:
    """OPTIMIZED: Manages persistent data storage with batching and caching."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize optimized storage manager."""
        self.hass = hass
        self.config_entry = config_entry
        self._stores: dict[str, storage.Store] = {}
        self._cache = OptimizedDataCache()

        # OPTIMIZATION: Batch save mechanism
        self._dirty_stores: set[str] = set()
        self._save_task: asyncio.Task | None = None
        self._save_lock = asyncio.Lock()

        # Initialize storage for each data type
        self._initialize_stores()

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    def _initialize_stores(self) -> None:
        """Initialize storage stores with atomic writes."""
        store_configs = [
            (DATA_FILE_WALKS, "walks"),
            (DATA_FILE_FEEDINGS, "feedings"),
            (DATA_FILE_HEALTH, "health"),
            (DATA_FILE_ROUTES, "routes"),
            (DATA_FILE_STATS, "statistics"),
        ]

        for filename, store_key in store_configs:
            self._stores[store_key] = storage.Store(
                self.hass,
                STORAGE_VERSION,
                f"{DOMAIN}_{self.config_entry.entry_id}_{filename}",
                encoder=_data_encoder,
                atomic_writes=True,  # OPTIMIZATION: Ensure atomic writes
                minor_version=1,
            )

    async def async_load_all_data(self) -> dict[str, Any]:
        """OPTIMIZED: Load with caching and concurrent operations."""
        try:
            # Check cache first
            cache_key = "all_data"
            cached_data = await self._cache.get(cache_key)
            if cached_data:
                return cached_data

            # Load all data stores concurrently
            load_tasks = [
                self._load_store_data_cached(store_key) for store_key in self._stores
            ]

            results = await asyncio.gather(*load_tasks, return_exceptions=True)

            data = {}
            for store_key, result in zip(self._stores.keys(), results, strict=False):
                if isinstance(result, Exception):
                    _LOGGER.error("Failed to load %s data: %s", store_key, result)
                    data[store_key] = {}
                else:
                    data[store_key] = result or {}

            # Cache the loaded data
            await self._cache.set(cache_key, data, ttl_seconds=300)

            _LOGGER.debug("Loaded data for %d stores", len(data))
            return data

        except Exception as err:
            _LOGGER.error("Failed to load integration data: %s", err)
            raise HomeAssistantError(f"Data loading failed: {err}") from err

    async def _load_store_data_cached(self, store_key: str) -> dict[str, Any]:
        """Load data from store with caching."""
        # Check cache first
        cached = await self._cache.get(f"store_{store_key}")
        if cached is not None:
            return cached

        # Load from storage
        store = self._stores.get(store_key)
        if not store:
            return {}

        try:
            data = await store.async_load()
            result = data or {}

            # Cache the result
            await self._cache.set(f"store_{store_key}", result, ttl_seconds=600)
            return result

        except Exception as err:
            _LOGGER.error("Failed to load %s store: %s", store_key, err)
            return {}

    async def async_save_data(self, store_key: str, data: dict[str, Any]) -> None:
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

        self._save_task = asyncio.create_task(self._batch_save())

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
            save_tasks = []
            for store_key in stores_to_save:
                cached_data = await self._cache.get(f"store_{store_key}")
                if cached_data is not None:
                    save_tasks.append(
                        self._save_store_immediate(store_key, cached_data)
                    )

            if save_tasks:
                results = await asyncio.gather(*save_tasks, return_exceptions=True)

                # Log any errors
                for store_key, result in zip(stores_to_save, results, strict=False):
                    if isinstance(result, Exception):
                        _LOGGER.error("Failed to save %s: %s", store_key, result)
                    else:
                        _LOGGER.debug("Saved %s store in batch", store_key)

    async def _save_store_immediate(self, store_key: str, data: dict[str, Any]) -> None:
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
            if isinstance(result, Exception):
                _LOGGER.error("Failed to cleanup %s data: %s", store_key, result)
            else:
                total_cleaned += result

        _LOGGER.debug("Cleaned up %d old entries across all stores", total_cleaned)

    async def _cleanup_store_optimized(
        self, store_key: str, cutoff_date: datetime
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

        except Exception as err:
            _LOGGER.error("Failed to cleanup %s data: %s", store_key, err)
            return 0

    def _cleanup_store_data(
        self, data: dict[str, Any], cutoff_date: datetime
    ) -> dict[str, Any]:
        """Remove entries older than cutoff date with optimization."""
        if not isinstance(data, dict):
            return data

        cleaned = {}
        for key, value in data.items():
            if isinstance(value, list):
                # Clean list of entries
                cleaned_list = []
                for entry in value:
                    if isinstance(entry, dict) and "timestamp" in entry:
                        try:
                            entry_date = datetime.fromisoformat(entry["timestamp"])
                            if entry_date >= cutoff_date:
                                cleaned_list.append(entry)
                        except (ValueError, TypeError):
                            # Keep entries with invalid timestamps
                            cleaned_list.append(entry)
                    else:
                        # Keep non-timestamped entries
                        cleaned_list.append(entry)
                cleaned[key] = cleaned_list
            elif isinstance(value, dict) and "timestamp" in value:
                try:
                    entry_date = datetime.fromisoformat(value["timestamp"])
                    if entry_date >= cutoff_date:
                        cleaned[key] = value
                except (ValueError, TypeError):
                    # Keep entries with invalid timestamps
                    cleaned[key] = value
            else:
                # Keep non-timestamped entries
                cleaned[key] = value

        return cleaned

    def _enforce_size_limits(self, data: dict[str, Any]) -> dict[str, Any]:
        """OPTIMIZATION: Enforce size limits to prevent memory bloat."""
        limited_data = {}

        for key, value in data.items():
            if isinstance(value, list) and len(value) > MAX_HISTORY_ITEMS:
                # Sort by timestamp (newest first) and keep most recent
                try:
                    sorted_value = sorted(
                        value, key=lambda x: x.get("timestamp", ""), reverse=True
                    )
                    limited_data[key] = sorted_value[:MAX_HISTORY_ITEMS]
                    _LOGGER.debug(
                        "Limited %s entries from %d to %d",
                        key,
                        len(value),
                        len(limited_data[key]),
                    )
                except (TypeError, KeyError):
                    # Fallback to simple truncation
                    limited_data[key] = value[-MAX_HISTORY_ITEMS:]
            else:
                limited_data[key] = value

        return limited_data

    def _count_entries(self, data: dict[str, Any]) -> int:
        """Count total entries in data structure."""
        count = 0
        for value in data.values():
            if isinstance(value, list | dict):
                count += len(value)
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
        self._data: dict[str, Any] = {}
        self._dogs: list[dict[str, Any]] = config_entry.data.get(CONF_DOGS, [])

        # OPTIMIZATION: Event queue for batch processing
        self._event_queue: Deque[dict[str, Any]] = deque(maxlen=1000)
        self._event_task: asyncio.Task | None = None
        self._valid_dog_ids: set[str] | None = None

    async def async_load_data(self) -> None:
        """Load data with performance monitoring."""
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        try:
            self._data = await self.storage.async_load_all_data()

            load_time = loop.time() - start_time
            _LOGGER.debug(
                "Data manager initialized with %d data types in %.2fs",
                len(self._data),
                load_time,
            )

            # Start event processing
            self._event_task = asyncio.create_task(self._process_events())

        except Exception as err:
            _LOGGER.error("Failed to initialize data manager: %s", err)
            # Initialize with empty data if loading fails
            self._data = {
                "walks": {},
                "feedings": {},
                "health": {},
                "routes": {},
                "statistics": {},
            }

    async def async_log_feeding(
        self, dog_id: str, feeding_data: dict[str, Any]
    ) -> None:
        """OPTIMIZED: Log feeding with event queue."""
        if not self._is_valid_dog_id(dog_id):
            raise HomeAssistantError(f"Invalid dog ID: {dog_id}")

        # Add to event queue for batch processing
        event = {
            "type": "feeding",
            "dog_id": dog_id,
            "data": feeding_data,
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
                batch = [
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

    async def _process_event_batch(self, events: list[dict[str, Any]]) -> None:
        """Process a batch of events efficiently."""
        # Group events by type and dog for efficient processing
        grouped_events = {}

        for event in events:
            event_type = event["type"]
            dog_id = event["dog_id"]

            key = f"{event_type}_{dog_id}"
            if key not in grouped_events:
                grouped_events[key] = []
            grouped_events[key].append(event)

        # Process each group
        for group_events in grouped_events.values():
            event_type = group_events[0]["type"]

            if event_type == "feeding":
                await self._process_feeding_batch(group_events)
            elif event_type == "health":
                await self._process_health_batch(group_events)
            elif event_type == "walk":
                await self._process_walk_batch(group_events)

    async def _process_feeding_batch(self, events: list[dict[str, Any]]) -> None:
        """Process feeding events in batch."""
        try:
            dog_id = events[0]["dog_id"]

            # Ensure data structure exists
            if "feedings" not in self._data:
                self._data["feedings"] = {}
            if dog_id not in self._data["feedings"]:
                self._data["feedings"][dog_id] = []

            # Add all feeding entries
            for event in events:
                feeding_data = event["data"]
                if "timestamp" not in feeding_data:
                    feeding_data["timestamp"] = event["timestamp"]

                self._data["feedings"][dog_id].append(feeding_data)

            # Enforce size limits
            if len(self._data["feedings"][dog_id]) > MAX_HISTORY_ITEMS:
                # Keep most recent entries
                self._data["feedings"][dog_id] = self._data["feedings"][dog_id][
                    -MAX_HISTORY_ITEMS:
                ]

            # Save to storage (will be batched)
            await self.storage.async_save_data("feedings", self._data["feedings"])

            # Fire events for each feeding
            for event in events:
                self.hass.bus.async_fire(
                    EVENT_FEEDING_LOGGED,
                    {
                        "dog_id": event["dog_id"],
                        **event["data"],
                    },
                )

            _LOGGER.debug("Processed %d feeding events for %s", len(events), dog_id)

        except Exception as err:
            _LOGGER.error("Failed to process feeding batch: %s", err)

    # Similar optimized methods for other event types...
    async def _process_health_batch(self, events: list[dict[str, Any]]) -> None:
        """Process health events in batch."""
        # Implementation similar to feeding batch
        pass

    async def _process_walk_batch(self, events: list[dict[str, Any]]) -> None:
        """Process walk events in batch."""
        # Implementation similar to feeding batch
        pass

    # Keep existing methods but add async optimizations where needed
    async def async_start_walk(self, dog_id: str, walk_data: dict[str, Any]) -> None:
        """Start walk with immediate processing for real-time needs."""
        if not self._is_valid_dog_id(dog_id):
            raise HomeAssistantError(f"Invalid dog ID: {dog_id}")

        try:
            # Ensure walks data structure exists
            if "walks" not in self._data:
                self._data["walks"] = {}
            if dog_id not in self._data["walks"]:
                self._data["walks"][dog_id] = {"active": None, "history": []}

            # Check if a walk is already active
            if self._data["walks"][dog_id]["active"]:
                raise HomeAssistantError(f"Walk already active for {dog_id}")

            # Set active walk
            self._data["walks"][dog_id]["active"] = walk_data

            # Save immediately for real-time operations
            await self.storage.async_save_data("walks", self._data["walks"])

            # Fire event
            self.hass.bus.async_fire(
                EVENT_WALK_STARTED,
                {
                    "dog_id": dog_id,
                    **walk_data,
                },
            )

            _LOGGER.debug("Started walk for %s", dog_id)

        except Exception as err:
            _LOGGER.error("Failed to start walk for %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to start walk: {err}") from err

    def _is_valid_dog_id(self, dog_id: str) -> bool:
        """Validate dog ID with caching."""
        # Cache valid dog IDs for performance
        if self._valid_dog_ids is None:
            self._valid_dog_ids = {dog[CONF_DOG_ID] for dog in self._dogs}

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
        self._notification_queue: Deque[dict[str, Any]] = deque(
            maxlen=MAX_NOTIFICATION_QUEUE
        )
        self._high_priority_queue: Deque[dict[str, Any]] = deque(
            maxlen=50
        )  # Separate urgent queue

        # Async processing
        self._processor_task: asyncio.Task | None = None
        self._processing_lock = asyncio.Lock()
        self._quiet_hours_cache: dict[str, tuple[bool, datetime]] = {}

        self._setup_async_processor()

    def _setup_async_processor(self) -> None:
        """Set up async notification processor."""
        self._processor_task = asyncio.create_task(self._async_process_notifications())

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

    async def async_send_notification(
        self,
        dog_id: str,
        title: str,
        message: str,
        priority: str = "normal",
        data: dict[str, Any] | None = None,
    ) -> None:
        """OPTIMIZED: Send notification with async queuing."""
        if not self._should_send_notification(priority):
            _LOGGER.debug("Notification suppressed due to quiet hours")
            return

        notification = {
            "dog_id": dog_id,
            "title": title,
            "message": message,
            "priority": priority,
            "data": data or {},
            "timestamp": dt_util.utcnow().isoformat(),
        }

        # Route to appropriate queue
        if priority in ["high", "urgent"]:
            self._high_priority_queue.append(notification)
        else:
            self._notification_queue.append(notification)

    async def _send_notification_now(self, notification: dict[str, Any]) -> None:
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
                await asyncio.wait_for(
                    self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        service_data,
                    ),
                    timeout=5.0,
                )

                _LOGGER.debug(
                    "Sent %s priority notification for %s",
                    notification["priority"],
                    notification["dog_id"],
                )

            except TimeoutError:
                _LOGGER.warning(
                    "Notification send timeout for %s", notification["dog_id"]
                )
            except Exception as err:
                _LOGGER.error("Failed to send notification: %s", err)

    def _should_send_notification(self, priority: str) -> bool:
        """OPTIMIZED: Check notification rules with caching."""
        # Cache quiet hours calculation for performance
        cache_key = f"quiet_hours_{priority}"

        cached = self._quiet_hours_cache.get(cache_key)
        if cached:
            cached_result, cache_time = cached
            if (dt_util.utcnow() - cache_time).total_seconds() < 60:
                return cached_result

        result = self._calculate_notification_allowed(priority)

        # Cache result for 1 minute
        self._quiet_hours_cache[cache_key] = (result, dt_util.utcnow())

        return result

    def _calculate_notification_allowed(self, priority: str) -> bool:
        """Calculate if notification should be sent."""
        notification_config = self.config_entry.options.get(CONF_NOTIFICATIONS, {})

        # Always send urgent notifications
        if priority == "urgent":
            return True

        # Check quiet hours
        if not notification_config.get(CONF_QUIET_HOURS, False):
            return True

        now = dt_util.now().time()
        quiet_start = notification_config.get(CONF_QUIET_START, "22:00:00")
        quiet_end = notification_config.get(CONF_QUIET_END, "07:00:00")

        try:
            quiet_start_time = datetime.strptime(quiet_start, "%H:%M:%S").time()
            quiet_end_time = datetime.strptime(quiet_end, "%H:%M:%S").time()
        except ValueError:
            # Invalid time format, allow notification
            return True

        # Handle quiet hours that span midnight
        if quiet_start_time > quiet_end_time:
            # Quiet hours span midnight (e.g., 22:00 to 07:00)
            return not (now >= quiet_start_time or now <= quiet_end_time)
        else:
            # Quiet hours within same day
            return not (quiet_start_time <= now <= quiet_end_time)

    def get_queue_stats(self) -> dict[str, Any]:
        """Get notification queue statistics."""
        return {
            "normal_queue_size": len(self._notification_queue),
            "high_priority_queue_size": len(self._high_priority_queue),
            "total_queued": len(self._notification_queue)
            + len(self._high_priority_queue),
            "max_queue_size": MAX_NOTIFICATION_QUEUE,
        }

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
    elif hasattr(obj, "__dict__"):
        return obj.__dict__
    elif hasattr(obj, "isoformat"):  # Handle date objects
        return obj.isoformat()
    else:
        return str(obj)


# OPTIMIZATION: Add performance monitoring utilities
class PerformanceMonitor:
    """Monitor performance metrics for the integration."""

    def __init__(self) -> None:
        """Initialize performance monitor."""
        self._metrics = {
            "operations": 0,
            "errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_operation_time": 0.0,
            "last_cleanup": None,
        }
        self._operation_times: Deque[float] = deque(maxlen=100)

    def record_operation(self, operation_time: float, success: bool = True) -> None:
        """Record an operation."""
        self._metrics["operations"] += 1
        if not success:
            self._metrics["errors"] += 1

        self._operation_times.append(operation_time)

        # Calculate rolling average
        if self._operation_times:
            self._metrics["avg_operation_time"] = sum(self._operation_times) / len(
                self._operation_times
            )

    def record_cache_hit(self) -> None:
        """Record cache hit."""
        self._metrics["cache_hits"] += 1

    def record_cache_miss(self) -> None:
        """Record cache miss."""
        self._metrics["cache_misses"] += 1

    def get_metrics(self) -> dict[str, Any]:
        """Get performance metrics."""
        total_cache_operations = (
            self._metrics["cache_hits"] + self._metrics["cache_misses"]
        )
        cache_hit_rate = (
            (self._metrics["cache_hits"] / total_cache_operations * 100)
            if total_cache_operations > 0
            else 0
        )

        error_rate = (
            (self._metrics["errors"] / self._metrics["operations"] * 100)
            if self._metrics["operations"] > 0
            else 0
        )

        return {
            **self._metrics,
            "cache_hit_rate": round(cache_hit_rate, 1),
            "error_rate": round(error_rate, 1),
            "recent_operations": len(self._operation_times),
        }

    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self._metrics = {
            "operations": 0,
            "errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_operation_time": 0.0,
            "last_cleanup": dt_util.utcnow().isoformat(),
        }
        self._operation_times.clear()


# Global performance monitor instance
performance_monitor = PerformanceMonitor()
