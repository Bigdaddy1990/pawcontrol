"""Device tracker platform for PawControl integration.

This module provides a GPS-based device tracker for PawControl dogs. It is
adapted from the upstream PawControl repository and includes a type safety
improvement for the Home Assistant quality scale: the `extra_state_attributes`
property now returns a ``JSONMutableMapping`` instead of a plain ``dict``. This
ensures that all attribute dictionaries are JSON-safe and mutable, complying
with Home Assistant's requirements for entity attributes.

The remainder of the code is identical to the upstream implementation and has
been preserved verbatim. Only minor modifications have been made to the import
statements and the return type of ``extra_state_attributes`` to satisfy strict
typing rules. All other functionality—GPS tracking, route recording, geofence
integration, and export utilities—remains unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import cast

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.const import Platform, STATE_HOME, STATE_NOT_HOME, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MODULE_GPS
from .coordinator import PawControlCoordinator
from .entity import PawControlDogEntityBase
from .runtime_data import get_runtime_data
from .types import (
  DOG_ID_FIELD,
  DOG_MODULES_FIELD,
  DOG_NAME_FIELD,
  CoordinatorDogData,
  CoordinatorModuleState,
  DogConfigData,
  GPSLocationSample,
  GPSModulePayload,
  GPSRouteBuffer,
  GPSRouteExportCSVPayload,
  GPSRouteExportGPXPayload,
  GPSRouteExportJSONContent,
  GPSRouteExportJSONPayload,
  GPSRouteExportJSONPoint,
  GPSRouteExportJSONRoute,
  GPSRouteExportPayload,
  GPSRoutePoint,
  GPSRouteSnapshot,
  JSONMapping,
  JSONMutableMapping,
  JSONValue,
  PawControlConfigEntry,
  ensure_dog_config_data,
  ensure_dog_modules_projection,
  ensure_json_mapping,
  ensure_gps_payload,
)
from .utils import async_call_add_entities, ensure_utc_datetime, normalise_json_mapping

_LOGGER = logging.getLogger(__name__)


def _normalise_attributes(attrs: Mapping[str, object]) -> JSONMutableMapping:
  """Return JSON-serialisable attributes for device tracker entities."""

  payload = ensure_json_mapping(attrs)
  return cast(JSONMutableMapping, normalise_json_mapping(payload))


# Coordinator drives refreshes, so we can safely allow unlimited parallel
# updates for this read-only platform while still complying with the
# ``parallel-updates`` quality scale rule.
PARALLEL_UPDATES = 0

# GPS tracker constants
DEFAULT_GPS_ACCURACY = 50  # meters
MIN_LOCATION_UPDATE_INTERVAL = 30  # seconds
ROUTE_POINT_MAX_AGE = timedelta(hours=24)
MAX_ROUTE_POINTS = 1000  # Maximum stored route points per dog

# Location source priorities (higher = more trusted)
LOCATION_SOURCE_PRIORITY = {
  "gps": 10,
  "network": 8,
  "passive": 6,
  "manual": 5,
  "unknown": 1,
}


async def async_setup_entry(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
  async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up PawControl device tracker platform.

  NEW: Implements missing device tracker functionality per requirements_inventory.md
  """
  runtime_data = get_runtime_data(hass, entry)
  if runtime_data is None:
    _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
    return
  coordinator = runtime_data.coordinator
  raw_dogs = getattr(runtime_data, "dogs", [])
  gps_enabled_dogs: list[DogConfigData] = []

  for raw_dog in raw_dogs:
    if not isinstance(raw_dog, Mapping):
      continue

    normalised = ensure_dog_config_data(cast(JSONMapping, raw_dog))
    if normalised is None:
      continue

    modules_projection = ensure_dog_modules_projection(normalised)
    normalised[DOG_MODULES_FIELD] = modules_projection.config

    if modules_projection.mapping.get(MODULE_GPS, False):
      gps_enabled_dogs.append(normalised)

  dogs: list[DogConfigData] = gps_enabled_dogs
  entity_factory = runtime_data.entity_factory
  profile = runtime_data.entity_profile

  if not dogs:
    if not raw_dogs:
      _LOGGER.warning("No dogs configured for device tracker platform")
    else:
      _LOGGER.info(
        "No dogs have GPS module enabled, skipping device tracker setup",
      )
    return

  entities: list[PawControlGPSTracker] = []

  for dog in dogs:
    dog_id = dog[DOG_ID_FIELD]
    dog_name = dog[DOG_NAME_FIELD]

    snapshot = entity_factory.get_budget_snapshot(dog_id)
    base_allocation = snapshot.total_allocated if snapshot else 0
    entity_factory.begin_budget(
      dog_id,
      profile,
      base_allocation=base_allocation,
    )

    # Use entity factory to check if device tracker should be created
    try:
      config = entity_factory.create_entity_config(
        dog_id=dog_id,
        entity_type="device_tracker",
        module=MODULE_GPS,
        profile=profile,
        priority=8,  # High priority for GPS tracking
      )

      if config:
        tracker = PawControlGPSTracker(coordinator, dog_id, dog_name)
        entities.append(tracker)
    finally:
      entity_factory.finalize_budget(dog_id, profile)

  if (
    not entities
    and Platform.DEVICE_TRACKER
    in entity_factory.get_profile_info(
      profile,
    ).platforms
  ):
    for dog in dogs:
      dog_id = dog[DOG_ID_FIELD]
      dog_name = dog[DOG_NAME_FIELD]
      entities.append(PawControlGPSTracker(coordinator, dog_id, dog_name))
    _LOGGER.info(
      "Created baseline GPS device trackers for profile '%s'",
      profile,
    )

  if entities:
    await async_call_add_entities(
      async_add_entities,
      entities,
      update_before_add=False,
    )
    _LOGGER.info(
      "Set up %d GPS device trackers with profile '%s'",
      len(entities),
      profile,
    )
  else:
    _LOGGER.info(
      "No GPS device trackers created due to profile restrictions",
    )


