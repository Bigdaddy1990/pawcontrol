"""Geofencing system for PawControl integration.

Comprehensive geofencing implementation with zone management, GPS tracking,
entry/exit detection, and safety alert system. Supports multiple zone types
including safe zones, restricted areas, and points of interest.

Quality Scale: Platinum target
P26.1.1++
Python: 3.13+
"""

import asyncio
from collections.abc import Iterable, Mapping
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import math
from typing import TYPE_CHECKING, Any, Final, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_GEOFENCE_ENTERED,
    EVENT_GEOFENCE_LEFT,
    MAX_GEOFENCE_RADIUS,
    MIN_GEOFENCE_RADIUS,
    STORAGE_VERSION,
)
from .exceptions import ValidationError
from .notifications import (
    NotificationPriority,
    NotificationTemplateData,
    NotificationType,
)
from .types import (
    GeofenceNotificationPayload,
    GeofenceStoragePayload,
    GeofenceZoneMetadata,
    GeofenceZoneStoragePayload,
    GPSLocation,
)
from .utils import async_fire_event
from .validation_helpers import validate_coordinate_pair

if TYPE_CHECKING:
    from .notifications import PawControlNotificationManager  # noqa: E111

_LOGGER = logging.getLogger(__name__)


def _sanitize_zone_metadata(
    metadata: Mapping[str, object] | GeofenceZoneMetadata | None,
) -> GeofenceZoneMetadata:
    """Normalise persisted geofence metadata to the typed contract."""  # noqa: E111

    if not metadata:  # noqa: E111
        return cast(GeofenceZoneMetadata, {})

    metadata_map = dict(metadata)  # noqa: E111
    result: GeofenceZoneMetadata = {}  # noqa: E111

    if "auto_created" in metadata_map:  # noqa: E111
        auto_created = metadata_map.get("auto_created")
        if isinstance(auto_created, bool):
            result["auto_created"] = auto_created  # noqa: E111

    if "color" in metadata_map:  # noqa: E111
        color = metadata_map.get("color")
        if isinstance(color, str) or color is None:
            result["color"] = color  # noqa: E111

    if "created_by" in metadata_map:  # noqa: E111
        created_by = metadata_map.get("created_by")
        if isinstance(created_by, str) or created_by is None:
            result["created_by"] = created_by  # noqa: E111

    if "notes" in metadata_map:  # noqa: E111
        notes = metadata_map.get("notes")
        if isinstance(notes, str) or notes is None:
            result["notes"] = notes  # noqa: E111

    if "tags" in metadata_map:  # noqa: E111
        tags_value = metadata_map.get("tags")
        tags: list[str] = []
        if isinstance(tags_value, str):
            tags = [tags_value]  # noqa: E111
        elif isinstance(tags_value, Mapping):
            tags = [value for value in tags_value.values() if isinstance(value, str)]  # noqa: E111
        elif isinstance(tags_value, Iterable):
            tags = [tag for tag in tags_value if isinstance(tag, str)]  # noqa: E111
        if tags:
            result["tags"] = tags  # noqa: E111

    return result  # noqa: E111


def _empty_zone_metadata() -> GeofenceZoneMetadata:
    """Provide an empty, typed metadata mapping for geofence zones."""  # noqa: E111

    return _sanitize_zone_metadata({})  # noqa: E111


# Geofencing constants
DEFAULT_HOME_ZONE_RADIUS: Final[int] = 50  # meters
DEFAULT_CHECK_INTERVAL: Final[int] = 30  # seconds
GEOFENCE_HYSTERESIS: Final[float] = 0.8  # 20% hysteresis to prevent flapping
EARTH_RADIUS_KM: Final[float] = 6371.0  # Earth radius in kilometers


class GeofenceType(Enum):
    """Enumeration of supported geofence zone types."""  # noqa: E111

    SAFE_ZONE = "safe_zone"  # noqa: E111
    RESTRICTED_AREA = "restricted_area"  # noqa: E111
    POINT_OF_INTEREST = "point_of_interest"  # noqa: E111
    HOME_ZONE = "home_zone"  # noqa: E111


