"""Performance optimization strategies for Paw Control integration.

This module provides optimized entity management, caching strategies,
and efficient update patterns to improve integration performance.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache, wraps
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Performance configuration
ENTITY_UPDATE_DEBOUNCE_TIME = 0.5  # seconds
CACHE_TTL_SECONDS = 300  # 5 minutes
MAX_ENTITIES_PER_DOG = 15  # Limit entity count per dog
BATCH_UPDATE_SIZE = 10  # Process entities in batches


class PerformanceMonitor:
    """Monitor and track performance metrics for the integration."""

    def __init__(self) -> None:
        """Initialize performance monitor."""
        self.update_times: list[float] = []
        self.entity_count = 0
        self.last_update_time: datetime | None = None
        self.slow_updates = 0
        self.failed_updates = 0

    def record_update_time(self, duration: float) -> None:
        """Record an update duration."""
        self.update_times.append(duration)
        # Keep only last 100 measurements
        if len(self.update_times) > 100:
            self.update_times.pop(0)

        # Track slow updates (>1 second)
        if duration > 1.0:
            self.slow_updates += 1
            _LOGGER.warning("Slow update detected: %.2fs", duration)

    def record_failed_update(self) -> None:
        """Record a failed update."""
        self.failed_updates += 1

    @property
    def average_update_time(self) -> float:
        """Get average update time."""
        if not self.update_times:
            return 0.0
        return sum(self.update_times) / len(self.update_times)

    @property
    def performance_score(self) -> float:
        """Calculate performance score (0-100)."""
        if not self.update_times:
            return 100.0

        avg_time = self.average_update_time
        slow_ratio = self.slow_updates / max(len(self.update_times), 1)
        fail_ratio = self.failed_updates / max(len(self.update_times), 1)

        # Score based on speed and reliability
        speed_score = max(0, 100 - (avg_time * 100))
        reliability_score = max(0, 100 - (slow_ratio * 50) - (fail_ratio * 100))

        return (speed_score + reliability_score) / 2


def performance_timer(func: Callable) -> Callable:
    """Decorator to time function execution."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = dt_util.utcnow()
        try:
            result = await func(*args, **kwargs)
            duration = (dt_util.utcnow() - start_time).total_seconds()

            # Log slow functions
            if duration > 0.5:
                _LOGGER.debug("Slow function %s took %.2fs", func.__name__, duration)

            return result
        except Exception as err:
            duration = (dt_util.utcnow() - start_time).total_seconds()
            _LOGGER.error(
                "Function %s failed after %.2fs: %s", func.__name__, duration, err
            )
            raise

    return wrapper


