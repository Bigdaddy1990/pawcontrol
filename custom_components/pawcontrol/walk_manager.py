"""Walk and GPS management for PawControl."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class WalkManager:
    """Manages walk tracking and GPS data processing.

    Separated from coordinator to handle all walk-related functionality
    including GPS tracking, walk detection, and location analysis.
    """

    def __init__(self) -> None:
        """Initialize walk manager."""
        self._walk_data: dict[str, dict[str, Any]] = {}
        self._gps_data: dict[str, dict[str, Any]] = {}
        self._current_walks: dict[str, dict[str, Any]] = {}
        self._walk_history: dict[str, list[dict[str, Any]]] = {}
        self._data_lock = asyncio.Lock()

        # GPS processing cache
        self._location_cache: dict[str, tuple[float, float, datetime]] = {}
        self._zone_cache: dict[str, str] = {}

        # Walk detection parameters
        self._walk_detection_enabled = True
        self._min_walk_distance = 50.0  # meters
        self._min_walk_duration = 120  # seconds
        self._walk_timeout = 1800  # 30 minutes

        _LOGGER.debug("WalkManager initialized")

    async def async_initialize(self, dog_ids: list[str]) -> None:
        """Initialize walk manager for specified dogs.

        Args:
            dog_ids: List of dog identifiers to track
        """
        async with self._data_lock:
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
                }

                self._walk_history[dog_id] = []

        _LOGGER.info("WalkManager initialized for %d dogs", len(dog_ids))

    async def async_update_gps_data(
        self,
        dog_id: str,
        latitude: float,
        longitude: float,
        accuracy: float | None = None,
        speed: float | None = None,
        heading: float | None = None,
        source: str = "unknown",
    ) -> bool:
        """Update GPS data for a dog.

        Args:
            dog_id: Dog identifier
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            accuracy: GPS accuracy in meters
            speed: Speed in km/h
            heading: Heading/direction in degrees
            source: GPS data source

        Returns:
            True if update successful
        """
        if not self._validate_coordinates(latitude, longitude):
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

            # Get previous location for distance calculation
            if (
                self._gps_data[dog_id]["latitude"] is not None
                and self._gps_data[dog_id]["longitude"] is not None
            ):
                old_location = (
                    self._gps_data[dog_id]["latitude"],
                    self._gps_data[dog_id]["longitude"],
                )

            # Update GPS data
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
                }
            )

            # Update location cache
            self._location_cache[dog_id] = (latitude, longitude, now)

            # Calculate distance from home and zone
            await self._update_location_analysis(dog_id, latitude, longitude)

            # Process walk detection
            if old_location and self._walk_detection_enabled:
                await self._process_walk_detection(
                    dog_id, old_location, (latitude, longitude)
                )

            _LOGGER.debug(
                "Updated GPS data for %s: %f, %f (accuracy: %s)",
                dog_id,
                latitude,
                longitude,
                accuracy,
            )
            return True

    async def async_start_walk(
        self, dog_id: str, walk_type: str = "manual"
    ) -> str | None:
        """Start a walk for a dog.

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

            # Get current location if available
            start_location = None
            if dog_id in self._gps_data and self._gps_data[dog_id]["available"]:
                start_location = {
                    "latitude": self._gps_data[dog_id]["latitude"],
                    "longitude": self._gps_data[dog_id]["longitude"],
                    "accuracy": self._gps_data[dog_id]["accuracy"],
                }

            walk_data = {
                "walk_id": walk_id,
                "dog_id": dog_id,
                "start_time": now.isoformat(),
                "end_time": None,
                "duration": None,
                "distance": 0.0,
                "start_location": start_location,
                "end_location": None,
                "path": [],
                "walk_type": walk_type,
                "status": "in_progress",
                "average_speed": None,
                "max_speed": None,
                "calories_burned": None,
            }

            self._current_walks[dog_id] = walk_data

            # Update walk status
            self._walk_data[dog_id]["walk_in_progress"] = True
            self._walk_data[dog_id]["current_walk"] = walk_data

            _LOGGER.info("Started %s walk for %s (ID: %s)", walk_type, dog_id, walk_id)
            return walk_id

    async def async_end_walk(self, dog_id: str) -> dict[str, Any] | None:
        """End the current walk for a dog.

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

            # Get end location if available
            end_location = None
            if dog_id in self._gps_data and self._gps_data[dog_id]["available"]:
                end_location = {
                    "latitude": self._gps_data[dog_id]["latitude"],
                    "longitude": self._gps_data[dog_id]["longitude"],
                    "accuracy": self._gps_data[dog_id]["accuracy"],
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

            # Calculate additional statistics
            if walk_data["path"]:
                walk_data["distance"] = self._calculate_total_distance(
                    walk_data["path"]
                )
                walk_data["average_speed"] = self._calculate_average_speed(walk_data)
                walk_data["max_speed"] = self._calculate_max_speed(walk_data["path"])
                walk_data["calories_burned"] = self._estimate_calories_burned(
                    dog_id, walk_data
                )

            # Update daily statistics
            await self._update_daily_walk_stats(dog_id, walk_data)

            # Store in history
            self._walk_history[dog_id].append(walk_data.copy())

            # Keep only last 100 walks
            if len(self._walk_history[dog_id]) > 100:
                self._walk_history[dog_id] = self._walk_history[dog_id][-100:]

            # Clear current walk
            del self._current_walks[dog_id]
            self._walk_data[dog_id]["walk_in_progress"] = False
            self._walk_data[dog_id]["current_walk"] = None

            _LOGGER.info(
                "Completed walk for %s: %.1fm in %.0fs",
                dog_id,
                walk_data["distance"],
                duration,
            )
            return walk_data

    async def async_get_current_walk(self, dog_id: str) -> dict[str, Any] | None:
        """Get current walk data for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Current walk data or None if no walk in progress
        """
        async with self._data_lock:
            return (
                self._current_walks.get(dog_id, {}).copy()
                if dog_id in self._current_walks
                else None
            )

    async def async_get_walk_data(self, dog_id: str) -> dict[str, Any]:
        """Get walk statistics for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Walk statistics data
        """
        async with self._data_lock:
            if dog_id not in self._walk_data:
                return {}

            data = self._walk_data[dog_id].copy()

            # Add current walk if in progress
            if dog_id in self._current_walks:
                data["current_walk"] = self._current_walks[dog_id].copy()
                data["walk_in_progress"] = True
            else:
                data["walk_in_progress"] = False
                data["current_walk"] = None

            return data

    async def async_get_gps_data(self, dog_id: str) -> dict[str, Any]:
        """Get GPS data for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            GPS data
        """
        async with self._data_lock:
            if dog_id not in self._gps_data:
                return {"available": False, "error": "Dog not initialized"}

            return self._gps_data[dog_id].copy()

    async def async_get_walk_history(
        self, dog_id: str, days: int = 7
    ) -> list[dict[str, Any]]:
        """Get walk history for a dog.

        Args:
            dog_id: Dog identifier
            days: Number of days of history to return

        Returns:
            List of walk records
        """
        async with self._data_lock:
            if dog_id not in self._walk_history:
                return []

            # Filter by date range
            cutoff = dt_util.now() - timedelta(days=days)
            recent_walks = []

            for walk in self._walk_history[dog_id]:
                start_time = dt_util.parse_datetime(walk["start_time"])
                if start_time and start_time >= cutoff:
                    recent_walks.append(walk.copy())

            return sorted(recent_walks, key=lambda w: w["start_time"], reverse=True)

    def _validate_coordinates(self, latitude: float, longitude: float) -> bool:
        """Validate GPS coordinates.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            True if coordinates are valid
        """
        try:
            lat = float(latitude)
            lon = float(longitude)
            return -90 <= lat <= 90 and -180 <= lon <= 180
        except (ValueError, TypeError):
            return False

    async def _update_location_analysis(
        self, dog_id: str, latitude: float, longitude: float
    ) -> None:
        """Update location-based analysis.

        Args:
            dog_id: Dog identifier
            latitude: Current latitude
            longitude: Current longitude
        """
        # Calculate distance from home (placeholder - would need home coordinates)
        # This would typically get home coordinates from Home Assistant
        distance_from_home = 0.0  # Placeholder

        # Determine zone (placeholder - would use Home Assistant zones)
        zone = "unknown"
        if distance_from_home < 50:
            zone = "home"
        elif distance_from_home < 200:
            zone = "neighborhood"
        else:
            zone = "away"

        # Update GPS data
        self._gps_data[dog_id]["distance_from_home"] = distance_from_home
        self._gps_data[dog_id]["zone"] = zone
        self._zone_cache[dog_id] = zone

    async def _process_walk_detection(
        self,
        dog_id: str,
        old_location: tuple[float, float],
        new_location: tuple[float, float],
    ) -> None:
        """Process automatic walk detection.

        Args:
            dog_id: Dog identifier
            old_location: Previous GPS coordinates
            new_location: Current GPS coordinates
        """
        distance = self._calculate_distance(old_location, new_location)

        # Check if movement indicates start of walk
        if (
            distance > 10  # Moved more than 10 meters
            and dog_id not in self._current_walks
            and self._gps_data[dog_id].get("speed", 0) > 1
        ):  # Speed > 1 km/h
            await self.async_start_walk(dog_id, "auto_detected")

        # Add to walk path if walk in progress
        if dog_id in self._current_walks:
            path_point = {
                "latitude": new_location[0],
                "longitude": new_location[1],
                "timestamp": dt_util.now().isoformat(),
                "accuracy": self._gps_data[dog_id].get("accuracy"),
                "speed": self._gps_data[dog_id].get("speed"),
            }
            self._current_walks[dog_id]["path"].append(path_point)

    async def _update_daily_walk_stats(
        self, dog_id: str, walk_data: dict[str, Any]
    ) -> None:
        """Update daily walk statistics.

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

        # Calculate averages
        recent_walks = await self.async_get_walk_history(dog_id, 7)
        if recent_walks:
            total_duration = sum(w.get("duration", 0) for w in recent_walks)
            avg_duration = total_duration / len(recent_walks)
            self._walk_data[dog_id]["average_duration"] = avg_duration

        # Update weekly stats
        week_walks = await self.async_get_walk_history(dog_id, 7)
        self._walk_data[dog_id]["weekly_walks"] = len(week_walks)
        self._walk_data[dog_id]["weekly_distance"] = sum(
            w.get("distance", 0) for w in week_walks
        )

        # Calculate walk streak
        today = dt_util.now().date()
        streak = 0
        current_date = today

        for _i in range(30):  # Check last 30 days
            day_walks = [
                w
                for w in recent_walks
                if dt_util.parse_datetime(w["start_time"]).date() == current_date
            ]
            if day_walks:
                streak += 1
                current_date -= timedelta(days=1)
            else:
                break

        self._walk_data[dog_id]["walk_streak"] = streak

    def _calculate_distance(
        self, point1: tuple[float, float], point2: tuple[float, float]
    ) -> float:
        """Calculate distance between two GPS points using Haversine formula.

        Args:
            point1: First GPS coordinate (lat, lon)
            point2: Second GPS coordinate (lat, lon)

        Returns:
            Distance in meters
        """
        import math

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
        r = 6371000

        return c * r

    def _calculate_total_distance(self, path: list[dict[str, Any]]) -> float:
        """Calculate total distance from path points.

        Args:
            path: List of GPS path points

        Returns:
            Total distance in meters
        """
        if len(path) < 2:
            return 0.0

        total_distance = 0.0
        for i in range(1, len(path)):
            point1 = (path[i - 1]["latitude"], path[i - 1]["longitude"])
            point2 = (path[i]["latitude"], path[i]["longitude"])
            total_distance += self._calculate_distance(point1, point2)

        return total_distance

    def _calculate_average_speed(self, walk_data: dict[str, Any]) -> float | None:
        """Calculate average speed for a walk.

        Args:
            walk_data: Walk data

        Returns:
            Average speed in km/h or None
        """
        if walk_data["duration"] <= 0:
            return None

        # Convert distance to km and duration to hours
        distance_km = walk_data["distance"] / 1000
        duration_hours = walk_data["duration"] / 3600

        return distance_km / duration_hours if duration_hours > 0 else None

    def _calculate_max_speed(self, path: list[dict[str, Any]]) -> float | None:
        """Calculate maximum speed from path.

        Args:
            path: List of GPS path points with speed data

        Returns:
            Maximum speed in km/h or None
        """
        speeds = [
            point.get("speed") for point in path if point.get("speed") is not None
        ]
        return max(speeds) if speeds else None

    def _estimate_calories_burned(
        self, dog_id: str, walk_data: dict[str, Any]
    ) -> float | None:
        """Estimate calories burned during walk.

        Args:
            dog_id: Dog identifier
            walk_data: Walk data

        Returns:
            Estimated calories burned or None
        """
        # Simplified calorie estimation
        # Would need dog weight and other factors for accuracy
        if walk_data["duration"] <= 0:
            return None

        # Rough estimate: 0.5 calories per minute per kg (placeholder)
        estimated_weight = 20.0  # kg (would get from dog config)
        duration_minutes = walk_data["duration"] / 60

        return estimated_weight * duration_minutes * 0.5

    async def async_get_statistics(self) -> dict[str, Any]:
        """Get walk manager statistics.

        Returns:
            Statistics about walk management
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

            return {
                "total_dogs": total_dogs,
                "dogs_with_gps": dogs_with_gps,
                "active_walks": active_walks,
                "total_walks_today": total_walks_today,
                "total_distance_today": round(total_distance_today, 1),
                "walk_detection_enabled": self._walk_detection_enabled,
                "location_cache_size": len(self._location_cache),
            }

    async def async_cleanup(self) -> None:
        """Clean up resources."""
        async with self._data_lock:
            self._walk_data.clear()
            self._gps_data.clear()
            self._current_walks.clear()
            self._walk_history.clear()
            self._location_cache.clear()
            self._zone_cache.clear()

        _LOGGER.debug("WalkManager cleanup completed")
