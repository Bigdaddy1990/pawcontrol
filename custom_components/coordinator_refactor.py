"""Refactored coordinator structure for better maintainability.

Split the monolithic coordinator into specialized components following 
the Single Responsibility Principle.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .dog_data_manager import DogDataManager
from .health_calculator import HealthCalculator
from .walk_manager import WalkManager
from .feeding_manager import FeedingManager

if TYPE_CHECKING:
    from .types import CoordinatorData, DogData

_LOGGER = logging.getLogger(__name__)


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Main coordinator orchestrating specialized dog management components.
    
    This coordinator acts as the central hub, delegating specific responsibilities
    to specialized managers while maintaining the overall data consistency.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator with specialized managers."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=5),
            always_update=False,
        )
        self.entry = entry
        
        # Initialize specialized managers
        self.dog_data_manager = DogDataManager(entry)
        self.health_calculator = HealthCalculator()
        self.walk_manager = WalkManager(hass, self.dog_data_manager)
        self.feeding_manager = FeedingManager(self.dog_data_manager)
        
        # System state
        self._visitor_mode: bool = False
        self._emergency_mode: bool = False
        self._last_update_time: datetime | None = None

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch data using specialized managers."""
        try:
            current_time = dt_util.now()
            
            # Get base dog data
            dog_data = self.dog_data_manager.get_all_dog_data()
            
            # Update calculated fields using specialized components
            await self._update_calculated_fields(dog_data)
            
            self._last_update_time = current_time
            return dog_data
            
        except Exception as err:
            _LOGGER.error("Critical error updating coordinator data: %s", err)
            raise UpdateFailed(f"Error updating data: {err}") from err

    async def _update_calculated_fields(self, dog_data: dict[str, DogData]) -> None:
        """Update calculated fields using specialized managers."""
        update_tasks = []
        
        for dog_id, data in dog_data.items():
            # Create update tasks for parallel processing
            task = self._update_dog_calculated_fields(dog_id, data)
            update_tasks.append(task)
        
        # Execute all updates in parallel
        if update_tasks:
            await asyncio.gather(*update_tasks, return_exceptions=True)

    async def _update_dog_calculated_fields(self, dog_id: str, data: DogData) -> None:
        """Update calculated fields for a single dog."""
        try:
            # Walk calculations
            data["walk"]["needs_walk"] = self.walk_manager.calculate_needs_walk(dog_id)
            
            # Feeding calculations  
            data["feeding"]["is_hungry"] = self.feeding_manager.calculate_is_hungry(dog_id)
            
            # Health calculations
            health_results = await self.health_calculator.calculate_health_metrics(dog_id, data)
            data["health"].update(health_results)
            
            # Activity calculations
            activity_level = self._calculate_activity_level(data)
            data["activity"]["activity_level"] = activity_level
            
            calories = self._calculate_calories(data)
            data["activity"]["calories_burned_today"] = calories
            
        except Exception as err:
            _LOGGER.error("Failed to update calculated fields for dog %s: %s", dog_id, err)

    def _calculate_activity_level(self, data: DogData) -> str:
        """Calculate activity level - keep simple calculations in coordinator."""
        walk_duration = data["walk"].get("walk_duration_min", 0)
        play_duration = data["activity"].get("play_duration_today_min", 0)
        
        total_activity = walk_duration + play_duration
        
        if total_activity < 30:
            return "low"
        elif total_activity < 90:
            return "medium"
        else:
            return "high"

    def _calculate_calories(self, data: DogData) -> float:
        """Calculate calories burned - delegate to health calculator if more complex."""
        # Simple calculation here, or delegate to health_calculator for complex logic
        weight = data["info"]["weight"]
        distance_km = data["walk"].get("total_distance_today", 0) / 1000
        play_min = data["activity"].get("play_duration_today_min", 0)
        
        walk_calories = distance_km * weight * 1.5  # Simple formula
        play_calories = play_min * weight * 0.25
        
        return round(walk_calories + play_calories, 1)

    # Delegate specific operations to managers
    async def start_walk(self, dog_id: str, source: str = "manual") -> None:
        """Start walk - delegate to walk manager."""
        await self.walk_manager.start_walk(dog_id, source)
        await self.async_request_refresh()

    async def end_walk(self, dog_id: str, reason: str = "manual") -> None:
        """End walk - delegate to walk manager."""
        await self.walk_manager.end_walk(dog_id, reason)
        await self.async_request_refresh()

    async def feed_dog(self, dog_id: str, meal_type: str, portion_g: int, food_type: str) -> None:
        """Feed dog - delegate to feeding manager."""
        await self.feeding_manager.feed_dog(dog_id, meal_type, portion_g, food_type)
        await self.async_request_refresh()

    def update_gps(self, dog_id: str, latitude: float, longitude: float, accuracy: float | None = None) -> None:
        """Update GPS - delegate to walk manager."""
        self.walk_manager.update_gps(dog_id, latitude, longitude, accuracy)
        self.async_update_listeners()

    def get_dog_data(self, dog_id: str) -> dict[str, Any]:
        """Get dog data from data manager."""
        return self.dog_data_manager.get_dog_data(dog_id)

    @property
    def visitor_mode(self) -> bool:
        """Return visitor mode status."""
        return self._visitor_mode

    @property
    def emergency_mode(self) -> bool:
        """Return emergency mode status."""
        return self._emergency_mode
