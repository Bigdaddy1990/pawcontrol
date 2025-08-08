"""Data coordinator for PawControl integration."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    CONF_DOG_BREED,
    CONF_DOG_AGE,
    CONF_DOG_WEIGHT,
    CONF_DOG_SIZE,
    CONF_MODULES,
    DEFAULT_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class PawControlCoordinator(DataUpdateCoordinator):
    """Coordinate data updates for a specific dog."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        dog_config: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        self.dog_config = dog_config
        self.dog_name = dog_config.get(CONF_DOG_NAME, "Unknown")
        self.entry = entry
        
        # Initialize data structure
        self._data: dict[str, Any] = {
            "profile": {
                "name": self.dog_name,
                "breed": dog_config.get(CONF_DOG_BREED, ""),
                "age": dog_config.get(CONF_DOG_AGE, 0),
                "weight": dog_config.get(CONF_DOG_WEIGHT, 0),
                "size": dog_config.get(CONF_DOG_SIZE, "Mittel"),
                "health_status": dog_config.get("health_status", "Gut"),
                "mood": dog_config.get("mood", "😊 Fröhlich"),
                "activity_level": dog_config.get("activity_level", "Normal"),
            },
            "status": {
                "last_feeding": None,
                "last_walk": None,
                "last_medication": None,
                "last_grooming": None,
                "last_training": None,
                "last_vet_visit": None,
                "is_hungry": False,
                "needs_walk": False,
                "needs_attention": False,
                "is_outside": False,
                "is_sleeping": False,
                "emergency_mode": False,
                "visitor_mode": False,
            },
            "health": {
                "temperature": 38.5,
                "heart_rate": 80,
                "respiratory_rate": 20,
                "weight_history": [],
                "medication_schedule": [],
                "symptoms": [],
                "vet_appointments": [],
            },
            "activity": {
                "daily_walks": 0,
                "daily_meals": 0,
                "daily_playtime": 0,
                "daily_training": 0,
                "walk_distance_today": 0,
                "calories_burned": 0,
                "activity_score": 0,
            },
            "location": {
                "current": None,
                "last_update": None,
                "is_home": True,
                "distance_from_home": 0,
                "gps_signal": 0,
                "route": [],
            },
            "feeding": {
                "breakfast_time": "07:00",
                "lunch_time": "12:00",
                "dinner_time": "18:00",
                "daily_amount": 500,
                "food_type": "Trockenfutter",
                "water_level": 100,
                "last_fed": None,
                "meals_today": 0,
            },
            "statistics": {
                "total_walks": 0,
                "total_meals": 0,
                "total_distance": 0,
                "average_walk_duration": 0,
                "favorite_walk_time": None,
                "health_score": 100,
                "happiness_score": 100,
            },
            "modules": dog_config.get(CONF_MODULES, {}),
        }
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"PawControl - {self.dog_name}",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from all sources."""
        try:
            # Update current time
            now = dt_util.now()
            
            # Check feeding status
            await self._update_feeding_status(now)
            
            # Check walk status
            await self._update_walk_status(now)
            
            # Check health status
            await self._update_health_status()
            
            # Check activity status
            await self._update_activity_status()
            
            # Check location if GPS enabled
            if self._data["modules"].get("gps", {}).get("enabled", False):
                await self._update_location_status()
            
            # Calculate scores
            self._calculate_scores()
            
            # Update last update time
            self._data["last_update"] = now.isoformat()
            
            return self._data
            
        except Exception as err:
            _LOGGER.error(f"Error updating data for {self.dog_name}: {err}")
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def _update_feeding_status(self, now: datetime) -> None:
        """Update feeding-related status."""
        feeding_data = self._data["feeding"]
        status = self._data["status"]
        
        # Check if it's feeding time
        current_time = now.strftime("%H:%M")
        
        # Check last feeding time
        if feeding_data["last_fed"]:
            try:
                last_fed = datetime.fromisoformat(feeding_data["last_fed"])
                hours_since = (now - last_fed).total_seconds() / 3600
                
                # Dog is likely hungry if more than 6 hours since last feeding
                status["is_hungry"] = hours_since > 6
            except (ValueError, TypeError):
                pass
        else:
            # No feeding recorded yet
            status["is_hungry"] = True

    async def _update_walk_status(self, now: datetime) -> None:
        """Update walk-related status."""
        status = self._data["status"]
        activity = self._data["activity"]
        
        # Check last walk time
        if status["last_walk"]:
            try:
                last_walk = datetime.fromisoformat(status["last_walk"])
                hours_since = (now - last_walk).total_seconds() / 3600
                
                # Dog needs walk if more than 8 hours since last walk
                status["needs_walk"] = hours_since > 8
                
                # Reset daily counters if new day
                if last_walk.date() != now.date():
                    activity["daily_walks"] = 0
                    activity["walk_distance_today"] = 0
            except (ValueError, TypeError):
                pass
        else:
            # No walk recorded yet
            status["needs_walk"] = True

    async def _update_health_status(self) -> None:
        """Update health-related status."""
        health = self._data["health"]
        profile = self._data["profile"]
        
        # Check if temperature is normal
        if health["temperature"] < 37.5 or health["temperature"] > 39.5:
            profile["health_status"] = "Unwohl"
        
        # Check heart rate
        expected_hr = self._get_expected_heart_rate()
        if abs(health["heart_rate"] - expected_hr) > 20:
            if profile["health_status"] == "Gut":
                profile["health_status"] = "Normal"

    async def _update_activity_status(self) -> None:
        """Update activity-related status."""
        activity = self._data["activity"]
        profile = self._data["profile"]
        
        # Calculate activity score based on daily activities
        walk_score = min(activity["daily_walks"] * 25, 50)  # Max 50 points
        play_score = min(activity["daily_playtime"] / 30 * 25, 25)  # Max 25 points
        training_score = min(activity["daily_training"] / 15 * 25, 25)  # Max 25 points
        
        activity["activity_score"] = walk_score + play_score + training_score

    async def _update_location_status(self) -> None:
        """Update GPS location status."""
        location = self._data["location"]
        
        # This would integrate with actual GPS tracking
        # For now, just maintain the structure
        if not location["current"]:
            location["current"] = {"latitude": 0.0, "longitude": 0.0}
            location["last_update"] = dt_util.now().isoformat()

    def _calculate_scores(self) -> None:
        """Calculate health and happiness scores."""
        stats = self._data["statistics"]
        profile = self._data["profile"]
        activity = self._data["activity"]
        
        # Health score calculation
        health_score = 100
        
        # Deduct for health status
        health_status_scores = {
            "Ausgezeichnet": 100,
            "Sehr gut": 95,
            "Gut": 90,
            "Normal": 80,
            "Unwohl": 60,
            "Krank": 40,
        }
        health_score = health_status_scores.get(profile["health_status"], 80)
        
        stats["health_score"] = health_score
        
        # Happiness score calculation
        happiness_score = 100
        
        # Factor in mood
        mood_scores = {
            "😊 Fröhlich": 100,
            "😐 Neutral": 80,
            "😟 Traurig": 60,
            "😠 Ärgerlich": 50,
            "😰 Ängstlich": 40,
            "😴 Müde": 70,
        }
        mood_score = mood_scores.get(profile["mood"], 80)
        
        # Factor in activity
        activity_factor = activity["activity_score"]
        
        happiness_score = (mood_score * 0.6 + activity_factor * 0.4)
        stats["happiness_score"] = happiness_score

    def _get_expected_heart_rate(self) -> int:
        """Get expected heart rate based on size."""
        size = self._data["profile"]["size"]
        
        # Heart rate ranges by size
        hr_by_size = {
            "Toy": 100,
            "Klein": 90,
            "Mittel": 80,
            "Groß": 70,
            "Riesig": 60,
        }
        
        return hr_by_size.get(size, 80)

    async def async_update_feeding(self, meal_type: str, amount: float | None = None) -> None:
        """Update feeding information."""
        now = dt_util.now()
        self._data["feeding"]["last_fed"] = now.isoformat()
        self._data["feeding"]["meals_today"] += 1
        self._data["status"]["last_feeding"] = now.isoformat()
        self._data["status"]["is_hungry"] = False
        self._data["activity"]["daily_meals"] += 1
        self._data["statistics"]["total_meals"] += 1
        
        if amount:
            self._data["feeding"]["daily_amount"] -= amount
        
        # Trigger coordinator update
        await self.async_request_refresh()

    async def async_update_walk(
        self,
        duration: int,
        distance: float | None = None,
        route: list | None = None,
    ) -> None:
        """Update walk information."""
        now = dt_util.now()
        self._data["status"]["last_walk"] = now.isoformat()
        self._data["status"]["needs_walk"] = False
        self._data["activity"]["daily_walks"] += 1
        self._data["statistics"]["total_walks"] += 1
        
        if distance:
            self._data["activity"]["walk_distance_today"] += distance
            self._data["statistics"]["total_distance"] += distance
        
        if route:
            self._data["location"]["route"] = route
        
        # Calculate calories burned (rough estimate)
        weight = self._data["profile"]["weight"]
        calories = (duration / 60) * weight * 3.5  # Simplified formula
        self._data["activity"]["calories_burned"] += calories
        
        # Update average walk duration
        total_walks = self._data["statistics"]["total_walks"]
        avg_duration = self._data["statistics"]["average_walk_duration"]
        new_avg = ((avg_duration * (total_walks - 1)) + duration) / total_walks
        self._data["statistics"]["average_walk_duration"] = new_avg
        
        # Trigger coordinator update
        await self.async_request_refresh()

    async def async_update_health(
        self,
        temperature: float | None = None,
        weight: float | None = None,
        symptoms: list | None = None,
    ) -> None:
        """Update health information."""
        if temperature is not None:
            self._data["health"]["temperature"] = temperature
        
        if weight is not None:
            self._data["profile"]["weight"] = weight
            # Add to weight history
            self._data["health"]["weight_history"].append({
                "date": dt_util.now().isoformat(),
                "weight": weight,
            })
            # Keep only last 30 entries
            self._data["health"]["weight_history"] = self._data["health"]["weight_history"][-30:]
        
        if symptoms:
            self._data["health"]["symptoms"] = symptoms
        
        # Trigger coordinator update
        await self.async_request_refresh()

    async def async_update_location(
        self,
        latitude: float,
        longitude: float,
        accuracy: float | None = None,
    ) -> None:
        """Update GPS location."""
        now = dt_util.now()
        self._data["location"]["current"] = {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
        }
        self._data["location"]["last_update"] = now.isoformat()
        
        # Calculate distance from home (would need home coordinates)
        # For now, just set as example
        self._data["location"]["is_home"] = accuracy and accuracy < 50
        
        # Trigger coordinator update
        await self.async_request_refresh()

    async def async_set_emergency(self, active: bool, reason: str | None = None) -> None:
        """Set emergency mode."""
        self._data["status"]["emergency_mode"] = active
        if reason:
            self._data["status"]["emergency_reason"] = reason
        
        # Trigger coordinator update
        await self.async_request_refresh()

    async def async_set_visitor_mode(
        self,
        active: bool,
        visitor_name: str | None = None,
        instructions: str | None = None,
    ) -> None:
        """Set visitor mode."""
        self._data["status"]["visitor_mode"] = active
        if visitor_name:
            self._data["status"]["visitor_name"] = visitor_name
        if instructions:
            self._data["status"]["visitor_instructions"] = instructions
        
        # Trigger coordinator update
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        # Clean up any resources
        _LOGGER.info(f"Shutting down coordinator for {self.dog_name}")
