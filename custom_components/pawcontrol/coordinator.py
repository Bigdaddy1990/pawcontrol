"""Data coordinator for Paw Control integration."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    CONF_DOGS,
    DEFAULT_WALK_THRESHOLD_HOURS,
    DOMAIN,
    EVENT_DOG_FED,
    EVENT_GROOMING_DONE,
    EVENT_MEDICATION_GIVEN,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
)

_LOGGER = logging.getLogger(__name__)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the Haversine distance between two points in meters."""
    R = 6371000  # Earth's radius in meters

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Haversine formula
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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
        self._dog_data: dict[str, dict[str, Any]] = {}
        self._visitor_mode: bool = False
        self._emergency_mode: bool = False
        self._emergency_level: str = "info"
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
                "safe_zone": {
                    "inside": None,
                    "last_ts": dt_util.now().isoformat(),
                    "enters": 0,
                    "leaves": 0,
                    "time_today_s": 0.0,
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API or calculate derived values."""
        try:
            # Update calculated fields
            for dog_id, data in self._dog_data.items():
                # Check if dog needs walk
                data["walk"]["needs_walk"] = self._calculate_needs_walk(dog_id)

                # Check if dog is hungry
                data["feeding"]["is_hungry"] = self._calculate_is_hungry(dog_id)

                # Check if grooming is needed
                data["grooming"]["needs_grooming"] = self._calculate_needs_grooming(
                    dog_id
                )

                # Calculate activity level
                data["activity"]["activity_level"] = self._calculate_activity_level(
                    dog_id
                )

                # Update medication due times
                data["health"]["next_medication_due"] = self._calculate_next_medication(
                    dog_id
                )

                # Calculate calories burned
                data["activity"]["calories_burned_today"] = self._calculate_calories(
                    dog_id
                )

            return self._dog_data

        except Exception as err:
            raise UpdateFailed(f"Error updating data: {err}") from err

    def _parse_datetime(self, date_string: str | None) -> datetime | None:
        """Parse a datetime string safely with timezone awareness."""
        if not date_string:
            return None

        try:
            # Try to parse ISO format
            parsed_dt = datetime.fromisoformat(date_string)

            # Ensure timezone awareness
            if parsed_dt.tzinfo is None:
                parsed_dt = dt_util.as_local(parsed_dt)

            return parsed_dt
        except (ValueError, TypeError, AttributeError):
            _LOGGER.debug(f"Failed to parse datetime: {date_string}")
            return None

    def _calculate_needs_walk(self, dog_id: str) -> bool:
        """Calculate if dog needs a walk."""
        data = self._dog_data[dog_id]["walk"]

        if data["walk_in_progress"]:
            return False

        last_walk_dt = self._parse_datetime(data["last_walk"])
        if not last_walk_dt:
            return True

        hours_since_walk = (dt_util.now() - last_walk_dt).total_seconds() / 3600
        return hours_since_walk >= DEFAULT_WALK_THRESHOLD_HOURS

    def _calculate_is_hungry(self, dog_id: str) -> bool:
        """Calculate if dog is hungry based on feeding schedule."""
        data = self._dog_data[dog_id]["feeding"]
        current_hour = dt_util.now().hour

        # Basic feeding schedule
        return bool(6 <= current_hour < 9 and data["feedings_today"]["breakfast"] == 0 or 11 <= current_hour < 14 and data["feedings_today"]["lunch"] == 0 or 17 <= current_hour < 20 and data["feedings_today"]["dinner"] == 0)

    def _calculate_needs_grooming(self, dog_id: str) -> bool:
        """Calculate if dog needs grooming."""
        data = self._dog_data[dog_id]["grooming"]

        last_grooming_dt = self._parse_datetime(data["last_grooming"])
        if not last_grooming_dt:
            return True

        days_since = (dt_util.now() - last_grooming_dt).days
        return days_since >= data["grooming_interval_days"]

    def _calculate_activity_level(self, dog_id: str) -> str:
        """Calculate activity level based on today's activities."""
        walk_data = self._dog_data[dog_id]["walk"]
        activity_data = self._dog_data[dog_id]["activity"]

        total_activity_min = walk_data.get("walk_duration_min", 0) + activity_data.get(
            "play_duration_today_min", 0
        )

        if total_activity_min < 30:
            return "low"
        elif total_activity_min < 90:
            return "medium"
        else:
            return "high"

    def _calculate_next_medication(self, dog_id: str) -> datetime | None:
        """Calculate next medication due time."""
        # This would be implemented based on medication schedules
        # For now, return None
        return None

    def _calculate_calories(self, dog_id: str) -> float:
        """Calculate approximate calories burned today."""
        from .const import (
            CALORIES_PER_KM_PER_KG,
            CALORIES_PER_MIN_PLAY_PER_KG,
            DEFAULT_DOG_WEIGHT_KG,
            MIN_DOG_WEIGHT_KG,
        )

        walk_data = self._dog_data[dog_id]["walk"]
        activity_data = self._dog_data[dog_id]["activity"]
        dog_weight = self._dog_data[dog_id]["info"]["weight"]

        # Validate and use default if necessary
        if dog_weight <= MIN_DOG_WEIGHT_KG:
            dog_weight = DEFAULT_DOG_WEIGHT_KG

        # Calculate based on scientific formula
        distance_km = walk_data.get("total_distance_today", 0) / 1000
        walk_calories = distance_km * dog_weight * CALORIES_PER_KM_PER_KG

        # Play calories based on intensity and weight
        play_minutes = activity_data.get("play_duration_today_min", 0)
        play_calories = play_minutes * dog_weight * CALORIES_PER_MIN_PLAY_PER_KG

        return round(walk_calories + play_calories, 1)

    def update_options(self, options: dict[str, Any] | Mapping[str, Any]) -> None:
        """Update coordinator options."""
        # Make a shallow copy to detach from the source mapping
        self.entry._options = dict(options)
        self._initialize_dog_data()

    def update_gps(
        self,
        dog_id: str,
        latitude: float,
        longitude: float,
        accuracy: float | None = None,
    ) -> None:
        """Update GPS-derived fields: last update, distance, and geofence enter/leave/time."""
        data = self._dog_data.get(dog_id)
        if not data:
            _LOGGER.warning("update_gps: unknown dog_id %s", dog_id)
            return

        loc = data.setdefault("location", {})
        loc["last_gps_update"] = dt_util.utcnow().isoformat()

        # Take home center from stored loc if available, else from options
        home_lat = loc.get("home_lat")
        home_lon = loc.get("home_lon")
        radius_m = loc.get("radius_m") or 0

        try:
            opts = dict(getattr(self.entry, "_options", {}) or {})
            geo = (
                (opts.get("geofence") or {})
                if isinstance(opts.get("geofence"), dict)
                else {}
            )
            home_lat = home_lat if home_lat is not None else geo.get("lat")
            home_lon = home_lon if home_lon is not None else geo.get("lon")
            radius_m = radius_m or int(geo.get("radius_m") or 0)
        except Exception:
            pass

        # Compute distance and inside flag
        dist = None
        inside = None
        if isinstance(home_lat, int | float) and isinstance(home_lon, int | float):
            try:
                dist = round(
                    _haversine_m(
                        float(home_lat),
                        float(home_lon),
                        float(latitude),
                        float(longitude),
                    ),
                    1,
                )
            except Exception:
                dist = None

        if dist is not None and radius_m and radius_m > 0:
            inside = dist <= float(radius_m)

        # Initialize counters
        if "enters_today" not in loc:
            loc["enters_today"] = 0
        if "leaves_today" not in loc:
            loc["leaves_today"] = 0
        if "time_inside_today_min" not in loc:
            loc["time_inside_today_min"] = 0.0

        # Transition tracking
        prev_inside = loc.get("is_home")
        last_ts = loc.get("last_ts")
        now = dt_util.utcnow()

        if last_ts:
            try:
                elapsed = (now - self._parse_datetime(last_ts)).total_seconds() / 60.0
                # Accumulate time when previously inside=True
                if prev_inside is True and elapsed > 0:
                    loc["time_inside_today_min"] = round(
                        float(loc.get("time_inside_today_min", 0.0)) + float(elapsed), 1
                    )
            except Exception:
                pass

        # Count transitions
        if inside is not None and prev_inside is not None and inside != prev_inside:
            if inside:
                loc["enters_today"] = int(loc.get("enters_today", 0)) + 1
            else:
                loc["leaves_today"] = int(loc.get("leaves_today", 0)) + 1

        # Update location fields
        if dist is not None:
            loc["distance_from_home"] = dist
        if inside is not None:
            loc["is_home"] = inside
            loc["current_location"] = "home" if inside else "away"
        loc["last_ts"] = now.isoformat()

        # Notify listeners for immediate UI update
        self.async_update_listeners()

    def get_dog_data(self, dog_id: str) -> dict[str, Any]:
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

            # Reset location counters
            self._dog_data[dog_id]["location"]["enters_today"] = 0
            self._dog_data[dog_id]["location"]["leaves_today"] = 0
            self._dog_data[dog_id]["location"]["time_inside_today_min"] = 0.0

            # Reset statistics
            self._dog_data[dog_id]["statistics"]["poop_count_today"] = 0

        await self.async_request_refresh()

    def increment_walk_distance(self, dog_id: str, inc_m: float) -> None:
        """Increment live walk distance for a dog and notify listeners."""
        if not dog_id or dog_id not in self._dog_data:
            _LOGGER.error("Invalid or unknown dog_id: %s", dog_id)
            return

        if inc_m <= 0:
            return  # No distance to add

        try:
            walk = self._dog_data[dog_id]["walk"]
            current = float(walk.get("walk_distance_m", 0.0))
            new_distance = round(current + float(inc_m), 1)

            # Only update if distance actually changed (avoid micro-updates)
            if new_distance > current:
                walk["walk_distance_m"] = new_distance

                # Mark last action for stats
                self._dog_data[dog_id]["statistics"]["last_action"] = (
                    dt_util.now().isoformat()
                )
                self._dog_data[dog_id]["statistics"]["last_action_type"] = (
                    "walk_progress"
                )

                # Import constant locally to avoid circular dependency
                from .const import WALK_DISTANCE_UPDATE_THRESHOLD_M

                # Notify entities immediately only if significant change
                if new_distance - current >= WALK_DISTANCE_UPDATE_THRESHOLD_M:
                    self.async_update_listeners()
        except Exception as err:
            _LOGGER.error(f"Failed to increment walk distance for {dog_id}: {err}")

    def notify_updates(self) -> None:
        """Notify all entities listening to this coordinator."""
        self.async_update_listeners()

    async def start_walk(self, dog_id: str, source: str = "manual") -> None:
        """Start a walk for a dog."""
        if not dog_id or dog_id not in self._dog_data:
            _LOGGER.error(f"Invalid or unknown dog_id: {dog_id}")
            return

        try:
            walk_data = self._dog_data[dog_id]["walk"]

            if walk_data.get("walk_in_progress", False):
                _LOGGER.warning(f"Walk already in progress for {dog_id}")
                return

            walk_data["walk_in_progress"] = True
            walk_data["walk_start_time"] = dt_util.now().isoformat()
            walk_data["walk_duration_min"] = 0
            walk_data["walk_distance_m"] = 0

            self._dog_data[dog_id]["statistics"]["last_action"] = (
                dt_util.now().isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_started"

            self.hass.bus.async_fire(
                EVENT_WALK_STARTED, {ATTR_DOG_ID: dog_id, "source": source}
            )

            await self.async_request_refresh()
        except Exception as err:
            _LOGGER.error(f"Failed to start walk for {dog_id}: {err}")

    async def end_walk(self, dog_id: str, reason: str = "manual") -> None:
        """End a walk for a dog."""
        if not dog_id or dog_id not in self._dog_data:
            _LOGGER.error(f"Invalid or unknown dog_id: {dog_id}")
            return

        try:
            walk_data = self._dog_data[dog_id]["walk"]

            if not walk_data.get("walk_in_progress", False):
                _LOGGER.warning(f"No walk in progress for {dog_id}")
                return

            # Calculate duration
            start_time_dt = self._parse_datetime(walk_data.get("walk_start_time"))
            if start_time_dt:
                duration = (dt_util.now() - start_time_dt).total_seconds() / 60
                walk_data["walk_duration_min"] = round(duration, 1)

            walk_data["walk_in_progress"] = False
            walk_data["last_walk"] = dt_util.now().isoformat()
            walk_data["walks_today"] = walk_data.get("walks_today", 0) + 1
            walk_data["total_distance_today"] = walk_data.get(
                "total_distance_today", 0
            ) + walk_data.get("walk_distance_m", 0)

            self._dog_data[dog_id]["statistics"]["last_action"] = (
                dt_util.now().isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_ended"

            self.hass.bus.async_fire(
                EVENT_WALK_ENDED,
                {
                    ATTR_DOG_ID: dog_id,
                    "reason": reason,
                    "duration_min": walk_data.get("walk_duration_min", 0),
                    "distance_m": walk_data.get("walk_distance_m", 0),
                },
            )

            await self.async_request_refresh()
        except Exception as err:
            _LOGGER.error(f"Failed to end walk for {dog_id}: {err}")

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

    async def feed_dog(
        self, dog_id: str, meal_type: str, portion_g: int, food_type: str
    ) -> None:
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
            },
        )

        await self.async_request_refresh()

    async def log_health_data(
        self, dog_id: str, weight_kg: float | None, note: str
    ) -> None:
        """Log health data for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return

        health_data = self._dog_data[dog_id]["health"]

        if weight_kg is not None:
            health_data["weight_kg"] = weight_kg
            # Keep last 30 weight measurements for trend
            health_data["weight_trend"].append(
                {"date": dt_util.now().isoformat(), "weight": weight_kg}
            )
            health_data["weight_trend"] = health_data["weight_trend"][-30:]

        if note:
            health_data["health_notes"].append(
                {"date": dt_util.now().isoformat(), "note": note}
            )

        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "health_logged"

        await self.async_request_refresh()

    async def log_medication(
        self, dog_id: str, medication_name: str, dose: str
    ) -> None:
        """Log medication for a dog."""
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
            },
        )

        await self.async_request_refresh()

    async def start_grooming(self, dog_id: str, grooming_type: str, notes: str) -> None:
        """Start grooming session for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return

        grooming_data = self._dog_data[dog_id]["grooming"]

        grooming_data["last_grooming"] = dt_util.now().isoformat()
        grooming_data["grooming_type"] = grooming_type
        grooming_data["grooming_history"].append(
            {"date": dt_util.now().isoformat(), "type": grooming_type, "notes": notes}
        )

        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "groomed"

        self.hass.bus.async_fire(
            EVENT_GROOMING_DONE,
            {
                ATTR_DOG_ID: dog_id,
                "type": grooming_type,
            },
        )

        await self.async_request_refresh()

    async def log_play_session(
        self, dog_id: str, duration_min: int, intensity: str
    ) -> None:
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

    async def log_training(
        self, dog_id: str, topic: str, duration_min: int, notes: str
    ) -> None:
        """Log training session for a dog."""
        if dog_id not in self._dog_data:
            _LOGGER.error(f"Dog {dog_id} not found")
            return

        training_data = self._dog_data[dog_id]["training"]

        training_data["last_training"] = dt_util.now().isoformat()
        training_data["last_topic"] = topic
        training_data["training_duration_min"] = duration_min
        training_data["training_sessions_today"] += 1
        training_data["training_history"].append(
            {
                "date": dt_util.now().isoformat(),
                "topic": topic,
                "duration": duration_min,
                "notes": notes,
            }
        )

        self._dog_data[dog_id]["statistics"]["last_action"] = dt_util.now().isoformat()
        self._dog_data[dog_id]["statistics"]["last_action_type"] = "trained"

        await self.async_request_refresh()

    async def set_visitor_mode(self, enabled: bool) -> None:
        """Set visitor mode."""
        self._visitor_mode = enabled
        await self.async_request_refresh()

    async def activate_emergency_mode(self, level: str, note: str) -> None:
        """Activate emergency mode."""
        self._emergency_mode = True
        self._emergency_level = level
        _LOGGER.warning(f"Emergency mode activated: {level} - {note}")
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
