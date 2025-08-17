"""Specialized manager classes for dog management responsibilities.

This module provides focused managers that handle specific aspects of dog care,
reducing the complexity of the main coordinator and improving maintainability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DOGS,
    DEFAULT_DOG_WEIGHT_KG,
    DEFAULT_WALK_THRESHOLD_HOURS,
    MIN_DOG_WEIGHT_KG,
    EVENT_WALK_STARTED,
    EVENT_WALK_ENDED,
    EVENT_DOG_FED,
    ATTR_DOG_ID,
)
from .utils import validate_coordinates, calculate_distance

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from .types import DogData, CoordinatorData

_LOGGER = logging.getLogger(__name__)


class DogDataManager:
    """Manages dog data storage and initialization.
    
    Handles the core data structures for all dogs and ensures
    proper initialization and data consistency.
    """

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the dog data manager."""
        self.entry = entry
        self._dog_data: dict[str, DogData] = {}
        self._initialize_dog_data()

    def _initialize_dog_data(self) -> None:
        """Initialize data structure for each configured dog."""
        dogs = self.entry.options.get(CONF_DOGS, [])

        for dog in dogs:
            dog_id = dog.get("dog_id")
            if not dog_id:
                _LOGGER.warning("Skipping dog with missing ID: %s", dog)
                continue

            dog_weight = max(MIN_DOG_WEIGHT_KG, float(dog.get("weight", DEFAULT_DOG_WEIGHT_KG)))
            dog_age = max(0, int(dog.get("age", 0)))

            self._dog_data[dog_id] = self._create_dog_data_structure(dog, dog_weight, dog_age)

    def _create_dog_data_structure(self, dog: dict, weight: float, age: int) -> DogData:
        """Create a complete dog data structure."""
        current_time = dt_util.now().isoformat()
        
        return {
            "info": {
                "name": str(dog.get("name", dog.get("dog_id", "Unknown"))),
                "breed": str(dog.get("breed", "Unknown")),
                "age": age,
                "weight": weight,
                "size": str(dog.get("size", "medium")),
            },
            "walk": {
                "last_walk": None,
                "walk_in_progress": False,
                "walk_start_time": None,
                "walk_duration_min": 0.0,
                "walk_distance_m": 0.0,
                "walks_today": 0,
                "total_distance_today": 0.0,
                "needs_walk": False,
            },
            "safe_zone": {
                "inside": None,
                "last_ts": current_time,
                "enters": 0,
                "leaves": 0,
                "time_today_s": 0.0,
            },
            "feeding": {
                "last_feeding": None,
                "last_meal_type": None,
                "last_portion_g": 0,
                "last_food_type": None,
                "feedings_today": {"breakfast": 0, "lunch": 0, "dinner": 0, "snack": 0},
                "total_portions_today": 0,
                "is_hungry": False,
            },
            "health": {
                "weight_kg": weight,
                "weight_trend": [],
                "last_medication": None,
                "medication_name": None,
                "medication_dose": None,
                "medications_today": 0,
                "next_medication_due": None,
                "vaccine_status": {},
                "last_vet_visit": None,
                "health_notes": [],
            },
            "grooming": {
                "last_grooming": None,
                "grooming_type": None,
                "grooming_interval_days": 30,
                "needs_grooming": False,
                "grooming_history": [],
            },
            "training": {
                "last_training": None,
                "last_topic": None,
                "training_duration_min": 0,
                "training_sessions_today": 0,
                "training_history": [],
            },
            "activity": {
                "last_play": None,
                "play_duration_today_min": 0,
                "activity_level": "medium",
                "calories_burned_today": 0.0,
            },
            "location": {
                "current_location": "home",
                "last_gps_update": None,
                "is_home": True,
                "distance_from_home": 0.0,
                "enters_today": 0,
                "leaves_today": 0,
                "time_inside_today_min": 0.0,
                "last_ts": None,
                "radius_m": 0,
                "home_lat": None,
                "home_lon": None,
            },
            "statistics": {
                "poop_count_today": 0,
                "last_poop": None,
                "last_action": None,
                "last_action_type": None,
            },
        }

    def get_dog_data(self, dog_id: str) -> dict[str, Any]:
        """Get data for specific dog."""
        return self._dog_data.get(dog_id, {})

    def get_all_dog_data(self) -> CoordinatorData:
        """Get all dog data."""
        return self._dog_data

    def dog_exists(self, dog_id: str) -> bool:
        """Check if dog exists."""
        return dog_id in self._dog_data

    def get_dog_ids(self) -> list[str]:
        """Get all dog IDs."""
        return list(self._dog_data.keys())


