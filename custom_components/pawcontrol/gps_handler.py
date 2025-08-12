"""GPS handler for Paw Control integration."""
from __future__ import annotations

import os
import json
import asyncio
from typing import Any, Dict, List, Tuple
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .gps_settings import GPSSettingsStore
from .const import DOMAIN, GPS_MAX_POINTS_PER_ROUTE, GPS_POINT_FILTER_DISTANCE

import logging
_LOGGER = logging.getLogger(__name__)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS coordinates in meters using Haversine formula."""
    try:
        R = 6371000.0  # Earth radius in meters
        phi1, phi2 = radians(lat1), radians(lat2)
        dphi = radians(lat2 - lat1)
        dlambda = radians(lon2 - lon1)
        
        a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
        c = 2*atan2(sqrt(a), sqrt(1 - a))
        
        return R * c
    except (ValueError, TypeError, OverflowError):
        return 0.0


def _now() -> datetime:
    """Get current UTC datetime."""
    return dt_util.utcnow()


def _inc_state(hass: HomeAssistant, entity_id: str, inc: float, attrs: dict | None = None) -> None:
    """Increment state value for an entity with validation."""
    try:
        state = hass.states.get(entity_id)
        current_val = 0.0
        
        if state and state.state not in ("unknown", "unavailable"):
            try:
                current_val = float(state.state)
            except (ValueError, TypeError):
                current_val = 0.0
        
        new_val = max(0, current_val + float(inc))
        
        # Round appropriately
        if isinstance(inc, int) or new_val.is_integer():
            new_val = int(new_val)
        else:
            new_val = round(new_val, 2)
        
        hass.states.async_set(entity_id, new_val, attrs or {})
    except Exception as exc:
        _LOGGER.debug("Failed to increment state for %s: %s", entity_id, exc)


class GPSPoint:
    """Represents a GPS point with metadata."""
    
    def __init__(self, latitude: float, longitude: float, timestamp: str, accuracy: float | None = None):
        """Initialize GPS point."""
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.timestamp = timestamp
        self.accuracy = float(accuracy) if accuracy is not None else None
        
    def distance_to(self, other: 'GPSPoint') -> float:
        """Calculate distance to another GPS point."""
        return _haversine_m(self.latitude, self.longitude, other.latitude, other.longitude)
    
    def to_tuple(self) -> Tuple[float, float, str]:
        """Convert to tuple format for backward compatibility."""
        return (self.latitude, self.longitude, self.timestamp)


class PawControlGPSHandler:
    """GPS handler providing walk tracking, dispatcher updates, and safe-zone events."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]):
        """Initialize the GPS handler."""
        self.hass = hass
        self.options = options or {}
        self.entry_id: str | None = None
        self._routes: Dict[str, Dict[str, Any]] = {}
        self._metrics: Dict[str, Dict[str, Any]] = {}
        self._settings_store: GPSSettingsStore | None = None
        self._settings: dict[str, Any] = {}
        self._safe_status: Dict[str, Dict[str, Any]] = {}
        self._last_location_update: Dict[str, datetime] = {}
        self._location_lock = asyncio.Lock()

    async def async_setup(self) -> None:
        """Set up the GPS handler."""
        try:
            self._settings_store = GPSSettingsStore(self.hass, self.entry_id or "default", DOMAIN)
            self._settings = await self._settings_store.async_load()
            
            # Merge options.safe_zones if present
            opt_safe_zones = (self.options or {}).get("safe_zones") or {}
            if opt_safe_zones:
                base_settings = dict(self._settings or {})
                base_settings.setdefault("safe_zones", {})
                base_settings["safe_zones"].update(opt_safe_zones)
                self._settings = base_settings
                await self._settings_store.async_save(self._settings)
                
            _LOGGER.debug("GPS handler setup completed")
        except Exception as exc:
            _LOGGER.error("GPS handler setup failed: %s", exc)
            # Continue with empty settings
            self._settings = {}

    def _dog_id(self, dog_id: str | None) -> str:
        """Get the dog ID, with fallback to first configured dog."""
        if dog_id and isinstance(dog_id, str):
            return dog_id
        
        dogs = (self.options or {}).get("dogs") or []
        if dogs and isinstance(dogs, list):
            first_dog = dogs[0]
            if isinstance(first_dog, dict):
                return first_dog.get("dog_id") or first_dog.get("name") or "dog"
        
        return "dog"

    def _get_route_data(self, dog: str) -> Dict[str, Any]:
        """Get or initialize route data for a dog with validation."""
        if dog not in self._routes:
            self._routes[dog] = {
                "active": False,
                "start": None,
                "points": [],
                "distance_m": 0.0,
                "paused": False,
                "last_update": None,
            }
        
        # Validate route data structure
        route_data = self._routes[dog]
        if not isinstance(route_data.get("points"), list):
            route_data["points"] = []
        if not isinstance(route_data.get("distance_m"), (int, float)):
            route_data["distance_m"] = 0.0
            
        return route_data

    def _get_metrics(self, dog: str) -> Dict[str, Any]:
        """Get or initialize metrics for a dog."""
        if dog not in self._metrics:
            self._metrics[dog] = {
                "points_total": 0,
                "points_dropped": 0,
                "acc_sum": 0.0,
                "acc_count": 0,
            }
        return self._metrics[dog]

    def _get_safe_status(self, dog: str) -> Dict[str, Any]:
        """Get or initialize safe zone status for a dog."""
        if dog not in self._safe_status:
            self._safe_status[dog] = {
                "inside": None,
                "last_ts": None,
                "enters": 0,
                "leaves": 0,
                "time_today": 0.0,
                "last_distance": None,
                "last_radius": None,
            }
        return self._safe_status[dog]

    async def async_start_walk(self, walk_type: str | None = None, dog_id: str | None = None) -> None:
        """Start a walk for a dog."""
        async with self._location_lock:
            try:
                dog = self._dog_id(dog_id)
                route_data = self._get_route_data(dog)
                
                if route_data["active"]:
                    _LOGGER.warning("Walk already active for dog %s", dog)
                    return
                
                now = _now()
                route_data.update({
                    "active": True,
                    "start": now,
                    "points": [],
                    "distance_m": 0.0,
                    "paused": False,
                    "last_update": now,
                })
                
                # Fire events
                self.hass.bus.async_fire("pawcontrol_walk_started", {
                    "dog_id": dog,
                    "walk_type": walk_type or "normal",
                    "timestamp": now.isoformat(),
                })
                
                # Update state
                self.hass.states.async_set(
                    f"sensor.{DOMAIN}_{dog}_walk_started", 
                    now.isoformat(),
                    {"walk_type": walk_type or "normal"}
                )
                
                _LOGGER.info("Started walk for dog %s (type: %s)", dog, walk_type or "normal")
                
            except Exception as exc:
                _LOGGER.error("Failed to start walk for dog %s: %s", dog_id, exc)

    async def async_end_walk(self, rating: int | None = None, notes: str | None = None, dog_id: str | None = None) -> None:
        """End a walk for a dog."""
        async with self._location_lock:
            try:
                dog = self._dog_id(dog_id)
                route_data = self._get_route_data(dog)
                
                if not route_data["active"]:
                    _LOGGER.warning("No active walk for dog %s", dog)
                    return
                
                end_time = _now()
                start_time = route_data.get("start") or end_time
                
                # Calculate metrics
                if isinstance(start_time, datetime):
                    duration_s = (end_time - start_time).total_seconds()
                else:
                    duration_s = 0.0
                    
                dist_m = float(route_data.get("distance_m") or 0.0)
                avg_kmh = (dist_m/1000.0) / (duration_s/3600.0) if duration_s > 0 else 0.0
                
                # Validate rating
                if rating is not None:
                    rating = max(1, min(5, int(rating)))
                
                # Update state entities with validation
                self._safe_state_update(f"sensor.{DOMAIN}_{dog}_walk_distance_last", dist_m, {"unit_of_measurement": "m"})
                self._safe_state_update(f"sensor.{DOMAIN}_{dog}_walk_duration_last", int(duration_s), {"unit_of_measurement": "s"})
                self._safe_state_update(f"sensor.{DOMAIN}_{dog}_walk_avg_speed_last", round(avg_kmh, 2), {"unit_of_measurement": "km/h"})
                
                # Fire events
                self.hass.bus.async_fire("pawcontrol_walk_finished", {
                    "dog_id": dog,
                    "distance_m": dist_m,
                    "duration_s": duration_s,
                    "avg_speed_kmh": avg_kmh,
                    "rating": rating,
                    "notes": notes or "",
                    "points_count": len(route_data.get("points", [])),
                })
                
                # Mark as inactive
                route_data["active"] = False
                route_data["end"] = end_time
                
                # Persist route summary
                await self._persist_route_summary(dog, start_time, end_time, dist_m, duration_s, len(route_data.get("points", [])))
                
                _LOGGER.info("Ended walk for dog %s: %.1fm in %.0fs", dog, dist_m, duration_s)
                
            except Exception as exc:
                _LOGGER.error("Failed to end walk for dog %s: %s", dog_id, exc)

    def _safe_state_update(self, entity_id: str, value: Any, attributes: dict | None = None) -> None:
        """Safely update entity state with validation."""
        try:
            self.hass.states.async_set(entity_id, value, attributes or {})
        except Exception as exc:
            _LOGGER.debug("Failed to update state %s: %s", entity_id, exc)

    async def _persist_route_summary(self, dog: str, start_time: datetime, end_time: datetime, 
                                   distance_m: float, duration_s: float, points_count: int) -> None:
        """Persist route summary to storage."""
        try:
            from .route_store import RouteHistoryStore
            
            store = RouteHistoryStore(self.hass, self.entry_id or "default", DOMAIN)
            
            # Get route history limit from options
            limit = 500
            try:
                advanced = (self.options or {}).get("advanced", {})
                limit = int(advanced.get("route_history_limit", 500))
            except (ValueError, TypeError):
                pass
            
            await store.async_add_walk(
                self.hass,
                self.entry_id or "default",
                DOMAIN,
                dog,
                start_time.isoformat() if isinstance(start_time, datetime) else None,
                end_time.isoformat(),
                distance_m,
                duration_s,
                points_count,
                limit=limit
            )
        except Exception as exc:
            _LOGGER.debug("Failed to persist route summary: %s", exc)

    async def async_update_location(self, latitude: float, longitude: float, 
                                  accuracy: float | None = None, source: str | None = None, 
                                  dog_id: str | None = None) -> None:
        """Update GPS location for a dog with comprehensive validation and filtering."""
        async with self._location_lock:
            try:
                # Validate input parameters
                try:
                    lat = float(latitude)
                    lon = float(longitude)
                    acc = float(accuracy) if accuracy is not None else None
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid GPS coordinates: lat=%s, lon=%s, acc=%s", latitude, longitude, accuracy)
                    return
                
                # Validate coordinate ranges
                if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                    _LOGGER.warning("GPS coordinates out of range: lat=%s, lon=%s", lat, lon)
                    return
                
                # Validate accuracy
                if acc is not None and (acc < 0 or acc > 10000):
                    _LOGGER.debug("GPS accuracy out of reasonable range: %s", acc)
                    acc = None
                
                dog = self._dog_id(dog_id)
                route_data = self._get_route_data(dog)
                now = _now()
                now_iso = now.isoformat()
                
                # Rate limiting: skip if update too frequent (< 5 seconds)
                last_update = self._last_location_update.get(dog)
                if last_update and (now - last_update).total_seconds() < 5:
                    return
                self._last_location_update[dog] = now
                
                # Create GPS point
                new_point = GPSPoint(lat, lon, now_iso, acc)
                points = route_data["points"]
                
                # Distance calculation and filtering
                distance_increment = 0.0
                should_add_point = True
                
                if points:
                    try:
                        last_point_data = points[-1]
                        if isinstance(last_point_data, tuple) and len(last_point_data) >= 2:
                            last_lat, last_lon = last_point_data[0], last_point_data[1]
                            distance_increment = _haversine_m(last_lat, last_lon, lat, lon)
                            
                            # Filter out points that are too close (noise reduction)
                            if distance_increment < GPS_POINT_FILTER_DISTANCE and not route_data.get("active"):
                                should_add_point = False
                    except (IndexError, TypeError, ValueError):
                        pass
                
                # Add point if it passes filters
                if should_add_point:
                    points.append(new_point.to_tuple())
                    route_data["distance_m"] = float(route_data.get("distance_m", 0.0)) + distance_increment
                    route_data["last_update"] = now
                    
                    # Limit points to prevent memory issues
                    if len(points) > GPS_MAX_POINTS_PER_ROUTE:
                        points.pop(0)  # Remove oldest point
                        self._get_metrics(dog)["points_dropped"] += 1
                
                # Update current walk distance if active
                if route_data.get("active"):
                    self._safe_state_update(
                        f"sensor.{DOMAIN}_{dog}_walk_distance_current",
                        round(route_data["distance_m"], 1),
                        {"unit_of_measurement": "m", "source": source or "unknown"}
                    )
                
                # Dispatch to device tracker & events
                async_dispatcher_send(self.hass, f"{DOMAIN}_gps_update_{dog}", lat, lon, acc)
                
                self.hass.bus.async_fire("pawcontrol_route_point", {
                    "dog_id": dog,
                    "lat": lat,
                    "lon": lon,
                    "acc": acc,
                    "ts": now_iso,
                    "source": source or "unknown",
                })
                
                # Skip accumulation if paused
                if route_data.get("paused"):
                    return
                
                # Accumulate daily distance
                if distance_increment > 0:
                    _inc_state(
                        self.hass,
                        f"sensor.{DOMAIN}_{dog}_walk_distance_today",
                        distance_increment,
                        {"unit_of_measurement": "m"}
                    )
                
                # Duration accumulation for active walks
                await self._update_duration_tracking(dog, points, route_data)
                
                # GPS metrics tracking
                await self._update_gps_metrics(dog, acc)
                
                # Safe zone evaluation
                await self._evaluate_safe_zone(dog, lat, lon)
                
            except Exception as exc:
                _LOGGER.error("Failed to update location for dog %s: %s", dog_id, exc)

    async def _update_duration_tracking(self, dog: str, points: List, route_data: Dict[str, Any]) -> None:
        """Update duration tracking for active walks."""
        try:
            if len(points) >= 2 and route_data.get("active"):
                prev_point = points[-2]
                if isinstance(prev_point, tuple) and len(prev_point) >= 3:
                    prev_time_str = prev_point[2]
                    try:
                        prev_time = datetime.fromisoformat(prev_time_str.replace("Z", "+00:00"))
                        current_time = _now()
                        time_delta = (current_time - prev_time).total_seconds()
                        
                        if 0 < time_delta < 300:  # Only count reasonable time deltas (< 5 minutes)
                            _inc_state(
                                self.hass,
                                f"sensor.{DOMAIN}_{dog}_walk_time_today",
                                time_delta,
                                {"unit_of_measurement": "s"}
                            )
                    except (ValueError, TypeError) as exc:
                        _LOGGER.debug("Failed to parse timestamp for duration tracking: %s", exc)
        except Exception as exc:
            _LOGGER.debug("Duration tracking failed for dog %s: %s", dog, exc)

    async def _update_gps_metrics(self, dog: str, accuracy: float | None) -> None:
        """Update GPS metrics and diagnostics."""
        try:
            metrics = self._get_metrics(dog)
            metrics["points_total"] = int(metrics.get("points_total", 0)) + 1
            
            # Update accuracy metrics
            if accuracy is not None and accuracy > 0:
                metrics["acc_sum"] = float(metrics.get("acc_sum", 0.0)) + float(accuracy)
                metrics["acc_count"] = int(metrics.get("acc_count", 0)) + 1
                
                avg_accuracy = metrics["acc_sum"] / max(1, metrics["acc_count"])
                self._safe_state_update(
                    f"sensor.{DOMAIN}_{dog}_gps_accuracy_avg",
                    round(avg_accuracy, 1),
                    {"unit_of_measurement": "m"}
                )
            
            # Update total points
            self._safe_state_update(f"sensor.{DOMAIN}_{dog}_gps_points_total", metrics["points_total"])
            
        except Exception as exc:
            _LOGGER.debug("GPS metrics update failed for dog %s: %s", dog, exc)

    async def _evaluate_safe_zone(self, dog: str, latitude: float, longitude: float) -> None:
        """Evaluate safe zone status for a dog with comprehensive error handling."""
        try:
            zone_config = (self._settings or {}).get("safe_zones", {}).get(dog) or {}
            if not zone_config:
                return
            
            # Validate zone configuration
            try:
                zone_lat = float(zone_config.get("latitude", 0))
                zone_lon = float(zone_config.get("longitude", 0))
                radius = float(zone_config.get("radius", 50))
                enable_alerts = bool(zone_config.get("enable_alerts", True))
            except (ValueError, TypeError):
                _LOGGER.debug("Invalid safe zone configuration for dog %s", dog)
                return
            
            # Validate zone coordinates
            if not (-90 <= zone_lat <= 90) or not (-180 <= zone_lon <= 180):
                return
            
            # Calculate distance and determine if inside
            distance = _haversine_m(zone_lat, zone_lon, latitude, longitude)
            inside = distance <= radius
            now_dt = _now()
            
            safe_status = self._get_safe_status(dog)
            prev_inside = safe_status.get("inside")
            
            # Time accumulation when inside zone
            last_ts = safe_status.get("last_ts")
            if last_ts and isinstance(last_ts, datetime) and prev_inside is True:
                time_delta = (now_dt - last_ts).total_seconds()
                if 0 < time_delta < 3600:  # Reasonable time delta (< 1 hour)
                    safe_status["time_today"] = float(safe_status.get("time_today", 0.0)) + time_delta
            
            # Transition detection and counting
            if prev_inside is not None and inside != prev_inside:
                if inside:
                    safe_status["enters"] = int(safe_status.get("enters", 0)) + 1
                    event_name = "pawcontrol_safe_zone_entered"
                else:
                    safe_status["leaves"] = int(safe_status.get("leaves", 0)) + 1
                    event_name = "pawcontrol_safe_zone_left"
                
                # Fire transition event if alerts enabled
                if enable_alerts:
                    self.hass.bus.async_fire(event_name, {
                        "dog_id": dog,
                        "distance_m": round(distance, 1),
                        "radius_m": radius,
                        "timestamp": now_dt.isoformat(),
                    })
            
            # Update status
            safe_status.update({
                "inside": inside,
                "last_ts": now_dt,
                "last_distance": round(distance, 1),
                "last_radius": radius,
            })
            
            # Update state entities
            self._safe_state_update(f"sensor.{DOMAIN}_{dog}_time_in_safe_zone_today", int(safe_status.get("time_today", 0.0)), {"unit_of_measurement": "s"})
            self._safe_state_update(f"sensor.{DOMAIN}_{dog}_safe_zone_enters_today", safe_status.get("enters", 0))
            self._safe_state_update(f"sensor.{DOMAIN}_{dog}_safe_zone_leaves_today", safe_status.get("leaves", 0))
            
            # Dispatch to binary_sensor
            async_dispatcher_send(
                self.hass,
                f"pawcontrol_safe_zone_update_{dog}",
                inside,
                distance,
                radius
            )
            
        except Exception as exc:
            _LOGGER.debug("Safe zone evaluation failed for dog %s: %s", dog, exc)

    async def async_pause_tracking(self, dog_id: str | None = None) -> None:
        """Pause GPS tracking for a dog."""
        try:
            dog = self._dog_id(dog_id)
            route_data = self._get_route_data(dog)
            route_data["paused"] = True
            
            self._safe_state_update(f"sensor.{DOMAIN}_{dog}_gps_tracking_paused", True)
            _LOGGER.info("GPS tracking paused for dog %s", dog)
        except Exception as exc:
            _LOGGER.error("Failed to pause tracking for dog %s: %s", dog_id, exc)

    async def async_resume_tracking(self, dog_id: str | None = None) -> None:
        """Resume GPS tracking for a dog."""
        try:
            dog = self._dog_id(dog_id)
            route_data = self._get_route_data(dog)
            route_data["paused"] = False
            
            self._safe_state_update(f"sensor.{DOMAIN}_{dog}_gps_tracking_paused", False)
            _LOGGER.info("GPS tracking resumed for dog %s", dog)
        except Exception as exc:
            _LOGGER.error("Failed to resume tracking for dog %s: %s", dog_id, exc)

    async def async_export_last_route(self, dog_id: str | None = None, fmt: str = "geojson", to_media: bool = False) -> str | None:
        """Export the last route for a dog with multiple format support."""
        try:
            dog = self._dog_id(dog_id)
            route_data = self._get_route_data(dog)
            
            # Determine export path
            if to_media:
                base_path = self.hass.config.path("media/pawcontrol_routes")
            else:
                base_path = self.hass.config.path("pawcontrol_routes")
            
            os.makedirs(base_path, exist_ok=True)
            
            points = route_data.get("points", [])
            if not points:
                _LOGGER.warning("No route points available for dog %s", dog)
                return None
            
            timestamp = _now().strftime("%Y%m%d_%H%M%S")
            
            if fmt.lower() == "geojson":
                return await self._export_geojson(dog, points, base_path, timestamp)
            elif fmt.lower() == "gpx":
                return await self._export_gpx(dog, points, base_path, timestamp)
            elif fmt.lower() == "kml":
                return await self._export_kml(dog, points, base_path, timestamp)
            else:
                _LOGGER.error("Unsupported export format: %s", fmt)
                return None
                
        except Exception as exc:
            _LOGGER.error("Failed to export route for dog %s: %s", dog_id, exc)
            return None

    async def _export_geojson(self, dog: str, points: List, base_path: str, timestamp: str) -> str:
        """Export route as GeoJSON."""
        try:
            coordinates = []
            for point in points:
                if isinstance(point, tuple) and len(point) >= 2:
                    # GeoJSON uses [lon, lat] order
                    coordinates.append([float(point[1]), float(point[0])])
            
            feature = {
                "type": "Feature",
                "properties": {
                    "dog_id": dog,
                    "timestamp": timestamp,
                    "point_count": len(coordinates),
                    "distance_m": self._get_route_data(dog).get("distance_m", 0),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates
                }
            }
            
            data = {
                "type": "FeatureCollection",
                "features": [feature]
            }
            
            file_path = os.path.join(base_path, f"{dog}_route_{timestamp}.geojson")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return file_path
        except Exception as exc:
            _LOGGER.error("GeoJSON export failed: %s", exc)
            raise

    async def _export_gpx(self, dog: str, points: List, base_path: str, timestamp: str) -> str:
        """Export route as GPX."""
        try:
            file_path = os.path.join(base_path, f"{dog}_route_{timestamp}.gpx")
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write('<gpx version="1.1" creator="PawControl">\n')
                f.write(f'  <trk>\n    <name>{dog} Route {timestamp}</name>\n    <trkseg>\n')
                
                for point in points:
                    if isinstance(point, tuple) and len(point) >= 2:
                        lat, lon = float(point[0]), float(point[1])
                        time_str = point[2] if len(point) > 2 else ""
                        f.write(f'      <trkpt lat="{lat}" lon="{lon}">')
                        if time_str:
                            f.write(f'<time>{time_str}</time>')
                        f.write('</trkpt>\n')
                
                f.write('    </trkseg>\n  </trk>\n</gpx>')
            
            return file_path
        except Exception as exc:
            _LOGGER.error("GPX export failed: %s", exc)
            raise

    async def _export_kml(self, dog: str, points: List, base_path: str, timestamp: str) -> str:
        """Export route as KML."""
        try:
            file_path = os.path.join(base_path, f"{dog}_route_{timestamp}.kml")
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write('<kml xmlns="http://www.opengis.net/kml/2.2">\n')
                f.write('  <Document>\n')
                f.write(f'    <name>{dog} Route {timestamp}</name>\n')
                f.write('    <Placemark>\n')
                f.write(f'      <name>{dog} Walk</name>\n')
                f.write('      <LineString>\n')
                f.write('        <coordinates>')
                
                for point in points:
                    if isinstance(point, tuple) and len(point) >= 2:
                        lat, lon = float(point[0]), float(point[1])
                        f.write(f'{lon},{lat},0 ')
                
                f.write('</coordinates>\n')
                f.write('      </LineString>\n')
                f.write('    </Placemark>\n')
                f.write('  </Document>\n')
                f.write('</kml>')
            
            return file_path
        except Exception as exc:
            _LOGGER.error("KML export failed: %s", exc)
            raise

    async def async_generate_diagnostics(self, dog_id: str | None = None) -> str | None:
        """Generate comprehensive diagnostics file for a dog."""
        try:
            dog = self._dog_id(dog_id)
            
            base_path = self.hass.config.path("pawcontrol_diagnostics")
            os.makedirs(base_path, exist_ok=True)
            
            route_data = self._get_route_data(dog)
            metrics = self._get_metrics(dog)
            safe_status = self._get_safe_status(dog)
            
            # Limit points in diagnostics to prevent huge files
            points = route_data.get("points", [])
            limited_points = points[-1000:] if len(points) > 1000 else points
            
            diagnostics_data = {
                "dog_id": dog,
                "timestamp": _now().isoformat(),
                "route_data": {
                    "active": route_data.get("active"),
                    "distance_m": route_data.get("distance_m"),
                    "points_count": len(points),
                    "points_sample": limited_points,
                    "paused": route_data.get("paused"),
                    "start": route_data.get("start").isoformat() if isinstance(route_data.get("start"), datetime) else None,
                },
                "metrics": metrics,
                "safe_status": safe_status,
                "options": self.options,
                "settings": self._settings,
            }
            
            file_path = os.path.join(base_path, f"{dog}_diagnostics.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(diagnostics_data, f, ensure_ascii=False, indent=2, default=str)
            
            _LOGGER.info("Generated diagnostics for dog %s: %s", dog, file_path)
            return file_path
            
        except Exception as exc:
            _LOGGER.error("Failed to generate diagnostics for dog %s: %s", dog_id, exc)
            return None

    async def async_reset_gps_stats(self, dog_id: str | None = None) -> None:
        """Reset GPS statistics for a dog."""
        try:
            dog = self._dog_id(dog_id)
            
            # Reset metrics
            self._metrics[dog] = {
                "points_total": 0,
                "points_dropped": 0,
                "acc_sum": 0.0,
                "acc_count": 0,
            }
            
            # Reset state entities
            self._safe_state_update(f"sensor.{DOMAIN}_{dog}_gps_points_total", 0)
            self._safe_state_update(f"sensor.{DOMAIN}_{dog}_gps_points_dropped", 0)
            self._safe_state_update(f"sensor.{DOMAIN}_{dog}_gps_accuracy_avg", None)
            
            _LOGGER.info("GPS statistics reset for dog %s", dog)
            
        except Exception as exc:
            _LOGGER.error("Failed to reset GPS stats for dog %s: %s", dog_id, exc)

    def get_route_summary(self, dog_id: str | None = None) -> Dict[str, Any]:
        """Get current route summary for a dog."""
        try:
            dog = self._dog_id(dog_id)
            route_data = self._get_route_data(dog)
            metrics = self._get_metrics(dog)
            
            return {
                "dog_id": dog,
                "active": route_data.get("active", False),
                "distance_m": route_data.get("distance_m", 0.0),
                "points_count": len(route_data.get("points", [])),
                "paused": route_data.get("paused", False),
                "start_time": route_data.get("start"),
                "last_update": route_data.get("last_update"),
                "metrics": metrics,
            }
        except Exception as exc:
            _LOGGER.error("Failed to get route summary for dog %s: %s", dog_id, exc)
            return {}
