"""GPS and Geofencing management for PawControl.

Provides comprehensive GPS tracking, route management, geofencing with safety zones,
and location-based alerts for dogs. Includes automatic walk detection and real-time
location monitoring with configurable safety boundaries.

Quality Scale: Platinum target
Home Assistant: 2025.9.4+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import inspect
import logging
import math
from typing import Any, NamedTuple, cast
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
  EVENT_GEOFENCE_BREACH,
  EVENT_GEOFENCE_ENTERED,
  EVENT_GEOFENCE_LEFT,
  EVENT_GEOFENCE_RETURN,
)
from .notifications import (
  NotificationPriority,
  NotificationTemplateData,
  NotificationType,
  PawControlNotificationManager,
)
from .resilience import ResilienceManager, RetryConfig
from .types import (
  GeofenceEventPayload,
  GeofenceNotificationCoordinates,
  GeofenceNotificationData,
  GPSGeofenceLocationSnapshot,
  GPSGeofenceStatusSnapshot,
  GPSGeofenceZoneStatusSnapshot,
  GPSManagerStatisticsSnapshot,
  GPSManagerStats,
  GPSRouteExportCSVPayload,
  GPSRouteExportGPXPayload,
  GPSRouteExportJSONContent,
  GPSRouteExportJSONEvent,
  GPSRouteExportJSONPayload,
  GPSRouteExportJSONPoint,
  GPSRouteExportJSONRoute,
  GPSRouteExportPayload,
  GPSTrackingConfigInput,
  JSONMapping,
)
from .utils import async_fire_event, normalize_value

_LOGGER = logging.getLogger(__name__)

_TRACKING_UPDATE_TIMEOUT = 30.0
_TASK_CANCEL_TIMEOUT = 5.0


class GeofenceEventType(Enum):
  """Types of geofence events."""  # noqa: E111

  ENTERED = "entered"  # noqa: E111
  EXITED = "exited"  # noqa: E111
  BREACH = "breach"  # Outside safe zone for too long  # noqa: E111
  RETURN = "return"  # Back within safe zone  # noqa: E111


class GPSAccuracy(Enum):
  """GPS accuracy levels."""  # noqa: E111

  EXCELLENT = "excellent"  # <5m  # noqa: E111
  GOOD = "good"  # 5-15m  # noqa: E111
  FAIR = "fair"  # 15-50m  # noqa: E111
  POOR = "poor"  # >50m  # noqa: E111


class LocationSource(Enum):
  """Source of location data."""  # noqa: E111

  DEVICE_TRACKER = "device_tracker"  # noqa: E111
  MANUAL_INPUT = "manual_input"  # noqa: E111
  COMPANION_APP = "companion_app"  # noqa: E111
  EXTERNAL_API = "external_api"  # noqa: E111
  WEBHOOK = "webhook"  # noqa: E111
  MQTT = "mqtt"  # noqa: E111
  ENTITY = "entity"  # noqa: E111


@dataclass
class GPSPoint:
  """Single GPS coordinate point with metadata."""  # noqa: E111

  latitude: float  # noqa: E111
  longitude: float  # noqa: E111
  timestamp: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111
  altitude: float | None = None  # noqa: E111
  accuracy: float | None = None  # noqa: E111
  speed: float | None = None  # noqa: E111
  heading: float | None = None  # noqa: E111
  source: LocationSource = LocationSource.DEVICE_TRACKER  # noqa: E111
  battery_level: int | None = None  # noqa: E111

  @property  # noqa: E111
  def accuracy_level(self) -> GPSAccuracy:  # noqa: E111
    """Get accuracy level based on accuracy value."""
    if self.accuracy is None:
      return GPSAccuracy.FAIR  # noqa: E111
    if self.accuracy < 5:
      return GPSAccuracy.EXCELLENT  # noqa: E111
    if self.accuracy < 15:
      return GPSAccuracy.GOOD  # noqa: E111
    if self.accuracy < 50:
      return GPSAccuracy.FAIR  # noqa: E111
    return GPSAccuracy.POOR

  @property  # noqa: E111
  def is_accurate(self) -> bool:  # noqa: E111
    """Check if GPS point is accurate enough for tracking."""
    return self.accuracy_level in [
      GPSAccuracy.EXCELLENT,
      GPSAccuracy.GOOD,
      GPSAccuracy.FAIR,
    ]


@dataclass
class GeofenceZone:
  """Geofence zone definition with safety parameters."""  # noqa: E111

  name: str  # noqa: E111
  center_lat: float  # noqa: E111
  center_lon: float  # noqa: E111
  radius_meters: float  # noqa: E111
  zone_type: str = "safe_zone"  # safe_zone, danger_zone, activity_zone  # noqa: E111
  enabled: bool = True  # noqa: E111
  notifications_enabled: bool = True  # noqa: E111
  breach_timeout_minutes: int = (
    15  # Time outside zone before breach alert  # noqa: E111
  )
  created_at: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111

  def contains_point(self, lat: float, lon: float) -> bool:  # noqa: E111
    """Check if a point is within this geofence zone."""
    distance = calculate_distance(
      self.center_lat,
      self.center_lon,
      lat,
      lon,
    )
    return distance <= self.radius_meters

  def distance_to_center(self, lat: float, lon: float) -> float:  # noqa: E111
    """Calculate distance from point to zone center in meters."""
    return calculate_distance(self.center_lat, self.center_lon, lat, lon)


@dataclass
class GeofenceEvent:
  """Geofence event with context information."""  # noqa: E111

  dog_id: str  # noqa: E111
  zone: GeofenceZone  # noqa: E111
  event_type: GeofenceEventType  # noqa: E111
  location: GPSPoint  # noqa: E111
  distance_from_center: float  # noqa: E111
  timestamp: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111
  previous_status: bool | None = None  # Was inside zone before event  # noqa: E111
  duration_outside: timedelta | None = None  # For breach events  # noqa: E111

  @property  # noqa: E111
  def severity(self) -> str:  # noqa: E111
    """Get event severity level."""
    if self.event_type == GeofenceEventType.BREACH:
      if (  # noqa: E111
        self.duration_outside and self.duration_outside.total_seconds() > 1800
      ):  # 30 min
        return "high"
      return "medium"  # noqa: E111
    if (
      self.event_type == GeofenceEventType.EXITED and self.zone.zone_type == "safe_zone"
    ):
      return "medium"  # noqa: E111
    return "low"


@dataclass
class RouteSegment:
  """Segment of a route with GPS points and statistics."""  # noqa: E111

  start_point: GPSPoint  # noqa: E111
  end_point: GPSPoint  # noqa: E111
  distance_meters: float  # noqa: E111
  duration_seconds: float  # noqa: E111
  avg_speed_mps: float | None = None  # noqa: E111
  elevation_gain: float | None = None  # noqa: E111

  @property  # noqa: E111
  def duration_minutes(self) -> float:  # noqa: E111
    """Get duration in minutes."""
    return self.duration_seconds / 60

  @property  # noqa: E111
  def distance_km(self) -> float:  # noqa: E111
    """Get distance in kilometers."""
    return self.distance_meters / 1000


@dataclass
class WalkRoute:
  """Complete walk route with GPS tracking data."""  # noqa: E111

  dog_id: str  # noqa: E111
  start_time: datetime  # noqa: E111
  end_time: datetime | None = None  # noqa: E111
  gps_points: list[GPSPoint] = field(default_factory=list)  # noqa: E111
  segments: list[RouteSegment] = field(default_factory=list)  # noqa: E111
  total_distance_meters: float = 0.0  # noqa: E111
  total_duration_seconds: float = 0.0  # noqa: E111
  avg_speed_mps: float | None = None  # noqa: E111
  max_speed_mps: float | None = None  # noqa: E111
  geofence_events: list[GeofenceEvent] = field(default_factory=list)  # noqa: E111
  route_quality: GPSAccuracy = GPSAccuracy.FAIR  # noqa: E111

  @property  # noqa: E111
  def is_active(self) -> bool:  # noqa: E111
    """Check if route is currently being tracked."""
    return self.end_time is None

  @property  # noqa: E111
  def duration_minutes(self) -> float:  # noqa: E111
    """Get total duration in minutes."""
    return self.total_duration_seconds / 60

  @property  # noqa: E111
  def distance_km(self) -> float:  # noqa: E111
    """Get total distance in kilometers."""
    return self.total_distance_meters / 1000

  @property  # noqa: E111
  def avg_speed_kmh(self) -> float | None:  # noqa: E111
    """Get average speed in km/h."""
    if self.avg_speed_mps is None:
      return None  # noqa: E111
    return self.avg_speed_mps * 3.6


class GPSTrackingConfig(NamedTuple):
  """GPS tracking configuration for a dog."""  # noqa: E111

  enabled: bool = True  # noqa: E111
  auto_start_walk: bool = True  # noqa: E111
  track_route: bool = True  # noqa: E111
  safety_alerts: bool = True  # noqa: E111
  geofence_notifications: bool = True  # noqa: E111
  auto_detect_home: bool = True  # noqa: E111
  accuracy_threshold: float = 50.0  # meters  # noqa: E111
  update_interval: int = 60  # seconds  # noqa: E111
  min_distance_for_point: float = 10.0  # meters  # noqa: E111
  route_smoothing: bool = True  # noqa: E111


def _coerce_tracking_bool(value: object | None, default: bool) -> bool:
  """Return a boolean configuration flag, falling back to ``default``."""  # noqa: E111

  return value if isinstance(value, bool) else default  # noqa: E111


def _coerce_tracking_float(value: object | None, default: float) -> float:
  """Return a floating-point configuration value with defensive conversion."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return default
  if isinstance(value, int | float):  # noqa: E111
    return float(value)
  return default  # noqa: E111


