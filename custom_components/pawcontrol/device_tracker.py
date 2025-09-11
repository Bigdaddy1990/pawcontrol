"""Device tracker platform for Paw Control integration.

This module provides GPS tracking and location monitoring for dogs through
device tracker entities. It supports real-time location tracking, geofencing,
route recording, and integration with Home Assistant's map and zone features.
Designed to meet Home Assistant's Platinum quality standards.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    STATE_HOME,
    STATE_NOT_HOME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_GPS,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Type aliases for better code readability
LocationTuple = tuple[float, float]  # (latitude, longitude)
AttributeDict = dict[str, Any]

# GPS tracking constants
DEFAULT_GPS_ACCURACY = 100  # meters
HOME_ZONE_RADIUS = 100  # meters
LOCATION_UPDATE_THRESHOLD = 10  # meters
BATTERY_LOW_THRESHOLD = 20  # percent
MAX_GPS_AGE = timedelta(minutes=30)  # Maximum age for GPS data


async def _async_add_entities_in_batches(
    async_add_entities_func,
    entities: list[PawControlDeviceTracker],
    batch_size: int = 8,
    delay_between_batches: float = 0.1,
) -> None:
    """Add device tracker entities in small batches to prevent Entity Registry overload.

    The Entity Registry logs warnings when >200 messages occur rapidly.
    By batching entities and adding delays, we prevent registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of device tracker entities to add
        batch_size: Number of entities per batch (default: 8)
        delay_between_batches: Seconds to wait between batches (default: 0.1s)
    """
    total_entities = len(entities)

    _LOGGER.debug(
        "Adding %d device tracker entities in batches of %d to prevent Registry overload",
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
        batch = entities[i: i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            "Processing device tracker batch %d/%d with %d entities",
            batch_num,
            total_batches,
            len(batch),
        )

        # Add batch without update_before_add to reduce Registry load
        async_add_entities_func(batch, update_before_add=False)

        # Small delay between batches to prevent Registry flooding
        if i + batch_size < total_entities:  # No delay after last batch
            await asyncio.sleep(delay_between_batches)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control device tracker platform.

    Creates device tracker entities for all dogs that have GPS tracking
    enabled. Each dog gets a dedicated device tracker for real-time
    location monitoring and zone detection.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry containing dog configurations
        async_add_entities: Callback to add device tracker entities
    """
    runtime_data = getattr(entry, "runtime_data", None)

    if runtime_data:
        coordinator: PawControlCoordinator = runtime_data["coordinator"]
        dogs: list[dict[str, Any]] = runtime_data.get("dogs", [])
    else:
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        dogs = entry.data.get(CONF_DOGS, [])

    entities: list[PawControlDeviceTracker] = []

    # Create device tracker entities for dogs with GPS enabled
    for dog in dogs:
        dog_id: str = dog[CONF_DOG_ID]
        dog_name: str = dog[CONF_DOG_NAME]
        modules: dict[str, bool] = dog.get("modules", {})

        # Only create device tracker if GPS module is enabled
        if modules.get(MODULE_GPS, False):
            _LOGGER.debug(
                "Creating device tracker for dog: %s (%s)", dog_name, dog_id)
            entities.append(PawControlDeviceTracker(
                coordinator, dog_id, dog_name))

    if entities:
        # Add entities in smaller batches to prevent Entity Registry overload
        # With GPS device tracker entities, batching prevents Registry flooding
        await _async_add_entities_in_batches(async_add_entities, entities, batch_size=8)

        _LOGGER.info(
            "Created %d device tracker entities for GPS-enabled dogs using batched approach",
            len(entities),
        )
    else:
        _LOGGER.debug("No GPS-enabled dogs found, no device trackers created")