class GeofenceEvent(Enum):
    """Enumeration of geofence events."""  # noqa: E111

    ENTERED = "entered"  # noqa: E111
    LEFT = "left"  # noqa: E111
    DWELL = "dwell"  # Remained in zone for extended time  # noqa: E111


@dataclass
class GeofenceZone:
    """Definition of a geofence zone with comprehensive metadata.

    Attributes:
        id: Unique identifier for the zone
        name: Human-readable name for the zone
        type: Type of geofence zone
        latitude: Center latitude coordinate
        longitude: Center longitude coordinate
        radius: Zone radius in meters
        enabled: Whether the zone is actively monitored
        alerts_enabled: Whether to generate alerts for this zone
        description: Optional description of the zone
        created_at: When the zone was created
        updated_at: When the zone was last modified
        metadata: Additional zone-specific data
    """  # noqa: E111

    id: str  # noqa: E111
    name: str  # noqa: E111
    type: GeofenceType  # noqa: E111
    latitude: float  # noqa: E111
    longitude: float  # noqa: E111
    radius: float  # noqa: E111
    enabled: bool = True  # noqa: E111
    alerts_enabled: bool = True  # noqa: E111
    description: str = ""  # noqa: E111
    created_at: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111
    updated_at: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111
    metadata: GeofenceZoneMetadata = field(  # noqa: E111
        default_factory=_empty_zone_metadata,
    )

    def __post_init__(self) -> None:  # noqa: E111
        """Validate zone parameters after initialization."""
        try:
            validate_coordinate_pair(self.latitude, self.longitude)  # noqa: E111
        except ValidationError as err:
            if err.field == "latitude":  # noqa: E111
                raise ValueError(f"Invalid latitude: {self.latitude}") from err
            raise ValueError(f"Invalid longitude: {self.longitude}") from err  # noqa: E111
        if not (MIN_GEOFENCE_RADIUS <= self.radius <= MAX_GEOFENCE_RADIUS):
            raise ValueError(  # noqa: E111
                f"Radius must be between {MIN_GEOFENCE_RADIUS} and {MAX_GEOFENCE_RADIUS} meters",  # noqa: E501
            )

        self.metadata = _sanitize_zone_metadata(self.metadata)

    def contains_location(self, location: GPSLocation, hysteresis: float = 1.0) -> bool:  # noqa: E111
        """Check if a location is within this geofence zone.

        Args:
            location: GPS location to check
            hysteresis: Multiplier for radius to prevent flapping (default: 1.0)

        Returns:
            True if location is within the zone boundary
        """
        distance = self.distance_to_location(location)
        effective_radius = self.radius * hysteresis
        return distance <= effective_radius

    def distance_to_location(self, location: GPSLocation) -> float:  # noqa: E111
        """Calculate distance from zone center to a location.

        Args:
            location: GPS location to calculate distance to

        Returns:
            Distance in meters
        """
        return calculate_distance(
            self.latitude,
            self.longitude,
            location.latitude,
            location.longitude,
        )

    def to_storage_payload(self) -> GeofenceZoneStoragePayload:  # noqa: E111
        """Convert zone to a typed storage payload."""

        metadata_dict = _sanitize_zone_metadata(self.metadata)
        if "tags" in metadata_dict:
            metadata_dict["tags"] = list(metadata_dict["tags"])  # noqa: E111

        payload_dict: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius": self.radius,
            "enabled": self.enabled,
            "alerts_enabled": self.alerts_enabled,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": cast(GeofenceZoneMetadata, cast(Any, metadata_dict)),
        }
        return cast(GeofenceZoneStoragePayload, cast(Any, payload_dict))

    @classmethod  # noqa: E111
    def from_storage_payload(cls, data: GeofenceZoneStoragePayload) -> GeofenceZone:  # noqa: E111
        """Create zone from dictionary data."""

        metadata_raw = data.get("metadata", {})
        metadata = _sanitize_zone_metadata(
            metadata_raw if isinstance(metadata_raw, Mapping) else {},
        )

        return cls(
            id=data["id"],
            name=data["name"],
            type=GeofenceType(data["type"]),
            latitude=data["latitude"],
            longitude=data["longitude"],
            radius=data["radius"],
            enabled=data.get("enabled", True),
            alerts_enabled=data.get("alerts_enabled", True),
            description=data.get("description", ""),
            created_at=(
                dt_util.parse_datetime(created_at)
                if isinstance(created_at := data.get("created_at"), str)
                else None
            )
            or dt_util.utcnow(),
            updated_at=(
                dt_util.parse_datetime(updated_at)
                if isinstance(updated_at := data.get("updated_at"), str)
                else None
            )
            or dt_util.utcnow(),
            metadata=metadata,
        )