class CacheManager:
    """Manage caching for expensive calculations."""

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        """Initialize cache manager."""
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._lock = asyncio.Lock()

    async def get_or_set(self, key: str, factory: Callable, *args, **kwargs) -> Any:
        """Get cached value or calculate and cache it."""
        async with self._lock:
            now = dt_util.utcnow()

            # Check if cached value exists and is fresh
            if key in self._cache:
                value, timestamp = self._cache[key]
                if (now - timestamp).total_seconds() < self.ttl_seconds:
                    return value

            # Calculate new value
            if asyncio.iscoroutinefunction(factory):
                value = await factory(*args, **kwargs)
            else:
                value = factory(*args, **kwargs)

            # Cache the new value
            self._cache[key] = (value, now)
            return value

    def invalidate(self, key: str) -> None:
        """Invalidate a cached value."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()

    def cleanup_expired(self) -> None:
        """Remove expired cache entries."""
        now = dt_util.utcnow()
        expired_keys = [
            key
            for key, (_, timestamp) in self._cache.items()
            if (now - timestamp).total_seconds() >= self.ttl_seconds
        ]
        for key in expired_keys:
            del self._cache[key]


class OptimizedEntity(CoordinatorEntity):
    """Base entity class with performance optimizations."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
    ) -> None:
        """Initialize optimized entity."""
        super().__init__(coordinator)
        self.dog_id = dog_id
        self.entity_key = entity_key
        self._last_state = None
        self._last_update_time: datetime | None = None
        self._update_count = 0

        # Debouncer for updates
        self._update_debouncer = Debouncer(
            coordinator.hass,
            _LOGGER,
            cooldown=ENTITY_UPDATE_DEBOUNCE_TIME,
            immediate=False,
            function=self._debounced_update,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update with debouncing."""
        # Only update if state actually changed
        current_state = self.state
        if current_state != self._last_state:
            self._last_state = current_state
            self._last_update_time = dt_util.utcnow()
            self._update_count += 1

            # Use debouncer to prevent rapid updates
            self._update_debouncer.async_schedule_update()

    async def _debounced_update(self) -> None:
        """Perform the actual entity update after debouncing."""
        self.async_write_ha_state()

    @property
    def should_poll(self) -> bool:
        """Disable polling for coordinator entities."""
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return optimized state attributes."""
        # Only include essential attributes to reduce payload size
        attributes = {
            "dog_id": self.dog_id,
            "update_count": self._update_count,
        }

        # Add last update time if available
        if self._last_update_time:
            attributes["last_updated"] = self._last_update_time.isoformat()

        return attributes


class EntityManager:
    """Manage entity creation and lifecycle with performance optimizations."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize entity manager."""
        self.hass = hass
        self.entry = entry
        self.performance_monitor = PerformanceMonitor()
        self.cache_manager = CacheManager()
        self._entity_registry: dict[str, set[str]] = {}  # dog_id -> entity_ids

    def register_entity(self, dog_id: str, entity_id: str) -> None:
        """Register an entity for a dog."""
        if dog_id not in self._entity_registry:
            self._entity_registry[dog_id] = set()

        self._entity_registry[dog_id].add(entity_id)
        self.performance_monitor.entity_count = sum(
            len(entities) for entities in self._entity_registry.values()
        )

    def get_entity_count_for_dog(self, dog_id: str) -> int:
        """Get entity count for a specific dog."""
        return len(self._entity_registry.get(dog_id, set()))

    def should_create_entity(self, dog_id: str, entity_type: str) -> bool:
        """Determine if an entity should be created based on performance limits."""
        current_count = self.get_entity_count_for_dog(dog_id)

        # Enforce entity limits per dog
        if current_count >= MAX_ENTITIES_PER_DOG:
            _LOGGER.warning(
                "Entity limit reached for dog %s (%d entities). Skipping %s",
                dog_id,
                current_count,
                entity_type,
            )
            return False

        # Check if this entity type is essential
        essential_entities = {
            "walk_in_progress",
            "is_home",
            "needs_walk",
            "last_walk",
            "walk_distance_today",
            "location",
            "battery_level",
        }

        return (
            entity_type in essential_entities
            or current_count < MAX_ENTITIES_PER_DOG // 2
        )

    @performance_timer
    async def batch_update_entities(
        self, entity_updates: list[tuple[str, dict]]
    ) -> None:
        """Update multiple entities in batches for better performance."""
        if not entity_updates:
            return

        # Process updates in batches
        for i in range(0, len(entity_updates), BATCH_UPDATE_SIZE):
            batch = entity_updates[i : i + BATCH_UPDATE_SIZE]

            # Create update tasks for this batch
            update_tasks = []
            for entity_id, update_data in batch:
                task = self._update_single_entity(entity_id, update_data)
                update_tasks.append(task)

            # Execute batch updates
            try:
                await asyncio.gather(*update_tasks, return_exceptions=True)
            except Exception as err:
                _LOGGER.error("Batch update failed: %s", err)
                self.performance_monitor.record_failed_update()

            # Small delay between batches to prevent overwhelming
            if i + BATCH_UPDATE_SIZE < len(entity_updates):
                await asyncio.sleep(0.1)

    async def _update_single_entity(self, entity_id: str, update_data: dict) -> None:
        """Update a single entity."""
        try:
            # Get entity from registry
            entity_registry = self.hass.helpers.entity_registry.async_get()
            entity_entry = entity_registry.async_get(entity_id)

            if entity_entry:
                # Trigger entity update
                self.hass.async_create_task(
                    self.hass.states.async_set(
                        entity_id,
                        update_data.get("state"),
                        update_data.get("attributes"),
                    )
                )
        except Exception as err:
            _LOGGER.debug("Failed to update entity %s: %s", entity_id, err)


class DataCompressor:
    """Compress and optimize data structures for better performance."""

    @staticmethod
    def compress_dog_data(dog_data: dict[str, Any]) -> dict[str, Any]:
        """Compress dog data by removing unnecessary fields."""
        compressed = {}

        # Only include essential fields
        essential_fields = {
            "info": ["name", "weight"],
            "walk": [
                "walk_in_progress",
                "needs_walk",
                "walk_distance_m",
                "walks_today",
            ],
            "feeding": ["is_hungry", "last_feeding", "feedings_today"],
            "health": ["weight_kg", "medications_today"],
            "location": ["is_home", "distance_from_home", "last_gps_update"],
            "statistics": ["last_action_type"],
        }

        for category, fields in essential_fields.items():
            if category in dog_data:
                compressed[category] = {
                    field: dog_data[category].get(field)
                    for field in fields
                    if field in dog_data[category]
                }

        return compressed

    @staticmethod
    @lru_cache(maxsize=128)
    def calculate_hash(data_str: str) -> str:
        """Calculate hash for data comparison (cached)."""
        import hashlib

        return hashlib.md5(data_str.encode()).hexdigest()

    @staticmethod
    def data_changed(old_data: dict, new_data: dict) -> bool:
        """Efficiently check if data has changed."""
        import json

        old_hash = DataCompressor.calculate_hash(json.dumps(old_data, sort_keys=True))
        new_hash = DataCompressor.calculate_hash(json.dumps(new_data, sort_keys=True))

        return old_hash != new_hash


class SmartUpdateCoordinator:
    """Smart coordinator that only updates when necessary."""

    def __init__(self, coordinator: PawControlCoordinator) -> None:
        """Initialize smart update coordinator."""
        self.coordinator = coordinator
        self.last_data_hashes: dict[str, str] = {}
        self.update_frequencies: dict[str, int] = {}  # Track update frequency per dog

    async def smart_update(self, dog_id: str, new_data: dict[str, Any]) -> bool:
        """Perform smart update that only processes changed data."""
        # Compress data for comparison
        compressed_data = DataCompressor.compress_dog_data(new_data)

        # Calculate hash
        import json

        data_str = json.dumps(compressed_data, sort_keys=True)
        new_hash = DataCompressor.calculate_hash(data_str)

        # Check if data actually changed
        old_hash = self.last_data_hashes.get(dog_id)
        if old_hash == new_hash:
            # Data hasn't changed, skip update
            return False

        # Data changed, perform update
        self.last_data_hashes[dog_id] = new_hash
        self.update_frequencies[dog_id] = self.update_frequencies.get(dog_id, 0) + 1

        # Log high-frequency updates
        if self.update_frequencies[dog_id] % 100 == 0:
            _LOGGER.debug(
                "Dog %s has been updated %d times",
                dog_id,
                self.update_frequencies[dog_id],
            )

        return True

    def get_update_frequency(self, dog_id: str) -> int:
        """Get update frequency for a dog."""
        return self.update_frequencies.get(dog_id, 0)

    def reset_statistics(self) -> None:
        """Reset update statistics."""
        self.update_frequencies.clear()
        self.last_data_hashes.clear()


# Performance utilities
def memory_usage() -> float:
    """Get current memory usage in MB."""
    try:
        import psutil
        import os

        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        return 0.0


def log_performance_metrics(performance_monitor: PerformanceMonitor) -> None:
    """Log current performance metrics."""
    _LOGGER.info(
        "Performance Metrics - Entities: %d, Avg Update: %.2fs, Score: %.1f, Memory: %.1fMB",
        performance_monitor.entity_count,
        performance_monitor.average_update_time,
        performance_monitor.performance_score,
        memory_usage(),
    )
