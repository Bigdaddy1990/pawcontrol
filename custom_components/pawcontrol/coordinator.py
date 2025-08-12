"""Data coordinator for Paw Control integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Mapping

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
    DEFAULT_WALK_THRESHOLD_HOURS,
)

_LOGGER = logging.getLogger(__name__)


class PawControlCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
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
        self._visitor_mode: bool = False
        self._emergency_mode: bool = False
        self._emergency_level: str = "info"
        self._lock = hass.helpers.asyncio.async_get_lock(f"{DOMAIN}_{entry.entry_id}")
        self._initialize_dog_data()

    def _initialize_dog_data(self) -> None:
        """Initialize data structure for each dog."""
        dogs = self.entry.options.get(CONF_DOGS, [])

        for dog in dogs:
            dog_id = dog.get("dog_id")
            if not dog_id:
                continue

            # Validate and sanitize dog data
            dog_name = str(dog.get("name", dog_id))
            dog_breed = str(dog.get("breed", "Unknown"))
            dog_age = max(0, float(dog.get("age", 0)))
            dog_weight = max(0.1, float(dog.get("weight", 20)))
            dog_size = str(dog.get("size", "medium"))

            self._dog_data[dog_id] = {
                "info": {
                    "name": dog_name,
                    "breed": dog_breed,
                    "age": dog_age,
                    "weight": dog_weight,
                    "size": dog_size,
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
                    "weight_kg": dog_weight,
                    "weight_trend": [],
                    "last_medication": None,
                    "medication_name": None,
                    "medication_dose": None,
                    "medications_today": 0,
                    "next_medication_due": None,
                    "vaccine_status": {},
                    "last_vet_visit": None,
                    "health_notes": [],
                    "temperature_c": None,
                    "heart_rate_bpm": None,
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
                    "latitude": None,
                    "longitude": None,
                    "accuracy": None,
                },
                "statistics": {
                    "poop_count_today": 0,
                    "last_poop": None,
                    "last_action": None,
                    "last_action_type": None,
                },
            }

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API or calculate derived values."""
        async with self._lock:
            try:
                # Update calculated fields for each dog
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
                raise UpdateFailed(f"Error updating data: {err}") from err

    def _parse_datetime(self, date_string: str | None) -> datetime | None:
        """Parse a datetime string safely with timezone awareness."""
        if not date_string:
            return None

        try:
            # Handle various datetime formats
            if isinstance(date_string, str):
                # Remove timezone suffix if present
                cleaned = date_string.replace("Z", "+00:00")
                parsed_dt = datetime.fromisoformat(cleaned)
                
                # Ensure timezone awareness
                if parsed_dt.tzinfo is None:
                    parsed_dt = dt_util.as_local(parsed_dt)
                
                return parsed_dt
        except (ValueError, TypeError, AttributeError) as exc:
            _LOGGER.debug("Failed to parse datetime '%s': %s", date_string, exc)
            return None

    def _calculate_needs_walk(self, dog_id: str) -> bool:
        """Calculate if dog needs a walk."""
        try:
            data = self._dog_data[dog_id]["walk"]

            if data["walk_in_progress"]:
                return False

            last_walk_dt = self._parse_datetime(data["last_walk"])
            if not last_walk_dt:
                return True

            hours_since_walk = (dt_util.now() - last_walk_dt).total_seconds() / 3600
            return hours_since_walk >= DEFAULT_WALK_THRESHOLD_HOURS
        except (KeyError, TypeError, AttributeError):
            return True  # Default to needing walk if calculation fails

    def _calculate_is_hungry(self, dog_id: str) -> bool:
        """Calculate if dog is hungry based on feeding schedule."""
        try:
            data = self._dog_data[dog_id]["feeding"]
            current_hour = dt_util.now().hour

            # Basic feeding schedule with safe defaults
            feedings_today = data.get("feedings_today", {})
            
            # Morning hunger (6-9 AM)
            if 6 <= current_hour < 9 and feedings_today.get("breakfast", 0) == 0:
                return True
            # Lunch hunger (11 AM - 2 PM)
            elif 11 <= current_hour < 14 and feedings_today.get("lunch", 0) == 0:
                return True
            # Dinner hunger (5-8 PM)
            elif 17 <= current_hour < 20 and feedings_today.get("dinner", 0) == 0:
                return True

            return False
        except (KeyError, TypeError, AttributeError):
            return False  # Default to not hungry if calculation fails

    def _calculate_needs_grooming(self, dog_id: str) -> bool:
        """Calculate if dog needs grooming."""
        try:
            data = self._dog_data[dog_id]["grooming"]

            last_grooming_dt = self._parse_datetime(data["last_grooming"])
            if not last_grooming_dt:
                return True

            days_since = (dt_util.now() - last_grooming_dt).days
            interval_days = data.get("grooming_interval_days", 30)
            return days_since >= interval_days
        except (KeyError, TypeError, AttributeError):
            return True  # Default to needing grooming if calculation fails

    def _calculate_activity_level(self, dog_id: str) -> str:
        """Calculate activity level based on today's activities."""
        try:
            walk_data = self._dog_data[dog_id]["walk"]
            activity_data = self._dog_data[dog_id]["activity"]

            walk_duration = float(walk_data.get("walk_duration_min", 0))
            play_duration = float(activity_data.get("play_duration_today_min", 0))
            total_activity_min = walk_duration + play_duration

            if total_activity_min < 30:
                return "low"
            elif total_activity_min < 90:
                return "medium"
            else:
                return "high"
        except (KeyError, TypeError, ValueError, AttributeError):
            return "medium"  # Safe default

    def _calculate_next_medication(self, dog_id: str) -> datetime | None:
        """Calculate next medication due time."""
        try:
            # This would be implemented based on medication schedules
            # For now, return None as placeholder
            return None
        except (KeyError, TypeError, AttributeError):
            return None

    def _calculate_calories(self, dog_id: str) -> float:
        """Calculate approximate calories burned today."""
        try:
            walk_data = self._dog_data[dog_id]["walk"]
            activity_data = self._dog_data[dog_id]["activity"]
            dog_weight = float(self._dog_data[dog_id]["info"]["weight"])

            if dog_weight <= 0:
                dog_weight = 20.0  # Default weight

            # Simple calculation: ~30 kcal per km for average dog
            distance_m = float(walk_data.get("total_distance_today", 0))
            distance_km = distance_m / 1000.0
            walk_calories = distance_km * 30.0 * (dog_weight / 20.0)

            # Play calories: ~5 kcal per minute for average dog  
            play_minutes = float(activity_data.get("play_duration_today_min", 0))
            play_calories = play_minutes * 5.0 * (dog_weight / 20.0)

            return round(walk_calories + play_calories, 1)
        except (KeyError, TypeError, ValueError, AttributeError):
            return 0.0  # Safe default

    def update_options(self, options: dict[str, Any] | Mapping[str, Any]) -> None:
        """Update coordinator options."""
        # Make a shallow copy to detach from the source mapping
        if hasattr(self.entry, '_options'):
            self.entry._options = dict(options)
        self._initialize_dog_data()

    def get_dog_data(self, dog_id: str) -> Dict[str, Any]:
        """Get data for specific dog."""
        return self._dog_data.get(dog_id, {})

    def get_all_dog_ids(self) -> List[str]:
        """Get list of all configured dog IDs."""
        return list(self._dog_data.keys())

    async def reset_daily_counters(self) -> None:
        """Reset all daily counters."""
        async with self._lock:
            _LOGGER.info("Resetting daily counters for all dogs")

            for dog_id in self._dog_data:
                try:
                    # Reset walk counters
                    self._dog_data[dog_id]["walk"]["walks_today"] = 0
                    self._dog_data[dog_id]["walk"]["total_distance_today"] = 0.0

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
                    self._dog_data[dog_id]["activity"]["calories_burned_today"] = 0.0

                    # Reset statistics
                    self._dog_data[dog_id]["statistics"]["poop_count_today"] = 0

                except Exception as exc:
                    _LOGGER.warning("Failed to reset counters for dog %s: %s", dog_id, exc)

            await self.async_request_refresh()

    async def start_walk(self, dog_id: str, source: str = "manual") -> None:
        """Start a walk for a dog."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            walk_data = self._dog_data[dog_id]["walk"]

            if walk_data["walk_in_progress"]:
                _LOGGER.warning("Walk already in progress for %s", dog_id)
                return

            walk_data["walk_in_progress"] = True
            walk_data["walk_start_time"] = dt_util.now().isoformat()
            walk_data["walk_duration_min"] = 0.0
            walk_data["walk_distance_m"] = 0.0

            self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_started"

            self.hass.bus.async_fire(
                EVENT_WALK_STARTED, {ATTR_DOG_ID: dog_id, "source": source}
            )

            await self.async_request_refresh()

    async def end_walk(self, dog_id: str, reason: str = "manual") -> None:
        """End a walk for a dog."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            walk_data = self._dog_data[dog_id]["walk"]

            if not walk_data["walk_in_progress"]:
                _LOGGER.warning("No walk in progress for %s", dog_id)
                return

            # Calculate duration
            start_time_dt = self._parse_datetime(walk_data["walk_start_time"])
            if start_time_dt:
                duration = (dt_util.now() - start_time_dt).total_seconds() / 60
                walk_data["walk_duration_min"] = round(duration, 1)

            walk_data["walk_in_progress"] = False
            walk_data["last_walk"] = dt_util.now().isoformat()
            walk_data["walks_today"] = walk_data.get("walks_today", 0) + 1
            walk_data["total_distance_today"] = (
                walk_data.get("total_distance_today", 0.0) + 
                walk_data.get("walk_distance_m", 0.0)
            )

            self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_ended"

            self.hass.bus.async_fire(
                EVENT_WALK_ENDED,
                {
                    ATTR_DOG_ID: dog_id,
                    "reason": reason,
                    "duration_min": walk_data["walk_duration_min"],
                    "distance_m": walk_data["walk_distance_m"],
                },
            )

            await self.async_request_refresh()

    async def log_walk(self, dog_id: str, duration_min: float, distance_m: float) -> None:
        """Log a completed walk."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            walk_data = self._dog_data[dog_id]["walk"]

            walk_data["last_walk"] = dt_util.now().isoformat()
            walk_data["walk_duration_min"] = float(duration_min)
            walk_data["walk_distance_m"] = float(distance_m)
            walk_data["walks_today"] = walk_data.get("walks_today", 0) + 1
            walk_data["total_distance_today"] = (
                walk_data.get("total_distance_today", 0.0) + float(distance_m)
            )

            self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_logged"

            await self.async_request_refresh()

    async def feed_dog(
        self, dog_id: str, meal_type: str, portion_g: int, food_type: str
    ) -> None:
        """Record feeding for a dog."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            feeding_data = self._dog_data[dog_id]["feeding"]

            feeding_data["last_feeding"] = dt_util.now().isoformat()
            feeding_data["last_meal_type"] = str(meal_type)
            feeding_data["last_portion_g"] = max(0, int(portion_g))
            feeding_data["last_food_type"] = str(food_type)

            if meal_type in feeding_data["feedings_today"]:
                feeding_data["feedings_today"][meal_type] += 1

            feeding_data["total_portions_today"] = (
                feeding_data.get("total_portions_today", 0) + max(0, int(portion_g))
            )

            self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "fed"

            self.hass.bus.async_fire(
                EVENT_DOG_FED,
                {
                    ATTR_DOG_ID: dog_id,
                    "meal_type": meal_type,
                    "portion_g": portion_g,
                    "food_type": food_type,
                },
            )

            await self.async_request_refresh()

    async def log_health_data(
        self, dog_id: str, weight_kg: Optional[float], note: str
    ) -> None:
        """Log health data for a dog."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            health_data = self._dog_data[dog_id]["health"]

            if weight_kg is not None and weight_kg > 0:
                health_data["weight_kg"] = float(weight_kg)
                # Keep last 30 weight measurements for trend
                health_data["weight_trend"].append(
                    {"date": dt_util.now().isoformat(), "weight": float(weight_kg)}
                )
                # Enforce strict limit to prevent memory leaks
                while len(health_data["weight_trend"]) > 30:
                    health_data["weight_trend"].pop(0)

            if note and note.strip():
                health_data["health_notes"].append(
                    {"date": dt_util.now().isoformat(), "note": str(note.strip())}
                )
                # Keep last 100 notes - enforce strict limit
                while len(health_data["health_notes"]) > 100:
                    health_data["health_notes"].pop(0)

            self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "health_logged"

            await self.async_request_refresh()

    async def log_medication(
        self, dog_id: str, medication_name: str, dose: str
    ) -> None:
        """Log medication given to a dog."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            health_data = self._dog_data[dog_id]["health"]

            health_data["last_medication"] = dt_util.now().isoformat()
            health_data["medication_name"] = str(medication_name)
            health_data["medication_dose"] = str(dose)
            health_data["medications_today"] = health_data.get("medications_today", 0) + 1

            self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "medication_given"

            self.hass.bus.async_fire(
                EVENT_MEDICATION_GIVEN,
                {
                    ATTR_DOG_ID: dog_id,
                    "medication": medication_name,
                    "dose": dose,
                },
            )

            await self.async_request_refresh()

    async def start_grooming(self, dog_id: str, grooming_type: str, notes: str) -> None:
        """Log grooming session for a dog."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            grooming_data = self._dog_data[dog_id]["grooming"]

            grooming_data["last_grooming"] = dt_util.now().isoformat()
            grooming_data["grooming_type"] = str(grooming_type)

            grooming_data["grooming_history"].append(
                {
                    "date": dt_util.now().isoformat(), 
                    "type": str(grooming_type), 
                    "notes": str(notes)
                }
            )

            # Keep last 50 grooming records - enforce strict limit
            while len(grooming_data["grooming_history"]) > 50:
                grooming_data["grooming_history"].pop(0)

            self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "groomed"

            self.hass.bus.async_fire(
                EVENT_GROOMING_DONE,
                {
                    ATTR_DOG_ID: dog_id,
                    "type": grooming_type,
                    "notes": notes,
                },
            )

            await self.async_request_refresh()

    async def log_play_session(
        self, dog_id: str, duration_min: int, intensity: str
    ) -> None:
        """Log play session for a dog."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            activity_data = self._dog_data[dog_id]["activity"]

            activity_data["last_play"] = dt_util.now().isoformat()
            activity_data["play_duration_today_min"] = (
                activity_data.get("play_duration_today_min", 0) + max(0, int(duration_min))
            )

            self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "played"

            await self.async_request_refresh()

    async def log_training(
        self, dog_id: str, topic: str, duration_min: int, notes: str
    ) -> None:
        """Log training session for a dog."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            training_data = self._dog_data[dog_id]["training"]

            training_data["last_training"] = dt_util.now().isoformat()
            training_data["last_topic"] = str(topic)
            training_data["training_duration_min"] = max(0, int(duration_min))
            training_data["training_sessions_today"] = (
                training_data.get("training_sessions_today", 0) + 1
            )

            training_data["training_history"].append(
                {
                    "date": dt_util.now().isoformat(),
                    "topic": str(topic),
                    "duration_min": max(0, int(duration_min)),
                    "notes": str(notes),
                }
            )

            # Keep last 100 training records - enforce strict limit
            while len(training_data["training_history"]) > 100:
                training_data["training_history"].pop(0)

            self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "trained"

            await self.async_request_refresh()

    async def log_poop(self, dog_id: str) -> None:
        """Log poop event for a dog."""
        async with self._lock:
            if dog_id not in self._dog_data:
                _LOGGER.error("Dog %s not found", dog_id)
                return

            stats_data = self._dog_data[dog_id]["statistics"]
            stats_data["poop_count_today"] = stats_data.get("poop_count_today", 0) + 1
            stats_data["last_poop"] = dt_util.now().isoformat()
            stats_data["last_action"] = dt_util.now().isoformat()
            stats_data["last_action_type"] = "poop_logged"

            await self.async_request_refresh()

    async def set_visitor_mode(self, enabled: bool) -> None:
        """Set visitor mode."""
        async with self._lock:
            self._visitor_mode = bool(enabled)
            _LOGGER.info("Visitor mode %s", "enabled" if enabled else "disabled")
            await self.async_request_refresh()

    async def activate_emergency_mode(self, level: str, note: str) -> None:
        """Activate emergency mode."""
        async with self._lock:
            self._emergency_mode = True
            self._emergency_level = str(level)
            _LOGGER.warning("Emergency mode activated: %s - %s", level, note)
            await self.async_request_refresh()

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