@dataclass
class DogLocationState:
    """Tracks the location state for a specific dog.

    Attributes:
        dog_id: Unique identifier for the dog
        last_location: Most recent GPS location
        current_zones: Set of zone IDs the dog is currently in
        zone_entry_times: Mapping of zone ID to entry timestamp
        location_history: Recent location history for trend analysis
        last_updated: When this state was last updated
    """  # noqa: E111

    dog_id: str  # noqa: E111
    last_location: GPSLocation | None = None  # noqa: E111
    current_zones: set[str] = field(default_factory=set)  # noqa: E111
    zone_entry_times: dict[str, datetime] = field(default_factory=dict)  # noqa: E111
    location_history: list[GPSLocation] = field(default_factory=list)  # noqa: E111
    last_updated: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111

    def add_location(self, location: GPSLocation, max_history: int = 50) -> None:  # noqa: E111
        """Add a new location to the state history.

        Args:
            location: New GPS location
            max_history: Maximum number of locations to keep in history
        """
        self.last_location = location
        self.location_history.append(location)
        self.last_updated = dt_util.utcnow()

        # Trim history to max size
        if len(self.location_history) > max_history:
            self.location_history = self.location_history[-max_history:]  # noqa: E111


class PawControlGeofencing:
    """Comprehensive geofencing system for PawControl integration."""  # noqa: E111

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:  # noqa: E111
        """Initialize geofencing system.

        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id

        # Storage for zones and state
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}_{entry_id}_geofencing",
        )

        # Runtime state
        self._zones: dict[str, GeofenceZone] = {}
        self._dog_states: dict[str, DogLocationState] = {}
        self._enabled = False
        self._check_interval = DEFAULT_CHECK_INTERVAL
        self._use_home_location = True
        self._home_zone_radius = DEFAULT_HOME_ZONE_RADIUS
        self._notification_manager: PawControlNotificationManager | None = None

        # Background task management
        self._update_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def set_notification_manager(  # noqa: E111
        self,
        notification_manager: PawControlNotificationManager | None,
    ) -> None:
        """Attach the notification manager used for zone alerts.

        Args:
            notification_manager: Notification manager instance or ``None`` to detach
        """

        self._notification_manager = notification_manager
        if notification_manager:
            _LOGGER.debug("Geofencing notification manager attached")  # noqa: E111
        else:
            _LOGGER.debug("Geofencing notification manager cleared")  # noqa: E111

    async def async_initialize(  # noqa: E111
        self,
        dogs: list[str],
        enabled: bool = False,
        use_home_location: bool = True,
        home_zone_radius: int = DEFAULT_HOME_ZONE_RADIUS,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
    ) -> None:
        """Initialize geofencing system with configuration.

        Args:
            dogs: List of dog IDs to track
            enabled: Whether geofencing is enabled
            use_home_location: Whether to create home zone automatically
            home_zone_radius: Radius for home zone in meters
            check_interval: How often to check locations in seconds
        """
        async with self._lock:
            try:  # noqa: E111
                # Load stored data
                stored_data_raw = await self._store.async_load()
                stored_data = cast(
                    GeofenceStoragePayload,
                    stored_data_raw or {},
                )

                # Load zones
                zones_data_raw = stored_data.get("zones", {})
                if isinstance(zones_data_raw, list):
                    zones_data_raw = {  # noqa: E111
                        cast(str, zone.get("id")): cast(
                            GeofenceZoneStoragePayload,
                            zone,
                        )
                        for zone in zones_data_raw
                        if isinstance(zone, Mapping) and isinstance(zone.get("id"), str)
                    }
                elif not isinstance(zones_data_raw, Mapping):
                    zones_data_raw = {}  # noqa: E111

                zones_data = cast(
                    dict[str, GeofenceZoneStoragePayload],
                    dict(zones_data_raw),
                )

                for zone_id, zone_data in zones_data.items():
                    try:  # noqa: E111
                        self._zones[zone_id] = GeofenceZone.from_storage_payload(
                            zone_data,
                        )
                    except Exception as err:  # noqa: E111
                        _LOGGER.warning(
                            "Failed to load geofence zone %s: %s",
                            zone_id,
                            err,
                        )

                # Initialize dog states
                for dog_id in dogs:
                    if dog_id not in self._dog_states:  # noqa: E111
                        self._dog_states[dog_id] = DogLocationState(dog_id)

                # Update configuration
                self._enabled = enabled
                self._use_home_location = use_home_location
                self._home_zone_radius = home_zone_radius
                self._check_interval = check_interval

                # Create home zone if enabled and not exists
                if use_home_location and "home" not in self._zones:
                    await self._create_home_zone()  # noqa: E111

                # Start monitoring if enabled
                if enabled:
                    await self._start_monitoring()  # noqa: E111

                _LOGGER.info(
                    "Geofencing initialized: %d zones, %d dogs, enabled=%s",
                    len(self._zones),
                    len(self._dog_states),
                    enabled,
                )

            except Exception as err:  # noqa: E111
                _LOGGER.error(
                    "Failed to initialize geofencing system: %s",
                    err,
                )
                raise

    async def _create_home_zone(self) -> None:  # noqa: E111
        """Create home zone based on Home Assistant location."""
        try:
            home_location = self.hass.config.location  # noqa: E111
            if home_location:  # noqa: E111
                home_zone = GeofenceZone(
                    id="home",
                    name="Home",
                    type=GeofenceType.HOME_ZONE,
                    latitude=home_location.latitude,
                    longitude=home_location.longitude,
                    radius=self._home_zone_radius,
                    description="Automatically created home zone",
                    metadata={"auto_created": True},
                )

                self._zones["home"] = home_zone
                await self._save_data()

                _LOGGER.info(
                    "Created home zone: %.6f,%.6f radius %dm",
                    home_zone.latitude,
                    home_zone.longitude,
                    home_zone.radius,
                )

        except Exception as err:
            _LOGGER.warning("Failed to create home zone: %s", err)  # noqa: E111

    async def _start_monitoring(self) -> None:  # noqa: E111
        """Start background monitoring tasks."""
        if self._update_task and not self._update_task.done():
            return  # noqa: E111

        # Start location checking task
        self._update_task = self.hass.async_create_task(
            self._monitoring_loop(),
        )

        # Start cleanup task
        self._cleanup_task = self.hass.async_create_task(self._cleanup_loop())

        _LOGGER.debug("Started geofencing monitoring tasks")

    async def _stop_monitoring(self) -> None:  # noqa: E111
        """Stop background monitoring tasks."""
        if self._update_task:
            self._update_task.cancel()  # noqa: E111
            with contextlib.suppress(asyncio.CancelledError):  # noqa: E111
                await self._update_task
            self._update_task = None  # noqa: E111

        if self._cleanup_task:
            self._cleanup_task.cancel()  # noqa: E111
            with contextlib.suppress(asyncio.CancelledError):  # noqa: E111
                await self._cleanup_task
            self._cleanup_task = None  # noqa: E111

        _LOGGER.debug("Stopped geofencing monitoring tasks")

    async def _monitoring_loop(self) -> None:  # noqa: E111
        """Main monitoring loop for geofence checking."""
        while True:
            try:  # noqa: E111
                await self._check_all_locations()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:  # noqa: E111
                break
            except Exception as err:  # noqa: E111
                _LOGGER.error("Error in geofencing monitoring loop: %s", err)
                await asyncio.sleep(self._check_interval)

    async def _cleanup_loop(self) -> None:  # noqa: E111
        """Cleanup loop for old location history."""
        while True:
            try:  # noqa: E111
                await asyncio.sleep(3600)  # Run every hour
                await self._cleanup_old_data()
            except asyncio.CancelledError:  # noqa: E111
                break
            except Exception as err:  # noqa: E111
                _LOGGER.error("Error in geofencing cleanup loop: %s", err)

    async def _check_all_locations(self) -> None:  # noqa: E111
        """Check all dog locations against all geofence zones."""
        async with self._lock:
            for dog_state in self._dog_states.values():  # noqa: E111
                if dog_state.last_location:
                    await self._check_dog_location(dog_state)  # noqa: E111

    async def _check_dog_location(self, dog_state: DogLocationState) -> None:  # noqa: E111
        """Check a specific dog's location against all zones.

        Args:
            dog_state: Current state for the dog
        """
        if not dog_state.last_location:
            return  # noqa: E111

        current_time = dt_util.utcnow()
        newly_entered_zones = set()
        newly_left_zones = set()

        # Check each zone
        for zone in self._zones.values():
            if not zone.enabled:  # noqa: E111
                continue

            zone_id = zone.id  # noqa: E111
            currently_inside = zone.contains_location(dog_state.last_location)  # noqa: E111
            was_inside = zone_id in dog_state.current_zones  # noqa: E111

            # Check for zone entry  # noqa: E114
            if currently_inside and not was_inside:  # noqa: E111
                # Use hysteresis to confirm entry
                if zone.contains_location(dog_state.last_location, GEOFENCE_HYSTERESIS):
                    dog_state.current_zones.add(zone_id)  # noqa: E111
                    dog_state.zone_entry_times[zone_id] = current_time  # noqa: E111
                    newly_entered_zones.add(zone_id)  # noqa: E111

            # Check for zone exit  # noqa: E114
            elif (  # noqa: E111
                not currently_inside
                and was_inside
                and not zone.contains_location(
                    dog_state.last_location,
                    1.0 / GEOFENCE_HYSTERESIS,
                )
            ):
                dog_state.current_zones.discard(zone_id)
                dog_state.zone_entry_times.pop(zone_id, None)
                newly_left_zones.add(zone_id)

        # Fire events for zone changes
        for zone_id in newly_entered_zones:
            await self._fire_zone_event(  # noqa: E111
                dog_state.dog_id,
                zone_id,
                GeofenceEvent.ENTERED,
            )

        for zone_id in newly_left_zones:
            await self._fire_zone_event(dog_state.dog_id, zone_id, GeofenceEvent.LEFT)  # noqa: E111

    async def _fire_zone_event(  # noqa: E111
        self,
        dog_id: str,
        zone_id: str,
        event: GeofenceEvent,
    ) -> None:
        """Fire a geofence event.

        Args:
            dog_id: ID of the dog
            zone_id: ID of the zone
            event: Type of geofence event
        """
        zone = self._zones.get(zone_id)
        if not zone or not zone.alerts_enabled:
            return  # noqa: E111

        dog_state = self._dog_states.get(dog_id)
        location = dog_state.last_location if dog_state else None

        event_data = {
            "dog_id": dog_id,
            "zone_id": zone_id,
            "zone_name": zone.name,
            "zone_type": zone.type.value,
            "event_type": event.value,
            "timestamp": dt_util.utcnow().isoformat(),
        }

        if location:
            event_data.update(  # noqa: E111
                {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "altitude": location.altitude,
                },
            )

        # Fire Home Assistant event
        if event == GeofenceEvent.ENTERED:
            await async_fire_event(self.hass, EVENT_GEOFENCE_ENTERED, event_data)  # noqa: E111
        elif event == GeofenceEvent.LEFT:
            await async_fire_event(self.hass, EVENT_GEOFENCE_LEFT, event_data)  # noqa: E111

        _LOGGER.info(
            "Geofence event: %s %s %s zone '%s'",
            dog_id,
            event.value,
            zone.type.value,
            zone.name,
        )

        if self._notification_manager:
            self.hass.async_create_task(  # noqa: E111
                self._notify_zone_event(dog_id, zone, event, location),
                name=f"pawcontrol_geofence_notify_{dog_id}_{zone_id}",
            )

    async def _cleanup_old_data(self) -> None:  # noqa: E111
        """Clean up old location history and zone entry times."""
        cutoff_time = dt_util.utcnow() - timedelta(hours=24)

        for dog_state in self._dog_states.values():
            # Clean old location history  # noqa: E114
            dog_state.location_history = [  # noqa: E111
                loc for loc in dog_state.location_history if loc.timestamp > cutoff_time
            ]

            # Clean old zone entry times for zones no longer occupied  # noqa: E114
            zones_to_clean = []  # noqa: E111
            for zone_id, entry_time in dog_state.zone_entry_times.items():  # noqa: E111
                if zone_id not in dog_state.current_zones and entry_time < cutoff_time:
                    zones_to_clean.append(zone_id)  # noqa: E111

            for zone_id in zones_to_clean:  # noqa: E111
                dog_state.zone_entry_times.pop(zone_id, None)

    async def async_update_location(self, dog_id: str, location: GPSLocation) -> None:  # noqa: E111
        """Update location for a dog and check geofences.

        Args:
            dog_id: Dog identifier
            location: New GPS location
        """
        async with self._lock:
            if dog_id not in self._dog_states:  # noqa: E111
                self._dog_states[dog_id] = DogLocationState(dog_id)

            dog_state = self._dog_states[dog_id]  # noqa: E111
            dog_state.add_location(location)  # noqa: E111

            if self._enabled:  # noqa: E111
                await self._check_dog_location(dog_state)

    async def async_add_zone(self, zone: GeofenceZone) -> bool:  # noqa: E111
        """Add a new geofence zone.

        Args:
            zone: Geofence zone to add

        Returns:
            True if zone was added successfully
        """
        async with self._lock:
            if zone.id in self._zones:  # noqa: E111
                return False

            self._zones[zone.id] = zone  # noqa: E111
            await self._save_data()  # noqa: E111

            _LOGGER.info(  # noqa: E111
                "Added geofence zone '%s' (%s): %.6f,%.6f radius %dm",
                zone.name,
                zone.type.value,
                zone.latitude,
                zone.longitude,
                zone.radius,
            )

            return True  # noqa: E111

    async def async_update_zone(self, zone: GeofenceZone) -> bool:  # noqa: E111
        """Update an existing geofence zone.

        Args:
            zone: Updated zone data

        Returns:
            True if zone was updated successfully
        """
        async with self._lock:
            if zone.id not in self._zones:  # noqa: E111
                return False

            zone.updated_at = dt_util.utcnow()  # noqa: E111
            self._zones[zone.id] = zone  # noqa: E111
            await self._save_data()  # noqa: E111

            _LOGGER.info("Updated geofence zone '%s'", zone.name)  # noqa: E111
            return True  # noqa: E111

    async def async_remove_zone(self, zone_id: str) -> bool:  # noqa: E111
        """Remove a geofence zone.

        Args:
            zone_id: ID of zone to remove

        Returns:
            True if zone was removed successfully
        """
        async with self._lock:
            if zone_id not in self._zones:  # noqa: E111
                return False

            zone = self._zones.pop(zone_id)  # noqa: E111

            # Remove zone from all dog states  # noqa: E114
            for dog_state in self._dog_states.values():  # noqa: E111
                dog_state.current_zones.discard(zone_id)
                dog_state.zone_entry_times.pop(zone_id, None)

            await self._save_data()  # noqa: E111

            _LOGGER.info("Removed geofence zone '%s'", zone.name)  # noqa: E111
            return True  # noqa: E111

    async def async_enable_geofencing(self, enabled: bool) -> None:  # noqa: E111
        """Enable or disable geofencing system.

        Args:
            enabled: Whether to enable geofencing
        """
        async with self._lock:
            if self._enabled == enabled:  # noqa: E111
                return

            self._enabled = enabled  # noqa: E111

            if enabled:  # noqa: E111
                await self._start_monitoring()
            else:  # noqa: E111
                await self._stop_monitoring()

            _LOGGER.info("Geofencing %s", "enabled" if enabled else "disabled")  # noqa: E111

    def get_zones(self) -> dict[str, GeofenceZone]:  # noqa: E111
        """Get all geofence zones.

        Returns:
            Dictionary of zone ID to zone data
        """
        return dict(self._zones)

    def get_zone(self, zone_id: str) -> GeofenceZone | None:  # noqa: E111
        """Get a specific geofence zone.

        Args:
            zone_id: ID of zone to retrieve

        Returns:
            Zone data or None if not found
        """
        return self._zones.get(zone_id)

    def get_dog_state(self, dog_id: str) -> DogLocationState | None:  # noqa: E111
        """Get current state for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Current dog state or None if not found
        """
        return self._dog_states.get(dog_id)

    def get_dogs_in_zone(self, zone_id: str) -> list[str]:  # noqa: E111
        """Get list of dogs currently in a zone.

        Args:
            zone_id: Zone identifier

        Returns:
            List of dog IDs currently in the zone
        """
        dogs_in_zone: list[str] = [
            dog_state.dog_id
            for dog_state in self._dog_states.values()
            if zone_id in dog_state.current_zones
        ]
        return dogs_in_zone

    def is_enabled(self) -> bool:  # noqa: E111
        """Check if geofencing is enabled.

        Returns:
            True if geofencing is enabled
        """
        return self._enabled

    async def _save_data(self) -> None:  # noqa: E111
        """Save geofencing data to storage."""
        try:
            zones_payload: dict[str, GeofenceZoneStoragePayload] = {  # noqa: E111
                zone_id: zone.to_storage_payload()
                for zone_id, zone in self._zones.items()
            }
            data: GeofenceStoragePayload = {  # noqa: E111
                "zones": zones_payload,
                "last_updated": dt_util.utcnow().isoformat(),
            }

            await self._store.async_save(data)  # noqa: E111

        except Exception as err:
            _LOGGER.error("Failed to save geofencing data: %s", err)  # noqa: E111

    async def async_cleanup(self) -> None:  # noqa: E111
        """Clean up geofencing system."""
        await self._stop_monitoring()

        async with self._lock:
            self._zones.clear()  # noqa: E111
            self._dog_states.clear()  # noqa: E111
            self._notification_manager = None  # noqa: E111

    async def _notify_zone_event(  # noqa: E111
        self,
        dog_id: str,
        zone: GeofenceZone,
        event: GeofenceEvent,
        location: GPSLocation | None,
    ) -> None:
        """Send a notification for a geofence event using the notification manager."""

        if not self._notification_manager:
            return  # noqa: E111

        priority = self._map_notification_priority(zone, event)
        title, message = self._format_notification_content(
            dog_id,
            zone,
            event,
            location,
        )

        notification_data: GeofenceNotificationPayload = {
            "zone_id": zone.id,
            "zone_name": zone.name,
            "zone_type": zone.type.value,
            "event_type": event.value,
            "radius": zone.radius,
        }

        if location:
            distance = zone.distance_to_location(location)  # noqa: E111
            notification_data["latitude"] = location.latitude  # noqa: E111
            notification_data["longitude"] = location.longitude  # noqa: E111
            notification_data["distance_from_center_m"] = round(distance, 2)  # noqa: E111
            notification_data["accuracy"] = location.accuracy  # noqa: E111

        try:
            await self._notification_manager.async_send_notification(  # noqa: E111
                notification_type=NotificationType.GEOFENCE_ALERT,
                title=title,
                message=message,
                dog_id=dog_id,
                priority=priority,
                data=cast(NotificationTemplateData, dict(notification_data)),
                allow_batching=False,
            )
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.error(  # noqa: E111
                "Failed to send geofence notification for %s/%s: %s",
                dog_id,
                zone.id,
                err,
            )

    @staticmethod  # noqa: E111
    def _map_notification_priority(  # noqa: E111
        zone: GeofenceZone,
        event: GeofenceEvent,
    ) -> NotificationPriority:
        """Determine notification priority for a geofence event."""

        if zone.type == GeofenceType.RESTRICTED_AREA:
            if event == GeofenceEvent.ENTERED:  # noqa: E111
                return NotificationPriority.URGENT
            if event == GeofenceEvent.DWELL:  # noqa: E111
                return NotificationPriority.HIGH
            return NotificationPriority.NORMAL  # noqa: E111

        if zone.type == GeofenceType.SAFE_ZONE:
            if event == GeofenceEvent.LEFT:  # noqa: E111
                return NotificationPriority.HIGH
            if event == GeofenceEvent.DWELL:  # noqa: E111
                return NotificationPriority.LOW
            return NotificationPriority.NORMAL  # noqa: E111

        if event == GeofenceEvent.DWELL:
            return NotificationPriority.NORMAL  # noqa: E111
        if event == GeofenceEvent.LEFT:
            return NotificationPriority.NORMAL  # noqa: E111
        return NotificationPriority.LOW

    @staticmethod  # noqa: E111
    def _format_notification_content(  # noqa: E111
        dog_id: str,
        zone: GeofenceZone,
        event: GeofenceEvent,
        location: GPSLocation | None,
    ) -> tuple[str, str]:
        """Create notification title and message for a geofence event."""

        location_suffix = ""
        if location:
            location_suffix = (
                f" (lat {location.latitude:.5f}, lon {location.longitude:.5f})"  # noqa: E111
            )

        if event == GeofenceEvent.ENTERED:
            if zone.type == GeofenceType.RESTRICTED_AREA:  # noqa: E111
                title = f"🚫 {dog_id} entered a restricted area"
                message = (
                    f"{dog_id} entered restricted zone '{zone.name}'{location_suffix}."
                )
            elif zone.type == GeofenceType.SAFE_ZONE:  # noqa: E111
                title = f"🏡 {dog_id} returned to the safe zone"
                message = (
                    f"{dog_id} is back inside safe zone '{zone.name}'{location_suffix}."
                )
            else:  # noqa: E111
                title = f"🗺️ {dog_id} entered {zone.name}"
                message = f"{dog_id} entered zone '{zone.name}'{location_suffix}."
        elif event == GeofenceEvent.LEFT:
            if zone.type == GeofenceType.SAFE_ZONE:  # noqa: E111
                title = f"⚠️ {dog_id} left the safe zone"
                message = f"{dog_id} left safe zone '{zone.name}'{location_suffix}."
            elif zone.type == GeofenceType.RESTRICTED_AREA:  # noqa: E111
                title = f"✅ {dog_id} left the restricted area"
                message = (
                    f"{dog_id} exited restricted zone '{zone.name}'{location_suffix}."
                )
            else:  # noqa: E111
                title = f"🚶 {dog_id} left {zone.name}"
                message = f"{dog_id} left zone '{zone.name}'{location_suffix}."
        else:  # GeofenceEvent.DWELL
            if zone.type == GeofenceType.RESTRICTED_AREA:  # noqa: E111
                title = f"⏱️ {dog_id} still in restricted area"
                message = f"{dog_id} remains inside restricted zone '{zone.name}'{location_suffix}."
            else:  # noqa: E111
                title = f"⏱️ {dog_id} still in {zone.name}"
                message = (
                    f"{dog_id} has been in zone '{zone.name}' for an extended time"
                    f"{location_suffix}."
                )

        return title, message


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS coordinates using Haversine formula.

    Args:
        lat1: First latitude
        lon1: First longitude
        lat2: Second latitude
        lon2: Second longitude

    Returns:
        Distance in meters
    """  # noqa: E111
    # Convert to radians  # noqa: E114
    lat1_rad = math.radians(lat1)  # noqa: E111
    lon1_rad = math.radians(lon1)  # noqa: E111
    lat2_rad = math.radians(lat2)  # noqa: E111
    lon2_rad = math.radians(lon2)  # noqa: E111

    # Haversine formula  # noqa: E114
    dlat = lat2_rad - lat1_rad  # noqa: E111
    dlon = lon2_rad - lon1_rad  # noqa: E111

    a = (  # noqa: E111
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))  # noqa: E111

    # Convert to meters  # noqa: E114
    distance_km = EARTH_RADIUS_KM * c  # noqa: E111
    return distance_km * 1000  # noqa: E111


def validate_coordinates(latitude: float, longitude: float) -> bool:
    """Validate GPS coordinates.

    Args:
        latitude: Latitude to validate
        longitude: Longitude to validate

    Returns:
        True if coordinates are valid
    """  # noqa: E111
    try:  # noqa: E111
        validate_coordinate_pair(latitude, longitude)
    except ValidationError:  # noqa: E111
        return False
    return True  # noqa: E111


def validate_radius(radius: float) -> bool:
    """Validate geofence radius.

    Args:
        radius: Radius to validate in meters

    Returns:
        True if radius is valid
    """  # noqa: E111
    return MIN_GEOFENCE_RADIUS <= radius <= MAX_GEOFENCE_RADIUS  # noqa: E111