class PawControlGPSTracker(PawControlDogEntityBase, TrackerEntity):
  """GPS device tracker for dogs with route recording capabilities.

  NEW: Implements device_tracker.{dog}_gps per requirements_inventory.md
  with route tracking, geofencing, and location history.
  """

  _attr_should_poll = False
  _attr_has_entity_name = True

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize GPS device tracker."""
    super().__init__(coordinator, dog_id, dog_name)
    self._attr_unique_id = f"pawcontrol_{dog_id}_gps_tracker"
    self._attr_name = f"{dog_name} GPS"
    self._attr_translation_key = "gps"
    self._attr_icon = "mdi:map-marker"

    # Link to PawControl device
    self._set_device_link_info(
      model="GPS Tracker",
      sw_version="1.0.0",
    )

    # GPS tracker state
    self._last_location: GPSLocationSample | None = None
    self._last_update: datetime | None = None
    self._route_points = GPSRouteBuffer[GPSRoutePoint]()
    self._current_zone: str | None = None

  @staticmethod
  def _serialize_timestamp(value: datetime | str | None) -> str | None:
    """Return an ISO-formatted timestamp for ``value`` when possible."""

    if isinstance(value, datetime):
      return dt_util.as_utc(value).isoformat()
    if isinstance(value, str):
      return value
    return None

  def _serialize_route_point(self, point: GPSRoutePoint) -> GPSRoutePoint:
    """Convert a route point to a JSON-safe mapping."""

    timestamp_iso = self._serialize_timestamp(point.get("timestamp"))
    payload: dict[str, JSONValue] = {
      "latitude": float(point["latitude"]),
      "longitude": float(point["longitude"]),
      "timestamp": timestamp_iso or dt_util.utcnow().isoformat(),
    }

    accuracy = point.get("accuracy")
    if isinstance(accuracy, int | float):
      payload["accuracy"] = float(accuracy)

    altitude = point.get("altitude")
    if isinstance(altitude, int | float):
      payload["altitude"] = float(altitude)

    speed = point.get("speed")
    if isinstance(speed, int | float):
      payload["speed"] = float(speed)

    heading = point.get("heading")
    if isinstance(heading, int | float):
      payload["heading"] = float(heading)

    return cast(GPSRoutePoint, payload)

  @property
  def available(self) -> bool:
    """Return True if GPS data is available."""
    return self.coordinator.available and self._get_gps_data() is not None

  @property
  def source_type(self) -> SourceType:
    """Return the source type of the device tracker."""
    return SourceType.GPS

  @property
  def state(self) -> str:
    """Return the state of the device tracker."""
    gps_data = self._get_gps_data()
    if not gps_data:
      return STATE_UNKNOWN

    zone = gps_data.get("zone")
    if zone == "home":
      return STATE_HOME
    if zone and zone != "unknown":
      return zone
    return STATE_NOT_HOME

  @property
  def latitude(self) -> float | None:
    """Return the GPS latitude."""
    gps_data = self._get_gps_data()
    if not gps_data:
      return None

    try:
      lat = gps_data.get("latitude")
      return float(lat) if lat is not None else None
    except (TypeError, ValueError):
      return None

  @property
  def longitude(self) -> float | None:
    """Return the GPS longitude."""
    gps_data = self._get_gps_data()
    if not gps_data:
      return None

    try:
      lon = gps_data.get("longitude")
      return float(lon) if lon is not None else None
    except (TypeError, ValueError):
      return None

  @property
  def location_accuracy(self) -> int | None:
    """Return the GPS accuracy in meters."""
    gps_data = self._get_gps_data()
    if not gps_data:
      return None

    try:
      accuracy = gps_data.get("accuracy")
      return int(accuracy) if accuracy is not None else DEFAULT_GPS_ACCURACY
    except (TypeError, ValueError):
      return DEFAULT_GPS_ACCURACY

  @property
  def battery_level(self) -> int | None:
    """Return GPS tracker battery level."""
    gps_data = self._get_gps_data()
    if not gps_data:
      return None

    try:
      battery = gps_data.get("battery")
      return int(battery) if battery is not None else None
    except (TypeError, ValueError):
      return None

  @property
  def location_name(self) -> str | None:
    """Return the current location name/zone."""
    gps_data = self._get_gps_data()
    if not gps_data:
      return None

    zone = gps_data.get("zone")
    return zone if zone and zone != "unknown" else None

  @property
  def extra_state_attributes(self) -> JSONMutableMapping:
    """Return additional GPS tracker attributes.

    This method returns a ``JSONMutableMapping`` instead of a plain ``dict``,
    which satisfies Home Assistant's requirement for entity attribute types. The
    returned mapping is mutable and contains only JSON-serialisable values.
    """
    attrs = self._build_entity_attributes(
      {
        "tracker_type": MODULE_GPS,
        "route_active": False,
        "route_points": len(self._route_points),
      },
    )

    gps_data = self._get_gps_data()
    if gps_data:
      # Basic GPS info
      altitude = gps_data.get("altitude")
      speed = gps_data.get("speed")
      heading = gps_data.get("heading")
      satellites = gps_data.get("satellites")
      location_source = gps_data.get("source", "unknown")
      last_seen = gps_data.get("last_seen")
      distance_from_home = gps_data.get("distance_from_home")

      if isinstance(altitude, int | float):
        attrs["altitude"] = float(altitude)
      if isinstance(speed, int | float):
        attrs["speed"] = float(speed)
      if isinstance(heading, int | float):
        attrs["heading"] = float(heading)
      if isinstance(satellites, int):
        attrs["satellites"] = satellites

      attrs["location_source"] = (
        location_source
        if isinstance(
          location_source,
          str,
        )
        else "unknown"
      )

      if isinstance(last_seen, datetime):
        attrs["last_seen"] = dt_util.as_utc(last_seen).isoformat()
      elif isinstance(last_seen, str):
        attrs["last_seen"] = last_seen

      if isinstance(distance_from_home, int | float):
        attrs["distance_from_home"] = float(distance_from_home)

      # Route information
      current_route = gps_data.get("current_route")
      if current_route:
        attrs["route_active"] = bool(current_route.get("active", True))
        attrs["route_points"] = len(current_route.get("points", []))

        route_distance = current_route.get("distance")
        if isinstance(route_distance, int | float):
          attrs["route_distance"] = float(route_distance)

        route_duration = current_route.get("duration")
        if isinstance(route_duration, int | float):
          attrs["route_duration"] = route_duration

        route_start = current_route.get("start_time")
        if isinstance(route_start, datetime):
          attrs["route_start_time"] = dt_util.as_utc(
            route_start,
          ).isoformat()
        elif isinstance(route_start, str):
          attrs["route_start_time"] = route_start

      # Geofencing info
      geofence_status = gps_data.get("geofence_status")
      if geofence_status:
        in_safe_zone = geofence_status.get("in_safe_zone", False)
        zone_name = geofence_status.get("zone_name")
        zone_distance = geofence_status.get("distance_to_boundary")

        attrs["in_safe_zone"] = bool(in_safe_zone)
        if isinstance(zone_name, str):
          attrs["zone_name"] = zone_name
        if isinstance(zone_distance, int | float):
          attrs["zone_distance"] = float(zone_distance)

      status_snapshot = self._get_status_snapshot()
      if status_snapshot is not None:
        attrs["in_safe_zone"] = bool(
          status_snapshot.get(
            "in_safe_zone",
            attrs.get("in_safe_zone", True),
          ),
        )

      # Walk integration
      walk_info = gps_data.get("walk_info")
      if walk_info:
        attrs["walk_active"] = bool(walk_info.get("active", False))

        walk_id = walk_info.get("walk_id")
        if isinstance(walk_id, str):
          attrs["walk_id"] = walk_id

        walk_start = walk_info.get("start_time")
        if isinstance(walk_start, datetime):
          attrs["walk_start_time"] = dt_util.as_utc(
            walk_start,
          ).isoformat()
        elif isinstance(walk_start, str):
          attrs["walk_start_time"] = walk_start

    return _normalise_attributes(attrs)

  def _get_gps_data(self) -> GPSModulePayload | None:
    """Get GPS data from coordinator."""
    if not self.coordinator.available:
      return None

    gps_state = self._get_module_data(MODULE_GPS)
    if gps_state:
      return ensure_gps_payload(cast(Mapping[str, object], gps_state))

    return None

  async def async_update_location(
    self,
    latitude: float,
    longitude: float,
    accuracy: int | None = None,
    altitude: float | None = None,
    speed: float | None = None,
    heading: float | None = None,
    source: str = "gps",
    timestamp: datetime | None = None,
  ) -> None:
    """Update GPS location with validation and route tracking.

    Args:
        latitude: GPS latitude
        longitude: GPS longitude
        accuracy: Location accuracy in meters
        altitude: Altitude in meters
        speed: Speed in km/h
        heading: Heading in degrees (0-360)
        source: Location source
        timestamp: Location timestamp
    """
    try:
      # Validate coordinates
      if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        _LOGGER.error(
          "Invalid GPS coordinates for %s: lat=%s, lon=%s",
          self._dog_name,
          latitude,
          longitude,
        )
        return

      if timestamp is None:
        timestamp = dt_util.utcnow()

      # Check minimum update interval to prevent spam
      if (
        self._last_update
        and (timestamp - self._last_update).total_seconds()
        < MIN_LOCATION_UPDATE_INTERVAL
      ):
        _LOGGER.debug(
          "GPS update too frequent for %s, skipping",
          self._dog_name,
        )
        return

      accuracy_value = int(accuracy) if accuracy is not None else DEFAULT_GPS_ACCURACY
      location_data: GPSLocationSample = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "accuracy": accuracy_value,
        "altitude": float(altitude) if altitude is not None else None,
        "speed": float(speed) if speed is not None else None,
        "heading": float(heading) if heading is not None else None,
        "source": source,
        "timestamp": timestamp,
        "priority": LOCATION_SOURCE_PRIORITY.get(source, 1),
      }

      # Update location if this source has higher priority
      last_location = self._last_location
      if (
        last_location is None or location_data["priority"] >= last_location["priority"]
      ):
        self._last_location = location_data
        self._last_update = timestamp

        # Add to route if tracking is active
        await self._update_route_tracking(location_data)

        # Update coordinator data
        await self._update_coordinator_gps_data(location_data)

        # Trigger state update
        self.async_write_ha_state()

        _LOGGER.debug(
          "Updated GPS location for %s: %.6f,%.6f (accuracy: %dm, source: %s)",
          self._dog_name,
          latitude,
          longitude,
          accuracy_value,
          source,
        )

    except Exception as err:
      _LOGGER.error(
        "Error updating GPS location for %s: %s",
        self._dog_name,
        err,
      )

  async def _update_route_tracking(self, location_data: GPSLocationSample) -> None:
    """Update route tracking with new location point."""
    try:
      gps_data = self._get_gps_data()
      if not gps_data:
        return

      current_route = gps_data.get("current_route")
      if not current_route or not current_route.get("active", False):
        return

      # Add point to route
      route_point: GPSRoutePoint = {
        "latitude": location_data["latitude"],
        "longitude": location_data["longitude"],
        "altitude": location_data.get("altitude"),
        "timestamp": location_data["timestamp"],
        "accuracy": location_data["accuracy"],
        "speed": location_data.get("speed"),
        "heading": location_data.get("heading"),
      }

      self._route_points.append(route_point)

      # Cleanup old route points and enforce retention limits
      cutoff_time = dt_util.utcnow() - ROUTE_POINT_MAX_AGE
      self._route_points.prune(
        cutoff=cutoff_time,
        max_points=MAX_ROUTE_POINTS,
      )

      _LOGGER.debug(
        "Added route point for %s (total points: %d)",
        self._dog_name,
        len(self._route_points),
      )

    except Exception as err:
      _LOGGER.error(
        "Error updating route tracking for %s: %s",
        self._dog_name,
        err,
      )

  async def _update_coordinator_gps_data(
    self,
    location_data: GPSLocationSample,
  ) -> None:
    """Update coordinator with new GPS data."""
    try:
      # Get current dog data
      dog_data = self.coordinator.get_dog_data(self._dog_id)
      if not dog_data:
        return

      # Update GPS section
      gps_state = dog_data.get(MODULE_GPS)
      if isinstance(gps_state, dict):
        mutable_gps_state = cast(GPSModulePayload, gps_state)
      elif isinstance(gps_state, Mapping):
        mutable_gps_state = cast(GPSModulePayload, dict(gps_state))
      else:
        mutable_gps_state = cast(GPSModulePayload, {})
        runtime_payload = cast(CoordinatorDogData, dog_data)
        runtime_payload["gps"] = cast(
          CoordinatorModuleState,
          mutable_gps_state,
        )

      timestamp_iso = (
        self._serialize_timestamp(location_data["timestamp"])
        or dt_util.utcnow().isoformat()
      )
      mutable_gps_state.update(
        {
          "latitude": location_data["latitude"],
          "longitude": location_data["longitude"],
          "accuracy": location_data["accuracy"],
          "altitude": location_data.get("altitude"),
          "speed": location_data.get("speed"),
          "heading": location_data.get("heading"),
          "last_seen": timestamp_iso,
          "source": location_data["source"],
        },
      )

      # Update route points if tracking
      current_route = mutable_gps_state.get("current_route")
      if isinstance(current_route, Mapping) and current_route.get(
        "active",
        False,
      ):
        start_time_iso = self._serialize_timestamp(
          cast(datetime | str | None, current_route.get("start_time")),
        )
        end_time_iso = self._serialize_timestamp(
          cast(datetime | str | None, current_route.get("end_time")),
        )
        route_points: list[GPSRoutePoint] = [
          cast(GPSRoutePoint, self._serialize_route_point(point))
          for point in self._route_points.snapshot(limit=100)
        ]
        route_snapshot: GPSRouteSnapshot = {
          "active": True,
          "id": str(current_route.get("id") or ""),
          "name": str(current_route.get("name") or f"{self._dog_name} Route"),
          "start_time": start_time_iso or timestamp_iso,
          "points": route_points,
          "last_point_time": timestamp_iso,
          "point_count": len(route_points),
        }

        if end_time_iso is not None:
          route_snapshot["end_time"] = end_time_iso

        route_distance = current_route.get("distance")
        if isinstance(route_distance, int | float):
          route_snapshot["distance"] = float(route_distance)

        route_duration = current_route.get("duration")
        if isinstance(route_duration, int | float):
          route_snapshot["duration"] = route_duration

        mutable_gps_state["current_route"] = route_snapshot

      # This would normally update the coordinator data
      # The actual implementation would depend on the coordinator's update mechanism

      _LOGGER.debug(
        "Updated coordinator GPS data for %s",
        self._dog_name,
      )

    except Exception as err:
      _LOGGER.error(
        "Error updating coordinator GPS data for %s: %s",
        self._dog_name,
        err,
      )

  async def async_start_route_recording(self, route_name: str | None = None) -> str:
    """Start recording a new GPS route.

    Args:
        route_name: Optional name for the route

    Returns:
        Route ID
    """
    try:
      route_id = f"route_{self._dog_id}_{int(dt_util.utcnow().timestamp())}"
      start_time = dt_util.utcnow()
      start_time_iso = dt_util.as_utc(start_time).isoformat()

      # Clear previous route points
      self._route_points.clear()

      # Update GPS data with new route info
      gps_data = self._get_gps_data() or cast(GPSModulePayload, {})
      gps_data["current_route"] = {
        "id": route_id,
        "name": route_name or f"{self._dog_name} Route",
        "active": True,
        "start_time": start_time_iso,
        "points": [],
        "distance": 0,
        "duration": 0,
      }

      _LOGGER.info(
        "Started route recording for %s (route_id: %s)",
        self._dog_name,
        route_id,
      )

      return route_id

    except Exception as err:
      _LOGGER.error(
        "Error starting route recording for %s: %s",
        self._dog_name,
        err,
      )
      raise

  async def async_stop_route_recording(
    self,
    save_route: bool = True,
  ) -> JSONMutableMapping | None:
    """Stop recording the current GPS route.

    Args:
        save_route: Whether to save the completed route

    Returns:
        Route data if saved, None otherwise
    """
    try:
      gps_data = self._get_gps_data()
      if not gps_data:
        return None

      current_route = gps_data.get("current_route")
      if not current_route or not current_route.get("active", False):
        _LOGGER.warning(
          "No active route recording for %s",
          self._dog_name,
        )
        return None

      end_time = dt_util.utcnow()
      start_time_raw = current_route.get("start_time")
      start_time = (
        ensure_utc_datetime(
          start_time_raw,
        )
        or dt_util.utcnow()
      )
      current_route["start_time"] = dt_util.as_utc(
        start_time,
      ).isoformat()

      duration = (end_time - start_time).total_seconds()

      # Calculate route distance (simplified)
      distance = self._calculate_route_distance(
        self._route_points.view(),
      )

      points_snapshot = self._route_points.snapshot()
      serialized_points = [
        self._serialize_route_point(point) for point in points_snapshot
      ]
      start_time_iso = dt_util.as_utc(start_time).isoformat()
      end_time_iso = dt_util.as_utc(end_time).isoformat()
      route_data: JSONMutableMapping = {
        "id": str(current_route.get("id") or ""),
        "name": str(current_route.get("name") or f"{self._dog_name} Route"),
        "active": False,
        "dog_id": self._dog_id,
        "dog_name": self._dog_name,
        "start_time": start_time_iso,
        "end_time": end_time_iso,
        "duration": duration,
        "distance": float(distance),
        "points": cast(JSONValue, serialized_points),
        "point_count": len(serialized_points),
      }

      # Mark route as inactive
      current_route["active"] = False
      current_route["end_time"] = end_time_iso
      current_route["duration"] = duration
      current_route["distance"] = float(distance)
      current_route["point_count"] = len(serialized_points)

      if save_route:
        # Save route (would normally store in database/coordinator)
        _LOGGER.info(
          "Completed route recording for %s: %.2f km in %.1f minutes (%d points)",
          self._dog_name,
          distance / 1000,
          duration / 60,
          len(points_snapshot),
        )
        return route_data
      _LOGGER.info("Discarded route recording for %s", self._dog_name)
      return None

    except Exception as err:
      _LOGGER.error(
        "Error stopping route recording for %s: %s",
        self._dog_name,
        err,
      )
      return None

  def _calculate_route_distance(self, points: Sequence[GPSRoutePoint]) -> float:
    """Calculate total distance of route points in meters.

    Args:
        points: List of GPS points with latitude/longitude

    Returns:
        Total distance in meters
    """
    if len(points) < 2:
      return 0.0

    total_distance = 0.0

    try:
      from math import atan2, cos, radians, sin, sqrt

      # Earth's radius in meters
      earth_radius_m = 6_371_000

      for i in range(1, len(points)):
        lat1 = radians(points[i - 1]["latitude"])
        lon1 = radians(points[i - 1]["longitude"])
        lat2 = radians(points[i]["latitude"])
        lon2 = radians(points[i]["longitude"])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = earth_radius_m * c

        total_distance += distance

    except Exception as err:
      _LOGGER.error("Error calculating route distance: %s", err)
      return 0.0

    return total_distance

  async def async_export_route(
    self,
    format_type: str = "gpx",
  ) -> GPSRouteExportPayload | None:
    """Export current or last route in specified format.

    Args:
        format_type: Export format (gpx, json, csv)

    Returns:
        Export data or None if no route available
    """
    try:
      if not self._route_points:
        _LOGGER.warning(
          "No route points available for export for %s",
          self._dog_name,
        )
        return None

      if format_type == "gpx":
        return await self._export_route_gpx()
      if format_type == "json":
        return await self._export_route_json()
      if format_type == "csv":
        return await self._export_route_csv()
      _LOGGER.error("Unsupported export format: %s", format_type)
      return None

    except Exception as err:
      _LOGGER.error(
        "Error exporting route for %s: %s",
        self._dog_name,
        err,
      )
      return None

  async def _export_route_gpx(self) -> GPSRouteExportGPXPayload:
    """Export route as GPX format."""
    # Simplified GPX export matching the typed payload contract
    timestamp = dt_util.utcnow().strftime("%Y%m%d_%H%M%S")
    content_lines = [
      '<?xml version="1.0" encoding="UTF-8"?>',
      '<gpx version="1.1" creator="PawControl">',
    ]

    for point in self._route_points:
      point_time = point["timestamp"]
      iso_timestamp = (
        dt_util.as_utc(point_time).isoformat()
        if isinstance(point_time, datetime)
        else str(point_time)
      )
      content_lines.append(
        '  <trkpt lat="{lat}" lon="{lon}">'.format(
          lat=point["latitude"],
          lon=point["longitude"],
        ),
      )
      altitude = point.get("altitude")
      if altitude is not None:
        content_lines.append(f"    <ele>{altitude}</ele>")
      content_lines.append(f"    <time>{iso_timestamp}</time>")
      content_lines.append("  </trkpt>")

    content_lines.append("</gpx>")

    payload: GPSRouteExportGPXPayload = {
      "format": "gpx",
      "filename": f"{self._dog_id}_route_{timestamp}.gpx",
      "content": "\n".join(content_lines),
      "routes_count": 1,
    }
    return payload

  async def _export_route_json(self) -> GPSRouteExportJSONPayload:
    """Export route as JSON format."""
    export_time = dt_util.utcnow()
    points_snapshot = self._route_points.snapshot()
    distance_meters = self._calculate_route_distance(
      self._route_points.view(),
    )
    start_time = points_snapshot[0]["timestamp"]
    end_time = points_snapshot[-1]["timestamp"]

    start_iso = (
      dt_util.as_utc(start_time).isoformat()
      if isinstance(start_time, datetime)
      else str(start_time)
    )
    end_iso = (
      dt_util.as_utc(end_time).isoformat()
      if isinstance(end_time, datetime)
      else str(end_time)
    )

    duration_seconds = 0.0
    if isinstance(start_time, datetime) and isinstance(end_time, datetime):
      duration_seconds = max(
        (end_time - start_time).total_seconds(),
        0.0,
      )

    duration_minutes = duration_seconds / 60 if duration_seconds else None
    distance_km = distance_meters / 1000 if distance_meters else None
    avg_speed_kmh = (
      (distance_meters / 1000) / (duration_seconds / 3600)
      if duration_seconds and distance_meters
      else None
    )

    json_route: GPSRouteExportJSONRoute = {
      "start_time": start_iso,
      "end_time": end_iso,
      "duration_minutes": duration_minutes,
      "distance_km": distance_km,
      "avg_speed_kmh": avg_speed_kmh,
      "route_quality": "basic",
      "gps_points": [],
      "geofence_events": [],
    }

    for point in points_snapshot:
      timestamp = point["timestamp"]
      iso_timestamp = (
        dt_util.as_utc(timestamp).isoformat()
        if isinstance(timestamp, datetime)
        else str(timestamp)
      )
      json_point: GPSRouteExportJSONPoint = {
        "latitude": point["latitude"],
        "longitude": point["longitude"],
        "timestamp": iso_timestamp,
      }

      accuracy = point.get("accuracy")
      if isinstance(accuracy, int | float):
        json_point["accuracy"] = accuracy
      altitude = point.get("altitude")
      if isinstance(altitude, int | float):
        json_point["altitude"] = float(altitude)
      json_point["source"] = None
      json_route["gps_points"].append(json_point)

    json_content: GPSRouteExportJSONContent = {
      "dog_id": self._dog_id,
      "export_timestamp": dt_util.as_utc(export_time).isoformat(),
      "routes": [json_route],
    }

    payload: GPSRouteExportJSONPayload = {
      "format": "json",
      "filename": f"{self._dog_id}_route_{export_time.strftime('%Y%m%d_%H%M%S')}.json",
      "content": json_content,
      "routes_count": 1,
    }
    return payload

  async def _export_route_csv(self) -> GPSRouteExportCSVPayload:
    """Export route as CSV format."""
    csv_header = "timestamp,latitude,longitude,altitude,accuracy,speed,heading\n"
    csv_rows: list[str] = []

    for point in self._route_points:
      timestamp = point["timestamp"]
      iso_timestamp = (
        dt_util.as_utc(timestamp).isoformat()
        if isinstance(timestamp, datetime)
        else str(timestamp)
      )
      row_parts = [
        iso_timestamp,
        str(point["latitude"]),
        str(point["longitude"]),
        str(point.get("altitude", "")),
        str(point.get("accuracy", "")),
        str(point.get("speed", "")),
        str(point.get("heading", "")),
      ]
      csv_rows.append(",".join(row_parts))

    export_time = dt_util.utcnow().strftime("%Y%m%d_%H%M%S")
    payload: GPSRouteExportCSVPayload = {
      "format": "csv",
      "filename": f"{self._dog_id}_route_{export_time}.csv",
      "content": csv_header + "\n".join(csv_rows),
      "routes_count": 1,
    }
    return payload
