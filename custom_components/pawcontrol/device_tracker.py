"""Device tracker platform for PawControl integration.

This module provides GPS-based device tracking functionality for dogs in the
Paw Control integration. It creates device tracker entities that show the
current location of each dog based on GPS coordinates, geofencing status,
and movement patterns.

Features:
- Real-time GPS location tracking
- Geofencing with home/away detection
- Location accuracy reporting
- Movement history and statistics
- Zone-based location naming
- Comprehensive error handling
- Full async operation with type safety

The device tracker integrates with Home Assistant's device tracking system
to provide location awareness for automation and presence detection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_MODULES,
    COORDINATE_PRECISION,
    DEFAULT_SAFE_ZONE_RADIUS,
    DOMAIN,
    GPS_MIN_ACCURACY,
    MODULE_GPS,
    PARALLEL_UPDATES,
)
from .entity import PawControlDeviceTrackerEntity

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator
    from .types import DogData, GPSData, LocationData

_LOGGER = logging.getLogger(__name__)

# Set parallel updates to 0 for real-time location updates
PARALLEL_UPDATES = 0

# ==============================================================================
# PLATFORM SETUP
# ==============================================================================

async def async_setup_entry(
    hass: HomeAssistant, 
    entry: ConfigEntry, 
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl device tracker entities from config entry.
    
    Creates device tracker entities for each dog that has GPS module enabled.
    Validates coordinator availability and dog configurations before creating
    entities to ensure reliable operation.
    
    Args:
        hass: Home Assistant instance
        entry: The config entry for this integration
        async_add_entities: Callback to add new entities
        
    Raises:
        PlatformNotReady: If coordinator is not available or has no data
    """
    try:
        # Get coordinator from runtime data
        coordinator: PawControlCoordinator = entry.runtime_data.coordinator
        
        # Ensure coordinator has valid data
        if not coordinator.last_update_success:
            _LOGGER.debug("Device tracker setup: coordinator refresh needed")
            await coordinator.async_refresh()
            
            if not coordinator.last_update_success:
                _LOGGER.error("Device tracker setup failed: coordinator unavailable")
                raise PlatformNotReady("Coordinator not ready for device tracker setup")

        # Get dog configurations
        dogs = entry.options.get(CONF_DOGS, [])
        if not dogs:
            _LOGGER.info("No dogs configured, skipping device tracker setup")
            return

        # Create device tracker entities for GPS-enabled dogs
        entities = []
        
        for dog_config in dogs:
            dog_id = dog_config.get(CONF_DOG_ID)
            if not dog_id:
                _LOGGER.warning("Dog configuration missing dog_id, skipping")
                continue
                
            # Check if GPS module is enabled for this dog
            modules = dog_config.get(CONF_MODULES, {})
            if not modules.get(MODULE_GPS, False):
                _LOGGER.debug("GPS module disabled for dog %s, skipping tracker", dog_id)
                continue
                
            # Validate dog exists in coordinator data
            if dog_id not in coordinator._dog_data:
                _LOGGER.warning(
                    "Dog %s not found in coordinator data, will be added when available",
                    dog_id,
                )
                
            # Create device tracker entity
            try:
                entity = PawDeviceTracker(coordinator, entry, dog_id)
                entities.append(entity)
                _LOGGER.debug("Created device tracker for dog: %s", dog_id)
                
            except Exception as err:
                _LOGGER.error(
                    "Failed to create device tracker for dog %s: %s",
                    dog_id,
                    err,
                )

        # Add entities if any were created
        if entities:
            _LOGGER.info("Adding %d device tracker entities", len(entities))
            async_add_entities(entities, update_before_add=True)
        else:
            _LOGGER.info("No device tracker entities to add")
            
    except Exception as err:
        _LOGGER.error("Device tracker platform setup failed: %s", err)
        raise PlatformNotReady(f"Device tracker setup error: {err}") from err

# ==============================================================================
# DEVICE TRACKER ENTITY
# ==============================================================================

