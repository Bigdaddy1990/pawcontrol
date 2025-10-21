"""Helpers that translate runtime managers into coordinator-facing adapters."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from aiohttp import ClientSession

try:
    from homeassistant.util import dt as dt_util
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for tests

    class _DateTimeModule:
        @staticmethod
        def utcnow() -> datetime:
            return datetime.now(UTC)

    dt_util = _DateTimeModule()

from .const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_WEATHER_ENTITY,
    MODULE_FEEDING,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    MODULE_WEATHER,
)
from .device_api import PawControlDeviceClient
from .exceptions import GPSUnavailableError, NetworkError, RateLimitError
from .http_client import ensure_shared_client_session
from .types import (
    CoordinatorModuleTask,
    DogModulesMapping,
    FeedingModulePayload,
    GardenModulePayload,
    GeofencingModulePayload,
    GPSModulePayload,
    HealthModulePayload,
    ModuleCacheMetrics,
    PawControlConfigEntry,
    WalkModulePayload,
    WeatherModulePayload,
)

if TYPE_CHECKING:
    from .data_manager import PawControlDataManager
    from .feeding_manager import FeedingManager
    from .garden_manager import GardenManager
    from .gps_manager import GPSGeofenceManager
    from .walk_manager import WalkManager
    from .weather_manager import WeatherHealthManager

_LOGGER = logging.getLogger(__name__)


class _ExpiringCache[PayloadT]:
    """Cache that evicts entries after a fixed TTL."""

    __slots__ = ("_data", "_hits", "_misses", "_ttl")

    def __init__(self, ttl: timedelta) -> None:
        self._data: dict[str, tuple[PayloadT, datetime]] = {}
        self._hits = 0
        self._misses = 0
        self._ttl = ttl

    def get(self, key: str) -> PayloadT | None:
        """Return cached data if it has not expired."""

        if key not in self._data:
            self._misses += 1
            return None

        value, timestamp = self._data[key]
        if dt_util.utcnow() - timestamp > self._ttl:
            self._misses += 1
            del self._data[key]
            return None

        self._hits += 1
        return value

    def set(self, key: str, value: PayloadT) -> None:
        """Store a value in the cache."""

        self._data[key] = (value, dt_util.utcnow())

    def cleanup(self, now: datetime) -> int:
        """Remove all expired entries and return count of evicted items."""

        expired: list[str] = []
        for key, (_, timestamp) in self._data.items():
            if now - timestamp > self._ttl:
                expired.append(key)

        for key in expired:
            del self._data[key]

        return len(expired)

    def clear(self) -> None:
        """Reset the cache entirely."""

        self._data.clear()
        self._hits = 0
        self._misses = 0

    def metrics(self) -> ModuleCacheMetrics:
        """Return current metrics for this cache."""

        return ModuleCacheMetrics(
            entries=len(self._data),
            hits=self._hits,
            misses=self._misses,
        )


class _BaseModuleAdapter[PayloadT]:
    """Base helper for adapters that maintain a TTL cache."""

    def __init__(self, ttl: timedelta | None) -> None:
        self._cache: _ExpiringCache[PayloadT] | None = (
            _ExpiringCache(ttl) if ttl else None
        )

    def _cached(self, key: str) -> PayloadT | None:
        if not self._cache:
            return None
        return self._cache.get(key)

    def _remember(self, key: str, value: PayloadT) -> None:
        if not self._cache:
            return
        self._cache.set(key, value)

    def cleanup(self, now: datetime) -> int:
        if not self._cache:
            return 0
        return self._cache.cleanup(now)

    def clear(self) -> None:
        if self._cache:
            self._cache.clear()

    def cache_metrics(self) -> ModuleCacheMetrics:
        if not self._cache:
            return ModuleCacheMetrics()
        return self._cache.metrics()


class FeedingModuleAdapter(_BaseModuleAdapter[FeedingModulePayload]):
    """Adapter that exposes feeding information through the coordinator."""

    def __init__(
        self,
        *,
        session: ClientSession,
        use_external_api: bool,
        ttl: timedelta,
        api_client: PawControlDeviceClient | None,
    ) -> None:
        """Initialise the feeding adapter with HTTP and manager context."""
        super().__init__(ttl)
        self._session = ensure_shared_client_session(
            session, owner="FeedingModuleAdapter"
        )
        self._use_external_api = use_external_api
        self._manager: FeedingManager | None = None
        self._api_client = api_client

    def attach(self, manager: FeedingManager | None) -> None:
        """Attach the feeding manager instance."""

        self._manager = manager

    async def async_get_data(self, dog_id: str) -> FeedingModulePayload:
        """Return the latest feeding context for the dog."""

        if (cached := self._cached(dog_id)) is not None:
            return cached

        if self._manager is not None:
            try:
                manager_data = await self._manager.async_get_feeding_data(dog_id)
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.debug("Feeding manager unavailable for %s: %s", dog_id, err)
            else:
                payload = cast(FeedingModulePayload, dict(manager_data))
                payload.setdefault("status", "ready")
                self._remember(dog_id, payload)
                return payload

        if self._use_external_api and self._api_client is not None:
            try:
                payload = cast(
                    FeedingModulePayload,
                    dict(await self._api_client.async_get_feeding_payload(dog_id)),
                )
            except RateLimitError:
                raise
            except NetworkError:
                raise
            except Exception as err:  # pragma: no cover - unexpected
                raise NetworkError(f"Device API error: {err}") from err
            payload.setdefault("status", "ready")
            self._remember(dog_id, payload)
            return payload

        default_data: FeedingModulePayload = {
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
        self._remember(dog_id, default_data)
        return default_data


class WalkModuleAdapter(_BaseModuleAdapter[WalkModulePayload]):
    """Expose detailed walk data using the walk manager."""

    def __init__(self, *, ttl: timedelta | None = None) -> None:
        """Initialise the walk adapter with optional caching."""
        super().__init__(ttl)
        self._manager: WalkManager | None = None

    def attach(self, manager: WalkManager | None) -> None:
        """Attach the walk manager used to gather live metrics."""
        self._manager = manager

    async def async_get_data(self, dog_id: str) -> WalkModulePayload:
        """Return cached or live walk telemetry for the given dog."""
        if (cached := self._cached(dog_id)) is not None:
            return cached

        if self._manager is None:
            return self._default_payload()

        try:
            walk_data = await self._manager.async_get_walk_data(dog_id)
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.warning("Failed to fetch walk data for %s: %s", dog_id, err)
            return self._default_payload(status="error", message=str(err))

        if not walk_data:
            return self._default_payload(status="empty")

        payload = cast(WalkModulePayload, walk_data)
        self._remember(dog_id, payload)
        return payload

    def _default_payload(
        self, *, status: str = "unavailable", message: str | None = None
    ) -> WalkModulePayload:
        payload: WalkModulePayload = {
            "current_walk": None,
            "last_walk": None,
            "daily_walks": 0,
            "total_distance": 0.0,
            "status": status,
        }
        if message:
            payload["message"] = message
        return payload


class GPSModuleAdapter:
    """Return GPS-centric data leveraging the GPS manager."""

    def __init__(self) -> None:
        """Initialise the GPS adapter without caching."""
        self._manager: GPSGeofenceManager | None = None

    def attach(self, manager: GPSGeofenceManager | None) -> None:
        """Attach the GPS manager that supplies live coordinates."""
        self._manager = manager

    async def async_get_data(self, dog_id: str) -> GPSModulePayload:
        """Return the latest GPS fix and active route information."""
        if not self._manager:
            raise GPSUnavailableError(dog_id, "GPS manager not available")

        try:
            current_location = await self._manager.async_get_current_location(dog_id)
            active_route = await self._manager.async_get_active_route(dog_id)
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.warning("Failed to retrieve GPS data for %s: %s", dog_id, err)
            raise GPSUnavailableError(dog_id, str(err)) from err

        payload: GPSModulePayload = {
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
        return payload


class GeofencingModuleAdapter(_BaseModuleAdapter[GeofencingModulePayload]):
    """Expose geofence metadata from the GPS manager."""

    def __init__(self, *, ttl: timedelta) -> None:
        """Initialise the geofencing adapter with a cache TTL."""
        super().__init__(ttl)
        self._manager: GPSGeofenceManager | None = None

    def attach(self, manager: GPSGeofenceManager | None) -> None:
        """Attach the geofence manager used to fetch zone information."""
        self._manager = manager

    async def async_get_data(self, dog_id: str) -> GeofencingModulePayload:
        """Return cached or live geofence details for the dog."""
        if (cached := self._cached(dog_id)) is not None:
            return cached

        payload: GeofencingModulePayload
        if not self._manager:
            payload = {
                "status": "unavailable",
                "message": "geofencing disabled",
                "zones_configured": 0,
                "zone_status": {},
                "current_location": None,
                "safe_zone_breaches": 0,
                "last_update": None,
            }
        else:
            try:
                geofence_status = await self._manager.async_get_geofence_status(dog_id)
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.warning(
                    "Failed to fetch geofence status for %s: %s", dog_id, err
                )
                payload = {
                    "status": "error",
                    "error": str(err),
                    "zones_configured": 0,
                    "zone_status": {},
                    "current_location": None,
                    "safe_zone_breaches": 0,
                    "last_update": None,
                }
            else:
                payload = {
                    "status": "active",
                    "zones_configured": geofence_status.get("zones_configured", 0),
                    "zone_status": geofence_status.get("zone_status", {}),
                    "current_location": geofence_status.get("current_location"),
                    "safe_zone_breaches": geofence_status.get("safe_zone_breaches", 0),
                    "last_update": geofence_status.get("last_update"),
                }

        geofence_payload: GeofencingModulePayload = payload
        self._remember(dog_id, geofence_payload)
        return geofence_payload


class HealthModuleAdapter(_BaseModuleAdapter[HealthModulePayload]):
    """Combine stored health data with live feeding/walk metrics."""

    def __init__(self, *, ttl: timedelta | None = None) -> None:
        """Initialise the health adapter with optional caching."""
        super().__init__(ttl)
        self._feeding_manager: FeedingManager | None = None
        self._data_manager: PawControlDataManager | None = None
        self._walk_manager: WalkManager | None = None

    def attach(
        self,
        *,
        feeding_manager: FeedingManager | None,
        data_manager: PawControlDataManager | None,
        walk_manager: WalkManager | None,
    ) -> None:
        """Provide the managers used to construct the health snapshot."""
        self._feeding_manager = feeding_manager
        self._data_manager = data_manager
        self._walk_manager = walk_manager

    async def async_get_data(self, dog_id: str) -> HealthModulePayload:
        """Build a composite health payload using cached and live data."""
        if (cached := self._cached(dog_id)) is not None:
            return cached

        health_data: dict[str, Any] = {
            "weight": None,
            "ideal_weight": None,
            "last_vet_visit": None,
            "medications": [],
            "health_alerts": [],
            "status": "healthy",
        }

        if self._data_manager is not None:
            try:
                entries = await self._data_manager.async_get_module_history(
                    MODULE_HEALTH, dog_id, limit=1
                )
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.debug(
                    "Unable to load stored health entries for %s: %s", dog_id, err
                )
            else:
                if entries:
                    latest = entries[0]
                    health_data.update(latest)
                    health_data.setdefault("status", "healthy")

        feeding_context: dict[str, Any] = {}
        if self._feeding_manager is not None:
            try:
                feeding_context = await self._feeding_manager.async_get_feeding_data(
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
                        "weight": summary.get("current_weight", health_data["weight"]),
                        "ideal_weight": summary.get(
                            "ideal_weight", health_data["ideal_weight"]
                        ),
                        "life_stage": summary.get("life_stage"),
                        "activity_level": summary.get("activity_level"),
                        "body_condition_score": summary.get("body_condition_score"),
                        "health_conditions": summary.get("health_conditions", []),
                    }
                )

            if feeding_context.get("health_conditions") and not health_data.get(
                "health_conditions"
            ):
                health_data["health_conditions"] = feeding_context.get(
                    "health_conditions", []
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
                "health_feeding_status", health_data.get("health_status", "healthy")
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

        if self._walk_manager is not None and "activity_level" not in health_data:
            try:
                walk_overview = await self._walk_manager.async_get_walk_data(dog_id)
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.debug("Walk context unavailable for %s: %s", dog_id, err)
            else:
                if walk_overview and walk_overview.get("daily_walks"):
                    health_data["activity_level"] = "active"
                elif walk_overview:
                    health_data["activity_level"] = "low"

        payload = cast(HealthModulePayload, health_data)
        self._remember(dog_id, payload)
        return payload


class WeatherModuleAdapter(_BaseModuleAdapter[WeatherModulePayload]):
    """Adapter for weather-informed health data."""

    def __init__(self, *, config_entry: PawControlConfigEntry, ttl: timedelta) -> None:
        """Initialise the weather adapter with config context."""
        super().__init__(ttl)
        self._config_entry = config_entry
        self._manager: WeatherHealthManager | None = None

    def attach(self, manager: WeatherHealthManager | None) -> None:
        """Attach the weather health manager to source observations."""
        self._manager = manager

    def _resolve_dog_config(self, dog_id: str) -> Mapping[str, Any] | None:
        """Return the config entry mapping for ``dog_id`` if available."""

        raw_dogs = self._config_entry.data.get(CONF_DOGS)
        if not isinstance(raw_dogs, list):
            return None

        for candidate in raw_dogs:
            if not isinstance(candidate, Mapping):
                continue
            configured_id = candidate.get(CONF_DOG_ID)
            if isinstance(configured_id, str) and configured_id == dog_id:
                return candidate

        return None

    async def async_get_data(self, dog_id: str) -> WeatherModulePayload:
        """Return weather-adjusted health information for a dog."""
        if (cached := self._cached(dog_id)) is not None:
            return cached

        if self._manager is None:
            payload = cast(
                WeatherModulePayload,
                {
                    "status": "disabled",
                    "health_score": None,
                    "alerts": [],
                    "recommendations": [],
                },
            )
            self._remember(dog_id, payload)
            return payload

        weather_entity = self._config_entry.options.get(CONF_WEATHER_ENTITY)
        if weather_entity:
            try:
                await self._manager.async_update_weather_data(weather_entity)
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.debug(
                    "Failed to refresh weather data from %s: %s", weather_entity, err
                )

        dog_config = self._resolve_dog_config(dog_id)
        dog_breed: str | None = None
        dog_age_months: int | None = None
        health_conditions: list[str] | None = None

        if dog_config is not None:
            raw_breed = dog_config.get(CONF_DOG_BREED)
            if isinstance(raw_breed, str) and raw_breed.strip():
                dog_breed = raw_breed

            raw_age = dog_config.get(CONF_DOG_AGE)
            if isinstance(raw_age, int):
                dog_age_months = raw_age
            elif isinstance(raw_age, str):
                try:
                    dog_age_months = int(raw_age)
                except ValueError:
                    dog_age_months = None

            raw_conditions = dog_config.get("health_conditions")
            if isinstance(raw_conditions, list):
                health_conditions = [
                    str(condition)
                    for condition in raw_conditions
                    if isinstance(condition, str) and condition.strip()
                ]

        try:
            alerts = [
                {
                    "type": getattr(alert.alert_type, "value", str(alert.alert_type)),
                    "severity": getattr(alert.severity, "value", str(alert.severity)),
                    "title": alert.title,
                    "message": alert.message,
                    "recommendations": list(alert.recommendations),
                    "duration_hours": alert.duration_hours,
                }
                for alert in self._manager.get_active_alerts()
            ]
            recommendations = self._manager.get_recommendations_for_dog(
                dog_breed=dog_breed,
                dog_age_months=dog_age_months,
                health_conditions=health_conditions,
            )
            health_score = self._manager.get_weather_health_score()
            conditions = self._manager.get_current_conditions()
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.warning("Failed to build weather health data: %s", err)
            payload = cast(
                WeatherModulePayload,
                {
                    "status": "error",
                    "alerts": [],
                    "recommendations": [],
                    "message": str(err),
                    "health_score": None,
                },
            )
        else:
            payload = cast(
                WeatherModulePayload,
                {
                    "status": "ready",
                    "health_score": health_score,
                    "alerts": alerts,
                    "recommendations": recommendations,
                },
            )
            if conditions is not None:
                payload["conditions"] = {
                    "temperature_c": conditions.temperature_c,
                    "humidity_percent": conditions.humidity_percent,
                    "uv_index": conditions.uv_index,
                    "wind_speed_kmh": conditions.wind_speed_kmh,
                    "condition": conditions.condition,
                    "last_updated": conditions.last_updated.isoformat(),
                }

        self._remember(dog_id, payload)
        return payload


class GardenModuleAdapter(_BaseModuleAdapter[GardenModulePayload]):
    """Adapter that exposes garden activity data."""

    def __init__(self, *, ttl: timedelta | None = None) -> None:
        """Initialise the garden adapter and optional cache."""
        super().__init__(ttl)
        self._manager: GardenManager | None = None

    def attach(self, manager: GardenManager | None) -> None:
        """Attach the garden manager used to pull session data."""
        self._manager = manager

    async def async_get_data(self, dog_id: str) -> GardenModulePayload:
        """Return garden status details for the requested dog."""
        if (cached := self._cached(dog_id)) is not None:
            return cached

        if self._manager is None:
            payload: GardenModulePayload = {
                "status": "disabled",
                "sessions": [],
                "recent_activity": [],
                "stats": {},
            }
            self._remember(dog_id, payload)
            return payload

        try:
            snapshot = self._manager.build_garden_snapshot(dog_id)
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.warning("Failed to build garden snapshot for %s: %s", dog_id, err)
            payload = cast(
                GardenModulePayload,
                {
                    "status": "error",
                    "message": str(err),
                    "sessions": [],
                    "recent_activity": [],
                    "stats": {},
                },
            )
            self._remember(dog_id, payload)
            return payload

        snapshot.setdefault("status", "idle")
        payload = cast(GardenModulePayload, snapshot)
        self._remember(dog_id, payload)
        return payload


class CoordinatorModuleAdapters:
    """Container that owns all module adapters used by the coordinator."""

    def __init__(
        self,
        *,
        session: ClientSession,
        config_entry: PawControlConfigEntry,
        use_external_api: bool,
        cache_ttl: timedelta,
        api_client: PawControlDeviceClient | None,
    ) -> None:
        """Initialise the container of module adapters with shared context."""
        self._cache_ttl = cache_ttl
        self.feeding = FeedingModuleAdapter(
            session=session,
            use_external_api=use_external_api,
            ttl=cache_ttl,
            api_client=api_client,
        )
        self.walk = WalkModuleAdapter(ttl=cache_ttl)
        self.gps = GPSModuleAdapter()
        self.geofencing = GeofencingModuleAdapter(ttl=cache_ttl)
        self.health = HealthModuleAdapter(ttl=cache_ttl)
        self.weather = WeatherModuleAdapter(config_entry=config_entry, ttl=cache_ttl)
        self.garden = GardenModuleAdapter(ttl=cache_ttl)

    def attach_managers(
        self,
        *,
        data_manager: PawControlDataManager | None,
        feeding_manager: FeedingManager | None,
        walk_manager: WalkManager | None,
        gps_geofence_manager: GPSGeofenceManager | None,
        weather_health_manager: WeatherHealthManager | None,
        garden_manager: GardenManager | None,
    ) -> None:
        """Attach runtime managers so adapters can fetch live data."""
        self.feeding.attach(feeding_manager)
        self.walk.attach(walk_manager)
        self.gps.attach(gps_geofence_manager)
        self.geofencing.attach(gps_geofence_manager)
        self.health.attach(
            feeding_manager=feeding_manager,
            data_manager=data_manager,
            walk_manager=walk_manager,
        )
        self.weather.attach(weather_health_manager)
        self.garden.attach(garden_manager)

    def detach_managers(self) -> None:
        """Detach all runtime managers when tearing down the coordinator."""
        self.feeding.attach(None)
        self.walk.attach(None)
        self.gps.attach(None)
        self.geofencing.attach(None)
        self.health.attach(
            feeding_manager=None,
            data_manager=None,
            walk_manager=None,
        )
        self.weather.attach(None)
        self.garden.attach(None)

    def build_tasks(
        self, dog_id: str, modules: DogModulesMapping
    ) -> list[CoordinatorModuleTask]:
        """Return coroutine tasks for every enabled module flag for the dog."""
        tasks: list[CoordinatorModuleTask] = []

        if modules.get(MODULE_FEEDING):
            tasks.append(
                CoordinatorModuleTask(
                    module="feeding",
                    coroutine=self.feeding.async_get_data(dog_id),
                )
            )
        if modules.get(MODULE_WALK):
            tasks.append(
                CoordinatorModuleTask(
                    module="walk",
                    coroutine=self.walk.async_get_data(dog_id),
                )
            )
        if modules.get(MODULE_GPS):
            tasks.append(
                CoordinatorModuleTask(
                    module="gps",
                    coroutine=self.gps.async_get_data(dog_id),
                )
            )
            tasks.append(
                CoordinatorModuleTask(
                    module="geofencing",
                    coroutine=self.geofencing.async_get_data(dog_id),
                )
            )
        if modules.get(MODULE_HEALTH):
            tasks.append(
                CoordinatorModuleTask(
                    module="health",
                    coroutine=self.health.async_get_data(dog_id),
                )
            )
        if modules.get(MODULE_WEATHER):
            tasks.append(
                CoordinatorModuleTask(
                    module="weather",
                    coroutine=self.weather.async_get_data(dog_id),
                )
            )
        if modules.get(MODULE_GARDEN):
            tasks.append(
                CoordinatorModuleTask(
                    module="garden",
                    coroutine=self.garden.async_get_data(dog_id),
                )
            )

        return tasks

    def cleanup_expired(self, now: datetime) -> int:
        """Expire cached entries and return the number of evictions."""
        expired = 0
        for adapter in (
            self.feeding,
            self.walk,
            self.geofencing,
            self.health,
            self.weather,
            self.garden,
        ):
            expired += adapter.cleanup(now)
        return expired

    def clear_caches(self) -> None:
        """Clear all adapter caches, typically during manual refreshes."""
        for adapter in (
            self.feeding,
            self.walk,
            self.geofencing,
            self.health,
            self.weather,
            self.garden,
        ):
            adapter.clear()

    def cache_metrics(self) -> ModuleCacheMetrics:
        """Aggregate cache metrics from every module adapter."""
        metrics = ModuleCacheMetrics()
        for adapter in (
            self.feeding,
            self.walk,
            self.geofencing,
            self.health,
            self.weather,
            self.garden,
        ):
            adapter_metrics = adapter.cache_metrics()
            metrics.entries += adapter_metrics.entries
            metrics.hits += adapter_metrics.hits
            metrics.misses += adapter_metrics.misses

        return metrics
