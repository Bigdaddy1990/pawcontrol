"""Refactored lightweight coordinator for PawControl with specialized managers.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

Coordinator responsibilities reduced to coordination only.
Heavy lifting delegated to specialized managers.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

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

# Maintenance interval for background tasks
MAINTENANCE_INTERVAL = 600  # 10 minutes


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Lightweight coordinator with specialized manager delegation.
    
    Responsibilities:
    - Overall coordination and orchestration
    - Manager integration and delegation
    - Background task management (simplified)
    - Public interface for entities
    - Configuration and lifecycle management
    
    Heavy lifting delegated to:
    - CacheManager: All caching logic
    - BatchManager: Batch processing and queuing
    - PerformanceMonitor: Performance tracking and alerting
    - DogDataManager: Dog data structures and validation
    - WalkManager: GPS and walk functionality
    - FeedingManager: Feeding logic and scheduling
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize lightweight coordinator with manager delegation."""
        self.config_entry = entry
        self._dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
        self.dogs = self._dogs_config
        
        # Calculate optimal update interval
        update_interval = self._calculate_optimal_update_interval()
        
        super().__init__(
            hass,
            _LOGGER,
            name="PawControl Data",
            update_interval=timedelta(seconds=update_interval),
            always_update=False,
        )
        
        # Initialize specialized managers
        self._cache_manager = CacheManager(max_size=150)
        self._batch_manager = BatchManager()
        self._performance_monitor = PerformanceMonitor()
        
        # Core data storage
        self._data: dict[str, Any] = {}
        self._data_checksums: dict[str, str] = {}
        self._last_successful_update: dict[str, datetime] = {}
        
        # Manager references (injected during setup)
        self._data_manager: Optional[DataManager] = None
        self.dog_data_manager: Optional[DogDataManager] = None
        self.walk_manager: Optional[WalkManager] = None
        self.feeding_manager: Optional[FeedingManager] = None
        self.health_calculator = None
        
        # Background tasks
        self._maintenance_task: Optional[asyncio.Task] = None
        self._batch_processor_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        _LOGGER.info(
            "Lightweight coordinator initialized: %d dogs, %ds interval",
            len(self.dogs),
            update_interval,
        )

    def set_managers(
        self,
        data_manager: Optional[DataManager] = None,
        dog_data_manager: Optional[DogDataManager] = None,
        walk_manager: Optional[WalkManager] = None,
        feeding_manager: Optional[FeedingManager] = None,
        health_calculator=None,
    ) -> None:
        """Inject manager dependencies.
        
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
        
        _LOGGER.debug("Manager references injected")

    async def async_start_background_tasks(self) -> None:
        """Start background tasks for maintenance and batch processing."""
        if self._maintenance_task is None:
            self._maintenance_task = asyncio.create_task(
                self._maintenance_loop(),
                name="pawcontrol_maintenance"
            )
        
        if self._batch_processor_task is None:
            self._batch_processor_task = asyncio.create_task(
                self._batch_processor_loop(),
                name="pawcontrol_batch_processor"
            )

    async def _maintenance_loop(self) -> None:
        """Simplified maintenance loop using manager delegation."""
        try:
            while not self._shutdown_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=MAINTENANCE_INTERVAL
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Continue with maintenance
                
                await self._perform_maintenance()
                
        except asyncio.CancelledError:
            _LOGGER.debug("Maintenance loop cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Maintenance loop error: %s", err, exc_info=True)

    async def _batch_processor_loop(self) -> None:
        """Simplified batch processor using BatchManager."""
        try:
            while not self._shutdown_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=5  # Check every 5 seconds
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Continue checking
                
                if await self._batch_manager.should_batch_now():
                    await self.async_refresh()
                    
        except asyncio.CancelledError:
            _LOGGER.debug("Batch processor cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Batch processor error: %s", err, exc_info=True)

    async def _perform_maintenance(self) -> None:
        """Delegate maintenance to managers."""
        # Clear expired cache entries
        cleared = await self._cache_manager.clear_expired()
        
        # Optimize cache if needed
        if cleared > 10:
            await self._cache_manager.optimize_cache()
        
        # Optimize batch processing
        await self._batch_manager.optimize_batching()
        
        # Log maintenance summary
        cache_stats = self._cache_manager.get_stats()
        perf_stats = self._performance_monitor.get_stats()
        
        if cleared > 0 or cache_stats["hit_rate"] < 50:
            _LOGGER.debug(
                "Maintenance: cache_cleared=%d, hit_rate=%.1f%%, p95=%.2fs",
                cleared,
                cache_stats["hit_rate"],
                perf_stats.get("p95", 0),
            )

    @performance_monitor(timeout=30.0)
    async def _async_update_data(self) -> dict[str, Any]:
        """Lightweight update using manager delegation."""
        start_time = dt_util.utcnow()
        
        try:
            if not self.dogs:
                return {}
            
            # Get batch from BatchManager
            batch = await self._batch_manager.get_batch()
            
            # If no specific batch, update all dogs
            if not batch:
                batch = [dog[CONF_DOG_ID] for dog in self.dogs]
            
            # Process dogs using manager delegation
            all_results: dict[str, Any] = {}
            errors = 0
            
            for dog_id in batch:
                try:
                    dog_data = await self._fetch_dog_data_delegated(dog_id)
                    if dog_data:
                        all_results[dog_id] = dog_data
                except Exception as err:
                    _LOGGER.warning("Failed to fetch data for %s: %s", dog_id, err)
                    errors += 1
                    # Use last known data
                    all_results[dog_id] = self._data.get(dog_id, {})
            
            if errors == len(batch):
                raise UpdateFailed("All dog updates failed")
            
            # Apply selective updates
            updated_count = self._apply_selective_updates(all_results)
            
            # Record performance using PerformanceMonitor
            duration = (dt_util.utcnow() - start_time).total_seconds()
            self._performance_monitor.record_update(duration, errors)
            
            if updated_count > 0 or errors > 0:
                _LOGGER.debug(
                    "Update completed: %d/%d dogs updated, %d errors, %.2fs",
                    updated_count,
                    len(batch),
                    errors,
                    duration,
                )
            
            return self._data
            
        except Exception as err:
            _LOGGER.error("Update failed: %s", err)
            self._performance_monitor.record_update(0, 1)
            raise UpdateFailed(f"Update failed: {err}") from err

    async def _fetch_dog_data_delegated(self, dog_id: str) -> dict[str, Any]:
        """Fetch dog data using manager delegation with caching.
        
        Args:
            dog_id: Dog identifier
            
        Returns:
            Complete dog data
        """
        # Check cache first
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
        
        # Delegate to specialized managers
        try:
            # Feeding data
            if modules.get(MODULE_FEEDING) and self.feeding_manager:
                feeding_data = await self.feeding_manager.async_get_feeding_data(dog_id)
                data[MODULE_FEEDING] = feeding_data
            
            # Walk data
            if modules.get(MODULE_WALK) and self.walk_manager:
                walk_data = await self.walk_manager.async_get_walk_data(dog_id)
                data[MODULE_WALK] = walk_data
            
            # GPS data  
            if modules.get(MODULE_GPS) and self.walk_manager:
                gps_data = await self.walk_manager.async_get_gps_data(dog_id)
                data[MODULE_GPS] = gps_data
            
            # Health data
            if modules.get(MODULE_HEALTH) and self.dog_data_manager:
                dog_full_data = await self.dog_data_manager.async_get_dog_data(dog_id)
                if dog_full_data:
                    data[MODULE_HEALTH] = dog_full_data.get("health", {})
            
        except asyncio.TimeoutError:
            _LOGGER.debug("Manager timeout for %s", dog_id)
            data = {"dog_info": dog_config, "error": "timeout"}
        
        # Cache result
        await self._cache_manager.set(cache_key, data, CACHE_TTL_MEDIUM)
        
        return data

    def _apply_selective_updates(self, new_data: dict[str, Any]) -> int:
        """Apply updates with change detection.
        
        Args:
            new_data: New data to apply
            
        Returns:
            Number of dogs updated
        """
        updated_count = 0
        
        for dog_id, dog_data in new_data.items():
            # Use hashlib for consistent change detection
            data_bytes = str(sorted(dog_data.items())).encode()
            checksum = hashlib.md5(data_bytes).hexdigest()
            
            old_checksum = self._data_checksums.get(dog_id)
            
            if old_checksum != checksum:
                self._data[dog_id] = dog_data
                self._data_checksums[dog_id] = checksum
                self._last_successful_update[dog_id] = dt_util.utcnow()
                updated_count += 1
        
        return updated_count

    def _calculate_optimal_update_interval(self) -> int:
        """Calculate optimal interval with improved heuristics."""
        base_interval = UPDATE_INTERVALS["frequent"]
        
        # Analyze module complexity
        total_complexity = 0
        gps_dogs = 0
        
        for dog in self.dogs:
            modules = dog.get("modules", {})
            
            # Calculate complexity score
            if modules.get(MODULE_GPS):
                total_complexity += 3
                gps_dogs += 1
            if modules.get(MODULE_WALK):
                total_complexity += 2
            if modules.get(MODULE_HEALTH):
                total_complexity += 1
            if modules.get(MODULE_FEEDING):
                total_complexity += 1
        
        # Dynamic interval based on total complexity
        if total_complexity == 0:
            return UPDATE_INTERVALS["slow"]
        
        # GPS requires frequent updates
        if gps_dogs > 0:
            gps_interval = self.config_entry.options.get(
                CONF_GPS_UPDATE_INTERVAL,
                UPDATE_INTERVALS["frequent"]
            )
            base_interval = min(base_interval, gps_interval)
        
        # Scale by complexity
        if total_complexity > 20:
            base_interval = max(base_interval, 90)
        elif total_complexity > 10:
            base_interval = max(base_interval, 60)
        elif total_complexity > 5:
            base_interval = max(base_interval, 45)
        
        # Never go below minimum
        return max(base_interval, UPDATE_INTERVALS["real_time"])

    # Public interface methods (simplified)
    def get_dog_config(self, dog_id: str) -> dict[str, Any] | None:
        """Get dog configuration."""
        for dog in self._dogs_config:
            if dog.get(CONF_DOG_ID) == dog_id:
                return dog
        return None

    def get_enabled_modules(self, dog_id: str) -> set[str]:
        """Get enabled modules for dog."""
        config = self.get_dog_config(dog_id)
        if not config:
            return set()
        modules = config.get("modules", {})
        return {name for name, enabled in modules.items() if enabled}

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        """Check if module is enabled."""
        return module in self.get_enabled_modules(dog_id)

    def get_dog_ids(self) -> list[str]:
        """Get all dog IDs."""
        return [dog.get(CONF_DOG_ID) for dog in self._dogs_config]

    def get_dog_data(self, dog_id: str) -> Optional[dict[str, Any]]:
        """Get data for specific dog."""
        return self._data.get(dog_id)

    def get_all_dogs_data(self) -> dict[str, Any]:
        """Get all dogs data."""
        return self._data.copy()

    async def async_request_selective_refresh(
        self, 
        dog_ids: list[str],
        priority: int = 5
    ) -> None:
        """Request selective refresh with priority using BatchManager.
        
        Args:
            dog_ids: Dogs to refresh
            priority: Update priority (0-10, higher = more urgent)
        """
        for dog_id in dog_ids:
            # Invalidate cache
            await self._cache_manager.invalidate(f"dog_{dog_id}")
            
            # Add to batch with priority
            await self._batch_manager.add_to_batch(dog_id, priority)
        
        # Force refresh if high priority
        if priority >= 8 and await self._batch_manager.has_pending():
            await self.async_refresh()

    async def invalidate_dog_cache(self, dog_id: str) -> None:
        """Invalidate all caches for a dog."""
        await self._cache_manager.invalidate(f"dog_{dog_id}")
        self._data_checksums.pop(dog_id, None)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics from all managers."""
        return {
            "cache": self._cache_manager.get_stats(),
            "performance": self._performance_monitor.get_stats(),
            "batch": self._batch_manager.get_stats(),
            "dogs_tracked": len(self._data),
            "last_updates": {
                dog_id: update_time.isoformat()
                for dog_id, update_time in 
                list(self._last_successful_update.items())[:5]  # Top 5
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
        """Clean shutdown with proper task cancellation."""
        _LOGGER.debug("Shutting down lightweight coordinator")
        
        # Signal shutdown to tasks
        self._shutdown_event.set()
        
        # Cancel background tasks gracefully
        tasks = []
        for task_name in ["_maintenance_task", "_batch_processor_task"]:
            task = getattr(self, task_name, None)
            if task and not task.done():
                tasks.append(task)
        
        # Wait for graceful shutdown with timeout
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                # Force cancellation if graceful shutdown fails
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clear managers
        await self._cache_manager.clear()
        await self._batch_manager.clear_pending()
        
        # Clear data structures
        self._data.clear()
        self._data_checksums.clear()
        self._last_successful_update.clear()
        
        _LOGGER.debug("Lightweight coordinator shutdown completed")
