"""Coordinator for the PawControl integration."""

"""Coordinator for the PawControl integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    CoordinatorUpdateFailed,
    DataUpdateCoordinator,
)

from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_EXTERNAL_INTEGRATIONS,
    UPDATE_INTERVALS,
)
from .coordinator_runtime import AdaptivePollingController, EntityBudgetSnapshot
from .coordinator_support import CoordinatorMetrics, DogConfigRegistry, UpdateResult
from .coordinator_tasks import (
    build_runtime_statistics,
    build_update_statistics,
    ensure_background_task,
    fetch_all_dogs,
    fetch_single_dog,
    run_maintenance,
)
from .coordinator_tasks import (
    shutdown as shutdown_tasks,
)
from .device_api import PawControlDeviceClient
from .exceptions import ValidationError
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

CACHE_TTL_SECONDS = 300
MAINTENANCE_INTERVAL = timedelta(hours=1)

__all__ = ["EntityBudgetSnapshot", "PawControlCoordinator"]


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Central orchestrator that keeps runtime logic in dedicated helpers."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PawControlConfigEntry,
        session: ClientSession | None = None,
    ) -> None:
        self.config_entry = entry
        self.session = session or async_get_clientsession(hass)
        self.registry = DogConfigRegistry.from_entry(entry)
        self._use_external_api = bool(
            entry.options.get(CONF_EXTERNAL_INTEGRATIONS, False)
        )
        self._api_client = self._build_api_client(
            endpoint=entry.options.get(CONF_API_ENDPOINT, ""),
            token=entry.options.get(CONF_API_TOKEN, ""),
        )

        base_interval = self._initial_update_interval(entry)
        self._adaptive_polling = AdaptivePollingController(
            initial_interval_seconds=float(base_interval)
        )

        super().__init__(
            hass,
            _LOGGER,
            name="PawControl Data",
            update_interval=timedelta(seconds=base_interval),
            config_entry=entry,
        )

        use_external_api = bool(entry.options.get(CONF_EXTERNAL_INTEGRATIONS, False))
        self._api_client = self._build_api_client(
            endpoint=entry.options.get(CONF_API_ENDPOINT, ""),
            token=entry.options.get(CONF_API_TOKEN, ""),
        )

        self._modules = CoordinatorModuleAdapters(
            session=self.session,
            config_entry=entry,
            use_external_api=use_external_api,
            cache_ttl=timedelta(seconds=CACHE_TTL_SECONDS),
            api_client=self._api_client,
        )

        self._data: dict[str, dict[str, Any]] = {
            dog_id: self.registry.empty_payload() for dog_id in self.registry.ids()
        }
        self._metrics = CoordinatorMetrics()
        self._entity_budget_snapshots: dict[str, EntityBudgetSnapshot] = {}
        self._setup_complete = False
        self._maintenance_unsub: callback | None = None

        self.data_manager: PawControlDataManager | None
        self.feeding_manager: FeedingManager | None
        self.walk_manager: WalkManager | None
        self.notification_manager: PawControlNotificationManager | None
        self.gps_geofence_manager: GPSGeofenceManager | None
        self.geofencing_manager: PawControlGeofencing | None
        self.weather_health_manager: WeatherHealthManager | None
        self.garden_manager: GardenManager | None

        for attr in (
            "data_manager",
            "feeding_manager",
            "walk_manager",
            "notification_manager",
            "gps_geofence_manager",
            "geofencing_manager",
            "weather_health_manager",
            "garden_manager",
        ):
            setattr(self, attr, None)

        self.resilience_manager = ResilienceManager(hass)
        self._retry_config = RetryConfig(
            max_attempts=2,
            initial_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=True,
        )

        self._runtime = CoordinatorRuntime(
            registry=self.registry,
            modules=self._modules,
            resilience_manager=self.resilience_manager,
            retry_config=self._retry_config,
            metrics=self._metrics,
            adaptive_polling=self._adaptive_polling,
            logger=_LOGGER,
        )

        _LOGGER.info(
            "Coordinator initialised: %d dogs, %ds interval, external_api=%s",
            len(self.registry),
            base_interval,
            self._use_external_api,
        )

    def _initial_update_interval(self, entry: PawControlConfigEntry) -> int:
        try:
            return self.registry.calculate_update_interval(entry.options)
        except ValidationError as err:
            _LOGGER.warning("Invalid update interval configuration: %s", err)
            return UPDATE_INTERVALS.get("balanced", 120)

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

    def logger(self) -> logging.Logger:
        return _LOGGER

    def report_entity_budget(self, snapshot: EntityBudgetSnapshot) -> None:
        """Receive entity budget metrics from the entity factory."""

        self._entity_budget_snapshots[snapshot.dog_id] = snapshot
        self._adaptive_polling.update_entity_saturation(self._entity_saturation())

    def _entity_saturation(self) -> float:
        if not self._entity_budget_snapshots:
            return 0.0

        dog_ids = self.registry.ids()
        data, cycle = await self._runtime.execute_cycle(
            dog_ids,
            self._data,
            empty_payload_factory=self.registry.empty_payload,
        )
        if total_capacity <= 0:
            return 0.0
        total_allocated = sum(
            snapshot.total_allocated
            for snapshot in self._entity_budget_snapshots.values()
        )
        return max(0.0, min(1.0, total_allocated / total_capacity))

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
        managers = {
            "data_manager": data_manager,
            "feeding_manager": feeding_manager,
            "walk_manager": walk_manager,
            "notification_manager": notification_manager,
            "gps_geofence_manager": gps_geofence_manager,
            "geofencing_manager": geofencing_manager,
            "weather_health_manager": weather_health_manager,
            "garden_manager": garden_manager,
        }

        for attr, value in managers.items():
            setattr(self, attr, value)

        if managers["gps_geofence_manager"]:
            managers["gps_geofence_manager"].set_notification_manager(
                notification_manager
            )

        self._modules.attach_managers(
            data_manager=managers["data_manager"],
            feeding_manager=managers["feeding_manager"],
            walk_manager=managers["walk_manager"],
            gps_geofence_manager=managers["gps_geofence_manager"],
            weather_health_manager=managers["weather_health_manager"],
            garden_manager=managers["garden_manager"],
        )

    def clear_runtime_managers(self) -> None:
        for attr in (
            "data_manager",
            "feeding_manager",
            "walk_manager",
            "notification_manager",
            "gps_geofence_manager",
            "geofencing_manager",
            "weather_health_manager",
            "garden_manager",
        ):
            setattr(self, attr, None)
        self._modules.detach_managers()

    async def _async_setup(self) -> None:
        if self._setup_complete:
            return

        self._data = {
            dog_id: self.registry.empty_payload() for dog_id in self.registry.ids()
        }
        self._modules.clear_caches()
        self._setup_complete = True

    async def _async_update_data(self) -> dict[str, Any]:
        if len(self.registry) == 0:
            return {}

        await self._async_setup()
        dog_ids = self.registry.ids()
        if not dog_ids:
            raise CoordinatorUpdateFailed("No valid dogs configured")

        self._metrics.start_cycle()
        cycle_start = time.perf_counter()
        result = await self._fetch_all_dogs(dog_ids)

        duration = max(time.perf_counter() - cycle_start, 0.0)
        error_ratio = result.errors / len(dog_ids)
        new_interval = self._adaptive_polling.record_cycle(
            duration=duration,
            success=result.errors < len(dog_ids),
            error_ratio=error_ratio,
        )
        self._apply_adaptive_interval(new_interval)

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

    def _apply_adaptive_interval(self, new_interval: float) -> None:
        current_seconds = self.update_interval.total_seconds()
        if abs(current_seconds - new_interval) < 0.01:
            return

        _LOGGER.debug(
            "Adaptive polling adjusted interval from %.3fs to %.3fs",
            current_seconds,
            new_interval,
        )
        self.update_interval = timedelta(seconds=new_interval)

    async def _fetch_all_dogs(self, dog_ids: list[str]) -> UpdateResult:
        return await fetch_all_dogs(self, dog_ids)

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
        return await fetch_single_dog(self, dog_id)

    def get_dog_config(self, dog_id: str) -> Any:
        return self.registry.get(dog_id)

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
        return self.registry.enabled_modules(dog_id)

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        return module in self.registry.enabled_modules(dog_id)

    def get_dog_ids(self) -> list[str]:
        return self.registry.ids()

    get_configured_dog_ids = get_dog_ids

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        return self._data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        return self._data.get(dog_id, {}).get(module, {})

    def get_configured_dog_name(self, dog_id: str) -> str | None:
        return self.registry.get_name(dog_id)

    @property
    def available(self) -> bool:
        return self.last_update_success and self._metrics.consecutive_errors < 5

    def get_update_statistics(self) -> dict[str, Any]:
        return build_update_statistics(self)

    def get_statistics(self) -> dict[str, Any]:
        return build_runtime_statistics(self)

    @callback
    def async_start_background_tasks(self) -> None:
        ensure_background_task(self, MAINTENANCE_INTERVAL)

    async def _async_maintenance(self, *_: Any) -> None:
        await run_maintenance(self)

    async def async_shutdown(self) -> None:
        await shutdown_tasks(self)