def _coerce_tracking_int(value: object | None, default: int) -> int:
  """Return an integer configuration value while filtering bools."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return default
  if isinstance(value, int):  # noqa: E111
    return value
  if isinstance(value, float):  # noqa: E111
    return int(value)
  return default  # noqa: E111


def _build_tracking_config(config: GPSTrackingConfigInput) -> GPSTrackingConfig:
  """Normalise external GPS tracking inputs into the runtime configuration."""  # noqa: E111

  return GPSTrackingConfig(  # noqa: E111
    enabled=_coerce_tracking_bool(config.get("enabled"), True),
    auto_start_walk=_coerce_tracking_bool(
      config.get("auto_start_walk"),
      True,
    ),
    track_route=_coerce_tracking_bool(config.get("track_route"), True),
    safety_alerts=_coerce_tracking_bool(config.get("safety_alerts"), True),
    geofence_notifications=_coerce_tracking_bool(
      config.get("geofence_notifications"),
      True,
    ),
    auto_detect_home=_coerce_tracking_bool(
      config.get("auto_detect_home"),
      True,
    ),
    accuracy_threshold=_coerce_tracking_float(
      config.get("gps_accuracy_threshold"),
      50.0,
    ),
    update_interval=_coerce_tracking_int(
      config.get("update_interval_seconds"),
      60,
    ),
    min_distance_for_point=_coerce_tracking_float(
      config.get("min_distance_for_point"),
      10.0,
    ),
    route_smoothing=_coerce_tracking_bool(
      config.get("route_smoothing"),
      True,
    ),
  )


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  """Calculate distance between two GPS points using Haversine formula.

  Args:
      lat1: Latitude of first point
      lon1: Longitude of first point
      lat2: Latitude of second point
      lon2: Longitude of second point

  Returns:
      Distance in meters
  """  # noqa: E111
  # Earth's radius in meters  # noqa: E114
  earth_radius_m = 6_371_000  # noqa: E111

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

  return earth_radius_m * c  # noqa: E111


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  """Calculate bearing between two GPS points.

  Args:
      lat1: Latitude of first point
      lon1: Longitude of first point
      lat2: Latitude of second point
      lon2: Longitude of second point

  Returns:
      Bearing in degrees (0-360)
  """  # noqa: E111
  lat1_rad = math.radians(lat1)  # noqa: E111
  lat2_rad = math.radians(lat2)  # noqa: E111
  dlon_rad = math.radians(lon2 - lon1)  # noqa: E111

  y = math.sin(dlon_rad) * math.cos(lat2_rad)  # noqa: E111
  x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(  # noqa: E111
    lat2_rad,
  ) * math.cos(dlon_rad)

  bearing = math.atan2(y, x)  # noqa: E111
  bearing_degrees = math.degrees(bearing)  # noqa: E111

  return (bearing_degrees + 360) % 360  # noqa: E111


class GPSGeofenceManager:
  """Manages GPS tracking and geofencing for PawControl dogs."""  # noqa: E111

  def __init__(self, hass: HomeAssistant) -> None:  # noqa: E111
    """Initialize GPS and geofencing manager.

    Args:
        hass: Home Assistant instance
    """
    self.hass = hass
    self._dog_configs: dict[str, GPSTrackingConfig] = {}
    self._active_routes: dict[str, WalkRoute] = {}
    self._geofence_zones: dict[str, list[GeofenceZone]] = {}
    self._zone_status: dict[
      str,
      dict[str, bool],
    ] = {}  # dog_id -> zone_name -> inside
    self._last_locations: dict[str, GPSPoint] = {}
    self._tracking_tasks: dict[str, asyncio.Task[Any]] = {}
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
    self._stats: GPSManagerStats = {
      "gps_points_processed": 0,
      "routes_completed": 0,
      "geofence_events": 0,
      "last_update": dt_util.utcnow(),
    }

  def set_notification_manager(  # noqa: E111
    self,
    manager: PawControlNotificationManager | None,
  ) -> None:
    """Attach or detach the notification manager used for alerts."""

    self._notification_manager = manager

  async def async_configure_dog_gps(  # noqa: E111
    self,
    dog_id: str,
    config: GPSTrackingConfigInput,
  ) -> None:
    """Configure GPS tracking for a specific dog.

    Args:
        dog_id: Dog identifier
        config: GPS configuration dictionary
    """
    try:
      gps_config = _build_tracking_config(config)  # noqa: E111

      self._dog_configs[dog_id] = gps_config  # noqa: E111

      # Initialize zone status tracking  # noqa: E114
      if dog_id not in self._zone_status:  # noqa: E111
        self._zone_status[dog_id] = {}

      # Initialize route history  # noqa: E114
      if dog_id not in self._route_history:  # noqa: E111
        self._route_history[dog_id] = []

      _LOGGER.info(  # noqa: E111
        "Configured GPS tracking for %s: auto_walk=%s, tracking=%s, alerts=%s",
        dog_id,
        gps_config.auto_start_walk,
        gps_config.track_route,
        gps_config.safety_alerts,
      )

    except Exception as err:
      _LOGGER.error("Failed to configure GPS for %s: %s", dog_id, err)  # noqa: E111
      raise  # noqa: E111

  async def async_setup_geofence_zone(  # noqa: E111
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
    if radius_meters <= 0:
      raise ValueError("Geofence radius must be greater than zero")  # noqa: E111

    if not (-90.0 <= center_lat <= 90.0):
      raise ValueError(  # noqa: E111
        "Geofence latitude must be between -90 and 90 degrees",
      )

    if not (-180.0 <= center_lon <= 180.0):
      raise ValueError(  # noqa: E111
        "Geofence longitude must be between -180 and 180 degrees",
      )

    try:
      zone = GeofenceZone(  # noqa: E111
        name=zone_name,
        center_lat=center_lat,
        center_lon=center_lon,
        radius_meters=radius_meters,
        zone_type=zone_type,
        enabled=True,
        notifications_enabled=notifications_enabled,
        breach_timeout_minutes=breach_timeout_minutes,
      )

      if dog_id not in self._geofence_zones:  # noqa: E111
        self._geofence_zones[dog_id] = []

      # Remove existing zone with same name  # noqa: E114
      self._geofence_zones[dog_id] = [  # noqa: E111
        z for z in self._geofence_zones[dog_id] if z.name != zone_name
      ]

      # Add new zone  # noqa: E114
      self._geofence_zones[dog_id].append(zone)  # noqa: E111

      # Initialize zone status  # noqa: E114
      if dog_id not in self._zone_status:  # noqa: E111
        self._zone_status[dog_id] = {}
      # Assume inside initially  # noqa: E114
      self._zone_status[dog_id][zone_name] = True  # noqa: E111

      _LOGGER.info(  # noqa: E111
        "Setup geofence zone for %s: %s at %.6f,%.6f radius=%dm",
        dog_id,
        zone_name,
        center_lat,
        center_lon,
        radius_meters,
      )

    except Exception as err:
      _LOGGER.error(  # noqa: E111
        "Failed to setup geofence zone for %s: %s",
        dog_id,
        err,
      )
      raise  # noqa: E111

  async def async_setup_safe_zone(  # noqa: E111
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

  async def async_start_gps_tracking(  # noqa: E111
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
      # End any existing active route  # noqa: E114
      if dog_id in self._active_routes:  # noqa: E111
        await self.async_end_gps_tracking(dog_id, save_route=True)

      # Create new route  # noqa: E114
      route = WalkRoute(  # noqa: E111
        dog_id=dog_id,
        start_time=dt_util.utcnow(),
      )

      self._active_routes[dog_id] = route  # noqa: E111

      # Start tracking task if configured  # noqa: E114
      config = self._dog_configs.get(dog_id)  # noqa: E111
      if config and config.enabled and track_route:  # noqa: E111
        await self._start_tracking_task(dog_id)

      session_id = f"{dog_id}_{uuid4().hex}"  # noqa: E111

      _LOGGER.info(  # noqa: E111
        "Started GPS tracking for %s: session=%s, route_tracking=%s, alerts=%s",
        dog_id,
        session_id,
        track_route,
        safety_alerts,
      )

      return session_id  # noqa: E111

    except Exception as err:
      _LOGGER.error(  # noqa: E111
        "Failed to start GPS tracking for %s: %s",
        dog_id,
        err,
      )
      raise  # noqa: E111

  async def async_end_gps_tracking(  # noqa: E111
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
      route = self._active_routes.get(dog_id)  # noqa: E111
      if not route:  # noqa: E111
        _LOGGER.warning("No active GPS tracking found for %s", dog_id)
        return None

      # Stop tracking task  # noqa: E114
      await self._stop_tracking_task(dog_id)  # noqa: E111

      # Finalize route  # noqa: E114
      route.end_time = dt_util.utcnow()  # noqa: E111

      if route.gps_points:  # noqa: E111
        # Calculate final statistics
        await self._calculate_route_statistics(route)

        # Save to history if requested
        if save_route:
          if dog_id not in self._route_history:  # noqa: E111
            self._route_history[dog_id] = []
          self._route_history[dog_id].append(route)  # noqa: E111

          # Limit history size (keep last 100 routes)  # noqa: E114
          self._enforce_route_history_limit(dog_id)  # noqa: E111

      # Ensure history never grows beyond the configured limit even when a  # noqa: E114
      # route is discarded (for example, when no GPS points were recorded).  # noqa: E114
      self._enforce_route_history_limit(dog_id)  # noqa: E111

      # Remove from active routes  # noqa: E114
      del self._active_routes[dog_id]  # noqa: E111

      # Update stats  # noqa: E114
      self._stats["routes_completed"] += 1  # noqa: E111
      self._stats["last_update"] = dt_util.utcnow()  # noqa: E111

      _LOGGER.info(  # noqa: E111
        "Ended GPS tracking for %s: %.2f km in %.1f minutes, %d points",
        dog_id,
        route.distance_km,
        route.duration_minutes,
        len(route.gps_points),
      )

      return route  # noqa: E111

    except Exception as err:
      _LOGGER.error("Failed to end GPS tracking for %s: %s", dog_id, err)  # noqa: E111
      raise  # noqa: E111

  async def async_add_gps_point(  # noqa: E111
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
    if not (-90.0 <= latitude <= 90.0):
      raise ValueError("Latitude must be between -90 and 90 degrees")  # noqa: E111

    if not (-180.0 <= longitude <= 180.0):
      raise ValueError("Longitude must be between -180 and 180 degrees")  # noqa: E111

    try:
      if timestamp is None:  # noqa: E111
        timestamp = dt_util.utcnow()

      # Create GPS point  # noqa: E114
      gps_point = GPSPoint(  # noqa: E111
        latitude=latitude,
        longitude=longitude,
        timestamp=timestamp,
        altitude=altitude,
        accuracy=accuracy,
        source=source,
      )

      # Check accuracy threshold  # noqa: E114
      config = self._dog_configs.get(dog_id)  # noqa: E111
      if config and accuracy and accuracy > config.accuracy_threshold:  # noqa: E111
        _LOGGER.debug(
          "GPS point for %s rejected: accuracy %.1fm > threshold %.1fm",
          dog_id,
          accuracy,
          config.accuracy_threshold,
        )
        return False

      # Update last known location  # noqa: E114
      self._last_locations[dog_id] = gps_point  # noqa: E111

      # Add to active route if tracking  # noqa: E114
      route = self._active_routes.get(dog_id)  # noqa: E111
      if route:  # noqa: E111
        # Check minimum distance filter
        if config and route.gps_points and config.min_distance_for_point > 0:
          last_point = route.gps_points[-1]  # noqa: E111
          distance = calculate_distance(  # noqa: E111
            last_point.latitude,
            last_point.longitude,
            latitude,
            longitude,
          )
          if distance < config.min_distance_for_point:  # noqa: E111
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
          await self._update_route_with_new_point(route, gps_point)  # noqa: E111

      # Check geofence zones  # noqa: E114
      await self._check_geofence_zones(dog_id, gps_point)  # noqa: E111

      # Update stats  # noqa: E114
      self._stats["gps_points_processed"] += 1  # noqa: E111
      self._stats["last_update"] = dt_util.utcnow()  # noqa: E111

      _LOGGER.debug(  # noqa: E111
        "Added GPS point for %s: %.6f,%.6f (accuracy: %.1fm)",
        dog_id,
        latitude,
        longitude,
        accuracy or 0,
      )

      return True  # noqa: E111

    except Exception as err:
      _LOGGER.error("Failed to add GPS point for %s: %s", dog_id, err)  # noqa: E111
      return False  # noqa: E111

  async def async_export_routes(  # noqa: E111
    self,
    dog_id: str,
    export_format: str = "gpx",
    last_n_routes: int = 1,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
  ) -> GPSRouteExportPayload | None:
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
      routes = self._route_history.get(dog_id, [])  # noqa: E111
      if not routes:  # noqa: E111
        _LOGGER.warning("No route history found for %s", dog_id)
        return None

      # Filter routes by date if specified  # noqa: E114
      if date_from or date_to:  # noqa: E111
        filtered_routes = []
        for route in routes:
          if date_from and route.start_time < date_from:  # noqa: E111
            continue
          if date_to and route.start_time > date_to:  # noqa: E111
            continue
          filtered_routes.append(route)  # noqa: E111
        routes = filtered_routes

      # Limit to last N routes  # noqa: E114
      if last_n_routes > 0:  # noqa: E111
        routes = routes[-last_n_routes:]

      if not routes:  # noqa: E111
        _LOGGER.warning(
          "No routes found matching criteria for %s",
          dog_id,
        )
        return None

      # Export based on format  # noqa: E114
      if export_format.lower() == "gpx":  # noqa: E111
        return await self._export_routes_gpx(dog_id, routes)
      if export_format.lower() == "json":  # noqa: E111
        return await self._export_routes_json(dog_id, routes)
      if export_format.lower() == "csv":  # noqa: E111
        return await self._export_routes_csv(dog_id, routes)
      raise ValueError(f"Unsupported export format: {export_format}")  # noqa: E111

    except Exception as err:
      _LOGGER.error("Failed to export routes for %s: %s", dog_id, err)  # noqa: E111
      raise  # noqa: E111

  async def async_get_current_location(self, dog_id: str) -> GPSPoint | None:  # noqa: E111
    """Get the current/last known location for a dog.

    Args:
        dog_id: Dog identifier

    Returns:
        Last known GPS point or None
    """
    return self._last_locations.get(dog_id)

  async def async_get_active_route(self, dog_id: str) -> WalkRoute | None:  # noqa: E111
    """Get currently active route for a dog.

    Args:
        dog_id: Dog identifier

    Returns:
        Active walk route or None
    """
    return self._active_routes.get(dog_id)

  async def async_get_geofence_status(self, dog_id: str) -> GPSGeofenceStatusSnapshot:  # noqa: E111
    """Get current geofence status for a dog.

    Args:
        dog_id: Dog identifier

    Returns:
        Geofence status information
    """
    zones = self._geofence_zones.get(dog_id, [])
    zone_state = self._zone_status.get(dog_id, {})
    current_location = self._last_locations.get(dog_id)

    zone_status_payload: dict[str, GPSGeofenceZoneStatusSnapshot] = {}
    status: GPSGeofenceStatusSnapshot = {
      "dog_id": dog_id,
      "zones_configured": len(zones),
      "current_location": None,
      "zone_status": zone_status_payload,
      "safe_zone_breaches": 0,
      "last_update": None,
    }

    if current_location:
      current_location_snapshot: GPSGeofenceLocationSnapshot = {  # noqa: E111
        "latitude": current_location.latitude,
        "longitude": current_location.longitude,
        "timestamp": current_location.timestamp.isoformat(),
        "accuracy": current_location.accuracy,
      }
      status["current_location"] = current_location_snapshot  # noqa: E111
      status["last_update"] = current_location.timestamp.isoformat()  # noqa: E111

    for zone in zones:
      is_inside = zone_state.get(zone.name, True)  # noqa: E111
      distance_to_center = 0.0  # noqa: E111

      if current_location:  # noqa: E111
        distance_to_center = zone.distance_to_center(
          current_location.latitude,
          current_location.longitude,
        )

      zone_snapshot: GPSGeofenceZoneStatusSnapshot = {  # noqa: E111
        "inside": is_inside,
        "zone_type": zone.zone_type,
        "radius_meters": zone.radius_meters,
        "distance_to_center": distance_to_center,
        "notifications_enabled": zone.notifications_enabled,
      }
      zone_status_payload[zone.name] = zone_snapshot  # noqa: E111

      if zone.zone_type == "safe_zone" and not is_inside:  # noqa: E111
        status["safe_zone_breaches"] += 1

    return status

  async def async_get_statistics(self) -> GPSManagerStatisticsSnapshot:  # noqa: E111
    """Get GPS and geofencing statistics.

    Returns:
        Statistics dictionary
    """
    total_routes = sum(len(routes) for routes in self._route_history.values())
    active_tracking = len(self._active_routes)

    snapshot: GPSManagerStatisticsSnapshot = {
      "gps_points_processed": int(self._stats["gps_points_processed"]),
      "routes_completed": int(self._stats["routes_completed"]),
      "geofence_events": int(self._stats["geofence_events"]),
      "last_update": self._stats["last_update"],
      "dogs_configured": len(self._dog_configs),
      "active_tracking_sessions": active_tracking,
      "total_routes_stored": total_routes,
      "geofence_zones_configured": sum(
        len(zones) for zones in self._geofence_zones.values()
      ),
    }
    return snapshot

  def _enforce_route_history_limit(self, dog_id: str) -> None:  # noqa: E111
    """Clamp the stored route history to the most recent 100 entries."""

    history = self._route_history.get(dog_id)
    if not history:
      return  # noqa: E111

    if len(history) > 100:
      self._route_history[dog_id] = history[-100:]  # noqa: E111

  async def _start_tracking_task(self, dog_id: str) -> None:  # noqa: E111
    """Start background tracking task for a dog."""
    await self._stop_tracking_task(dog_id)  # Stop any existing task

    config = self._dog_configs.get(dog_id)
    if not config or not config.enabled:
      return  # noqa: E111

    async def _tracking_loop() -> None:
      """Background task for GPS tracking."""  # noqa: E111
      try:  # noqa: E111
        while dog_id in self._active_routes:
          # Try to get location from device tracker  # noqa: E114
          try:  # noqa: E111
            await asyncio.wait_for(
              self._update_location_from_device_tracker(dog_id),
              timeout=min(
                _TRACKING_UPDATE_TIMEOUT,
                max(5.0, float(config.update_interval)),
              ),
            )
          except TimeoutError:  # noqa: E111
            _LOGGER.warning(
              "GPS tracking update timed out for %s",
              dog_id,
            )

          # Wait for next update  # noqa: E114
          await asyncio.sleep(config.update_interval)  # noqa: E111

      except asyncio.CancelledError:  # noqa: E111
        _LOGGER.debug("GPS tracking task cancelled for %s", dog_id)
      except Exception as err:  # noqa: E111
        _LOGGER.error(
          "GPS tracking task error for %s: %s",
          dog_id,
          err,
        )

    async def _resolve_task(candidate: Any) -> asyncio.Task[Any] | None:
      """Coerce scheduler return values into asyncio tasks."""  # noqa: E111

      current: Any = candidate  # noqa: E111
      while True:  # noqa: E111
        if isinstance(current, asyncio.Task):
          return current  # noqa: E111
        if isinstance(current, asyncio.Future):
          return cast(asyncio.Task[Any], current)  # noqa: E111
        if inspect.isawaitable(current):
          try:  # noqa: E111
            current = await current
          except Exception as err:  # pragma: no cover - defensive guard  # noqa: E111
            _LOGGER.debug(
              "Awaiting scheduled task wrapper failed for %s: %s",
              dog_id,
              err,
            )
            return None
          continue  # noqa: E111
        return None

    def _loop_factory() -> Coroutine[Any, Any, None]:
      return _tracking_loop()  # noqa: E111

    task_name = f"pawcontrol_gps_tracking_{dog_id}"
    task_handle: asyncio.Task[Any] | None = None

    hass_create_task = getattr(self.hass, "async_create_task", None)
    hass_coroutine: Coroutine[Any, Any, None] | None = None
    if callable(hass_create_task):
      hass_coroutine = _loop_factory()  # noqa: E111
      try:  # noqa: E111
        scheduled = hass_create_task(hass_coroutine, name=task_name)
      except TypeError:  # noqa: E111
        scheduled = hass_create_task(hass_coroutine)
      except Exception as err:  # pragma: no cover - defensive guard  # noqa: E111
        _LOGGER.debug(
          "Home Assistant task scheduling failed for %s: %s",
          dog_id,
          err,
        )
        scheduled = None
      else:  # noqa: E111
        task_handle = await _resolve_task(scheduled)

      if task_handle is None and hass_coroutine is not None:  # noqa: E111
        hass_coroutine.close()
        hass_coroutine = None

    if task_handle is None:
      loop = getattr(self.hass, "loop", None)  # noqa: E111
      if loop is not None:  # noqa: E111
        try:
          task_handle = loop.create_task(  # noqa: E111
            _loop_factory(),
            name=task_name,
          )
        except TypeError:
          task_handle = loop.create_task(_loop_factory())  # noqa: E111
      else:  # noqa: E111
        try:
          task_handle = asyncio.create_task(  # noqa: E111
            _loop_factory(),
            name=task_name,
          )
        except TypeError:  # pragma: no cover - <3.8 compatibility guard
          task_handle = asyncio.create_task(_loop_factory())  # noqa: E111

    if task_handle is None:
      raise RuntimeError(  # noqa: E111
        f"Failed to schedule GPS tracking task for {dog_id}",
      )

    self._tracking_tasks[dog_id] = task_handle

    _LOGGER.debug("Started GPS tracking task for %s", dog_id)

  async def _stop_tracking_task(self, dog_id: str) -> None:  # noqa: E111
    """Stop background tracking task for a dog."""
    task = self._tracking_tasks.pop(dog_id, None)
    if task is None:
      return  # noqa: E111

    if not task.done():
      task.cancel()  # noqa: E111
      try:  # noqa: E111
        await asyncio.wait_for(task, timeout=_TASK_CANCEL_TIMEOUT)
      except TimeoutError:  # noqa: E111
        _LOGGER.warning(
          "Timeout while stopping GPS tracking task for %s",
          dog_id,
        )
      except asyncio.CancelledError:  # noqa: E111
        _LOGGER.debug("GPS tracking task cancelled for %s", dog_id)

    _LOGGER.debug("Stopped GPS tracking task for %s", dog_id)

  async def _update_location_from_device_tracker(self, dog_id: str) -> None:  # noqa: E111
    """Try to update location from associated device tracker with retry."""

    async def _fetch_device_tracker_location() -> None:
      """Internal function to fetch location - wrapped by retry logic."""  # noqa: E111
      # Try to find device tracker entity for this dog  # noqa: E114
      entity_registry = er.async_get(self.hass)  # noqa: E111
      dr.async_get(self.hass)  # noqa: E111

      # Look for device tracker entities that might belong to this dog  # noqa: E114
      for entity in entity_registry.entities.values():  # noqa: E111
        if (
          entity.platform == "device_tracker"
          and dog_id.lower() in (entity.name or "").lower()
        ):
          state = self.hass.states.get(entity.entity_id)  # noqa: E111
          if state and state.state not in ["unavailable", "unknown"]:  # noqa: E111
            # Extract GPS coordinates
            lat = state.attributes.get("latitude")
            lon = state.attributes.get("longitude")
            accuracy = state.attributes.get("gps_accuracy")

            if lat is not None and lon is not None:
              await self.async_add_gps_point(  # noqa: E111
                dog_id=dog_id,
                latitude=lat,
                longitude=lon,
                accuracy=accuracy,
                source=LocationSource.DEVICE_TRACKER,
              )
              return  # noqa: E111

      # Could also check for companion app entities, etc.  # noqa: E114

    # RESILIENCE: Wrap in retry logic for transient failures
    try:
      await self.resilience_manager.execute_with_resilience(  # noqa: E111
        _fetch_device_tracker_location,
        retry_config=self._gps_retry_config,
      )
    except Exception as err:
      _LOGGER.debug(  # noqa: E111
        "Failed to update location from device tracker for %s after retries: %s",
        dog_id,
        err,
      )

  async def _check_geofence_zones(self, dog_id: str, gps_point: GPSPoint) -> None:  # noqa: E111
    """Check GPS point against all geofence zones for a dog."""
    zones = self._geofence_zones.get(dog_id, [])
    if not zones:
      return  # noqa: E111

    zone_status = self._zone_status.get(dog_id, {})

    for zone in zones:
      if not zone.enabled:  # noqa: E111
        continue

      is_inside = zone.contains_point(  # noqa: E111
        gps_point.latitude,
        gps_point.longitude,
      )
      was_inside = zone_status.get(zone.name, True)  # noqa: E111

      # Check for zone transitions  # noqa: E114
      if is_inside != was_inside:  # noqa: E111
        event_type = (
          GeofenceEventType.ENTERED if is_inside else GeofenceEventType.EXITED
        )

        distance_from_center = zone.distance_to_center(
          gps_point.latitude,
          gps_point.longitude,
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
          route.geofence_events.append(event)  # noqa: E111

        # Send notification if enabled
        if zone.notifications_enabled:
          await self._send_geofence_notification(event)  # noqa: E111

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

  async def _send_geofence_notification(self, event: GeofenceEvent) -> None:  # noqa: E111
    """Send notification for geofence event."""
    try:
      event_payload: GeofenceEventPayload = {  # noqa: E111
        "dog_id": event.dog_id,
        "zone": event.zone.name,
        "zone_type": event.zone.zone_type,
        "event": event.event_type.value,
        "distance_meters": float(round(event.distance_from_center, 2)),
        "timestamp": event.timestamp.isoformat(),
        "latitude": event.location.latitude,
        "longitude": event.location.longitude,
      }
      if event.duration_outside:  # noqa: E111
        event_payload["duration_seconds"] = int(
          event.duration_outside.total_seconds(),
        )

      hass_event = {  # noqa: E111
        GeofenceEventType.ENTERED: EVENT_GEOFENCE_ENTERED,
        GeofenceEventType.EXITED: EVENT_GEOFENCE_LEFT,
        GeofenceEventType.BREACH: EVENT_GEOFENCE_BREACH,
        GeofenceEventType.RETURN: EVENT_GEOFENCE_RETURN,
      }[event.event_type]
      await async_fire_event(  # noqa: E111
        self.hass,
        hass_event,
        cast(JSONMapping, event_payload),
      )

      title = f"Geofence alert • {event.dog_id}"  # noqa: E111
      zone_name = event.zone.name  # noqa: E111
      distance: float = event_payload["distance_meters"]  # noqa: E111

      if event.event_type == GeofenceEventType.ENTERED:  # noqa: E111
        message = f"{event.dog_id} entered {zone_name}."
        priority = NotificationPriority.NORMAL
      elif event.event_type == GeofenceEventType.RETURN:  # noqa: E111
        message = f"{event.dog_id} returned to {zone_name}."
        priority = NotificationPriority.NORMAL
      elif event.event_type == GeofenceEventType.EXITED:  # noqa: E111
        message = f"{event.dog_id} left {zone_name} and is {distance:.0f} m away."
        priority = (
          NotificationPriority.HIGH
          if event.zone.zone_type == "safe_zone"
          else NotificationPriority.NORMAL
        )
      else:  # noqa: E111
        duration = event_payload.get("duration_seconds")
        minutes = duration / 60 if isinstance(duration, int) else 0.0
        message = (
          f"{event.dog_id} has been outside {zone_name} for {minutes:.1f} minutes"
        )
        priority = NotificationPriority.URGENT

      coordinates: GeofenceNotificationCoordinates = {  # noqa: E111
        "latitude": event.location.latitude,
        "longitude": event.location.longitude,
      }
      notification_data: GeofenceNotificationData = {  # noqa: E111
        "zone": zone_name,
        "zone_type": event.zone.zone_type,
        "event": event.event_type.value,
        "distance_meters": distance,
        "coordinates": coordinates,
      }
      if event.duration_outside:  # noqa: E111
        notification_data["duration_seconds"] = event_payload["duration_seconds"]

      _LOGGER.info("Geofence notification: %s - %s", title, message)  # noqa: E111

      if self._notification_manager:  # noqa: E111
        await self._notification_manager.async_send_notification(
          NotificationType.GEOFENCE_ALERT,
          title,
          message,
          dog_id=event.dog_id,
          priority=priority,
          data=cast(
            NotificationTemplateData,
            dict(notification_data),
          ),
        )

    except Exception as err:
      _LOGGER.error("Failed to send geofence notification: %s", err)  # noqa: E111

  async def _calculate_route_statistics(self, route: WalkRoute) -> None:  # noqa: E111
    """Calculate comprehensive statistics for a completed route."""
    if not route.gps_points:
      return  # noqa: E111

    total_distance = 0.0
    total_time = 0.0
    speeds = []

    # Calculate segments and statistics
    route.segments = []

    for i in range(1, len(route.gps_points)):
      prev_point = route.gps_points[i - 1]  # noqa: E111
      curr_point = route.gps_points[i]  # noqa: E111

      # Calculate distance  # noqa: E114
      distance = calculate_distance(  # noqa: E111
        prev_point.latitude,
        prev_point.longitude,
        curr_point.latitude,
        curr_point.longitude,
      )

      # Calculate time  # noqa: E114
      time_diff = (curr_point.timestamp - prev_point.timestamp).total_seconds()  # noqa: E111

      # Skip invalid segments  # noqa: E114
      if time_diff <= 0 or distance > 1000:  # Skip if >1km between points  # noqa: E111
        continue

      # Calculate speed  # noqa: E114
      speed_mps = distance / time_diff if time_diff > 0 else 0  # noqa: E111

      # Create segment  # noqa: E114
      segment = RouteSegment(  # noqa: E111
        start_point=prev_point,
        end_point=curr_point,
        distance_meters=distance,
        duration_seconds=time_diff,
        avg_speed_mps=speed_mps,
      )

      route.segments.append(segment)  # noqa: E111

      total_distance += distance  # noqa: E111
      total_time += time_diff  # noqa: E111
      speeds.append(speed_mps)  # noqa: E111

    # Update route totals
    route.total_distance_meters = total_distance
    route.total_duration_seconds = total_time

    if speeds:
      route.avg_speed_mps = sum(speeds) / len(speeds)  # noqa: E111
      route.max_speed_mps = max(speeds)  # noqa: E111

    # Assess route quality based on GPS accuracy
    accurate_points = sum(1 for p in route.gps_points if p.is_accurate)
    accuracy_ratio = accurate_points / len(route.gps_points)

    if accuracy_ratio >= 0.9:
      route.route_quality = GPSAccuracy.EXCELLENT  # noqa: E111
    elif accuracy_ratio >= 0.7:
      route.route_quality = GPSAccuracy.GOOD  # noqa: E111
    elif accuracy_ratio >= 0.5:
      route.route_quality = GPSAccuracy.FAIR  # noqa: E111
    else:
      route.route_quality = GPSAccuracy.POOR  # noqa: E111

  async def _update_route_with_new_point(  # noqa: E111
    self,
    route: WalkRoute,
    new_point: GPSPoint,
  ) -> None:
    """Update route statistics with a new GPS point."""
    if len(route.gps_points) < 2:
      return  # noqa: E111

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

  async def _export_routes_gpx(  # noqa: E111
    self,
    dog_id: str,
    routes: list[WalkRoute],
  ) -> GPSRouteExportGPXPayload:
    """Export routes in GPX format."""
    gpx_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    gpx_content += '<gpx version="1.1" creator="PawControl">\n'

    for route in routes:
      gpx_content += "  <trk>\n"  # noqa: E111
      gpx_content += (  # noqa: E111
        f"    <name>Walk {route.start_time.strftime('%Y-%m-%d %H:%M')}</name>\n"
      )
      gpx_content += "    <trkseg>\n"  # noqa: E111

      for point in route.gps_points:  # noqa: E111
        gpx_content += f'      <trkpt lat="{point.latitude}" lon="{point.longitude}">\n'
        if point.altitude is not None:
          gpx_content += f"        <ele>{point.altitude}</ele>\n"  # noqa: E111
        gpx_content += f"        <time>{point.timestamp.isoformat()}Z</time>\n"
        gpx_content += "      </trkpt>\n"

      gpx_content += "    </trkseg>\n"  # noqa: E111
      gpx_content += "  </trk>\n"  # noqa: E111

    gpx_content += "</gpx>\n"

    payload: GPSRouteExportGPXPayload = {
      "format": "gpx",
      "content": gpx_content,
      "filename": f"{dog_id}_routes_{dt_util.utcnow().strftime('%Y%m%d')}.gpx",
      "routes_count": len(routes),
    }
    return payload

  async def _export_routes_json(  # noqa: E111
    self,
    dog_id: str,
    routes: list[WalkRoute],
  ) -> GPSRouteExportJSONPayload:
    """Export routes in JSON format."""
    export_data: GPSRouteExportJSONContent = {
      "dog_id": dog_id,
      "export_timestamp": dt_util.utcnow().isoformat(),
      "routes": [],
    }

    for route in routes:
      route_data: GPSRouteExportJSONRoute = {  # noqa: E111
        "start_time": route.start_time.isoformat(),
        "end_time": route.end_time.isoformat() if route.end_time else None,
        "duration_minutes": route.duration_minutes,
        "distance_km": route.distance_km,
        "avg_speed_kmh": route.avg_speed_kmh,
        "route_quality": route.route_quality.value,
        "gps_points": [],
        "geofence_events": [],
      }

      for point in route.gps_points:  # noqa: E111
        point_payload: GPSRouteExportJSONPoint = {
          "latitude": point.latitude,
          "longitude": point.longitude,
          "timestamp": point.timestamp.isoformat(),
          "altitude": point.altitude,
          "accuracy": point.accuracy,
          "source": point.source.value,
        }
        route_data["gps_points"].append(point_payload)

      for event in route.geofence_events:  # noqa: E111
        event_payload: GPSRouteExportJSONEvent = {
          "event_type": event.event_type.value,
          "zone_name": event.zone.name,
          "timestamp": event.timestamp.isoformat(),
          "distance_from_center": event.distance_from_center,
          "severity": event.severity,
        }
        route_data["geofence_events"].append(event_payload)

      export_data["routes"].append(route_data)  # noqa: E111

    normalised_content = cast(
      GPSRouteExportJSONContent,
      normalize_value(export_data),
    )
    payload: GPSRouteExportJSONPayload = {
      "format": "json",
      "content": normalised_content,
      "filename": f"{dog_id}_routes_{dt_util.utcnow().strftime('%Y%m%d')}.json",
      "routes_count": len(routes),
    }
    return payload

  async def _export_routes_csv(  # noqa: E111
    self,
    dog_id: str,
    routes: list[WalkRoute],
  ) -> GPSRouteExportCSVPayload:
    """Export routes in CSV format."""
    csv_lines = [
      "timestamp,latitude,longitude,altitude,accuracy,route_id,distance_km,duration_min",
    ]

    for index, route in enumerate(routes, start=1):
      route_id = f"route_{index}"  # noqa: E111

      csv_lines.extend(  # noqa: E111
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
          ],
        )
        for point in route.gps_points
      )

    csv_content = "\n".join(csv_lines)

    payload: GPSRouteExportCSVPayload = {
      "format": "csv",
      "content": csv_content,
      "filename": f"{dog_id}_routes_{dt_util.utcnow().strftime('%Y%m%d')}.csv",
      "routes_count": len(routes),
    }
    return payload

  async def async_cleanup(self) -> None:  # noqa: E111
    """Cleanup GPS manager resources."""
    # Stop all tracking tasks
    for dog_id in list(self._tracking_tasks.keys()):
      await self._stop_tracking_task(dog_id)  # noqa: E111

    # Clear all data
    self._dog_configs.clear()
    self._active_routes.clear()
    self._geofence_zones.clear()
    self._zone_status.clear()
    self._last_locations.clear()
    self._route_history.clear()

    _LOGGER.debug("GPS and geofencing manager cleaned up")
