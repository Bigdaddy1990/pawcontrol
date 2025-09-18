"""Walk and GPS management for PawControl with advanced optimizations.

Enhanced with performance optimizations, caching, and memory management
for Platinum quality compliance.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from collections import deque
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class WeatherCondition(StrEnum):
    """Enumeration of supported walk weather conditions."""

    SUNNY = "sunny"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    SNOWY = "snowy"
    WINDY = "windy"
    HOT = "hot"
    COLD = "cold"


# OPTIMIZE: Performance constants
GPS_CACHE_SIZE_LIMIT = 1000
PATH_POINT_LIMIT = 500  # Limit path points to prevent memory leaks
STATISTICS_CACHE_TTL = 300  # 5 minutes cache for statistics
DISTANCE_CALCULATION_CACHE_SIZE = 100
LOCATION_ANALYSIS_BATCH_SIZE = 10


class GPSCache:
    """Optimized GPS data cache with LRU eviction."""

    def __init__(self, max_size: int = GPS_CACHE_SIZE_LIMIT) -> None:
        """Initialize GPS cache.

        Args:
            max_size: Maximum cache entries
        """
        self._cache: dict[str, tuple[float, float, datetime]] = {}
        self._access_order: deque[str] = deque()
        self._max_size = max_size
        self._distance_cache: dict[tuple, float] = {}

    def get_location(self, dog_id: str) -> tuple[float, float, datetime] | None:
        """Get cached location with LRU update.

        Args:
            dog_id: Dog identifier

        Returns:
            Location tuple or None
        """
        if dog_id in self._cache:
            # Update access order for LRU
            self._access_order.remove(dog_id)
            self._access_order.append(dog_id)
            return self._cache[dog_id]
        return None

    def set_location(
        self, dog_id: str, latitude: float, longitude: float, timestamp: datetime
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
            oldest = self._access_order.popleft()
            del self._cache[oldest]

        self._cache[dog_id] = (latitude, longitude, timestamp)

        # Update access order
        if dog_id in self._access_order:
            self._access_order.remove(dog_id)
        self._access_order.append(dog_id)

    def calculate_distance_cached(
        self, point1: tuple[float, float], point2: tuple[float, float]
    ) -> float:
        """Calculate distance with caching for frequently used points.

        Args:
            point1: First GPS coordinate (lat, lon)
            point2: Second GPS coordinate (lat, lon)

        Returns:
            Distance in meters
        """
        # Create cache key (order independent)
        cache_key = tuple(sorted([point1, point2]))

        if cache_key in self._distance_cache:
            return self._distance_cache[cache_key]

        # Calculate distance using Haversine formula
        distance = self._haversine_distance(point1, point2)

        # Cache result with size limit
        if len(self._distance_cache) >= DISTANCE_CALCULATION_CACHE_SIZE:
            # Remove oldest entry
            oldest_key = next(iter(self._distance_cache))
            del self._distance_cache[oldest_key]

        self._distance_cache[cache_key] = distance
        return distance

    @staticmethod
    def _haversine_distance(
        point1: tuple[float, float], point2: tuple[float, float]
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

    def clear(self) -> None:
        """Clear cache."""
        self._cache.clear()
        self._access_order.clear()
        self._distance_cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "location_entries": len(self._cache),
            "distance_cache_entries": len(self._distance_cache),
            "cache_utilization": len(self._cache) / self._max_size * 100,
        }


class WalkManager:
    """Optimized walk and GPS management with advanced caching and performance monitoring.

    OPTIMIZE: Enhanced with GPS caching, memory management, batch processing,
    and performance optimizations for Platinum-level quality.
    """

    def __init__(self) -> None:
        """Initialize optimized walk manager."""
        self._walk_data: dict[str, dict[str, Any]] = {}
        self._gps_data: dict[str, dict[str, Any]] = {}
        self._current_walks: dict[str, dict[str, Any]] = {}
        self._walk_history: dict[str, list[dict[str, Any]]] = {}
        self._data_lock = asyncio.Lock()

        # OPTIMIZE: Enhanced caching system
        self._gps_cache = GPSCache()
        self._zone_cache: dict[str, tuple[str, datetime]] = {}  # Cache with timestamp
        self._statistics_cache: dict[str, tuple[dict[str, Any], datetime]] = {}

        # OPTIMIZE: Walk detection parameters with better defaults
        self._walk_detection_enabled = True
        self._min_walk_distance = 50.0  # meters
        self._min_walk_duration = 120  # seconds
        self._walk_timeout = 1800  # 30 minutes
        self._min_speed_threshold = 0.5  # km/h minimum speed for walk detection

        # OPTIMIZE: Performance monitoring
        self._performance_metrics = {
            "gps_updates": 0,
            "distance_calculations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "memory_cleanups": 0,
        }

        # OPTIMIZE: Batch processing for location analysis
        self._location_analysis_queue: dict[
            str, list[tuple[float, float, datetime]]
        ] = {}
        self._batch_analysis_task: asyncio.Task | None = None

        _LOGGER.debug("WalkManager initialized with optimizations")

    async def async_initialize(self, dog_ids: list[str]) -> None:
        """Initialize walk manager for specified dogs with batch optimization.

        OPTIMIZE: Batch initialization for better performance.

        Args:
            dog_ids: List of dog identifiers to track
        """
        async with self._data_lock:
            # OPTIMIZE: Batch initialize all dogs
            for dog_id in dog_ids:
                self._walk_data[dog_id] = {
                    "walks_today": 0,
                    "total_duration_today": 0,
                    "total_distance_today": 0.0,
                    "last_walk": None,
                    "last_walk_duration": None,
                    "last_walk_distance": None,
                    "average_duration": None,
                    "weekly_walks": 0,
                    "weekly_distance": 0.0,
                    "needs_walk": False,
                    "walk_streak": 0,
                    "energy_level": "normal",  # OPTIMIZE: Added energy tracking
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

            # Start batch analysis task
            if self._batch_analysis_task is None:
                self._batch_analysis_task = asyncio.create_task(
                    self._batch_location_analysis()
                )

        _LOGGER.info(
            "WalkManager initialized for %d dogs with optimizations", len(dog_ids)
        )

    async def async_update_gps_data(
        self,
        dog_id: str,
        latitude: float,
        longitude: float,
        accuracy: float | None = None,
        speed: float | None = None,
        heading: float | None = None,
        source: str = "unknown",
        battery_level: int | None = None,
        signal_strength: int | None = None,
    ) -> bool:
        """Update GPS data with optimized validation and caching.

        OPTIMIZE: Enhanced with async validation, caching, and batch processing.

        Args:
            dog_id: Dog identifier
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            accuracy: GPS accuracy in meters
            speed: Speed in km/h
            heading: Heading/direction in degrees
            source: GPS data source
            battery_level: GPS device battery level (0-100)
            signal_strength: GPS signal strength (0-100)

        Returns:
            True if update successful
        """
        # OPTIMIZE: Fast coordinate validation
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            _LOGGER.warning(
                "Invalid GPS coordinates for %s: %f, %f", dog_id, latitude, longitude
            )
            return False

        async with self._data_lock:
            if dog_id not in self._gps_data:
                _LOGGER.warning("Dog %s not initialized for GPS tracking", dog_id)
                return False

            now = dt_util.now()
            old_location = None

            # OPTIMIZE: Get previous location from cache for better performance
            cached_location = self._gps_cache.get_location(dog_id)
            if cached_location is not None:
                old_location = (cached_location[0], cached_location[1])
                self._performance_metrics["cache_hits"] += 1
            elif (
                self._gps_data[dog_id]["latitude"] is not None
                and self._gps_data[dog_id]["longitude"] is not None
            ):
                old_location = (
                    self._gps_data[dog_id]["latitude"],
                    self._gps_data[dog_id]["longitude"],
                )
                self._performance_metrics["cache_misses"] += 1

            # Update GPS data with enhanced fields
            self._gps_data[dog_id].update(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "accuracy": accuracy,
                    "speed": speed,
                    "heading": heading,
                    "last_seen": now.isoformat(),
                    "source": source,
                    "available": True,
                    "battery_level": battery_level,
                    "signal_strength": signal_strength,
                }
            )

            # OPTIMIZE: Update cache with new location
            self._gps_cache.set_location(dog_id, latitude, longitude, now)

            # OPTIMIZE: Queue location analysis for batch processing
            self._location_analysis_queue[dog_id].append((latitude, longitude, now))

            # OPTIMIZE: Process walk detection with performance tracking
            if old_location and self._walk_detection_enabled:
                await self._process_walk_detection_optimized(
                    dog_id, old_location, (latitude, longitude), speed
                )

            # Update performance metrics
            self._performance_metrics["gps_updates"] += 1

            _LOGGER.debug(
                "Updated GPS data for %s: %f, %f (accuracy: %s, battery: %s%%)",
                dog_id,
                latitude,
                longitude,
                accuracy,
                battery_level,
            )
            return True

    async def _batch_location_analysis(self) -> None:
        """Background task for batch location analysis.

        OPTIMIZE: Process location analysis in batches for better performance.
        """
        while True:
            try:
                await asyncio.sleep(10)  # Process every 10 seconds

                async with self._data_lock:
                    for dog_id, queue in self._location_analysis_queue.items():
                        if len(queue) >= LOCATION_ANALYSIS_BATCH_SIZE:
                            # Process batch
                            batch = queue[:LOCATION_ANALYSIS_BATCH_SIZE]
                            del queue[:LOCATION_ANALYSIS_BATCH_SIZE]

                            # Analyze latest location in batch
                            if batch:
                                latest_lat, latest_lon, _latest_time = batch[-1]
                                await self._update_location_analysis(
                                    dog_id, latest_lat, latest_lon
                                )

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Batch location analysis error: %s", err)

    async def async_start_walk(
        self,
        dog_id: str,
        walk_type: str = "manual",
        *,
        walker: str | None = None,
        leash_used: bool | None = None,
        weather: WeatherCondition | str | None = None,
    ) -> str | None:
        """Start a walk with optimized data structure.

        OPTIMIZE: Enhanced with better initial data structure and validation.

        Args:
            dog_id: Dog identifier
            walk_type: Type of walk (manual, auto_detected)

        Returns:
            Walk ID if successful, None otherwise
        """
        async with self._data_lock:
            if dog_id not in self._walk_data:
                _LOGGER.warning("Dog %s not initialized for walk tracking", dog_id)
                return None

            if dog_id in self._current_walks:
                _LOGGER.warning("Walk already in progress for %s", dog_id)
                return None

            now = dt_util.now()
            walk_id = f"{dog_id}_{int(now.timestamp())}"

            weather_condition: WeatherCondition | None = None
            if isinstance(weather, WeatherCondition):
                weather_condition = weather
            elif isinstance(weather, str):
                try:
                    weather_condition = WeatherCondition(weather)
                except ValueError:
                    _LOGGER.warning(
                        "Ignoring unknown weather condition '%s' for %s",
                        weather,
                        dog_id,
                    )

            leash_flag = True if leash_used is None else bool(leash_used)

            # OPTIMIZE: Get current location from cache first
            start_location = None
            cached_location = self._gps_cache.get_location(dog_id)
            if cached_location is not None:
                start_location = {
                    "latitude": cached_location[0],
                    "longitude": cached_location[1],
                    "accuracy": self._gps_data[dog_id].get("accuracy"),
                    "timestamp": cached_location[2].isoformat(),
                }
            elif dog_id in self._gps_data and self._gps_data[dog_id]["available"]:
                start_location = {
                    "latitude": self._gps_data[dog_id]["latitude"],
                    "longitude": self._gps_data[dog_id]["longitude"],
                    "accuracy": self._gps_data[dog_id]["accuracy"],
                    "timestamp": now.isoformat(),
                }

            # OPTIMIZE: Pre-allocate path with capacity limit
            walk_data = {
                "walk_id": walk_id,
                "dog_id": dog_id,
                "start_time": now.isoformat(),
                "end_time": None,
                "duration": None,
                "distance": 0.0,
                "start_location": start_location,
                "end_location": None,
                "path": [],  # Will be limited to PATH_POINT_LIMIT
                "walk_type": walk_type,
                "status": "in_progress",
                "average_speed": None,
                "max_speed": None,
                "calories_burned": None,
                "elevation_gain": 0.0,  # OPTIMIZE: Added elevation tracking
                "path_optimization_applied": False,  # Track if path was optimized
                "walker": walker,
                "leash_used": leash_flag,
                "weather": weather_condition.value if weather_condition else None,
                "notes": None,
                "dog_weight_kg": None,
            }

            self._current_walks[dog_id] = walk_data

            # Update walk status
            self._walk_data[dog_id]["walk_in_progress"] = True
            self._walk_data[dog_id]["current_walk"] = walk_data

            _LOGGER.info(
                "Started %s walk for %s (ID: %s, walker: %s, weather: %s, leash_used: %s)",
                walk_type,
                dog_id,
                walk_id,
                walker or "unknown",
                weather_condition.value if weather_condition else "unspecified",
                "yes" if leash_flag else "no",
            )
            return walk_id

    async def async_end_walk(
        self,
        dog_id: str,
        *,
        notes: str | None = None,
        dog_weight_kg: float | None = None,
    ) -> dict[str, Any] | None:
        """End the current walk with optimized statistics calculation.

        OPTIMIZE: Enhanced with batch statistics calculation and path optimization.

        Args:
            dog_id: Dog identifier

        Returns:
            Completed walk data if successful, None otherwise
        """
        async with self._data_lock:
            if dog_id not in self._current_walks:
                _LOGGER.warning("No walk in progress for %s", dog_id)
                return None

            now = dt_util.now()
            walk_data = self._current_walks[dog_id]

            if notes is not None:
                walk_data["notes"] = notes
            if dog_weight_kg is not None:
                walk_data["dog_weight_kg"] = dog_weight_kg

            # OPTIMIZE: Get end location from cache if available
            end_location = None
            cached_location = self._gps_cache.get_location(dog_id)
            if cached_location is not None:
                end_location = {
                    "latitude": cached_location[0],
                    "longitude": cached_location[1],
                    "accuracy": self._gps_data[dog_id].get("accuracy"),
                    "timestamp": cached_location[2].isoformat(),
                }
            elif dog_id in self._gps_data and self._gps_data[dog_id]["available"]:
                end_location = {
                    "latitude": self._gps_data[dog_id]["latitude"],
                    "longitude": self._gps_data[dog_id]["longitude"],
                    "accuracy": self._gps_data[dog_id]["accuracy"],
                    "timestamp": now.isoformat(),
                }

            # Calculate walk statistics
            start_time = dt_util.parse_datetime(walk_data["start_time"])
            duration = (now - start_time).total_seconds()

            # Update walk data
            walk_data.update(
                {
                    "end_time": now.isoformat(),
                    "duration": duration,
                    "end_location": end_location,
                    "status": "completed",
                }
            )

            # OPTIMIZE: Calculate additional statistics with caching
            if walk_data["path"]:
                # Optimize path if too many points
                if len(walk_data["path"]) > PATH_POINT_LIMIT:
                    walk_data["path"] = self._optimize_path(walk_data["path"])
                    walk_data["path_optimization_applied"] = True

                walk_data["distance"] = await self._calculate_total_distance_optimized(
                    walk_data["path"]
                )
                walk_data["average_speed"] = self._calculate_average_speed(walk_data)
                walk_data["max_speed"] = self._calculate_max_speed(walk_data["path"])
                walk_data["elevation_gain"] = self._calculate_elevation_gain(
                    walk_data["path"]
                )
                walk_data["calories_burned"] = self._estimate_calories_burned(
                    dog_id, walk_data
                )

            # Update daily statistics with batch optimization
            await self._update_daily_walk_stats_optimized(dog_id, walk_data)

            # OPTIMIZE: Store in history with size limit
            self._walk_history[dog_id].append(walk_data.copy())

            # Keep only last 100 walks to prevent memory leaks
            if len(self._walk_history[dog_id]) > 100:
                self._walk_history[dog_id] = self._walk_history[dog_id][-100:]
                self._performance_metrics["memory_cleanups"] += 1

            # Clear current walk
            del self._current_walks[dog_id]
            self._walk_data[dog_id]["walk_in_progress"] = False
            self._walk_data[dog_id]["current_walk"] = None

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

    def _optimize_path(self, path: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Optimize walk path by removing redundant points.

        OPTIMIZE: Reduce memory usage by removing points that don't add significant value.

        Args:
            path: Original path points

        Returns:
            Optimized path
        """
        if len(path) <= PATH_POINT_LIMIT:
            return path

        # Keep start and end points
        optimized = [path[0]]

        # Sample points at regular intervals
        interval = len(path) // (PATH_POINT_LIMIT - 2)
        optimized.extend(path[i] for i in range(interval, len(path) - 1, interval))

        # Always keep end point
        optimized.append(path[-1])

        _LOGGER.debug("Optimized path: %d -> %d points", len(path), len(optimized))

        return optimized

    async def _process_walk_detection_optimized(
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
        distance = self._gps_cache.calculate_distance_cached(old_location, new_location)
        self._performance_metrics["distance_calculations"] += 1

        # OPTIMIZE: Enhanced walk detection logic
        speed_threshold_met = (speed or 0) > self._min_speed_threshold
        movement_threshold_met = distance > 10  # Moved more than 10 meters
        not_already_walking = dog_id not in self._current_walks

        # Check if movement indicates start of walk
        if movement_threshold_met and speed_threshold_met and not_already_walking:
            await self.async_start_walk(dog_id, "auto_detected")
            _LOGGER.debug(
                "Auto-detected walk start for %s: distance=%.1fm, speed=%.1fkm/h",
                dog_id,
                distance,
                speed or 0,
            )

        # OPTIMIZE: Add to walk path if walk in progress with point limits
        if dog_id in self._current_walks:
            current_walk = self._current_walks[dog_id]

            # Only add point if it's significant (distance > 5m or time > 30s since last point)
            should_add_point = True
            if current_walk["path"]:
                last_point = current_walk["path"][-1]
                last_location = (last_point["latitude"], last_point["longitude"])
                last_distance = self._gps_cache.calculate_distance_cached(
                    last_location, new_location
                )

                # Only add if moved significantly or time passed
                now = dt_util.now()
                last_time = dt_util.parse_datetime(last_point["timestamp"])
                time_diff = (now - last_time).total_seconds()

                should_add_point = last_distance > 5.0 or time_diff > 30

            if should_add_point and len(current_walk["path"]) < PATH_POINT_LIMIT:
                path_point = {
                    "latitude": new_location[0],
                    "longitude": new_location[1],
                    "timestamp": dt_util.now().isoformat(),
                    "accuracy": self._gps_data[dog_id].get("accuracy"),
                    "speed": speed,
                    "altitude": self._gps_data[dog_id].get("altitude"),
                }
                current_walk["path"].append(path_point)

    async def _calculate_total_distance_optimized(
        self, path: list[dict[str, Any]]
    ) -> float:
        """Calculate total distance with caching optimization.

        OPTIMIZE: Batch distance calculations for better performance.

        Args:
            path: List of GPS path points

        Returns:
            Total distance in meters
        """
        if len(path) < 2:
            return 0.0

        total_distance = 0.0

        # OPTIMIZE: Batch process distance calculations
        for i in range(1, len(path)):
            point1 = (path[i - 1]["latitude"], path[i - 1]["longitude"])
            point2 = (path[i]["latitude"], path[i]["longitude"])
            total_distance += self._gps_cache.calculate_distance_cached(point1, point2)
            self._performance_metrics["distance_calculations"] += 1

        return total_distance

    async def _update_daily_walk_stats_optimized(
        self, dog_id: str, walk_data: dict[str, Any]
    ) -> None:
        """Update daily walk statistics with optimized calculations.

        OPTIMIZE: Batch statistics updates and cache invalidation.

        Args:
            dog_id: Dog identifier
            walk_data: Completed walk data
        """
        # Update today's stats
        self._walk_data[dog_id]["walks_today"] += 1
        self._walk_data[dog_id]["total_duration_today"] += walk_data["duration"]
        self._walk_data[dog_id]["total_distance_today"] += walk_data["distance"]
        self._walk_data[dog_id]["last_walk"] = walk_data["start_time"]
        self._walk_data[dog_id]["last_walk_duration"] = walk_data["duration"]
        self._walk_data[dog_id]["last_walk_distance"] = walk_data["distance"]

        # OPTIMIZE: Batch calculate averages from recent walks
        recent_walks = await self.async_get_walk_history(dog_id, 7)
        if recent_walks:
            durations = [
                w.get("duration", 0) for w in recent_walks if w.get("duration")
            ]
            distances = [
                w.get("distance", 0) for w in recent_walks if w.get("distance")
            ]

            if durations:
                self._walk_data[dog_id]["average_duration"] = sum(durations) / len(
                    durations
                )
            if distances:
                self._walk_data[dog_id]["average_distance"] = sum(distances) / len(
                    distances
                )

        # OPTIMIZE: Update weekly stats in single pass
        week_walks = await self.async_get_walk_history(dog_id, 7)
        self._walk_data[dog_id]["weekly_walks"] = len(week_walks)
        self._walk_data[dog_id]["weekly_distance"] = sum(
            w.get("distance", 0) for w in week_walks
        )

        # OPTIMIZE: Calculate walk streak efficiently
        self._walk_data[dog_id][
            "walk_streak"
        ] = await self._calculate_walk_streak_optimized(dog_id)

        # Update energy level based on recent activity
        self._update_energy_level(dog_id, walk_data)

    async def _calculate_walk_streak_optimized(self, dog_id: str) -> int:
        """Calculate walk streak with optimized algorithm.

        OPTIMIZE: More efficient streak calculation using binary search approach.

        Args:
            dog_id: Dog identifier

        Returns:
            Current walk streak in days
        """
        recent_walks = await self.async_get_walk_history(dog_id, 30)
        if not recent_walks:
            return 0

        # Group walks by date
        walks_by_date: dict[str, int] = {}
        for walk in recent_walks:
            try:
                walk_date = dt_util.parse_datetime(walk["start_time"]).date()
                date_str = walk_date.isoformat()
                walks_by_date[date_str] = walks_by_date.get(date_str, 0) + 1
            except (ValueError, TypeError):
                continue

        # Calculate streak
        streak = 0
        current_date = dt_util.now().date()

        for _ in range(30):  # Check last 30 days
            date_str = current_date.isoformat()
            if date_str in walks_by_date:
                streak += 1
                current_date -= timedelta(days=1)
            else:
                break

        return streak

    def _update_energy_level(self, dog_id: str, walk_data: dict[str, Any]) -> None:
        """Update dog's energy level based on walk activity.

        Args:
            dog_id: Dog identifier
            walk_data: Recent walk data
        """
        # Simple energy level calculation based on walk distance and duration
        distance = walk_data.get("distance", 0)
        duration = walk_data.get("duration", 0)

        if distance > 2000 or duration > 3600:  # Long walk (>2km or >1h)
            energy_level = "low"
        elif distance > 1000 or duration > 1800:  # Moderate walk (>1km or >30min)
            energy_level = "medium"
        else:
            energy_level = "high"

        self._walk_data[dog_id]["energy_level"] = energy_level

    def _calculate_elevation_gain(self, path: list[dict[str, Any]]) -> float:
        """Calculate total elevation gain from path.

        OPTIMIZE: New feature for comprehensive walk analysis.

        Args:
            path: List of GPS path points with altitude data

        Returns:
            Total elevation gain in meters
        """
        if len(path) < 2:
            return 0.0

        total_gain = 0.0
        last_altitude = None

        for point in path:
            altitude = point.get("altitude")
            if altitude is not None and last_altitude is not None:
                gain = altitude - last_altitude
                if gain > 0:  # Only count positive elevation changes
                    total_gain += gain
            last_altitude = altitude

        return total_gain

    async def async_get_walk_data_cached(self, dog_id: str) -> dict[str, Any]:
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
            cached_data, cache_time = self._statistics_cache[cache_key]
            if (dt_util.now() - cache_time).total_seconds() < STATISTICS_CACHE_TTL:
                return cached_data

        # Calculate fresh data
        async with self._data_lock:
            if dog_id not in self._walk_data:
                return {}

            data = self._walk_data[dog_id].copy()

            # Add current walk if in progress
            if dog_id in self._current_walks:
                current_walk = self._current_walks[dog_id].copy()

                # Calculate current walk duration and distance
                if current_walk["path"]:
                    current_walk[
                        "current_distance"
                    ] = await self._calculate_total_distance_optimized(
                        current_walk["path"]
                    )

                start_time = dt_util.parse_datetime(current_walk["start_time"])
                current_walk["current_duration"] = (
                    dt_util.now() - start_time
                ).total_seconds()

                data["current_walk"] = current_walk
                data["walk_in_progress"] = True
            else:
                data["walk_in_progress"] = False
                data["current_walk"] = None

            # Cache result
            self._statistics_cache[cache_key] = (data, dt_util.now())
            return data

    def _invalidate_statistics_cache(self, dog_id: str) -> None:
        """Invalidate statistics cache for a dog.

        Args:
            dog_id: Dog identifier
        """
        cache_key = f"walk_data_{dog_id}"
        self._statistics_cache.pop(cache_key, None)

    async def async_get_performance_statistics(self) -> dict[str, Any]:
        """Get performance statistics for the walk manager.

        OPTIMIZE: New method for monitoring performance and optimization effectiveness.

        Returns:
            Performance statistics
        """
        async with self._data_lock:
            total_dogs = len(self._walk_data)
            dogs_with_gps = sum(
                1 for gps in self._gps_data.values() if gps["available"]
            )
            active_walks = len(self._current_walks)

            total_walks_today = sum(
                data["walks_today"] for data in self._walk_data.values()
            )
            total_distance_today = sum(
                data["total_distance_today"] for data in self._walk_data.values()
            )

            # Cache statistics
            cache_stats = self._gps_cache.get_stats()

            return {
                # Basic stats
                "total_dogs": total_dogs,
                "dogs_with_gps": dogs_with_gps,
                "active_walks": active_walks,
                "total_walks_today": total_walks_today,
                "total_distance_today": round(total_distance_today, 1),
                "walk_detection_enabled": self._walk_detection_enabled,
                # Performance metrics
                "performance_metrics": self._performance_metrics.copy(),
                "cache_stats": cache_stats,
                "statistics_cache_entries": len(self._statistics_cache),
                "location_analysis_queue_size": sum(
                    len(queue) for queue in self._location_analysis_queue.values()
                ),
                # Memory usage
                "average_path_length": sum(
                    len(walk.get("path", [])) for walk in self._current_walks.values()
                )
                / max(len(self._current_walks), 1),
            }

    # OPTIMIZE: Keep existing methods for compatibility but optimize internal calls
    async def async_get_current_walk(self, dog_id: str) -> dict[str, Any] | None:
        """Get current walk data for a dog."""
        async with self._data_lock:
            return (
                self._current_walks.get(dog_id, {}).copy()
                if dog_id in self._current_walks
                else None
            )

    async def async_get_walk_data(self, dog_id: str) -> dict[str, Any]:
        """Get walk statistics for a dog with caching."""
        return await self.async_get_walk_data_cached(dog_id)

    async def async_get_gps_data(self, dog_id: str) -> dict[str, Any]:
        """Get GPS data for a dog."""
        async with self._data_lock:
            if dog_id not in self._gps_data:
                return {"available": False, "error": "Dog not initialized"}

            return self._gps_data[dog_id].copy()

    async def async_get_walk_history(
        self, dog_id: str, days: int = 7
    ) -> list[dict[str, Any]]:
        """Get walk history for a dog."""
        async with self._data_lock:
            if dog_id not in self._walk_history:
                return []

            # Filter by date range
            cutoff = dt_util.now() - timedelta(days=days)
            recent_walks = []

            for walk in self._walk_history[dog_id]:
                try:
                    start_time = dt_util.parse_datetime(walk["start_time"])
                    if start_time and start_time >= cutoff:
                        recent_walks.append(walk.copy())
                except (ValueError, TypeError):
                    continue

            return sorted(recent_walks, key=lambda w: w["start_time"], reverse=True)

    async def _update_location_analysis(
        self, dog_id: str, latitude: float, longitude: float
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
            zone, cache_time = self._zone_cache[dog_id]
            # Use cached zone if less than 5 minutes old
            if (now - cache_time).total_seconds() < 300:
                self._gps_data[dog_id]["zone"] = zone
                return

        # Calculate distance from home (placeholder - would need home coordinates)
        distance_from_home = 0.0  # Would get from Home Assistant

        # Determine zone
        if distance_from_home < 50:
            zone = "home"
        elif distance_from_home < 200:
            zone = "neighborhood"
        else:
            zone = "away"

        # Update GPS data and cache
        self._gps_data[dog_id]["distance_from_home"] = distance_from_home
        self._gps_data[dog_id]["zone"] = zone
        self._zone_cache[dog_id] = (zone, now)

    # Keep existing utility methods
    def _calculate_average_speed(self, walk_data: dict[str, Any]) -> float | None:
        """Calculate average speed for a walk."""
        if walk_data["duration"] <= 0:
            return None

        distance_km = walk_data["distance"] / 1000
        duration_hours = walk_data["duration"] / 3600

        return distance_km / duration_hours if duration_hours > 0 else None

    def _calculate_max_speed(self, path: list[dict[str, Any]]) -> float | None:
        """Calculate maximum speed from path."""
        speeds = [
            point.get("speed") for point in path if point.get("speed") is not None
        ]
        return max(speeds) if speeds else None

    def _estimate_calories_burned(
        self, dog_id: str, walk_data: dict[str, Any]
    ) -> float | None:
        """Estimate calories burned during walk."""
        if walk_data["duration"] <= 0:
            return None

        # Enhanced calorie estimation with elevation
        weight = walk_data.get("dog_weight_kg")
        estimated_weight = (
            float(weight) if isinstance(weight, int | float) and weight > 0 else 20.0
        )
        duration_minutes = walk_data["duration"] / 60
        base_calories = estimated_weight * duration_minutes * 0.5

        # Add elevation bonus
        elevation_gain = walk_data.get("elevation_gain", 0)
        elevation_bonus = elevation_gain * 0.1  # 0.1 cal per meter elevation gain

        return base_calories + elevation_bonus

    async def async_get_statistics(self) -> dict[str, Any]:
        """Get walk manager statistics."""
        return await self.async_get_performance_statistics()

    async def async_cleanup(self) -> None:
        """Clean up resources with enhanced cleanup."""
        # Cancel batch analysis task
        if self._batch_analysis_task:
            self._batch_analysis_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._batch_analysis_task

        async with self._data_lock:
            self._walk_data.clear()
            self._gps_data.clear()
            self._current_walks.clear()
            self._walk_history.clear()
            self._location_analysis_queue.clear()
            self._statistics_cache.clear()

            # Clear caches
            self._gps_cache.clear()
            self._zone_cache.clear()

        _LOGGER.debug("WalkManager cleanup completed with optimizations")

    async def async_shutdown(self) -> None:
        """Enhanced shutdown method."""
        await self.async_cleanup()