class WalkManager:
    """Manages walk-related operations and GPS tracking.
    
    Handles walk start/end, GPS updates, distance calculations,
    and walk-related status determinations.
    """

    def __init__(self, hass: HomeAssistant, dog_data_manager: DogDataManager) -> None:
        """Initialize the walk manager."""
        self.hass = hass
        self.dog_data_manager = dog_data_manager

    def calculate_needs_walk(self, dog_id: str) -> bool:
        """Calculate if dog needs a walk."""
        if not self.dog_data_manager.dog_exists(dog_id):
            return False

        data = self.dog_data_manager.get_dog_data(dog_id)["walk"]

        # Don't recommend walk if one is already in progress
        if data["walk_in_progress"]:
            return False

        last_walk_dt = self._parse_datetime(data["last_walk"])
        if not last_walk_dt:
            return True

        hours_since_walk = (dt_util.now() - last_walk_dt).total_seconds() / 3600
        return hours_since_walk >= DEFAULT_WALK_THRESHOLD_HOURS

    async def start_walk(self, dog_id: str, source: str = "manual") -> None:
        """Start a walk for a dog."""
        if not self.dog_data_manager.dog_exists(dog_id):
            raise ValueError(f"Invalid dog_id: {dog_id}")

        data = self.dog_data_manager.get_dog_data(dog_id)
        walk_data = data["walk"]

        if walk_data.get("walk_in_progress", False):
            _LOGGER.warning("Walk already in progress for dog %s", dog_id)
            return

        current_time = dt_util.now()
        walk_data["walk_in_progress"] = True
        walk_data["walk_start_time"] = current_time.isoformat()
        walk_data["walk_duration_min"] = 0.0
        walk_data["walk_distance_m"] = 0.0

        # Update statistics
        data["statistics"]["last_action"] = current_time.isoformat()
        data["statistics"]["last_action_type"] = "walk_started"

        # Fire event
        self.hass.bus.async_fire(EVENT_WALK_STARTED, {ATTR_DOG_ID: dog_id, "source": source})
        _LOGGER.info("Started walk for dog %s (source: %s)", dog_id, source)

    async def end_walk(self, dog_id: str, reason: str = "manual") -> None:
        """End a walk for a dog."""
        if not self.dog_data_manager.dog_exists(dog_id):
            raise ValueError(f"Invalid dog_id: {dog_id}")

        data = self.dog_data_manager.get_dog_data(dog_id)
        walk_data = data["walk"]

        if not walk_data.get("walk_in_progress", False):
            _LOGGER.warning("No walk in progress for dog %s", dog_id)
            return

        current_time = dt_util.now()

        # Calculate final duration
        start_time_dt = self._parse_datetime(walk_data.get("walk_start_time"))
        if start_time_dt:
            duration_seconds = (current_time - start_time_dt).total_seconds()
            walk_data["walk_duration_min"] = round(duration_seconds / 60, 1)

        # Finalize walk state
        walk_data["walk_in_progress"] = False
        walk_data["last_walk"] = current_time.isoformat()
        walk_data["walks_today"] = walk_data.get("walks_today", 0) + 1

        # Add distance to daily total
        walk_distance = walk_data.get("walk_distance_m", 0)
        walk_data["total_distance_today"] = walk_data.get("total_distance_today", 0) + walk_distance

        # Update statistics
        data["statistics"]["last_action"] = current_time.isoformat()
        data["statistics"]["last_action_type"] = "walk_ended"

        # Fire event
        self.hass.bus.async_fire(
            EVENT_WALK_ENDED,
            {
                ATTR_DOG_ID: dog_id,
                "reason": reason,
                "duration_min": walk_data.get("walk_duration_min", 0),
                "distance_m": walk_distance,
            },
        )
        _LOGGER.info("Ended walk for dog %s: %.1f min, %.1f m", dog_id, walk_data.get("walk_duration_min", 0), walk_distance)

    def update_gps(self, dog_id: str, latitude: float, longitude: float, accuracy: float | None = None) -> None:
        """Update GPS location for a dog."""
        if not self.dog_data_manager.dog_exists(dog_id):
            raise ValueError(f"Dog not found: {dog_id}")

        if not validate_coordinates(latitude, longitude):
            raise ValueError(f"Invalid coordinates: lat={latitude}, lon={longitude}")

        data = self.dog_data_manager.get_dog_data(dog_id)
        loc = data["location"]
        current_time = dt_util.utcnow()
        
        loc["last_gps_update"] = current_time.isoformat()

        # Calculate distance and geofence status if home coordinates are available
        home_lat = loc.get("home_lat")
        home_lon = loc.get("home_lon")
        radius_m = loc.get("radius_m", 0)

        if isinstance(home_lat, (int, float)) and isinstance(home_lon, (int, float)):
            try:
                distance = calculate_distance(float(home_lat), float(home_lon), latitude, longitude)
                loc["distance_from_home"] = round(distance, 1)
                
                if radius_m and radius_m > 0:
                    inside = distance <= float(radius_m)
                    loc["is_home"] = inside
                    loc["current_location"] = "home" if inside else "away"
            except (ValueError, TypeError) as err:
                _LOGGER.warning("Failed to calculate distance for dog %s: %s", dog_id, err)

        # Update last action
        data["statistics"]["last_action"] = current_time.isoformat()
        data["statistics"]["last_action_type"] = "gps_update"

    def _parse_datetime(self, date_string: str | None) -> datetime | None:
        """Parse a datetime string safely."""
        if not date_string:
            return None

        try:
            parsed_dt = datetime.fromisoformat(date_string)
            if parsed_dt.tzinfo is None:
                parsed_dt = dt_util.as_local(parsed_dt)
            return parsed_dt
        except (ValueError, TypeError, AttributeError) as err:
            _LOGGER.debug("Failed to parse datetime '%s': %s", date_string, err)
            return None


