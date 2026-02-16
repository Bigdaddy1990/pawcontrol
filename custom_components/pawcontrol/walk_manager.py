"""Walk and GPS management for PawControl with advanced optimizations.

Enhanced with performance optimizations, caching, and memory management
for Platinum quality compliance.

Quality Scale: Platinum target
P26.1.1++
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Mapping
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from html import escape
import json
import logging
import math
from typing import Any, Final, TypeVar, cast

from homeassistant.util import dt as dt_util

from .types import (
  GPSCacheDiagnosticsMetadata,
  GPSCacheSnapshot,
  GPSCacheStats,
  GPXAttributeMap,
  JSONMutableMapping,
  JSONValue,
  WalkDailyStatistics,
  WalkDetectionMetadata,
  WalkDetectionMutableMetadata,
  WalkGPSSnapshot,
  WalkLocationSnapshot,
  WalkManagerDogSnapshot,
  WalkOverviewSnapshot,
  WalkPerformanceCounters,
  WalkPerformanceSnapshot,
  WalkRouteBounds,
  WalkRouteExportFormat,
  WalkRouteExportPayload,
  WalkRoutePoint,
  WalkSessionSnapshot,
  WalkStatisticsSnapshot,
  WalkWeeklyStatistics,
)
from .utils import Number, is_number, normalize_value

_LOGGER = logging.getLogger(__name__)


class WeatherCondition(StrEnum):
  """Enumeration of supported walk weather conditions."""  # noqa: E111

  SUNNY = "sunny"  # noqa: E111
  CLOUDY = "cloudy"  # noqa: E111
  RAINY = "rainy"  # noqa: E111
  SNOWY = "snowy"  # noqa: E111
  WINDY = "windy"  # noqa: E111
  HOT = "hot"  # noqa: E111
  COLD = "cold"  # noqa: E111


# OPTIMIZE: Performance constants
GPS_CACHE_SIZE_LIMIT = 1000
PATH_POINT_LIMIT = 500  # Limit path points to prevent memory leaks
STATISTICS_CACHE_TTL = 300  # 5 minutes cache for statistics
DISTANCE_CALCULATION_CACHE_SIZE = 100
LOCATION_ANALYSIS_BATCH_SIZE = 10

# GPX Export constants
GPX_VERSION = "1.1"
GPX_CREATOR = "PawControl Home Assistant Integration v2.0"
GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
GPX_SCHEMA_LOCATION = (
  "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd"
)


type CachedGPSLocation = tuple[float, float, datetime]
type DistanceCacheKey = tuple[tuple[float, float], tuple[float, float]]


LocationT = TypeVar("LocationT", bound=CachedGPSLocation)


class GPSCache[LocationT: CachedGPSLocation]:
  """Optimized GPS data cache with LRU eviction."""  # noqa: E111

  _DISTANCE_CACHE_LIMIT: Final[int] = DISTANCE_CALCULATION_CACHE_SIZE  # noqa: E111

  def __init__(self, max_size: int = GPS_CACHE_SIZE_LIMIT) -> None:  # noqa: E111
    """Initialize GPS cache.

    Args:
        max_size: Maximum cache entries
    """
    self._cache: dict[str, LocationT] = {}
    self._access_order: deque[str] = deque()
    self._max_size = max_size
    self._distance_cache: dict[DistanceCacheKey, float] = {}
    self._hits = 0
    self._misses = 0
    self._evictions = 0

  def get_location(self, dog_id: str) -> LocationT | None:  # noqa: E111
    """Get cached location with LRU update.

    Args:
        dog_id: Dog identifier

    Returns:
        Location tuple or None
    """
    if dog_id in self._cache:
      # Update access order for LRU  # noqa: E114
      self._access_order.remove(dog_id)  # noqa: E111
      self._access_order.append(dog_id)  # noqa: E111
      self._hits += 1  # noqa: E111
      return self._cache[dog_id]  # noqa: E111
    self._misses += 1
    return None

  def set_location(  # noqa: E111
    self,
    dog_id: str,
    latitude: float,
    longitude: float,
    timestamp: datetime,
  ) -> None:
    """Set location with LRU eviction.

    Args:
        dog_id: Dog identifier
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        timestamp: Location timestamp
    """
    # Evict oldest if at capacity
    if len(self._cache) >= self._max_size and dog_id not in self._cache:
      oldest = self._access_order.popleft()  # noqa: E111
      del self._cache[oldest]  # noqa: E111
      self._evictions += 1  # noqa: E111

    self._cache[dog_id] = cast(LocationT, (latitude, longitude, timestamp))

    # Update access order
    if dog_id in self._access_order:
      self._access_order.remove(dog_id)  # noqa: E111
    self._access_order.append(dog_id)

  def calculate_distance_cached(  # noqa: E111
    self,
    point1: tuple[float, float],
    point2: tuple[float, float],
  ) -> float:
    """Calculate distance with caching for frequently used points.

    Args:
        point1: First GPS coordinate (lat, lon)
        point2: Second GPS coordinate (lat, lon)

    Returns:
        Distance in meters
    """
    # Create cache key (order independent)
    ordered = tuple(sorted((point1, point2)))
    cache_key = cast(DistanceCacheKey, ordered)

    if cache_key in self._distance_cache:
      return self._distance_cache[cache_key]  # noqa: E111

    # Calculate distance using Haversine formula
    distance = self._haversine_distance(point1, point2)

    # Cache result with size limit
    if len(self._distance_cache) >= self._DISTANCE_CACHE_LIMIT:
      # Remove oldest entry  # noqa: E114
      oldest_key = next(iter(self._distance_cache))  # noqa: E111
      del self._distance_cache[oldest_key]  # noqa: E111

    self._distance_cache[cache_key] = distance
    return distance

  @staticmethod  # noqa: E111
  def _haversine_distance(  # noqa: E111
    point1: tuple[float, float],
    point2: tuple[float, float],
  ) -> float:
    """Calculate Haversine distance between two points.

    OPTIMIZE: Static method for better performance, no self access needed.

    Args:
        point1: First GPS coordinate (lat, lon)
        point2: Second GPS coordinate (lat, lon)

    Returns:
        Distance in meters
    """
    lat1, lon1 = math.radians(point1[0]), math.radians(point1[1])
    lat2, lon2 = math.radians(point2[0]), math.radians(point2[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
      math.sin(dlat / 2) ** 2
      + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    # Earth radius in meters
    return c * 6371000

  def clear(self) -> None:  # noqa: E111
    """Clear cache."""
    self._cache.clear()
    self._access_order.clear()
    self._distance_cache.clear()
    self._hits = 0
    self._misses = 0
    self._evictions = 0

  def get_stats(self) -> GPSCacheStats:  # noqa: E111
    """Get cache statistics."""
    total_requests = self._hits + self._misses
    hit_rate = (self._hits / total_requests * 100.0) if total_requests else 0.0

    stats: GPSCacheStats = {
      "hits": self._hits,
      "misses": self._misses,
      "hit_rate": hit_rate,
      "cached_locations": len(self._cache),
      "distance_cache_entries": len(self._distance_cache),
      "evictions": self._evictions,
      "max_size": self._max_size,
    }

    return stats

  def get_metadata(self) -> GPSCacheDiagnosticsMetadata:  # noqa: E111
    """Return metadata describing current cache contents."""

    metadata: GPSCacheDiagnosticsMetadata = {
      "cached_dogs": sorted(self._cache),
      "max_size": self._max_size,
      "distance_cache_entries": len(self._distance_cache),
      "evictions": self._evictions,
    }

    return metadata

  def coordinator_snapshot(self) -> GPSCacheSnapshot:  # noqa: E111
    """Return a telemetry snapshot suitable for diagnostics."""

    return GPSCacheSnapshot(stats=self.get_stats(), metadata=self.get_metadata())


@dataclass(slots=True)
class WalkSession:
  """Representation of an active walk session."""  # noqa: E111

  walk_id: str  # noqa: E111
  dog_id: str  # noqa: E111
  walk_type: str  # noqa: E111
  start_time: datetime  # noqa: E111
  walker: str | None = None  # noqa: E111
  leash_used: bool = True  # noqa: E111
  weather: WeatherCondition | None = None  # noqa: E111
  track_route: bool = True  # noqa: E111
  safety_alerts: bool = True  # noqa: E111
  start_location: WalkLocationSnapshot | None = None  # noqa: E111
  path: list[WalkRoutePoint] = field(default_factory=list)  # noqa: E111
  detection_confidence: float | None = None  # noqa: E111
  door_sensor: str | None = None  # noqa: E111
  detection_metadata: WalkDetectionMutableMetadata | None = None  # noqa: E111

  def as_dict(self) -> WalkSessionSnapshot:  # noqa: E111
    """Convert the session to a mutable dictionary."""

    start_location = (
      cast(WalkLocationSnapshot, dict(self.start_location))
      if self.start_location is not None
      else None
    )
    detection_metadata = (
      cast(WalkDetectionMutableMetadata, dict(self.detection_metadata))
      if self.detection_metadata is not None
      else None
    )

    snapshot: WalkSessionSnapshot = {
      "walk_id": self.walk_id,
      "dog_id": self.dog_id,
      "walk_type": self.walk_type,
      "start_time": self.start_time.isoformat(),
      "walker": self.walker,
      "leash_used": self.leash_used,
      "weather": self.weather.value if self.weather else None,
      "track_route": self.track_route,
      "safety_alerts": self.safety_alerts,
      "start_location": start_location,
      "end_time": None,
      "duration": None,
      "distance": 0.0,
      "end_location": None,
      "status": "in_progress",
      "average_speed": None,
      "max_speed": None,
      "calories_burned": None,
      "elevation_gain": 0.0,
      "path": list(self.path),
      "notes": None,
      "dog_weight_kg": None,
      "detection_confidence": self.detection_confidence,
      "door_sensor": self.door_sensor,
      "detection_metadata": detection_metadata,
    }
    return snapshot


class WalkManager:
  """Optimized walk and GPS management with advanced caching and performance monitoring.

  OPTIMIZE: Enhanced with GPS caching, memory management, batch processing,
  and performance optimizations for Platinum-targeted quality.
  """  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    """Initialize optimized walk manager."""
    self._dogs: dict[str, WalkManagerDogSnapshot] = {}
    self._walk_data: dict[str, WalkStatisticsSnapshot] = {}
    self._gps_data: dict[str, WalkGPSSnapshot] = {}
    self._current_walks: dict[str, WalkSessionSnapshot] = {}
    self._walk_history: dict[str, list[WalkSessionSnapshot]] = {}
    self._session_counters: dict[str, int] = {}
    self._data_lock = asyncio.Lock()

    # OPTIMIZE: Enhanced caching system
    self._gps_cache: GPSCache[CachedGPSLocation] = GPSCache()
    # Cache with timestamp
    self._zone_cache: dict[str, tuple[str, datetime]] = {}
    self._statistics_cache: dict[
      str,
      tuple[WalkStatisticsSnapshot, datetime],
    ] = {}

    # OPTIMIZE: Walk detection parameters with better defaults
    self._walk_detection_enabled = True
    self._min_walk_distance = 50.0  # meters
    self._min_walk_duration = 120  # seconds
    self._walk_timeout = 1800  # 30 minutes
    self._min_speed_threshold = 0.5  # km/h minimum speed for walk detection

    # OPTIMIZE: Performance monitoring
    self._performance_metrics: WalkPerformanceCounters = {
      "gps_updates": 0,
      "distance_calculations": 0,
      "cache_hits": 0,
      "cache_misses": 0,
      "memory_cleanups": 0,
      "gpx_exports": 0,
      "export_errors": 0,
    }

    # OPTIMIZE: Batch processing for location analysis
    self._location_analysis_queue: dict[
      str,
      list[tuple[float, float, datetime]],
    ] = {}
    self._batch_analysis_task: asyncio.Task | None = None

    _LOGGER.debug("WalkManager initialized with optimizations")

  def _update_dog_container(self, dog_id: str) -> None:  # noqa: E111
    """Ensure compatibility structure for tests and legacy callers."""

    container = self._dogs.setdefault(
      dog_id,
      {
        "active_walk": None,
        "history": [],
        "stats": cast(WalkStatisticsSnapshot, {}),
        "gps": cast(WalkGPSSnapshot, {}),
      },
    )
    active_walk = self._current_walks.get(dog_id)
    if active_walk is not None:
      container["active_walk"] = cast(  # noqa: E111
        WalkSessionSnapshot,
        dict(active_walk),
      )
    history = self._walk_history.get(dog_id, [])
    container["history"] = [cast(WalkSessionSnapshot, dict(entry)) for entry in history]
    stats = self._walk_data.get(dog_id)
    container["stats"] = (
      cast(WalkStatisticsSnapshot, stats.copy())
      if stats is not None
      else cast(WalkStatisticsSnapshot, {})
    )
    gps = self._gps_data.get(dog_id)
    container["gps"] = (
      cast(WalkGPSSnapshot, gps.copy())
      if gps is not None
      else cast(WalkGPSSnapshot, {})
    )

  async def async_initialize(self, dog_ids: list[str]) -> None:  # noqa: E111
    """Initialize walk manager for specified dogs with batch optimization.

    OPTIMIZE: Batch initialization for better performance.

    Args:
        dog_ids: List of dog identifiers to track
    """
    async with self._data_lock:
      # OPTIMIZE: Batch initialize all dogs  # noqa: E114
      for dog_id in dog_ids:  # noqa: E111
        self._walk_data[dog_id] = {
          "walks_today": 0,
          "total_duration_today": 0.0,
          "total_distance_today": 0.0,
          "last_walk": None,
          "last_walk_duration": None,
          "last_walk_distance": None,
          "average_duration": None,
          "average_distance": None,
          "weekly_walks": 0,
          "weekly_distance": 0.0,
          "needs_walk": False,
          "walk_streak": 0,
          "energy_level": "normal",  # OPTIMIZE: Added energy tracking
          "walk_in_progress": False,
          "current_walk": None,
        }

        self._gps_data[dog_id] = {
          "latitude": None,
          "longitude": None,
          "accuracy": None,
          "speed": None,
          "heading": None,
          "altitude": None,
          "last_seen": None,
          "source": None,
          "available": False,
          "zone": "unknown",
          "distance_from_home": None,
          "signal_strength": None,  # OPTIMIZE: Added signal strength
          "battery_level": None,  # OPTIMIZE: Added battery tracking
        }

        self._walk_history[dog_id] = []
        self._location_analysis_queue[dog_id] = []
        self._session_counters[dog_id] = 0

        self._update_dog_container(dog_id)

      # Start batch analysis task  # noqa: E114
      if self._batch_analysis_task is None:  # noqa: E111
        self._batch_analysis_task = asyncio.create_task(
          self._batch_location_analysis(),
        )

    _LOGGER.info(
      "WalkManager initialized for %d dogs with optimizations",
      len(
        dog_ids,
      ),
    )

  async def async_update_gps_data(  # noqa: E111
    self,
    dog_id: str,
    latitude: float,
    longitude: float,
    *,
    accuracy: float | None = None,
    altitude: float | None = None,
    speed: float | None = None,
    heading: float | None = None,
    source: str = "unknown",
    battery_level: int | None = None,
    signal_strength: int | None = None,
    timestamp: datetime | None = None,
  ) -> bool:
    """Update GPS data with optimized validation and caching.

    OPTIMIZE: Enhanced with async validation, caching, and batch processing.

    Args:
        dog_id: Dog identifier.
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        accuracy: GPS accuracy in meters.
        altitude: Altitude in meters when available.
        speed: Speed in km/h.
        heading: Heading/direction in degrees.
        source: GPS data source.
        battery_level: GPS device battery level (0-100).
        signal_strength: GPS signal strength (0-100).

    Returns:
        True if update successful
    """
    # OPTIMIZE: Fast coordinate validation
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
      _LOGGER.warning(  # noqa: E111
        "Invalid GPS coordinates for %s: %f, %f",
        dog_id,
        latitude,
        longitude,
      )
      return False  # noqa: E111

    async with self._data_lock:
      if dog_id not in self._gps_data:  # noqa: E111
        _LOGGER.warning(
          "Dog %s not initialized for GPS tracking",
          dog_id,
        )
        return False

      now = timestamp or dt_util.now()  # noqa: E111
      old_location: tuple[float, float] | None = None  # noqa: E111

      # OPTIMIZE: Get previous location from cache for better performance  # noqa: E114
      cached_location = self._gps_cache.get_location(dog_id)  # noqa: E111
      if cached_location is not None:  # noqa: E111
        cached_latitude, cached_longitude, _cached_timestamp = cached_location
        old_location = (cached_latitude, cached_longitude)
        self._performance_metrics["cache_hits"] += 1
      else:  # noqa: E111
        previous_latitude = self._gps_data[dog_id]["latitude"]
        previous_longitude = self._gps_data[dog_id]["longitude"]
        if previous_latitude is not None and previous_longitude is not None:
          old_location = (previous_latitude, previous_longitude)  # noqa: E111
          self._performance_metrics["cache_misses"] += 1  # noqa: E111

      # Update GPS data with enhanced fields  # noqa: E114
      self._gps_data[dog_id].update(  # noqa: E111
        {
          "latitude": latitude,
          "longitude": longitude,
          "accuracy": accuracy,
          "altitude": altitude,
          "speed": speed,
          "heading": heading,
          "last_seen": now.isoformat(),
          "source": source,
          "available": True,
          "battery_level": battery_level,
          "signal_strength": signal_strength,
        },
      )

      # OPTIMIZE: Update cache with new location  # noqa: E114
      self._gps_cache.set_location(dog_id, latitude, longitude, now)  # noqa: E111

      # OPTIMIZE: Queue location analysis for batch processing  # noqa: E114
      self._location_analysis_queue[dog_id].append(  # noqa: E111
        (latitude, longitude, now),
      )

      # OPTIMIZE: Process walk detection with performance tracking  # noqa: E114
      if old_location and self._walk_detection_enabled:  # noqa: E111
        await self._process_walk_detection_optimized(
          dog_id,
          old_location,
          (latitude, longitude),
          speed,
        )

      # Update performance metrics  # noqa: E114
      self._performance_metrics["gps_updates"] += 1  # noqa: E111

      _LOGGER.debug(  # noqa: E111
        "Updated GPS data for %s: %f, %f (accuracy: %s, battery: %s%%)",
        dog_id,
        latitude,
        longitude,
        accuracy,
        battery_level,
      )
      return True  # noqa: E111

  async def async_add_gps_point(  # noqa: E111
    self,
    *,
    dog_id: str,
    latitude: float,
    longitude: float,
    altitude: float | None = None,
    accuracy: float | None = None,
    timestamp: datetime | None = None,
  ) -> bool:
    """Add a GPS point provided by the ``pawcontrol.add_gps_point`` service.

    Args:
        dog_id: Identifier of the dog for which the position was reported.
        latitude: Latitude coordinate from the service call.
        longitude: Longitude coordinate from the service call.
        altitude: Optional altitude in meters above sea level.
        accuracy: Optional horizontal accuracy value in meters.

    Returns:
        ``True`` when the GPS payload is accepted and stored.
    """

    return await self.async_update_gps_data(
      dog_id=dog_id,
      latitude=latitude,
      longitude=longitude,
      accuracy=accuracy,
      altitude=altitude,
      source="service_call",
      timestamp=timestamp,
    )

  async def _batch_location_analysis(self) -> None:  # noqa: E111
    """Background task for batch location analysis.

    OPTIMIZE: Process location analysis in batches for better performance.
    """
    while True:
      try:  # noqa: E111
        await asyncio.sleep(10)  # Process every 10 seconds

        async with self._data_lock:
          for dog_id, queue in self._location_analysis_queue.items():  # noqa: E111
            if len(queue) >= LOCATION_ANALYSIS_BATCH_SIZE:
              # Process batch  # noqa: E114
              batch = queue[:LOCATION_ANALYSIS_BATCH_SIZE]  # noqa: E111
              del queue[:LOCATION_ANALYSIS_BATCH_SIZE]  # noqa: E111

              # Analyze latest location in batch  # noqa: E114
              if batch:  # noqa: E111
                latest_lat, latest_lon, _latest_time = batch[-1]
                await self._update_location_analysis(
                  dog_id,
                  latest_lat,
                  latest_lon,
                )

      except asyncio.CancelledError:  # noqa: E111
        break
      except Exception as err:  # noqa: E111
        _LOGGER.error("Batch location analysis error: %s", err)

  async def async_start_walk(  # noqa: E111
    self,
    dog_id: str,
    walk_type: str = "manual",
    *,
    walker: str | None = None,
    leash_used: bool | None = None,
    weather: WeatherCondition | str | None = None,
    track_route: bool = True,
    safety_alerts: bool = True,
    detection_confidence: float | None = None,
    door_sensor: str | None = None,
    detection_metadata: (
      WalkDetectionMetadata | WalkDetectionMutableMetadata | None
    ) = None,
  ) -> str | None:
    """Start a walk with optimized data structure.

    OPTIMIZE: Enhanced with better initial data structure and validation.

    Args:
        dog_id: Dog identifier
        walk_type: Type of walk (manual, auto_detected)
        detection_confidence: Normalised confidence score for automatic detection
        door_sensor: Entity ID of the triggering door sensor when available
        detection_metadata: Additional detection metadata forwarded by callers

    Returns:
        Walk ID if successful, None otherwise
    """
    async with self._data_lock:
      if dog_id not in self._walk_data:  # noqa: E111
        _LOGGER.warning(
          "Dog %s not initialized for walk tracking",
          dog_id,
        )
        raise KeyError(dog_id)

      if dog_id in self._current_walks:  # noqa: E111
        _LOGGER.info(
          "Walk already in progress for %s - ending existing session",
          dog_id,
        )
        await self._finalize_walk_locked(dog_id)

      now = dt_util.utcnow()  # noqa: E111
      counter = self._session_counters.get(dog_id, 0) + 1  # noqa: E111
      self._session_counters[dog_id] = counter  # noqa: E111
      walk_id = f"{dog_id}_{int(now.timestamp())}_{counter}"  # noqa: E111

      weather_condition: WeatherCondition | None = None  # noqa: E111
      if isinstance(weather, WeatherCondition):  # noqa: E111
        weather_condition = weather
      elif isinstance(weather, str):  # noqa: E111
        try:
          weather_condition = WeatherCondition(weather)  # noqa: E111
        except ValueError:
          _LOGGER.warning(  # noqa: E111
            "Ignoring unknown weather condition '%s' for %s",
            weather,
            dog_id,
          )

      leash_flag = True if leash_used is None else bool(leash_used)  # noqa: E111

      confidence_value: float | None = None  # noqa: E111
      if detection_confidence is not None:  # noqa: E111
        try:
          confidence_value = max(  # noqa: E111
            0.0,
            min(float(detection_confidence), 1.0),
          )
        except ValueError:
          confidence_value = None  # noqa: E111
        except TypeError:
          confidence_value = None  # noqa: E111

      detection_payload: WalkDetectionMutableMetadata | None = None  # noqa: E111
      if detection_metadata:  # noqa: E111
        try:
          detection_payload = cast(  # noqa: E111
            WalkDetectionMutableMetadata,
            {
              str(key): cast(JSONValue, value)
              for key, value in dict(detection_metadata).items()
            },
          )
        except Exception:  # pragma: no cover - defensive
          detection_payload = None  # noqa: E111

      # OPTIMIZE: Get current location from cache first  # noqa: E114
      start_location = None  # noqa: E111
      cached_location = self._gps_cache.get_location(dog_id)  # noqa: E111
      if cached_location is not None:  # noqa: E111
        start_location = cast(
          WalkLocationSnapshot,
          {
            "latitude": cached_location[0],
            "longitude": cached_location[1],
            "accuracy": self._gps_data[dog_id].get("accuracy"),
            "timestamp": cached_location[2].isoformat(),
          },
        )
      elif dog_id in self._gps_data and self._gps_data[dog_id]["available"]:  # noqa: E111
        start_location = cast(
          WalkLocationSnapshot,
          {
            "latitude": self._gps_data[dog_id]["latitude"],
            "longitude": self._gps_data[dog_id]["longitude"],
            "accuracy": self._gps_data[dog_id]["accuracy"],
            "timestamp": now.isoformat(),
          },
        )

      # OPTIMIZE: Pre-allocate path with capacity limit  # noqa: E114
      session = WalkSession(  # noqa: E111
        walk_id=walk_id,
        dog_id=dog_id,
        walk_type=walk_type,
        start_time=now,
        walker=walker,
        leash_used=leash_flag,
        weather=weather_condition,
        track_route=track_route,
        safety_alerts=safety_alerts,
        start_location=start_location,
        detection_confidence=confidence_value,
        door_sensor=door_sensor,
        detection_metadata=detection_payload,
      )

      walk_data: WalkSessionSnapshot = session.as_dict()  # noqa: E111
      walk_data["path_optimization_applied"] = False  # noqa: E111
      walk_data["track_route"] = track_route  # noqa: E111
      walk_data["safety_alerts"] = safety_alerts  # noqa: E111
      if confidence_value is not None:  # noqa: E111
        walk_data["detection_confidence"] = confidence_value
      if door_sensor is not None:  # noqa: E111
        walk_data["door_sensor"] = door_sensor
      if detection_payload is not None:  # noqa: E111
        walk_data["detection_metadata"] = detection_payload

      self._current_walks[dog_id] = walk_data  # noqa: E111

      # Update walk status  # noqa: E114
      self._walk_data[dog_id]["walk_in_progress"] = True  # noqa: E111
      self._walk_data[dog_id]["current_walk"] = walk_data  # noqa: E111
      self._update_dog_container(dog_id)  # noqa: E111
      self._dogs[dog_id]["active_walk"] = walk_data  # noqa: E111

      _LOGGER.info(  # noqa: E111
        "Started %s walk for %s (ID: %s, walker: %s, weather: %s, leash_used: %s)",
        walk_type,
        dog_id,
        walk_id,
        walker or "unknown",
        weather_condition.value if weather_condition else "unspecified",
        "yes" if leash_flag else "no",
      )
      return walk_id  # noqa: E111

  async def _finalize_walk_locked(  # noqa: E111
    self,
    dog_id: str,
    *,
    notes: str | None = None,
    dog_weight_kg: float | None = None,
    save_route: bool = True,
  ) -> WalkSessionSnapshot | None:
    """Finalize an active walk while the data lock is held."""

    if dog_id not in self._current_walks:
      _LOGGER.warning("No walk in progress for %s", dog_id)  # noqa: E111
      return None  # noqa: E111

    now = dt_util.utcnow()
    walk_data = self._current_walks[dog_id]

    if notes is not None:
      walk_data["notes"] = notes  # noqa: E111
    if dog_weight_kg is not None:
      walk_data["dog_weight_kg"] = dog_weight_kg  # noqa: E111

    walk_data["save_route"] = save_route

    # OPTIMIZE: Get end location from cache if available
    end_location = None
    cached_location = self._gps_cache.get_location(dog_id)
    if cached_location is not None:
      end_location = cast(  # noqa: E111
        WalkLocationSnapshot,
        {
          "latitude": cached_location[0],
          "longitude": cached_location[1],
          "accuracy": self._gps_data[dog_id].get("accuracy"),
          "timestamp": cached_location[2].isoformat(),
        },
      )
    elif dog_id in self._gps_data and self._gps_data[dog_id]["available"]:
      end_location = cast(  # noqa: E111
        WalkLocationSnapshot,
        {
          "latitude": self._gps_data[dog_id]["latitude"],
          "longitude": self._gps_data[dog_id]["longitude"],
          "accuracy": self._gps_data[dog_id]["accuracy"],
          "timestamp": now.isoformat(),
        },
      )

    # Calculate walk statistics
    start_time_raw = walk_data.get("start_time")
    start_time = (
      start_time_raw
      if isinstance(start_time_raw, datetime)
      else dt_util.parse_datetime(start_time_raw)
    )
    if start_time is None:
      start_time = now  # noqa: E111
    else:
      if start_time.tzinfo is None:  # noqa: E111
        start_time = start_time.replace(tzinfo=UTC)
      start_time = dt_util.as_utc(start_time)  # noqa: E111
    duration = max(0.0, (now - start_time).total_seconds())

    # Update walk data
    walk_data.update(
      {
        "end_time": now.isoformat(),
        "duration": duration,
        "end_location": end_location,
        "status": "completed",
      },
    )

    # OPTIMIZE: Calculate additional statistics with caching
    if walk_data.get("path"):
      # Optimize path if too many points  # noqa: E114
      if len(walk_data["path"]) > PATH_POINT_LIMIT:  # noqa: E111
        walk_data["path"] = self._optimize_path(walk_data["path"])
        walk_data["path_optimization_applied"] = True

      walk_data["distance"] = await self._calculate_total_distance_optimized(  # noqa: E111
        walk_data["path"],
      )
      walk_data["average_speed"] = self._calculate_average_speed(  # noqa: E111
        walk_data,
      )
      walk_data["max_speed"] = self._calculate_max_speed(  # noqa: E111
        walk_data["path"],
      )
      walk_data["elevation_gain"] = self._calculate_elevation_gain(  # noqa: E111
        walk_data["path"],
      )
      walk_data["calories_burned"] = self._estimate_calories_burned(  # noqa: E111
        dog_id,
        walk_data,
      )

    # Update daily statistics with batch optimization
    await self._update_daily_walk_stats_optimized(dog_id, walk_data)

    # OPTIMIZE: Store in history with size limit
    self._walk_history[dog_id].append(
      cast(WalkSessionSnapshot, normalize_value(dict(walk_data))),
    )

    # Keep only last 100 walks to prevent memory leaks
    if len(self._walk_history[dog_id]) > 100:
      self._walk_history[dog_id] = self._walk_history[dog_id][-100:]  # noqa: E111
      self._performance_metrics["memory_cleanups"] += 1  # noqa: E111

    # Clear current walk
    del self._current_walks[dog_id]
    self._walk_data[dog_id]["walk_in_progress"] = False
    self._walk_data[dog_id]["current_walk"] = None
    self._dogs[dog_id]["active_walk"] = None
    self._dogs[dog_id]["history"] = self._walk_history[dog_id]

    # Invalidate statistics cache
    self._invalidate_statistics_cache(dog_id)

    _LOGGER.info(
      "Completed walk for %s: %.1fm in %.0fs (path points: %d)",
      dog_id,
      walk_data["distance"],
      duration,
      len(walk_data.get("path", [])),
    )
    return walk_data

  async def async_end_walk(  # noqa: E111
    self,
    dog_id: str,
    *,
    notes: str | None = None,
    dog_weight_kg: float | None = None,
    save_route: bool = True,
  ) -> WalkSessionSnapshot | None:
    """End the current walk with optimized statistics calculation.

    OPTIMIZE: Enhanced with batch statistics calculation and path optimization.

    Args:
        dog_id: Dog identifier

    Returns:
        Completed walk data if successful, None otherwise
    """

    async with self._data_lock:
      return await self._finalize_walk_locked(  # noqa: E111
        dog_id,
        notes=notes,
        dog_weight_kg=dog_weight_kg,
        save_route=save_route,
      )

  def _optimize_path(self, path: list[WalkRoutePoint]) -> list[WalkRoutePoint]:  # noqa: E111
    """Optimize walk path by removing redundant points.

    OPTIMIZE: Reduce memory usage by removing points that don't add significant value.

    Args:
        path: Original path points

    Returns:
        Optimized path
    """
    if len(path) <= PATH_POINT_LIMIT:
      return path  # noqa: E111

    # Keep start and end points
    optimized = [path[0]]

    # Sample points at regular intervals
    interval = len(path) // (PATH_POINT_LIMIT - 2)
    optimized.extend(path[i] for i in range(interval, len(path) - 1, interval))

    # Always keep end point
    optimized.append(path[-1])

    _LOGGER.debug(
      "Optimized path: %d -> %d points",
      len(path),
      len(optimized),
    )

    return optimized

  async def _process_walk_detection_optimized(  # noqa: E111
    self,
    dog_id: str,
    old_location: tuple[float, float],
    new_location: tuple[float, float],
    speed: float | None,
  ) -> None:
    """Process automatic walk detection with optimization.

    OPTIMIZE: Enhanced with speed-based detection and reduced false positives.

    Args:
        dog_id: Dog identifier
        old_location: Previous GPS coordinates
        new_location: Current GPS coordinates
        speed: Current speed in km/h
    """
    # OPTIMIZE: Use cached distance calculation
    distance = self._gps_cache.calculate_distance_cached(
      old_location,
      new_location,
    )
    self._performance_metrics["distance_calculations"] += 1

    # OPTIMIZE: Enhanced walk detection logic
    speed_threshold_met = (speed or 0) > self._min_speed_threshold
    movement_threshold_met = distance > 10  # Moved more than 10 meters
    not_already_walking = dog_id not in self._current_walks

    # Check if movement indicates start of walk
    if movement_threshold_met and speed_threshold_met and not_already_walking:
      await self.async_start_walk(dog_id, "auto_detected")  # noqa: E111
      _LOGGER.debug(  # noqa: E111
        "Auto-detected walk start for %s: distance=%.1fm, speed=%.1fkm/h",
        dog_id,
        distance,
        speed or 0,
      )

    # OPTIMIZE: Add to walk path if walk in progress with point limits
    if dog_id in self._current_walks:
      current_walk = self._current_walks[dog_id]  # noqa: E111

      # Only add point if it's significant (distance > 5m or time > 30s since last point)  # noqa: E114, E501
      should_add_point = True  # noqa: E111
      if current_walk["path"]:  # noqa: E111
        last_point = current_walk["path"][-1]
        last_location = (
          last_point["latitude"],
          last_point["longitude"],
        )
        last_distance = self._gps_cache.calculate_distance_cached(
          last_location,
          new_location,
        )

        # Only add if moved significantly or time passed
        now = dt_util.now()
        last_time = dt_util.parse_datetime(last_point["timestamp"])
        time_diff = (now - last_time).total_seconds()

        should_add_point = last_distance > 5.0 or time_diff > 30

      if should_add_point and len(current_walk["path"]) < PATH_POINT_LIMIT:  # noqa: E111
        path_point = cast(
          WalkRoutePoint,
          {
            "latitude": new_location[0],
            "longitude": new_location[1],
            "timestamp": dt_util.now().isoformat(),
            "accuracy": self._gps_data[dog_id].get("accuracy"),
            "speed": speed,
            "altitude": self._gps_data[dog_id].get("altitude"),
          },
        )
        current_walk["path"].append(path_point)

  async def _calculate_total_distance_optimized(  # noqa: E111
    self,
    path: list[WalkRoutePoint],
  ) -> float:
    """Calculate total distance with caching optimization.

    OPTIMIZE: Batch distance calculations for better performance.

    Args:
        path: List of GPS path points

    Returns:
        Total distance in meters
    """
    if len(path) < 2:
      return 0.0  # noqa: E111

    total_distance = 0.0

    # OPTIMIZE: Batch process distance calculations
    for i in range(1, len(path)):
      point1 = (path[i - 1]["latitude"], path[i - 1]["longitude"])  # noqa: E111
      point2 = (path[i]["latitude"], path[i]["longitude"])  # noqa: E111
      total_distance += self._gps_cache.calculate_distance_cached(  # noqa: E111
        point1,
        point2,
      )
      self._performance_metrics["distance_calculations"] += 1  # noqa: E111

    return total_distance

  async def _update_daily_walk_stats_optimized(  # noqa: E111
    self,
    dog_id: str,
    walk_data: WalkSessionSnapshot,
  ) -> None:
    """Update daily walk statistics with optimized calculations.

    OPTIMIZE: Batch statistics updates and cache invalidation.

    Args:
        dog_id: Dog identifier
        walk_data: Completed walk data
    """
    # Update today's stats
    self._walk_data[dog_id]["walks_today"] += 1
    duration_value = float(walk_data.get("duration") or 0.0)
    distance_value = float(walk_data.get("distance") or 0.0)
    self._walk_data[dog_id]["total_duration_today"] += duration_value
    self._walk_data[dog_id]["total_distance_today"] += distance_value
    self._walk_data[dog_id]["last_walk"] = walk_data["start_time"]
    self._walk_data[dog_id]["last_walk_duration"] = duration_value
    self._walk_data[dog_id]["last_walk_distance"] = distance_value

    # OPTIMIZE: Batch calculate averages from recent walks
    recent_walks = self.get_walk_history(dog_id)
    recent_walks.insert(0, cast(WalkSessionSnapshot, dict(walk_data)))
    cutoff = dt_util.utcnow() - timedelta(days=7)

    def _parse_start(value: Any) -> datetime | None:
      if value is None:  # noqa: E111
        return None
      if isinstance(value, datetime):  # noqa: E111
        if value.tzinfo is None:
          value = value.replace(tzinfo=UTC)  # noqa: E111
        return dt_util.as_utc(value)
      parsed = dt_util.parse_datetime(value)  # noqa: E111
      if parsed is None:  # noqa: E111
        return None
      return dt_util.as_utc(parsed)  # noqa: E111

    recent_walks = [
      walk
      for walk in recent_walks
      if ((parsed := _parse_start(walk.get("start_time"))) and parsed >= cutoff)
    ]
    if recent_walks:
      durations = [  # noqa: E111
        float(w.get("duration") or 0.0)
        for w in recent_walks
        if w.get("duration") is not None
      ]
      distances = [  # noqa: E111
        float(w.get("distance") or 0.0)
        for w in recent_walks
        if w.get("distance") is not None
      ]

      if durations:  # noqa: E111
        self._walk_data[dog_id]["average_duration"] = sum(durations) / len(
          durations,
        )
      if distances:  # noqa: E111
        self._walk_data[dog_id]["average_distance"] = sum(distances) / len(
          distances,
        )

    # OPTIMIZE: Update weekly stats in single pass
    week_walks = recent_walks
    self._walk_data[dog_id]["weekly_walks"] = len(week_walks)
    self._walk_data[dog_id]["weekly_distance"] = sum(
      float(w.get("distance") or 0.0) for w in week_walks
    )

    # OPTIMIZE: Calculate walk streak efficiently
    self._walk_data[dog_id][
      "walk_streak"
    ] = await self._calculate_walk_streak_optimized(dog_id)

    # Update energy level based on recent activity
    self._update_energy_level(dog_id, walk_data)

  async def _calculate_walk_streak_optimized(self, dog_id: str) -> int:  # noqa: E111
    """Calculate walk streak with optimized algorithm.

    OPTIMIZE: More efficient streak calculation using binary search approach.

    Args:
        dog_id: Dog identifier

    Returns:
        Current walk streak in days
    """
    recent_walks = self.get_walk_history(dog_id)

    def _parse_start(value: Any) -> datetime | None:
      return (  # noqa: E111
        value
        if isinstance(
          value,
          datetime,
        )
        else dt_util.parse_datetime(value)
      )

    cutoff = dt_util.now() - timedelta(days=30)
    recent_walks = [
      walk
      for walk in recent_walks
      if ((parsed := _parse_start(walk.get("start_time"))) and parsed >= cutoff)
    ]
    if not recent_walks:
      return 0  # noqa: E111

    # Group walks by date
    walks_by_date: dict[str, int] = {}
    for walk in recent_walks:
      try:  # noqa: E111
        walk_time = _parse_start(walk["start_time"])
        if not walk_time:
          continue  # noqa: E111
        walk_date = walk_time.date()
        date_str = walk_date.isoformat()
        walks_by_date[date_str] = walks_by_date.get(date_str, 0) + 1
      except ValueError:  # noqa: E111
        continue
      except TypeError:  # noqa: E111
        continue

    # Calculate streak
    streak = 0
    current_date = dt_util.now().date()

    for _ in range(30):  # Check last 30 days
      date_str = current_date.isoformat()  # noqa: E111
      if date_str in walks_by_date:  # noqa: E111
        streak += 1
        current_date -= timedelta(days=1)
      else:  # noqa: E111
        break

    return streak

  def _update_energy_level(self, dog_id: str, walk_data: WalkSessionSnapshot) -> None:  # noqa: E111
    """Update dog's energy level based on walk activity.

    Args:
        dog_id: Dog identifier
        walk_data: Recent walk data
    """
    # Simple energy level calculation based on walk distance and duration
    distance = float(walk_data.get("distance") or 0.0)
    duration = float(walk_data.get("duration") or 0.0)

    if distance > 2000 or duration > 3600:  # Long walk (>2km or >1h)
      energy_level = "low"  # noqa: E111
    # Moderate walk (>1km or >30min)
    elif distance > 1000 or duration > 1800:
      energy_level = "medium"  # noqa: E111
    else:
      energy_level = "high"  # noqa: E111

    self._walk_data[dog_id]["energy_level"] = energy_level

  def _calculate_elevation_gain(self, path: list[WalkRoutePoint]) -> float:  # noqa: E111
    """Calculate total elevation gain from path.

    OPTIMIZE: New feature for comprehensive walk analysis.

    Args:
        path: List of GPS path points with altitude data

    Returns:
        Total elevation gain in meters
    """
    if len(path) < 2:
      return 0.0  # noqa: E111

    total_gain = 0.0
    last_altitude = None

    for point in path:
      altitude = point.get("altitude")  # noqa: E111
      if altitude is not None and last_altitude is not None:  # noqa: E111
        gain = altitude - last_altitude
        if gain > 0:  # Only count positive elevation changes
          total_gain += gain  # noqa: E111
      last_altitude = altitude  # noqa: E111

    return total_gain

  async def async_get_walk_data_cached(self, dog_id: str) -> WalkStatisticsSnapshot:  # noqa: E111
    """Get walk statistics with caching optimization.

    OPTIMIZE: Cache frequently accessed walk data for better performance.

    Args:
        dog_id: Dog identifier

    Returns:
        Walk statistics data
    """
    # Check cache first
    cache_key = f"walk_data_{dog_id}"
    if cache_key in self._statistics_cache:
      cached_data, cache_time = self._statistics_cache[cache_key]  # noqa: E111
      if (dt_util.now() - cache_time).total_seconds() < STATISTICS_CACHE_TTL:  # noqa: E111
        return cached_data

    # Calculate fresh data
    async with self._data_lock:
      if dog_id not in self._walk_data:  # noqa: E111
        return cast(WalkStatisticsSnapshot, {})

      data = cast(WalkStatisticsSnapshot, dict(self._walk_data[dog_id]))  # noqa: E111

      # Add current walk if in progress  # noqa: E114
      if dog_id in self._current_walks:  # noqa: E111
        current_walk = cast(
          WalkSessionSnapshot,
          dict(self._current_walks[dog_id]),
        )

        # Calculate current walk duration and distance
        if current_walk["path"]:
          current_walk[  # noqa: E111
            "current_distance"
          ] = await self._calculate_total_distance_optimized(
            current_walk["path"],
          )

        start_time = dt_util.parse_datetime(current_walk["start_time"])
        current_walk["current_duration"] = (dt_util.now() - start_time).total_seconds()

        data["current_walk"] = current_walk
        data["walk_in_progress"] = True
      else:  # noqa: E111
        data["walk_in_progress"] = False
        data["current_walk"] = None

      normalised = cast(WalkStatisticsSnapshot, normalize_value(data))  # noqa: E111

      # Cache result  # noqa: E114
      self._statistics_cache[cache_key] = (normalised, dt_util.now())  # noqa: E111
      return normalised  # noqa: E111

  def _invalidate_statistics_cache(self, dog_id: str) -> None:  # noqa: E111
    """Invalidate statistics cache for a dog.

    Args:
        dog_id: Dog identifier
    """
    cache_key = f"walk_data_{dog_id}"
    self._statistics_cache.pop(cache_key, None)

  async def async_get_performance_statistics(self) -> WalkPerformanceSnapshot:  # noqa: E111
    """Get performance statistics for the walk manager.

    OPTIMIZE: New method for monitoring performance and optimization effectiveness.

    Returns:
        Performance statistics
    """
    async with self._data_lock:
      total_dogs = len(self._walk_data)  # noqa: E111
      dogs_with_gps = sum(1 for gps in self._gps_data.values() if gps["available"])  # noqa: E111
      active_walks = len(self._current_walks)  # noqa: E111

      total_walks_today = sum(data["walks_today"] for data in self._walk_data.values())  # noqa: E111
      total_distance_today = sum(  # noqa: E111
        data["total_distance_today"] for data in self._walk_data.values()
      )

      # Cache statistics  # noqa: E114
      cache_stats = self._gps_cache.get_stats()  # noqa: E111

      performance_metrics = cast(  # noqa: E111
        WalkPerformanceCounters,
        dict(self._performance_metrics),
      )
      snapshot: WalkPerformanceSnapshot = {  # noqa: E111
        # Basic stats
        "total_dogs": total_dogs,
        "dogs_with_gps": dogs_with_gps,
        "active_walks": active_walks,
        "total_walks_today": total_walks_today,
        "total_distance_today": round(total_distance_today, 1),
        "walk_detection_enabled": self._walk_detection_enabled,
        # Performance metrics
        "performance_metrics": performance_metrics,
        "cache_stats": cache_stats,
        "statistics_cache_entries": len(self._statistics_cache),
        "location_analysis_queue_size": sum(
          len(queue) for queue in self._location_analysis_queue.values()
        ),
        # Memory usage
        "average_path_length": sum(
          len(walk["path"]) for walk in self._current_walks.values()
        )
        / max(len(self._current_walks), 1),
      }
      return snapshot  # noqa: E111

  # OPTIMIZE: Keep existing methods for compatibility but optimize internal calls  # noqa: E114, E501
  async def async_get_current_walk(self, dog_id: str) -> WalkSessionSnapshot | None:  # noqa: E111
    """Get current walk data for a dog."""
    async with self._data_lock:
      return (  # noqa: E111
        cast(WalkSessionSnapshot, dict(self._current_walks[dog_id]))
        if dog_id in self._current_walks
        else None
      )

  async def async_get_walk_data(self, dog_id: str) -> WalkStatisticsSnapshot:  # noqa: E111
    """Get walk statistics for a dog with caching."""
    return await self.async_get_walk_data_cached(dog_id)

  async def async_get_gps_data(self, dog_id: str) -> WalkGPSSnapshot:  # noqa: E111
    """Get GPS data for a dog."""
    async with self._data_lock:
      if dog_id not in self._gps_data:  # noqa: E111
        return cast(
          WalkGPSSnapshot,
          {
            "available": False,
            "zone": "unknown",
            "error": "Dog not initialized",
          },
        )

      return cast(WalkGPSSnapshot, dict(self._gps_data[dog_id]))  # noqa: E111

  async def async_get_walk_history(  # noqa: E111
    self,
    dog_id: str,
    days: int = 7,
  ) -> list[WalkSessionSnapshot]:
    """Get walk history for a dog."""
    async with self._data_lock:
      if dog_id not in self._walk_history:  # noqa: E111
        return []

      # Filter by date range  # noqa: E114
      cutoff = dt_util.now() - timedelta(days=days)  # noqa: E111
      recent_walks = []  # noqa: E111

      for walk in self._walk_history[dog_id]:  # noqa: E111
        try:
          start_time = dt_util.parse_datetime(walk["start_time"])  # noqa: E111
          if start_time and start_time >= cutoff:  # noqa: E111
            recent_walks.append(
              cast(WalkSessionSnapshot, dict(walk)),
            )
        except ValueError:
          continue  # noqa: E111
        except TypeError:
          continue  # noqa: E111

      ordered = sorted(  # noqa: E111
        recent_walks,
        key=lambda w: w["start_time"],
        reverse=True,
      )
      return cast(list[WalkSessionSnapshot], normalize_value(ordered))  # noqa: E111

  def get_walk_history(  # noqa: E111
    self,
    dog_id: str,
    limit: int | None = None,
  ) -> list[WalkSessionSnapshot]:
    """Return stored walk history synchronously for testing helpers."""

    history = self._walk_history.get(dog_id, [])
    if not history:
      return []  # noqa: E111

    history_slice = history[-limit:] if limit is not None else history[:]

    history_payload = [
      cast(WalkSessionSnapshot, dict(walk)) for walk in reversed(history_slice)
    ]
    return cast(list[WalkSessionSnapshot], normalize_value(history_payload))

  def get_last_walk_info(self, dog_id: str) -> WalkSessionSnapshot | None:  # noqa: E111
    """Return the most recent walk if available."""

    history = self.get_walk_history(dog_id, limit=1)
    return history[0] if history else None

  def get_active_walk_info(self, dog_id: str) -> WalkSessionSnapshot | None:  # noqa: E111
    """Return details about the active walk."""

    container = self._dogs.get(dog_id)
    if container is None:
      return None  # noqa: E111

    active_walk = container["active_walk"]
    if not active_walk:
      return None  # noqa: E111

    info = cast(WalkSessionSnapshot, dict(active_walk))
    start_time_raw = cast(str | datetime | None, info.get("start_time"))
    start_time = (
      start_time_raw
      if isinstance(start_time_raw, datetime)
      else dt_util.parse_datetime(start_time_raw)
    )
    if start_time:
      elapsed = (dt_util.now() - start_time).total_seconds()  # noqa: E111
      if elapsed >= 0:  # noqa: E111
        info["elapsed_duration"] = elapsed

    return cast(WalkSessionSnapshot, normalize_value(info))

  def get_walk_data(self, dog_id: str) -> WalkOverviewSnapshot | None:  # noqa: E111
    """Return a snapshot of walk data for a dog."""

    if dog_id not in self._dogs:
      return None  # noqa: E111

    active_walk = self._dogs[dog_id].get("active_walk")
    active_snapshot = (
      cast(WalkSessionSnapshot, dict(active_walk))
      if isinstance(active_walk, dict)
      else cast(WalkSessionSnapshot | None, active_walk)
    )

    stats = self._walk_data.get(dog_id)
    stats_snapshot = (
      cast(WalkStatisticsSnapshot, dict(stats))
      if stats is not None
      else cast(WalkStatisticsSnapshot, {})
    )

    gps = self._gps_data.get(dog_id)
    gps_snapshot = (
      cast(WalkGPSSnapshot, dict(gps))
      if gps is not None
      else cast(WalkGPSSnapshot, {"available": False, "zone": "unknown"})
    )

    overview: WalkOverviewSnapshot = {
      "active_walk": active_snapshot,
      "history": self.get_walk_history(dog_id),
      "stats": stats_snapshot,
      "statistics": cast(WalkStatisticsSnapshot, dict(stats_snapshot)),
      "gps": gps_snapshot,
    }
    return cast(WalkOverviewSnapshot, normalize_value(overview))

  def get_daily_walk_stats(self, dog_id: str) -> WalkDailyStatistics | None:  # noqa: E111
    """Return aggregated statistics for the current day."""

    stats = self._walk_data.get(dog_id)
    if stats is None:
      return None  # noqa: E111

    daily_stats: WalkDailyStatistics = {
      "total_walks_today": stats["walks_today"],
      "total_duration_today": stats["total_duration_today"],
      "total_distance_today": stats["total_distance_today"],
      "average_duration": (
        cast(float | None, stats["average_duration"])
        if "average_duration" in stats
        else None
      ),
      "average_distance": (
        cast(float | None, stats["average_distance"])
        if "average_distance" in stats
        else None
      ),
      "energy_level": stats["energy_level"],
    }
    return daily_stats

  def get_weekly_walk_stats(self, dog_id: str) -> WalkWeeklyStatistics | None:  # noqa: E111
    """Return aggregated statistics for the current week."""

    stats = self._walk_data.get(dog_id)
    if stats is None:
      return None  # noqa: E111

    weekly_stats: WalkWeeklyStatistics = {
      "total_walks_this_week": stats["weekly_walks"],
      "total_distance_this_week": stats["weekly_distance"],
      "walk_streak": stats["walk_streak"],
    }
    return weekly_stats

  async def _update_location_analysis(  # noqa: E111
    self,
    dog_id: str,
    latitude: float,
    longitude: float,
  ) -> None:
    """Update location-based analysis with caching.

    OPTIMIZE: Enhanced with zone caching and reduced calculations.

    Args:
        dog_id: Dog identifier
        latitude: Current latitude
        longitude: Current longitude
    """
    # Check zone cache first
    now = dt_util.now()
    if dog_id in self._zone_cache:
      zone, cache_time = self._zone_cache[dog_id]  # noqa: E111
      # Use cached zone if less than 5 minutes old  # noqa: E114
      if (now - cache_time).total_seconds() < 300:  # noqa: E111
        self._gps_data[dog_id]["zone"] = zone
        return

    # Calculate distance from home (placeholder - would need home coordinates)
    distance_from_home = 0.0  # Would get from Home Assistant

    # Determine zone
    if distance_from_home < 50:
      zone = "home"  # noqa: E111
    elif distance_from_home < 200:
      zone = "neighborhood"  # noqa: E111
    else:
      zone = "away"  # noqa: E111

    # Update GPS data and cache
    self._gps_data[dog_id]["distance_from_home"] = distance_from_home
    self._gps_data[dog_id]["zone"] = zone
    self._zone_cache[dog_id] = (zone, now)

  # Keep existing utility methods  # noqa: E114
  def _calculate_average_speed(self, walk_data: WalkSessionSnapshot) -> float | None:  # noqa: E111
    """Calculate average speed for a walk."""

    duration_raw = walk_data.get("duration")
    if not is_number(duration_raw):
      return None  # noqa: E111

    duration_value: Number = duration_raw
    duration_seconds = float(duration_value)
    if duration_seconds <= 0.0:
      return None  # noqa: E111

    distance_raw = walk_data.get("distance")
    if not is_number(distance_raw):
      return None  # noqa: E111

    distance_value: Number = distance_raw
    distance_meters = float(distance_value)
    if distance_meters <= 0.0:
      return None  # noqa: E111

    distance_km = distance_meters / 1000.0
    duration_hours = duration_seconds / 3600.0
    if duration_hours <= 0.0:
      return None  # noqa: E111

    return distance_km / duration_hours

  def _calculate_max_speed(self, path: list[WalkRoutePoint]) -> float | None:  # noqa: E111
    """Calculate maximum speed from path."""
    speeds: list[float] = []
    for point in path:
      speed = point.get("speed")  # noqa: E111
      if not is_number(speed):  # noqa: E111
        continue

      speed_value: Number = speed  # noqa: E111
      speeds.append(float(speed_value))  # noqa: E111
    return max(speeds) if speeds else None

  def _estimate_calories_burned(  # noqa: E111
    self,
    dog_id: str,
    walk_data: WalkSessionSnapshot,
  ) -> float | None:
    """Estimate calories burned during walk."""
    duration_raw = walk_data.get("duration")
    if not is_number(duration_raw):
      return None  # noqa: E111

    duration_value: Number = duration_raw
    duration_seconds = float(duration_value)
    if duration_seconds <= 0.0:
      return None  # noqa: E111

    # Enhanced calorie estimation with elevation
    weight = walk_data.get("dog_weight_kg")
    estimated_weight = 20.0
    if is_number(weight):
      weight_value: Number = weight  # noqa: E111
      coerced_weight = float(weight_value)  # noqa: E111
      if coerced_weight > 0:  # noqa: E111
        estimated_weight = coerced_weight
    duration_minutes = duration_seconds / 60.0
    base_calories = estimated_weight * duration_minutes * 0.5

    # Add elevation bonus
    elevation_gain_raw = walk_data.get("elevation_gain", 0)
    elevation_gain = 0.0
    if is_number(elevation_gain_raw):
      elevation_gain_value: Number = elevation_gain_raw  # noqa: E111
      elevation_gain = float(elevation_gain_value)  # noqa: E111
    elevation_bonus = elevation_gain * 0.1  # 0.1 cal per meter elevation gain

    return base_calories + elevation_bonus

  async def async_get_statistics(self) -> WalkPerformanceSnapshot:  # noqa: E111
    """Get walk manager statistics."""
    return await self.async_get_performance_statistics()

  async def async_cleanup(self) -> None:  # noqa: E111
    """Clean up resources with enhanced cleanup."""
    # Cancel batch analysis task
    if self._batch_analysis_task:
      self._batch_analysis_task.cancel()  # noqa: E111
      with contextlib.suppress(asyncio.CancelledError):  # noqa: E111
        await self._batch_analysis_task

    async with self._data_lock:
      self._walk_data.clear()  # noqa: E111
      self._gps_data.clear()  # noqa: E111
      self._current_walks.clear()  # noqa: E111
      self._walk_history.clear()  # noqa: E111
      self._location_analysis_queue.clear()  # noqa: E111
      self._statistics_cache.clear()  # noqa: E111
      self._dogs.clear()  # noqa: E111
      self._session_counters.clear()  # noqa: E111

      # Clear caches  # noqa: E114
      self._gps_cache.clear()  # noqa: E111
      self._zone_cache.clear()  # noqa: E111

    _LOGGER.debug("WalkManager cleanup completed with optimizations")

  async def async_export_routes(  # noqa: E111
    self,
    dog_id: str,
    *,
    format: WalkRouteExportFormat = "gpx",
    last_n_walks: int = 1,
  ) -> WalkRouteExportPayload | None:
    """Export walk routes in specified format with enhanced validation.

    OPTIMIZED: Full GPX 1.1 compliance, robust error handling, comprehensive metadata.

    Args:
        dog_id: Dog identifier
        format: Export format (gpx, json, csv)
        last_n_walks: Number of recent walks to export

    Returns:
        Export data with file paths and metadata, or None if no walks found
    """
    try:
      async with self._data_lock:  # noqa: E111
        if dog_id not in self._walk_history:
          _LOGGER.warning("No walk history found for %s", dog_id)  # noqa: E111
          return None  # noqa: E111

        # Get recent walks with routes - validate data
        recent_walks = []
        for walk in self._walk_history[dog_id][-last_n_walks:]:
          if (  # noqa: E111
            walk["path"] and walk["status"] == "completed" and len(walk["path"]) >= 2
          ):  # At least 2 points for valid route
            # Validate route data integrity
            valid_path = self._validate_route_data(walk["path"])
            if valid_path:
              walk_copy = cast(WalkSessionSnapshot, dict(walk))  # noqa: E111
              walk_copy["path"] = valid_path  # noqa: E111
              recent_walks.append(walk_copy)  # noqa: E111

        if not recent_walks:
          _LOGGER.warning(  # noqa: E111
            "No valid walks with routes found for %s",
            dog_id,
          )
          return None  # noqa: E111

        # Calculate route statistics
        total_distance = 0.0
        total_duration = 0.0
        for walk_snapshot in recent_walks:
          distance_raw = walk_snapshot.get("distance")  # noqa: E111
          if is_number(distance_raw):  # noqa: E111
            distance_value: Number = distance_raw
            total_distance += float(distance_value)
          duration_raw = walk_snapshot.get("duration")  # noqa: E111
          if is_number(duration_raw):  # noqa: E111
            duration_value: Number = duration_raw
            total_duration += float(duration_value)
        total_points = sum(len(walk["path"]) for walk in recent_walks)

        serialised_walks = cast(
          list[JSONMutableMapping],
          normalize_value(recent_walks),
        )

        export_data: WalkRouteExportPayload = {
          "dog_id": dog_id,
          "export_timestamp": dt_util.now().isoformat(),
          "format": format,
          "walks_count": len(recent_walks),
          "total_distance_meters": round(total_distance, 2),
          "total_duration_seconds": round(total_duration, 2),
          "total_gps_points": total_points,
          "walks": serialised_walks,
          "export_metadata": {
            "creator": GPX_CREATOR,
            "version": GPX_VERSION,
            "generated_by": "PawControl WalkManager",
            "bounds": self._calculate_route_bounds(recent_walks),
          },
        }

        # Generate format-specific data with enhanced error handling
        if format == "gpx":
          try:  # noqa: E111
            export_data["gpx_data"] = self._generate_enhanced_gpx_data(
              recent_walks,
              dog_id,
            )
            export_data["file_extension"] = ".gpx"
            export_data["mime_type"] = "application/gpx+xml"
          except Exception as err:  # noqa: E111
            _LOGGER.error(
              "GPX generation failed for %s: %s",
              dog_id,
              err,
            )
            self._performance_metrics["export_errors"] += 1
            return None

        elif format == "json":
          try:  # noqa: E111
            export_data["json_data"] = json.dumps(
              serialised_walks,
              indent=2,
              ensure_ascii=False,
            )
            export_data["file_extension"] = ".json"
            export_data["mime_type"] = "application/json"
          except Exception as err:  # noqa: E111
            _LOGGER.error(
              "JSON generation failed for %s: %s",
              dog_id,
              err,
            )
            self._performance_metrics["export_errors"] += 1
            return None

        elif format == "csv":
          try:  # noqa: E111
            export_data["csv_data"] = self._generate_enhanced_csv_data(
              recent_walks,
            )
            export_data["file_extension"] = ".csv"
            export_data["mime_type"] = "text/csv"
          except Exception as err:  # noqa: E111
            _LOGGER.error(
              "CSV generation failed for %s: %s",
              dog_id,
              err,
            )
            self._performance_metrics["export_errors"] += 1
            return None
        else:
          _LOGGER.error("Unsupported export format: %s", format)  # noqa: E111
          return None  # noqa: E111

        # Update performance metrics
        self._performance_metrics["gpx_exports"] += 1

        _LOGGER.info(
          "Successfully exported %d route(s) for %s in %s format (%.1fm, %d points)",
          len(recent_walks),
          dog_id,
          format,
          total_distance,
          total_points,
        )

        return export_data

    except Exception as err:
      _LOGGER.error("Route export failed for %s: %s", dog_id, err)  # noqa: E111
      self._performance_metrics["export_errors"] += 1  # noqa: E111
      return None  # noqa: E111

  def _validate_route_data(  # noqa: E111
    self,
    path: list[WalkRoutePoint],
  ) -> list[WalkRoutePoint] | None:
    """Validate and clean route data for export.

    Args:
        path: Raw GPS path data

    Returns:
        Validated path data or None if invalid
    """
    if not path or len(path) < 2:
      return None  # noqa: E111

    validated_path: list[WalkRoutePoint] = []

    for point in path:
      # Validate required GPS data  # noqa: E114
      lat = point.get("latitude")  # noqa: E111
      lon = point.get("longitude")  # noqa: E111
      timestamp = point.get("timestamp")  # noqa: E111

      if (  # noqa: E111
        lat is None
        or lon is None
        or timestamp is None
        or not (-90 <= lat <= 90)
        or not (-180 <= lon <= 180)
      ):
        continue  # Skip invalid points

      # Create validated point with standardized fields  # noqa: E114
      validated_point = cast(  # noqa: E111
        WalkRoutePoint,
        {
          "latitude": float(lat),
          "longitude": float(lon),
          "timestamp": timestamp,
          "accuracy": point.get("accuracy"),
          "speed": point.get("speed"),
          "altitude": point.get("altitude"),
        },
      )

      validated_path.append(validated_point)  # noqa: E111

    # Return None if too few valid points remain
    return validated_path if len(validated_path) >= 2 else None

  def _calculate_route_bounds(  # noqa: E111
    self,
    walks: list[WalkSessionSnapshot],
  ) -> WalkRouteBounds:
    """Calculate geographic bounds for all routes.

    Args:
        walks: List of walk data with paths

    Returns:
        Bounding box coordinates
    """
    if not walks:
      return {"min_lat": 0, "max_lat": 0, "min_lon": 0, "max_lon": 0}  # noqa: E111

    all_lats = []
    all_lons = []

    for walk in walks:
      for point in walk.get("path", []):  # noqa: E111
        lat = point.get("latitude")
        lon = point.get("longitude")
        if lat is not None and lon is not None:
          all_lats.append(lat)  # noqa: E111
          all_lons.append(lon)  # noqa: E111

    if not all_lats or not all_lons:
      return {"min_lat": 0, "max_lat": 0, "min_lon": 0, "max_lon": 0}  # noqa: E111

    return {
      "min_lat": min(all_lats),
      "max_lat": max(all_lats),
      "min_lon": min(all_lons),
      "max_lon": max(all_lons),
    }

  def _generate_enhanced_gpx_data(  # noqa: E111
    self,
    walks: list[WalkSessionSnapshot],
    dog_id: str,
  ) -> str:
    """Generate GPX data with defensive error handling."""

    try:
      return self._render_enhanced_gpx_document(walks, dog_id)  # noqa: E111
    except Exception:  # pragma: no cover - defensive logging
      _LOGGER.exception("Enhanced GPX generation failed for %s", dog_id)  # noqa: E111
      raise  # noqa: E111

  def _render_enhanced_gpx_document(  # noqa: E111
    self,
    walks: list[WalkSessionSnapshot],
    dog_id: str,
  ) -> str:
    """Generate GPX 1.1 compliant data with full metadata."""

    def _escape(value: str) -> str:
      escaped = escape(value, quote=True)  # noqa: E111
      return escaped.replace("&#x27;", "&apos;")  # noqa: E111

    def _format_attrs(attrs: GPXAttributeMap) -> str:
      parts: list[str] = []  # noqa: E111
      for key, raw_value in attrs.items():  # noqa: E111
        if raw_value is None:
          continue  # noqa: E111
        parts.append(f'{key}="{_escape(str(raw_value))}"')
      return (" " + " ".join(parts)) if parts else ""  # noqa: E111

    def _append(level: int, text: str) -> None:
      lines.append(f"{'  ' * level}{text}" if level > 0 else text)  # noqa: E111

    def _text_element(level: int, tag: str, value: str) -> None:
      _append(level, f"<{tag}>{_escape(value)}</{tag}>")  # noqa: E111

    def _open_tag(
      level: int,
      tag: str,
      attrs: GPXAttributeMap | None = None,
    ) -> None:
      _append(level, f"<{tag}{_format_attrs(attrs or {})}>")  # noqa: E111

    def _close_tag(level: int, tag: str) -> None:
      _append(level, f"</{tag}>")  # noqa: E111

    lines: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']

    gpx_attrs = {
      "version": GPX_VERSION,
      "creator": GPX_CREATOR,
      "xmlns": GPX_NAMESPACE,
      "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
      "xsi:schemaLocation": GPX_SCHEMA_LOCATION,
    }
    _append(0, f"<gpx{_format_attrs(gpx_attrs)}>")

    _open_tag(1, "metadata")
    _text_element(2, "name", f"PawControl Routes - {dog_id}")
    _text_element(
      2,
      "desc",
      f"GPS tracks for {dog_id} exported from PawControl",
    )
    _open_tag(2, "author")
    _text_element(3, "name", "PawControl")
    _close_tag(2, "author")
    _text_element(2, "time", dt_util.now().strftime("%Y-%m-%dT%H:%M:%SZ"))

    bounds_data = self._calculate_route_bounds(walks)
    if any(bounds_data.values()):
      bounds_attrs = {  # noqa: E111
        "minlat": f"{bounds_data['min_lat']:.6f}",
        "minlon": f"{bounds_data['min_lon']:.6f}",
        "maxlat": f"{bounds_data['max_lat']:.6f}",
        "maxlon": f"{bounds_data['max_lon']:.6f}",
      }
      _append(2, f"<bounds{_format_attrs(bounds_attrs)} />")  # noqa: E111

    _close_tag(1, "metadata")

    for index, walk in enumerate(walks, 1):
      start_location = walk.get("start_location")  # noqa: E111
      end_location = walk.get("end_location")  # noqa: E111

      if (  # noqa: E111
        start_location
        and start_location.get("latitude")
        and start_location.get("longitude")
      ):
        start_attrs = {
          "lat": f"{start_location['latitude']:.6f}",
          "lon": f"{start_location['longitude']:.6f}",
        }
        _open_tag(1, "wpt", start_attrs)
        _text_element(2, "name", f"Walk {index} Start")
        _text_element(
          2,
          "desc",
          f"Start of walk {walk.get('walk_id', index)} for {dog_id}",
        )
        if start_location.get("timestamp"):
          _text_element(  # noqa: E111
            2,
            "time",
            self._format_gpx_timestamp(
              start_location["timestamp"],
            ),
          )
        _close_tag(1, "wpt")

      if (  # noqa: E111
        end_location and end_location.get("latitude") and end_location.get("longitude")
      ):
        end_attrs = {
          "lat": f"{end_location['latitude']:.6f}",
          "lon": f"{end_location['longitude']:.6f}",
        }
        _open_tag(1, "wpt", end_attrs)
        _text_element(2, "name", f"Walk {index} End")
        _text_element(
          2,
          "desc",
          f"End of walk {walk.get('walk_id', index)} for {dog_id}",
        )
        if end_location.get("timestamp"):
          _text_element(  # noqa: E111
            2,
            "time",
            self._format_gpx_timestamp(end_location["timestamp"]),
          )
        _close_tag(1, "wpt")

    for index, walk in enumerate(walks, 1):
      _open_tag(1, "trk")  # noqa: E111
      _text_element(2, "name", f"{dog_id} - Walk {index}")  # noqa: E111

      walk_info: list[str] = []  # noqa: E111
      if walk.get("distance"):  # noqa: E111
        walk_info.append(f"Distance: {walk['distance']:.1f}m")
      if walk.get("duration"):  # noqa: E111
        walk_info.append(f"Duration: {walk['duration']:.0f}s")
      if walk.get("walker"):  # noqa: E111
        walk_info.append(f"Walker: {walk['walker']}")
      if walk.get("weather"):  # noqa: E111
        walk_info.append(f"Weather: {walk['weather']}")

      description = (  # noqa: E111
        " | ".join(
          walk_info,
        )
        if walk_info
        else f"Walk for {dog_id}"
      )
      _text_element(2, "desc", description)  # noqa: E111
      _text_element(2, "type", walk.get("walk_type", "walk"))  # noqa: E111

      _open_tag(2, "trkseg")  # noqa: E111
      for point in walk.get("path", []):  # noqa: E111
        lat = point.get("latitude")
        lon = point.get("longitude")
        if lat is None or lon is None:
          continue  # noqa: E111

        trkpt_attrs = {
          "lat": f"{lat:.6f}",
          "lon": f"{lon:.6f}",
        }
        _open_tag(3, "trkpt", trkpt_attrs)

        altitude = point.get("altitude")
        if altitude is not None:
          _text_element(4, "ele", f"{altitude:.1f}")  # noqa: E111

        timestamp = point.get("timestamp")
        if timestamp:
          _text_element(  # noqa: E111
            4,
            "time",
            self._format_gpx_timestamp(timestamp),
          )

        speed = point.get("speed")
        if speed is not None:
          _text_element(4, "speed", f"{float(speed):.2f}")  # noqa: E111

        accuracy = point.get("accuracy")
        if accuracy is not None:
          _text_element(4, "hdop", f"{float(accuracy):.1f}")  # noqa: E111

        _close_tag(3, "trkpt")

      _close_tag(2, "trkseg")  # noqa: E111
      _close_tag(1, "trk")  # noqa: E111

    _close_tag(0, "gpx")

    return "\n".join(lines)

  def _format_gpx_timestamp(self, timestamp: str) -> str:  # noqa: E111
    """Format timestamp for GPX compliance.

    Args:
        timestamp: ISO timestamp string

    Returns:
        GPX-compliant timestamp string
    """
    try:
      # Parse the timestamp and ensure UTC format  # noqa: E114
      dt = dt_util.parse_datetime(timestamp)  # noqa: E111
      if dt is None:  # noqa: E111
        return dt_util.now().strftime("%Y-%m-%dT%H:%M:%SZ")

      # Convert to UTC if not already  # noqa: E114
      if dt.tzinfo is None:  # noqa: E111
        dt = dt.replace(tzinfo=dt_util.UTC)
      elif dt.tzinfo != dt_util.UTC:  # noqa: E111
        dt = dt.astimezone(dt_util.UTC)

      return dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E111
    except ValueError:
      # Fallback to current time if parsing fails  # noqa: E114
      return dt_util.now().strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E111
    except TypeError:
      # Fallback to current time if parsing fails  # noqa: E114
      return dt_util.now().strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E111

  def _generate_enhanced_csv_data(self, walks: list[WalkSessionSnapshot]) -> str:  # noqa: E111
    """Generate enhanced CSV format data with comprehensive metadata.

    Args:
        walks: List of walk data with paths

    Returns:
        Enhanced CSV formatted string with headers and metadata
    """
    csv_lines = [
      "# PawControl Route Export",
      f"# Generated: {dt_util.now().isoformat()}",
      f"# Total Walks: {len(walks)}",
      f"# Creator: {GPX_CREATOR}",
      "#",
      "walk_id,walk_number,timestamp,latitude,longitude,altitude,accuracy,speed,duration_from_start,distance_from_start,weather,walker,notes",
    ]

    for walk_num, walk in enumerate(walks, 1):
      walk_id = str(walk.get("walk_id", f"walk_{walk_num}"))  # noqa: E111
      weather = str(walk.get("weather", ""))  # noqa: E111
      walker = str(walk.get("walker", ""))  # noqa: E111
      raw_notes = walk.get("notes")  # noqa: E111
      notes = (  # noqa: E111
        raw_notes.replace(",", ";").replace("\n", " ")
        if isinstance(raw_notes, str)
        else ""
      )

      start_time = None  # noqa: E111
      if walk.get("start_time"):  # noqa: E111
        start_time = dt_util.parse_datetime(walk["start_time"])

      cumulative_distance = 0.0  # noqa: E111
      last_point = None  # noqa: E111

      for point in walk["path"]:  # noqa: E111
        lat = point.get("latitude")
        lon = point.get("longitude")
        alt = point.get("altitude", "")
        acc = point.get("accuracy", "")
        speed = point.get("speed", "")
        timestamp = point.get("timestamp", "")

        # Calculate duration from start
        duration_from_start = ""
        if timestamp and start_time:
          try:  # noqa: E111
            point_time = dt_util.parse_datetime(timestamp)
            if point_time:
              duration_from_start = (point_time - start_time).total_seconds()  # noqa: E111
          except ValueError:  # noqa: E111
            pass
          except TypeError:  # noqa: E111
            pass

        # Calculate cumulative distance
        if last_point and lat is not None and lon is not None:
          last_lat, last_lon = last_point  # noqa: E111
          point_distance = self._gps_cache.calculate_distance_cached(  # noqa: E111
            (last_lat, last_lon),
            (lat, lon),
          )
          cumulative_distance += point_distance  # noqa: E111

        csv_lines.append(
          f"{walk_id},{walk_num},{timestamp},{lat},{lon},{alt},{acc},{speed},{duration_from_start},{cumulative_distance:.1f},{weather},{walker},{notes}",
        )

        if lat is not None and lon is not None:
          last_point = (lat, lon)  # noqa: E111

    return "\n".join(csv_lines)

  async def async_configure_automatic_gps(  # noqa: E111
    self,
    dog_id: str,
    config: Mapping[str, JSONValue],
  ) -> bool:
    """Configure automatic GPS settings for a dog.

    Args:
        dog_id: Dog identifier
        config: GPS configuration dictionary

    Returns:
        True if configuration successful
    """
    try:
      async with self._data_lock:  # noqa: E111
        if dog_id not in self._gps_data:
          _LOGGER.warning(  # noqa: E111
            "Dog %s not initialized for GPS configuration",
            dog_id,
          )
          return False  # noqa: E111

        # Store GPS configuration
        automatic_config: JSONMutableMapping = {
          str(key): cast(JSONValue, value) for key, value in config.items()
        }
        self._gps_data[dog_id]["automatic_config"] = automatic_config

        # Update detection parameters based on config
        accuracy_value = config.get("gps_accuracy_threshold")
        if isinstance(accuracy_value, int | float):
          self._gps_data[dog_id]["accuracy_threshold"] = float(  # noqa: E111
            accuracy_value,
          )

        update_interval_value = config.get("update_interval_seconds")
        if isinstance(update_interval_value, int | float):
          self._gps_data[dog_id]["update_interval"] = update_interval_value  # noqa: E111

        _LOGGER.info(
          "Configured automatic GPS for %s: %s",
          dog_id,
          {
            k: v
            for k, v in config.items()
            if k
            not in [
              "safe_zone_radius",
            ]
          },
        )
        return True

    except Exception as err:
      _LOGGER.error(  # noqa: E111
        "Failed to configure automatic GPS for %s: %s",
        dog_id,
        err,
      )
      return False  # noqa: E111

  async def async_shutdown(self) -> None:  # noqa: E111
    """Enhanced shutdown method."""
    await self.async_cleanup()