class PawControlDeviceTracker(
    CoordinatorEntity[PawControlCoordinator], TrackerEntity, RestoreEntity
):
    """Device tracker entity for dog GPS location tracking.

    This entity provides comprehensive GPS tracking functionality including
    real-time location updates, zone detection, battery monitoring, and
    movement tracking. It integrates seamlessly with Home Assistant's
    mapping and automation features.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
    ) -> None:
        """Initialize the device tracker entity.

        Args:
            coordinator: Data coordinator for updates
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
        """
        super().__init__(coordinator)

        self._dog_id = dog_id
        self._dog_name = dog_name

        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_gps"
        self._attr_name = f"{dog_name} GPS"
        self._attr_icon = "mdi:dog"

        # Device info for proper grouping - HA 2025.8+ compatible with configuration_url
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog_id)},
            "name": dog_name,
            "manufacturer": "Paw Control",
            "model": "Smart Dog GPS Tracker",
            "sw_version": "1.0.0",
            "configuration_url": "https://github.com/BigDaddy1990/pawcontrol",
        }

        # Internal state
        self._last_known_location: LocationTuple | None = None
        self._last_update_time: datetime | None = None
        self._location_history: list[dict[str, Any]] = []
        self._current_zone: str | None = None

        # Restore previous state
        self._restored_data: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant.

        Restores previous state and initializes the tracker.
        """
        await super().async_added_to_hass()

        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state:
            self._restored_data = {
                "latitude": last_state.attributes.get(ATTR_LATITUDE),
                "longitude": last_state.attributes.get(ATTR_LONGITUDE),
                "gps_accuracy": last_state.attributes.get(ATTR_GPS_ACCURACY),
                "battery_level": last_state.attributes.get(ATTR_BATTERY_LEVEL),
                "source_type": last_state.attributes.get("source_type"),
                "last_seen": last_state.attributes.get("last_seen"),
            }

            # Restore location if available
            lat = self._restored_data.get("latitude")
            lon = self._restored_data.get("longitude")
            if lat is not None and lon is not None:
                self._last_known_location = (float(lat), float(lon))

            _LOGGER.debug(
                "Restored previous state for %s GPS tracker", self._dog_name)

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device tracker.

        Returns:
            GPS source type for location tracking
        """
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return the latitude of the dog's current location.

        Returns:
            Latitude coordinate or None if unknown
        """
        gps_data = self._get_gps_data()
        if gps_data and gps_data.get("latitude") is not None:
            return float(gps_data["latitude"])

        # Fall back to restored data if no current data
        if self._restored_data.get("latitude") is not None:
            return float(self._restored_data["latitude"])

        return None

    @property
    def longitude(self) -> float | None:
        """Return the longitude of the dog's current location.

        Returns:
            Longitude coordinate or None if unknown
        """
        gps_data = self._get_gps_data()
        if gps_data and gps_data.get("longitude") is not None:
            return float(gps_data["longitude"])

        # Fall back to restored data if no current data
        if self._restored_data.get("longitude") is not None:
            return float(self._restored_data["longitude"])

        return None

    @property
    def location_accuracy(self) -> int:
        """Return the GPS accuracy in meters.

        Returns:
            GPS accuracy in meters
        """
        gps_data = self._get_gps_data()
        if gps_data and gps_data.get("accuracy") is not None:
            return int(gps_data["accuracy"])

        # Fall back to restored data
        if self._restored_data.get("gps_accuracy") is not None:
            return int(self._restored_data["gps_accuracy"])

        return DEFAULT_GPS_ACCURACY

    @property
    def battery_level(self) -> int | None:
        """Return the battery level of the GPS tracker.

        Returns:
            Battery level percentage or None if unknown
        """
        gps_data = self._get_gps_data()
        if gps_data and gps_data.get("battery_level") is not None:
            return int(gps_data["battery_level"])

        # Fall back to restored data
        if self._restored_data.get("battery_level") is not None:
            return int(self._restored_data["battery_level"])

        return None

    @property
    def location_name(self) -> str | None:
        """Return the name of the current location/zone.

        Determines the current zone based on GPS coordinates and
        configured Home Assistant zones.

        Returns:
            Zone name or None if not in a known zone
        """
        current_lat = self.latitude
        current_lon = self.longitude

        if current_lat is None or current_lon is None:
            return None

        # Check if at home
        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude

        home_distance = distance(current_lat, current_lon, home_lat, home_lon)
        if home_distance <= HOME_ZONE_RADIUS:
            return STATE_HOME

        # Check other configured zones
        zone_name = self._determine_zone_from_coordinates(
            current_lat, current_lon)
        if zone_name:
            return zone_name

        return STATE_NOT_HOME

    def _determine_zone_from_coordinates(self, lat: float, lon: float) -> str | None:
        """Determine zone name from coordinates.

        Checks if the given coordinates fall within any configured
        Home Assistant zones.

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate

        Returns:
            Zone name or None if not in any zone
        """
        # Get all zone entities from Home Assistant
        zone_entities = self.hass.states.async_all("zone")

        for zone_state in zone_entities:
            zone_lat = zone_state.attributes.get("latitude")
            zone_lon = zone_state.attributes.get("longitude")
            zone_radius = zone_state.attributes.get("radius", 100)

            if zone_lat is not None and zone_lon is not None:
                zone_distance = distance(lat, lon, zone_lat, zone_lon)
                if zone_distance <= zone_radius:
                    # Return the friendly name or entity ID without domain
                    return (
                        zone_state.attributes.get("friendly_name")
                        or zone_state.entity_id.split(".", 1)[1]
                    )

        return None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for the device tracker.

        Provides comprehensive information about the GPS tracking status,
        movement patterns, and device health.

        Returns:
            Dictionary of additional state attributes
        """
        attrs: AttributeDict = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "tracker_type": "gps",
        }

        gps_data = self._get_gps_data()
        if gps_data:
            # Core GPS attributes
            attrs.update(
                {
                    ATTR_GPS_ACCURACY: self.location_accuracy,
                    "last_seen": gps_data.get("last_seen"),
                    "source": gps_data.get("source", "unknown"),
                    "heading": gps_data.get("heading"),
                    "speed": gps_data.get("speed"),
                    "altitude": gps_data.get("altitude"),
                }
            )

            # Battery information
            if self.battery_level is not None:
                attrs[ATTR_BATTERY_LEVEL] = self.battery_level
                attrs["battery_status"] = self._get_battery_status()

            # Location analysis
            attrs.update(
                {
                    "distance_from_home": gps_data.get("distance_from_home"),
                    "current_zone": self.location_name,
                    "is_moving": self._is_currently_moving(gps_data),
                    "movement_status": self._get_movement_status(gps_data),
                }
            )

            # Data quality indicators
            attrs.update(
                {
                    "gps_signal_strength": self._assess_gps_signal_quality(gps_data),
                    "data_freshness": self._assess_data_freshness(gps_data),
                    "tracking_status": self._get_tracking_status(gps_data),
                }
            )

            # Walk integration
            walk_data = self._get_walk_data()
            if walk_data:
                attrs.update(
                    {
                        "walk_in_progress": walk_data.get("walk_in_progress", False),
                        "current_walk_distance": walk_data.get("current_walk_distance"),
                        "current_walk_duration": walk_data.get("current_walk_duration"),
                    }
                )

        # Add dog-specific information
        dog_data = self._get_dog_data()
        if dog_data and "dog_info" in dog_data:
            dog_info = dog_data["dog_info"]
            attrs.update(
                {
                    "dog_breed": dog_info.get("dog_breed", ""),
                    "dog_age": dog_info.get("dog_age"),
                    "dog_size": dog_info.get("dog_size"),
                }
            )

        return attrs

    def _get_battery_status(self) -> str:
        """Get battery status description.

        Returns:
            Battery status description
        """
        battery_level = self.battery_level
        if battery_level is None:
            return "unknown"

        if battery_level <= 5:
            return "critical"
        elif battery_level <= 15:
            return "low"
        elif battery_level <= 30:
            return "medium"
        else:
            return "good"

    def _is_currently_moving(self, gps_data: dict[str, Any]) -> bool:
        """Determine if the dog is currently moving.

        Args:
            gps_data: GPS module data

        Returns:
            True if the dog is moving, False otherwise
        """
        speed = gps_data.get("speed")
        if speed is not None:
            return speed > 1.0  # 1 km/h threshold

        # Fall back to location change analysis
        current_lat = gps_data.get("latitude")
        current_lon = gps_data.get("longitude")

        if (
            current_lat is not None
            and current_lon is not None
            and self._last_known_location is not None
        ):
            last_lat, last_lon = self._last_known_location
            location_change = distance(
                current_lat, current_lon, last_lat, last_lon)

            # Consider moving if location changed by more than threshold
            return location_change > LOCATION_UPDATE_THRESHOLD

        return False

    def _get_movement_status(self, gps_data: dict[str, Any]) -> str:
        """Get detailed movement status.

        Args:
            gps_data: GPS module data

        Returns:
            Movement status description
        """
        if self._is_currently_moving(gps_data):
            speed = gps_data.get("speed", 0)
            if speed > 10:
                return "running"
            elif speed > 3:
                return "walking"
            else:
                return "moving_slowly"
        else:
            return "stationary"

    def _assess_gps_signal_quality(self, gps_data: dict[str, Any]) -> str:
        """Assess GPS signal quality based on accuracy.

        Args:
            gps_data: GPS module data

        Returns:
            Signal quality description
        """
        accuracy = gps_data.get("accuracy")
        if accuracy is None:
            return "unknown"

        if accuracy <= 5:
            return "excellent"
        elif accuracy <= 15:
            return "good"
        elif accuracy <= 50:
            return "fair"
        else:
            return "poor"

    def _assess_data_freshness(self, gps_data: dict[str, Any]) -> str:
        """Assess how fresh the GPS data is.

        Args:
            gps_data: GPS module data

        Returns:
            Data freshness description
        """
        last_seen = gps_data.get("last_seen")
        if not last_seen:
            return "unknown"

        try:
            last_seen_dt = datetime.fromisoformat(last_seen)
            age = dt_util.utcnow() - last_seen_dt

            if age < timedelta(minutes=1):
                return "current"
            elif age < timedelta(minutes=5):
                return "recent"
            elif age < timedelta(minutes=15):
                return "stale"
            else:
                return "old"
        except (ValueError, TypeError):
            return "unknown"

    def _get_tracking_status(self, gps_data: dict[str, Any]) -> str:
        """Get overall tracking status.

        Args:
            gps_data: GPS module data

        Returns:
            Tracking status description
        """
        has_location = (
            gps_data.get("latitude") is not None
            and gps_data.get("longitude") is not None
        )

        if not has_location:
            return "no_location"

        signal_quality = self._assess_gps_signal_quality(gps_data)
        data_freshness = self._assess_data_freshness(gps_data)
        battery_status = self._get_battery_status()

        # Determine overall status
        if signal_quality in ["excellent", "good"] and data_freshness in [
            "current",
            "recent",
        ]:
            if battery_status == "critical":
                return "tracking_battery_critical"
            elif battery_status == "low":
                return "tracking_battery_low"
            else:
                return "tracking_active"
        elif signal_quality == "poor" or data_freshness in ["stale", "old"]:
            return "tracking_degraded"
        else:
            return "tracking_limited"

    @property
    def available(self) -> bool:
        """Return if the device tracker is available.

        The tracker is considered available if we have recent GPS data
        or if there's restored state to fall back on.

        Returns:
            True if tracker is available, False otherwise
        """
        if not self.coordinator.available:
            return False

        gps_data = self._get_gps_data()
        if gps_data:
            # Check if GPS data is not too old
            last_seen = gps_data.get("last_seen")
            if last_seen:
                with suppress(ValueError, TypeError):
                    last_seen_dt = datetime.fromisoformat(last_seen)
                    age = dt_util.utcnow() - last_seen_dt
                    return age < MAX_GPS_AGE

        # Fall back to checking if we have any location data
        return self.latitude is not None and self.longitude is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Processes new GPS data, updates location history, and triggers
        location-based automations if needed.
        """
        gps_data = self._get_gps_data()
        if not gps_data:
            return

        # Update location history
        current_lat = gps_data.get("latitude")
        current_lon = gps_data.get("longitude")

        if current_lat is not None and current_lon is not None:
            new_location = (float(current_lat), float(current_lon))

            # Check for significant location change
            if self._last_known_location:
                location_change = distance(
                    new_location[0],
                    new_location[1],
                    self._last_known_location[0],
                    self._last_known_location[1],
                )

                # Only update if location changed significantly
                if location_change > LOCATION_UPDATE_THRESHOLD:
                    self._update_location_history(new_location, gps_data)
                    self._last_known_location = new_location
            else:
                # First location update
                self._last_known_location = new_location
                self._update_location_history(new_location, gps_data)

        # Update current zone
        new_zone = self.location_name
        if new_zone != self._current_zone:
            self._handle_zone_change(self._current_zone, new_zone)
            self._current_zone = new_zone

        self._last_update_time = dt_util.utcnow()

        # Call parent update
        super()._handle_coordinator_update()

    def _update_location_history(
        self, location: LocationTuple, gps_data: dict[str, Any]
    ) -> None:
        """Update the location history with a new position.

        Args:
            location: New location coordinates
            gps_data: Associated GPS data
        """
        history_entry = {
            "timestamp": dt_util.utcnow().isoformat(),
            "latitude": location[0],
            "longitude": location[1],
            "accuracy": gps_data.get("accuracy"),
            "speed": gps_data.get("speed"),
            "zone": self.location_name,
        }

        # Add to history (keep last 100 entries)
        self._location_history.append(history_entry)
        if len(self._location_history) > 100:
            self._location_history.pop(0)

        _LOGGER.debug(
            "Updated location for %s: %f, %f (accuracy: %sm)",
            self._dog_name,
            location[0],
            location[1],
            gps_data.get("accuracy", "unknown"),
        )

    def _handle_zone_change(self, old_zone: str | None, new_zone: str | None) -> None:
        """Handle zone change events.

        Fires events and logs zone transitions for automation purposes.

        Args:
            old_zone: Previous zone name
            new_zone: New zone name
        """
        if old_zone == new_zone:
            return

        # Fire zone change events
        if new_zone == STATE_HOME:
            self.hass.bus.async_fire(
                "pawcontrol_dog_arrived_home",
                {
                    ATTR_DOG_ID: self._dog_id,
                    ATTR_DOG_NAME: self._dog_name,
                    "previous_zone": old_zone,
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )
        elif old_zone == STATE_HOME:
            self.hass.bus.async_fire(
                "pawcontrol_dog_left_home",
                {
                    ATTR_DOG_ID: self._dog_id,
                    ATTR_DOG_NAME: self._dog_name,
                    "new_zone": new_zone,
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )

        # General zone change event
        self.hass.bus.async_fire(
            "pawcontrol_dog_zone_change",
            {
                ATTR_DOG_ID: self._dog_id,
                ATTR_DOG_NAME: self._dog_name,
                "old_zone": old_zone,
                "new_zone": new_zone,
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )

        _LOGGER.info(
            "Zone change for %s: %s -> %s",
            self._dog_name,
            old_zone or "unknown",
            new_zone or "unknown",
        )

    def _get_dog_data(self) -> dict[str, Any] | None:
        """Get data for this tracker's dog from the coordinator.

        Returns:
            Dog data dictionary or None if not available
        """
        if not self.coordinator.available:
            return None

        return self.coordinator.get_dog_data(self._dog_id)

    def _get_gps_data(self) -> dict[str, Any] | None:
        """Get GPS module data for this dog.

        Returns:
            GPS data dictionary or None if not available
        """
        return self.coordinator.get_module_data(self._dog_id, "gps")

    def _get_walk_data(self) -> dict[str, Any] | None:
        """Get walk module data for this dog.

        Returns:
            Walk data dictionary or None if not available
        """
        return self.coordinator.get_module_data(self._dog_id, "walk")

    async def async_update_location(
        self, latitude: float, longitude: float, accuracy: float | None = None
    ) -> None:
        """Manually update the dog's location.

        This method can be called by services or automations to
        update the dog's location from external sources.

        Args:
            latitude: New latitude coordinate
            longitude: New longitude coordinate
            accuracy: GPS accuracy in meters
        """
        # Validate coordinates
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise ValueError("Invalid coordinates provided")

        # Update the coordinator with new location data
        # This would typically call a service to update GPS data
        _LOGGER.info(
            "Manual location update for %s: %f, %f", self._dog_name, latitude, longitude
        )

        # Trigger coordinator refresh to process the new data
        await self.coordinator.async_refresh_dog(self._dog_id)

    def get_location_history(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get location history for the specified time period.

        Args:
            hours: Number of hours of history to return

        Returns:
            List of location history entries
        """
        cutoff_time = dt_util.utcnow() - timedelta(hours=hours)

        return [
            entry
            for entry in self._location_history
            if datetime.fromisoformat(entry["timestamp"]) >= cutoff_time
        ]

    def calculate_distance_traveled(self, hours: int = 24) -> float:
        """Calculate total distance traveled in the specified time period.

        Args:
            hours: Number of hours to calculate distance for

        Returns:
            Total distance traveled in meters
        """
        history = self.get_location_history(hours)
        if len(history) < 2:
            return 0.0

        total_distance = 0.0
        for i in range(1, len(history)):
            prev_entry = history[i - 1]
            curr_entry = history[i]

            dist = distance(
                prev_entry["latitude"],
                prev_entry["longitude"],
                curr_entry["latitude"],
                curr_entry["longitude"],
            )
            total_distance += dist * 1000  # Convert km to meters

        return total_distance

    @property
    def state_attributes(self) -> AttributeDict:
        """Return state attributes for the device tracker.

        Combines base tracker attributes with custom Paw Control attributes
        for comprehensive tracking information.

        Returns:
            Complete state attributes dictionary
        """
        attrs = super().extra_state_attributes or {}

        # Add coordinate information
        if self.latitude is not None:
            attrs[ATTR_LATITUDE] = self.latitude
        if self.longitude is not None:
            attrs[ATTR_LONGITUDE] = self.longitude
        if self.location_accuracy:
            attrs[ATTR_GPS_ACCURACY] = self.location_accuracy

        # Add source type
        attrs["source_type"] = self.source_type

        return attrs
