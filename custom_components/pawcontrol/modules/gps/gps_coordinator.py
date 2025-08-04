"""GPS Coordinator implementation for Paw Control."""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2
from typing import List, Dict, Tuple, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_DOG_NAME
from .utils import calculate_distance, validate_coordinates, safe_service_call
from .exceptions import GPSError, InvalidCoordinates

_LOGGER = logging.getLogger(__name__)


class PawControlDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for Paw Control data updates with GPS tracking."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )
        self.dog_name = entry.data[CONF_DOG_NAME]
        self.entry = entry
        
        # GPS tracking variables
        self._gps_tracking_active = False
        self._current_walk_points = []
        self._last_gps_update = None
        self._home_coordinates = None

    # ================================================================================
    # 📍 CORE GPS FUNCTIONS
    # ================================================================================
    
    async def async_update_gps_simple(self, data: dict) -> None:
        """Update GPS position from any source."""
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        accuracy = float(data.get("accuracy", 0))
        source_info = data.get("source_info", "manual")
        
        # Validate coordinates
        if not validate_coordinates(latitude, longitude):
            raise InvalidCoordinates(f"Invalid GPS coordinates: {latitude}, {longitude}")
        
        try:
            # Update current location
            entity_id = f"input_text.{self.dog_name}_current_location"
            await safe_service_call(
                self.hass, "input_text", "set_value",
                {"entity_id": entity_id, "value": f"{latitude},{longitude}"}
            )
            
            # Update GPS signal strength
            if accuracy > 0:
                signal_strength = min(100, max(0, 100 - accuracy))
                entity_id = f"input_number.{self.dog_name}_gps_signal_strength"
                await safe_service_call(
                    self.hass, "input_number", "set_value",
                    {"entity_id": entity_id, "value": signal_strength}
                )
            
            # Check automatic walk detection
            await self._check_automatic_walk_detection(latitude, longitude)
            
            # Update walk tracking if active
            if await self._is_walk_in_progress():
                await self._update_walk_tracking(latitude, longitude, accuracy)
            
            # Store last GPS update time
            self._last_gps_update = datetime.now()
            
            _LOGGER.info("GPS updated for %s: %s,%s (accuracy: %sm, source: %s)", 
                        self.dog_name, latitude, longitude, accuracy, source_info)
                        
        except Exception as e:
            _LOGGER.error("Error updating GPS for %s: %s", self.dog_name, e)
            raise GPSError(f"Failed to update GPS: {e}")

    async def async_setup_automatic_gps(self, data: dict) -> None:
        """Setup automatic GPS tracking."""
        gps_source = data.get("gps_source")
        gps_entity = data.get("gps_entity")
        tracking_sensitivity = data.get("tracking_sensitivity", "medium")
        movement_threshold = data.get("movement_threshold", 50)
        auto_start_walk = data.get("auto_start_walk", True)
        auto_end_walk = data.get("auto_end_walk", True)
        home_zone_radius = data.get("home_zone_radius", 100)
        track_route = data.get("track_route", True)
        calculate_stats = data.get("calculate_stats", True)
        
        try:
            # Enable/disable automatic walk detection
            await self.hass.services.async_call(
                "input_boolean", "turn_on" if auto_start_walk else "turn_off",
                {"entity_id": f"input_boolean.{self.dog_name}_auto_walk_detection"},
                blocking=True
            )
            
            # Enable GPS tracking
            await self.hass.services.async_call(
                "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self.dog_name}_gps_tracking_enabled"},
                blocking=True
            )
            
            # Store GPS configuration
            gps_config = {
                "source": gps_source,
                "entity": gps_entity,
                "sensitivity": tracking_sensitivity,
                "auto_start": auto_start_walk,
                "auto_end": auto_end_walk,
                "track_route": track_route,
                "calculate_stats": calculate_stats,
                "setup_time": datetime.now().isoformat()
            }
            
            await self.hass.services.async_call(
                "input_text", "set_value",
                {
                    "entity_id": f"input_text.{self.dog_name}_gps_tracker_status",
                    "value": json.dumps(gps_config)
                },
                blocking=True
            )
            
            self._gps_tracking_active = True
            
            _LOGGER.info("Automatic GPS tracking setup for %s: source=%s, threshold=%sm", 
                        self.dog_name, gps_source, movement_threshold)
                        
        except Exception as e:
            _LOGGER.error("Error setting up automatic GPS for %s: %s", self.dog_name, e)
            raise GPSError(f"Failed to setup automatic GPS: {e}")

    # ================================================================================
    # 📍 WALK TRACKING FUNCTIONS
    # ================================================================================
    
    async def async_start_walk_tracking(self, data: dict) -> None:
        """Start GPS-based walk tracking."""
        walk_name = data.get("walk_name", f"Spaziergang {datetime.now().strftime('%H:%M')}")
        expected_duration = data.get("expected_duration")
        track_detailed_route = data.get("track_detailed_route", True)
        
        try:
            # Check if walk already in progress
            if await self._is_walk_in_progress():
                _LOGGER.warning("Walk already in progress for %s", self.dog_name)
                return
            
            # Mark walk as in progress
            await self.hass.services.async_call(
                "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self.dog_name}_walk_in_progress"},
                blocking=True
            )
            
            # Reset current walk stats
            walk_entities_to_reset = [
                f"input_number.{self.dog_name}_current_walk_distance",
                f"input_number.{self.dog_name}_current_walk_duration", 
                f"input_number.{self.dog_name}_current_walk_speed",
                f"input_number.{self.dog_name}_current_walk_calories"
            ]
            
            for entity_id in walk_entities_to_reset:
                await safe_service_call(
                    self.hass, "input_number", "set_value",
                    {"entity_id": entity_id, "value": 0}
                )
            
            # Store walk start data
            walk_start_data = {
                "name": walk_name,
                "start_time": datetime.now().isoformat(),
                "expected_duration": expected_duration,
                "track_route": track_detailed_route
            }
            
            await self.hass.services.async_call(
                "input_text", "set_value",
                {
                    "entity_id": f"input_text.{self.dog_name}_current_walk_data",
                    "value": json.dumps(walk_start_data)
                },
                blocking=True
            )
            
            # Initialize walk points list
            self._current_walk_points = []
            
            _LOGGER.info("Walk tracking started for %s: %s", self.dog_name, walk_name)
            
        except Exception as e:
            _LOGGER.error("Error starting walk tracking for %s: %s", self.dog_name, e)
            raise GPSError(f"Failed to start walk tracking: {e}")

    async def async_end_walk_tracking(self, data: dict) -> None:
        """End GPS-based walk tracking and calculate statistics."""
        walk_rating = data.get("walk_rating", 5)
        notes = data.get("notes", "")
        
        try:
            # Check if walk is in progress
            if not await self._is_walk_in_progress():
                _LOGGER.warning("No walk in progress for %s", self.dog_name)
                return
            
            # Get walk start data
            walk_data_entity = self.hass.states.get(f"input_text.{self.dog_name}_current_walk_data")
            if walk_data_entity and walk_data_entity.state:
                try:
                    walk_start_data = json.loads(walk_data_entity.state)
                    start_time = datetime.fromisoformat(walk_start_data["start_time"])
                    walk_name = walk_start_data.get("name", "Spaziergang")
                except (json.JSONDecodeError, KeyError):
                    start_time = datetime.now() - timedelta(minutes=30)  # Default fallback
                    walk_name = "Spaziergang"
            else:
                start_time = datetime.now() - timedelta(minutes=30)
                walk_name = "Spaziergang"
            
            # Calculate walk statistics
            end_time = datetime.now()
            duration_minutes = int((end_time - start_time).total_seconds() / 60)
            
            # Calculate distance from GPS points
            total_distance_km = 0.0
            if len(self._current_walk_points) > 1:
                for i in range(1, len(self._current_walk_points)):
                    try:
                        distance = calculate_distance(
                            self._current_walk_points[i-1], 
                            self._current_walk_points[i]
                        )
                        total_distance_km += distance / 1000  # Convert to km
                    except InvalidCoordinates:
                        continue
            
            # Calculate average speed
            avg_speed_kmh = (total_distance_km / (duration_minutes / 60)) if duration_minutes > 0 else 0
            
            # Calculate calories (simplified: 50 kcal per km for average dog)
            calories_burned = int(total_distance_km * 50)
            
            # Update final walk statistics
            await self._update_final_walk_stats(
                duration_minutes, total_distance_km, avg_speed_kmh, calories_burned
            )
            
            # Mark walk as completed
            await self.hass.services.async_call(
                "input_boolean", "turn_off",
                {"entity_id": f"input_boolean.{self.dog_name}_walk_in_progress"},
                blocking=True
            )
            
            # Increment walk counters
            await self._increment_walk_counters()
            
            # Store walk in history
            await self._store_walk_in_history(
                walk_name, start_time, end_time, total_distance_km, 
                duration_minutes, calories_burned, walk_rating, notes
            )
            
            # Clear current walk data
            self._current_walk_points = []
            
            _LOGGER.info(
                "Walk completed for %s: %s (%.2f km, %d min, %d kcal)",
                self.dog_name, walk_name, total_distance_km, duration_minutes, calories_burned
            )
            
        except Exception as e:
            _LOGGER.error("Error ending walk tracking for %s: %s", self.dog_name, e)
            raise GPSError(f"Failed to end walk tracking: {e}")

    # ================================================================================
    # 📍 HELPER METHODS
    # ================================================================================
    
    async def _is_walk_in_progress(self) -> bool:
        """Check if a walk is currently in progress."""
        entity = self.hass.states.get(f"input_boolean.{self.dog_name}_walk_in_progress")
        return entity and entity.state == "on"
    
    async def _check_automatic_walk_detection(self, latitude: float, longitude: float) -> None:
        """Check if automatic walk detection should trigger."""
        try:
            # Get home coordinates if not set
            if not self._home_coordinates:
                home_entity = self.hass.states.get(f"input_text.{self.dog_name}_home_location")
                if home_entity and home_entity.state:
                    try:
                        home_lat, home_lon = map(float, home_entity.state.split(','))
                        self._home_coordinates = (home_lat, home_lon)
                    except ValueError:
                        return
                else:
                    # Set current location as home if not defined
                    self._home_coordinates = (latitude, longitude)
                    await safe_service_call(
                        self.hass, "input_text", "set_value",
                        {
                            "entity_id": f"input_text.{self.dog_name}_home_location",
                            "value": f"{latitude},{longitude}"
                        }
                    )
                    return
            
            # Calculate distance from home
            distance_from_home = calculate_distance(
                (latitude, longitude), 
                self._home_coordinates
            )
            
            # Check if walk should auto-start (> 50m from home)
            if distance_from_home > 50 and not await self._is_walk_in_progress():
                auto_detection_entity = self.hass.states.get(f"input_boolean.{self.dog_name}_auto_walk_detection")
                if auto_detection_entity and auto_detection_entity.state == "on":
                    await self.async_start_walk_tracking({
                        "walk_name": "Automatischer Spaziergang",
                        "track_detailed_route": True
                    })
                    _LOGGER.info("Auto-started walk for %s (%.0fm from home)", self.dog_name, distance_from_home)
            
            # Check if walk should auto-end (< 20m from home for 2+ minutes)
            elif distance_from_home < 20 and await self._is_walk_in_progress():
                # Simple auto-end after being close to home
                await asyncio.sleep(30)  # Wait 30 seconds
                current_distance = calculate_distance(
                    (latitude, longitude), 
                    self._home_coordinates
                )
                if current_distance < 20:  # Still close to home
                    await self.async_end_walk_tracking({
                        "walk_rating": 5,
                        "notes": "Automatisch beendet (zurück zu Hause)"
                    })
                    _LOGGER.info("Auto-ended walk for %s (zurück zu Hause)", self.dog_name)
            
        except Exception as e:
            _LOGGER.error("Error in automatic walk detection for %s: %s", self.dog_name, e)
    
    async def _update_walk_tracking(self, latitude: float, longitude: float, accuracy: float) -> None:
        """Update ongoing walk tracking with new GPS point."""
        try:
            # Add point to current walk
            self._current_walk_points.append((latitude, longitude))
            
            # Calculate current distance
            total_distance = 0.0
            if len(self._current_walk_points) > 1:
                for i in range(1, len(self._current_walk_points)):
                    try:
                        distance = calculate_distance(
                            self._current_walk_points[i-1],
                            self._current_walk_points[i]
                        )
                        total_distance += distance / 1000  # Convert to km
                    except InvalidCoordinates:
                        continue
            
            # Update current walk distance
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {
                    "entity_id": f"input_number.{self.dog_name}_current_walk_distance",
                    "value": round(total_distance, 2)
                }
            )
            
            # Calculate and update current speed if we have recent points
            if len(self._current_walk_points) >= 2:
                recent_distance = calculate_distance(
                    self._current_walk_points[-2],
                    self._current_walk_points[-1]
                ) / 1000  # km
                
                # Assume 1 minute between updates for speed calculation
                current_speed = recent_distance * 60  # km/h
                
                await safe_service_call(
                    self.hass, "input_number", "set_value",
                    {
                        "entity_id": f"input_number.{self.dog_name}_current_walk_speed",
                        "value": round(current_speed, 1)
                    }
                )
            
        except Exception as e:
            _LOGGER.error("Error updating walk tracking for %s: %s", self.dog_name, e)
    
    async def _update_final_walk_stats(self, duration: int, distance: float, speed: float, calories: int) -> None:
        """Update final walk statistics."""
        try:
            stats_updates = [
                (f"input_number.{self.dog_name}_current_walk_duration", duration),
                (f"input_number.{self.dog_name}_current_walk_distance", round(distance, 2)),
                (f"input_number.{self.dog_name}_current_walk_speed", round(speed, 1)),
                (f"input_number.{self.dog_name}_current_walk_calories", calories),
            ]
            
            for entity_id, value in stats_updates:
                await safe_service_call(
                    self.hass, "input_number", "set_value",
                    {"entity_id": entity_id, "value": value}
                )
                
        except Exception as e:
            _LOGGER.error("Error updating final walk stats for %s: %s", self.dog_name, e)
    
    async def _increment_walk_counters(self) -> None:
        """Increment daily/weekly/monthly walk counters."""
        try:
            counters = [
                f"counter.{self.dog_name}_daily_walks",
                f"counter.{self.dog_name}_weekly_walks", 
                f"counter.{self.dog_name}_monthly_walks",
                f"counter.{self.dog_name}_total_walks"
            ]
            
            for counter_id in counters:
                await safe_service_call(
                    self.hass, "counter", "increment",
                    {"entity_id": counter_id}
                )
                
        except Exception as e:
            _LOGGER.error("Error incrementing walk counters for %s: %s", self.dog_name, e)
    
    async def _store_walk_in_history(self, name: str, start_time: datetime, end_time: datetime,
                                   distance: float, duration: int, calories: int, 
                                   rating: int, notes: str) -> None:
        """Store completed walk in history."""
        try:
            walk_record = {
                "name": name,
                "date": start_time.strftime("%Y-%m-%d"),
                "start_time": start_time.strftime("%H:%M"),
                "end_time": end_time.strftime("%H:%M"),
                "duration_minutes": duration,
                "distance_km": round(distance, 2),
                "calories_burned": calories,
                "rating": rating,
                "notes": notes,
                "gps_points": len(self._current_walk_points)
            }
            
            # Get existing history
            history_entity = self.hass.states.get(f"input_text.{self.dog_name}_walk_history_today")
            current_history = []
            
            if history_entity and history_entity.state:
                try:
                    current_history = json.loads(history_entity.state)
                except json.JSONDecodeError:
                    current_history = []
            
            # Add new walk to history
            current_history.append(walk_record)
            
            # Store updated history (keep last 10 walks for today)
            if len(current_history) > 10:
                current_history = current_history[-10:]
            
            await self.hass.services.async_call(
                "input_text", "set_value",
                {
                    "entity_id": f"input_text.{self.dog_name}_walk_history_today",
                    "value": json.dumps(current_history)
                },
                blocking=True
            )
            
        except Exception as e:
            _LOGGER.error("Error storing walk history for %s: %s", self.dog_name, e)

    # ================================================================================
    # 📍 COORDINATOR INTERFACE METHODS
    # ================================================================================
    
    async def _async_update_data(self):
        """Fetch data for the coordinator."""
        try:
            # This method is called by the base DataUpdateCoordinator
            # We can return current GPS and walk status here
            return {
                "last_update": datetime.now().isoformat(),
                "gps_active": self._gps_tracking_active,
                "walk_in_progress": await self._is_walk_in_progress(),
                "current_walk_points": len(self._current_walk_points)
            }
        except Exception as e:
            _LOGGER.error("Error updating coordinator data for %s: %s", self.dog_name, e)
            return {}
    
    async def async_shutdown(self):
        """Shutdown the coordinator."""
        _LOGGER.info("Shutting down GPS coordinator for %s", self.dog_name)
        
        # End any walk in progress
        if await self._is_walk_in_progress():
            await self.async_end_walk_tracking({
                "walk_rating": 3,
                "notes": "Automatisch beendet beim Herunterfahren"
            })
        
        # Reset GPS tracking
        self._gps_tracking_active = False
        self._current_walk_points = []
