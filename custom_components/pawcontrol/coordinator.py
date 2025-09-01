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
from collections import defaultdict, deque
from datetime import datetime, timedelta, date
from typing import Any, Callable, Optional, TYPE_CHECKING
import weakref

from homeassistant.const import STATE_UNKNOWN, STATE_ONLINE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util
from homeassistant.helpers.storage import Store

from .const import (
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_GPS_UPDATE_INTERVAL,
    DEFAULT_GPS_UPDATE_INTERVAL,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    UPDATE_INTERVALS,
    MEAL_TYPES,
)
from .utils import performance_monitor

if TYPE_CHECKING:
    from .types import DogConfigData, PawControlRuntimeData

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
        
    def set(self, key: str, data: dict[str, Any], ttl_seconds: int = CACHE_TTL_MEDIUM) -> None:
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
        expired_keys = [
            key for key, expiry in self._expiry.items() 
            if now > expiry
        ]
        
        for key in expired_keys:
            self.invalidate(key)
            
        return len(expired_keys)
        
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "total_entries": len(self._cache),
            "total_accesses": sum(self._access_count.values()),
            "most_accessed": max(self._access_count.items(), key=lambda x: x[1])
            if self._access_count else None,
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
        batch = list(self._pending_updates)[:self._max_batch_size]
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
        self.entry = entry
        self.dogs: list[DogConfigData] = entry.data.get(CONF_DOGS, [])

        # Calculate optimal update interval
        update_interval = self._calculate_optimal_update_interval()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=update_interval),
            always_update=False,
        )

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
        
        # Background tasks
        self._cleanup_task: asyncio.Task | None = None
        self._start_background_tasks()
        
        _LOGGER.info(
            "Advanced coordinator initialized: %d dogs, %ds interval, batch_size=%d",
            len(self.dogs),
            update_interval,
            MAX_BATCH_SIZE,
        )

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
                _LOGGER.info("Performance stats: avg=%.2fs, errors=%d", 
                           avg_time, perf_stats.get("error_count", 0))

    def _calculate_optimal_update_interval(self) -> int:
        """Calculate optimal update interval with advanced logic."""
        base_interval = UPDATE_INTERVALS["balanced"]
        
        # Analyze module requirements
        gps_dogs = 0
        realtime_dogs = 0
        
        for dog in self.dogs:
            modules = dog.get("modules", {})
            if modules.get(MODULE_GPS, False):
                gps_dogs += 1
                gps_interval = self.entry.options.get(
                    CONF_GPS_UPDATE_INTERVAL, DEFAULT_GPS_UPDATE_INTERVAL
                )
                base_interval = min(base_interval, gps_interval)
                
            realtime_modules = [MODULE_GPS, MODULE_WALK]
            if any(modules.get(mod, False) for mod in realtime_modules):
                realtime_dogs += 1
                
        # Smart interval calculation based on load
        total_dogs = len(self.dogs)
        if total_dogs == 0:
            return 120
            
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
        """Advanced batch processing data update."""
        start_time = dt_util.utcnow()
        
        try:
            if not self.dogs:
                return {}
                
            # Process dogs in optimized batches
            all_results = {}
            error_count = 0
            
            # Split dogs into batches
            dog_batches = self._create_optimized_batches()
            
            for batch in dog_batches:
                try:
                    batch_results = await self._process_dog_batch(batch)
                    all_results.update(batch_results)
                except Exception as err:
                    _LOGGER.error("Batch processing failed: %s", err)
                    error_count += len(batch)
                    
                    # Add fallback data for failed dogs
                    for dog in batch:
                        dog_id = dog[CONF_DOG_ID]
                        all_results[dog_id] = self._data.get(dog_id, {})
                        
            # Update internal data with change detection
            updated_dogs = self._apply_selective_updates(all_results)
            
            # Record performance metrics
            update_time = (dt_util.utcnow() - start_time).total_seconds()
            self._performance_monitor.record_update(update_time, error_count)
            
            # Log batch processing results
            if updated_dogs > 0:
                _LOGGER.debug(
                    "Batch update completed: %d dogs updated, %d errors, %.2fs",
                    updated_dogs,
                    error_count,
                    update_time,
                )
                
            # Fail only if ALL dogs failed
            if error_count == len(self.dogs) and len(self.dogs) > 0:
                raise UpdateFailed("All batch updates failed")
                
            return self._data

        except Exception as err:
            _LOGGER.error("Critical batch update error: %s", err)
            self._performance_monitor.record_update(0, len(self.dogs))
            raise UpdateFailed(f"Batch update failed: {err}") from err

    def _create_optimized_batches(self) -> list[list[DogConfigData]]:
        """Create optimized batches based on dog module complexity."""
        # Sort dogs by complexity (GPS dogs are more resource intensive)
        def get_complexity_score(dog: DogConfigData) -> int:
            modules = dog.get("modules", {})
            score = 0
            if modules.get(MODULE_GPS): score += 3
            if modules.get(MODULE_WALK): score += 2  
            if modules.get(MODULE_HEALTH): score += 1
            if modules.get(MODULE_FEEDING): score += 1
            return score
            
        sorted_dogs = sorted(self.dogs, key=get_complexity_score, reverse=True)
        
        # Create balanced batches
        batches = []
        current_batch = []
        current_complexity = 0
        max_batch_complexity = MAX_BATCH_SIZE * 2  # Adjust based on resources
        
        for dog in sorted_dogs:
            dog_complexity = get_complexity_score(dog)
            
            if (len(current_batch) >= MAX_BATCH_SIZE or 
                current_complexity + dog_complexity > max_batch_complexity):
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_complexity = 0
                    
            current_batch.append(dog)
            current_complexity += dog_complexity
            
        if current_batch:
            batches.append(current_batch)
            
        return batches

    async def _process_dog_batch(self, batch: list[DogConfigData]) -> dict[str, Any]:
        """Process a batch of dogs concurrently."""
        # Create concurrent tasks for the batch
        tasks = []
        for dog in batch:
            dog_id = dog[CONF_DOG_ID]
            
            # Check cache first for non-realtime data
            cached_data = self._try_get_cached_data(dog)
            if cached_data is not None:
                continue  # Skip if cached data is fresh
                
            tasks.append(self._async_update_dog_data_cached(dog))
            
        if not tasks:
            # All data was cached
            return {dog[CONF_DOG_ID]: self._data.get(dog[CONF_DOG_ID], {}) 
                   for dog in batch}
            
        # Execute batch with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=25.0
            )
        except asyncio.TimeoutError:
            _LOGGER.warning("Batch processing timeout for %d dogs", len(batch))
            return {}
            
        # Process results
        batch_data = {}
        for dog, result in zip(batch, results):
            dog_id = dog[CONF_DOG_ID]
            
            if isinstance(result, Exception):
                _LOGGER.warning("Dog %s update failed: %s", dog_id, result)
                batch_data[dog_id] = self._data.get(dog_id, {})
            else:
                batch_data[dog_id] = result
                
        return batch_data

    def _try_get_cached_data(self, dog: DogConfigData) -> dict[str, Any] | None:
        """Try to get cached data for dog if still fresh."""
        dog_id = dog[CONF_DOG_ID]
        modules = dog.get("modules", {})
        
        # Use different cache strategies based on modules
        if modules.get(MODULE_GPS) or modules.get(MODULE_WALK):
            # Real-time modules need fresh data
            return None
            
        # For less dynamic modules, try cache
        cache_key = f"dog_{dog_id}"
        cached_data = self._cache.get(cache_key)
        
        if cached_data:
            _LOGGER.debug("Using cached data for dog %s", dog_id)
            return cached_data
            
        return None

    async def _async_update_dog_data_cached(self, dog: DogConfigData) -> dict[str, Any]:
        """Update dog data with intelligent caching."""
        dog_id = dog[CONF_DOG_ID]
        
        # Get fresh data
        dog_data = await self._async_update_dog_data(dog)
        
        # Cache with appropriate TTL based on modules
        modules = dog.get("modules", {})
        if modules.get(MODULE_GPS) or modules.get(MODULE_WALK):
            ttl = CACHE_TTL_FAST
        elif modules.get(MODULE_FEEDING):
            ttl = CACHE_TTL_MEDIUM
        else:
            ttl = CACHE_TTL_SLOW
            
        cache_key = f"dog_{dog_id}"
        self._cache.set(cache_key, dog_data, ttl)
        
        return dog_data

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

    # Keep essential methods from original implementation
    async def _async_update_dog_data(self, dog: DogConfigData) -> dict[str, Any]:
        """Update data for a specific dog (optimized version)."""
        dog_id = dog[CONF_DOG_ID]
        enabled_modules = dog.get("modules", {})

        dog_data: dict[str, Any] = {
            "dog_info": dog,
            "last_update": dt_util.utcnow().isoformat(),
            "status": STATE_ONLINE,
            "enabled_modules": [mod for mod, enabled in enabled_modules.items() if enabled],
            "update_source": "coordinator_optimized",
            "data_version": 2,  # Incremented for optimized version
        }

        try:
            # Use managers with parallel processing where possible
            module_tasks = []
            
            if enabled_modules.get(MODULE_GPS, False):
                module_tasks.append(("gps", self._get_gps_data(dog_id)))
                
            if enabled_modules.get(MODULE_FEEDING, False):
                module_tasks.append(("feeding", self._get_feeding_data(dog_id)))
                
            if enabled_modules.get(MODULE_HEALTH, False):
                module_tasks.append(("health", self._get_health_data(dog_id)))
                
            if enabled_modules.get(MODULE_WALK, False):
                module_tasks.append(("walk", self._get_walk_data(dog_id)))
                
            # Execute module data fetching in parallel
            if module_tasks:
                results = await asyncio.gather(
                    *[task for _, task in module_tasks], 
                    return_exceptions=True
                )
                
                for (module_name, _), result in zip(module_tasks, results):
                    if isinstance(result, Exception):
                        _LOGGER.debug("Module %s failed for dog %s: %s", 
                                    module_name, dog_id, result)
                        dog_data[module_name] = {}
                    else:
                        dog_data[module_name] = result

            return dog_data

        except Exception as err:
            _LOGGER.error("Error updating data for dog %s: %s", dog_id, err)
            return dog_data

    # Manager integration methods (optimized versions)
    async def _get_gps_data(self, dog_id: str) -> dict[str, Any]:
        """Get GPS data with fallback."""
        try:
            if self.walk_manager and hasattr(self.walk_manager, "async_get_gps_data"):
                return await asyncio.wait_for(
                    self.walk_manager.async_get_gps_data(dog_id),
                    timeout=5.0
                )
                
            # Fast fallback
            return {}
        except (asyncio.TimeoutError, Exception) as err:
            _LOGGER.debug("GPS data timeout/error for %s: %s", dog_id, err)
            return {}

    async def _get_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Get feeding data with fallback."""
        try:
            if self.feeding_manager and hasattr(self.feeding_manager, "async_get_feeding_data"):
                return await asyncio.wait_for(
                    self.feeding_manager.async_get_feeding_data(dog_id),
                    timeout=3.0
                )
                
            return {}
        except (asyncio.TimeoutError, Exception) as err:
            _LOGGER.debug("Feeding data timeout/error for %s: %s", dog_id, err)
            return {}

    async def _get_health_data(self, dog_id: str) -> dict[str, Any]:
        """Get health data with fallback."""
        try:
            if self.health_calculator and hasattr(self.health_calculator, "async_get_health_data"):
                return await asyncio.wait_for(
                    self.health_calculator.async_get_health_data(dog_id),
                    timeout=3.0
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
                    self.walk_manager.async_get_walk_data(dog_id),
                    timeout=5.0
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
        
        # Cancel background tasks
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
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
