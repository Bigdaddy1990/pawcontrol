"""GPS and Geofencing management for PawControl.

Provides comprehensive GPS tracking, route management, geofencing with safety zones,
and location-based alerts for dogs. Includes automatic walk detection and real-time
location monitoring with configurable safety boundaries.

Quality Scale: Platinum
Home Assistant: 2025.9.4+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, NamedTuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    EVENT_GEOFENCE_BREACH,
    EVENT_GEOFENCE_ENTERED,
    EVENT_GEOFENCE_LEFT,
    EVENT_GEOFENCE_RETURN,
)
from .notifications import (
    NotificationPriority,
    NotificationType,
    PawControlNotificationManager,
)
from .resilience import ResilienceManager, RetryConfig

_LOGGER = logging.getLogger(__name__)


class GeofenceEventType(Enum):
    """Types of geofence events."""

    ENTERED = "entered"
    EXITED = "exited"
    BREACH = "breach"  # Outside safe zone for too long
    RETURN = "return"  # Back within safe zone


class GPSAccuracy(Enum):
    """GPS accuracy levels."""

    EXCELLENT = "excellent"  # <5m
    GOOD = "good"  # 5-15m
    FAIR = "fair"  # 15-50m
    POOR = "poor"  # >50m


class LocationSource(Enum):
    """Source of location data."""

    DEVICE_TRACKER = "device_tracker"
    MANUAL_INPUT = "manual_input"
    COMPANION_APP = "companion_app"
    EXTERNAL_API = "external_api"


@dataclass
class GPSPoint:
    """Single GPS coordinate point with metadata."""

    latitude: float
    longitude: float
    timestamp: datetime = field(default_factory=dt_util.utcnow)
    altitude: float | None = None
    accuracy: float | None = None
    speed: float | None = None
    heading: float | None = None
    source: LocationSource = LocationSource.DEVICE_TRACKER
    battery_level: int | None = None

    @property
    def accuracy_level(self) -> GPSAccuracy:
        """Get accuracy level based on accuracy value."""
        if self.accuracy is None:
            return GPSAccuracy.FAIR
        elif self.accuracy < 5:
            return GPSAccuracy.EXCELLENT
        elif self.accuracy < 15:
            return GPSAccuracy.GOOD
        elif self.accuracy < 50:
            return GPSAccuracy.FAIR
        else:
            return GPSAccuracy.POOR

    @property
    def is_accurate(self) -> bool:
        """Check if GPS point is accurate enough for tracking."""
        return self.accuracy_level in [
            GPSAccuracy.EXCELLENT,
            GPSAccuracy.GOOD,
            GPSAccuracy.FAIR,
        ]


@dataclass
class GeofenceZone:
    """Geofence zone definition with safety parameters."""

    name: str
    center_lat: float
    center_lon: float
    radius_meters: float
    zone_type: str = "safe_zone"  # safe_zone, danger_zone, activity_zone
    enabled: bool = True
    notifications_enabled: bool = True
    breach_timeout_minutes: int = 15  # Time outside zone before breach alert
    created_at: datetime = field(default_factory=dt_util.utcnow)

    def contains_point(self, lat: float, lon: float) -> bool:
        """Check if a point is within this geofence zone."""
        distance = calculate_distance(self.center_lat, self.center_lon, lat, lon)
        return distance <= self.radius_meters

    def distance_to_center(self, lat: float, lon: float) -> float:
        """Calculate distance from point to zone center in meters."""
        return calculate_distance(self.center_lat, self.center_lon, lat, lon)


@dataclass
class GeofenceEvent:
    """Geofence event with context information."""

    dog_id: str
    zone: GeofenceZone
    event_type: GeofenceEventType
    location: GPSPoint
    distance_from_center: float
    timestamp: datetime = field(default_factory=dt_util.utcnow)
    previous_status: bool | None = None  # Was inside zone before event
    duration_outside: timedelta | None = None  # For breach events

    @property
    def severity(self) -> str:
        """Get event severity level."""
        if self.event_type == GeofenceEventType.BREACH:
            if (
                self.duration_outside and self.duration_outside.total_seconds() > 1800
            ):  # 30 min
                return "high"
            return "medium"
        elif (
            self.event_type == GeofenceEventType.EXITED
            and self.zone.zone_type == "safe_zone"
        ):
            return "medium"
        return "low"


@dataclass
class RouteSegment:
    """Segment of a route with GPS points and statistics."""

    start_point: GPSPoint
    end_point: GPSPoint
    distance_meters: float
    duration_seconds: float
    avg_speed_mps: float | None = None
    elevation_gain: float | None = None

    @property
    def duration_minutes(self) -> float:
        """Get duration in minutes."""
        return self.duration_seconds / 60

    @property
    def distance_km(self) -> float:
        """Get distance in kilometers."""
        return self.distance_meters / 1000


@dataclass
class WalkRoute:
    """Complete walk route with GPS tracking data."""

    dog_id: str
    start_time: datetime
    end_time: datetime | None = None
    gps_points: list[GPSPoint] = field(default_factory=list)
    segments: list[RouteSegment] = field(default_factory=list)
    total_distance_meters: float = 0.0
    total_duration_seconds: float = 0.0
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    geofence_events: list[GeofenceEvent] = field(default_factory=list)
    route_quality: GPSAccuracy = GPSAccuracy.FAIR

    @property
    def is_active(self) -> bool:
        """Check if route is currently being tracked."""
        return self.end_time is None

    @property
    def duration_minutes(self) -> float:
        """Get total duration in minutes."""
        return self.total_duration_seconds / 60

    @property
    def distance_km(self) -> float:
        """Get total distance in kilometers."""
        return self.total_distance_meters / 1000

    @property
    def avg_speed_kmh(self) -> float | None:
        """Get average speed in km/h."""
        if self.avg_speed_mps is None:
            return None
        return self.avg_speed_mps * 3.6


class GPSTrackingConfig(NamedTuple):
    """GPS tracking configuration for a dog."""

    enabled: bool = True
    auto_start_walk: bool = True
    track_route: bool = True
    safety_alerts: bool = True
    geofence_notifications: bool = True
    auto_detect_home: bool = True
    accuracy_threshold: float = 50.0  # meters
    update_interval: int = 60  # seconds
    min_distance_for_point: float = 10.0  # meters
    route_smoothing: bool = True


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS points using Haversine formula.

    Args:
        lat1: Latitude of first point
        lon1: Longitude of first point
        lat2: Latitude of second point
        lon2: Longitude of second point

    Returns:
        Distance in meters
    """
    # Earth's radius in meters
    earth_radius_m = 6_371_000

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius_m * c


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate bearing between two GPS points.

    Args:
        lat1: Latitude of first point
        lon1: Longitude of first point
        lat2: Latitude of second point
        lon2: Longitude of second point

    Returns:
        Bearing in degrees (0-360)
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon_rad = math.radians(lon2 - lon1)

    y = math.sin(dlon_rad) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(
        lat2_rad
    ) * math.cos(dlon_rad)

    bearing = math.atan2(y, x)
    bearing_degrees = math.degrees(bearing)

    return (bearing_degrees + 360) % 360


