"""Data coordinator for Paw Control integration.

This module provides the central data coordination for the Paw Control integration.
It manages all dog-related data, GPS tracking, activity monitoring, and state
calculations while ensuring efficient data handling and minimal resource usage.

The coordinator follows Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations
- Robust error handling
- Efficient data management and caching
- Comprehensive logging and monitoring
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    CALORIES_PER_KM_PER_KG,
    CALORIES_PER_MIN_PLAY_PER_KG,
    CONF_DOGS,
    COORDINATOR_REFRESH_THROTTLE_SECONDS,
    DEFAULT_DOG_WEIGHT_KG,
    DEFAULT_MEDICATION_REMINDER_HOURS,
    DEFAULT_WALK_THRESHOLD_HOURS,
    DOMAIN,
    ENTITY_UPDATE_DEBOUNCE_SECONDS,
    ERROR_COORDINATOR_UNAVAILABLE,
    ERROR_INVALID_COORDINATES,
    EVENT_DOG_FED,
    EVENT_GROOMING_DONE,
    EVENT_MEDICATION_GIVEN,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
    INTEGRATION_VERSION,
    MIN_DOG_WEIGHT_KG,
    MIN_MEANINGFUL_DISTANCE_M,
    STATUS_READY,
    WALK_DISTANCE_UPDATE_THRESHOLD_M,
)
from .utils import calculate_distance, validate_coordinates

if TYPE_CHECKING:
    from .types import CoordinatorData, DogData

_LOGGER = logging.getLogger(__name__)


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage fetching and updating Paw Control data.

    This coordinator serves as the central data hub for all dog-related information.
    It handles GPS tracking, activity monitoring, health data, and automated
    calculations while ensuring efficient updates and minimal resource usage.

    The coordinator maintains real-time state for:
    - Dog location and geofencing
    - Activity tracking (walks, feeding, health)
    - Automated status calculations (needs walk, is hungry, etc.)
    - Emergency and visitor modes
    - Daily statistics and counters
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator.

        Sets up the data coordinator with proper update intervals and
        initializes all dog data structures based on configuration.

        Args:
            hass: Home Assistant instance
            entry: Config entry containing dog configurations
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=5),
            always_update=False,  # Platinum optimization - only update when data changes
        )
        self.entry = entry
        self._dog_data: dict[str, DogData] = {}
        self._visitor_mode: bool = False
        self._emergency_mode: bool = False
        self._emergency_level: str = "info"
        self._last_update_time: datetime | None = None
        
        # Platinum performance optimizations
        self._last_refresh_request: datetime | None = None
        self._update_debounce_tasks: dict[str, asyncio.Task] = {}
        self._refresh_lock = asyncio.Lock()
        self._status: str = STATUS_READY
        self._error_count: int = 0
        self._version: str = INTEGRATION_VERSION

        # Initialize dog data structures
        self._initialize_dog_data()

    def _initialize_dog_data(self) -> None:
        """Initialize data structure for each configured dog.

        Creates comprehensive data structures for each dog including all
        tracking categories: info, walks, location, feeding, health, etc.
        This method ensures all required fields are present with safe defaults.
        """
        dogs = self.entry.options.get(CONF_DOGS, [])

        for dog in dogs:
            dog_id = dog.get("dog_id")
            if not dog_id:
                _LOGGER.warning("Skipping dog with missing ID: %s", dog)
                continue

            _LOGGER.debug("Initializing data for dog %s", dog_id)

            # Create comprehensive dog data structure
            self._dog_data[dog_id] = {
                "info": {
                    "name": dog.get("name", dog_id),
                    "breed": dog.get("breed", "Unknown"),
                    "age": max(0, int(dog.get("age", 0))),
                    "weight": max(0.1, float(dog.get("weight", 0))),
                    "size": dog.get("size", "medium"),
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
                    "weight_kg": float(dog.get("weight", 0)),
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

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch data from API or calculate derived values.

        This method performs all necessary data updates and calculations
        for each dog. It's called periodically by the coordinator framework
        to ensure data stays current.

        Returns:
            Updated dog data dictionary

        Raises:
            UpdateFailed: If critical data update operations fail
        """
        try:
            current_time = dt_util.now()

            # Update calculated fields for each dog
            for dog_id, data in self._dog_data.items():
                try:
                    # Calculate derived status fields
                    data["walk"]["needs_walk"] = self._calculate_needs_walk(dog_id)
                    data["feeding"]["is_hungry"] = self._calculate_is_hungry(dog_id)
                    data["grooming"]["needs_grooming"] = self._calculate_needs_grooming(
                        dog_id
                    )
                    data["activity"]["activity_level"] = self._calculate_activity_level(
                        dog_id
                    )
                    data["health"][
                        "next_medication_due"
                    ] = await self._calculate_next_medication(dog_id)
                    data["activity"]["calories_burned_today"] = (
                        self._calculate_calories(dog_id)
                    )

                except Exception as err:
                    _LOGGER.error(
                        "Failed to update calculated fields for dog %s: %s",
                        dog_id,
                        err,
                    )
                    # Continue with other dogs even if one fails

            self._last_update_time = current_time
            return self._dog_data

        except Exception as err:
            _LOGGER.error("Critical error updating coordinator data: %s", err)
            raise UpdateFailed(f"Error updating data: {err}") from err

    def _parse_datetime(self, date_string: str | None) -> datetime | None:
        """Parse a datetime string safely with timezone awareness.

        Handles various datetime formats and ensures proper timezone handling
        for consistent time calculations throughout the integration.

        Args:
            date_string: ISO format datetime string or None

        Returns:
            Parsed datetime object with timezone info, or None if invalid
        """
        if not date_string:
            return None

        try:
            # Try to parse ISO format
            parsed_dt = datetime.fromisoformat(date_string)

            # Ensure timezone awareness
            if parsed_dt.tzinfo is None:
                parsed_dt = dt_util.as_local(parsed_dt)

            return parsed_dt
        except (ValueError, TypeError, AttributeError) as err:
            _LOGGER.debug("Failed to parse datetime '%s': %s", date_string, err)
            return None

    def _calculate_needs_walk(self, dog_id: str) -> bool:
        """Calculate if dog needs a walk based on last walk time.

        Uses configurable threshold to determine if enough time has passed
        since the last walk to warrant a new walk recommendation.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            True if dog needs a walk, False otherwise
        """
        data = self._dog_data[dog_id]["walk"]

        # Don't recommend walk if one is already in progress
        if data["walk_in_progress"]:
            return False

        last_walk_dt = self._parse_datetime(data["last_walk"])
        if not last_walk_dt:
            return True  # No previous walk recorded

        hours_since_walk = (dt_util.now() - last_walk_dt).total_seconds() / 3600
        return hours_since_walk >= DEFAULT_WALK_THRESHOLD_HOURS

    def _calculate_is_hungry(self, dog_id: str) -> bool:
        """Calculate if dog is hungry based on feeding schedule and current time.

        Determines hunger status based on typical feeding times and whether
        the dog has already been fed for the current meal period.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            True if dog is likely hungry, False otherwise
        """
        data = self._dog_data[dog_id]["feeding"]
        current_hour = dt_util.now().hour

        # Check feeding schedule against current time
        is_breakfast_time = (
            6 <= current_hour < 9 and data["feedings_today"]["breakfast"] == 0
        )
        is_lunch_time = 11 <= current_hour < 14 and data["feedings_today"]["lunch"] == 0
        is_dinner_time = (
            17 <= current_hour < 20 and data["feedings_today"]["dinner"] == 0
        )

        return bool(is_breakfast_time or is_lunch_time or is_dinner_time)

    def _calculate_needs_grooming(self, dog_id: str) -> bool:
        """Calculate if dog needs grooming based on interval since last session.

        Compares time since last grooming against the configured grooming
        interval for this dog to determine if grooming is overdue.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            True if grooming is due, False otherwise
        """
        data = self._dog_data[dog_id]["grooming"]

        last_grooming_dt = self._parse_datetime(data["last_grooming"])
        if not last_grooming_dt:
            return True  # No previous grooming recorded

        days_since = (dt_util.now() - last_grooming_dt).days
        interval_days = max(1, data.get("grooming_interval_days", 30))

        return days_since >= interval_days

    def _calculate_activity_level(self, dog_id: str) -> str:
        """Calculate current activity level based on today's activities.

        Combines walk duration and play time to determine overall
        activity level using predefined thresholds.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            Activity level: "low", "medium", or "high"
        """
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

    async def _calculate_next_medication(self, dog_id: str) -> datetime | None:
        """Calculate next medication due time based on last dose.

        Uses the configured reminder interval when available; otherwise
        falls back to :data:`DEFAULT_MEDICATION_REMINDER_HOURS`.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            Next medication due time, or None if no previous medication
        """
        health_data = self._dog_data[dog_id]["health"]
        last_med_dt = self._parse_datetime(health_data.get("last_medication"))
        if not last_med_dt:
            return None

        try:
            reminder_hours = float(
                self._dog_data[dog_id]
                .get("settings", {})
                .get(
                    "medication_reminder_hours",
                    DEFAULT_MEDICATION_REMINDER_HOURS,
                )
            )
        except (TypeError, ValueError):
            reminder_hours = DEFAULT_MEDICATION_REMINDER_HOURS

        return last_med_dt + timedelta(hours=reminder_hours)

    def _calculate_calories(self, dog_id: str) -> float:
        """Calculate approximate calories burned today based on activity.

        Uses scientific formulas considering dog weight, distance walked,
        and play time to estimate caloric expenditure.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            Estimated calories burned today
        """

        walk_data = self._dog_data[dog_id]["walk"]
        activity_data = self._dog_data[dog_id]["activity"]
        dog_weight = self._dog_data[dog_id]["info"]["weight"]

        # Validate and use default weight if necessary
        if dog_weight <= MIN_DOG_WEIGHT_KG:
            dog_weight = DEFAULT_DOG_WEIGHT_KG
            _LOGGER.debug(
                "Using default weight %s kg for dog %s (invalid weight)",
                DEFAULT_DOG_WEIGHT_KG,
                dog_id,
            )

        # Calculate calories from walking (based on distance and weight)
        distance_km = walk_data.get("total_distance_today", 0) / 1000
        walk_calories = distance_km * dog_weight * CALORIES_PER_KM_PER_KG

        # Calculate calories from play (based on time and intensity)
        play_minutes = activity_data.get("play_duration_today_min", 0)
        play_calories = play_minutes * dog_weight * CALORIES_PER_MIN_PLAY_PER_KG

        total_calories = walk_calories + play_calories
        return round(total_calories, 1)

    def update_options(self, options: dict[str, Any] | Mapping[str, Any]) -> None:
        """Update coordinator options and reinitialize dog data.

        This method is called when the integration configuration changes.
        It safely updates the internal options and reinitializes data structures.

        Args:
            options: New configuration options from config entry
        """
        try:
            # Make a shallow copy to detach from the source mapping
            self.entry._options = dict(options)

            # Preserve existing data where possible during reinitialization
            old_data = dict(self._dog_data)
            self._initialize_dog_data()

            # Restore preserved data for existing dogs
            for dog_id, new_data in self._dog_data.items():
                if dog_id in old_data:
                    # Preserve runtime state while updating configuration
                    old_dog_data = old_data[dog_id]
                    new_data["walk"].update(
                        {
                            k: v
                            for k, v in old_dog_data["walk"].items()
                            if k not in ["needs_walk"]  # Recalculate derived fields
                        }
                    )
                    new_data["feeding"].update(
                        {
                            k: v
                            for k, v in old_dog_data["feeding"].items()
                            if k not in ["is_hungry"]
                        }
                    )
                    # Continue for other categories...

            _LOGGER.info("Successfully updated coordinator options")

        except Exception as err:
            _LOGGER.error("Failed to update coordinator options: %s", err)
            # Revert to previous state if update fails
            if hasattr(self.entry, "_options"):
                self._initialize_dog_data()

    def update_gps(
        self,
        dog_id: str,
        latitude: float,
        longitude: float,
        accuracy: float | None = None,
    ) -> None:
        """Update GPS-derived fields: last update, distance, and geofence tracking.

        This method efficiently processes GPS updates and calculates derived
        values like distance from home and geofence transitions.

        Args:
            dog_id: Unique identifier for the dog
            latitude: GPS latitude coordinate
            longitude: GPS longitude coordinate
            accuracy: GPS accuracy in meters (optional)
        """
        data = self._dog_data.get(dog_id)
        if not data:
            _LOGGER.warning("GPS update for unknown dog_id: %s", dog_id)
            return

        try:
            # Platinum validation - use proper coordinate validation
            if not validate_coordinates(latitude, longitude):
                _LOGGER.error(
                    "Invalid GPS coordinates for dog %s: lat=%s, lon=%s",
                    dog_id,
                    latitude,
                    longitude,
                )
                # Fire error event for monitoring
                self.hass.bus.async_fire(
                    f"{DOMAIN}_error",
                    {"error_type": ERROR_INVALID_COORDINATES, "dog_id": dog_id}
                )
                return

            loc = data.setdefault("location", {})
            current_time = dt_util.utcnow()
            loc["last_gps_update"] = current_time.isoformat()

            # Get home coordinates and radius from configuration
            home_lat = loc.get("home_lat")
            home_lon = loc.get("home_lon")
            radius_m = loc.get("radius_m", 0)

            # Fall back to options if not stored in location data
            try:
                opts = dict(getattr(self.entry, "_options", {}) or {})
                geo = (
                    opts.get("geofence", {})
                    if isinstance(opts.get("geofence"), dict)
                    else {}
                )

                home_lat = home_lat if home_lat is not None else geo.get("lat")
                home_lon = home_lon if home_lon is not None else geo.get("lon")
                radius_m = radius_m or int(geo.get("radius_m", 0))

            except (TypeError, ValueError) as err:
                _LOGGER.debug(
                    "Failed to get geofence config for dog %s: %s", dog_id, err
                )

            # Calculate distance and geofence status
            distance = None
            inside = None

            if isinstance(home_lat, int | float) and isinstance(home_lon, int | float):
                try:
                    if validate_coordinates(
                        float(home_lat), float(home_lon)
                    ) and validate_coordinates(latitude, longitude):
                        distance = calculate_distance(
                            float(home_lat), float(home_lon), latitude, longitude
                        )
                        distance = round(distance, 1)

                        if radius_m and radius_m > 0:
                            inside = distance <= float(radius_m)
                except (ValueError, TypeError) as err:
                    _LOGGER.warning(
                        "Failed to calculate distance for dog %s: %s", dog_id, err
                    )

            # Initialize counters if missing
            for counter in ["enters_today", "leaves_today", "time_inside_today_min"]:
                if counter not in loc:
                    loc[counter] = 0 if counter.endswith("_today") else 0.0

            # Track transitions and time accumulation
            prev_inside = loc.get("is_home")
            last_ts = loc.get("last_ts")

            if last_ts:
                try:
                    last_time = self._parse_datetime(last_ts)
                    if last_time:
                        elapsed_minutes = (
                            current_time - last_time
                        ).total_seconds() / 60.0

                        # Accumulate time when previously inside geofence
                        if prev_inside is True and elapsed_minutes > 0:
                            current_inside_time = float(
                                loc.get("time_inside_today_min", 0.0)
                            )
                            loc["time_inside_today_min"] = round(
                                current_inside_time + elapsed_minutes, 1
                            )

                except Exception as err:
                    _LOGGER.debug("Failed to calculate time accumulation: %s", err)

            # Count geofence transitions
            if inside is not None and prev_inside is not None and inside != prev_inside:
                if inside:
                    loc["enters_today"] = int(loc.get("enters_today", 0)) + 1
                    _LOGGER.debug("Dog %s entered geofence", dog_id)
                else:
                    loc["leaves_today"] = int(loc.get("leaves_today", 0)) + 1
                    _LOGGER.debug("Dog %s left geofence", dog_id)

            # Update location fields
            if distance is not None:
                loc["distance_from_home"] = distance
            if inside is not None:
                loc["is_home"] = inside
                loc["current_location"] = "home" if inside else "away"
            loc["last_ts"] = current_time.isoformat()

            # Update last action for statistics
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "gps_update"

            # Notify listeners for immediate UI update (efficient batching)
            self.async_update_listeners()

        except Exception as err:
            _LOGGER.error("Failed to update GPS for dog %s: %s", dog_id, err)

    def get_dog_data(self, dog_id: str) -> dict[str, Any]:
        """Get data for specific dog with safe fallback.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            Dog data dictionary, or empty dict if dog not found
        """
        return self._dog_data.get(dog_id, {})

    async def reset_daily_counters(self) -> None:
        """Reset all daily counters for all dogs.

        This method is typically called at midnight via scheduler to reset
        all daily tracking counters while preserving historical data.
        """
        _LOGGER.info("Resetting daily counters for all dogs")

        try:
            for dog_id in self._dog_data:
                dog_data = self._dog_data[dog_id]

                # Reset walk counters
                dog_data["walk"]["walks_today"] = 0
                dog_data["walk"]["total_distance_today"] = 0.0

                # Reset feeding counters
                dog_data["feeding"]["feedings_today"] = {
                    "breakfast": 0,
                    "lunch": 0,
                    "dinner": 0,
                    "snack": 0,
                }
                dog_data["feeding"]["total_portions_today"] = 0

                # Reset health counters
                dog_data["health"]["medications_today"] = 0

                # Reset training counters
                dog_data["training"]["training_sessions_today"] = 0

                # Reset activity counters
                dog_data["activity"]["play_duration_today_min"] = 0
                dog_data["activity"]["calories_burned_today"] = 0.0

                # Reset location counters
                dog_data["location"]["enters_today"] = 0
                dog_data["location"]["leaves_today"] = 0
                dog_data["location"]["time_inside_today_min"] = 0.0

                # Reset statistics
                dog_data["statistics"]["poop_count_today"] = 0

            await self._safe_request_refresh()
            _LOGGER.info(
                "Successfully reset daily counters for %d dogs", len(self._dog_data)
            )

        except Exception as err:
            _LOGGER.error("Failed to reset daily counters: %s", err)

    def increment_walk_distance(self, dog_id: str, inc_m: float) -> None:
        """Increment live walk distance for a dog and notify listeners.

        Efficiently updates walk distance during active walks while
        minimizing unnecessary UI updates through threshold checking.

        Args:
            dog_id: Unique identifier for the dog
            inc_m: Distance increment in meters
        """
        if not dog_id or dog_id not in self._dog_data:
            _LOGGER.error("Invalid or unknown dog_id: %s", dog_id)
            return

        if inc_m <= MIN_MEANINGFUL_DISTANCE_M:
            return  # Filter out noise/insignificant updates

        try:
            walk = self._dog_data[dog_id]["walk"]
            current_distance = float(walk.get("walk_distance_m", 0.0))
            new_distance = round(current_distance + float(inc_m), 1)

            # Only update if distance actually changed (avoid micro-updates)
            if new_distance > current_distance:
                walk["walk_distance_m"] = new_distance

                # Update statistics
                current_time = dt_util.now()
                self._dog_data[dog_id]["statistics"]["last_action"] = (
                    current_time.isoformat()
                )
                self._dog_data[dog_id]["statistics"]["last_action_type"] = (
                    "walk_progress"
                )

                # Use debounced updates for better performance
                if new_distance - current_distance >= WALK_DISTANCE_UPDATE_THRESHOLD_M:
                    self._schedule_debounced_update(f"walk_distance_{dog_id}")

        except (ValueError, TypeError) as err:
            _LOGGER.error(
                "Failed to increment walk distance for dog %s: %s", dog_id, err
            )

    def notify_updates(self) -> None:
        """Notify all entities listening to this coordinator.

        This is a convenience method for triggering UI updates when
        data changes outside the normal update cycle.
        
        Platinum optimization: Implements debouncing to prevent UI spam.
        """
        self._schedule_debounced_update("general")
        
    def _schedule_debounced_update(self, update_key: str) -> None:
        """Schedule a debounced update to prevent UI spam.
        
        Args:
            update_key: Key to identify the type of update for debouncing
        """
        # Cancel existing debounce task if any
        if update_key in self._update_debounce_tasks:
            self._update_debounce_tasks[update_key].cancel()
        
        # Schedule new debounced update
        async def _debounced_update() -> None:
            await asyncio.sleep(ENTITY_UPDATE_DEBOUNCE_SECONDS)
            try:
                self.async_update_listeners()
            except Exception as err:
                _LOGGER.debug("Error during debounced update: %s", err)
            finally:
                self._update_debounce_tasks.pop(update_key, None)
        
        self._update_debounce_tasks[update_key] = self.hass.async_create_task(
            _debounced_update()
        )
        
    async def _safe_request_refresh(self) -> None:
        """Request a refresh with throttling and error handling.
        
        Platinum optimization: Prevents spam requests and tracks errors.
        """
        async with self._refresh_lock:
            now = dt_util.utcnow()
            
            # Throttle refresh requests to prevent performance issues
            if self._last_refresh_request:
                time_since_last = (now - self._last_refresh_request).total_seconds()
                if time_since_last < COORDINATOR_REFRESH_THROTTLE_SECONDS:
                    _LOGGER.debug(
                        "Throttling refresh request (%.1fs since last)",
                        time_since_last
                    )
                    return
            
            self._last_refresh_request = now
            try:
                await self.async_request_refresh()
                self._error_count = 0  # Reset error count on successful refresh
                self._status = STATUS_READY
            except Exception as err:
                self._error_count += 1
                _LOGGER.warning(
                    "Coordinator refresh failed (attempt %d): %s",
                    self._error_count,
                    err
                )
                if self._error_count >= 3:
                    self._status = ERROR_COORDINATOR_UNAVAILABLE
                    # Fire error event for monitoring
                    self.hass.bus.async_fire(
                        f"{DOMAIN}_coordinator_error",
                        {"error_count": self._error_count, "status": self._status}
                    )
                raise
                
    @property 
    def coordinator_status(self) -> str:
        """Return current coordinator status for health monitoring."""
        return self._status
        
    @property
    def integration_version(self) -> str:
        """Return integration version."""
        return self._version
        
    @property
    def error_count(self) -> int:
        """Return current error count for diagnostics."""
        return self._error_count

    async def start_walk(self, dog_id: str, source: str = "manual") -> None:
        """Start a walk for a dog.

        Initializes walk tracking state and fires appropriate events
        for other parts of the integration to respond to.

        Args:
            dog_id: Unique identifier for the dog
            source: Source of the walk start (manual, automatic, etc.)
        """
        if not dog_id or dog_id not in self._dog_data:
            _LOGGER.error("Cannot start walk for invalid dog_id: %s", dog_id)
            return

        try:
            walk_data = self._dog_data[dog_id]["walk"]

            # Check if walk already in progress
            if walk_data.get("walk_in_progress", False):
                _LOGGER.warning("Walk already in progress for dog %s", dog_id)
                return

            # Initialize walk state
            current_time = dt_util.now()
            walk_data["walk_in_progress"] = True
            walk_data["walk_start_time"] = current_time.isoformat()
            walk_data["walk_duration_min"] = 0.0
            walk_data["walk_distance_m"] = 0.0

            # Update statistics
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_started"

            # Fire event for other components
            self.hass.bus.async_fire(
                EVENT_WALK_STARTED, {ATTR_DOG_ID: dog_id, "source": source}
            )

            await self.async_request_refresh()
            _LOGGER.info("Started walk for dog %s (source: %s)", dog_id, source)

        except Exception as err:
            _LOGGER.error("Failed to start walk for dog %s: %s", dog_id, err)

    async def end_walk(self, dog_id: str, reason: str = "manual") -> None:
        """End a walk for a dog.

        Finalizes walk statistics, updates daily counters, and fires
        completion events with walk summary data.

        Args:
            dog_id: Unique identifier for the dog
            reason: Reason for ending walk (manual, automatic, timeout, etc.)
        """
        if not dog_id or dog_id not in self._dog_data:
            _LOGGER.error("Cannot end walk for invalid dog_id: %s", dog_id)
            return

        try:
            walk_data = self._dog_data[dog_id]["walk"]

            # Check if walk is actually in progress
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
            walk_data["total_distance_today"] = (
                walk_data.get("total_distance_today", 0) + walk_distance
            )

            # Update statistics
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_ended"

            # Fire completion event with summary
            self.hass.bus.async_fire(
                EVENT_WALK_ENDED,
                {
                    ATTR_DOG_ID: dog_id,
                    "reason": reason,
                    "duration_min": walk_data.get("walk_duration_min", 0),
                    "distance_m": walk_distance,
                },
            )

            await self.async_request_refresh()
            _LOGGER.info(
                "Ended walk for dog %s: %.1f min, %.1f m (reason: %s)",
                dog_id,
                walk_data.get("walk_duration_min", 0),
                walk_distance,
                reason,
            )

        except Exception as err:
            _LOGGER.error("Failed to end walk for dog %s: %s", dog_id, err)

    async def log_walk(self, dog_id: str, duration_min: int, distance_m: int) -> None:
        """Log a completed walk (manual entry).

        Records a walk that was completed outside the normal tracking system.

        Args:
            dog_id: Unique identifier for the dog
            duration_min: Walk duration in minutes
            distance_m: Walk distance in meters
        """
        if dog_id not in self._dog_data:
            _LOGGER.error("Cannot log walk for unknown dog: %s", dog_id)
            return

        try:
            walk_data = self._dog_data[dog_id]["walk"]
            current_time = dt_util.now()

            # Record walk data
            walk_data["last_walk"] = current_time.isoformat()
            walk_data["walk_duration_min"] = max(0, float(duration_min))
            walk_data["walk_distance_m"] = max(0, float(distance_m))
            walk_data["walks_today"] += 1
            walk_data["total_distance_today"] += max(0, float(distance_m))

            # Update statistics
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "walk_logged"

            await self.async_request_refresh()
            _LOGGER.info(
                "Logged walk for dog %s: %d min, %d m", dog_id, duration_min, distance_m
            )

        except (ValueError, TypeError) as err:
            _LOGGER.error("Invalid walk data for dog %s: %s", dog_id, err)
        except Exception as err:
            _LOGGER.error("Failed to log walk for dog %s: %s", dog_id, err)

    async def feed_dog(
        self, dog_id: str, meal_type: str, portion_g: int, food_type: str
    ) -> None:
        """Record feeding for a dog.

        Tracks feeding events and updates daily nutrition counters.

        Args:
            dog_id: Unique identifier for the dog
            meal_type: Type of meal (breakfast, lunch, dinner, snack)
            portion_g: Portion size in grams
            food_type: Type of food given
        """
        if dog_id not in self._dog_data:
            _LOGGER.error("Cannot feed unknown dog: %s", dog_id)
            return

        try:
            feeding_data = self._dog_data[dog_id]["feeding"]
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
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "fed"

            # Fire feeding event
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
            _LOGGER.info(
                "Fed dog %s: %s, %d g of %s", dog_id, meal_type, portion_g, food_type
            )

        except (ValueError, TypeError) as err:
            _LOGGER.error("Invalid feeding data for dog %s: %s", dog_id, err)
        except Exception as err:
            _LOGGER.error("Failed to record feeding for dog %s: %s", dog_id, err)

    async def log_health_data(
        self, dog_id: str, weight_kg: float | None, note: str
    ) -> None:
        """Log health data for a dog.

        Records health information and maintains weight trend history.

        Args:
            dog_id: Unique identifier for the dog
            weight_kg: Current weight in kilograms (optional)
            note: Health note or observation
        """
        if dog_id not in self._dog_data:
            _LOGGER.error("Cannot log health data for unknown dog: %s", dog_id)
            return

        try:
            health_data = self._dog_data[dog_id]["health"]
            current_time = dt_util.now()

            # Record weight if provided
            if weight_kg is not None:
                weight_kg = max(0.1, float(weight_kg))  # Minimum weight validation
                health_data["weight_kg"] = weight_kg

                # Maintain weight trend (last 30 measurements)
                health_data["weight_trend"].append(
                    {"date": current_time.isoformat(), "weight": weight_kg}
                )
                health_data["weight_trend"] = health_data["weight_trend"][-30:]

            # Record health note if provided
            if note and note.strip():
                health_data["health_notes"].append(
                    {"date": current_time.isoformat(), "note": note.strip()}
                )
                # Keep last 100 notes
                health_data["health_notes"] = health_data["health_notes"][-100:]

            # Update statistics
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "health_logged"

            await self.async_request_refresh()
            _LOGGER.info("Logged health data for dog %s", dog_id)

        except (ValueError, TypeError) as err:
            _LOGGER.error("Invalid health data for dog %s: %s", dog_id, err)
        except Exception as err:
            _LOGGER.error("Failed to log health data for dog %s: %s", dog_id, err)

    async def log_medication(
        self, dog_id: str, medication_name: str, dose: str
    ) -> None:
        """Log medication for a dog.

        Records medication administration and updates daily counters.

        Args:
            dog_id: Unique identifier for the dog
            medication_name: Name of the medication
            dose: Dosage information
        """
        if dog_id not in self._dog_data:
            _LOGGER.error("Cannot log medication for unknown dog: %s", dog_id)
            return

        try:
            health_data = self._dog_data[dog_id]["health"]
            current_time = dt_util.now()

            # Record medication data
            health_data["last_medication"] = current_time.isoformat()
            health_data["medication_name"] = medication_name
            health_data["medication_dose"] = dose
            health_data["medications_today"] += 1

            # Update statistics
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = (
                "medication_given"
            )

            # Fire medication event
            self.hass.bus.async_fire(
                EVENT_MEDICATION_GIVEN,
                {
                    ATTR_DOG_ID: dog_id,
                    "medication": medication_name,
                    "dose": dose,
                },
            )

            await self.async_request_refresh()
            _LOGGER.info(
                "Logged medication for dog %s: %s (%s)", dog_id, medication_name, dose
            )

        except Exception as err:
            _LOGGER.error("Failed to log medication for dog %s: %s", dog_id, err)

    async def start_grooming(self, dog_id: str, grooming_type: str, notes: str) -> None:
        """Start grooming session for a dog.

        Records grooming activity and maintains grooming history.

        Args:
            dog_id: Unique identifier for the dog
            grooming_type: Type of grooming (bath, brush, nail_trim, etc.)
            notes: Additional notes about the grooming session
        """
        if dog_id not in self._dog_data:
            _LOGGER.error("Cannot start grooming for unknown dog: %s", dog_id)
            return

        try:
            grooming_data = self._dog_data[dog_id]["grooming"]
            current_time = dt_util.now()

            # Record grooming data
            grooming_data["last_grooming"] = current_time.isoformat()
            grooming_data["grooming_type"] = grooming_type

            # Add to grooming history
            grooming_data["grooming_history"].append(
                {
                    "date": current_time.isoformat(),
                    "type": grooming_type,
                    "notes": notes,
                }
            )
            # Keep last 50 grooming sessions
            grooming_data["grooming_history"] = grooming_data["grooming_history"][-50:]

            # Update statistics
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "groomed"

            # Fire grooming event
            self.hass.bus.async_fire(
                EVENT_GROOMING_DONE,
                {
                    ATTR_DOG_ID: dog_id,
                    "type": grooming_type,
                },
            )

            await self.async_request_refresh()
            _LOGGER.info("Started grooming for dog %s: %s", dog_id, grooming_type)

        except Exception as err:
            _LOGGER.error("Failed to start grooming for dog %s: %s", dog_id, err)

    async def log_play_session(
        self, dog_id: str, duration_min: int, intensity: str
    ) -> None:
        """Log play session for a dog.

        Records play activity and updates daily activity counters.

        Args:
            dog_id: Unique identifier for the dog
            duration_min: Play duration in minutes
            intensity: Play intensity (low, medium, high)
        """
        if dog_id not in self._dog_data:
            _LOGGER.error("Cannot log play session for unknown dog: %s", dog_id)
            return

        try:
            activity_data = self._dog_data[dog_id]["activity"]
            current_time = dt_util.now()

            # Record play data
            activity_data["last_play"] = current_time.isoformat()
            activity_data["play_duration_today_min"] += max(0, int(duration_min))

            # Update statistics
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "played"

            await self.async_request_refresh()
            _LOGGER.info(
                "Logged play session for dog %s: %d min (%s intensity)",
                dog_id,
                duration_min,
                intensity,
            )

        except (ValueError, TypeError) as err:
            _LOGGER.error("Invalid play session data for dog %s: %s", dog_id, err)
        except Exception as err:
            _LOGGER.error("Failed to log play session for dog %s: %s", dog_id, err)

    async def log_training(
        self, dog_id: str, topic: str, duration_min: int, notes: str
    ) -> None:
        """Log training session for a dog.

        Records training activity and maintains training history.

        Args:
            dog_id: Unique identifier for the dog
            topic: Training topic or skill
            duration_min: Training duration in minutes
            notes: Training notes and observations
        """
        if dog_id not in self._dog_data:
            _LOGGER.error("Cannot log training for unknown dog: %s", dog_id)
            return

        try:
            training_data = self._dog_data[dog_id]["training"]
            current_time = dt_util.now()

            # Record training data
            training_data["last_training"] = current_time.isoformat()
            training_data["last_topic"] = topic
            training_data["training_duration_min"] = max(0, int(duration_min))
            training_data["training_sessions_today"] += 1

            # Add to training history
            training_data["training_history"].append(
                {
                    "date": current_time.isoformat(),
                    "topic": topic,
                    "duration": duration_min,
                    "notes": notes,
                }
            )
            # Keep last 100 training sessions
            training_data["training_history"] = training_data["training_history"][-100:]

            # Update statistics
            self._dog_data[dog_id]["statistics"]["last_action"] = (
                current_time.isoformat()
            )
            self._dog_data[dog_id]["statistics"]["last_action_type"] = "trained"

            await self.async_request_refresh()
            _LOGGER.info(
                "Logged training for dog %s: %s (%d min)", dog_id, topic, duration_min
            )

        except (ValueError, TypeError) as err:
            _LOGGER.error("Invalid training data for dog %s: %s", dog_id, err)
        except Exception as err:
            _LOGGER.error("Failed to log training for dog %s: %s", dog_id, err)

    async def set_visitor_mode(self, enabled: bool) -> None:
        """Set visitor mode state.

        Visitor mode can be used to modify behavior when guests are present.

        Args:
            enabled: True to enable visitor mode, False to disable
        """
        try:
            self._visitor_mode = bool(enabled)
            await self.async_request_refresh()
            _LOGGER.info("Visitor mode %s", "enabled" if enabled else "disabled")
        except Exception as err:
            _LOGGER.error("Failed to set visitor mode: %s", err)

    async def activate_emergency_mode(self, level: str, note: str) -> None:
        """Activate emergency mode with specified level.

        Emergency mode can trigger enhanced monitoring and notifications.

        Args:
            level: Emergency level (info, warning, critical)
            note: Description of the emergency situation
        """
        try:
            self._emergency_mode = True
            self._emergency_level = level

            _LOGGER.warning("Emergency mode activated: level=%s, note=%s", level, note)

            await self.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to activate emergency mode: %s", err)

    @property
    def visitor_mode(self) -> bool:
        """Return visitor mode status.

        Returns:
            True if visitor mode is enabled, False otherwise
        """
        return self._visitor_mode

    @property
    def emergency_mode(self) -> bool:
        """Return emergency mode status.

        Returns:
            True if emergency mode is active, False otherwise
        """
        return self._emergency_mode

    @property
    def emergency_level(self) -> str:
        """Return current emergency level.

        Returns:
            Emergency level string (info, warning, critical)
        """
        return self._emergency_level
