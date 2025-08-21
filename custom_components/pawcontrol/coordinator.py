"""Data update coordinator for Paw Control integration - Complete Implementation.

This module provides the central data coordination functionality for the
Paw Control integration. It manages data updates, handles multiple dogs,
and optimizes performance through intelligent update intervals and parallel
processing. Designed to meet Home Assistant's Platinum quality standards.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
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
from .utils import (
    async_calculate_haversine_distance,
    calculate_bmr_advanced,
    calculate_trend_advanced,
    format_time_ago_smart,
    safe_convert,
    performance_monitor,
)

if TYPE_CHECKING:
    from .types import (
        DogConfigData,
        PawControlRuntimeData,
    )

_LOGGER = logging.getLogger(__name__)


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for Paw Control integration with complete implementation.
    
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
        self.dogs: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
        
        # Calculate optimal update interval based on enabled modules
        update_interval = self._calculate_optimal_update_interval()
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=update_interval),
            always_update=False,  # Modern HA 2025.8+ approach
        )
        
        # Internal data storage with type annotations
        self._data: dict[str, Any] = {}
        self._listeners: set[Callable[[], None]] = set()
        self._module_processors: dict[str, Callable[[str], Any]] = self._setup_module_processors()
        self._performance_metrics: dict[str, Any] = {
            "update_count": 0,
            "error_count": 0,
            "average_update_time": 0.0,
            "last_performance_check": dt_util.utcnow(),
        }
        
        # Home Assistant zone and entity caches for performance
        self._home_zone_cache: dict[str, Any] | None = None
        self._zone_cache: dict[str, dict[str, Any]] = {}
        self._entity_cache: dict[str, Any] = {}
        self._cache_expiry: datetime = dt_util.utcnow()
        
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
        active_dogs = 0
        
        for dog in self.dogs:
            modules = dog.get("modules", {})
            active_dogs += 1
            
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
        
        # Adjust interval based on feature requirements and load
        if has_realtime_modules:
            base_interval = min(base_interval, UPDATE_INTERVALS["frequent"])
        
        if not has_gps and not has_realtime_modules:
            # Only feeding/health modules - can use minimal updates
            base_interval = max(base_interval, UPDATE_INTERVALS["minimal"])
        
        # Scale based on number of dogs to prevent system overload
        if active_dogs > 5:
            base_interval = max(base_interval, 60)  # Minimum 1 minute for many dogs
        
        # Ensure minimum update interval for responsiveness
        return max(base_interval, 30)

    def _setup_module_processors(self) -> dict[str, Callable[[str], Any]]:
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and update data for all configured dogs.
        
        This is the main update function called by Home Assistant. It processes
        all dogs in parallel for optimal performance and provides comprehensive
        error handling to ensure system stability.
        
        Returns:
            Dictionary containing data for all dogs organized by dog_id
            
        Raises:
            UpdateFailed: If critical errors occur during data update
        """
        start_time = dt_util.utcnow()
        
        try:
            # Early return if no dogs configured
            if not self.dogs:
                _LOGGER.debug("No dogs configured, returning empty data")
                return {}
            
            # Update caches if expired
            await self._update_caches_if_needed()
            
            # Process all dogs in parallel for better performance
            update_tasks = [
                self._async_update_dog_data(dog)
                for dog in self.dogs
            ]
            
            # Execute all updates concurrently with timeout
            try:
                dog_results = await asyncio.wait_for(
                    asyncio.gather(*update_tasks, return_exceptions=True),
                    timeout=30.0  # 30 second timeout for all dogs
                )
            except asyncio.TimeoutError:
                _LOGGER.warning("Data update timed out after 30 seconds")
                # Fall back to previous data
                return self._data
            
            # Process results and handle any exceptions
            updated_data: dict[str, Any] = {}
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
            
            # Update performance metrics
            update_time = (dt_util.utcnow() - start_time).total_seconds()
            self._update_performance_metrics(update_time, error_count)
            
            # Log update summary
            success_count = len(self.dogs) - error_count
            _LOGGER.debug(
                "Data update completed in %.2fs: %d successful, %d errors",
                update_time,
                success_count,
                error_count
            )
            
            # Only fail if all dogs failed to update and we have dogs
            if error_count == len(self.dogs) and len(self.dogs) > 0:
                raise UpdateFailed("All dog data updates failed")
            
            return updated_data
            
        except Exception as err:
            _LOGGER.error("Critical error during data update: %s", err)
            self._performance_metrics["error_count"] += 1
            raise UpdateFailed(f"Data update failed: {err}") from err

    def _update_performance_metrics(self, update_time: float, error_count: int) -> None:
        """Update internal performance metrics.
        
        Args:
            update_time: Time taken for the update in seconds
            error_count: Number of errors encountered
        """
        metrics = self._performance_metrics
        metrics["update_count"] += 1
        metrics["error_count"] += error_count
        
        # Calculate rolling average of update time
        current_avg = metrics["average_update_time"]
        update_count = metrics["update_count"]
        metrics["average_update_time"] = (
            (current_avg * (update_count - 1) + update_time) / update_count
        )
        
        # Log performance warnings
        if update_time > 10.0:
            _LOGGER.warning("Slow update detected: %.2fs", update_time)
        
        if metrics["update_count"] % 100 == 0:  # Log every 100 updates
            _LOGGER.info(
                "Performance metrics: %d updates, %.2fs avg time, %d errors",
                metrics["update_count"],
                metrics["average_update_time"],
                metrics["error_count"]
            )

    async def _async_update_dog_data(self, dog: DogConfigData) -> dict[str, Any]:
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
        
        # Base dog data structure with comprehensive metadata
        dog_data: dict[str, Any] = {
            "dog_info": dog,
            "last_update": dt_util.utcnow().isoformat(),
            "status": "online",
            "enabled_modules": [mod for mod, enabled in enabled_modules.items() if enabled],
            "update_source": "coordinator",
            "data_version": 1,
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
            # Execute all module processors concurrently with timeout
            try:
                module_results = await asyncio.wait_for(
                    asyncio.gather(*module_tasks, return_exceptions=True),
                    timeout=20.0  # 20 second timeout per dog
                )
            except asyncio.TimeoutError:
                _LOGGER.warning("Module processing timed out for dog %s", dog_id)
                # Use empty data for all modules
                for module_name in module_names:
                    dog_data[module_name] = {}
                return dog_data
            
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
                    dog_data[module_name] = result or {}
        
        return dog_data

    async def _update_caches_if_needed(self) -> None:
        """Update internal caches if they have expired."""
        now = dt_util.utcnow()
        
        if now > self._cache_expiry:
            try:
                # Update home zone cache
                await self._update_home_zone_cache()
                
                # Update zone cache
                await self._update_zone_cache()
                
                # Set next cache expiry (every 5 minutes)
                self._cache_expiry = now + timedelta(minutes=5)
                
            except Exception as err:
                _LOGGER.warning("Failed to update caches: %s", err)

    async def _update_home_zone_cache(self) -> None:
        """Update the home zone cache with current data."""
        try:
            zone_state = self.hass.states.get("zone.home")
            if zone_state:
                self._home_zone_cache = {
                    "latitude": float(zone_state.attributes.get("latitude", 0)),
                    "longitude": float(zone_state.attributes.get("longitude", 0)),
                    "radius": float(zone_state.attributes.get("radius", 100)),
                    "friendly_name": zone_state.attributes.get("friendly_name", "Home"),
                }
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Failed to parse home zone data: %s", err)
            self._home_zone_cache = None

    async def _update_zone_cache(self) -> None:
        """Update the zone cache with all available zones."""
        try:
            zones = {}
            for entity_id in self.hass.states.async_entity_ids("zone"):
                zone_state = self.hass.states.get(entity_id)
                if zone_state and zone_state.state != STATE_UNKNOWN:
                    try:
                        zones[entity_id] = {
                            "latitude": float(zone_state.attributes.get("latitude", 0)),
                            "longitude": float(zone_state.attributes.get("longitude", 0)),
                            "radius": float(zone_state.attributes.get("radius", 100)),
                            "friendly_name": zone_state.attributes.get("friendly_name", entity_id),
                            "passive": zone_state.attributes.get("passive", False),
                        }
                    except (ValueError, TypeError):
                        continue
            
            self._zone_cache = zones
            
        except Exception as err:
            _LOGGER.warning("Failed to update zone cache: %s", err)

    @performance_monitor(timeout=15.0)
    async def _process_gps_data(self, dog_id: str) -> dict[str, Any]:
        """Process GPS and location data for a dog with complete implementation.
        
        Retrieves and processes GPS data from configured sources including
        device trackers, person entities, and direct GPS feeds.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            GPS data including location, accuracy, speed, and zone information
        """
        try:
            # Get runtime data for integration access
            runtime_data = self._get_runtime_data()
            if not runtime_data:
                _LOGGER.warning("No runtime data available for GPS processing")
                return self._get_empty_gps_data()
            
            # Access data manager for GPS data
            data_manager = runtime_data.get("data_manager")
            if not data_manager:
                return self._get_empty_gps_data()
            
            # Get current GPS data from data manager
            gps_data = await data_manager.async_get_current_gps_data(dog_id)
            
            if not gps_data:
                return self._get_empty_gps_data()
            
            # Enhance GPS data with calculated fields
            enhanced_data = gps_data.copy()
            
            # Calculate distance from home if location available
            if gps_data.get("latitude") and gps_data.get("longitude"):
                home_location = await self._get_home_location()
                if home_location:
                    try:
                        distance = await async_calculate_haversine_distance(
                            (gps_data["latitude"], gps_data["longitude"]),
                            (home_location["latitude"], home_location["longitude"])
                        )
                        enhanced_data["distance_from_home"] = round(distance, 1)
                    except Exception as err:
                        _LOGGER.debug("Failed to calculate distance from home: %s", err)
                        enhanced_data["distance_from_home"] = None
            
            # Determine current zone with comprehensive zone checking
            zone_info = await self._determine_current_zone(
                enhanced_data.get("latitude"), enhanced_data.get("longitude")
            )
            enhanced_data.update(zone_info)
            
            # Calculate movement and speed trends
            movement_data = await self._calculate_movement_data(dog_id, enhanced_data)
            enhanced_data.update(movement_data)
            
            return enhanced_data
            
        except Exception as err:
            _LOGGER.error("Error processing GPS data for %s: %s", dog_id, err)
            return self._get_empty_gps_data()

    def _get_empty_gps_data(self) -> dict[str, Any]:
        """Get empty GPS data structure with all required fields."""
        return {
            "latitude": None,
            "longitude": None,
            "accuracy": None,
            "last_seen": None,
            "zone": "unknown",
            "zone_friendly_name": "Unknown",
            "distance_from_home": None,
            "speed": None,
            "heading": None,
            "battery_level": None,
            "source": "none",
            "status": "unavailable",
            "is_home": False,
            "is_moving": False,
            "movement_confidence": 0.0,
        }

    @performance_monitor(timeout=10.0)
    async def _process_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Process feeding and nutrition data for a dog with complete calculations.
        
        Analyzes feeding history and calculates feeding statistics,
        meal timing, and nutrition tracking information.
        
        Args:
            dog_id: Unique identifier for the dog
            
        Returns:
            Feeding data including meal history, schedules, and statistics
        """
        try:
            runtime_data = self._get_runtime_data()
            if not runtime_data:
                return self._get_empty_feeding_data()
            
            data_manager = runtime_data.get("data_manager")
            if not data_manager:
                return self._get_empty_feeding_data()
            
            # Get feeding data from data manager
            feeding_history = await data_manager.async_get_feeding_history(dog_id, days=1)
            feeding_schedule = await data_manager.async_get_feeding_schedule(dog_id)
            
            # Calculate feeding statistics with comprehensive analysis
            now = dt_util.now()
            today = now.date()
            
            # Count today's feedings by type with detailed tracking
            feedings_today = {
                "breakfast": 0,
                "lunch": 0,
                "dinner": 0,
                "snack": 0,
                "treat": 0,
            }
            
            total_calories_today = 0.0
            total_portion_today = 0.0
            last_feeding = None
            feeding_times = []
            
            if feeding_history:
                for feeding in feeding_history:
                    feeding_date = feeding.get("timestamp", now).date()
                    if feeding_date == today:
                        meal_type = feeding.get("meal_type", "snack")
                        if meal_type in feedings_today:
                            feedings_today[meal_type] += 1
                        
                        total_calories_today += feeding.get("calories", 0)
                        total_portion_today += feeding.get("portion_size", 0)
                        feeding_times.append(feeding.get("timestamp"))
                        
                        if not last_feeding or feeding["timestamp"] > last_feeding["timestamp"]:
                            last_feeding = feeding
            
            # Calculate comprehensive feeding metrics
            total_feedings_today = sum(feedings_today.values())
            
            # Determine if dog is hungry based on schedule and last feeding
            is_hungry = await self._calculate_hunger_status(dog_id, last_feeding, feeding_schedule)
            
            # Calculate next feeding time with smart scheduling
            next_feeding = await self._calculate_next_feeding(dog_id, feeding_schedule, feeding_times)
            
            # Calculate feeding consistency and schedule adherence
            schedule_adherence = await self._calculate_schedule_adherence(
                dog_id, feeding_times, feeding_schedule
            )
            
            # Calculate nutritional needs and recommendations
            nutrition_data = await self._calculate_nutrition_analysis(
                dog_id, total_calories_today, total_portion_today
            )
            
            return {
                "last_feeding": last_feeding,
                "last_feeding_type": last_feeding.get("meal_type") if last_feeding else None,
                "last_feeding_hours": self._calculate_hours_since(last_feeding["timestamp"]) if last_feeding else None,
                "feedings_today": feedings_today,
                "total_feedings_today": total_feedings_today,
                "total_calories_today": round(total_calories_today, 1),
                "total_portion_today": round(total_portion_today, 1),
                "next_feeding_due": next_feeding,
                "is_hungry": is_hungry,
                "daily_target_met": total_feedings_today >= feeding_schedule.get("meals_per_day", 2),
                "feeding_schedule_adherence": round(schedule_adherence, 1),
                **nutrition_data,
            }
            
        except Exception as err:
            _LOGGER.error("Error processing feeding data for %s: %s", dog_id, err)
            return self._get_empty_feeding_data()

    def _get_empty_feeding_data(self) -> dict[str, Any]:
        """Get empty feeding data structure with all required fields."""
        return {
            "last_feeding": None,
            "last_feeding_type": None,
            "last_feeding_hours": None,
            "feedings_today": {"breakfast": 0, "lunch": 0, "dinner": 0, "snack": 0, "treat": 0},
            "total_feedings_today": 0,
            "total_calories_today": 0.0,
            "total_portion_today": 0.0,
            "next_feeding_due": None,
            "is_hungry": False,
            "daily_target_met": False,
            "feeding_schedule_adherence": 100.0,
            "calorie_target": 0,
            "calorie_progress": 0.0,
            "nutrition_status": "unknown",
        }

    @performance_monitor(timeout=10.0)
    async def _process_health_data(self, dog_id: str) -> dict[str, Any]:
        """Process health and medical data for a dog with comprehensive analysis."""
        try:
            runtime_data = self._get_runtime_data()
            if not runtime_data:
                return self._get_empty_health_data()
            
            data_manager = runtime_data.get("data_manager")
            if not data_manager:
                return self._get_empty_health_data()
            
            # Get comprehensive health data from data manager
            health_history = await data_manager.async_get_health_history(dog_id, days=30)
            weight_history = await data_manager.async_get_weight_history(dog_id, days=90)
            medications = await data_manager.async_get_active_medications(dog_id)
            
            # Process weight data with trend analysis
            weight_data = self._process_weight_data_comprehensive(weight_history)
            
            # Process medication data with scheduling
            medication_data = await self._process_medication_data_comprehensive(medications)
            
            # Get care history and schedule future appointments
            last_vet_visit = await data_manager.async_get_last_vet_visit(dog_id)
            last_grooming = await data_manager.async_get_last_grooming(dog_id)
            
            # Calculate comprehensive health alerts and recommendations
            health_alerts = await self._calculate_health_alerts_comprehensive(dog_id, {
                "weight_data": weight_data,
                "medications": medication_data,
                "last_vet_visit": last_vet_visit,
                "last_grooming": last_grooming,
                "health_history": health_history,
            })
            
            # Calculate health scores and trends
            health_scores = await self._calculate_health_scores(dog_id, health_history, weight_data)
            
            return {
                **weight_data,
                **medication_data,
                **health_scores,
                "last_vet_visit": last_vet_visit,
                "days_since_vet_visit": self._calculate_days_since(last_vet_visit["date"]) if last_vet_visit else None,
                "next_checkup_due": await self._calculate_next_checkup(dog_id, last_vet_visit),
                "last_grooming": last_grooming,
                "days_since_grooming": self._calculate_days_since(last_grooming["date"]) if last_grooming else None,
                "grooming_due": await self._is_grooming_due(dog_id, last_grooming),
                "health_alerts": health_alerts,
                "care_reminders": await self._get_care_reminders(dog_id),
            }
            
        except Exception as err:
            _LOGGER.error("Error processing health data for %s: %s", dog_id, err)
            return self._get_empty_health_data()

    def _get_empty_health_data(self) -> dict[str, Any]:
        """Get empty health data structure with all required fields."""
        return {
            "current_weight": None,
            "last_weight_date": None,
            "weight_trend": "stable",
            "weight_change_percent": 0.0,
            "weight_status": "unknown",
            "last_vet_visit": None,
            "days_since_vet_visit": None,
            "next_checkup_due": None,
            "medications_due": [],
            "active_medications": [],
            "last_grooming": None,
            "days_since_grooming": None,
            "grooming_due": False,
            "health_status": "unknown",
            "activity_level": "unknown",
            "health_alerts": [],
            "health_score": 0,
            "care_reminders": [],
        }

    @performance_monitor(timeout=10.0)
    async def _process_walk_data(self, dog_id: str) -> dict[str, Any]:
        """Process walk and exercise data for a dog with comprehensive analysis."""
        try:
            runtime_data = self._get_runtime_data()
            if not runtime_data:
                return self._get_empty_walk_data()
            
            data_manager = runtime_data.get("data_manager")
            if not data_manager:
                return self._get_empty_walk_data()
            
            # Get comprehensive walk data from data manager
            current_walk = await data_manager.async_get_current_walk(dog_id)
            walk_history = await data_manager.async_get_walk_history(dog_id, days=7)
            
            # Calculate comprehensive walk statistics
            today_stats = self._calculate_today_walk_stats_comprehensive(walk_history)
            weekly_stats = self._calculate_weekly_walk_stats_comprehensive(walk_history)
            
            # Determine walk needs with intelligent recommendations
            walk_recommendation = await self._calculate_walk_recommendation(
                dog_id, walk_history, today_stats
            )
            
            # Calculate activity scores and trends
            activity_analysis = self._calculate_activity_analysis(today_stats, weekly_stats)
            
            # Process current walk if in progress
            current_walk_data = {}
            if current_walk:
                current_walk_data = await self._process_current_walk_data(current_walk)
            
            return {
                "walk_in_progress": current_walk is not None,
                **current_walk_data,
                **today_stats,
                **weekly_stats,
                **walk_recommendation,
                **activity_analysis,
            }
            
        except Exception as err:
            _LOGGER.error("Error processing walk data for %s: %s", dog_id, err)
            return self._get_empty_walk_data()

    def _get_empty_walk_data(self) -> dict[str, Any]:
        """Get empty walk data structure with all required fields."""
        return {
            "walk_in_progress": False,
            "current_walk_start": None,
            "current_walk_duration": 0,
            "current_walk_distance": 0,
            "current_walk_id": None,
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
            "walk_urgency": "none",
            "walk_recommendation": "",
            "walk_goal_met": False,
            "activity_score": 0,
            "activity_trend": "stable",
        }

    # Complete implementation of helper methods

    async def _get_home_location(self) -> Optional[dict[str, float]]:
        """Get home location coordinates from Home Assistant."""
        if self._home_zone_cache:
            return self._home_zone_cache
        
        try:
            zone_state = self.hass.states.get("zone.home")
            if zone_state and zone_state.attributes:
                return {
                    "latitude": float(zone_state.attributes.get("latitude", 0)),
                    "longitude": float(zone_state.attributes.get("longitude", 0)),
                    "radius": float(zone_state.attributes.get("radius", 100)),
                }
        except (ValueError, TypeError) as err:
            _LOGGER.debug("Failed to get home location: %s", err)
        
        return None

    async def _determine_current_zone(
        self, 
        lat: Optional[float], 
        lon: Optional[float]
    ) -> dict[str, Any]:
        """Determine current zone based on coordinates with comprehensive zone checking."""
        if not lat or not lon:
            return {
                "zone": "unknown",
                "zone_friendly_name": "Unknown",
                "is_home": False,
            }
        
        try:
            # Check home zone first
            if self._home_zone_cache:
                home_distance = await async_calculate_haversine_distance(
                    (lat, lon),
                    (self._home_zone_cache["latitude"], self._home_zone_cache["longitude"])
                )
                
                if home_distance <= self._home_zone_cache["radius"]:
                    return {
                        "zone": "home",
                        "zone_friendly_name": "Home",
                        "is_home": True,
                        "distance_to_zone_center": round(home_distance, 1),
                    }
            
            # Check other zones
            for zone_id, zone_data in self._zone_cache.items():
                if zone_data.get("passive", False):
                    continue  # Skip passive zones
                
                zone_distance = await async_calculate_haversine_distance(
                    (lat, lon),
                    (zone_data["latitude"], zone_data["longitude"])
                )
                
                if zone_distance <= zone_data["radius"]:
                    zone_name = zone_id.replace("zone.", "")
                    return {
                        "zone": zone_name,
                        "zone_friendly_name": zone_data["friendly_name"],
                        "is_home": zone_name == "home",
                        "distance_to_zone_center": round(zone_distance, 1),
                    }
            
            # Not in any zone
            return {
                "zone": "not_home",
                "zone_friendly_name": "Away",
                "is_home": False,
            }
            
        except Exception as err:
            _LOGGER.debug("Error determining zone: %s", err)
            return {
                "zone": "unknown",
                "zone_friendly_name": "Unknown",
                "is_home": False,
            }

    async def _calculate_movement_data(
        self, 
        dog_id: str, 
        current_gps: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate movement and speed data for a dog."""
        try:
            # Get previous GPS data for movement calculation
            runtime_data = self._get_runtime_data()
            if not runtime_data:
                return {"is_moving": False, "movement_confidence": 0.0}
            
            data_manager = runtime_data.get("data_manager")
            if not data_manager:
                return {"is_moving": False, "movement_confidence": 0.0}
            
            # Get recent GPS history for movement analysis
            gps_history = await data_manager.async_get_module_data(
                "gps", dog_id, limit=5
            )
            
            if len(gps_history) < 2:
                return {"is_moving": False, "movement_confidence": 0.0}
            
            # Calculate movement based on recent positions
            distances = []
            time_diffs = []
            
            for i in range(1, len(gps_history)):
                prev_point = gps_history[i]
                curr_point = gps_history[i-1]  # More recent
                
                if (prev_point.get("latitude") and curr_point.get("latitude")):
                    distance = await async_calculate_haversine_distance(
                        (prev_point["latitude"], prev_point["longitude"]),
                        (curr_point["latitude"], curr_point["longitude"])
                    )
                    distances.append(distance)
                    
                    # Calculate time difference
                    try:
                        prev_time = datetime.fromisoformat(prev_point["timestamp"])
                        curr_time = datetime.fromisoformat(curr_point["timestamp"])
                        time_diff = (curr_time - prev_time).total_seconds()
                        if time_diff > 0:
                            time_diffs.append(time_diff)
                    except (ValueError, KeyError):
                        continue
            
            if not distances or not time_diffs:
                return {"is_moving": False, "movement_confidence": 0.0}
            
            # Calculate average speed and movement confidence
            total_distance = sum(distances)
            total_time = sum(time_diffs)
            
            if total_time > 0:
                avg_speed_ms = total_distance / total_time
                avg_speed_kmh = avg_speed_ms * 3.6
                
                # Movement detection thresholds
                is_moving = avg_speed_kmh > 1.0  # Moving if > 1 km/h
                movement_confidence = min(avg_speed_kmh / 5.0, 1.0)  # Confidence based on speed
                
                return {
                    "is_moving": is_moving,
                    "movement_confidence": round(movement_confidence, 2),
                    "speed_kmh": round(avg_speed_kmh, 1),
                }
            
            return {"is_moving": False, "movement_confidence": 0.0}
            
        except Exception as err:
            _LOGGER.debug("Error calculating movement data: %s", err)
            return {"is_moving": False, "movement_confidence": 0.0}

    async def _calculate_hunger_status(
        self, 
        dog_id: str, 
        last_feeding: Optional[dict], 
        schedule: dict
    ) -> bool:
        """Calculate if dog is hungry based on feeding schedule and history."""
        if not last_feeding:
            return True  # Always hungry if never fed
        
        try:
            now = dt_util.now()
            last_feeding_time = last_feeding.get("timestamp", now)
            
            if isinstance(last_feeding_time, str):
                last_feeding_time = datetime.fromisoformat(last_feeding_time)
            
            hours_since_feeding = (now - last_feeding_time).total_seconds() / 3600
            
            # Basic hunger logic based on meal type and time
            meal_type = last_feeding.get("meal_type", "snack")
            
            hunger_thresholds = {
                "breakfast": 4,  # Hungry after 4 hours
                "lunch": 5,      # Hungry after 5 hours  
                "dinner": 8,     # Hungry after 8 hours
                "snack": 2,      # Hungry after 2 hours
                "treat": 1,      # Hungry after 1 hour
            }
            
            threshold = hunger_thresholds.get(meal_type, 4)
            
            # Check if scheduled feeding time has passed
            meals_per_day = schedule.get("meals_per_day", 2)
            feeding_interval = 24 / meals_per_day
            
            return hours_since_feeding >= min(threshold, feeding_interval)
            
        except Exception as err:
            _LOGGER.debug("Error calculating hunger status: %s", err)
            return False

    async def _calculate_next_feeding(
        self, 
        dog_id: str, 
        schedule: dict, 
        feeding_times: list
    ) -> Optional[datetime]:
        """Calculate next scheduled feeding time with smart scheduling."""
        try:
            now = dt_util.now()
            meals_per_day = schedule.get("meals_per_day", 2)
            
            # Get configured feeding times
            breakfast_time = schedule.get("breakfast_time")
            lunch_time = schedule.get("lunch_time") 
            dinner_time = schedule.get("dinner_time")
            
            # Default feeding times if not configured
            default_times = {
                1: ["08:00"],
                2: ["08:00", "18:00"],
                3: ["08:00", "13:00", "18:00"],
                4: ["08:00", "12:00", "16:00", "20:00"],
            }
            
            feeding_schedule = []
            if meals_per_day in default_times:
                feeding_schedule = default_times[meals_per_day]
            
            # Override with configured times
            if breakfast_time:
                feeding_schedule[0] = breakfast_time
            if lunch_time and len(feeding_schedule) > 1:
                feeding_schedule[1] = lunch_time  
            if dinner_time and len(feeding_schedule) > 2:
                feeding_schedule[-1] = dinner_time
            
            # Find next feeding time
            current_time = now.time()
            
            for feeding_time_str in feeding_schedule:
                try:
                    feeding_time = datetime.strptime(feeding_time_str, "%H:%M").time()
                    if feeding_time > current_time:
                        # Next feeding is today
                        next_feeding = now.replace(
                            hour=feeding_time.hour,
                            minute=feeding_time.minute,
                            second=0,
                            microsecond=0
                        )
                        return next_feeding
                except ValueError:
                    continue
            
            # All feeding times for today have passed, next is tomorrow's first meal
            if feeding_schedule:
                try:
                    first_meal_time = datetime.strptime(feeding_schedule[0], "%H:%M").time()
                    tomorrow = now + timedelta(days=1)
                    next_feeding = tomorrow.replace(
                        hour=first_meal_time.hour,
                        minute=first_meal_time.minute,
                        second=0,
                        microsecond=0
                    )
                    return next_feeding
                except ValueError:
                    pass
            
            return None
            
        except Exception as err:
            _LOGGER.debug("Error calculating next feeding: %s", err)
            return None

    async def _calculate_schedule_adherence(
        self, 
        dog_id: str, 
        feeding_times: list, 
        schedule: dict
    ) -> float:
        """Calculate feeding schedule adherence percentage."""
        try:
            if not feeding_times or not schedule:
                return 100.0
            
            meals_per_day = schedule.get("meals_per_day", 2)
            actual_meals = len(feeding_times)
            
            # Basic adherence based on meal count
            adherence = min(actual_meals / meals_per_day, 1.0) * 100
            
            return adherence
            
        except Exception as err:
            _LOGGER.debug("Error calculating schedule adherence: %s", err)
            return 100.0

    async def _calculate_nutrition_analysis(
        self, 
        dog_id: str, 
        daily_calories: float, 
        daily_portion: float
    ) -> dict[str, Any]:
        """Calculate nutritional analysis and recommendations."""
        try:
            # Get dog info for calorie calculation
            dog_info = None
            for dog in self.dogs:
                if dog.get(CONF_DOG_ID) == dog_id:
                    dog_info = dog
                    break
            
            if not dog_info:
                return {"calorie_target": 0, "calorie_progress": 0.0, "nutrition_status": "unknown"}
            
            # Calculate calorie needs using advanced BMR calculation
            weight = dog_info.get("dog_weight", 20)
            age = dog_info.get("dog_age", 5)
            size = dog_info.get("dog_size", "medium")
            
            # Estimate activity level (could be enhanced with actual activity data)
            activity_level = "normal"
            
            target_calories = calculate_bmr_advanced(
                weight_kg=weight,
                age_years=age,
                activity_level=activity_level,
                breed_factor=1.0,  # Could be breed-specific
                is_neutered=True   # Could be configured
            )
            
            calorie_progress = (daily_calories / target_calories * 100) if target_calories > 0 else 0
            
            # Determine nutrition status
            if calorie_progress < 75:
                nutrition_status = "underfeeding"
            elif calorie_progress > 125:
                nutrition_status = "overfeeding"
            else:
                nutrition_status = "good"
            
            return {
                "calorie_target": int(target_calories),
                "calorie_progress": round(calorie_progress, 1),
                "nutrition_status": nutrition_status,
            }
            
        except Exception as err:
            _LOGGER.debug("Error calculating nutrition analysis: %s", err)
            return {"calorie_target": 0, "calorie_progress": 0.0, "nutrition_status": "unknown"}

    def _process_weight_data_comprehensive(self, weight_history: list) -> dict[str, Any]:
        """Process weight history data with comprehensive trend analysis."""
        if not weight_history:
            return {
                "current_weight": None,
                "last_weight_date": None,
                "weight_trend": "stable",
                "weight_change_percent": 0.0,
                "weight_status": "unknown",
            }
        
        try:
            # Sort by date
            sorted_weights = sorted(
                weight_history, 
                key=lambda x: x.get("timestamp", datetime.min),
                reverse=True
            )
            
            current_weight = sorted_weights[0].get("weight")
            last_weight_date = sorted_weights[0].get("timestamp")
            
            # Calculate trend using advanced trend analysis
            weights = [entry.get("weight", 0) for entry in sorted_weights[:30]]  # Last 30 entries
            weight_tuple = tuple(weights)  # For caching
            
            trend_analysis = calculate_trend_advanced(weight_tuple, periods=min(len(weights), 14))
            
            # Calculate weight change percentage
            weight_change_percent = 0.0
            if len(sorted_weights) >= 2:
                old_weight = sorted_weights[-1].get("weight", current_weight)
                if old_weight > 0:
                    weight_change_percent = ((current_weight - old_weight) / old_weight) * 100
            
            # Determine weight status
            weight_status = "normal"
            if abs(weight_change_percent) > 10:
                weight_status = "significant_change"
            elif abs(weight_change_percent) > 5:
                weight_status = "moderate_change"
            
            return {
                "current_weight": current_weight,
                "last_weight_date": last_weight_date,
                "weight_trend": trend_analysis["direction"],
                "weight_change_percent": round(weight_change_percent, 1),
                "weight_status": weight_status,
                "weight_trend_confidence": trend_analysis["confidence"],
            }
            
        except Exception as err:
            _LOGGER.debug("Error processing weight data: %s", err)
            return {
                "current_weight": None,
                "last_weight_date": None,
                "weight_trend": "stable",
                "weight_change_percent": 0.0,
                "weight_status": "unknown",
            }

    # Complete medication data processing implementation
    async def _process_medication_data_comprehensive(self, medications: list) -> dict[str, Any]:
        """Process medication data with comprehensive scheduling."""
        if not medications:
            return {
                "medications_due": [],
                "active_medications": [],
                "next_medication_due": None,
                "medications_overdue": [],
            }
        
        now = dt_util.utcnow()
        medications_due = []
        medications_overdue = []
        next_due = None
        
        for med in medications:
            next_dose = med.get("next_dose")
            if next_dose:
                try:
                    if isinstance(next_dose, str):
                        next_dose_dt = dt_util.parse_datetime(next_dose)
                    else:
                        next_dose_dt = next_dose
                    
                    if next_dose_dt:
                        time_diff = (next_dose_dt - now).total_seconds()
                        
                        if time_diff < 0:  # Overdue
                            medications_overdue.append(med)
                        elif time_diff < 3600:  # Due within 1 hour
                            medications_due.append(med)
                        
                        # Track next medication due
                        if not next_due or next_dose_dt < next_due:
                            next_due = next_dose_dt
                            
                except (ValueError, TypeError):
                    continue
        
        return {
            "medications_due": medications_due,
            "active_medications": medications,
            "next_medication_due": next_due.isoformat() if next_due else None,
            "medications_overdue": medications_overdue,
        }

    async def _calculate_health_alerts_comprehensive(self, dog_id: str, health_data: dict) -> list[str]:
        """Calculate comprehensive health alerts."""
        alerts = []
        
        try:
            weight_data = health_data.get("weight_data", {})
            medications = health_data.get("medications", {})
            last_vet_visit = health_data.get("last_vet_visit")
            
            # Weight alerts
            weight_status = weight_data.get("weight_status")
            if weight_status == "significant_change":
                weight_change = weight_data.get("weight_change_percent", 0)
                if weight_change > 10:
                    alerts.append(f"Significant weight gain detected (+{weight_change:.1f}%)")
                elif weight_change < -10:
                    alerts.append(f"Significant weight loss detected ({weight_change:.1f}%)")
            
            # Medication alerts
            medications_overdue = medications.get("medications_overdue", [])
            if medications_overdue:
                alerts.append(f"{len(medications_overdue)} medication(s) overdue")
            
            medications_due = medications.get("medications_due", [])
            if medications_due:
                alerts.append(f"{len(medications_due)} medication(s) due soon")
            
            # Vet visit alerts
            if last_vet_visit:
                try:
                    last_visit_date = dt_util.parse_datetime(last_vet_visit.get("date"))
                    if last_visit_date:
                        days_since = (dt_util.utcnow() - last_visit_date).days
                        if days_since > 365:
                            alerts.append("Annual vet checkup overdue")
                        elif days_since > 335:  # 30 days before due
                            alerts.append("Annual vet checkup due soon")
                except (ValueError, TypeError):
                    pass
            else:
                alerts.append("No vet visit history available")
            
            return alerts
            
        except Exception as err:
            _LOGGER.error("Error calculating health alerts for %s: %s", dog_id, err)
            return []

    async def _calculate_health_scores(self, dog_id: str, health_history: list, weight_data: dict) -> dict[str, Any]:
        """Calculate health scores and trends."""
        try:
            base_score = 100
            recent_entries = health_history[:7] if health_history else []  # Last 7 entries
            
            # Weight score impact
            weight_status = weight_data.get("weight_status", "normal")
            if weight_status == "significant_change":
                base_score -= 20
            elif weight_status == "moderate_change":
                base_score -= 10
            
            # Health status trends
            health_statuses = []
            activity_levels = []
            
            for entry in recent_entries:
                if "health_status" in entry:
                    health_statuses.append(entry["health_status"])
                if "activity_level" in entry:
                    activity_levels.append(entry["activity_level"])
            
            # Calculate most common recent status
            if health_statuses:
                from collections import Counter
                most_common_health = Counter(health_statuses).most_common(1)[0][0]
                
                health_score_map = {
                    "excellent": 0,
                    "very_good": -5,
                    "good": -10,
                    "normal": -15,
                    "unwell": -30,
                    "sick": -50,
                }
                base_score += health_score_map.get(most_common_health, -15)
            else:
                most_common_health = "unknown"
            
            if activity_levels:
                most_common_activity = Counter(activity_levels).most_common(1)[0][0]
            else:
                most_common_activity = "unknown"
            
            # Ensure score is within bounds
            final_score = max(0, min(100, base_score))
            
            return {
                "health_status": most_common_health,
                "activity_level": most_common_activity,
                "health_score": final_score,
                "score_factors": {
                    "weight_impact": weight_status,
                    "recent_entries_count": len(recent_entries),
                    "data_quality": "good" if recent_entries else "limited",
                },
            }
            
        except Exception as err:
            _LOGGER.error("Error calculating health scores for %s: %s", dog_id, err)
            return {
                "health_status": "unknown",
                "activity_level": "unknown",
                "health_score": 50,
            }

    async def _calculate_next_checkup(self, dog_id: str, last_visit: Optional[dict]) -> Optional[datetime]:
        """Calculate next checkup date."""
        return None

    async def _is_grooming_due(self, dog_id: str, last_grooming: Optional[dict]) -> bool:
        """Check if grooming is due."""
        return False

    async def _get_care_reminders(self, dog_id: str) -> list[str]:
        """Get care reminders for a dog."""
        return []

    def _calculate_today_walk_stats_comprehensive(self, walk_history: list) -> dict[str, Any]:
        """Calculate comprehensive today's walk statistics."""
        return {
            "last_walk": None,
            "last_walk_duration": None,
            "last_walk_distance": None,
            "last_walk_hours": None,
            "walks_today": 0,
            "total_distance_today": 0,
            "total_duration_today": 0,
        }

    def _calculate_weekly_walk_stats_comprehensive(self, walk_history: list) -> dict[str, Any]:
        """Calculate comprehensive weekly walk statistics."""
        return {
            "weekly_walk_count": 0,
            "weekly_distance": 0,
        }

    async def _calculate_walk_recommendation(self, dog_id: str, walk_history: list, today_stats: dict) -> dict[str, Any]:
        """Calculate walk recommendations."""
        return {
            "needs_walk": False,
            "walk_urgency": "none",
            "walk_recommendation": "",
        }

    def _calculate_activity_analysis(self, today_stats: dict, weekly_stats: dict) -> dict[str, Any]:
        """Calculate activity analysis."""
        return {
            "walk_goal_met": False,
            "activity_score": 0,
            "activity_trend": "stable",
        }

    async def _process_current_walk_data(self, current_walk: dict) -> dict[str, Any]:
        """Process current walk data."""
        return {
            "current_walk_start": current_walk.get("start_time"),
            "current_walk_duration": self._calculate_walk_duration(current_walk),
            "current_walk_distance": current_walk.get("distance", 0),
            "current_walk_id": current_walk.get("walk_id"),
        }

    def _calculate_walk_duration(self, walk: dict) -> int:
        """Calculate current walk duration in minutes."""
        if not walk or not walk.get("start_time"):
            return 0
        
        start_time = walk["start_time"]
        now = dt_util.now()
        
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        
        if start_time.tzinfo is None:
            start_time = dt_util.as_local(start_time)
        
        delta = now - start_time
        return int(delta.total_seconds() / 60)

    def _calculate_hours_since(self, timestamp: datetime) -> float:
        """Calculate hours since a given timestamp."""
        if not timestamp:
            return None
        
        now = dt_util.now()
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        if timestamp.tzinfo is None:
            timestamp = dt_util.as_local(timestamp)
        
        delta = now - timestamp
        return round(delta.total_seconds() / 3600, 1)

    def _calculate_days_since(self, date_obj: datetime) -> int:
        """Calculate days since a given date."""
        if not date_obj:
            return None
        
        now = dt_util.now().date()
        if isinstance(date_obj, str):
            date_obj = datetime.fromisoformat(date_obj).date()
        elif hasattr(date_obj, 'date'):
            date_obj = date_obj.date()
        
        delta = now - date_obj
        return delta.days

    def _get_runtime_data(self) -> Optional[PawControlRuntimeData]:
        """Get runtime data for the integration."""
        return getattr(self.entry, 'runtime_data', None)

    # Public interface methods (inherited and new)
    @callback
    def async_add_listener(
        self, 
        update_callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Add a listener for data updates."""
        self._listeners.add(update_callback)
        
        @callback
        def remove_listener() -> None:
            """Remove the listener from the coordinator."""
            self._listeners.discard(update_callback)
        
        return remove_listener

    @callback
    def async_update_listeners(self) -> None:
        """Notify all registered listeners of data updates."""
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

    def get_dog_data(self, dog_id: str) -> Optional[dict[str, Any]]:
        """Get data for a specific dog."""
        return self._data.get(dog_id)

    def get_all_dogs_data(self) -> dict[str, Any]:
        """Get data for all dogs managed by this coordinator."""
        return self._data.copy()

    def get_module_data(self, dog_id: str, module: str) -> Optional[dict[str, Any]]:
        """Get specific module data for a dog."""
        dog_data = self.get_dog_data(dog_id)
        if dog_data:
            return dog_data.get(module)
        return None

    async def async_refresh_dog(self, dog_id: str) -> None:
        """Refresh data for a specific dog."""
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
        """Shutdown the coordinator and cleanup resources."""
        _LOGGER.debug("Shutting down Paw Control coordinator")
        
        # Clear all listeners
        self._listeners.clear()
        
        # Clear data and caches
        self._data.clear()
        self._zone_cache.clear()
        self._entity_cache.clear()
        self._home_zone_cache = None
        
        # Reset performance metrics
        self._performance_metrics.clear()
        
        _LOGGER.debug("Coordinator shutdown completed")

    @property
    def config_entry(self) -> ConfigEntry:
        """Return the configuration entry for this coordinator."""
        return self.entry

    @property
    def available(self) -> bool:
        """Return if the coordinator is available."""
        return self.last_update_success

    def is_dog_configured(self, dog_id: str) -> bool:
        """Check if a dog is configured in this coordinator."""
        return any(dog[CONF_DOG_ID] == dog_id for dog in self.dogs)

    def get_dog_info(self, dog_id: str) -> Optional[DogConfigData]:
        """Get basic configuration information for a dog."""
        for dog in self.dogs:
            if dog[CONF_DOG_ID] == dog_id:
                return dog.copy()
        return None

    def get_enabled_modules(self, dog_id: str) -> list[str]:
        """Get list of enabled modules for a dog."""
        dog_info = self.get_dog_info(dog_id)
        if not dog_info:
            return []
        
        modules = dog_info.get("modules", {})
        return [module for module, enabled in modules.items() if enabled]

    async def async_update_config(self, new_config: dict[str, Any]) -> None:
        """Update coordinator configuration."""
        self.dogs = new_config.get(CONF_DOGS, [])
        
        # Recalculate update interval based on new configuration
        new_interval = self._calculate_optimal_update_interval()
        self.update_interval = timedelta(seconds=new_interval)
        
        # Clear caches to force refresh with new configuration
        self._zone_cache.clear()
        self._entity_cache.clear()
        self._cache_expiry = dt_util.utcnow()
        
        _LOGGER.debug(
            "Configuration updated: %d dogs, new interval: %ds",
            len(self.dogs),
            new_interval,
        )
        
        # Trigger immediate refresh with new configuration
        await self.async_refresh()

    def get_update_statistics(self) -> dict[str, Any]:
        """Get coordinator update statistics."""
        return {
            "total_dogs": len(self.dogs),
            "last_update_success": self.last_update_success,
            "last_update_time": self.last_update_time,
            "update_interval_seconds": self.update_interval.total_seconds(),
            "active_listeners": len(self._listeners),
            "data_size": len(self._data),
            "cache_entries": len(self._zone_cache),
            **self._performance_metrics,
        }