"""Coordinator for the PawControl integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_EXTERNAL_INTEGRATIONS,
    UPDATE_INTERVALS,
)
from .coordinator_observability import (
    EntityBudgetTracker,
    build_performance_snapshot,
    build_security_scorecard,
    normalise_webhook_status,
)
from .coordinator_runtime import (
    API_TIMEOUT,
    AdaptivePollingController,
    CoordinatorRuntime,
    EntityBudgetSnapshot,
)
from .coordinator_support import CoordinatorMetrics, DogConfigRegistry, UpdateResult
from .coordinator_tasks import (
    build_runtime_statistics,
    build_update_statistics,
    ensure_background_task,
    run_maintenance,
)
from .coordinator_tasks import shutdown as shutdown_tasks
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

        self._modules = CoordinatorModuleAdapters(
            session=self.session,
            config_entry=entry,
            use_external_api=self._use_external_api,
            cache_ttl=timedelta(seconds=CACHE_TTL_SECONDS),
            api_client=self._api_client,
        )

        self._data: dict[str, dict[str, Any]] = {
            dog_id: self.registry.empty_payload() for dog_id in self.registry.ids()
        }
        self._metrics = CoordinatorMetrics()
        self._entity_budget = EntityBudgetTracker()
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

        self._entity_budget.record(snapshot)
        self._adaptive_polling.update_entity_saturation(
            self._entity_budget.saturation()
        )

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

        data, cycle = await self._runtime.execute_cycle(
            dog_ids,
            self._data,
            empty_payload_factory=self.registry.empty_payload,
        )
        self._apply_adaptive_interval(cycle.new_interval)

        self._data = data
        return self._data

    async def _fetch_dog_data_protected(self, dog_id: str) -> dict[str, Any]:
        """Delegate to the runtime's protected fetch for legacy callers."""

        return await self._runtime._fetch_dog_data_protected(dog_id)

    async def _fetch_dog_data(self, dog_id: str) -> dict[str, Any]:
        """Delegate to the runtime fetch implementation."""

        return await self._runtime._fetch_dog_data(dog_id)

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

    def get_performance_snapshot(self) -> dict[str, Any]:
        """Return a lightweight snapshot of runtime performance metrics."""

        adaptive = self._adaptive_polling.as_diagnostics()
        entity_budget = self._entity_budget.summary()
        update_interval = (
            self.update_interval.total_seconds() if self.update_interval else 0.0
        )
        last_update_time = getattr(self, "last_update_time", None)

        return build_performance_snapshot(
            metrics=self._metrics,
            adaptive=adaptive,
            entity_budget=entity_budget,
            update_interval=update_interval,
            last_update_time=last_update_time,
            last_update_success=self.last_update_success,
            webhook_status=self._webhook_security_status(),
        )

    def get_security_scorecard(self) -> dict[str, Any]:
        """Return aggregated pass/fail status for security critical checks."""

        adaptive = self._adaptive_polling.as_diagnostics()
        entity_summary = self._entity_budget.summary()
        webhook_status = self._webhook_security_status()
        return build_security_scorecard(
            adaptive=adaptive,
            entity_summary=entity_summary,
            webhook_status=webhook_status,
        )

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

    def _webhook_security_status(self) -> dict[str, Any]:
        """Return normalised webhook security information."""

        manager = getattr(self, "notification_manager", None)
        return normalise_webhook_status(manager)
