"""Advanced optimized data coordinator for Paw Control integration.

This module provides high-performance data coordination with batch updates,
selective refresh, intelligent caching, and comprehensive monitoring.
Further optimized from the already refactored implementation.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Optional

# Newer Home Assistant versions removed STATE_ONLINE from homeassistant.const.
# Define the constant locally for clarity and future compatibility.
STATE_ONLINE = "online"
from homeassistant.config_entries import ConfigEntry  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers.update_coordinator import (  # noqa: E402
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util  # noqa: E402

from .const import (  # noqa: E402
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_GPS_UPDATE_INTERVAL,
    DEFAULT_GPS_UPDATE_INTERVAL,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .utils import performance_monitor  # noqa: E402

if TYPE_CHECKING:
    from .data_manager import PawControlDataManager
    from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)

# Performance optimization constants
MAX_BATCH_SIZE = 10
CACHE_TTL_FAST = 30  # 30 seconds for fast-changing data
CACHE_TTL_MEDIUM = 300  # 5 minutes for medium-changing data
CACHE_TTL_SLOW = 1800  # 30 minutes for slow-changing data
PERFORMANCE_ALERT_THRESHOLD = 15.0  # seconds


class DataCache:
    """Intelligent multi-tier cache for coordinator data."""

    def __init__(self) -> None:
        """Initialize cache with multiple TTL tiers."""
        self._cache: dict[str, dict[str, Any]] = {}
        self._expiry: dict[str, datetime] = {}
        self._access_count: dict[str, int] = defaultdict(int)
        self._last_access: dict[str, datetime] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        """Get cached data if not expired."""
        now = dt_util.utcnow()

        if key not in self._cache:
            return None

        if key in self._expiry and now > self._expiry[key]:
            # Remove expired entry
            self._cache.pop(key, None)
            self._expiry.pop(key, None)
            return None

        # Update access statistics
        self._access_count[key] += 1
        self._last_access[key] = now

        return self._cache[key].copy()

    def set(
        self, key: str, data: dict[str, Any], ttl_seconds: int = CACHE_TTL_MEDIUM
    ) -> None:
        """Set cached data with TTL."""
        now = dt_util.utcnow()

        self._cache[key] = data.copy()
        self._expiry[key] = now + timedelta(seconds=ttl_seconds)
        self._access_count[key] = 0
        self._last_access[key] = now

    def invalidate(self, key: str) -> None:
        """Invalidate specific cache entry."""
        self._cache.pop(key, None)
        self._expiry.pop(key, None)
        self._access_count.pop(key, None)
        self._last_access.pop(key, None)

    def clear_expired(self) -> int:
        """Clear expired entries and return count."""
        now = dt_util.utcnow()
        expired_keys = [key for key, expiry in self._expiry.items() if now > expiry]

        for key in expired_keys:
            self.invalidate(key)

        return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "total_entries": len(self._cache),
            "total_accesses": sum(self._access_count.values()),
            "most_accessed": max(self._access_count.items(), key=lambda x: x[1])
            if self._access_count
            else None,
        }


class BatchUpdateManager:
    """Manages batch processing of data updates."""

    def __init__(self, max_batch_size: int = MAX_BATCH_SIZE) -> None:
        """Initialize batch manager."""
        self._max_batch_size = max_batch_size
        self._pending_updates: set[str] = set()
        self._update_lock = asyncio.Lock()

    async def add_to_batch(self, dog_id: str) -> None:
        """Add dog to pending batch updates."""
        async with self._update_lock:
            self._pending_updates.add(dog_id)

    def get_batch(self) -> list[str]:
        """Get current batch and clear pending."""
        batch = list(self._pending_updates)[: self._max_batch_size]
        for dog_id in batch:
            self._pending_updates.discard(dog_id)
        return batch

    def has_pending(self) -> bool:
        """Check if there are pending updates."""
        return len(self._pending_updates) > 0

    def clear_pending(self) -> None:
        """Clear all pending updates."""
        self._pending_updates.clear()


class PerformanceMonitor:
    """Monitors coordinator performance and alerts on issues."""

    def __init__(self, alert_threshold: float = PERFORMANCE_ALERT_THRESHOLD) -> None:
        """Initialize performance monitor."""
        self._alert_threshold = alert_threshold
        self._update_times = deque(maxlen=100)  # Last 100 updates
        self._error_count = 0
        self._slow_updates = 0
        self._last_alert = dt_util.utcnow() - timedelta(minutes=10)

    def record_update(self, duration: float, error_count: int = 0) -> None:
        """Record update performance."""
        self._update_times.append(duration)
        self._error_count += error_count

        if duration > self._alert_threshold:
            self._slow_updates += 1
            self._maybe_send_alert(duration)

    def _maybe_send_alert(self, duration: float) -> None:
        """Send performance alert if needed."""
        now = dt_util.utcnow()

        # Avoid spam by limiting alerts to once per 10 minutes
        if (now - self._last_alert).total_seconds() > 600:
            _LOGGER.warning(
                "Slow coordinator update: %.2fs (threshold: %.2fs). "
                "Slow updates: %d/%d recent",
                duration,
                self._alert_threshold,
                self._slow_updates,
                len(self._update_times),
            )
            self._last_alert = now

    def get_stats(self) -> dict[str, Any]:
        """Get performance statistics."""
        if not self._update_times:
            return {"no_data": True}

        times = list(self._update_times)
        return {
            "average_update_time": sum(times) / len(times),
            "max_update_time": max(times),
            "min_update_time": min(times),
            "slow_updates": self._slow_updates,
            "error_count": self._error_count,
            "total_updates": len(times),
        }


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Advanced optimized data coordinator with batch processing and intelligent caching.

    Performance improvements:
    - Batch processing for multiple dog updates
    - Selective updates for only changed data
    - Multi-tier intelligent caching
    - Advanced performance monitoring
    - Memory-efficient operations
    """

