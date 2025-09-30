"""Coordinator for the PawControl integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import (
    CoordinatorUpdateFailed,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_EXTERNAL_INTEGRATIONS,
)
from .coordinator_support import CoordinatorMetrics, DogConfigRegistry, UpdateResult
from .device_api import PawControlDeviceClient
from .exceptions import GPSUnavailableError, NetworkError, ValidationError
from .module_adapters import CoordinatorModuleAdapters
from .resilience import ResilienceManager, RetryConfig
from .types import PawControlConfigEntry

if TYPE_CHECKING:
    from .data_manager import PawControlDataManager
    from .feeding_manager import FeedingManager
    from .garden_manager import GardenManager
    from .geofencing import PawControlGeofencing
    from .gps_manager import GPSGeofenceManager
    from .notifications import PawControlNotificationManager
    from .walk_manager import WalkManager
    from .weather_manager import WeatherHealthManager

_LOGGER = logging.getLogger(__name__)

API_TIMEOUT = 30.0
CACHE_TTL_SECONDS = 300
MAINTENANCE_INTERVAL = timedelta(hours=1)


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Central data coordinator with a compact, testable core."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PawControlConfigEntry,
        session: ClientSession | None = None,
    ) -> None:
        self.config_entry = entry
        self.session = session or async_get_clientsession(hass)
        self.registry = DogConfigRegistry.from_entry(entry)
        self._configured_dog_ids = self.registry.ids()
        self._use_external_api = bool(
            entry.options.get(CONF_EXTERNAL_INTEGRATIONS, False)
        )
        self._api_client = self._build_api_client(
            endpoint=entry.options.get(CONF_API_ENDPOINT, ""),
            token=entry.options.get(CONF_API_TOKEN, ""),
        )

        update_interval = self.registry.calculate_update_interval(entry.options)
        super().__init__(
            hass,
            _LOGGER,
            name="PawControl Data",
            update_interval=timedelta(seconds=update_interval),
            config_entry=entry,
        )

        self._modules = CoordinatorModuleAdapters(
            session=self.session,
            config_entry=entry,
            use_external_api=self._use_external_api,
            cache_ttl=timedelta(seconds=CACHE_TTL_SECONDS),
            api_client=self._api_client,
        )

        self._data: dict[str, dict[str, Any]] = {
            dog_id: self.registry.empty_payload() for dog_id in self._configured_dog_ids
        }
        self._metrics = CoordinatorMetrics()
        self._maintenance_unsub: callback | None = None
        self._setup_complete = False

        self.data_manager: PawControlDataManager | None = None
        self.feeding_manager: FeedingManager | None = None
        self.walk_manager: WalkManager | None = None
        self.notification_manager: PawControlNotificationManager | None = None
        self.gps_geofence_manager: GPSGeofenceManager | None = None
        self.geofencing_manager: PawControlGeofencing | None = None
        self.weather_health_manager: WeatherHealthManager | None = None
        self.garden_manager: GardenManager | None = None

        self.resilience_manager = ResilienceManager(hass)
        self._retry_config = RetryConfig(
            max_attempts=2,
            initial_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=True,
        )

        _LOGGER.info(
            "Coordinator initialised: %d dogs, %ds interval, external_api=%s",
            len(self.registry),
            update_interval,
            self._use_external_api,
        )

    def _build_api_client(
        self, *, endpoint: str, token: str
    ) -> PawControlDeviceClient | None:
        if not endpoint:
            return None
        try:
            return PawControlDeviceClient(
                session=self.session,
                endpoint=endpoint.strip(),
                api_key=token.strip() or None,
            )
        except ValueError as err:
            _LOGGER.warning("Invalid Paw Control API endpoint '%s': %s", endpoint, err)
            return None

    @property
    def use_external_api(self) -> bool:
        return self._use_external_api

    @use_external_api.setter
    def use_external_api(self, value: bool) -> None:
        self._use_external_api = bool(value)

    @property
    def api_client(self) -> PawControlDeviceClient | None:
        return self._api_client

    def attach_runtime_managers(
        self,
        *,
        data_manager: PawControlDataManager,
        feeding_manager: FeedingManager,
        walk_manager: WalkManager,
        notification_manager: PawControlNotificationManager,
        geofencing_manager: PawControlGeofencing | None = None,
        gps_geofence_manager: GPSGeofenceManager | None = None,
        weather_health_manager: WeatherHealthManager | None = None,
        garden_manager: GardenManager | None = None,
    ) -> None:
        self.data_manager = data_manager
        self.feeding_manager = feeding_manager
        self.walk_manager = walk_manager
        self.notification_manager = notification_manager
        self.gps_geofence_manager = gps_geofence_manager
        self.geofencing_manager = geofencing_manager
        self.weather_health_manager = weather_health_manager
        self.garden_manager = garden_manager

        if gps_geofence_manager:
            gps_geofence_manager.set_notification_manager(notification_manager)

        self._modules.attach_managers(
            data_manager=data_manager,
            feeding_manager=feeding_manager,
            walk_manager=walk_manager,
            gps_geofence_manager=gps_geofence_manager,
            weather_health_manager=weather_health_manager,
            garden_manager=garden_manager,
        )

    def clear_runtime_managers(self) -> None:
        self.data_manager = None
        self.feeding_manager = None
        self.walk_manager = None
        self.notification_manager = None
        self.gps_geofence_manager = None
        self.geofencing_manager = None
        self.weather_health_manager = None
        self.garden_manager = None
        self._modules.detach_managers()

    async def _async_setup(self) -> None:
        if self._setup_complete:
            return
        self._data.update(
            {
                dog_id: self.registry.empty_payload()
                for dog_id in self._configured_dog_ids
            }
        )
        self._modules.clear_caches()
        self._setup_complete = True

    async def _async_update_data(self) -> dict[str, Any]:
        if len(self.registry) == 0:
            return {}

        await self._async_setup()

        dog_ids = list(self._configured_dog_ids)
        if not dog_ids:
            raise CoordinatorUpdateFailed("No valid dogs configured")

        self._metrics.start_cycle()
        result = await self._fetch_all_dogs(dog_ids)

        success_rate, all_failed = self._metrics.record_cycle(
            len(dog_ids), result.errors
        )
        if all_failed:
            raise CoordinatorUpdateFailed(f"All {len(dog_ids)} dogs failed to update")

        if success_rate < 0.5:
            _LOGGER.warning(
                "Low success rate: %d/%d dogs updated successfully",
                len(dog_ids) - result.errors,
                len(dog_ids),
            )

        self._data = result.payload
        return self._data

    async def _fetch_all_dogs(self, dog_ids: list[str]) -> UpdateResult:
        result = UpdateResult()

        tasks = [self._fetch_with_resilience(dog_id) for dog_id in dog_ids]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for dog_id, response in zip(dog_ids, responses, strict=True):
            if isinstance(response, ConfigEntryAuthFailed):
                raise response
            if isinstance(response, ValidationError):
                _LOGGER.error("Invalid configuration for dog %s: %s", dog_id, response)
                result.add_error(dog_id, self.registry.empty_payload())
            elif isinstance(response, Exception):
                _LOGGER.error(
                    "Resilience exhausted for dog %s: %s (%s)",
                    dog_id,
                    response,
                    response.__class__.__name__,
                )
                result.add_error(
                    dog_id,
                    self._data.get(dog_id, self.registry.empty_payload()),
                )
            else:
                result.add_success(dog_id, response)

        return result

    async def _fetch_with_resilience(self, dog_id: str) -> dict[str, Any]:
        return await self.resilience_manager.execute_with_resilience(
            self._fetch_dog_data_protected,
            dog_id,
            circuit_breaker_name=f"dog_data_{dog_id}",
            retry_config=self._retry_config,
        )

    async def _fetch_dog_data_protected(self, dog_id: str) -> dict[str, Any]:
        async with asyncio.timeout(API_TIMEOUT):
            return await self._fetch_dog_data(dog_id)

    async def _fetch_dog_data(self, dog_id: str) -> dict[str, Any]:
        dog_config = self.registry.get(dog_id)
        if not dog_config:
            raise ValidationError("dog_id", dog_id, "Dog configuration not found")

        payload = {
            "dog_info": dog_config,
            "status": "online",
            "last_update": dt_util.utcnow().isoformat(),
        }

        modules = dog_config.get("modules", {})
        module_tasks = self._modules.build_tasks(dog_id, modules)
        if not module_tasks:
            return payload

        results = await asyncio.gather(
            *(task for _, task in module_tasks), return_exceptions=True
        )

        for (module_name, _), result in zip(module_tasks, results, strict=True):
            if isinstance(result, GPSUnavailableError):
                _LOGGER.debug("GPS unavailable for %s: %s", dog_id, result)
                payload[module_name] = {"status": "unavailable", "reason": str(result)}
            elif isinstance(result, NetworkError):
                _LOGGER.warning(
                    "Network error fetching %s data for %s: %s",
                    module_name,
                    dog_id,
                    result,
                )
                payload[module_name] = {"status": "network_error"}
            elif isinstance(result, Exception):
                _LOGGER.warning(
                    "Failed to fetch %s data for %s: %s (%s)",
                    module_name,
                    dog_id,
                    result,
                    result.__class__.__name__,
                )
                payload[module_name] = {"status": "error"}
            else:
                payload[module_name] = result

        return payload

    def get_dog_config(self, dog_id: str) -> Any:
        return self.registry.get(dog_id)

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
        return self.registry.enabled_modules(dog_id)

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        return module in self.registry.enabled_modules(dog_id)

    def get_dog_ids(self) -> list[str]:
        return list(self._configured_dog_ids)

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        return self._data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        return self._data.get(dog_id, {}).get(module, {})

    def get_configured_dog_ids(self) -> list[str]:
        return list(self._configured_dog_ids)

    def get_configured_dog_name(self, dog_id: str) -> str | None:
        return self.registry.get_name(dog_id)

    @property
    def available(self) -> bool:
        return self.last_update_success and self._metrics.consecutive_errors < 5

    def get_update_statistics(self) -> dict[str, Any]:
        cache_metrics = self._modules.cache_metrics()
        return self._metrics.update_statistics(
            cache_entries=cache_metrics.entries,
            cache_hit_rate=cache_metrics.hit_rate,
            last_update=self.last_update_time,
            interval=self.update_interval,
        )

    def get_statistics(self) -> dict[str, Any]:
        cache_metrics = self._modules.cache_metrics()
        stats = self._metrics.runtime_statistics(
            cache_metrics=cache_metrics,
            total_dogs=len(self.registry),
            last_update=self.last_update_time,
            interval=self.update_interval,
        )
        stats["resilience"] = self.resilience_manager.get_all_circuit_breakers()
        return stats

    @callback
    def async_start_background_tasks(self) -> None:
        if self._maintenance_unsub is None:
            self._maintenance_unsub = async_track_time_interval(
                self.hass, self._async_maintenance, MAINTENANCE_INTERVAL
            )

    async def _async_maintenance(self, *_: Any) -> None:
        now = dt_util.utcnow()
        expired = self._modules.cleanup_expired(now)
        if expired:
            _LOGGER.debug("Cleaned %d expired cache entries", expired)

        if self._metrics.consecutive_errors > 0 and self.last_update_success:
            hours_since_last_update = (
                now - (self.last_update_time or now)
            ).total_seconds() / 3600
            if hours_since_last_update > 1:
                previous = self._metrics.consecutive_errors
                self._metrics.reset_consecutive()
                _LOGGER.info(
                    "Reset consecutive error count (%d) after %d hours of stability",
                    previous,
                    int(hours_since_last_update),
                )

    async def async_shutdown(self) -> None:
        if self._maintenance_unsub:
            self._maintenance_unsub()
            self._maintenance_unsub = None

        self._data.clear()
        self._modules.clear_caches()
        _LOGGER.info("Coordinator shutdown completed successfully")
