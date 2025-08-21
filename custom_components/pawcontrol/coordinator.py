"""Data update coordinator for Paw Control integration.

This module provides the central data coordination functionality for the
Paw Control integration. It manages data updates, handles multiple dogs,
and optimizes performance through intelligent update intervals and parallel
processing. Designed to meet Home Assistant's Platinum quality standards.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_GPS_UPDATE_INTERVAL,
    DEFAULT_GPS_UPDATE_INTERVAL,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    UPDATE_INTERVALS,
)

_LOGGER = logging.getLogger(__name__)

# Type aliases for better code readability
DogData = Dict[str, Any]
ModuleData = Dict[str, Any]
CoordinatorData = Dict[str, DogData]


class PawControlCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Data update coordinator for Paw Control integration.
    
    This coordinator manages data updates for all dogs in a config entry.
    It provides intelligent update scheduling based on enabled modules,
    parallel data processing for optimal performance, and robust error
    handling to maintain system stability.
    
    The coordinator follows Home Assistant's async patterns and provides
    efficient data management for the integration's entities.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the Paw Control coordinator.
        
        Sets up the coordinator with optimal update intervals based on
        enabled modules and prepares data structures for efficient operation.
        
        Args:
            hass: Home Assistant instance
            entry: Configuration entry containing dog configurations
        """
        self.entry = entry
        self.dogs: List[Dict[str, Any]] = entry.data.get(CONF_DOGS, [])
        
        # Calculate optimal update interval based on enabled modules
        update_interval = self._calculate_optimal_update_interval()
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=update_interval),
        )
        
        # Internal data storage
        self._data: CoordinatorData = {}
        self._listeners: Set[Callable[[], None]] = set()
        self._module_processors: Dict[str, Callable] = self._setup_module_processors()
        
        _LOGGER.debug(
            "Coordinator initialized for %d dogs with %ds update interval",
            len(self.dogs),
            update_interval,
        )

    def _calculate_optimal_update_interval(self) -> int:
        """Calculate the optimal update interval based on enabled modules.
        
        Analyzes all configured dogs and their enabled modules to determine
        the most appropriate update frequency. GPS and walk modules require
        more frequent updates, while feeding and health can use longer intervals.
        
        Returns:
            Update interval in seconds (minimum 30 seconds)
        """
        # Start with default balanced interval
        base_interval = UPDATE_INTERVALS["balanced"]
        
        # Check for modules requiring frequent updates
        has_gps = False
        has_realtime_modules = False
        
        for dog in self.dogs:
            modules = dog.get("modules", {})
            
            # GPS module requires frequent updates
            if modules.get(MODULE_GPS, False):
                has_gps = True
                gps_interval = self.entry.options.get(
                    CONF_GPS_UPDATE_INTERVAL,
                    DEFAULT_GPS_UPDATE_INTERVAL
                )
                base_interval = min(base_interval, gps_interval)
            
            # Real-time modules (GPS, Walk tracking)
            realtime_modules = [MODULE_GPS, MODULE_WALK]
            if any(modules.get(module, False) for module in realtime_modules):
                has_realtime_modules = True
        
        # Adjust interval based on feature requirements
        if has_realtime_modules:
            base_interval = min(base_interval, UPDATE_INTERVALS["frequent"])
        
        if not has_gps and not has_realtime_modules:
            # Only feeding/health modules - can use minimal updates
            base_interval = max(base_interval, UPDATE_INTERVALS["minimal"])
        
        # Ensure minimum update interval for responsiveness
        return max(base_interval, 30)

    def _setup_module_processors(self) -> Dict[str, Callable]:
        """Setup module-specific data processors.
        
        Creates a mapping of module names to their respective data processing
        functions. This allows for modular and maintainable data handling.
        
        Returns:
            Dictionary mapping module names to processor functions
        """
        return {
            MODULE_GPS: self._process_gps_data,
            MODULE_FEEDING: self._process_feeding_data,
            MODULE_HEALTH: self._process_health_data,
            MODULE_WALK: self._process_walk_data,
        }

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch and update data for all configured dogs.
        
        This is the main update function called by Home Assistant. It processes
        all dogs in parallel for optimal performance and provides comprehensive
        error handling to ensure system stability.
        
        Returns:
            Dictionary containing data for all dogs organized by dog_id
            
        Raises:
            UpdateFailed: If critical errors occur during data update
        """
        try:
            # Process all dogs in parallel for better performance
            update_tasks = [
                self._async_update_dog_data(dog)
                for dog in self.dogs
            ]
            
            # Execute all updates concurrently
            dog_results = await asyncio.gather(*update_tasks, return_exceptions=True)
            
            # Process results and handle any exceptions
            updated_data: CoordinatorData = {}
            error_count = 0
            
            for dog, result in zip(self.dogs, dog_results):
                dog_id = dog[CONF_DOG_ID]
                
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "Failed to update data for dog %s: %s",
                        dog_id,
                        result
                    )
                    error_count += 1
                    # Keep previous data if available, otherwise use empty dict
                    updated_data[dog_id] = self._data.get(dog_id, {})
                else:
                    updated_data[dog_id] = result
            
            # Update internal data storage
            self._data = updated_data
            
            # Log update summary
            success_count = len(self.dogs) - error_count
            _LOGGER.debug(
                "Data update completed: %d successful, %d errors",
                success_count,
                error_count
            )
            
            # Only fail if all dogs failed to update
            if error_count == len(self.dogs) and len(self.dogs) > 0:
                raise UpdateFailed("All dog data updates failed")
            
            return updated_data
            
        except Exception as err:
            _LOGGER.error("Critical error during data update: %s", err)
            raise UpdateFailed(f"Data update failed: {err}") from err

    async def _async_update_dog_data(self, dog: Dict[str, Any]) -> DogData:
        """Update data for a specific dog.
        
        Processes all enabled modules for a dog in parallel and combines
        the results into a comprehensive data structure.
        
        Args:
            dog: Dog configuration dictionary
            
        Returns:
            Complete data structure for the dog including all module data
            
        Raises:
            Exception: If dog data processing fails
        """
        dog_id = dog[CONF_DOG_ID]
        dog_name = dog[CONF_DOG_NAME]
        enabled_modules = dog.get("modules", {})
        
        _LOGGER.debug("Updating data for dog: %s (%s)", dog_name, dog_id)
        
        # Base dog data structure
        dog_data: DogData = {
            "dog_info": dog,
            "last_update": dt_util.utcnow().isoformat(),
            "status": "online",
            "enabled_modules": list(enabled_modules.keys()),
        }
        
        # Process enabled modules in parallel
        module_tasks = []
        module_names = []
        
        for module_name, enabled in enabled_modules.items():
            if enabled and module_name in self._module_processors:
                module_tasks.append(
                    self._module_processors[module_name](dog_id)
                )
                module_names.append(module_name)
        
        if module_tasks:
            # Execute all module processors concurrently
            module_results = await asyncio.gather(
                *module_tasks, 
                return_exceptions=True
            )
            
            # Process module results
            for module_name, result in zip(module_names, module_results):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "Failed to process %s data for %s: %s",
                        module_name,
                        dog_id,
                        result
                    )
                    # Use empty data for failed modules
                    dog_data[module_name] = {}
                else:
                    dog_data[module_name] = result
        
        return dog_data

    async def _process_gps_data(self, dog_id: str) -> ModuleData:
        """Process GPS and location data for a dog.
        
        Retrieves and processes GPS data from configured sources including
        device trackers, person entities, and direct GPS feeds.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            GPS data including location, accuracy, speed, and zone information
        """
        # TODO: Implement GPS data processing from configured sources
        # This would integrate with Home Assistant's device_tracker,
        # person entities, and external GPS services
        
        gps_data: ModuleData = {
            "latitude": None,
            "longitude": None,
            "accuracy": None,
            "last_seen": None,
            "zone": "unknown",
            "distance_from_home": None,
            "speed": None,
            "heading": None,
            "battery_level": None,
            "source": "none",
        }
        
        # Simulate data processing - in real implementation this would:
        # 1. Query configured device_tracker entities
        # 2. Get person entity locations
        # 3. Calculate distances and zones
        # 4. Determine GPS accuracy and freshness
        
        return gps_data

    async def _process_feeding_data(self, dog_id: str) -> ModuleData:
        """Process feeding and nutrition data for a dog.
        
        Analyzes feeding history and calculates feeding statistics,
        meal timing, and nutrition tracking information.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            Feeding data including meal history, schedules, and statistics
        """
        now = dt_util.now()
        now.date()
        
        # TODO: Load actual feeding data from storage
        # This would query the data manager for feeding history
        
        feeding_data: ModuleData = {
            "last_feeding": None,
            "last_feeding_type": None,
            "last_feeding_hours": None,
            "feedings_today": {
                "breakfast": 0,
                "lunch": 0,
                "dinner": 0,
                "snack": 0,
            },
            "total_feedings_today": 0,
            "next_feeding_due": None,
            "is_hungry": False,
            "daily_target_met": False,
            "feeding_schedule_adherence": 100.0,
        }
        
        # Calculate feeding metrics
        total_today = sum(feeding_data["feedings_today"].values())
        feeding_data["total_feedings_today"] = total_today
        feeding_data["is_hungry"] = total_today == 0  # Simplified logic
        
        return feeding_data

    async def _process_health_data(self, dog_id: str) -> ModuleData:
        """Process health and medical data for a dog.
        
        Analyzes health records, weight tracking, medication schedules,
        and veterinary appointment information.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            Health data including weight trends, medical status, and care schedules
        """
        # TODO: Load actual health data from storage
        # This would query the data manager for health records
        
        health_data: ModuleData = {
            "current_weight": None,
            "last_weight_date": None,
            "weight_trend": "stable",
            "weight_change_percent": 0.0,
            "last_vet_visit": None,
            "days_since_vet_visit": None,
            "next_checkup_due": None,
            "medications_due": [],
            "active_medications": [],
            "last_grooming": None,
            "days_since_grooming": None,
            "grooming_due": False,
            "health_status": "good",
            "activity_level": "normal",
            "health_alerts": [],
        }
        
        return health_data

    async def _process_walk_data(self, dog_id: str) -> ModuleData:
        """Process walk and exercise data for a dog.
        
        Analyzes walk history, exercise patterns, and activity levels
        to provide comprehensive activity tracking.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            Walk data including activity history, current status, and statistics
        """
        # TODO: Load actual walk data from storage
        # This would query the data manager for walk history
        
        walk_data: ModuleData = {
            "walk_in_progress": False,
            "current_walk_start": None,
            "current_walk_duration": 0,
            "current_walk_distance": 0,
            "last_walk": None,
            "last_walk_duration": None,
            "last_walk_distance": None,
            "last_walk_hours": None,
            "walks_today": 0,
            "total_distance_today": 0,
            "total_duration_today": 0,
            "weekly_walk_count": 0,
            "weekly_distance": 0,
            "needs_walk": False,
            "walk_goal_met": False,
            "activity_score": 0,
        }
        
        return walk_data

    @callback
    def async_add_listener(
        self, 
        update_callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Add a listener for data updates.
        
        Registers a callback function to be called whenever coordinator
        data is updated. This is used by entities to stay synchronized.
        
        Args:
            update_callback: Function to call when data updates
            
        Returns:
            Function to remove the listener when no longer needed
        """
        self._listeners.add(update_callback)
        
        @callback
        def remove_listener() -> None:
            """Remove the listener from the coordinator.
            
            This function should be called when the listener is no longer
            needed to prevent memory leaks.
            """
            self._listeners.discard(update_callback)
        
        return remove_listener

    @callback
    def async_update_listeners(self) -> None:
        """Notify all registered listeners of data updates.
        
        Calls all registered listener callbacks to inform them that
        coordinator data has been updated. Handles exceptions gracefully
        to prevent one failing listener from affecting others.
        """
        failed_listeners = []
        
        for listener in self._listeners:
            try:
                listener()
            except Exception as err:
                _LOGGER.exception("Error calling update listener: %s", err)
                failed_listeners.append(listener)
        
        # Remove listeners that consistently fail
        for failed_listener in failed_listeners:
            self._listeners.discard(failed_listener)
        
        if failed_listeners:
            _LOGGER.warning("Removed %d failed listeners", len(failed_listeners))

    def get_dog_data(self, dog_id: str) -> Optional[DogData]:
        """Get data for a specific dog.
        
        Retrieves the complete data structure for a dog including
        all module data and metadata.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            Dog data dictionary or None if dog not found
        """
        return self._data.get(dog_id)

    def get_all_dogs_data(self) -> CoordinatorData:
        """Get data for all dogs managed by this coordinator.
        
        Returns:
            Complete data structure containing all dogs' data
        """
        return self._data.copy()

    def get_module_data(self, dog_id: str, module: str) -> Optional[ModuleData]:
        """Get specific module data for a dog.
        
        Args:
            dog_id: Unique identifier for the dog
            module: Module name to retrieve data for
            
        Returns:
            Module data dictionary or None if not found
        """
        dog_data = self.get_dog_data(dog_id)
        if dog_data:
            return dog_data.get(module)
        return None

    async def async_refresh_dog(self, dog_id: str) -> None:
        """Refresh data for a specific dog.
        
        Triggers an immediate data update for a single dog without
        affecting the normal update cycle for other dogs.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Raises:
            ValueError: If dog_id is not found in configuration
        """
        # Find the dog configuration
        dog_config = None
        for dog in self.dogs:
            if dog[CONF_DOG_ID] == dog_id:
                dog_config = dog
                break
        
        if not dog_config:
            raise ValueError(f"Dog {dog_id} not found in configuration")
        
        try:
            # Update data for this specific dog
            updated_dog_data = await self._async_update_dog_data(dog_config)
            self._data[dog_id] = updated_dog_data
            
            # Notify listeners of the update
            self.async_update_listeners()
            
            _LOGGER.debug("Refreshed data for dog %s", dog_id)
            
        except Exception as err:
            _LOGGER.error("Failed to refresh data for dog %s: %s", dog_id, err)
            raise

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and cleanup resources.
        
        Performs cleanup operations when the coordinator is being
        shut down, including clearing listeners and stopping any
        background tasks.
        """
        _LOGGER.debug("Shutting down Paw Control coordinator")
        
        # Clear all listeners
        self._listeners.clear()
        
        # Clear data
        self._data.clear()
        
        _LOGGER.debug("Coordinator shutdown completed")

    @property
    def config_entry(self) -> ConfigEntry:
        """Return the configuration entry for this coordinator.
        
        Returns:
            ConfigEntry instance containing integration configuration
        """
        return self.entry

    @property
    def available(self) -> bool:
        """Return if the coordinator is available.
        
        A coordinator is considered available if the last update
        was successful and recent.
        
        Returns:
            True if coordinator is available, False otherwise
        """
        return self.last_update_success

    def is_dog_configured(self, dog_id: str) -> bool:
        """Check if a dog is configured in this coordinator.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            True if the dog is configured, False otherwise
        """
        return any(dog[CONF_DOG_ID] == dog_id for dog in self.dogs)

    def get_dog_info(self, dog_id: str) -> Optional[Dict[str, Any]]:
        """Get basic configuration information for a dog.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            Dog configuration dictionary or None if not found
        """
        for dog in self.dogs:
            if dog[CONF_DOG_ID] == dog_id:
                return dog.copy()
        return None

    def get_enabled_modules(self, dog_id: str) -> List[str]:
        """Get list of enabled modules for a dog.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            List of enabled module names
        """
        dog_info = self.get_dog_info(dog_id)
        if not dog_info:
            return []
        
        modules = dog_info.get("modules", {})
        return [module for module, enabled in modules.items() if enabled]

    async def async_update_config(self, new_config: Dict[str, Any]) -> None:
        """Update coordinator configuration.
        
        Updates the coordinator's configuration and recalculates
        update intervals based on new module settings.
        
        Args:
            new_config: New configuration data
        """
        self.dogs = new_config.get(CONF_DOGS, [])
        
        # Recalculate update interval based on new configuration
        new_interval = self._calculate_optimal_update_interval()
        self.update_interval = timedelta(seconds=new_interval)
        
        _LOGGER.debug(
            "Configuration updated: %d dogs, new interval: %ds",
            len(self.dogs),
            new_interval,
        )
        
        # Trigger immediate refresh with new configuration
        await self.async_refresh()

    def get_update_statistics(self) -> Dict[str, Any]:
        """Get coordinator update statistics.
        
        Provides information about coordinator performance and
        update patterns for diagnostics and monitoring.
        
        Returns:
            Dictionary containing update statistics
        """
        return {
            "total_dogs": len(self.dogs),
            "last_update_success": self.last_update_success,
            "last_update_time": self.last_update_time,
            "update_interval_seconds": self.update_interval.total_seconds(),
            "active_listeners": len(self._listeners),
            "data_size": len(self._data),
        }
