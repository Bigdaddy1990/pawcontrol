"""Coordinator for PawControl integration.

Simplified coordinator with session management and intelligent caching
for Platinum quality compliance without overengineering.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_EXTERNAL_INTEGRATIONS,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_WEATHER_ENTITY,
    MODULE_FEEDING,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    MODULE_WEATHER,
    UPDATE_INTERVALS,
)
from .exceptions import (
    GPSUnavailableError,
    NetworkError,
    RateLimitError,
    ValidationError,
)
from .types import DogConfigData, PawControlConfigEntry

if TYPE_CHECKING:
    from .data_manager import PawControlDataManager
    from .feeding_manager import FeedingManager
    from .garden_manager import GardenManager
    from .gps_manager import GPSGeofenceManager
    from .notifications import PawControlNotificationManager
    from .walk_manager import WalkManager
    from .weather_manager import WeatherHealthManager

_LOGGER = logging.getLogger(__name__)

# PLATINUM: Optimized constants
API_TIMEOUT = 30.0
CACHE_TTL_SECONDS = 300  # 5 minutes
MAINTENANCE_INTERVAL = timedelta(hours=1)
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 1.5


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for PawControl integration.

    Enhanced coordinator focused on reliability, maintainability and performance
    while meeting all Platinum quality requirements with specific error handling.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PawControlConfigEntry,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize coordinator with session management and enhanced caching.

        Args:
            hass: Home Assistant instance
            entry: Config entry for this integration with typed runtime data
            session: Optional aiohttp session for external API calls

        Raises:
            ConfigEntryNotReady: If initialization prerequisites are not met
            ValidationError: If entry configuration is invalid
        """
        self.config_entry = entry
        self.session = session or async_get_clientsession(hass)

        # PLATINUM: Enhanced configuration validation
        try:
            self._dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
            if not isinstance(self._dogs_config, list):
                raise ValidationError(
                    "dogs_config",
                    type(self._dogs_config).__name__,
                    "Must be a list of dog configurations",
                )
        except (KeyError, TypeError) as err:
            raise ValidationError(
                "dogs_config", None, f"Invalid dogs configuration: {err}"
            ) from err

        self._use_external_api = bool(
            entry.options.get(CONF_EXTERNAL_INTEGRATIONS, False)
        )

        # Enhanced TTL-based cache with performance tracking
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        # Calculate update interval with validation
        try:
            update_interval = self._calculate_update_interval()
            if update_interval <= 0:
                raise ValueError("Update interval must be positive")
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Invalid update interval calculation: %s", err)
            update_interval = UPDATE_INTERVALS.get("balanced", 120)

        # PLATINUM: Pass config_entry to coordinator for proper type safety
        super().__init__(
            hass,
            _LOGGER,
            name="PawControl Data",
            update_interval=timedelta(seconds=update_interval),
            config_entry=entry,
        )

        # Runtime data and performance tracking
        self._data: dict[str, dict[str, Any]] = {}
        self._update_count = 0
        self._error_count = 0
        self._consecutive_errors = 0
        self._maintenance_unsub: callback | None = None

        # Runtime manager references (TYPE_CHECKING imports)
        self.data_manager: PawControlDataManager | None = None
        self.feeding_manager: FeedingManager | None = None
        self.walk_manager: WalkManager | None = None
        self.notification_manager: PawControlNotificationManager | None = None
        self.gps_geofence_manager: GPSGeofenceManager | None = None
        self.weather_health_manager: WeatherHealthManager | None = None
        self.garden_manager: GardenManager | None = None

        _LOGGER.info(
            "Coordinator initialized: %d dogs, %ds interval, external_api=%s",
            len(self._dogs_config),
            update_interval,
            self._use_external_api,
        )

    @property
    def use_external_api(self) -> bool:
        """Return whether external integrations are enabled."""
        return self._use_external_api

    @use_external_api.setter
    def use_external_api(self, value: bool) -> None:
        """Update the external API usage flag."""
        self._use_external_api = bool(value)

    def attach_runtime_managers(
        self,
        *,
        data_manager: PawControlDataManager,
        feeding_manager: FeedingManager,
        walk_manager: WalkManager,
        notification_manager: PawControlNotificationManager,
        gps_geofence_manager: GPSGeofenceManager | None = None,
        weather_health_manager: WeatherHealthManager | None = None,
        garden_manager: GardenManager | None = None,
    ) -> None:
        """Attach runtime managers for service integration.

        Args:
            data_manager: Data management service
            feeding_manager: Feeding tracking service
            walk_manager: Walk tracking service
            notification_manager: Notification service
            gps_geofence_manager: GPS and geofencing service (optional)
            weather_health_manager: Weather health service (optional)
        """
        self.data_manager = data_manager
        self.feeding_manager = feeding_manager
        self.walk_manager = walk_manager
        self.notification_manager = notification_manager
        self.gps_geofence_manager = gps_geofence_manager
        self.weather_health_manager = weather_health_manager
        self.garden_manager = garden_manager
        _LOGGER.debug(
            "Runtime managers attached (gps_geofence: %s, weather: %s)",
            bool(gps_geofence_manager),
            bool(weather_health_manager),
        )

    def clear_runtime_managers(self) -> None:
        """Clear runtime manager references during unload."""
        self.data_manager = None
        self.feeding_manager = None
        self.walk_manager = None
        self.notification_manager = None
        self.gps_geofence_manager = None
        self.weather_health_manager = None
        self.garden_manager = None

    def _get_cache(self, key: str) -> Any | None:
        """Get item from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
        if key not in self._cache:
            self._cache_misses += 1
            return None

        data, timestamp = self._cache[key]
        if (dt_util.utcnow() - timestamp).total_seconds() > CACHE_TTL_SECONDS:
            del self._cache[key]
            self._cache_misses += 1
            return None

        self._cache_hits += 1
        return data

    def _set_cache(self, key: str, data: Any) -> None:
        """Set item in cache with timestamp.

        Args:
            key: Cache key
            data: Data to cache
        """
        self._cache[key] = (data, dt_util.utcnow())

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data for all dogs efficiently with enhanced error handling.

        Returns:
            Dictionary mapping dog_id to dog data

        Raises:
            UpdateFailed: If all dogs fail or critical errors occur
            ConfigEntryAuthFailed: If authentication fails
            ConfigEntryNotReady: If coordinator is not ready
        """
        if not self._dogs_config:
            return {}

        self._update_count += 1
        all_data: dict[str, dict[str, Any]] = {}
        errors = 0

        # PLATINUM: Enhanced dog ID validation
        dog_ids: list[str] = []
        for dog in self._dogs_config:
            dog_id = dog.get(CONF_DOG_ID)
            if isinstance(dog_id, str) and dog_id.strip():
                dog_ids.append(dog_id.strip())
            else:
                _LOGGER.warning("Skipping dog with invalid identifier: %s", dog_id)

        if not dog_ids:
            self._error_count += 1
            raise UpdateFailed("No valid dogs configured")

        # PLATINUM: Enhanced concurrent fetch with specific error handling
        async def fetch_and_store(dog_id: str) -> None:
            nonlocal errors
            retry_count = 0
            last_error: Exception | None = None

            while retry_count < MAX_RETRY_ATTEMPTS:
                try:
                    async with asyncio.timeout(API_TIMEOUT):
                        all_data[dog_id] = await self._fetch_dog_data(dog_id)
                    return  # Success, exit retry loop

                except TimeoutError as err:
                    last_error = err
                    _LOGGER.warning(
                        "Timeout fetching data for dog %s (attempt %d/%d): %s",
                        dog_id,
                        retry_count + 1,
                        MAX_RETRY_ATTEMPTS,
                        err,
                    )
                except ConfigEntryAuthFailed:
                    # Authentication errors should not be retried
                    raise
                except (ClientError, NetworkError) as err:
                    last_error = err
                    _LOGGER.warning(
                        "Network error fetching data for dog %s (attempt %d/%d): %s",
                        dog_id,
                        retry_count + 1,
                        MAX_RETRY_ATTEMPTS,
                        err,
                    )
                except RateLimitError as err:
                    last_error = err
                    _LOGGER.warning(
                        "Rate limit hit for dog %s, waiting %s seconds",
                        dog_id,
                        err.retry_after or 60,
                    )
                    if err.retry_after:
                        await asyncio.sleep(min(err.retry_after, 300))  # Max 5 min wait
                except ValidationError as err:
                    # Data validation errors shouldn't be retried
                    errors += 1
                    _LOGGER.error("Invalid configuration for dog %s: %s", dog_id, err)
                    all_data[dog_id] = self._get_empty_dog_data()
                    return
                except HomeAssistantError as err:
                    last_error = err
                    _LOGGER.warning(
                        "HA error fetching data for dog %s (attempt %d/%d): %s",
                        dog_id,
                        retry_count + 1,
                        MAX_RETRY_ATTEMPTS,
                        err,
                    )

                retry_count += 1
                if retry_count < MAX_RETRY_ATTEMPTS:
                    # Exponential backoff
                    wait_time = min(2**retry_count * RETRY_BACKOFF_FACTOR, 30)
                    await asyncio.sleep(wait_time)

            # All retries failed
            errors += 1
            _LOGGER.error(
                "Failed to fetch data for dog %s after %d attempts, last error: %s",
                dog_id,
                MAX_RETRY_ATTEMPTS,
                last_error,
            )
            all_data[dog_id] = self._data.get(dog_id, self._get_empty_dog_data())

        # Execute with proper task group error handling
        try:
            async with asyncio.TaskGroup() as task_group:
                for dog_id in dog_ids:
                    task_group.create_task(fetch_and_store(dog_id))
        except* ConfigEntryAuthFailed as auth_error_group:
            # Re-raise authentication failures
            raise auth_error_group.exceptions[0]  # noqa: B904
        except* Exception as error_group:
            # Log other task group errors but continue
            for exc in error_group.exceptions:
                _LOGGER.error("Task group error: %s", exc)

        # PLATINUM: Enhanced failure analysis
        total_dogs = len(dog_ids)
        success_rate = ((total_dogs - errors) / total_dogs) if total_dogs > 0 else 0

        if errors == total_dogs:
            self._error_count += 1
            self._consecutive_errors += 1
            raise UpdateFailed(f"All {total_dogs} dogs failed to update")

        if success_rate < 0.5:  # More than 50% failed
            self._consecutive_errors += 1
            _LOGGER.warning(
                "Low success rate: %d/%d dogs updated successfully",
                total_dogs - errors,
                total_dogs,
            )
        else:
            self._consecutive_errors = 0  # Reset on good update

        self._data = all_data
        return self._data

    def get_update_statistics(self) -> dict[str, Any]:
        """Return coordinator update metrics for diagnostics and system health.

        Returns:
            Dictionary containing update statistics and performance metrics
        """
        successful_updates = max(self._update_count - self._error_count, 0)
        cache_entries = len(self._cache)
        total_cache_requests = self._cache_hits + self._cache_misses
        cache_hit_rate = (
            (self._cache_hits / total_cache_requests * 100)
            if total_cache_requests > 0
            else 0
        )

        return {
            "update_counts": {
                "total": self._update_count,
                "successful": successful_updates,
                "failed": self._error_count,
                "consecutive_errors": self._consecutive_errors,
            },
            "performance_metrics": {
                "api_calls": self._update_count if self._use_external_api else 0,
                "cache_entries": cache_entries,
                "cache_hit_rate": round(cache_hit_rate, 1),
                "cache_ttl": CACHE_TTL_SECONDS,
            },
            "health_indicators": {
                "success_rate": round(
                    (successful_updates / max(self._update_count, 1)) * 100, 1
                ),
                "is_healthy": self._consecutive_errors < 3,
                "external_api_enabled": self._use_external_api,
            },
        }

    async def _fetch_dog_data(self, dog_id: str) -> dict[str, Any]:
        """Fetch data for a single dog with enhanced error handling.

        Args:
            dog_id: Dog identifier

        Returns:
            Dog data dictionary

        Raises:
            ValidationError: If dog configuration is invalid
            NetworkError: If network-related errors occur
            ConfigEntryAuthFailed: If authentication fails
        """
        dog_config = self.get_dog_config(dog_id)
        if not dog_config:
            raise ValidationError("dog_id", dog_id, "Dog configuration not found")

        data = {
            "dog_info": dog_config,
            "status": "online",
            "last_update": dt_util.utcnow().isoformat(),
        }

        modules = dog_config.get("modules", {})

        # PLATINUM: Enhanced module data fetching with specific error handling
        module_tasks = []
        if modules.get(MODULE_FEEDING):
            module_tasks.append(("feeding", self._get_feeding_data(dog_id)))
        if modules.get(MODULE_WALK):
            module_tasks.append(("walk", self._get_walk_data(dog_id)))
        if modules.get(MODULE_GPS):
            module_tasks.append(("gps", self._get_gps_data(dog_id)))
            # Include geofencing data if GPS manager is available and GPS is enabled
            if self.gps_geofence_manager:
                module_tasks.append(("geofencing", self._get_geofencing_data(dog_id)))
        if modules.get(MODULE_HEALTH):
            module_tasks.append(("health", self._get_health_data(dog_id)))
        if modules.get(MODULE_WEATHER):
            module_tasks.append(("weather", self._get_weather_data(dog_id)))
        if modules.get(MODULE_GARDEN):
            module_tasks.append(("garden", self._get_garden_data(dog_id)))

        # Execute module tasks concurrently with enhanced error handling
        if module_tasks:
            results = await asyncio.gather(
                *(task for _, task in module_tasks), return_exceptions=True
            )

            for (module_name, _), result in zip(module_tasks, results, strict=False):
                if isinstance(result, Exception):
                    # PLATINUM: Module-specific error handling
                    if isinstance(result, GPSUnavailableError):
                        _LOGGER.debug("GPS unavailable for %s: %s", dog_id, result)
                        data[module_name] = {
                            "status": "unavailable",
                            "reason": str(result),
                        }
                    elif isinstance(result, NetworkError):
                        _LOGGER.warning(
                            "Network error fetching %s data for %s: %s",
                            module_name,
                            dog_id,
                            result,
                        )
                        data[module_name] = {"status": "network_error"}
                    else:
                        _LOGGER.warning(
                            "Failed to fetch %s data for %s: %s (%s)",
                            module_name,
                            dog_id,
                            result,
                            result.__class__.__name__,
                        )
                        data[module_name] = {"status": "error"}
                else:
                    data[module_name] = result

        return data

    async def _get_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Get feeding data for dog with caching and error handling.

        Args:
            dog_id: Dog identifier

        Returns:
            Feeding data dictionary

        Raises:
            NetworkError: If external API call fails
        """
        cache_key = f"feeding_{dog_id}"
        if (cached := self._get_cache(cache_key)) is not None:
            return cached

        # Prefer local feeding manager data for Platinum compliance
        if self.feeding_manager:
            try:
                data = await self.feeding_manager.async_get_feeding_data(dog_id)
                feeding_data = dict(data)
                feeding_data.setdefault("status", "ready")
                self._set_cache(cache_key, feeding_data)
                return feeding_data
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.debug(
                    "Feeding manager data unavailable for %s: %s", dog_id, err
                )

        try:
            if self._use_external_api:
                async with self.session.get(
                    f"/api/dogs/{dog_id}/feeding", timeout=ClientTimeout(total=10.0)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._set_cache(cache_key, data)
                        return data
                    elif resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        raise RateLimitError(
                            "feeding_data",
                            retry_after=int(retry_after) if retry_after else 60,
                        )
                    elif resp.status >= 400:
                        raise NetworkError(f"HTTP {resp.status}")
        except ClientError as err:
            raise NetworkError(f"Client error: {err}") from err

        # Default data
        default_data = {
            "last_feeding": None,
            "feedings_today": {},
            "total_feedings_today": 0,
            "daily_amount_consumed": 0.0,
            "daily_portions": 0,
            "feeding_schedule": [],
            "status": "ready",
            "daily_calorie_target": None,
            "total_calories_today": 0.0,
            "portion_adjustment_factor": None,
            "health_feeding_status": "insufficient_data",
            "medication_with_meals": False,
            "health_aware_feeding": False,
            "health_conditions": [],
            "daily_activity_level": None,
            "weight_goal": None,
            "weight_goal_progress": None,
            "health_emergency": False,
            "emergency_mode": None,
        }
        self._set_cache(cache_key, default_data)
        return default_data

    async def _get_walk_data(self, dog_id: str) -> dict[str, Any]:
        """Get walk data for dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Walk data dictionary
        """
        return {
            "current_walk": None,
            "last_walk": None,
            "daily_walks": 0,
            "total_distance": 0.0,
            "status": "ready",
        }

    async def _get_gps_data(self, dog_id: str) -> dict[str, Any]:
        """Get GPS data for dog.

        Args:
            dog_id: Dog identifier

        Returns:
            GPS data dictionary

        Raises:
            GPSUnavailableError: If GPS data is not available
        """
        if not self.gps_geofence_manager:
            raise GPSUnavailableError(dog_id, "GPS manager not available")

        try:
            # Get current location
            current_location = (
                await self.gps_geofence_manager.async_get_current_location(dog_id)
            )

            # Get active route if any
            active_route = await self.gps_geofence_manager.async_get_active_route(
                dog_id
            )

            return {
                "latitude": current_location.latitude if current_location else None,
                "longitude": current_location.longitude if current_location else None,
                "accuracy": current_location.accuracy if current_location else None,
                "last_update": current_location.timestamp.isoformat()
                if current_location
                else None,
                "source": current_location.source.value if current_location else None,
                "status": "tracking"
                if active_route and active_route.is_active
                else "ready",
                "active_route": {
                    "start_time": active_route.start_time.isoformat(),
                    "duration_minutes": active_route.duration_minutes,
                    "distance_km": active_route.distance_km,
                    "points_count": len(active_route.gps_points),
                }
                if active_route and active_route.is_active
                else None,
            }

        except Exception as err:
            _LOGGER.warning("Failed to get GPS data for %s: %s", dog_id, err)
            raise GPSUnavailableError(dog_id, str(err)) from err

    async def _get_health_data(self, dog_id: str) -> dict[str, Any]:
        """Get health data for dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Health data dictionary
        """
        health_data: dict[str, Any] = {
            "weight": None,
            "ideal_weight": None,
            "last_vet_visit": None,
            "medications": [],
            "health_alerts": [],
            "status": "healthy",
        }

        feeding_context: dict[str, Any] = {}
        if self.feeding_manager:
            try:
                feeding_context = await self.feeding_manager.async_get_feeding_data(
                    dog_id
                )
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.debug(
                    "Failed to gather feeding context for %s: %s", dog_id, err
                )

        if feeding_context:
            summary = feeding_context.get("health_summary", {})
            if summary:
                health_data.update(
                    {
                        "weight": summary.get("current_weight"),
                        "ideal_weight": summary.get("ideal_weight"),
                        "life_stage": summary.get("life_stage"),
                        "activity_level": summary.get("activity_level"),
                        "body_condition_score": summary.get("body_condition_score"),
                        "health_conditions": summary.get("health_conditions", []),
                    }
                )

            if "health_conditions" not in health_data and feeding_context.get(
                "health_conditions"
            ):
                health_data["health_conditions"] = feeding_context.get(
                    "health_conditions"
                )

            if feeding_context.get("health_emergency"):
                emergency = feeding_context.get("emergency_mode") or {}
                health_data["status"] = "attention"
                health_data["emergency"] = emergency
                health_data.setdefault("health_alerts", []).append(
                    {
                        "type": "emergency_feeding",
                        "severity": "critical",
                        "details": emergency,
                    }
                )

            if feeding_context.get("medication_with_meals"):
                health_data.setdefault("medications", []).append("meal_medication")

            health_data["health_status"] = feeding_context.get(
                "health_feeding_status", "healthy"
            )
            health_data["daily_calorie_target"] = feeding_context.get(
                "daily_calorie_target"
            )
            health_data["total_calories_today"] = feeding_context.get(
                "total_calories_today"
            )
            health_data["weight_goal_progress"] = feeding_context.get(
                "weight_goal_progress"
            )
            health_data["weight_goal"] = feeding_context.get("weight_goal")
            if feeding_context.get("daily_activity_level"):
                health_data["activity_level"] = feeding_context.get(
                    "daily_activity_level"
                )

        return health_data

    async def _get_weather_data(self, dog_id: str) -> dict[str, Any]:
        """Get weather health data for dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Weather health data dictionary
        """
        if not self.weather_health_manager:
            return {"status": "disabled", "health_score": None, "alerts": []}

        try:
            # Update weather data from configured entity
            weather_entity = self.config_entry.options.get(CONF_WEATHER_ENTITY)
            if weather_entity:
                await self.weather_health_manager.async_update_weather_data(
                    weather_entity
                )

            # Get weather health information
            weather_conditions = self.weather_health_manager.get_current_conditions()
            weather_score = self.weather_health_manager.get_weather_health_score()
            active_alerts = self.weather_health_manager.get_active_alerts()

            # Get dog-specific recommendations
            dog_config = self.get_dog_config(dog_id)
            recommendations = []
            if dog_config:
                recommendations = (
                    self.weather_health_manager.get_recommendations_for_dog(
                        dog_breed=dog_config.get("breed"),
                        dog_age_months=dog_config.get("age_months"),
                        health_conditions=dog_config.get("health_conditions", []),
                    )
                )

            return {
                "status": "active"
                if weather_conditions and weather_conditions.is_valid
                else "no_data",
                "health_score": weather_score,
                "temperature_c": weather_conditions.temperature_c
                if weather_conditions
                else None,
                "condition": weather_conditions.condition
                if weather_conditions
                else None,
                "alerts": [
                    {
                        "type": alert.alert_type.value,
                        "severity": alert.severity.value,
                        "title": alert.title,
                        "message": alert.message,
                    }
                    for alert in active_alerts[:3]  # Limit to 3 most important
                ],
                "recommendations": recommendations[:5],  # Limit to 5 recommendations
                "last_updated": weather_conditions.last_updated.isoformat()
                if weather_conditions
                else None,
            }

        except Exception as err:
            _LOGGER.warning("Failed to get weather data for %s: %s", dog_id, err)
            return {"status": "error", "error": str(err)}

    async def _get_geofencing_data(self, dog_id: str) -> dict[str, Any]:
        """Get geofencing data for dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Geofencing data dictionary
        """
        if not self.gps_geofence_manager:
            return {"status": "disabled", "zones": []}

        try:
            # Get geofence status from GPS manager
            geofence_status = await self.gps_geofence_manager.async_get_geofence_status(
                dog_id
            )

            return {
                "status": "active"
                if geofence_status.get("current_location")
                else "no_location",
                "zones_configured": geofence_status.get("zones_configured", 0),
                "safe_zone_breaches": geofence_status.get("safe_zone_breaches", 0),
                "current_location": geofence_status.get("current_location"),
                "zone_status": geofence_status.get("zone_status", {}),
                "last_update": geofence_status.get("last_update"),
            }

        except Exception as err:
            _LOGGER.warning("Failed to get geofencing data for %s: %s", dog_id, err)
            return {"status": "error", "error": str(err)}

    async def _get_garden_data(self, dog_id: str) -> dict[str, Any]:
        """Get garden tracking data for a dog."""

        if not self.garden_manager:
            return {"status": "disabled"}

        try:
            snapshot = self.garden_manager.build_garden_snapshot(dog_id)
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.warning("Failed to build garden snapshot for %s: %s", dog_id, err)
            return {"status": "error", "message": str(err)}

        snapshot.setdefault("status", "idle")
        return snapshot

    def _get_empty_dog_data(self) -> dict[str, Any]:
        """Get empty dog data structure.

        Returns:
            Empty dog data dictionary
        """
        return {
            "dog_info": {},
            "status": "unknown",
            "last_update": None,
            "feeding": {},
            "walk": {},
            "gps": {},
            "health": {},
        }

    def _calculate_update_interval(self) -> int:
        """Calculate optimized update interval with validation.

        Returns:
            Update interval in seconds

        Raises:
            ValueError: If configuration is invalid
        """
        if not self._dogs_config:
            return UPDATE_INTERVALS.get("minimal", 300)

        # Check for GPS requirements
        has_gps = any(
            dog.get("modules", {}).get(MODULE_GPS, False) for dog in self._dogs_config
        )

        if has_gps:
            gps_interval = self.config_entry.options.get(
                CONF_GPS_UPDATE_INTERVAL, UPDATE_INTERVALS.get("frequent", 60)
            )
            if not isinstance(gps_interval, int) or gps_interval <= 0:
                raise ValueError(f"Invalid GPS update interval: {gps_interval}")
            return gps_interval

        # Check for weather module - needs frequent updates for accurate health alerts
        has_weather = any(
            dog.get("modules", {}).get(MODULE_WEATHER, False)
            for dog in self._dogs_config
        )

        if has_weather:
            return UPDATE_INTERVALS.get("frequent", 60)

        # Calculate based on enabled modules
        total_modules = sum(
            sum(1 for enabled in dog.get("modules", {}).values() if enabled)
            for dog in self._dogs_config
        )

        if total_modules > 15:
            return UPDATE_INTERVALS.get("real_time", 30)
        elif total_modules > 8:
            return UPDATE_INTERVALS.get("balanced", 120)
        else:
            return UPDATE_INTERVALS.get("minimal", 300)

    # Public interface methods with enhanced documentation

    def get_dog_config(self, dog_id: str) -> DogConfigData | None:
        """Get dog configuration by ID.

        Args:
            dog_id: Dog identifier

        Returns:
            Dog configuration or None if not found
        """
        for config in self._dogs_config:
            if config.get(CONF_DOG_ID) == dog_id:
                return config
        return None

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
        """Get enabled modules for dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Set of enabled module names
        """
        config = self.get_dog_config(dog_id)
        if not config:
            return frozenset()

        modules = config.get("modules", {})
        return frozenset(name for name, enabled in modules.items() if enabled)

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        """Check if module is enabled for dog.

        Args:
            dog_id: Dog identifier
            module: Module name

        Returns:
            True if module is enabled
        """
        return module in self.get_enabled_modules(dog_id)

    def get_dog_ids(self) -> list[str]:
        """Get all configured dog IDs.

        Returns:
            List of dog identifiers
        """
        return [
            dog[CONF_DOG_ID]
            for dog in self._dogs_config
            if CONF_DOG_ID in dog and isinstance(dog[CONF_DOG_ID], str)
        ]

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        """Get data for specific dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Dog data or None if not found
        """
        return self._data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        """Get data for specific module.

        Args:
            dog_id: Dog identifier
            module: Module name

        Returns:
            Module data dictionary
        """
        return self._data.get(dog_id, {}).get(module, {})

    @property
    def available(self) -> bool:
        """Check if coordinator is available.

        Returns:
            True if coordinator is available and healthy
        """
        return self.last_update_success and self._consecutive_errors < 5

    def get_statistics(self) -> dict[str, Any]:
        """Get coordinator statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_dogs": len(self._dogs_config),
            "update_count": self._update_count,
            "error_count": self._error_count,
            "consecutive_errors": self._consecutive_errors,
            "error_rate": self._error_count / max(self._update_count, 1),
            "last_update": self.last_update_time,
            "update_interval": self.update_interval.total_seconds(),
            "cache_performance": {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "hit_rate": (
                    self._cache_hits / max(self._cache_hits + self._cache_misses, 1)
                ),
            },
        }

    @callback
    def async_start_background_tasks(self) -> None:
        """Start background maintenance tasks."""
        if self._maintenance_unsub is None:
            self._maintenance_unsub = async_track_time_interval(
                self.hass, self._async_maintenance, MAINTENANCE_INTERVAL
            )

    async def _async_maintenance(self, *_: Any) -> None:
        """Perform periodic maintenance with enhanced cache management.

        Args:
            *_: Unused arguments from time tracking
        """
        # PLATINUM: Enhanced cache cleanup
        now = dt_util.utcnow()
        expired_keys = [
            key
            for key, (_, timestamp) in self._cache.items()
            if (now - timestamp).total_seconds() > CACHE_TTL_SECONDS
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            _LOGGER.debug("Cleaned %d expired cache entries", len(expired_keys))

        # Reset consecutive errors if we've been stable
        if self._consecutive_errors > 0 and self.last_update_success:
            hours_since_last_error = (
                now - (self.last_update_time or now)
            ).total_seconds() / 3600
            if hours_since_last_error > 1:  # 1 hour of stability
                old_errors = self._consecutive_errors
                self._consecutive_errors = 0
                _LOGGER.info(
                    "Reset consecutive error count (%d) after %d hours of stability",
                    old_errors,
                    int(hours_since_last_error),
                )

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and cleanup resources.

        Raises:
            Exception: If shutdown encounters critical errors
        """
        _LOGGER.debug("Shutting down coordinator")

        try:
            # Cancel maintenance task
            if self._maintenance_unsub:
                self._maintenance_unsub()
                self._maintenance_unsub = None

            # Clear data and cache
            self._data.clear()
            self._cache.clear()

            _LOGGER.info("Coordinator shutdown completed successfully")

        except Exception as err:
            _LOGGER.error("Error during coordinator shutdown: %s", err)
            raise
