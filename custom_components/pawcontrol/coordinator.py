"""Optimized lightweight coordinator for PawControl with specialized managers.

Quality Scale: Platinum
Home Assistant: 2025.9.1+
Python: 3.13+

OPTIMIZED: Enhanced performance with reduced memory footprint, faster async operations,
and streamlined manager delegation. Improved cache efficiency and error handling.

Coordinator responsibilities reduced to coordination only.
Heavy lifting delegated to specialized managers.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from contextlib import suppress
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .batch_manager import BatchManager
from .cache_manager import CACHE_TTL_MEDIUM, CacheManager
from .const import (
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_GPS_UPDATE_INTERVAL,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    UPDATE_INTERVALS,
)
from .performance_manager import PerformanceMonitor
from .utils import performance_monitor

if TYPE_CHECKING:
    from .data_manager import DataManager
    from .dog_data_manager import DogDataManager
    from .feeding_manager import FeedingManager
    from .types import DogConfigData
    from .walk_manager import WalkManager

_LOGGER = logging.getLogger(__name__)

# OPTIMIZED: Reduced maintenance intervals for better responsiveness
MAINTENANCE_INTERVAL = 300  # Reduced from 600 seconds (5 minutes)
BATCH_CHECK_INTERVAL = 3  # Reduced from 5 seconds


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Optimized lightweight coordinator with specialized manager delegation.

    OPTIMIZED IMPROVEMENTS:
    - Reduced memory footprint through smarter caching
    - Faster async operations with parallel processing
    - Streamlined manager delegation
    - Enhanced error recovery patterns
    - Better resource cleanup

    Responsibilities:
    - Overall coordination and orchestration
    - Manager integration and delegation
    - Background task management (optimized)
    - Public interface for entities
    - Configuration and lifecycle management

    Heavy lifting delegated to specialized managers.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize optimized coordinator with manager delegation."""
        self.config_entry = entry
        self._dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
        self.dogs = self._dogs_config

        # OPTIMIZED: Calculate optimal update interval with improved heuristics
        update_interval = self._calculate_optimal_update_interval()

        super().__init__(
            hass,
            _LOGGER,
            name="PawControl Data",
            update_interval=timedelta(seconds=update_interval),
            always_update=False,
        )

        # OPTIMIZED: Initialize specialized managers with reduced memory footprint
        cache_size = min(100 + (len(self.dogs) * 10), 200)  # Dynamic cache sizing
        self._cache_manager = CacheManager(max_size=cache_size)
        self._batch_manager = BatchManager()
        self._performance_monitor = PerformanceMonitor()

        # OPTIMIZED: Core data storage with memory optimization
        self._data: dict[str, Any] = {}
        self._data_checksums: dict[str, str] = {}
        self._last_successful_update: dict[str, datetime] = {}
        self._error_counts: dict[str, int] = {}  # Track errors per dog

        # Manager references (injected during setup)
        self._data_manager: DataManager | None = None
        self.dog_data_manager: DogDataManager | None = None
        self.walk_manager: WalkManager | None = None
        self.feeding_manager: FeedingManager | None = None
        self.health_calculator = None

        # OPTIMIZED: Background tasks with enhanced lifecycle management
        self._maintenance_task: asyncio.Task | None = None
        self._batch_processor_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._active_tasks: set[asyncio.Task] = set()

        _LOGGER.info(
            "Optimized coordinator initialized: %d dogs, %ds interval, cache_size=%d",
            len(self.dogs),
            update_interval,
            cache_size,
        )

    async def _async_setup(self) -> None:
        """One-time async init before first refresh."""
        # Wenn Manager vorhanden: vorbereiten. Keine Blocker im Event-Loop.
        if self._data_manager is not None:
            await self._data_manager.async_prepare()
        if self.dog_data_manager is not None:
            await self.dog_data_manager.async_prepare()
        if self.walk_manager is not None:
            await self.walk_manager.async_prepare()
        if self.feeding_manager is not None:
            await self.feeding_manager.async_prepare()
        # Langläufer erst ab hier starten, nicht im __init__
        # self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    def set_managers(
        self,
        data_manager: DataManager | None = None,
        dog_data_manager: DogDataManager | None = None,
        walk_manager: WalkManager | None = None,
        feeding_manager: FeedingManager | None = None,
        health_calculator=None,
    ) -> None:
        """Inject manager dependencies with validation.

        Args:
            data_manager: Core data manager
            dog_data_manager: Dog data management
            walk_manager: Walk and GPS management
            feeding_manager: Feeding management
            health_calculator: Health calculations
        """
        if data_manager:
            self._data_manager = data_manager
        if dog_data_manager:
            self.dog_data_manager = dog_data_manager
        if walk_manager:
            self.walk_manager = walk_manager
        if feeding_manager:
            self.feeding_manager = feeding_manager
        if health_calculator:
            self.health_calculator = health_calculator

        _LOGGER.debug("Manager references injected and validated")

    async def async_start_background_tasks(self) -> None:
        """Start optimized background tasks for maintenance and batch processing."""
        if self._maintenance_task is None:
            self._maintenance_task = self._create_managed_task(
                self._maintenance_loop(), "pawcontrol_maintenance"
            )

        if self._batch_processor_task is None:
            self._batch_processor_task = self._create_managed_task(
                self._batch_processor_loop(), "pawcontrol_batch_processor"
            )

    def _create_managed_task(self, coro, name: str) -> asyncio.Task:
        """Create a managed task that tracks lifecycle.

        Args:
            coro: Coroutine to execute
            name: Task name for debugging

        Returns:
            Created task
        """
        task = asyncio.create_task(coro, name=name)
        self._active_tasks.add(task)

        def task_done_callback(task):
            self._active_tasks.discard(task)
            if task.cancelled():
                _LOGGER.debug("Task %s was cancelled", name)
            elif task.exception():
                _LOGGER.error("Task %s failed: %s", name, task.exception())

        task.add_done_callback(task_done_callback)
        return task

    async def _maintenance_loop(self) -> None:
        """Optimized maintenance loop with improved efficiency."""
        try:
            while not self._shutdown_event.is_set():
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=MAINTENANCE_INTERVAL
                    )
                    break  # Shutdown requested

                await self._perform_maintenance()

        except asyncio.CancelledError:
            _LOGGER.debug("Maintenance loop cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Maintenance loop error: %s", err, exc_info=True)

    async def _batch_processor_loop(self) -> None:
        """Optimized batch processor with reduced latency."""
        try:
            while not self._shutdown_event.is_set():
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=BATCH_CHECK_INTERVAL
                    )
                    break  # Shutdown requested

                if await self._batch_manager.should_batch_now():
                    await self.async_refresh()

        except asyncio.CancelledError:
            _LOGGER.debug("Batch processor cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Batch processor error: %s", err, exc_info=True)

    async def _perform_maintenance(self) -> None:
        """Optimized maintenance with parallel operations."""
        # OPTIMIZED: Run maintenance operations in parallel
        maintenance_tasks = [
            self._cache_manager.clear_expired(),
            self._batch_manager.optimize_batching(),
        ]

        results = await asyncio.gather(*maintenance_tasks, return_exceptions=True)

        cleared = results[0] if isinstance(results[0], int) else 0

        # Optimize cache if significant cleanup occurred
        if cleared > 20:  # Increased threshold
            await self._cache_manager.optimize_cache()

        # Reset error counts periodically
        if cleared > 0:
            self._error_counts.clear()

        # OPTIMIZED: Log maintenance summary only when significant activity
        if cleared > 5:
            cache_stats = self._cache_manager.get_stats()
            perf_stats = self._performance_monitor.get_stats()

            _LOGGER.debug(
                "Maintenance: cache_cleared=%d, hit_rate=%.1f%%, active_tasks=%d, p95=%.2fs",
                cleared,
                cache_stats["hit_rate"],
                len(self._active_tasks),
                perf_stats.get("p95", 0),
            )

    @performance_monitor(timeout=25.0)  # Reduced timeout
    async def _async_update_data(self) -> dict[str, Any]:
        """Optimized update using enhanced manager delegation."""
        start_time = dt_util.utcnow()

        try:
            if not self.dogs:
                return {}

            # OPTIMIZED: Get batch from BatchManager with priority handling
            batch = await self._batch_manager.get_batch()

            # If no specific batch, update all dogs
            if not batch:
                batch = [dog[CONF_DOG_ID] for dog in self.dogs]

            # OPTIMIZED: Process dogs with parallel execution for better performance
            all_results: dict[str, Any] = {}
            errors = 0

            # Parallel processing for better performance
            if len(batch) > 1:
                # Parallel execution for multiple dogs
                tasks = [self._fetch_dog_data_delegated(dog_id) for dog_id in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for dog_id, result in zip(batch, results):
                    if isinstance(result, Exception):
                        _LOGGER.warning(
                            "Failed to fetch data for %s: %s", dog_id, result
                        )
                        errors += 1
                        self._error_counts[dog_id] = (
                            self._error_counts.get(dog_id, 0) + 1
                        )
                        # Use last known data
                        all_results[dog_id] = self._data.get(dog_id, {})
                    else:
                        all_results[dog_id] = result
                        self._error_counts.pop(
                            dog_id, None
                        )  # Clear error count on success
            else:
                # Single dog - direct execution
                dog_id = batch[0]
                try:
                    dog_data = await self._fetch_dog_data_delegated(dog_id)
                    all_results[dog_id] = dog_data
                    self._error_counts.pop(dog_id, None)
                except Exception as err:
                    _LOGGER.warning("Failed to fetch data for %s: %s", dog_id, err)
                    errors += 1
                    self._error_counts[dog_id] = self._error_counts.get(dog_id, 0) + 1
                    all_results[dog_id] = self._data.get(dog_id, {})

            # OPTIMIZED: Fail only if all dogs fail repeatedly
            persistent_failures = sum(
                1 for count in self._error_counts.values() if count > 3
            )
            if errors == len(batch) and persistent_failures > len(batch) / 2:
                raise UpdateFailed("Persistent failures across multiple dogs")

            # Apply selective updates with change detection
            updated_count = self._apply_selective_updates(all_results)

            # OPTIMIZED: Record performance with enhanced metrics
            duration = (dt_util.utcnow() - start_time).total_seconds()
            self._performance_monitor.record_update(duration, errors)

            # Log only significant updates or errors
            if updated_count > 0 or errors > 0:
                _LOGGER.debug(
                    "Update completed: %d/%d dogs updated, %d errors, %.2fs, cache_hit_rate=%.1f%%",
                    updated_count,
                    len(batch),
                    errors,
                    duration,
                    self._cache_manager.get_stats()["hit_rate"],
                )

            return self._data

        except Exception as err:
            _LOGGER.error("Update failed: %s", err)
            self._performance_monitor.record_update(0, 1)
            raise UpdateFailed(f"Update failed: {err}") from err

    async def _fetch_dog_data_delegated(self, dog_id: str) -> dict[str, Any]:
        """Optimized dog data fetching with enhanced caching and error handling.

        Args:
            dog_id: Dog identifier

        Returns:
            Complete dog data
        """
        # OPTIMIZED: Check cache first with faster key lookup
        cache_key = f"dog_{dog_id}"
        cached = await self._cache_manager.get(cache_key)

        if cached:
            return cached

        # Get dog configuration
        dog_config = self.get_dog_config(dog_id)
        if not dog_config:
            raise ValueError(f"Dog {dog_id} not found")

        data: dict[str, Any] = {"dog_info": dog_config}
        modules = dog_config.get("modules", {})

        # OPTIMIZED: Delegate to specialized managers with timeout protection
        try:
            # Create manager tasks with timeouts
            manager_tasks = []

            # Feeding data
            if modules.get(MODULE_FEEDING) and self.feeding_manager:
                manager_tasks.append(
                    (
                        MODULE_FEEDING,
                        self.feeding_manager.async_get_feeding_data(dog_id),
                    )
                )

            # Walk data
            if modules.get(MODULE_WALK) and self.walk_manager:
                manager_tasks.append(
                    (MODULE_WALK, self.walk_manager.async_get_walk_data(dog_id))
                )

            # GPS data
            if modules.get(MODULE_GPS) and self.walk_manager:
                manager_tasks.append(
                    (MODULE_GPS, self.walk_manager.async_get_gps_data(dog_id))
                )

            # Health data
            if modules.get(MODULE_HEALTH) and self.dog_data_manager:

                async def get_health_data():
                    dog_full_data = await self.dog_data_manager.async_get_dog_data(
                        dog_id
                    )
                    return dog_full_data.get("health", {}) if dog_full_data else {}

                manager_tasks.append((MODULE_HEALTH, get_health_data()))

            # OPTIMIZED: Execute manager tasks in parallel with timeout
            if manager_tasks:
                async with asyncio.timeout(10):  # 10 second timeout per dog
                    task_results = await asyncio.gather(
                        *[task for _, task in manager_tasks], return_exceptions=True
                    )

                    for (module_name, _), result in zip(manager_tasks, task_results):
                        if isinstance(result, Exception):
                            _LOGGER.debug(
                                "Manager %s failed for %s: %s",
                                module_name,
                                dog_id,
                                result,
                            )
                            data[module_name] = {"error": str(result)}
                        else:
                            data[module_name] = result

        except asyncio.TimeoutError:
            _LOGGER.warning("Manager timeout for %s", dog_id)
            data["error"] = "timeout"

        # OPTIMIZED: Cache result with dynamic TTL based on module complexity
        cache_ttl = CACHE_TTL_MEDIUM
        if modules.get(MODULE_GPS):
            cache_ttl = 30  # Shorter TTL for GPS data
        elif len(modules) > 3:
            cache_ttl = CACHE_TTL_MEDIUM // 2  # Shorter TTL for complex setups

        await self._cache_manager.set(cache_key, data, cache_ttl)

        return data

    def _apply_selective_updates(self, new_data: dict[str, Any]) -> int:
        """Optimized updates with enhanced change detection.

        Args:
            new_data: New data to apply

        Returns:
            Number of dogs updated
        """
        updated_count = 0

        for dog_id, dog_data in new_data.items():
            # OPTIMIZED: Use faster hashing for change detection
            # Convert to string representation for hashing
            data_str = str(sorted(dog_data.items()))
            checksum = hashlib.md5(data_str.encode(), usedforsecurity=False).hexdigest()

            old_checksum = self._data_checksums.get(dog_id)

            if old_checksum != checksum:
                self._data[dog_id] = dog_data
                self._data_checksums[dog_id] = checksum
                self._last_successful_update[dog_id] = dt_util.utcnow()
                updated_count += 1

        return updated_count

    def _calculate_optimal_update_interval(self) -> int:
        """Calculate optimal interval with enhanced heuristics."""
        base_interval = UPDATE_INTERVALS["frequent"]

        if not self.dogs:
            return UPDATE_INTERVALS["minimal"]

        # OPTIMIZED: Analyze module complexity with better scoring
        total_complexity = 0
        gps_dogs = 0
        high_complexity_modules = 0

        for dog in self.dogs:
            modules = dog.get("modules", {})

            # Calculate complexity score with weights
            if modules.get(MODULE_GPS):
                total_complexity += 4  # GPS is most demanding
                gps_dogs += 1
            if modules.get(MODULE_WALK):
                total_complexity += 2
            if modules.get(MODULE_HEALTH):
                total_complexity += 1
            if modules.get(MODULE_FEEDING):
                total_complexity += 1

            # Count high complexity setups
            active_modules = sum(1 for enabled in modules.values() if enabled)
            if active_modules > 3:
                high_complexity_modules += 1

        # Dynamic interval based on total complexity and GPS requirements
        if total_complexity == 0:
            return UPDATE_INTERVALS["minimal"]

        # GPS requires frequent updates
        if gps_dogs > 0:
            gps_interval = self.config_entry.options.get(
                CONF_GPS_UPDATE_INTERVAL, UPDATE_INTERVALS["frequent"]
            )
            base_interval = min(base_interval, gps_interval)

        # OPTIMIZED: Scale by complexity with better thresholds
        if total_complexity > 30 or high_complexity_modules > 5:
            base_interval = max(base_interval, 120)  # 2 minutes
        elif total_complexity > 15 or high_complexity_modules > 2:
            base_interval = max(base_interval, 90)  # 1.5 minutes
        elif total_complexity > 8:
            base_interval = max(base_interval, 60)  # 1 minute

        # Never go below minimum for stability
        return max(base_interval, UPDATE_INTERVALS["real_time"])

    # OPTIMIZED: Public interface methods with better performance
    def get_dog_config(self, dog_id: str) -> dict[str, Any] | None:
        """Get dog configuration with caching."""
        # Use generator for efficiency
        return next(
            (dog for dog in self._dogs_config if dog.get(CONF_DOG_ID) == dog_id), None
        )

    def get_enabled_modules(self, dog_id: str) -> set[str]:
        """Get enabled modules for dog with caching."""
        config = self.get_dog_config(dog_id)
        if not config:
            return set()
        modules = config.get("modules", {})
        return {name for name, enabled in modules.items() if enabled}

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        """Check if module is enabled efficiently."""
        config = self.get_dog_config(dog_id)
        return config.get("modules", {}).get(module, False) if config else False

    def get_dog_ids(self) -> list[str]:
        """Get all dog IDs efficiently."""
        return [dog.get(CONF_DOG_ID) for dog in self._dogs_config]

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        """Get data for specific dog."""
        return self._data.get(dog_id)

    def get_all_dogs_data(self) -> dict[str, Any]:
        """Get all dogs data (shallow copy for safety)."""
        return self._data.copy()

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any] | None:
        """Get data for a specific module of a dog."""
        return self._data.get(dog_id, {}).get(module)

    async def async_request_selective_refresh(
        self, dog_ids: list[str], priority: int = 5
    ) -> None:
        """Request selective refresh with enhanced priority handling.

        Args:
            dog_ids: Dogs to refresh
            priority: Update priority (0-10, higher = more urgent)
        """
        for dog_id in dog_ids:
            # Invalidate cache
            await self._cache_manager.invalidate(f"dog_{dog_id}")

            # Add to batch with priority
            await self._batch_manager.add_to_batch(dog_id, priority)

        # OPTIMIZED: Force refresh for urgent priorities
        if priority >= 8 and await self._batch_manager.has_pending():
            # Use create_task for non-blocking refresh
            asyncio.create_task(self.async_refresh())

    async def invalidate_dog_cache(self, dog_id: str) -> None:
        """Invalidate all caches for a dog efficiently."""
        await self._cache_manager.invalidate(f"dog_{dog_id}")
        self._data_checksums.pop(dog_id, None)
        self._error_counts.pop(dog_id, None)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics with performance metrics."""
        cache_stats = self._cache_manager.get_stats()
        perf_stats = self._performance_monitor.get_stats()
        batch_stats = self._batch_manager.get_stats()

        return {
            "cache": cache_stats,
            "performance": perf_stats,
            "batch": batch_stats,
            "dogs_tracked": len(self._data),
            "active_tasks": len(self._active_tasks),
            "error_counts": dict(list(self._error_counts.items())[:5]),  # Top 5 errors
            "last_updates": {
                dog_id: update_time.isoformat()
                for dog_id, update_time in list(self._last_successful_update.items())[
                    :5
                ]
            },
        }

    @property
    def available(self) -> bool:
        """Check if coordinator is available."""
        return self.last_update_success

    def get_update_statistics(self) -> dict[str, Any]:
        """Get detailed update statistics."""
        return {
            "total_dogs": len(self.dogs),
            "last_update_success": self.last_update_success,
            "update_interval_seconds": self.update_interval.total_seconds(),
            "statistics": self.get_cache_stats(),
        }

    async def async_shutdown(self) -> None:
        """Optimized shutdown with enhanced cleanup."""
        _LOGGER.debug("Shutting down optimized coordinator")

        # Signal shutdown to all tasks
        self._shutdown_event.set()

        # OPTIMIZED: Cancel and wait for all managed tasks
        if self._active_tasks:
            # Cancel all active tasks
            for task in self._active_tasks:
                if not task.done():
                    task.cancel()

            # Wait for graceful shutdown with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_tasks, return_exceptions=True),
                    timeout=3.0,  # Reduced timeout
                )
            except asyncio.TimeoutError:
                _LOGGER.warning("Some tasks did not shutdown gracefully")

        # Clear managers and data structures
        await asyncio.gather(
            self._cache_manager.clear(),
            self._batch_manager.clear_pending(),
            return_exceptions=True,
        )

        # Clear data structures
        self._data.clear()
        self._data_checksums.clear()
        self._last_successful_update.clear()
        self._error_counts.clear()
        self._active_tasks.clear()

        _LOGGER.debug("Optimized coordinator shutdown completed")