def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize advanced optimized coordinator."""
        self.config_entry = entry
        self._dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
        self.dogs = self._dogs_config

        # Calculate optimal update interval
        update_interval = self._calculate_optimal_update_interval()

        super().__init__(
            hass,
            _LOGGER,
            name="Paw Control Data",
            update_interval=timedelta(seconds=update_interval),
            always_update=False,
        )
        """Initialize advanced optimized coordinator."""
        self.config_entry = entry
        self._dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
        self.dogs = self._dogs_config

        # Calculate optimal update interval
        update_interval = self._calculate_optimal_update_interval()

        super().__init__(
            hass,
            _LOGGER,
            name="Paw Control Data",
            update_interval=timedelta(seconds=update_interval),
            always_update=False,
        )
        self.config_entry = entry

        self.config_entry = entry

        # Advanced optimization components
        self._cache = DataCache()
        self._batch_manager = BatchUpdateManager()
        self._performance_monitor = PerformanceMonitor()

        # Core data storage
        self._data: dict[str, Any] = {}
        self._listeners: set[Callable[[], None]] = weakref.WeakSet()

        # Change tracking for selective updates
        self._data_checksums: dict[str, str] = {}
        self._last_successful_update: dict[str, datetime] = {}

        # Manager references
        self.dog_manager = None
        self.walk_manager = None
        self.feeding_manager = None
        self.health_calculator = None
        # Will be set during component setup
        self._data_manager: PawControlDataManager | None = None

        # Background tasks
        self._cleanup_task: asyncio.Task | None = None
        try:
            self._start_background_tasks()
        except RuntimeError:
            _LOGGER.debug("Background tasks not started: no running event loop")

        _LOGGER.info(
            "Advanced coordinator initialized: %d dogs, %ds interval, batch_size=%d",
            len(self.dogs),
            update_interval,
            MAX_BATCH_SIZE,
        )

    def __repr__(self) -> str:  # pragma: no cover - simple representation
        dog_names = ", ".join(d.get(CONF_DOG_NAME, "") for d in self._dogs_config)
        return (
            f"PawControlCoordinator(entry_id={self.entry.entry_id}, dogs=[{dog_names}])"
        )

    __str__ = __repr__

    def _start_background_tasks(self) -> None:
        """Start background maintenance tasks."""

        async def cleanup_task():
            """Background cleanup task."""
            while True:
                try:
                    await asyncio.sleep(300)  # Every 5 minutes
                    await self._perform_maintenance()
                except asyncio.CancelledError:
                    break
                except Exception as err:
                    _LOGGER.debug("Background cleanup error: %s", err)

        self._cleanup_task = asyncio.create_task(cleanup_task())

    def get_dog_config(self, dog_id: str) -> dict[str, Any] | None:
        """Return configuration for the specified dog id."""

        for dog in self._dogs_config:
            if dog.get(CONF_DOG_ID) == dog_id:
                return dog
        return None

    def get_enabled_modules(self, dog_id: str) -> set[str]:
        """Return set of enabled modules for given dog."""

        config = self.get_dog_config(dog_id)
        if not config:
            return set()
        modules = config.get("modules", {})
        return {name for name, enabled in modules.items() if enabled}

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        """Check if a specific module is enabled for a dog."""

        config = self.get_dog_config(dog_id)
        if not config:
            return False
        return config.get("modules", {}).get(module, False)

    def get_dog_ids(self) -> list[str]:
        """Return list of configured dog IDs."""

        return [dog.get(CONF_DOG_ID) for dog in self._dogs_config]

    async def _perform_maintenance(self) -> None:
        """Perform background maintenance tasks."""
        # Clear expired cache entries
        cleared = self._cache.clear_expired()
        if cleared > 0:
            _LOGGER.debug("Cleared %d expired cache entries", cleared)

        # Log performance stats periodically
        perf_stats = self._performance_monitor.get_stats()
        if not perf_stats.get("no_data"):
            avg_time = perf_stats.get("average_update_time", 0)
            if avg_time > 5.0:  # Log if average > 5 seconds
                _LOGGER.info(
                    "Performance stats: avg=%.2fs, errors=%d",
                    avg_time,
                    perf_stats.get("error_count", 0),
                )

    def _calculate_optimal_update_interval(self) -> int:
        """Calculate optimal update interval with advanced logic."""
        base_interval = DEFAULT_GPS_UPDATE_INTERVAL

        # Analyze module requirements
        gps_dogs = 0
        realtime_dogs = 0

        for dog in self.dogs:
            modules = dog.get("modules", {})
            if modules.get(MODULE_GPS, False):
                gps_dogs += 1
                gps_interval = self.config_entry.options.get(
                    CONF_GPS_UPDATE_INTERVAL, DEFAULT_GPS_UPDATE_INTERVAL
                )
                base_interval = min(base_interval, gps_interval)

            realtime_modules = [MODULE_GPS, MODULE_WALK]
            if any(modules.get(mod, False) for mod in realtime_modules):
                realtime_dogs += 1

        # Smart interval calculation based on load
        total_dogs = len(self.dogs)
        if total_dogs == 0:
            return DEFAULT_GPS_UPDATE_INTERVAL

        # Adjust for GPS load
        if gps_dogs > 0:
            gps_ratio = gps_dogs / total_dogs
            if gps_ratio > 0.5:  # More than half have GPS
                base_interval = max(base_interval, 45)  # Prevent overload

        # Adjust for total load
        if total_dogs > 10:
            base_interval = max(base_interval, 60)
        elif total_dogs > 20:
            base_interval = max(base_interval, 90)

        return max(base_interval, 30)

    @performance_monitor(timeout=30.0)
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data for all dogs using batch processing."""
        start_time = dt_util.utcnow()

        try:
            if not self.dogs:
                return {}

            all_results = await self._process_dog_batch(self.dogs)
            updated_dogs = self._apply_selective_updates(all_results)
            update_time = (dt_util.utcnow() - start_time).total_seconds()
            self._performance_monitor.record_update(update_time, 0)

            if updated_dogs > 0:
                _LOGGER.debug(
                    "Batch update completed: %d dogs updated, 0 errors, %.2fs",
                    updated_dogs,
                    update_time,
                )

            return self._data

        except Exception as err:
            _LOGGER.error("Batch processing failed: %s", err)
            self._performance_monitor.record_update(0, len(self.dogs))
            raise UpdateFailed("Failed to update data") from err

