"""Data coordinator for Paw Control integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_DOGS,
    EVENT_WALK_STARTED,
    EVENT_WALK_ENDED,
    EVENT_DOG_FED,
    EVENT_MEDICATION_GIVEN,
    EVENT_GROOMING_DONE,
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    DEFAULT_WALK_THRESHOLD_HOURS,
)

_LOGGER = logging.getLogger(__name__)


class PawControlCoordinator(DataUpdateCoordinator):
    """Manage fetching and updating Paw Control data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=5),
        )
        self.entry = entry
        self._dog_data: Dict[str, Dict[str, Any]] = {}
        self._visitor_mode = False
        self._emergency_mode = False
        self._emergency_level = "info"
        self._initialize_dog_data()

    def _initialize_dog_data(self) -> None:
        """Initialize data structure for each dog."""
        dogs = self.entry.options.get(CONF_DOGS, [])
        
        for dog in dogs:
            dog_id = dog.get("dog_id")
            if not dog_id:
                continue
                
            self._dog_data[dog_id] = {
                "info": {
                    "name": dog.get("name", dog_id),
                    "breed": dog.get("breed", "Unknown"),
                    "age": dog.get("age", 0),
                    "weight": dog.get("weight", 0),
                    "size": dog.get("size", "medium"),
                },
                "walk": {
                    "last_walk": None,
                    "walk_in_progress": False,
                    "walk_start_time": None,
                    "walk_duration_min": 0,
                    "walk_distance_m": 0,
                    "walks_today": 0,
                    "total_distance_today": 0,
                    "needs_walk": False,
                },
                "feeding": {
                    "last_feeding": None,
                    "last_meal_type": None,
                    "last_portion_g": 0,
                    "last_food_type": None,
                    "feedings_today": {
                        "breakfast": 0,
                        "lunch": 0,
                        "dinner": 0,
                        "snack": 0,
                    },
                    "total_portions_today": 0,
                    "is_hungry": False,
                },
                "health": {
                    "weight_kg": dog.get("weight", 0),
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
                    "calories_burned_today": 0,
                },
                "location": {
                    "current_location": "home",
                    "last_gps_update": None,
                    "is_home": True,
                    "distance_from_home": 0,
                },
                "statistics": {
                    "poop_count_today": 0,
                    "last_poop": None,
                    "last_action": None,
                    "last_action_type": None,
                }
            }

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API or calculate derived values."""
        try:
            # Update calculated fields
            for dog_id, data in self._dog_data.items():
                # Check if dog needs walk
                data["walk"]["needs_walk"] = self._calculate_needs_walk(dog_id)
                
                # Check if dog is hungry
                data["feeding"]["is_hungry"] = self._calculate_is_hungry(dog_id)
                
                # Check if grooming is needed
                data["grooming"]["needs_grooming"] = self._calculate_needs_grooming(dog_id)
                
                # Calculate activity level
                data["activity"]["activity_level"] = self._calculate_activity_level(dog_id)
                
                # Update medication due times
                data["health"]["next_medication_due"] = self._calculate_next_medication(dog_id)
                
                # Calculate calories burned
                data["activity"]["calories_burned_today"] = self._calculate_calories(dog_id)
            
            return self._dog_data
            
        except Exception as err:
            raise UpdateFailed(f"Error updating data: {err}")

    def _calculate_needs_walk(self, dog_id: str) -> bool:
        """Calculate if dog needs a walk."""
        data = self._dog_data[dog_id]["walk"]
        
        if data["walk_in_progress"]:
            return False
            
        if not data["last_walk"]:
            return True
            
        try:
            last_walk = datetime.fromisoformat(data["last_walk"])
            hours_since_walk = (dt_util.now() - last_walk).total_seconds() / 3600
            return hours_since_walk >= DEFAULT_WALK_THRESHOLD_HOURS
        except (ValueError, TypeError):
            return True

    def _calculate_is_hungry(self, dog_id: str) -> bool:
        """Calculate if dog is hungry based on feeding schedule."""
        data = self._dog_data[dog_id]["feeding"]
        current_hour = dt_util.now().hour
        
        # Basic feeding schedule
        if 6 <= current_hour < 9 and data["feedings_today"]["breakfast"] == 0:
            return True
        elif 11 <= current_hour < 14 and data["feedings_today"]["lunch"] == 0:
            return True
        elif 17 <= current_hour < 20 and data["feedings_today"]["dinner"] == 0:
            return True
            
        return False

    def _calculate_needs_grooming(self, dog_id: str) -> bool:
        """Calculate if dog needs grooming."""
        data = self._dog_data[dog_id]["grooming"]
        
        if not data["last_grooming"]:
            return True
            
        try:
            last_grooming = datetime.fromisoformat(data["last_grooming"])
            days_since = (dt_util.now() - last_grooming).days
            return days_since >= data["grooming_interval_days"]
        except (ValueError, TypeError):
            return False

    def _calculate_activity_level(self, dog_id: str) -> str:
        """Calculate activity level based on today's activities."""
        walk_data = self._dog_data[dog_id]["walk"]
        activity_data = self._dog_data[dog_id]["activity"]
        
        total_activity_min = walk_data.get("walk_duration_min", 0) + activity_data.get("play_duration_today_min", 0)
        
        if total_activity_min < 30:
            return "low"
        elif total_activity_min < 90:
            return "medium"
        else:
            return "high"

    def _calculate_next_medication(self, dog_id: str) -> Optional[datetime]:
        """Calculate next medication due time."""
        # This would be implemented based on medication schedules
        # For now, return None
        return None

    def _calculate_calories(self, dog_id: str) -> float:
        """Calculate approximate calories burned today."""
        walk_data = self._dog_data[dog_id]["walk"]
        activity_data = self._dog_data[dog_id]["activity"]
        dog_weight = self._dog_data[dog_id]["info"]["weight"]
        
        if dog_weight <= 0:
            dog_weight = 20  # Default weight
        
        # Simple calculation: ~30 kcal per km for average dog
        distance_km = walk_data.get("total_distance_today", 0) / 1000
        walk_calories = distance_km * 30 * (dog_weight / 20)
        
        # Play calories: ~5 kcal per minute for average dog
        play_calories = activity_data.get("play_duration_today_min", 0) * 5 * (dog_weight / 20)
        
        return round(walk_calories + play_calories, 1)

    def update_options(self, options: dict) -> None:
        """Update coordinator options."""
        self.entry._options = options
        self._initialize_dog_data()

    def get_dog_data(self, dog_id: str) -> Dict[str, Any]:
        """Get data for specific dog."""
        return self._dog_data.get(dog_id, {})

    async def reset_daily_counters(self) -> None:
        """Reset all daily counters."""
        _LOGGER.info("Resetting daily counters for all dogs")
        
        for dog_id in self._dog_data:
            # Reset walk counters
            self._dog_data[dog_id]["walk"]["walks_today"] = 0
            self._dog_data[dog_id]["walk"]["total_distance_today"] = 0
            
            # Reset feeding counters
            self._dog_data[dog_id]["feeding"]["feedings_today"] = {
                "breakfast": 0,
                "lunch": 0,
                "dinner": 0,
                "snack": 0,
            }
            self._dog_data[dog_id]["feeding"]["total_portions_today"] = 0
            
            # Reset health counters
            self._dog_data[dog_id]["health"]["medications_today"] = 0
            
            # Reset training counters
            self._dog_data[dog_id]["training"]["training_sessions_today"] = 0
            
            # Reset activity counters
            self._dog_data[dog_id]["activity"]["play_duration_today_min"] = 0
            self._dog_data[dog_id]["activity"]["calories_burned_today"] = 0
            
            # Reset statistics
            self._dog_data[dog_id]["statistics"]["poop_count_today"] = 0
        
        await self.async_request_refresh()

    async def start_walk(self, dog_id: str, source: str = "manual") -> None:
        """Start a walk for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return
        
        walk_data = self._dog_data[dog_id]["walk"]
        
        if walk_data["walk_in_progress"]:
            _LOGGER.warning(f"Walk already in progress for {dog_id}")
            return
        
        walk_data["walk_in_progress"] = True
        walk_data["walk_start_time"] = dt_util.now().isoformat()
        walk_data["walk_duration_min"] = 0
        walk_data["walk_distance_m"] = 0
        
        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_started"
        
        self.hass.bus.async_fire(
            EVENT_WALK_STARTED,
            {ATTR_DOG_ID: dog_id, "source": source}
        )
        
        await self.async_request_refresh()

    async def end_walk(self, dog_id: str, reason: str = "manual") -> None:
        """End a walk for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return
        
        walk_data = self._dog_data[dog_id]["walk"]
        
        if not walk_data["walk_in_progress"]:
            _LOGGER.warning(f"No walk in progress for {dog_id}")
            return
        
        # Calculate duration
        if walk_data["walk_start_time"]:
            try:
                start_time = datetime.fromisoformat(walk_data["walk_start_time"])
                duration = (dt_util.now() - start_time).total_seconds() / 60
                walk_data["walk_duration_min"] = round(duration, 1)
            except ValueError:
                walk_data["walk_duration_min"] = 0
        
        walk_data["walk_in_progress"] = False
        walk_data["last_walk"] = dt_util.now().isoformat()
        walk_data["walks_today"] += 1
        walk_data["total_distance_today"] += walk_data.get("walk_distance_m", 0)
        
        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_ended"
        
        self.hass.bus.async_fire(
            EVENT_WALK_ENDED,
            {
                ATTR_DOG_ID: dog_id,
                "reason": reason,
                "duration_min": walk_data["walk_duration_min"],
                "distance_m": walk_data["walk_distance_m"],
            }
        )
        
        await self.async_request_refresh()

    async def log_walk(self, dog_id: str, duration_min: int, distance_m: int) -> None:
        """Log a completed walk."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return
        
        walk_data = self._dog_data[dog_id]["walk"]
        
        walk_data["last_walk"] = dt_util.now().isoformat()
        walk_data["walk_duration_min"] = duration_min
        walk_data["walk_distance_m"] = distance_m
        walk_data["walks_today"] += 1
        walk_data["total_distance_today"] += distance_m
        
        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_logged"
        
        await self.async_request_refresh()

    async def feed_dog(self, dog_id: str, meal_type: str, portion_g: int, food_type: str) -> None:
        """Record feeding for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return
        
        feeding_data = self._dog_data[dog_id]["feeding"]
        
        feeding_data["last_feeding"] = dt_util.now().isoformat()
        feeding_data["last_meal_type"] = meal_type
        feeding_data["last_portion_g"] = portion_g
        feeding_data["last_food_type"] = food_type
        
        if meal_type in feeding_data["feedings_today"]:
            feeding_data["feedings_today"][meal_type] += 1
        
        feeding_data["total_portions_today"] += portion_g
        
        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "fed"
        
        self.hass.bus.async_fire(
            EVENT_DOG_FED,
            {
                ATTR_DOG_ID: dog_id,
                "meal_type": meal_type,
                "portion_g": portion_g,
                "food_type": food_type,
            }
        )
        
        await self.async_request_refresh()

    async def log_health_data(self, dog_id: str, weight_kg: Optional[float], note: str) -> None:
        """Log health data for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return
        
        health_data = self._dog_data[dog_id]["health"]
        
        if weight_kg is not None:
            health_data["weight_kg"] = weight_kg
            # Keep last 30 weight measurements for trend
            health_data["weight_trend"].append({
                "date": dt_util.now().isoformat(),
                "weight": weight_kg
            })
            if len(health_data["weight_trend"]) > 30:
                health_data["weight_trend"].pop(0)
        
        if note:
            health_data["health_notes"].append({
                "date": dt_util.now().isoformat(),
                "note": note
            })
            # Keep last 100 notes
            if len(health_data["health_notes"]) > 100:
                health_data["health_notes"].pop(0)
        
        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "health_logged"
        
        await self.async_request_refresh()

    async def log_medication(self, dog_id: str, medication_name: str, dose: str) -> None:
        """Log medication given to a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return
        
        health_data = self._dog_data[dog_id]["health"]
        
        health_data["last_medication"] = dt_util.now().isoformat()
        health_data["medication_name"] = medication_name
        health_data["medication_dose"] = dose
        health_data["medications_today"] += 1
        
        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "medication_given"
        
        self.hass.bus.async_fire(
            EVENT_MEDICATION_GIVEN,
            {
                ATTR_DOG_ID: dog_id,
                "medication": medication_name,
                "dose": dose,
            }
        )
        
        await self.async_request_refresh()

    async def start_grooming(self, dog_id: str, grooming_type: str, notes: str) -> None:
        """Log grooming session for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return
        
        grooming_data = self._dog_data[dog_id]["grooming"]
        
        grooming_data["last_grooming"] = dt_util.now().isoformat()
        grooming_data["grooming_type"] = grooming_type
        
        grooming_data["grooming_history"].append({
            "date": dt_util.now().isoformat(),
            "type": grooming_type,
            "notes": notes
        })
        
        # Keep last 50 grooming records
        if len(grooming_data["grooming_history"]) > 50:
            grooming_data["grooming_history"].pop(0)
        
        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "groomed"
        
        self.hass.bus.async_fire(
            EVENT_GROOMING_DONE,
            {
                ATTR_DOG_ID: dog_id,
                "type": grooming_type,
                "notes": notes,
            }
        )
        
        await self.async_request_refresh()

    async def log_play_session(self, dog_id: str, duration_min: int, intensity: str) -> None:
        """Log play session for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return
        
        activity_data = self._dog_data[dog_id]["activity"]
        
        activity_data["last_play"] = dt_util.now().isoformat()
        activity_data["play_duration_today_min"] += duration_min
        
        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "played"
        
        await self.async_request_refresh()

    async def log_training(self, dog_id: str, topic: str, duration_min: int, notes: str) -> None:
        """Log training session for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return
        
        training_data = self._dog_data[dog_id]["training"]
        
        training_data["last_training"] = dt_util.now().isoformat()
        training_data["last_topic"] = topic
        training_data["training_duration_min"] = duration_min
        training_data["training_sessions_today"] += 1
        
        training_data["training_history"].append({
            "date": dt_util.now().isoformat(),
            "topic": topic,
            "duration_min": duration_min,
            "notes": notes
        })
        
        # Keep last 100 training records
        if len(training_data["training_history"]) > 100:
            training_data["training_history"].pop(0)
        
        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "trained"
        
        await self.async_request_refresh()

    async def set_visitor_mode(self, enabled: bool) -> None:
        """Set visitor mode."""
        self._visitor_mode = enabled
        _LOGGER.info(f"Visitor mode {'enabled' if enabled else 'disabled'}")
        await self.async_request_refresh()

    async def activate_emergency_mode(self, level: str, note: str) -> None:
        """Activate emergency mode."""
        self._emergency_mode = True
        self._emergency_level = level
        _LOGGER.warning(f"Emergency mode activated: {level} - {note}")
        await self.async_request_refresh()

    async def generate_report(self, scope: str, target: str, format_type: str) -> None:
        """Generate activity report."""
        _LOGGER.info(f"Generating {scope} report in {format_type} format to {target}")
        # Implementation would generate and send/save report
        # This is a placeholder for the actual implementation
        pass

    async def export_health_data(self, dog_id: str, date_from: str, date_to: str, format_type: str) -> None:
        """Export health data for a dog."""
        _LOGGER.info(f"Exporting health data for {dog_id} from {date_from} to {date_to} in {format_type} format")
        # Implementation would export data to file
        # This is a placeholder for the actual implementation
        pass

    @property
    def visitor_mode(self) -> bool:
        """Return visitor mode status."""
        return self._visitor_mode

    @property
    def emergency_mode(self) -> bool:
        """Return emergency mode status."""
        return self._emergency_mode

    @property
    def emergency_level(self) -> str:
        """Return emergency level."""
        return self._emergency_level
