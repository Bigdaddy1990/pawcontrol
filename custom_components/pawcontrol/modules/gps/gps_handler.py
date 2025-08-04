"""GPS tracking handler for Paw Control integration - REVOLUTIONÄRES GPS-SYSTEM."""
from __future__ import annotations

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
from math import radians, sin, cos, sqrt, atan2

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.template import Template
from homeassistant.util.dt import now, utcnow

from .const import (
    DOMAIN,
    GPS_CONFIG,
    GPS_ACCURACY_THRESHOLDS,
    GEOFENCE_MIN_RADIUS,
    GEOFENCE_MAX_RADIUS,
    DEFAULT_HOME_COORDINATES,
    ICONS,
)
from .utils import (
    calculate_distance,
    calculate_speed_kmh,
    validate_coordinates,
    format_coordinates,
    safe_service_call,
)
from .exceptions import GPSError, InvalidCoordinates, GPSProviderError

_LOGGER = logging.getLogger(__name__)


class PawControlGPSHandler:
    """Advanced GPS tracking handler for dogs."""

    def __init__(self, hass: HomeAssistant, dog_name: str, config: Dict[str, Any]) -> None:
        """Initialize GPS handler."""
        self.hass = hass
        self.dog_name = dog_name
        self.config = config
        
        # GPS state
        self._current_location: Optional[Tuple[float, float]] = None
        self._previous_location: Optional[Tuple[float, float]] = None
        self._home_location: Optional[Tuple[float, float]] = None
        self._last_update: Optional[datetime] = None
        self._accuracy: float = 0.0
        self._speed: float = 0.0
        
        # Walk tracking
        self._walk_active: bool = False
        self._walk_start_time: Optional[datetime] = None
        self._walk_route: List[Dict[str, Any]] = []
        self._walk_distance: float = 0.0
        self._walk_max_speed: float = 0.0
        self._walk_avg_speed: float = 0.0
        
        # Geofencing
        self._geofences: Dict[str, Dict[str, Any]] = {}
        self._last_geofence_status: Dict[str, bool] = {}
        
        # Movement detection
        self._movement_history: List[Dict[str, Any]] = []
        self._stationary_since: Optional[datetime] = None
        self._is_moving: bool = False
        
        # Event listeners
        self._listeners: List[Callable[[], None]] = []
        
        # Statistics
        self._total_distance_today: float = 0.0
        self._total_walks_today: int = 0
        self._calories_burned: int = 0
        
        # GPS source configuration
        self._gps_source_type: str = "manual"
        self._gps_entity_id: Optional[str] = None
        self._gps_webhook_id: Optional[str] = None
        
        # Auto-detection settings
        self._auto_walk_detection: bool = False
        self._auto_walk_sensitivity: str = "medium"

    async def async_setup(self) -> None:
        """Set up the GPS handler."""
        try:
            _LOGGER.info("Setting up GPS handler for %s", self.dog_name)
            
            # Load home coordinates
            await self._load_home_coordinates()
            
            # Setup geofences
            await self._setup_default_geofences()
            
            # Configure GPS source
            await self._configure_gps_source()
            
            # Setup periodic updates
            self._setup_periodic_tasks()
            
            _LOGGER.info("✅ GPS handler setup completed for %s", self.dog_name)
            
        except Exception as e:
            _LOGGER.error("❌ Error setting up GPS handler for %s: %s", self.dog_name, e)
            raise GPSError(f"GPS handler setup failed: {e}")

    async def async_cleanup(self) -> None:
        """Clean up GPS handler."""
        # Remove all listeners
        for remove_listener in self._listeners:
            try:
                remove_listener()
            except Exception as e:
                _LOGGER.warning("Error removing GPS listener: %s", e)
        
        self._listeners.clear()
        _LOGGER.info("GPS handler cleanup completed for %s", self.dog_name)

    # ================================================================================
    # GPS SOURCE CONFIGURATION
    # ================================================================================

    async def _configure_gps_source(self) -> None:
        """Configure GPS source based on settings."""
        try:
            # Get GPS source configuration
            gps_config_entity = f"input_text.{self.dog_name}_gps_tracker_config"
            gps_config_state = self.hass.states.get(gps_config_entity)
            
            if gps_config_state and gps_config_state.state:
                try:
                    config_data = json.loads(gps_config_state.state)
                    self._gps_source_type = config_data.get("source_type", "manual")
                    self._gps_entity_id = config_data.get("entity_id")
                    self._auto_walk_detection = config_data.get("auto_walk_detection", False)
                    self._auto_walk_sensitivity = config_data.get("sensitivity", "medium")
                except (json.JSONDecodeError, TypeError):
                    _LOGGER.warning("Invalid GPS config for %s, using defaults", self.dog_name)
            
            # Setup GPS source tracking
            if self._gps_source_type == "device_tracker" and self._gps_entity_id:
                await self._setup_device_tracker_source()
            elif self._gps_source_type == "person" and self._gps_entity_id:
                await self._setup_person_source()
            elif self._gps_source_type == "manual":
                await self._setup_manual_source()
            
            _LOGGER.info("GPS source configured: %s for %s", self._gps_source_type, self.dog_name)
            
        except Exception as e:
            _LOGGER.error("Error configuring GPS source: %s", e)
            # Fallback to manual mode
            self._gps_source_type = "manual"

    async def _setup_device_tracker_source(self) -> None:
        """Setup device tracker as GPS source."""
        if not self._gps_entity_id:
            return
        
        @callback
        def device_tracker_updated(event: Event) -> None:
            """Handle device tracker updates."""
            self.hass.async_create_task(self._handle_device_tracker_update(event))
        
        # Track device tracker state changes
        remove_listener = async_track_state_change_event(
            self.hass, [self._gps_entity_id], device_tracker_updated
        )
        self._listeners.append(remove_listener)
        
        _LOGGER.info("Device tracker GPS source setup for %s: %s", self.dog_name, self._gps_entity_id)

    async def _setup_person_source(self) -> None:
        """Setup person entity as GPS source."""
        if not self._gps_entity_id:
            return
        
        @callback
        def person_updated(event: Event) -> None:
            """Handle person entity updates."""
            self.hass.async_create_task(self._handle_person_update(event))
        
        # Track person state changes
        remove_listener = async_track_state_change_event(
            self.hass, [self._gps_entity_id], person_updated
        )
        self._listeners.append(remove_listener)
        
        _LOGGER.info("Person GPS source setup for %s: %s", self.dog_name, self._gps_entity_id)

    async def _setup_manual_source(self) -> None:
        """Setup manual GPS updates."""
        # Track manual location updates
        location_entity = f"input_text.{self.dog_name}_current_location"
        
        @callback
        def location_updated(event: Event) -> None:
            """Handle manual location updates."""
            self.hass.async_create_task(self._handle_manual_location_update(event))
        
        if self.hass.states.get(location_entity):
            remove_listener = async_track_state_change_event(
                self.hass, [location_entity], location_updated
            )
            self._listeners.append(remove_listener)
        
        _LOGGER.info("Manual GPS source setup for %s", self.dog_name)

    # ================================================================================
    # GPS UPDATE HANDLERS
    # ================================================================================

    async def _handle_device_tracker_update(self, event: Event) -> None:
        """Handle device tracker GPS updates."""
        try:
            new_state = event.data.get("new_state")
            if not new_state or not new_state.attributes:
                return
            
            latitude = new_state.attributes.get("latitude")
            longitude = new_state.attributes.get("longitude")
            accuracy = new_state.attributes.get("gps_accuracy", 50)
            
            if latitude is not None and longitude is not None:
                await self.async_update_location(
                    latitude, longitude, accuracy, "device_tracker"
                )
                
        except Exception as e:
            _LOGGER.error("Error handling device tracker update for %s: %s", self.dog_name, e)

    async def _handle_person_update(self, event: Event) -> None:
        """Handle person entity GPS updates."""
        try:
            new_state = event.data.get("new_state")
            if not new_state or not new_state.attributes:
                return
            
            latitude = new_state.attributes.get("latitude")
            longitude = new_state.attributes.get("longitude")
            accuracy = new_state.attributes.get("gps_accuracy", 50)
            
            if latitude is not None and longitude is not None:
                await self.async_update_location(
                    latitude, longitude, accuracy, "person"
                )
                
        except Exception as e:
            _LOGGER.error("Error handling person update for %s: %s", self.dog_name, e)

    async def _handle_manual_location_update(self, event: Event) -> None:
        """Handle manual location updates."""
        try:
            new_state = event.data.get("new_state")
            if not new_state or not new_state.state:
                return
            
            # Parse coordinates from text field
            location_str = new_state.state
            if "," in location_str:
                try:
                    lat_str, lon_str = location_str.split(",", 1)
                    latitude = float(lat_str.strip())
                    longitude = float(lon_str.strip())
                    
                    await self.async_update_location(
                        latitude, longitude, 50, "manual"
                    )
                except (ValueError, IndexError) as e:
                    _LOGGER.warning("Invalid manual coordinates for %s: %s", self.dog_name, location_str)
                    
        except Exception as e:
            _LOGGER.error("Error handling manual location update for %s: %s", self.dog_name, e)

    # ================================================================================
    # CORE GPS PROCESSING
    # ================================================================================

    async def async_update_location(
        self, 
        latitude: float, 
        longitude: float, 
        accuracy: float = 50,
        source: str = "unknown"
    ) -> None:
        """Update GPS location and process movement."""
        try:
            if not validate_coordinates(latitude, longitude):
                raise InvalidCoordinates(f"Invalid coordinates: {latitude}, {longitude}")
            
            # Store previous location
            self._previous_location = self._current_location
            self._current_location = (latitude, longitude)
            self._accuracy = accuracy
            self._last_update = now()
            
            # Update entities
            await self._update_gps_entities()
            
            # Process movement
            await self._process_movement()
            
            # Check geofences
            await self._check_geofences()
            
            # Auto walk detection
            if self._auto_walk_detection:
                await self._auto_detect_walk()
            
            # Update statistics
            await self._update_gps_statistics()
            
            _LOGGER.debug("GPS updated for %s: %.6f,%.6f (accuracy: %.1fm, source: %s)", 
                         self.dog_name, latitude, longitude, accuracy, source)
            
        except Exception as e:
            _LOGGER.error("Error updating GPS location for %s: %s", self.dog_name, e)
            raise GPSError(f"GPS location update failed: {e}")

    async def _process_movement(self) -> None:
        """Process movement and calculate metrics."""
        if not self._current_location or not self._previous_location:
            return
        
        try:
            # Calculate distance moved
            distance_moved = calculate_distance(self._previous_location, self._current_location)
            
            # Calculate speed if we have timing
            if self._last_update and len(self._movement_history) > 0:
                time_diff = (self._last_update - self._movement_history[-1]["timestamp"]).total_seconds()
                if time_diff > 0:
                    self._speed = calculate_speed_kmh(distance_moved, time_diff)
            
            # Movement detection
            movement_threshold = GPS_CONFIG["movement_threshold"]
            if distance_moved >= movement_threshold:
                self._is_moving = True
                self._stationary_since = None
            else:
                if self._stationary_since is None:
                    self._stationary_since = self._last_update
                elif (self._last_update - self._stationary_since).total_seconds() >= GPS_CONFIG["stationary_time"]:
                    self._is_moving = False
            
            # Add to movement history
            self._movement_history.append({
                "timestamp": self._last_update,
                "location": self._current_location,
                "distance_moved": distance_moved,
                "speed": self._speed,
                "accuracy": self._accuracy
            })
            
            # Limit history size
            if len(self._movement_history) > 100:
                self._movement_history = self._movement_history[-50:]
            
            # Update walk tracking if active
            if self._walk_active:
                await self._update_walk_tracking(distance_moved)
            
        except Exception as e:
            _LOGGER.error("Error processing movement for %s: %s", self.dog_name, e)

    async def _update_walk_tracking(self, distance_moved: float) -> None:
        """Update active walk tracking."""
        try:
            if not self._walk_active or not self._current_location:
                return
            
            # Add distance to walk
            self._walk_distance += distance_moved / 1000  # Convert to km
            
            # Update max speed
            if self._speed > self._walk_max_speed:
                self._walk_max_speed = self._speed
            
            # Add point to route
            self._walk_route.append({
                "timestamp": self._last_update.isoformat(),
                "latitude": self._current_location[0],
                "longitude": self._current_location[1],
                "speed": self._speed,
                "accuracy": self._accuracy
            })
            
            # Calculate average speed
            if self._walk_start_time:
                walk_duration_hours = (self._last_update - self._walk_start_time).total_seconds() / 3600
                if walk_duration_hours > 0:
                    self._walk_avg_speed = self._walk_distance / walk_duration_hours
            
            # Update walk entities
            await self._update_walk_entities()
            
        except Exception as e:
            _LOGGER.error("Error updating walk tracking for %s: %s", self.dog_name, e)

    # ================================================================================
    # WALK MANAGEMENT
    # ================================================================================

    async def async_start_walk(self, walk_type: str = "normal") -> None:
        """Start walk tracking."""
        try:
            if self._walk_active:
                _LOGGER.warning("Walk already active for %s", self.dog_name)
                return
            
            self._walk_active = True
            self._walk_start_time = now()
            self._walk_route = []
            self._walk_distance = 0.0
            self._walk_max_speed = 0.0
            self._walk_avg_speed = 0.0
            
            # Add starting point
            if self._current_location:
                self._walk_route.append({
                    "timestamp": self._walk_start_time.isoformat(),
                    "latitude": self._current_location[0],
                    "longitude": self._current_location[1],
                    "speed": 0.0,
                    "accuracy": self._accuracy
                })
            
            # Update entities
            await safe_service_call(
                self.hass, "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self.dog_name}_walk_in_progress"}
            )
            
            await self._update_walk_entities()
            
            _LOGGER.info("🚶 Walk started for %s (type: %s)", self.dog_name, walk_type)
            
        except Exception as e:
            _LOGGER.error("Error starting walk for %s: %s", self.dog_name, e)

    async def async_end_walk(self) -> Dict[str, Any]:
        """End walk tracking and return statistics."""
        try:
            if not self._walk_active:
                _LOGGER.warning("No active walk for %s", self.dog_name)
                return {}
            
            walk_end_time = now()
            walk_duration = 0
            
            if self._walk_start_time:
                walk_duration = int((walk_end_time - self._walk_start_time).total_seconds() / 60)
            
            # Calculate calories burned (rough estimate)
            weight_entity = f"input_number.{self.dog_name}_weight"
            weight_state = self.hass.states.get(weight_entity)
            weight = float(weight_state.state) if weight_state else 15.0
            
            calories_burned = self._estimate_calories_burned(self._walk_distance, weight)
            
            # Create walk statistics
            walk_stats = {
                "start_time": self._walk_start_time.isoformat() if self._walk_start_time else None,
                "end_time": walk_end_time.isoformat(),
                "duration_minutes": walk_duration,
                "distance_km": round(self._walk_distance, 3),
                "max_speed_kmh": round(self._walk_max_speed, 1),
                "avg_speed_kmh": round(self._walk_avg_speed, 1),
                "calories_burned": calories_burned,
                "route_points": len(self._walk_route),
                "accuracy_avg": round(sum(p.get("accuracy", 50) for p in self._walk_route) / len(self._walk_route), 0) if self._walk_route else 50
            }
            
            # Reset walk state
            self._walk_active = False
            self._walk_start_time = None
            
            # Update statistics
            self._total_distance_today += self._walk_distance
            self._total_walks_today += 1
            self._calories_burned += calories_burned
            
            # Update entities
            await self._finalize_walk_entities(walk_stats)
            
            # Store route if significant
            if self._walk_distance >= 0.1:  # At least 100m
                await self._store_walk_route()
            
            _LOGGER.info("🏁 Walk ended for %s: %.2fkm in %d minutes", 
                        self.dog_name, self._walk_distance, walk_duration)
            
            return walk_stats
            
        except Exception as e:
            _LOGGER.error("Error ending walk for %s: %s", self.dog_name, e)
            return {}

    async def _auto_detect_walk(self) -> None:
        """Automatically detect walk start/end based on movement."""
        try:
            if not self._current_location or not self._home_location:
                return
            
            home_distance = calculate_distance(self._home_location, self._current_location)
            movement_threshold = GPS_CONFIG["walk_detection_distance"]
            
            # Auto start walk
            if not self._walk_active and home_distance > movement_threshold and self._is_moving:
                # Check if we've been moving for a while
                moving_time = 0
                if self._movement_history:
                    for entry in reversed(self._movement_history[-10:]):
                        if entry.get("distance_moved", 0) >= GPS_CONFIG["movement_threshold"]:
                            moving_time += 30  # Assume 30 second intervals
                        else:
                            break
                
                if moving_time >= 120:  # Moving for at least 2 minutes
                    await self.async_start_walk("auto_detected")
            
            # Auto end walk
            elif self._walk_active and not self._is_moving:
                # Check if we've been stationary near home
                if (home_distance <= movement_threshold and 
                    self._stationary_since and 
                    (now() - self._stationary_since).total_seconds() >= 300):  # 5 minutes stationary
                    
                    walk_stats = await self.async_end_walk()
                    if walk_stats.get("duration_minutes", 0) >= GPS_CONFIG["min_walk_duration"]:
                        _LOGGER.info("Auto-detected walk completed for %s", self.dog_name)
            
        except Exception as e:
            _LOGGER.error("Error in auto walk detection for %s: %s", self.dog_name, e)

    # ================================================================================
    # GEOFENCING
    # ================================================================================

    async def _setup_default_geofences(self) -> None:
        """Setup default geofences."""
        try:
            if not self._home_location:
                return
            
            # Home geofence
            home_radius_entity = f"input_number.{self.dog_name}_geofence_radius"
            home_radius_state = self.hass.states.get(home_radius_entity)
            home_radius = float(home_radius_state.state) if home_radius_state else GPS_CONFIG["home_zone_radius"]
            
            self._geofences["home"] = {
                "name": "Zuhause",
                "center": self._home_location,
                "radius": home_radius,
                "type": "safe_zone",
                "notify_enter": True,
                "notify_exit": True
            }
            
            # Initialize geofence status
            self._last_geofence_status["home"] = True  # Assume starting at home
            
            _LOGGER.info("Default geofences setup for %s: home (%.0fm radius)", 
                        self.dog_name, home_radius)
            
        except Exception as e:
            _LOGGER.error("Error setting up geofences for %s: %s", self.dog_name, e)

    async def _check_geofences(self) -> None:
        """Check all geofences and trigger notifications."""
        if not self._current_location:
            return
        
        try:
            for fence_id, fence_config in self._geofences.items():
                fence_center = fence_config["center"]
                fence_radius = fence_config["radius"]
                
                # Calculate distance to fence center
                distance = calculate_distance(fence_center, self._current_location)
                inside_fence = distance <= fence_radius
                
                # Check for status change
                previous_status = self._last_geofence_status.get(fence_id, False)
                
                if inside_fence != previous_status:
                    # Status changed
                    self._last_geofence_status[fence_id] = inside_fence
                    
                    # Send notifications
                    if inside_fence and fence_config.get("notify_enter", False):
                        await self._send_geofence_notification(fence_id, "entered")
                    elif not inside_fence and fence_config.get("notify_exit", False):
                        await self._send_geofence_notification(fence_id, "exited")
                    
                    # Update home distance entity
                    if fence_id == "home":
                        await safe_service_call(
                            self.hass, "input_number", "set_value",
                            {
                                "entity_id": f"input_number.{self.dog_name}_home_distance",
                                "value": int(distance)
                            }
                        )
            
        except Exception as e:
            _LOGGER.error("Error checking geofences for %s: %s", self.dog_name, e)

    async def _send_geofence_notification(self, fence_id: str, action: str) -> None:
        """Send geofence notification."""
        try:
            fence_config = self._geofences.get(fence_id, {})
            fence_name = fence_config.get("name", fence_id)
            
            if action == "entered":
                title = f"🏠 Sicherheitsbereich - {self.dog_name.title()}"
                message = f"{self.dog_name.title()} ist in '{fence_name}' angekommen"
            else:
                title = f"🚶 Sicherheitsbereich - {self.dog_name.title()}"
                message = f"{self.dog_name.title()} hat '{fence_name}' verlassen"
            
            # Send notification
            if self.hass.services.has_service("persistent_notification", "create"):
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": title,
                        "message": message,
                        "notification_id": f"geofence_{self.dog_name}_{fence_id}_{action}",
                    }
                )
            
            _LOGGER.info("Geofence notification sent for %s: %s %s", 
                        self.dog_name, fence_name, action)
            
        except Exception as e:
            _LOGGER.error("Error sending geofence notification for %s: %s", self.dog_name, e)

    # ================================================================================
    # ENTITY UPDATES
    # ================================================================================

    async def _update_gps_entities(self) -> None:
        """Update GPS-related entities."""
        if not self._current_location:
            return
        
        try:
            latitude, longitude = self._current_location
            
            # Update current location
            location_str = format_coordinates(latitude, longitude)
            await safe_service_call(
                self.hass, "input_text", "set_value",
                {
                    "entity_id": f"input_text.{self.dog_name}_current_location",
                    "value": location_str
                }
            )
            
            # Update GPS signal strength (based on accuracy)
            signal_strength = max(0, min(100, 100 - self._accuracy))
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {
                    "entity_id": f"input_number.{self.dog_name}_gps_signal_strength",
                    "value": signal_strength
                }
            )
            
            # Update GPS tracker status
            status_message = f"Active - {self._gps_source_type} (Accuracy: {self._accuracy:.0f}m)"
            await safe_service_call(
                self.hass, "input_text", "set_value",
                {
                    "entity_id": f"input_text.{self.dog_name}_gps_tracker_status",
                    "value": status_message
                }
            )
            
        except Exception as e:
            _LOGGER.error("Error updating GPS entities for %s: %s", self.dog_name, e)

    async def _update_walk_entities(self) -> None:
        """Update walk-related entities during active walk."""
        if not self._walk_active:
            return
        
        try:
            # Update current walk distance
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {
                    "entity_id": f"input_number.{self.dog_name}_current_walk_distance",
                    "value": round(self._walk_distance, 3)
                }
            )
            
            # Update current walk duration
            if self._walk_start_time:
                duration_minutes = int((now() - self._walk_start_time).total_seconds() / 60)
                await safe_service_call(
                    self.hass, "input_number", "set_value",
                    {
                        "entity_id": f"input_number.{self.dog_name}_current_walk_duration",
                        "value": duration_minutes
                    }
                )
            
            # Update current speed
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {
                    "entity_id": f"input_number.{self.dog_name}_current_walk_speed",
                    "value": round(self._speed, 1)
                }
            )
            
            # Update route (limited to prevent entity overflow)
            if len(self._walk_route) <= 50:  # Limit route points
                route_json = json.dumps(self._walk_route[-50:])  # Last 50 points
                await safe_service_call(
                    self.hass, "input_text", "set_value",
                    {
                        "entity_id": f"input_text.{self.dog_name}_current_walk_route",
                        "value": route_json[:1000]  # Limit length
                    }
                )
            
        except Exception as e:
            _LOGGER.error("Error updating walk entities for %s: %s", self.dog_name, e)

    async def _finalize_walk_entities(self, walk_stats: Dict[str, Any]) -> None:
        """Update entities after walk completion."""
        try:
            # Turn off walk in progress
            await safe_service_call(
                self.hass, "input_boolean", "turn_off",
                {"entity_id": f"input_boolean.{self.dog_name}_walk_in_progress"}
            )
            
            # Mark as walked today
            await safe_service_call(
                self.hass, "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self.dog_name}_walked_today"}
            )
            
            # Mark as outside
            await safe_service_call(
                self.hass, "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self.dog_name}_outside"}
            )
            
            # Increment walk counter
            await safe_service_call(
                self.hass, "counter", "increment",
                {"entity_id": f"counter.{self.dog_name}_walk_count"}
            )
            
            # Update last walk time
            await safe_service_call(
                self.hass, "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self.dog_name}_last_walk",
                    "datetime": now().isoformat()
                }
            )
            
            # Update daily totals
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {
                    "entity_id": f"input_number.{self.dog_name}_walk_distance_today",
                    "value": round(self._total_distance_today, 3)
                }
            )
            
            # Update walk duration
            duration = walk_stats.get("duration_minutes", 0)
            if duration > 0:
                await safe_service_call(
                    self.hass, "input_number", "set_value",
                    {
                        "entity_id": f"input_number.{self.dog_name}_daily_walk_duration",
                        "value": duration
                    }
                )
            
            # Update calories burned
            calories = walk_stats.get("calories_burned", 0)
            if calories > 0:
                await safe_service_call(
                    self.hass, "input_number", "set_value",
                    {
                        "entity_id": f"input_number.{self.dog_name}_calories_burned_walk",
                        "value": calories
                    }
                )
            
            # Reset current walk values
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {"entity_id": f"input_number.{self.dog_name}_current_walk_distance", "value": 0}
            )
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {"entity_id": f"input_number.{self.dog_name}_current_walk_duration", "value": 0}
            )
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {"entity_id": f"input_number.{self.dog_name}_current_walk_speed", "value": 0}
            )
            
        except Exception as e:
            _LOGGER.error("Error finalizing walk entities for %s: %s", self.dog_name, e)

    # ================================================================================
    # UTILITY METHODS
    # ================================================================================

    async def _load_home_coordinates(self) -> None:
        """Load home coordinates from entity or use defaults."""
        try:
            home_coords_entity = f"input_text.{self.dog_name}_home_coordinates"
            home_coords_state = self.hass.states.get(home_coords_entity)
            
            if home_coords_state and home_coords_state.state:
                try:
                    lat_str, lon_str = home_coords_state.state.split(",")
                    latitude = float(lat_str.strip())
                    longitude = float(lon_str.strip())
                    
                    if validate_coordinates(latitude, longitude):
                        self._home_location = (latitude, longitude)
                        _LOGGER.info("Home coordinates loaded for %s: %.6f,%.6f", 
                                   self.dog_name, latitude, longitude)
                        return
                except (ValueError, IndexError):
                    pass
            
            # Use default coordinates
            self._home_location = DEFAULT_HOME_COORDINATES
            
            # Save default to entity
            default_coords_str = format_coordinates(*DEFAULT_HOME_COORDINATES)
            await safe_service_call(
                self.hass, "input_text", "set_value",
                {
                    "entity_id": home_coords_entity,
                    "value": default_coords_str
                }
            )
            
            _LOGGER.info("Default home coordinates set for %s: %.6f,%.6f", 
                        self.dog_name, *DEFAULT_HOME_COORDINATES)
            
        except Exception as e:
            _LOGGER.error("Error loading home coordinates for %s: %s", self.dog_name, e)
            self._home_location = DEFAULT_HOME_COORDINATES

    def _setup_periodic_tasks(self) -> None:
        """Setup periodic GPS tasks."""
        # GPS health check every 5 minutes
        @callback
        def gps_health_check(time) -> None:
            """Periodic GPS health check."""
            self.hass.async_create_task(self._gps_health_check())
        
        remove_listener = async_track_time_interval(
            self.hass, gps_health_check, timedelta(minutes=5)
        )
        self._listeners.append(remove_listener)
        
        # Daily statistics reset at midnight
        @callback
        def daily_reset(time) -> None:
            """Daily statistics reset."""
            self.hass.async_create_task(self._daily_statistics_reset())
        
        remove_listener = async_track_time_interval(
            self.hass, daily_reset, timedelta(days=1)
        )
        self._listeners.append(remove_listener)

    async def _gps_health_check(self) -> None:
        """Perform GPS health check."""
        try:
            current_time = now()
            
            # Check if GPS data is stale
            if self._last_update:
                time_since_update = (current_time - self._last_update).total_seconds()
                
                if time_since_update > 600:  # 10 minutes without update
                    # GPS signal lost
                    await safe_service_call(
                        self.hass, "input_number", "set_value",
                        {
                            "entity_id": f"input_number.{self.dog_name}_gps_signal_strength",
                            "value": 0
                        }
                    )
                    
                    await safe_service_call(
                        self.hass, "input_text", "set_value",
                        {
                            "entity_id": f"input_text.{self.dog_name}_gps_tracker_status",
                            "value": f"Signal verloren - Letztes Update: {self._last_update.strftime('%H:%M')}"
                        }
                    )
                    
                    # Send notification
                    if self.hass.services.has_service("persistent_notification", "create"):
                        await self.hass.services.async_call(
                            "persistent_notification", "create",
                            {
                                "title": f"📡 GPS-Signal verloren - {self.dog_name.title()}",
                                "message": f"Kein GPS-Update seit {int(time_since_update/60)} Minuten",
                                "notification_id": f"gps_lost_{self.dog_name}",
                            }
                        )
                    
                    _LOGGER.warning("GPS signal lost for %s - %d seconds since last update", 
                                  self.dog_name, time_since_update)
            
        except Exception as e:
            _LOGGER.error("Error in GPS health check for %s: %s", self.dog_name, e)

    async def _daily_statistics_reset(self) -> None:
        """Reset daily GPS statistics."""
        try:
            self._total_distance_today = 0.0
            self._total_walks_today = 0
            self._calories_burned = 0
            
            # Reset daily entities
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {"entity_id": f"input_number.{self.dog_name}_walk_distance_today", "value": 0}
            )
            
            _LOGGER.info("Daily GPS statistics reset for %s", self.dog_name)
            
        except Exception as e:
            _LOGGER.error("Error resetting daily statistics for %s: %s", self.dog_name, e)

    async def _update_gps_statistics(self) -> None:
        """Update GPS-related statistics."""
        try:
            # Update weekly distance (simplified - would need more complex tracking)
            current_weekly = self._total_distance_today * 7  # Rough estimate
            await safe_service_call(
                self.hass, "input_number", "set_value",
                {
                    "entity_id": f"input_number.{self.dog_name}_walk_distance_weekly",
                    "value": round(current_weekly, 1)
                }
            )
            
        except Exception as e:
            _LOGGER.error("Error updating GPS statistics for %s: %s", self.dog_name, e)

    async def _store_walk_route(self) -> None:
        """Store completed walk route."""
        try:
            if not self._walk_route:
                return
            
            # Create simplified route for storage
            simplified_route = []
            for i, point in enumerate(self._walk_route):
                # Store every 5th point to reduce data size
                if i % 5 == 0 or i == len(self._walk_route) - 1:
                    simplified_route.append({
                        "lat": point["latitude"],
                        "lon": point["longitude"],
                        "time": point["timestamp"][:16],  # Shortened timestamp
                        "speed": round(point.get("speed", 0), 1)
                    })
            
            # Store in favorite routes if significant
            if len(simplified_route) >= 10:  # At least 10 points
                routes_entity = f"input_text.{self.dog_name}_favorite_walk_routes"
                routes_state = self.hass.states.get(routes_entity)
                
                current_routes = []
                if routes_state and routes_state.state:
                    try:
                        current_routes = json.loads(routes_state.state)
                        if not isinstance(current_routes, list):
                            current_routes = []
                    except json.JSONDecodeError:
                        current_routes = []
                
                # Add new route
                new_route = {
                    "date": now().strftime("%Y-%m-%d"),
                    "distance": round(self._walk_distance, 2),
                    "duration": int((now() - self._walk_start_time).total_seconds() / 60) if self._walk_start_time else 0,
                    "points": simplified_route[:20]  # Limit to 20 points
                }
                
                current_routes.append(new_route)
                
                # Keep only last 10 routes
                if len(current_routes) > 10:
                    current_routes = current_routes[-10:]
                
                # Store back
                routes_json = json.dumps(current_routes)
                if len(routes_json) <= 1000:  # Respect entity limit
                    await safe_service_call(
                        self.hass, "input_text", "set_value",
                        {
                            "entity_id": routes_entity,
                            "value": routes_json
                        }
                    )
            
        except Exception as e:
            _LOGGER.error("Error storing walk route for %s: %s", self.dog_name, e)

    def _estimate_calories_burned(self, distance_km: float, weight_kg: float) -> int:
        """Estimate calories burned during walk."""
        try:
            # Basic formula: calories = distance(km) * weight(kg) * 0.8
            # This is a rough approximation for dogs
            base_calories = distance_km * weight_kg * 0.8
            
            # Adjust for walk intensity based on average speed
            if self._walk_avg_speed > 6:  # Fast walk/run
                intensity_multiplier = 1.4
            elif self._walk_avg_speed > 4:  # Normal pace
                intensity_multiplier = 1.0
            else:  # Slow walk
                intensity_multiplier = 0.7
            
            total_calories = base_calories * intensity_multiplier
            return max(1, int(total_calories))
            
        except Exception:
            return int(distance_km * 10)  # Fallback estimate

    # ================================================================================
    # PUBLIC API METHODS
    # ================================================================================

    def get_current_location(self) -> Optional[Tuple[float, float]]:
        """Get current GPS location."""
        return self._current_location

    def get_home_location(self) -> Optional[Tuple[float, float]]:
        """Get home location."""
        return self._home_location

    def is_walk_active(self) -> bool:
        """Check if walk is currently active."""
        return self._walk_active

    def get_walk_stats(self) -> Dict[str, Any]:
        """Get current walk statistics."""
        if not self._walk_active:
            return {}
        
        duration = 0
        if self._walk_start_time:
            duration = int((now() - self._walk_start_time).total_seconds() / 60)
        
        return {
            "active": self._walk_active,
            "duration_minutes": duration,
            "distance_km": round(self._walk_distance, 3),
            "current_speed_kmh": round(self._speed, 1),
            "max_speed_kmh": round(self._walk_max_speed, 1),
            "avg_speed_kmh": round(self._walk_avg_speed, 1),
            "route_points": len(self._walk_route)
        }

    def get_gps_status(self) -> Dict[str, Any]:
        """Get GPS system status."""
        return {
            "source_type": self._gps_source_type,
            "entity_id": self._gps_entity_id,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "accuracy": self._accuracy,
            "is_moving": self._is_moving,
            "current_speed": self._speed,
            "home_location": self._home_location,
            "geofences_count": len(self._geofences),
            "auto_walk_detection": self._auto_walk_detection
        }

    async def async_set_home_location(self, latitude: float, longitude: float) -> None:
        """Set new home location."""
        if not validate_coordinates(latitude, longitude):
            raise InvalidCoordinates("Invalid home coordinates")
        
        self._home_location = (latitude, longitude)
        
        # Update entity
        coords_str = format_coordinates(latitude, longitude)
        await safe_service_call(
            self.hass, "input_text", "set_value",
            {
                "entity_id": f"input_text.{self.dog_name}_home_coordinates",
                "value": coords_str
            }
        )
        
        # Update geofences
        await self._setup_default_geofences()
        
        _LOGGER.info("Home location updated for %s: %.6f,%.6f", self.dog_name, latitude, longitude)