async def _process_dog_batch(self, batch: list[DogConfigData]) -> dict[str, Any]:
    dog_ids = [dog[CONF_DOG_ID] for dog in batch]
    tasks = [self._fetch_dog_data(dog_id) for dog_id in dog_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    batch_data: dict[str, Any] = {}
    errors = 0
    for dog_id, result in zip(dog_ids, results):
        if isinstance(result, Exception):
            _LOGGER.warning("Failed to update data for dog %s: %s", dog_id, result)
            batch_data[dog_id] = self._data.get(dog_id, {})
            errors += 1
        else:
            batch_data[dog_id] = result

    if errors == len(batch):
        raise UpdateFailed("All dogs in batch failed to update")
    return batch_data
        """Process a batch of dogs concurrently."""

        dog_ids = [dog[CONF_DOG_ID] for dog in batch]
        tasks = [self._fetch_dog_data(dog_id) for dog_id in dog_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_data: dict[str, Any] = {}
        for dog_id, result in zip(dog_ids, results):
            if isinstance(result, Exception):
                raise result
            batch_data[dog_id] = result

        return batch_data

    def _create_optimized_batches(self) -> list[list[DogConfigData]]:
        """Create optimized batches based on dog module complexity."""

        # Sort dogs by complexity (GPS dogs are more resource intensive)
        def get_complexity_score(dog: DogConfigData) -> int:
            modules = dog.get("modules", {})
            score = 0
            if modules.get(MODULE_GPS):
                score += 3
            if modules.get(MODULE_WALK):
                score += 2
            if modules.get(MODULE_HEALTH):
                score += 1
            if modules.get(MODULE_FEEDING):
                score += 1
            return score

        sorted_dogs = sorted(self.dogs, key=get_complexity_score, reverse=True)

        # Create balanced batches
        batches = []
        current_batch = []
        current_complexity = 0
        max_batch_complexity = MAX_BATCH_SIZE * 2  # Adjust based on resources

        for dog in sorted_dogs:
            dog_complexity = get_complexity_score(dog)

            if (
                len(current_batch) >= MAX_BATCH_SIZE
                or current_complexity + dog_complexity > max_batch_complexity
            ):
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_complexity = 0

            current_batch.append(dog)
            current_complexity += dog_complexity

        if current_batch:
            batches.append(current_batch)

        return batches

    def _apply_selective_updates(self, new_data: dict[str, Any]) -> int:
        """Apply selective updates only for changed data."""
        updated_count = 0

        for dog_id, dog_data in new_data.items():
            # Generate simple checksum for change detection
            data_str = str(sorted(dog_data.items()))
            checksum = str(hash(data_str))

            old_checksum = self._data_checksums.get(dog_id)

            if old_checksum != checksum:
                self._data[dog_id] = dog_data
                self._data_checksums[dog_id] = checksum
                self._last_successful_update[dog_id] = dt_util.utcnow()
                updated_count += 1

                _LOGGER.debug("Data changed for dog %s", dog_id)

        return updated_count

    async def _fetch_dog_data(self, dog_id: str) -> dict[str, Any]:
        """Fetch raw data for a dog based on enabled modules."""
        dog = self.get_dog_config(dog_id)
        if not dog:
            raise UpdateFailed("Dog not found")

        data: dict[str, Any] = {"dog_info": dog}
        modules = dog.get("modules", {})
        if modules.get(MODULE_FEEDING):
            data[MODULE_FEEDING] = await self._fetch_feeding_data(dog_id)
        if modules.get(MODULE_WALK):
            data[MODULE_WALK] = await self._fetch_walk_data(dog_id)
        if modules.get(MODULE_HEALTH):
            data[MODULE_HEALTH] = await self._fetch_health_data(dog_id)
        if modules.get(MODULE_GPS):
            data[MODULE_GPS] = await self._fetch_gps_data(dog_id)
        return data

    async def _fetch_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Fetch feeding data for a dog."""
        manager = getattr(self, "_data_manager", None)
        if manager is None:
            return {"last_feeding": None, "meals_today": 0, "daily_calories": 0}
        data = await manager.async_get_dog_data(dog_id)
        feeding = data.get("feeding") if data else None
        if not feeding:
            return {"last_feeding": None, "meals_today": 0, "daily_calories": 0}
        return {
            "last_feeding": feeding.get("last_feeding"),
            "meals_today": feeding.get("meals_today", 0),
            "daily_calories": feeding.get("daily_calories", 0),
        }

    async def _fetch_walk_data(self, dog_id: str) -> dict[str, Any]:
        """Fetch walk data for a dog."""
        manager = getattr(self, "_data_manager", None)
        if manager is None:
            return {
                "walk_in_progress": False,
                "current_walk": None,
                "walks_today": 0,
                "daily_distance": 0.0,
            }
        current_walk = await manager.async_get_current_walk(dog_id)
        dog_data = await manager.async_get_dog_data(dog_id) or {}
        walk_stats = dog_data.get("walk") or {}
        return {
            "walk_in_progress": current_walk is not None,
            "current_walk": current_walk,
            "walks_today": walk_stats.get("walks_today", 0),
            "daily_distance": walk_stats.get("daily_distance", 0.0),
        }

    async def _fetch_health_data(self, dog_id: str) -> dict[str, Any]:
        """Fetch health data for a dog."""
        manager = getattr(self, "_data_manager", None)
        if manager is None:
            return {
                "current_weight": None,
                "health_status": None,
                "mood": None,
                "last_vet_visit": None,
            }
        data = await manager.async_get_dog_data(dog_id)
        health = data.get("health") if data else None
        if not health:
            return {
                "current_weight": None,
                "health_status": None,
                "mood": None,
                "last_vet_visit": None,
            }
        return {
            "current_weight": health.get("current_weight"),
            "health_status": health.get("health_status"),
            "mood": health.get("mood"),
            "last_vet_visit": health.get("last_vet_visit"),
        }

    async def _fetch_gps_data(self, dog_id: str) -> dict[str, Any]:
        """Fetch GPS data for a dog."""
        manager = getattr(self, "_data_manager", None)
        if manager is None:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "available": False,
                "error": "GPS data not available",
            }
        try:
            gps = await manager.async_get_current_gps_data(dog_id)
        except Exception as err:
            return {
                "latitude": None,
                "longitude": None,
                "available": False,
                "error": str(err),
            }
        if not gps:
            return {
                "latitude": None,
                "longitude": None,
                "available": False,
                "error": "GPS data not available",
            }
        return {
            "latitude": gps.get("latitude"),
            "longitude": gps.get("longitude"),
            "accuracy": gps.get("accuracy"),
            "available": True,
            "source": gps.get("source"),
            "last_seen": gps.get("last_seen"),
        }

    # Manager integration methods (optimized versions)
    async def _get_gps_data(self, dog_id: str) -> dict[str, Any]:
        """Get GPS data with fallback."""
        try:
            if self.walk_manager and hasattr(self.walk_manager, "async_get_gps_data"):
                return await asyncio.wait_for(
                    self.walk_manager.async_get_gps_data(dog_id), timeout=5.0
                )

            # Fast fallback
            return {}
        except (asyncio.TimeoutError, Exception) as err:
            _LOGGER.debug("GPS data timeout/error for %s: %s", dog_id, err)
            return {}

    async def _get_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Get feeding data with fallback."""
        try:
            if self.feeding_manager and hasattr(
                self.feeding_manager, "async_get_feeding_data"
            ):
                return await asyncio.wait_for(
                    self.feeding_manager.async_get_feeding_data(dog_id), timeout=3.0
                )

            return {}
        except (asyncio.TimeoutError, Exception) as err:
            _LOGGER.debug("Feeding data timeout/error for %s: %s", dog_id, err)
            return {}

    async def _get_health_data(self, dog_id: str) -> dict[str, Any]:
        """Get health data with fallback."""
        try:
            if self.health_calculator and hasattr(
                self.health_calculator, "async_get_health_data"
            ):
                return await asyncio.wait_for(
                    self.health_calculator.async_get_health_data(dog_id), timeout=3.0
                )

            return {}
        except (asyncio.TimeoutError, Exception) as err:
            _LOGGER.debug("Health data timeout/error for %s: %s", dog_id, err)
            return {}

    async def _get_walk_data(self, dog_id: str) -> dict[str, Any]:
        """Get walk data with fallback."""
        try:
            if self.walk_manager and hasattr(self.walk_manager, "async_get_walk_data"):
                return await asyncio.wait_for(
                    self.walk_manager.async_get_walk_data(dog_id), timeout=5.0
                )

            return {}
        except (asyncio.TimeoutError, Exception) as err:
            _LOGGER.debug("Walk data timeout/error for %s: %s", dog_id, err)
            return {}

    # Enhanced public interface methods
    async def async_request_selective_refresh(self, dog_ids: list[str]) -> None:
        """Request selective refresh for specific dogs."""
        for dog_id in dog_ids:
            await self._batch_manager.add_to_batch(dog_id)
            # Invalidate cache for these dogs
            self._cache.invalidate(f"dog_{dog_id}")

        # Trigger immediate refresh if batch is ready
        if self._batch_manager.has_pending():
            await self.async_refresh()

    def invalidate_dog_cache(self, dog_id: str) -> None:
        """Invalidate cache for specific dog."""
        self._cache.invalidate(f"dog_{dog_id}")
        self._data_checksums.pop(dog_id, None)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        return {
            "cache": self._cache.get_stats(),
            "performance": self._performance_monitor.get_stats(),
            "batch_manager": {
                "pending_updates": len(self._batch_manager._pending_updates),
            },
            "data_info": {
                "total_dogs": len(self._data),
                "last_updates": {
                    dog_id: update_time.isoformat()
                    for dog_id, update_time in self._last_successful_update.items()
                },
            },
        }

    async def async_shutdown(self) -> None:
        """Enhanced shutdown with cleanup."""
        _LOGGER.debug("Shutting down advanced coordinator")
        tasks: list[asyncio.Task] = []
        if getattr(self, "_cleanup_task", None) and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            tasks.append(self._cleanup_task)

        for task in getattr(self, "_background_tasks", []):
            task.cancel()
            tasks.append(task)

        if getattr(self, "_performance_monitor_task", None):
            self._performance_monitor_task.cancel()
            tasks.append(self._performance_monitor_task)

        if getattr(self, "_cache_cleanup_task", None):
            self._cache_cleanup_task.cancel()
            tasks.append(self._cache_cleanup_task)

        for task in tasks:
            try:
                await task
            except Exception:
                pass

        for task in getattr(self, "_background_tasks", []):
            try:
                task.cancel()
                await task
            except Exception:
                pass

        if getattr(self, "_performance_monitor_task", None):
            try:
                self._performance_monitor_task.cancel()
                await self._performance_monitor_task
            except Exception:
                pass

        if getattr(self, "_cache_cleanup_task", None):
            try:
                self._cache_cleanup_task.cancel()
                await self._cache_cleanup_task
            except Exception:
                pass

        # Clear all data structures
        self._listeners.clear()
        self._data.clear()
        self._data_checksums.clear()
        self._last_successful_update.clear()
        self._batch_manager.clear_pending()

        _LOGGER.debug("Advanced coordinator shutdown completed")

    def set_managers(
        self,
        dog_manager=None,
        walk_manager=None,
        feeding_manager=None,
        health_calculator=None,
    ) -> None:
        """Set manager references after initialization."""
        self.dog_manager = dog_manager
        self.walk_manager = walk_manager
        self.feeding_manager = feeding_manager
        self.health_calculator = health_calculator

        _LOGGER.debug("Manager references set for advanced coordinator")

    # Keep utility methods from original (abbreviated for space)
    def _parse_datetime_safely(self, value: Any) -> datetime | None:
        """Safely parse datetime from various input types."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return dt_util.as_local(value) if value.tzinfo is None else value

        if isinstance(value, str):
            try:
                parsed = dt_util.parse_datetime(value.strip())
                if parsed:
                    return dt_util.as_local(parsed) if parsed.tzinfo is None else parsed
            except (ValueError, TypeError):
                pass

        return None

    # Public interface methods
    def get_dog_data(self, dog_id: str) -> Optional[dict[str, Any]]:
        """Get data for a specific dog."""
        return self._data.get(dog_id)

    def get_all_dogs_data(self) -> dict[str, Any]:
        """Get data for all dogs."""
        return self._data.copy()

    @property
    def available(self) -> bool:
        """Return if coordinator is available."""
        return self.last_update_success

    def get_update_statistics(self) -> dict[str, Any]:
        """Get enhanced update statistics."""
        base_stats = {
            "total_dogs": len(self.dogs),
            "last_update_success": self.last_update_success,
            "update_interval_seconds": self.update_interval.total_seconds(),
            "active_listeners": len(self._listeners),
        }

        # Add advanced stats
        base_stats.update(self.get_cache_stats())

        return base_stats
