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

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
import logging
from typing import cast

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DEFAULT_MODEL, DEFAULT_SW_VERSION, MODULE_GPS
from .coordinator import PawControlCoordinator
from .entity import PawControlDogEntityBase
from .runtime_data import get_runtime_data
from .types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
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
    ensure_gps_payload,
)
from .utils import (
    async_call_add_entities,
    ensure_utc_datetime,
    normalise_entity_attributes,
)

_LOGGER = logging.getLogger(__name__)


def _normalise_attributes(attrs: Mapping[str, object]) -> JSONMutableMapping:
    """Return JSON-serialisable attributes for device tracker entities."""  # noqa: E111

    return normalise_entity_attributes(attrs)  # noqa: E111


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
    """  # noqa: E111
    runtime_data = get_runtime_data(hass, entry)  # noqa: E111
    if runtime_data is None:  # noqa: E111
        _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
        return
    coordinator = runtime_data.coordinator  # noqa: E111
    raw_dogs = getattr(runtime_data, "dogs", [])  # noqa: E111
    gps_enabled_dogs: list[DogConfigData] = []  # noqa: E111

    for raw_dog in raw_dogs:  # noqa: E111
        if not isinstance(raw_dog, Mapping):
            continue  # noqa: E111

        normalised = ensure_dog_config_data(cast(JSONMapping, raw_dog))
        if normalised is None:
            continue  # noqa: E111

        modules_projection = ensure_dog_modules_projection(normalised)
        normalised[DOG_MODULES_FIELD] = modules_projection.config

        if modules_projection.mapping.get(MODULE_GPS, False):
            gps_enabled_dogs.append(normalised)  # noqa: E111

    dogs: list[DogConfigData] = gps_enabled_dogs  # noqa: E111
    entity_factory = runtime_data.entity_factory  # noqa: E111
    profile = runtime_data.entity_profile  # noqa: E111

    if not dogs:  # noqa: E111
        if not raw_dogs:
            _LOGGER.warning("No dogs configured for device tracker platform")  # noqa: E111
        else:
            _LOGGER.info(  # noqa: E111
                "No dogs have GPS module enabled, skipping device tracker setup",
            )
        return

    entities: list[PawControlGPSTracker] = []  # noqa: E111

    for dog in dogs:  # noqa: E111
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
            config = entity_factory.create_entity_config(  # noqa: E111
                dog_id=dog_id,
                entity_type="device_tracker",
                module=MODULE_GPS,
                profile=profile,
                priority=8,  # High priority for GPS tracking
            )

            if config:  # noqa: E111
                tracker = PawControlGPSTracker(coordinator, dog_id, dog_name)
                entities.append(tracker)
        finally:
            entity_factory.finalize_budget(dog_id, profile)  # noqa: E111

    if (  # noqa: E111
        not entities
        and Platform.DEVICE_TRACKER
        in entity_factory.get_profile_info(
            profile,
        ).platforms
    ):
        for dog in dogs:
            dog_id = dog[DOG_ID_FIELD]  # noqa: E111
            dog_name = dog[DOG_NAME_FIELD]  # noqa: E111
            entities.append(PawControlGPSTracker(coordinator, dog_id, dog_name))  # noqa: E111
        _LOGGER.info(
            "Created baseline GPS device trackers for profile '%s'",
            profile,
        )

    if entities:  # noqa: E111
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
    else:  # noqa: E111
        _LOGGER.info(
            "No GPS device trackers created due to profile restrictions",
        )


class PawControlGPSTracker(PawControlDogEntityBase, TrackerEntity):
    """GPS device tracker for dogs with route recording capabilities.

    NEW: Implements device_tracker.{dog}_gps per requirements_inventory.md
    with route tracking, geofencing, and location history.
    """  # noqa: E111

    _attr_should_poll = False  # noqa: E111
    _attr_has_entity_name = True  # noqa: E111

    def __init__(  # noqa: E111
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
            model=DEFAULT_MODEL,
            sw_version=DEFAULT_SW_VERSION,
        )

        # GPS tracker state
        self._last_location: GPSLocationSample | None = None
        self._last_update: datetime | None = None
        self._route_points = GPSRouteBuffer[GPSRoutePoint]()
        self._current_zone: str | None = None

    @staticmethod  # noqa: E111
    def _serialize_timestamp(value: datetime | str | None) -> str | None:  # noqa: E111
        """Return an ISO-formatted timestamp for ``value`` when possible."""

        if isinstance(value, datetime):
            return dt_util.as_utc(value).isoformat()  # noqa: E111
        if isinstance(value, str):
            return value  # noqa: E111
        return None

    def _serialize_route_point(self, point: GPSRoutePoint) -> GPSRoutePoint:  # noqa: E111
        """Convert a route point to a JSON-safe mapping."""

        timestamp_iso = self._serialize_timestamp(point.get("timestamp"))
        payload: dict[str, JSONValue] = {
            "latitude": float(point["latitude"]),
            "longitude": float(point["longitude"]),
            "timestamp": timestamp_iso or dt_util.utcnow().isoformat(),
        }

        accuracy = point.get("accuracy")
        if isinstance(accuracy, int | float):
            payload["accuracy"] = float(accuracy)  # noqa: E111

        altitude = point.get("altitude")
        if isinstance(altitude, int | float):
            payload["altitude"] = float(altitude)  # noqa: E111

        speed = point.get("speed")
        if isinstance(speed, int | float):
            payload["speed"] = float(speed)  # noqa: E111

        heading = point.get("heading")
        if isinstance(heading, int | float):
            payload["heading"] = float(heading)  # noqa: E111

        return cast(GPSRoutePoint, payload)

    @property  # noqa: E111
    def available(self) -> bool:  # noqa: E111
        """Return True if GPS data is available."""
        return self.coordinator.available and self._get_gps_data() is not None

    @property  # noqa: E111
    def source_type(self) -> SourceType:  # noqa: E111
        """Return the source type of the device tracker."""
        return SourceType.GPS

    @property  # noqa: E111
    def state(self) -> str:  # noqa: E111
        """Return the state of the device tracker."""
        gps_data = self._get_gps_data()
        if not gps_data:
            return STATE_UNKNOWN  # noqa: E111

        zone = gps_data.get("zone")
        if zone == "home":
            return STATE_HOME  # noqa: E111
        if zone and zone != "unknown":
            return zone  # noqa: E111
        return STATE_NOT_HOME

    @property  # noqa: E111
    def latitude(self) -> float | None:  # noqa: E111
        """Return the GPS latitude."""
        gps_data = self._get_gps_data()
        if not gps_data:
            return None  # noqa: E111

        try:
            lat = gps_data.get("latitude")  # noqa: E111
            return float(lat) if lat is not None else None  # noqa: E111
        except ValueError:
            return None  # noqa: E111
        except TypeError:
            return None  # noqa: E111

    @property  # noqa: E111
    def longitude(self) -> float | None:  # noqa: E111
        """Return the GPS longitude."""
        gps_data = self._get_gps_data()
        if not gps_data:
            return None  # noqa: E111

        try:
            lon = gps_data.get("longitude")  # noqa: E111
            return float(lon) if lon is not None else None  # noqa: E111
        except ValueError:
            return None  # noqa: E111
        except TypeError:
            return None  # noqa: E111

    @property  # noqa: E111
    def location_accuracy(self) -> int | None:  # noqa: E111
        """Return the GPS accuracy in meters."""
        gps_data = self._get_gps_data()
        if not gps_data:
            return None  # noqa: E111

        try:
            accuracy = gps_data.get("accuracy")  # noqa: E111
            return int(accuracy) if accuracy is not None else DEFAULT_GPS_ACCURACY  # noqa: E111
        except ValueError:
            return DEFAULT_GPS_ACCURACY  # noqa: E111
        except TypeError:
            return DEFAULT_GPS_ACCURACY  # noqa: E111

    @property  # noqa: E111
    def battery_level(self) -> int | None:  # noqa: E111
        """Return GPS tracker battery level."""
        gps_data = self._get_gps_data()
        if not gps_data:
            return None  # noqa: E111

        try:
            battery = gps_data.get("battery")  # noqa: E111
            return int(battery) if battery is not None else None  # noqa: E111
        except ValueError:
            return None  # noqa: E111
        except TypeError:
            return None  # noqa: E111

    @property  # noqa: E111
    def location_name(self) -> str | None:  # noqa: E111
        """Return the current location name/zone."""
        gps_data = self._get_gps_data()
        if not gps_data:
            return None  # noqa: E111

        zone = gps_data.get("zone")
        return zone if zone and zone != "unknown" else None

    @property  # noqa: E111
    def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
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
            # Basic GPS info  # noqa: E114
            altitude = gps_data.get("altitude")  # noqa: E111
            speed = gps_data.get("speed")  # noqa: E111
            heading = gps_data.get("heading")  # noqa: E111
            satellites = gps_data.get("satellites")  # noqa: E111
            location_source = gps_data.get("source", "unknown")  # noqa: E111
            last_seen = gps_data.get("last_seen")  # noqa: E111
            distance_from_home = gps_data.get("distance_from_home")  # noqa: E111

            if isinstance(altitude, int | float):  # noqa: E111
                attrs["altitude"] = float(altitude)
            if isinstance(speed, int | float):  # noqa: E111
                attrs["speed"] = float(speed)
            if isinstance(heading, int | float):  # noqa: E111
                attrs["heading"] = float(heading)
            if isinstance(satellites, int):  # noqa: E111
                attrs["satellites"] = satellites

            attrs["location_source"] = (  # noqa: E111
                location_source
                if isinstance(
                    location_source,
                    str,
                )
                else "unknown"
            )

            if isinstance(last_seen, datetime):  # noqa: E111
                attrs["last_seen"] = dt_util.as_utc(last_seen).isoformat()
            elif isinstance(last_seen, str):  # noqa: E111
                attrs["last_seen"] = last_seen

            if isinstance(distance_from_home, int | float):  # noqa: E111
                attrs["distance_from_home"] = float(distance_from_home)

            # Route information  # noqa: E114
            current_route = gps_data.get("current_route")  # noqa: E111
            if current_route:  # noqa: E111
                attrs["route_active"] = bool(current_route.get("active", True))
                attrs["route_points"] = len(current_route.get("points", []))

                route_distance = current_route.get("distance")
                if isinstance(route_distance, int | float):
                    attrs["route_distance"] = float(route_distance)  # noqa: E111

                route_duration = current_route.get("duration")
                if isinstance(route_duration, int | float):
                    attrs["route_duration"] = route_duration  # noqa: E111

                route_start = current_route.get("start_time")
                if isinstance(route_start, datetime):
                    attrs["route_start_time"] = dt_util.as_utc(  # noqa: E111
                        route_start,
                    ).isoformat()
                elif isinstance(route_start, str):
                    attrs["route_start_time"] = route_start  # noqa: E111

            # Geofencing info  # noqa: E114
            geofence_status = gps_data.get("geofence_status")  # noqa: E111
            if geofence_status:  # noqa: E111
                in_safe_zone = geofence_status.get("in_safe_zone", False)
                zone_name = geofence_status.get("zone_name")
                zone_distance = geofence_status.get("distance_to_boundary")

                attrs["in_safe_zone"] = bool(in_safe_zone)
                if isinstance(zone_name, str):
                    attrs["zone_name"] = zone_name  # noqa: E111
                if isinstance(zone_distance, int | float):
                    attrs["zone_distance"] = float(zone_distance)  # noqa: E111

            status_snapshot = self._get_status_snapshot()  # noqa: E111
            if status_snapshot is not None:  # noqa: E111
                attrs["in_safe_zone"] = bool(
                    status_snapshot.get(
                        "in_safe_zone",
                        attrs.get("in_safe_zone", True),
                    ),
                )

            # Walk integration  # noqa: E114
            walk_info = gps_data.get("walk_info")  # noqa: E111
            if walk_info:  # noqa: E111
                attrs["walk_active"] = bool(walk_info.get("active", False))

                walk_id = walk_info.get("walk_id")
                if isinstance(walk_id, str):
                    attrs["walk_id"] = walk_id  # noqa: E111

                walk_start = walk_info.get("start_time")
                if isinstance(walk_start, datetime):
                    attrs["walk_start_time"] = dt_util.as_utc(  # noqa: E111
                        walk_start,
                    ).isoformat()
                elif isinstance(walk_start, str):
                    attrs["walk_start_time"] = walk_start  # noqa: E111

        return _normalise_attributes(attrs)

    def _get_gps_data(self) -> GPSModulePayload | None:  # noqa: E111
        """Get GPS data from coordinator."""
        if not self.coordinator.available:
            return None  # noqa: E111

        gps_state = self._get_module_data(MODULE_GPS)
        if gps_state:
            return ensure_gps_payload(cast(Mapping[str, object], gps_state))  # noqa: E111

        return None

    async def async_update_location(  # noqa: E111
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
            # Validate coordinates  # noqa: E114
            if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):  # noqa: E111
                _LOGGER.error(
                    "Invalid GPS coordinates for %s: lat=%s, lon=%s",
                    self._dog_name,
                    latitude,
                    longitude,
                )
                return

            if timestamp is None:  # noqa: E111
                timestamp = dt_util.utcnow()

            # Check minimum update interval to prevent spam  # noqa: E114
            if (  # noqa: E111
                self._last_update
                and (timestamp - self._last_update).total_seconds()
                < MIN_LOCATION_UPDATE_INTERVAL
            ):
                _LOGGER.debug(
                    "GPS update too frequent for %s, skipping",
                    self._dog_name,
                )
                return

            accuracy_value = (
                int(accuracy) if accuracy is not None else DEFAULT_GPS_ACCURACY
            )  # noqa: E111
            location_data: GPSLocationSample = {  # noqa: E111
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

            # Update location if this source has higher priority  # noqa: E114
            last_location = self._last_location  # noqa: E111
            if (  # noqa: E111
                last_location is None
                or location_data["priority"] >= last_location["priority"]
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
            _LOGGER.error(  # noqa: E111
                "Error updating GPS location for %s: %s",
                self._dog_name,
                err,
            )

    async def _update_route_tracking(self, location_data: GPSLocationSample) -> None:  # noqa: E111
        """Update route tracking with new location point."""
        try:
            gps_data = self._get_gps_data()  # noqa: E111
            if not gps_data:  # noqa: E111
                return

            current_route = gps_data.get("current_route")  # noqa: E111
            if not current_route or not current_route.get("active", False):  # noqa: E111
                return

            # Add point to route  # noqa: E114
            route_point: GPSRoutePoint = {  # noqa: E111
                "latitude": location_data["latitude"],
                "longitude": location_data["longitude"],
                "altitude": location_data.get("altitude"),
                "timestamp": location_data["timestamp"],
                "accuracy": location_data["accuracy"],
                "speed": location_data.get("speed"),
                "heading": location_data.get("heading"),
            }

            self._route_points.append(route_point)  # noqa: E111

            # Cleanup old route points and enforce retention limits  # noqa: E114
            cutoff_time = dt_util.utcnow() - ROUTE_POINT_MAX_AGE  # noqa: E111
            self._route_points.prune(  # noqa: E111
                cutoff=cutoff_time,
                max_points=MAX_ROUTE_POINTS,
            )

            _LOGGER.debug(  # noqa: E111
                "Added route point for %s (total points: %d)",
                self._dog_name,
                len(self._route_points),
            )

        except Exception as err:
            _LOGGER.error(  # noqa: E111
                "Error updating route tracking for %s: %s",
                self._dog_name,
                err,
            )

    async def _update_coordinator_gps_data(  # noqa: E111
        self,
        location_data: GPSLocationSample,
    ) -> None:
        """Update coordinator with new GPS data."""
        try:
            timestamp_iso = (  # noqa: E111
                self._serialize_timestamp(location_data["timestamp"])
                or dt_util.utcnow().isoformat()
            )
            gps_updates: JSONMutableMapping = {  # noqa: E111
                "latitude": location_data["latitude"],
                "longitude": location_data["longitude"],
                "accuracy": location_data["accuracy"],
                "altitude": location_data.get("altitude"),
                "speed": location_data.get("speed"),
                "heading": location_data.get("heading"),
                "last_seen": timestamp_iso,
                "source": location_data["source"],
            }

            # Update route points if tracking  # noqa: E114
            gps_data = self._get_gps_data()  # noqa: E111
            current_route = (  # noqa: E111
                gps_data.get("current_route") if isinstance(gps_data, Mapping) else None
            )
            if isinstance(current_route, Mapping) and current_route.get(  # noqa: E111
                "active",
                False,
            ):
                start_time_iso = self._serialize_timestamp(
                    cast(datetime | str | None, current_route.get("start_time")),
                )
                end_time_iso = self._serialize_timestamp(
                    current_route.get("end_time"),
                )
                route_points: list[GPSRoutePoint] = [
                    self._serialize_route_point(point)
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
                    route_snapshot["end_time"] = end_time_iso  # noqa: E111

                route_distance = current_route.get("distance")
                if isinstance(route_distance, int | float):
                    route_snapshot["distance"] = float(route_distance)  # noqa: E111

                route_duration = current_route.get("duration")
                if isinstance(route_duration, int | float):
                    route_snapshot["duration"] = route_duration  # noqa: E111

                gps_updates["current_route"] = route_snapshot

            await self.coordinator.async_apply_module_updates(  # noqa: E111
                self._dog_id,
                MODULE_GPS,
                gps_updates,
            )

            _LOGGER.debug(  # noqa: E111
                "Updated coordinator GPS data for %s",
                self._dog_name,
            )

        except Exception as err:
            _LOGGER.error(  # noqa: E111
                "Error updating coordinator GPS data for %s: %s",
                self._dog_name,
                err,
            )

    async def async_start_route_recording(self, route_name: str | None = None) -> str:  # noqa: E111
        """Start recording a new GPS route.

        Args:
            route_name: Optional name for the route

        Returns:
            Route ID
        """
        try:
            route_id = f"route_{self._dog_id}_{int(dt_util.utcnow().timestamp())}"  # noqa: E111
            start_time = dt_util.utcnow()  # noqa: E111
            start_time_iso = dt_util.as_utc(start_time).isoformat()  # noqa: E111

            # Clear previous route points  # noqa: E114
            self._route_points.clear()  # noqa: E111

            # Update GPS data with new route info  # noqa: E114
            gps_data = self._get_gps_data() or cast(GPSModulePayload, {})  # noqa: E111
            gps_data["current_route"] = {  # noqa: E111
                "id": route_id,
                "name": route_name or f"{self._dog_name} Route",
                "active": True,
                "start_time": start_time_iso,
                "points": [],
                "distance": 0,
                "duration": 0,
            }

            _LOGGER.info(  # noqa: E111
                "Started route recording for %s (route_id: %s)",
                self._dog_name,
                route_id,
            )

            return route_id  # noqa: E111

        except Exception as err:
            _LOGGER.error(  # noqa: E111
                "Error starting route recording for %s: %s",
                self._dog_name,
                err,
            )
            raise  # noqa: E111

    async def async_stop_route_recording(  # noqa: E111
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
            gps_data = self._get_gps_data()  # noqa: E111
            if not gps_data:  # noqa: E111
                return None

            current_route = gps_data.get("current_route")  # noqa: E111
            if not current_route or not current_route.get("active", False):  # noqa: E111
                _LOGGER.warning(
                    "No active route recording for %s",
                    self._dog_name,
                )
                return None

            end_time = dt_util.utcnow()  # noqa: E111
            start_time_raw = current_route.get("start_time")  # noqa: E111
            start_time = (  # noqa: E111
                ensure_utc_datetime(
                    start_time_raw,
                )
                or dt_util.utcnow()
            )
            current_route["start_time"] = dt_util.as_utc(  # noqa: E111
                start_time,
            ).isoformat()

            duration = (end_time - start_time).total_seconds()  # noqa: E111

            # Calculate route distance (simplified)  # noqa: E114
            distance = self._calculate_route_distance(  # noqa: E111
                self._route_points.view(),
            )

            points_snapshot = self._route_points.snapshot()  # noqa: E111
            serialized_points = [  # noqa: E111
                self._serialize_route_point(point) for point in points_snapshot
            ]
            start_time_iso = dt_util.as_utc(start_time).isoformat()  # noqa: E111
            end_time_iso = dt_util.as_utc(end_time).isoformat()  # noqa: E111
            route_data: JSONMutableMapping = {  # noqa: E111
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

            # Mark route as inactive  # noqa: E114
            current_route["active"] = False  # noqa: E111
            current_route["end_time"] = end_time_iso  # noqa: E111
            current_route["duration"] = duration  # noqa: E111
            current_route["distance"] = float(distance)  # noqa: E111
            current_route["point_count"] = len(serialized_points)  # noqa: E111

            if save_route:  # noqa: E111
                # Save route (would normally store in database/coordinator)
                _LOGGER.info(
                    "Completed route recording for %s: %.2f km in %.1f minutes (%d points)",
                    self._dog_name,
                    distance / 1000,
                    duration / 60,
                    len(points_snapshot),
                )
                return route_data
            _LOGGER.info("Discarded route recording for %s", self._dog_name)  # noqa: E111
            return None  # noqa: E111

        except Exception as err:
            _LOGGER.error(  # noqa: E111
                "Error stopping route recording for %s: %s",
                self._dog_name,
                err,
            )
            return None  # noqa: E111

    def _calculate_route_distance(self, points: Sequence[GPSRoutePoint]) -> float:  # noqa: E111
        """Calculate total distance of route points in meters.

        Args:
            points: List of GPS points with latitude/longitude

        Returns:
            Total distance in meters
        """
        if len(points) < 2:
            return 0.0  # noqa: E111

        total_distance = 0.0

        try:
            from math import atan2, cos, radians, sin, sqrt  # noqa: E111

            # Earth's radius in meters  # noqa: E114
            earth_radius_m = 6_371_000  # noqa: E111

            for i in range(1, len(points)):  # noqa: E111
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
            _LOGGER.error("Error calculating route distance: %s", err)  # noqa: E111
            return 0.0  # noqa: E111

        return total_distance

    async def async_export_route(  # noqa: E111
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
            if not self._route_points:  # noqa: E111
                _LOGGER.warning(
                    "No route points available for export for %s",
                    self._dog_name,
                )
                return None

            if format_type == "gpx":  # noqa: E111
                return await self._export_route_gpx()
            if format_type == "json":  # noqa: E111
                return await self._export_route_json()
            if format_type == "csv":  # noqa: E111
                return await self._export_route_csv()
            _LOGGER.error("Unsupported export format: %s", format_type)  # noqa: E111
            return None  # noqa: E111

        except Exception as err:
            _LOGGER.error(  # noqa: E111
                "Error exporting route for %s: %s",
                self._dog_name,
                err,
            )
            return None  # noqa: E111

    async def _export_route_gpx(self) -> GPSRouteExportGPXPayload:  # noqa: E111
        """Export route as GPX format."""
        # Simplified GPX export matching the typed payload contract
        timestamp = dt_util.utcnow().strftime("%Y%m%d_%H%M%S")
        content_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<gpx version="1.1" creator="PawControl">',
        ]

        for point in self._route_points:
            point_time = point["timestamp"]  # noqa: E111
            iso_timestamp = (  # noqa: E111
                dt_util.as_utc(point_time).isoformat()
                if isinstance(point_time, datetime)
                else str(point_time)
            )
            content_lines.append(  # noqa: E111
                '  <trkpt lat="{lat}" lon="{lon}">'.format(
                    lat=point["latitude"],
                    lon=point["longitude"],
                ),
            )
            altitude = point.get("altitude")  # noqa: E111
            if altitude is not None:  # noqa: E111
                content_lines.append(f"    <ele>{altitude}</ele>")
            content_lines.append(f"    <time>{iso_timestamp}</time>")  # noqa: E111
            content_lines.append("  </trkpt>")  # noqa: E111

        content_lines.append("</gpx>")

        payload: GPSRouteExportGPXPayload = {
            "format": "gpx",
            "filename": f"{self._dog_id}_route_{timestamp}.gpx",
            "content": "\n".join(content_lines),
            "routes_count": 1,
        }
        return payload

    async def _export_route_json(self) -> GPSRouteExportJSONPayload:  # noqa: E111
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
            duration_seconds = max(  # noqa: E111
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
            timestamp = point["timestamp"]  # noqa: E111
            iso_timestamp = (  # noqa: E111
                dt_util.as_utc(timestamp).isoformat()
                if isinstance(timestamp, datetime)
                else str(timestamp)
            )
            json_point: GPSRouteExportJSONPoint = {  # noqa: E111
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "timestamp": iso_timestamp,
            }

            accuracy = point.get("accuracy")  # noqa: E111
            if isinstance(accuracy, int | float):  # noqa: E111
                json_point["accuracy"] = accuracy
            altitude = point.get("altitude")  # noqa: E111
            if isinstance(altitude, int | float):  # noqa: E111
                json_point["altitude"] = float(altitude)
            json_point["source"] = None  # noqa: E111
            json_route["gps_points"].append(json_point)  # noqa: E111

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

    async def _export_route_csv(self) -> GPSRouteExportCSVPayload:  # noqa: E111
        """Export route as CSV format."""
        csv_header = "timestamp,latitude,longitude,altitude,accuracy,speed,heading\n"
        csv_rows: list[str] = []

        for point in self._route_points:
            timestamp = point["timestamp"]  # noqa: E111
            iso_timestamp = (  # noqa: E111
                dt_util.as_utc(timestamp).isoformat()
                if isinstance(timestamp, datetime)
                else str(timestamp)
            )
            row_parts = [  # noqa: E111
                iso_timestamp,
                str(point["latitude"]),
                str(point["longitude"]),
                str(point.get("altitude", "")),
                str(point.get("accuracy", "")),
                str(point.get("speed", "")),
                str(point.get("heading", "")),
            ]
            csv_rows.append(",".join(row_parts))  # noqa: E111

        export_time = dt_util.utcnow().strftime("%Y%m%d_%H%M%S")
        payload: GPSRouteExportCSVPayload = {
            "format": "csv",
            "filename": f"{self._dog_id}_route_{export_time}.csv",
            "content": csv_header + "\n".join(csv_rows),
            "routes_count": 1,
        }
        return payload