class FeedingManager:
    """Manages feeding-related operations and calculations.
    
    Handles feeding events, hunger calculations, and meal scheduling.
    """

    def __init__(self, dog_data_manager: DogDataManager) -> None:
        """Initialize the feeding manager."""
        self.dog_data_manager = dog_data_manager

    def calculate_is_hungry(self, dog_id: str) -> bool:
        """Calculate if dog is hungry based on feeding schedule."""
        if not self.dog_data_manager.dog_exists(dog_id):
            return False

        data = self.dog_data_manager.get_dog_data(dog_id)["feeding"]
        current_hour = dt_util.now().hour

        # Check feeding schedule against current time
        is_breakfast_time = 6 <= current_hour < 9 and data["feedings_today"]["breakfast"] == 0
        is_lunch_time = 11 <= current_hour < 14 and data["feedings_today"]["lunch"] == 0
        is_dinner_time = 17 <= current_hour < 20 and data["feedings_today"]["dinner"] == 0

        return bool(is_breakfast_time or is_lunch_time or is_dinner_time)

    async def feed_dog(self, dog_id: str, meal_type: str, portion_g: int, food_type: str) -> None:
        """Record feeding for a dog."""
        if not self.dog_data_manager.dog_exists(dog_id):
            raise ValueError(f"Unknown dog: {dog_id}")

        if portion_g < 0:
            raise ValueError("Portion size must be non-negative")

        data = self.dog_data_manager.get_dog_data(dog_id)
        feeding_data = data["feeding"]
        current_time = dt_util.now()

        # Record feeding data
        feeding_data["last_feeding"] = current_time.isoformat()
        feeding_data["last_meal_type"] = meal_type
        feeding_data["last_portion_g"] = max(0, int(portion_g))
        feeding_data["last_food_type"] = food_type

        # Update daily counters
        if meal_type in feeding_data["feedings_today"]:
            feeding_data["feedings_today"][meal_type] += 1

        feeding_data["total_portions_today"] += max(0, int(portion_g))

        # Update statistics
        data["statistics"]["last_action"] = current_time.isoformat()
        data["statistics"]["last_action_type"] = "fed"

        _LOGGER.info("Fed dog %s: %s, %d g of %s", dog_id, meal_type, portion_g, food_type)


class HealthCalculator:
    """Calculates health-related metrics and status.
    
    Handles health calculations, medication scheduling,
    and grooming requirements.
    """

    async def calculate_health_metrics(self, dog_id: str, data: DogData) -> dict[str, Any]:
        """Calculate health-related metrics for a dog."""
        results = {}
        
        # Calculate next medication due
        results["next_medication_due"] = await self._calculate_next_medication(data)
        
        # Calculate grooming needs
        results["needs_grooming"] = self._calculate_needs_grooming(data)
        
        return results

    async def _calculate_next_medication(self, data: DogData) -> datetime | None:
        """Calculate next medication due time."""
        health_data = data["health"]
        last_med_str = health_data.get("last_medication")
        
        if not last_med_str:
            return None

        try:
            last_med_dt = datetime.fromisoformat(last_med_str)
            if last_med_dt.tzinfo is None:
                last_med_dt = dt_util.as_local(last_med_dt)
            
            # Default 12 hour interval
            reminder_hours = 12
            return last_med_dt + timedelta(hours=reminder_hours)
            
        except (ValueError, TypeError):
            return None

    def _calculate_needs_grooming(self, data: DogData) -> bool:
        """Calculate if dog needs grooming."""
        grooming_data = data["grooming"]
        last_grooming_str = grooming_data.get("last_grooming")
        
        if not last_grooming_str:
            return True

        try:
            last_grooming_dt = datetime.fromisoformat(last_grooming_str)
            if last_grooming_dt.tzinfo is None:
                last_grooming_dt = dt_util.as_local(last_grooming_dt)
            
            days_since = (dt_util.now() - last_grooming_dt).days
            interval_days = max(1, grooming_data.get("grooming_interval_days", 30))
            
            return days_since >= interval_days
            
        except (ValueError, TypeError):
            return True