class PawDeviceTracker(PawControlDeviceTrackerEntity, TrackerEntity):
    """Device tracker entity for PawControl dog location tracking.
    
    Provides real-time GPS location tracking for a dog with features including:
    - GPS coordinate reporting with accuracy
    - Home/away detection based on geofencing
    - Location name resolution
    - Movement statistics and history
    - Zone-based presence detection
    
    The entity integrates with Home Assistant's device tracking system and
    supports all standard device tracker features including map display,
    automation triggers, and zone detection.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the PawControl device tracker.
        
        Creates a device tracker entity that monitors the GPS location of a
        specific dog. The entity provides real-time location updates and
        integrates with Home Assistant's presence detection system.
        
        Args:
            coordinator: The data update coordinator
            entry: Config entry for this integration instance
            dog_id: Unique identifier for the dog to track
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="device_tracker",
            translation_key="dog_location",
            icon="mdi:crosshairs-gps",
        )
        
        # Initialize device tracker specific attributes
        self._attr_force_update = True  # Always update for location changes
        self._attr_source_type = SourceType.GPS
        
        # Cache frequently accessed data
        self._last_location_update: str | None = None
        self._last_coordinates: tuple[float, float] | None = None
        
        _LOGGER.debug("Initialized device tracker for dog: %s", dog_id)

    # ==========================================================================
    # DEVICE TRACKER PROPERTIES
    # ==========================================================================

    @property
    def latitude(self) -> float | None:
        """Return the latitude value of the dog's current location.
        
        Gets the current GPS latitude from the coordinator data. Returns None
        if no valid GPS coordinates are available or if GPS accuracy is too low.
        
        Returns:
            Latitude coordinate or None if unavailable
        """
        try:
            location_data = self._get_location_data()
            if not location_data:
                return None
                
            gps_data = self._get_gps_data(location_data)
            if not gps_data:
                return None
                
            # Check if we have current GPS coordinates
            latitude = gps_data.get("current_latitude")
            if latitude is not None and self._is_coordinate_valid(latitude, "latitude"):
                return round(float(latitude), COORDINATE_PRECISION)
                
            # Fall back to last known coordinates if current not available
            last_latitude = gps_data.get("last_known_latitude")
            if last_latitude is not None and self._is_coordinate_valid(last_latitude, "latitude"):
                return round(float(last_latitude), COORDINATE_PRECISION)
                
            # If no GPS coordinates, check if at home location
            if location_data.get("is_home", False):
                home_lat = location_data.get("home_latitude")
                if home_lat is not None:
                    return round(float(home_lat), COORDINATE_PRECISION)
                    
            return None
            
        except (ValueError, TypeError) as err:
            _LOGGER.debug("Error getting latitude for %s: %s", self.dog_id, err)
            return None

    @property
    def longitude(self) -> float | None:
        """Return the longitude value of the dog's current location.
        
        Gets the current GPS longitude from the coordinator data. Returns None
        if no valid GPS coordinates are available or if GPS accuracy is too low.
        
        Returns:
            Longitude coordinate or None if unavailable
        """
        try:
            location_data = self._get_location_data()
            if not location_data:
                return None
                
            gps_data = self._get_gps_data(location_data)
            if not gps_data:
                return None
                
            # Check if we have current GPS coordinates
            longitude = gps_data.get("current_longitude")
            if longitude is not None and self._is_coordinate_valid(longitude, "longitude"):
                return round(float(longitude), COORDINATE_PRECISION)
                
            # Fall back to last known coordinates if current not available
            last_longitude = gps_data.get("last_known_longitude")
            if last_longitude is not None and self._is_coordinate_valid(last_longitude, "longitude"):
                return round(float(last_longitude), COORDINATE_PRECISION)
                
            # If no GPS coordinates, check if at home location
            if location_data.get("is_home", False):
                home_lon = location_data.get("home_longitude")
                if home_lon is not None:
                    return round(float(home_lon), COORDINATE_PRECISION)
                    
            return None
            
        except (ValueError, TypeError) as err:
            _LOGGER.debug("Error getting longitude for %s: %s", self.dog_id, err)
            return None

    @property
    def location_accuracy(self) -> int | None:
        """Return the location accuracy of the device in meters.
        
        Gets the GPS accuracy from the coordinator data. Returns None if no
        accuracy information is available or if accuracy is below threshold.
        
        Returns:
            GPS accuracy in meters or None if unavailable
        """
        try:
            location_data = self._get_location_data()
            if not location_data:
                return None
                
            gps_data = self._get_gps_data(location_data)
            if not gps_data:
                return None
                
            # Get current accuracy
            accuracy = gps_data.get("current_accuracy")
            if accuracy is not None:
                accuracy_value = int(float(accuracy))
                
                # Only return accuracy if it meets minimum standards
                if accuracy_value <= GPS_MIN_ACCURACY:
                    return accuracy_value
                    
            # Check if we're at home and return default home accuracy
            if location_data.get("is_home", False):
                return DEFAULT_SAFE_ZONE_RADIUS // 2  # Half of safe zone radius
                
            return None
            
        except (ValueError, TypeError) as err:
            _LOGGER.debug("Error getting location accuracy for %s: %s", self.dog_id, err)
            return None

    @property
    def location_name(self) -> str | None:
        """Return a location name for the current location of the device.
        
        Provides a human-readable name for the dog's current location based on
        geofencing and zone detection. Returns None for unknown locations to
        let Home Assistant determine zone names.
        
        Returns:
            Location name string or None for zone-based detection
        """
        try:
            location_data = self._get_location_data()
            if not location_data:
                return None
                
            # Check specific location states
            current_location = location_data.get("current_location", "unknown")
            
            if current_location == "home":
                return "Home"
            elif current_location in ["away", "unknown"]:
                # Let Home Assistant determine zone-based location
                return None
            elif isinstance(current_location, str) and current_location:
                # Return custom location name if available
                return current_location
                
            # Check geofencing status
            if location_data.get("is_home", False):
                return "Home"
            elif location_data.get("is_away", False):
                return None  # Let HA determine based on zones
                
            return None
            
        except Exception as err:
            _LOGGER.debug("Error getting location name for %s: %s", self.dog_id, err)
            return None

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device tracker.
        
        Returns:
            GPS source type for location tracking
        """
        return SourceType.GPS

    @property
    def battery_level(self) -> int | None:
        """Return the battery level of the GPS device.
        
        Gets battery information from GPS device if available.
        
        Returns:
            Battery level percentage or None if unavailable
        """
        try:
            location_data = self._get_location_data()
            if not location_data:
                return None
                
            gps_data = self._get_gps_data(location_data)
            if not gps_data:
                return None
                
            battery_level = gps_data.get("battery_level")
            if battery_level is not None:
                return max(0, min(100, int(float(battery_level))))
                
            return None
            
        except (ValueError, TypeError) as err:
            _LOGGER.debug("Error getting battery level for %s: %s", self.dog_id, err)
            return None

    # ==========================================================================
    # ENTITY STATE AND ATTRIBUTES
    # ==========================================================================

    @property
    def available(self) -> bool:
        """Return True if the device tracker is available.
        
        A device tracker is considered available if:
        1. The base entity is available
        2. GPS module is enabled for this dog
        3. Location data exists
        
        Returns:
            True if entity is available, False otherwise
        """
        if not super().available:
            return False
            
        # Check if GPS module is enabled
        dog_config = self._get_dog_config()
        if not dog_config:
            return False
            
        modules = dog_config.get(CONF_MODULES, {})
        if not modules.get(MODULE_GPS, False):
            return False
            
        # Check if location data is available
        location_data = self._get_location_data()
        return location_data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes for the device tracker.
        
        Provides comprehensive location and movement information including:
        - Distance from home
        - GPS accuracy and timing
        - Daily movement statistics
        - Battery status
        - Geofencing information
        
        Returns:
            Dictionary of additional state attributes
        """
        try:
            # Get base attributes
            attributes = dict(super().extra_state_attributes or {})
            
            # Get location data
            location_data = self._get_location_data()
            if not location_data:
                return attributes
                
            gps_data = self._get_gps_data(location_data)
            
            # Add location-specific attributes
            attributes.update({
                "gps_enabled": True,
                "is_home": location_data.get("is_home", False),
                "is_away": location_data.get("is_away", False),
                "safe_zone_radius": location_data.get("safe_zone_radius", DEFAULT_SAFE_ZONE_RADIUS),
            })
            
            # Add distance information
            if distance := location_data.get("distance_from_home"):
                attributes["distance_from_home"] = round(float(distance), 1)
                
            # Add GPS-specific attributes
            if gps_data:
                if last_update := gps_data.get("last_gps_update"):
                    attributes["last_gps_update"] = last_update
                    
                if speed := gps_data.get("current_speed"):
                    attributes["speed"] = round(float(speed), 1)
                    
                if altitude := gps_data.get("current_altitude"):
                    attributes["altitude"] = round(float(altitude), 1)
                    
                if heading := gps_data.get("current_heading"):
                    attributes["heading"] = round(float(heading), 1)
                    
                # Add battery information
                if battery := gps_data.get("battery_level"):
                    attributes["battery_level"] = int(float(battery))
                    
            # Add daily statistics
            daily_stats = location_data.get("daily_stats", {})
            attributes.update({
                "enters_today": daily_stats.get("enters_today", 0),
                "leaves_today": daily_stats.get("leaves_today", 0),
                "time_inside_today_min": daily_stats.get("time_inside_today_min", 0),
                "time_outside_today_min": daily_stats.get("time_outside_today_min", 0),
                "total_distance_today_m": daily_stats.get("total_distance_today_m", 0),
            })
            
            # Add movement status
            attributes["is_moving"] = location_data.get("is_moving", False)
            attributes["location_source"] = location_data.get("source", "gps")
            
            return attributes
            
        except Exception as err:
            _LOGGER.error(
                "Error getting device tracker attributes for %s: %s",
                self.dog_id,
                err,
            )
            return dict(super().extra_state_attributes or {})

    # ==========================================================================
    # DATA ACCESS METHODS
    # ==========================================================================

    def _get_location_data(self) -> LocationData | None:
        """Get location data for this dog from coordinator.
        
        Retrieves the complete location data structure for the dog including
        GPS coordinates, geofencing status, and movement information.
        
        Returns:
            Location data dictionary or None if unavailable
        """
        try:
            dog_data: DogData = self.coordinator.get_dog_data(self.dog_id)
            if not dog_data:
                return None
                
            return dog_data.get("location")
            
        except Exception as err:
            _LOGGER.debug("Error getting location data for %s: %s", self.dog_id, err)
            return None

    def _get_gps_data(self, location_data: LocationData) -> GPSData | None:
        """Get GPS-specific data from location data.
        
        Extracts GPS coordinates, accuracy, and device information from the
        location data structure.
        
        Args:
            location_data: Complete location data for the dog
            
        Returns:
            GPS data dictionary or None if unavailable
        """
        try:
            if not location_data:
                return None
                
            return location_data.get("gps")
            
        except Exception as err:
            _LOGGER.debug("Error getting GPS data for %s: %s", self.dog_id, err)
            return None

    def _is_coordinate_valid(self, coordinate: float, coord_type: str) -> bool:
        """Validate GPS coordinate values.
        
        Checks if a GPS coordinate is within valid ranges for latitude or
        longitude values.
        
        Args:
            coordinate: The coordinate value to validate
            coord_type: Either "latitude" or "longitude"
            
        Returns:
            True if coordinate is valid, False otherwise
        """
        try:
            if coord_type == "latitude":
                return -90.0 <= coordinate <= 90.0
            elif coord_type == "longitude":
                return -180.0 <= coordinate <= 180.0
            else:
                return False
                
        except (TypeError, ValueError):
            return False

    # ==========================================================================
    # STATE MANAGEMENT
    # ==========================================================================

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator data updates.
        
        Processes location data updates and triggers entity state updates
        when GPS coordinates or location status changes.
        """
        try:
            # Get current location data
            location_data = self._get_location_data()
            if not location_data:
                super()._handle_coordinator_update()
                return
                
            # Check if location has changed significantly
            current_coordinates = None
            if self.latitude is not None and self.longitude is not None:
                current_coordinates = (self.latitude, self.longitude)
                
            # Update cached coordinates if changed
            if current_coordinates != self._last_coordinates:
                self._last_coordinates = current_coordinates
                _LOGGER.debug(
                    "Location updated for %s: %s",
                    self.dog_id,
                    current_coordinates,
                )
                
            # Update last location update timestamp
            gps_data = self._get_gps_data(location_data)
            if gps_data:
                last_update = gps_data.get("last_gps_update")
                if last_update != self._last_location_update:
                    self._last_location_update = last_update
                    
            super()._handle_coordinator_update()
            
        except Exception as err:
            _LOGGER.error(
                "Error handling coordinator update for device tracker %s: %s",
                self.dog_id,
                err,
            )
            super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant.
        
        Performs initialization tasks when the entity is first added to the
        Home Assistant entity registry.
        """
        await super().async_added_to_hass()
        _LOGGER.info("Device tracker added for dog: %s", self.dog_id)

    async def async_will_remove_from_hass(self) -> None:
        """Called when entity will be removed from Home Assistant.
        
        Performs cleanup tasks when the entity is being removed from the
        Home Assistant entity registry.
        """
        await super().async_will_remove_from_hass()
        _LOGGER.info("Device tracker removed for dog: %s", self.dog_id)
