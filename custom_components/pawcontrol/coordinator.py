"""Coordinator for the PawControl integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_EXTERNAL_INTEGRATIONS,
)
from .coordinator_runtime import (
    AdaptivePollingController,
    CoordinatorRuntime,
    EntityBudgetSnapshot,
    RuntimeCycleInfo,
    summarize_entity_budgets,
)
from .coordinator_support import CoordinatorMetrics, DogConfigRegistry
from .device_api import PawControlDeviceClient
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

        base_interval = self.registry.calculate_update_interval(entry.options)
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
        self._entity_budget_summary = summarize_entity_budgets(())
        self._last_cycle: RuntimeCycleInfo | None = None
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
            use_external_api,
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

    def report_entity_budget(self, snapshot: EntityBudgetSnapshot) -> None:
        """Receive entity budget metrics from the entity factory."""

        self._entity_budget_snapshots[snapshot.dog_id] = snapshot
        self._entity_budget_summary = summarize_entity_budgets(
            self._entity_budget_snapshots.values()
        )
        self._adaptive_polling.update_entity_saturation(
            self._entity_budget_summary["peak_utilization"] / 100
        )

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
        data, cycle = await self._runtime.execute_cycle(
            dog_ids,
            self._data,
            empty_payload_factory=self.registry.empty_payload,
        )

        self._data = data
        self._last_cycle = cycle
        self.update_interval = timedelta(seconds=cycle.new_interval)
        return self._data

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

    def get_dog_config(self, dog_id: str) -> Any:
        return self.registry.get(dog_id)

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
        return self.registry.enabled_modules(dog_id)

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        return module in self.registry.enabled_modules(dog_id)

    def get_dog_ids(self) -> list[str]:
        return self.registry.ids()

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        return self._data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        return self._data.get(dog_id, {}).get(module, {})

    def get_configured_dog_ids(self) -> list[str]:
        return self.registry.ids()

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
        stats["adaptive_polling"] = self._adaptive_polling.as_diagnostics()
        stats["entity_budget"] = self._entity_budget_summary
        if self._last_cycle:
            stats["last_cycle"] = self._last_cycle.to_dict()
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