class GPSGeofenceManager:
    """Manages GPS tracking and geofencing for PawControl dogs."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize GPS and geofencing manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._dog_configs: dict[str, GPSTrackingConfig] = {}
        self._active_routes: dict[str, WalkRoute] = {}
        self._geofence_zones: dict[str, list[GeofenceZone]] = {}
        self._zone_status: dict[
            str, dict[str, bool]
        ] = {}  # dog_id -> zone_name -> inside
        self._last_locations: dict[str, GPSPoint] = {}
        self._tracking_tasks: dict[str, asyncio.Task] = {}
        self._route_history: dict[str, list[WalkRoute]] = {}
        self._notification_manager: PawControlNotificationManager | None = None

        # RESILIENCE: Initialize resilience manager for GPS operations
        self.resilience_manager = ResilienceManager(hass)
        self._gps_retry_config = RetryConfig(
            max_attempts=3,  # 2 retries (3 total attempts)
            initial_delay=0.5,
            max_delay=2.0,
            exponential_base=2.0,
            jitter=True,
        )

        # Performance tracking
        self._stats = {
            "gps_points_processed": 0,
            "routes_completed": 0,
            "geofence_events": 0,
            "last_update": dt_util.utcnow(),
        }

    def set_notification_manager(
        self, manager: PawControlNotificationManager | None
    ) -> None:
        """Attach or detach the notification manager used for alerts."""

        self._notification_manager = manager

    async def async_configure_dog_gps(
        self, dog_id: str, config: dict[str, Any]
    ) -> None:
        """Configure GPS tracking for a specific dog.

        Args:
            dog_id: Dog identifier
            config: GPS configuration dictionary
        """
        try:
            gps_config = GPSTrackingConfig(
                enabled=config.get("enabled", True),
                auto_start_walk=config.get("auto_start_walk", True),
                track_route=config.get("track_route", True),
                safety_alerts=config.get("safety_alerts", True),
                geofence_notifications=config.get("geofence_notifications", True),
                auto_detect_home=config.get("auto_detect_home", True),
                accuracy_threshold=config.get("gps_accuracy_threshold", 50.0),
                update_interval=config.get("update_interval_seconds", 60),
                min_distance_for_point=config.get("min_distance_for_point", 10.0),
                route_smoothing=config.get("route_smoothing", True),
            )

            self._dog_configs[dog_id] = gps_config

            # Initialize zone status tracking
            if dog_id not in self._zone_status:
                self._zone_status[dog_id] = {}

            # Initialize route history
            if dog_id not in self._route_history:
                self._route_history[dog_id] = []

            _LOGGER.info(
                "Configured GPS tracking for %s: auto_walk=%s, tracking=%s, alerts=%s",
                dog_id,
                gps_config.auto_start_walk,
                gps_config.track_route,
                gps_config.safety_alerts,
            )

        except Exception as err:
            _LOGGER.error("Failed to configure GPS for %s: %s", dog_id, err)
            raise

    async def async_setup_geofence_zone(
        self,
        dog_id: str,
        zone_name: str,
        center_lat: float,
        center_lon: float,
        radius_meters: float,
        zone_type: str = "safe_zone",
        notifications_enabled: bool = True,
        breach_timeout_minutes: int = 15,
    ) -> None:
        """Setup a geofence zone for a dog.

        Args:
            dog_id: Dog identifier
            zone_name: Name of the zone
            center_lat: Center latitude
            center_lon: Center longitude
            radius_meters: Zone radius in meters
            zone_type: Type of zone (safe_zone, danger_zone, activity_zone)
            notifications_enabled: Enable notifications for this zone
            breach_timeout_minutes: Minutes outside zone before breach alert
        """
        try:
            zone = GeofenceZone(
                name=zone_name,
                center_lat=center_lat,
                center_lon=center_lon,
                radius_meters=radius_meters,
                zone_type=zone_type,
                enabled=True,
                notifications_enabled=notifications_enabled,
                breach_timeout_minutes=breach_timeout_minutes,
            )

            if dog_id not in self._geofence_zones:
                self._geofence_zones[dog_id] = []

            # Remove existing zone with same name
            self._geofence_zones[dog_id] = [
                z for z in self._geofence_zones[dog_id] if z.name != zone_name
            ]

            # Add new zone
            self._geofence_zones[dog_id].append(zone)

            # Initialize zone status
            if dog_id not in self._zone_status:
                self._zone_status[dog_id] = {}
            self._zone_status[dog_id][zone_name] = True  # Assume inside initially

            _LOGGER.info(
                "Setup geofence zone for %s: %s at %.6f,%.6f radius=%dm",
                dog_id,
                zone_name,
                center_lat,
                center_lon,
                radius_meters,
            )

        except Exception as err:
            _LOGGER.error("Failed to setup geofence zone for %s: %s", dog_id, err)
            raise

    async def async_setup_safe_zone(
        self,
        dog_id: str,
        center_lat: float,
        center_lon: float,
        radius_meters: float,
        notifications_enabled: bool = True,
    ) -> None:
        """Setup a safe zone (convenience method for home/safe areas).

        Args:
            dog_id: Dog identifier
            center_lat: Center latitude
            center_lon: Center longitude
            radius_meters: Safe zone radius in meters
            notifications_enabled: Enable notifications for zone breaches
        """
        await self.async_setup_geofence_zone(
            dog_id=dog_id,
            zone_name="home_safe_zone",
            center_lat=center_lat,
            center_lon=center_lon,
            radius_meters=radius_meters,
            zone_type="safe_zone",
            notifications_enabled=notifications_enabled,
            breach_timeout_minutes=15,
        )

    async def async_start_gps_tracking(
        self,
        dog_id: str,
        walker: str | None = None,
        track_route: bool = True,
        safety_alerts: bool = True,
    ) -> str:
        """Start GPS tracking for a walk.

        Args:
            dog_id: Dog identifier
            walker: Name of person walking the dog
            track_route: Whether to track and save the route
            safety_alerts: Whether to send safety alerts

        Returns:
            Route/session ID for the tracking session
        """
        try:
            # End any existing active route
            if dog_id in self._active_routes:
                await self.async_end_gps_tracking(dog_id, save_route=True)

            # Create new route
            route = WalkRoute(
                dog_id=dog_id,
                start_time=dt_util.utcnow(),
            )

            self._active_routes[dog_id] = route

            # Start tracking task if configured
            config = self._dog_configs.get(dog_id)
            if config and config.enabled and track_route:
                await self._start_tracking_task(dog_id)

            session_id = f"{dog_id}_{int(route.start_time.timestamp())}"

            _LOGGER.info(
                "Started GPS tracking for %s: session=%s, route_tracking=%s, alerts=%s",
                dog_id,
                session_id,
                track_route,
                safety_alerts,
            )

            return session_id

        except Exception as err:
            _LOGGER.error("Failed to start GPS tracking for %s: %s", dog_id, err)
            raise

    async def async_end_gps_tracking(
        self,
        dog_id: str,
        save_route: bool = True,
        notes: str | None = None,
    ) -> WalkRoute | None:
        """End GPS tracking for a walk.

        Args:
            dog_id: Dog identifier
            save_route: Whether to save the route to history
            notes: Optional notes about the walk

        Returns:
            Completed walk route or None if no active route
        """
        try:
            route = self._active_routes.get(dog_id)
            if not route:
                _LOGGER.warning("No active GPS tracking found for %s", dog_id)
                return None

            # Stop tracking task
            await self._stop_tracking_task(dog_id)

            # Finalize route
            route.end_time = dt_util.utcnow()

            if route.gps_points:
                # Calculate final statistics
                await self._calculate_route_statistics(route)

                # Save to history if requested
                if save_route:
                    if dog_id not in self._route_history:
                        self._route_history[dog_id] = []
                    self._route_history[dog_id].append(route)

                    # Limit history size (keep last 100 routes)
                    if len(self._route_history[dog_id]) > 100:
                        self._route_history[dog_id] = self._route_history[dog_id][-100:]

            # Remove from active routes
            del self._active_routes[dog_id]

            # Update stats
            self._stats["routes_completed"] += 1
            self._stats["last_update"] = dt_util.utcnow()

            _LOGGER.info(
                "Ended GPS tracking for %s: %.2f km in %.1f minutes, %d points",
                dog_id,
                route.distance_km,
                route.duration_minutes,
                len(route.gps_points),
            )

            return route

        except Exception as err:
            _LOGGER.error("Failed to end GPS tracking for %s: %s", dog_id, err)
            raise

    async def async_add_gps_point(
        self,
        dog_id: str,
        latitude: float,
        longitude: float,
        altitude: float | None = None,
        accuracy: float | None = None,
        timestamp: datetime | None = None,
        source: LocationSource = LocationSource.DEVICE_TRACKER,
    ) -> bool:
        """Add a GPS point to the tracking system.

        Args:
            dog_id: Dog identifier
            latitude: GPS latitude
            longitude: GPS longitude
            altitude: GPS altitude in meters
            accuracy: GPS accuracy in meters
            timestamp: Point timestamp
            source: Source of location data

        Returns:
            True if point was added successfully
        """
        try:
            if timestamp is None:
                timestamp = dt_util.utcnow()

            # Create GPS point
            gps_point = GPSPoint(
                latitude=latitude,
                longitude=longitude,
                timestamp=timestamp,
                altitude=altitude,
                accuracy=accuracy,
                source=source,
            )

            # Check accuracy threshold
            config = self._dog_configs.get(dog_id)
            if config and accuracy and accuracy > config.accuracy_threshold:
                _LOGGER.debug(
                    "GPS point for %s rejected: accuracy %.1fm > threshold %.1fm",
                    dog_id,
                    accuracy,
                    config.accuracy_threshold,
                )
                return False

            # Update last known location
            self._last_locations[dog_id] = gps_point

            # Add to active route if tracking
            route = self._active_routes.get(dog_id)
            if route:
                # Check minimum distance filter
                if config and route.gps_points and config.min_distance_for_point > 0:
                    last_point = route.gps_points[-1]
                    distance = calculate_distance(
                        last_point.latitude, last_point.longitude, latitude, longitude
                    )
                    if distance < config.min_distance_for_point:
                        _LOGGER.debug(
                            "GPS point for %s filtered: distance %.1fm < minimum %.1fm",
                            dog_id,
                            distance,
                            config.min_distance_for_point,
                        )
                        return False

                route.gps_points.append(gps_point)

                # Update route statistics
                if len(route.gps_points) > 1:
                    await self._update_route_with_new_point(route, gps_point)

            # Check geofence zones
            await self._check_geofence_zones(dog_id, gps_point)

            # Update stats
            self._stats["gps_points_processed"] += 1
            self._stats["last_update"] = dt_util.utcnow()

            _LOGGER.debug(
                "Added GPS point for %s: %.6f,%.6f (accuracy: %.1fm)",
                dog_id,
                latitude,
                longitude,
                accuracy or 0,
            )

            return True

        except Exception as err:
            _LOGGER.error("Failed to add GPS point for %s: %s", dog_id, err)
            return False

    async def async_export_routes(
        self,
        dog_id: str,
        export_format: str = "gpx",
        last_n_routes: int = 1,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Export dog routes in specified format.

        Args:
            dog_id: Dog identifier
            export_format: Export format (gpx, json, csv)
            last_n_routes: Number of recent routes to export
            date_from: Start date filter
            date_to: End date filter

        Returns:
            Exported route data or None if no routes found
        """
        try:
            routes = self._route_history.get(dog_id, [])
            if not routes:
                _LOGGER.warning("No route history found for %s", dog_id)
                return None

            # Filter routes by date if specified
            if date_from or date_to:
                filtered_routes = []
                for route in routes:
                    if date_from and route.start_time < date_from:
                        continue
                    if date_to and route.start_time > date_to:
                        continue
                    filtered_routes.append(route)
                routes = filtered_routes

            # Limit to last N routes
            if last_n_routes > 0:
                routes = routes[-last_n_routes:]

            if not routes:
                _LOGGER.warning("No routes found matching criteria for %s", dog_id)
                return None

            # Export based on format
            if export_format.lower() == "gpx":
                return await self._export_routes_gpx(dog_id, routes)
            elif export_format.lower() == "json":
                return await self._export_routes_json(dog_id, routes)
            elif export_format.lower() == "csv":
                return await self._export_routes_csv(dog_id, routes)
            else:
                raise ValueError(f"Unsupported export format: {export_format}")

        except Exception as err:
            _LOGGER.error("Failed to export routes for %s: %s", dog_id, err)
            raise

    async def async_get_current_location(self, dog_id: str) -> GPSPoint | None:
        """Get the current/last known location for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Last known GPS point or None
        """
        return self._last_locations.get(dog_id)

    async def async_get_active_route(self, dog_id: str) -> WalkRoute | None:
        """Get currently active route for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Active walk route or None
        """
        return self._active_routes.get(dog_id)

    async def async_get_geofence_status(self, dog_id: str) -> dict[str, Any]:
        """Get current geofence status for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Geofence status information
        """
        zones = self._geofence_zones.get(dog_id, [])
        zone_status = self._zone_status.get(dog_id, {})
        current_location = self._last_locations.get(dog_id)

        status = {
            "dog_id": dog_id,
            "zones_configured": len(zones),
            "current_location": None,
            "zone_status": {},
            "safe_zone_breaches": 0,
            "last_update": None,
        }

        if current_location:
            status["current_location"] = {
                "latitude": current_location.latitude,
                "longitude": current_location.longitude,
                "timestamp": current_location.timestamp.isoformat(),
                "accuracy": current_location.accuracy,
            }
            status["last_update"] = current_location.timestamp.isoformat()

        for zone in zones:
            is_inside = zone_status.get(zone.name, True)
            distance_to_center = 0.0

            if current_location:
                distance_to_center = zone.distance_to_center(
                    current_location.latitude, current_location.longitude
                )

            status["zone_status"][zone.name] = {
                "inside": is_inside,
                "zone_type": zone.zone_type,
                "radius_meters": zone.radius_meters,
                "distance_to_center": distance_to_center,
                "notifications_enabled": zone.notifications_enabled,
            }

            if zone.zone_type == "safe_zone" and not is_inside:
                status["safe_zone_breaches"] += 1

        return status

    async def async_get_statistics(self) -> dict[str, Any]:
        """Get GPS and geofencing statistics.

        Returns:
            Statistics dictionary
        """
        total_routes = sum(len(routes) for routes in self._route_history.values())
        active_tracking = len(self._active_routes)

        return {
            **self._stats,
            "dogs_configured": len(self._dog_configs),
            "active_tracking_sessions": active_tracking,
            "total_routes_stored": total_routes,
            "geofence_zones_configured": sum(
                len(zones) for zones in self._geofence_zones.values()
            ),
        }

    async def _start_tracking_task(self, dog_id: str) -> None:
        """Start background tracking task for a dog."""
        await self._stop_tracking_task(dog_id)  # Stop any existing task

        config = self._dog_configs.get(dog_id)
        if not config or not config.enabled:
            return

        async def _tracking_loop() -> None:
            """Background task for GPS tracking."""
            try:
                while dog_id in self._active_routes:
                    # Try to get location from device tracker
                    await self._update_location_from_device_tracker(dog_id)

                    # Wait for next update
                    await asyncio.sleep(config.update_interval)

            except asyncio.CancelledError:
                _LOGGER.debug("GPS tracking task cancelled for %s", dog_id)
            except Exception as err:
                _LOGGER.error("GPS tracking task error for %s: %s", dog_id, err)

        task = self.hass.async_create_task(_tracking_loop())
        self._tracking_tasks[dog_id] = task

        _LOGGER.debug("Started GPS tracking task for %s", dog_id)

    async def _stop_tracking_task(self, dog_id: str) -> None:
        """Stop background tracking task for a dog."""
        task = self._tracking_tasks.pop(dog_id, None)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        _LOGGER.debug("Stopped GPS tracking task for %s", dog_id)

    async def _update_location_from_device_tracker(self, dog_id: str) -> None:
        """Try to update location from associated device tracker with retry."""
        
        async def _fetch_device_tracker_location() -> None:
            """Internal function to fetch location - wrapped by retry logic."""
            # Try to find device tracker entity for this dog
            entity_registry = er.async_get(self.hass)
            dr.async_get(self.hass)

            # Look for device tracker entities that might belong to this dog
            for entity in entity_registry.entities.values():
                if (
                    entity.platform == "device_tracker"
                    and dog_id.lower() in (entity.name or "").lower()
                ):
                    state = self.hass.states.get(entity.entity_id)
                    if state and state.state not in ["unavailable", "unknown"]:
                        # Extract GPS coordinates
                        lat = state.attributes.get("latitude")
                        lon = state.attributes.get("longitude")
                        accuracy = state.attributes.get("gps_accuracy")

                        if lat is not None and lon is not None:
                            await self.async_add_gps_point(
                                dog_id=dog_id,
                                latitude=lat,
                                longitude=lon,
                                accuracy=accuracy,
                                source=LocationSource.DEVICE_TRACKER,
                            )
                            return

            # Could also check for companion app entities, etc.
        
        # RESILIENCE: Wrap in retry logic for transient failures
        try:
            await self.resilience_manager.execute_with_resilience(
                _fetch_device_tracker_location,
                retry_config=self._gps_retry_config,
            )
        except Exception as err:
            _LOGGER.debug(
                "Failed to update location from device tracker for %s after retries: %s",
                dog_id,
                err,
            )

    async def _check_geofence_zones(self, dog_id: str, gps_point: GPSPoint) -> None:
        """Check GPS point against all geofence zones for a dog."""
        zones = self._geofence_zones.get(dog_id, [])
        if not zones:
            return

        zone_status = self._zone_status.get(dog_id, {})

        for zone in zones:
            if not zone.enabled:
                continue

            is_inside = zone.contains_point(gps_point.latitude, gps_point.longitude)
            was_inside = zone_status.get(zone.name, True)

            # Check for zone transitions
            if is_inside != was_inside:
                event_type = (
                    GeofenceEventType.ENTERED if is_inside else GeofenceEventType.EXITED
                )

                distance_from_center = zone.distance_to_center(
                    gps_point.latitude, gps_point.longitude
                )

                event = GeofenceEvent(
                    dog_id=dog_id,
                    zone=zone,
                    event_type=event_type,
                    location=gps_point,
                    distance_from_center=distance_from_center,
                    previous_status=was_inside,
                )

                # Update zone status
                zone_status[zone.name] = is_inside
                self._zone_status[dog_id] = zone_status

                # Add to active route if tracking
                route = self._active_routes.get(dog_id)
                if route:
                    route.geofence_events.append(event)

                # Send notification if enabled
                if zone.notifications_enabled:
                    await self._send_geofence_notification(event)

                # Update stats
                self._stats["geofence_events"] += 1

                _LOGGER.info(
                    "Geofence event for %s: %s %s zone '%s' (distance: %.1fm)",
                    dog_id,
                    event_type.value,
                    zone.zone_type,
                    zone.name,
                    distance_from_center,
                )

    async def _send_geofence_notification(self, event: GeofenceEvent) -> None:
        """Send notification for geofence event."""
        try:
            event_payload: dict[str, Any] = {
                "dog_id": event.dog_id,
                "zone": event.zone.name,
                "zone_type": event.zone.zone_type,
                "event": event.event_type.value,
                "distance_meters": round(event.distance_from_center, 2),
                "timestamp": event.timestamp.isoformat(),
                "latitude": event.location.latitude,
                "longitude": event.location.longitude,
            }
            if event.duration_outside:
                event_payload["duration_seconds"] = int(
                    event.duration_outside.total_seconds()
                )

            hass_event = {
                GeofenceEventType.ENTERED: EVENT_GEOFENCE_ENTERED,
                GeofenceEventType.EXITED: EVENT_GEOFENCE_LEFT,
                GeofenceEventType.BREACH: EVENT_GEOFENCE_BREACH,
                GeofenceEventType.RETURN: EVENT_GEOFENCE_RETURN,
            }[event.event_type]
            self.hass.bus.async_fire(hass_event, event_payload)

            title = f"Geofence alert • {event.dog_id}"
            zone_name = event.zone.name
            distance = event_payload["distance_meters"]

            if event.event_type == GeofenceEventType.ENTERED:
                message = f"{event.dog_id} entered {zone_name}."
                priority = NotificationPriority.NORMAL
            elif event.event_type == GeofenceEventType.RETURN:
                message = f"{event.dog_id} returned to {zone_name}."
                priority = NotificationPriority.NORMAL
            elif event.event_type == GeofenceEventType.EXITED:
                message = (
                    f"{event.dog_id} left {zone_name} and is {distance:.0f} m away."
                )
                priority = (
                    NotificationPriority.HIGH
                    if event.zone.zone_type == "safe_zone"
                    else NotificationPriority.NORMAL
                )
            else:
                duration = event_payload.get("duration_seconds", 0)
                minutes = duration / 60 if duration else 0
                message = f"{event.dog_id} has been outside {zone_name} for {minutes:.1f} minutes"
                priority = NotificationPriority.URGENT

            notification_data = {
                "zone": zone_name,
                "zone_type": event.zone.zone_type,
                "event": event.event_type.value,
                "distance_meters": distance,
                "coordinates": {
                    "latitude": event.location.latitude,
                    "longitude": event.location.longitude,
                },
            }
            if event.duration_outside:
                notification_data["duration_seconds"] = event_payload[
                    "duration_seconds"
                ]

            _LOGGER.info("Geofence notification: %s - %s", title, message)

            if self._notification_manager:
                await self._notification_manager.async_send_notification(
                    NotificationType.GEOFENCE_ALERT,
                    title,
                    message,
                    dog_id=event.dog_id,
                    priority=priority,
                    data=notification_data,
                )

        except Exception as err:
            _LOGGER.error("Failed to send geofence notification: %s", err)

    async def _calculate_route_statistics(self, route: WalkRoute) -> None:
        """Calculate comprehensive statistics for a completed route."""
        if not route.gps_points:
            return

        total_distance = 0.0
        total_time = 0.0
        speeds = []

        # Calculate segments and statistics
        route.segments = []

        for i in range(1, len(route.gps_points)):
            prev_point = route.gps_points[i - 1]
            curr_point = route.gps_points[i]

            # Calculate distance
            distance = calculate_distance(
                prev_point.latitude,
                prev_point.longitude,
                curr_point.latitude,
                curr_point.longitude,
            )

            # Calculate time
            time_diff = (curr_point.timestamp - prev_point.timestamp).total_seconds()

            # Skip invalid segments
            if time_diff <= 0 or distance > 1000:  # Skip if >1km between points
                continue

            # Calculate speed
            speed_mps = distance / time_diff if time_diff > 0 else 0

            # Create segment
            segment = RouteSegment(
                start_point=prev_point,
                end_point=curr_point,
                distance_meters=distance,
                duration_seconds=time_diff,
                avg_speed_mps=speed_mps,
            )

            route.segments.append(segment)

            total_distance += distance
            total_time += time_diff
            speeds.append(speed_mps)

        # Update route totals
        route.total_distance_meters = total_distance
        route.total_duration_seconds = total_time

        if speeds:
            route.avg_speed_mps = sum(speeds) / len(speeds)
            route.max_speed_mps = max(speeds)

        # Assess route quality based on GPS accuracy
        accurate_points = sum(1 for p in route.gps_points if p.is_accurate)
        accuracy_ratio = accurate_points / len(route.gps_points)

        if accuracy_ratio >= 0.9:
            route.route_quality = GPSAccuracy.EXCELLENT
        elif accuracy_ratio >= 0.7:
            route.route_quality = GPSAccuracy.GOOD
        elif accuracy_ratio >= 0.5:
            route.route_quality = GPSAccuracy.FAIR
        else:
            route.route_quality = GPSAccuracy.POOR

    async def _update_route_with_new_point(
        self, route: WalkRoute, new_point: GPSPoint
    ) -> None:
        """Update route statistics with a new GPS point."""
        if len(route.gps_points) < 2:
            return

        prev_point = route.gps_points[-2]

        # Calculate distance for this segment
        distance = calculate_distance(
            prev_point.latitude,
            prev_point.longitude,
            new_point.latitude,
            new_point.longitude,
        )

        # Update total distance
        route.total_distance_meters += distance

        # Update total time
        route.total_duration_seconds = (
            new_point.timestamp - route.start_time
        ).total_seconds()

    async def _export_routes_gpx(
        self, dog_id: str, routes: list[WalkRoute]
    ) -> dict[str, Any]:
        """Export routes in GPX format."""
        gpx_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
        gpx_content += '<gpx version="1.1" creator="PawControl">\n'

        for route in routes:
            gpx_content += "  <trk>\n"
            gpx_content += (
                f"    <name>Walk {route.start_time.strftime('%Y-%m-%d %H:%M')}</name>\n"
            )
            gpx_content += "    <trkseg>\n"

            for point in route.gps_points:
                gpx_content += (
                    f'      <trkpt lat="{point.latitude}" lon="{point.longitude}">\n'
                )
                if point.altitude is not None:
                    gpx_content += f"        <ele>{point.altitude}</ele>\n"
                gpx_content += f"        <time>{point.timestamp.isoformat()}Z</time>\n"
                gpx_content += "      </trkpt>\n"

            gpx_content += "    </trkseg>\n"
            gpx_content += "  </trk>\n"

        gpx_content += "</gpx>\n"

        return {
            "format": "gpx",
            "content": gpx_content,
            "filename": f"{dog_id}_routes_{dt_util.utcnow().strftime('%Y%m%d')}.gpx",
            "routes_count": len(routes),
        }

    async def _export_routes_json(
        self, dog_id: str, routes: list[WalkRoute]
    ) -> dict[str, Any]:
        """Export routes in JSON format."""
        export_data = {
            "dog_id": dog_id,
            "export_timestamp": dt_util.utcnow().isoformat(),
            "routes": [],
        }

        for route in routes:
            route_data = {
                "start_time": route.start_time.isoformat(),
                "end_time": route.end_time.isoformat() if route.end_time else None,
                "duration_minutes": route.duration_minutes,
                "distance_km": route.distance_km,
                "avg_speed_kmh": route.avg_speed_kmh,
                "route_quality": route.route_quality.value,
                "gps_points": [
                    {
                        "latitude": p.latitude,
                        "longitude": p.longitude,
                        "timestamp": p.timestamp.isoformat(),
                        "altitude": p.altitude,
                        "accuracy": p.accuracy,
                        "source": p.source.value,
                    }
                    for p in route.gps_points
                ],
                "geofence_events": [
                    {
                        "event_type": e.event_type.value,
                        "zone_name": e.zone.name,
                        "timestamp": e.timestamp.isoformat(),
                        "distance_from_center": e.distance_from_center,
                        "severity": e.severity,
                    }
                    for e in route.geofence_events
                ],
            }
            export_data["routes"].append(route_data)

        return {
            "format": "json",
            "content": export_data,
            "filename": f"{dog_id}_routes_{dt_util.utcnow().strftime('%Y%m%d')}.json",
            "routes_count": len(routes),
        }

    async def _export_routes_csv(
        self, dog_id: str, routes: list[WalkRoute]
    ) -> dict[str, Any]:
        """Export routes in CSV format."""
        csv_lines = [
            "timestamp,latitude,longitude,altitude,accuracy,route_id,distance_km,duration_min"
        ]

        for index, route in enumerate(routes, start=1):
            route_id = f"route_{index}"

            csv_lines.extend(
                ",".join(
                    [
                        point.timestamp.isoformat(),
                        str(point.latitude),
                        str(point.longitude),
                        str(point.altitude if point.altitude is not None else ""),
                        str(point.accuracy if point.accuracy is not None else ""),
                        route_id,
                        str(route.distance_km),
                        str(route.duration_minutes),
                    ]
                )
                for point in route.gps_points
            )

        csv_content = "\n".join(csv_lines)

        return {
            "format": "csv",
            "content": csv_content,
            "filename": f"{dog_id}_routes_{dt_util.utcnow().strftime('%Y%m%d')}.csv",
            "routes_count": len(routes),
        }

    async def async_cleanup(self) -> None:
        """Cleanup GPS manager resources."""
        # Stop all tracking tasks
        for dog_id in list(self._tracking_tasks.keys()):
            await self._stop_tracking_task(dog_id)

        # Clear all data
        self._dog_configs.clear()
        self._active_routes.clear()
        self._geofence_zones.clear()
        self._zone_status.clear()
        self._last_locations.clear()
        self._route_history.clear()

        _LOGGER.debug("GPS and geofencing manager cleaned up")
