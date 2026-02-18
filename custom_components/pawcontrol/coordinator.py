"""Coordinator for the PawControl integration."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import timedelta
from inspect import isawaitable
import logging
from time import perf_counter
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import (
    coordinator_observability,
    coordinator_runtime,
    coordinator_support,
    coordinator_tasks,
    types as paw_types,
)
from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_EXTERNAL_INTEGRATIONS,
    MODULE_GARDEN,
    MODULE_WALK,
    UPDATE_INTERVALS,
)
from .coordinator_accessors import CoordinatorDataAccessMixin
from .device_api import PawControlDeviceClient
from .exceptions import ConfigEntryAuthFailed, UpdateFailed, ValidationError
from .http_client import ensure_shared_client_session
from .logging_utils import log_api_client_build_error
from .module_adapters import CoordinatorModuleAdapters
from .resilience import ResilienceManager, RetryConfig
from .telemetry import get_runtime_performance_stats
from .types import PawControlConfigEntry
from .utils import deep_merge_dicts

# Single canonical alias — do not re-define CoordinatorUpdateFailed in other modules.
# See py/multiple-definition fix: exceptions.py also exposes UpdateFailed; importing
# that alias and re-aliasing here was the root of the multiple-definition alert.
CoordinatorUpdateFailed = UpdateFailed

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
GARDEN_MODULE_FIELD: Final[Literal["garden"]] = cast(
    Literal["garden"],
    MODULE_GARDEN,
)

CACHE_TTL_SECONDS: Final[int] = 300
MAINTENANCE_INTERVAL: Final[timedelta] = timedelta(hours=1)

EntityBudgetSnapshot = coordinator_runtime.EntityBudgetSnapshot
RuntimeCycleInfo = coordinator_runtime.RuntimeCycleInfo

__all__ = ["EntityBudgetSnapshot", "PawControlCoordinator", "RuntimeCycleInfo"]


class PawControlCoordinator(
    CoordinatorDataAccessMixin,
    DataUpdateCoordinator[paw_types.CoordinatorDataPayload],
):
    """Central orchestrator that keeps runtime logic in dedicated helpers."""

    _options: paw_types.ConfigEntryOptionsPayload

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PawControlConfigEntry,
        session: ClientSession,
    ) -> None:
        """Initialise the coordinator with Home Assistant runtime context."""
        self.config_entry = entry
        self._options = cast(paw_types.ConfigEntryOptionsPayload, entry.options)
        self.session = ensure_shared_client_session(
            session,
            owner="PawControlCoordinator",
        )
        self.registry = coordinator_support.DogConfigRegistry.from_entry(entry)
        self._use_external_api = bool(
            self._options.get(CONF_EXTERNAL_INTEGRATIONS, False),
        )
        # Initialise resilience handling before building the API client so the
        # underlying device client can use shared retry/backoff logic.
        self.resilience_manager = ResilienceManager(hass)
        self._retry_config = RetryConfig(
            max_attempts=2,
            initial_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=True,
        )
        endpoint = self._options.get(CONF_API_ENDPOINT)
        token = self._options.get(CONF_API_TOKEN)
        self._api_client = self._build_api_client(
            endpoint=endpoint if isinstance(endpoint, str) else "",
            token=token if isinstance(token, str) else "",
            resilience_manager=self.resilience_manager,
        )

        base_interval = self._initial_update_interval(entry)
        self._adaptive_polling = coordinator_runtime.AdaptivePollingController(
            initial_interval_seconds=float(base_interval),
            min_interval_seconds=float(max(base_interval * 0.25, 30.0)),
            max_interval_seconds=float(max(base_interval * 4, 900.0)),
            idle_interval_seconds=float(max(base_interval * 6, 900.0)),
            idle_grace_seconds=600.0,
        )

        super().__init__(
            hass,
            logger=_LOGGER,
            name="PawControl Data",
            update_interval=timedelta(seconds=base_interval),
            config_entry=entry,
        )
        self.last_update_success = True
        # NOTE: Do NOT set self.last_update_time — DataUpdateCoordinator provides
        # ``last_update_success_time`` as the authoritative last-update timestamp.
        # A custom ``last_update_time`` attribute set here would never be updated by
        # the base class and would always remain None in performance snapshots.
        # All callers should use ``getattr(coordinator, "last_update_success_time")``.

        # DataUpdateCoordinator initialises ``update_interval`` but MyPy cannot
        # determine the attribute on subclasses without an explicit assignment.
        # Re-assign the value here to make the attribute type explicit for
        # downstream telemetry helpers.
        self.update_interval = timedelta(seconds=base_interval)

        self._modules = CoordinatorModuleAdapters(
            session=self.session,
            config_entry=entry,
            use_external_api=self._use_external_api,
            cache_ttl=timedelta(seconds=CACHE_TTL_SECONDS),
            api_client=self._api_client,
        )

        self._data: paw_types.CoordinatorDataPayload = {
            dog_id: self.registry.empty_payload() for dog_id in self.registry.ids()
        }
        self._metrics = coordinator_support.CoordinatorMetrics()
        self._entity_budget = coordinator_observability.EntityBudgetTracker()
        self._setup_complete = False
        self._maintenance_unsub: callback | None = None

        self.data_manager: PawControlDataManager | None = None
        self.feeding_manager: FeedingManager | None = None
        self.walk_manager: WalkManager | None = None
        self.notification_manager: PawControlNotificationManager | None = None
        self.gps_geofence_manager: GPSGeofenceManager | None = None
        self.geofencing_manager: PawControlGeofencing | None = None
        self.weather_health_manager: WeatherHealthManager | None = None
        self.garden_manager: GardenManager | None = None

        self._runtime_managers = paw_types.CoordinatorRuntimeManagers()

        # resilience_manager and _retry_config are initialised earlier

        self._runtime = coordinator_runtime.CoordinatorRuntime(
            registry=self.registry,
            modules=self._modules,
            resilience_manager=self.resilience_manager,
            retry_config=self._retry_config,
            metrics=self._metrics,
            adaptive_polling=self._adaptive_polling,
            logger=_LOGGER,
        )
        self._last_cycle: RuntimeCycleInfo | None = None

        _LOGGER.info(
            "Coordinator started (event=coordinator_start dogs=%d interval_s=%d external_api=%s)",  # noqa: E501
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
        self,
        *,
        endpoint: str,
        token: str,
        resilience_manager: ResilienceManager | None,
    ) -> PawControlDeviceClient | None:
        if not endpoint:
            return None
        try:
            return PawControlDeviceClient(
                session=self.session,
                endpoint=endpoint.strip(),
                api_key=token.strip() or None,
                resilience_manager=resilience_manager,
            )
        except ValueError as err:
            # Use the logging utility so the token is never included in the
            # warning message (py/clear-text-logging-sensitive-data fix).
            log_api_client_build_error(_LOGGER, endpoint, err)
            return None

    @property
    def use_external_api(self) -> bool:
        """Return whether the external Paw Control API is enabled."""
        return self._use_external_api

    @use_external_api.setter
    def use_external_api(self, value: bool) -> None:
        self._use_external_api = bool(value)

    @property
    def api_client(self) -> PawControlDeviceClient | None:
        """Return the device API client when configured."""
        return self._api_client

    def report_entity_budget(self, snapshot: EntityBudgetSnapshot) -> None:
        """Receive entity budget metrics from the entity factory."""

        self._entity_budget.record(snapshot)
        self._adaptive_polling.update_entity_saturation(
            self._entity_budget.saturation(),
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
        """Bind manager instances to the module adapters."""
        managers = paw_types.CoordinatorRuntimeManagers(
            data_manager=data_manager,
            feeding_manager=feeding_manager,
            walk_manager=walk_manager,
            notification_manager=notification_manager,
            gps_geofence_manager=gps_geofence_manager,
            geofencing_manager=geofencing_manager,
            weather_health_manager=weather_health_manager,
            garden_manager=garden_manager,
        )
        self._runtime_managers = managers

        coordinator_support.bind_runtime_managers(self, self._modules, managers)

        if hasattr(data_manager, "set_metrics_sink"):
            data_manager.set_metrics_sink(self._metrics)

    def clear_runtime_managers(self) -> None:
        """Detach runtime managers during teardown or reload."""
        coordinator_support.clear_runtime_managers(self, self._modules)
        self._runtime_managers = paw_types.CoordinatorRuntimeManagers()

    @property
    def runtime_managers(self) -> paw_types.CoordinatorRuntimeManagers:
        """Return the currently attached runtime managers."""

        return self._runtime_managers

    @runtime_managers.setter
    def runtime_managers(self, managers: paw_types.CoordinatorRuntimeManagers) -> None:
        """Replace the cached runtime manager container."""

        self._runtime_managers = managers

    async def async_prepare_entry(self) -> None:
        """Public hook to initialize coordinator state for a config entry."""

        if self._setup_complete:
            return
        self._data = {
            dog_id: self.registry.empty_payload() for dog_id in self.registry.ids()
        }
        self._modules.clear_caches()
        self._setup_complete = True

    async def _async_update_data(self) -> paw_types.CoordinatorDataPayload:
        if len(self.registry) == 0:
            return {}
        # async_prepare_entry is idempotent; setup logic runs only once per entry.
        await self.async_prepare_entry()
        dog_ids = self.registry.ids()
        if not dog_ids:
            raise CoordinatorUpdateFailed("No valid dogs configured")
        try:
            data, _cycle = await self._execute_cycle(dog_ids)
        except ConfigEntryAuthFailed:
            # Propagate configuration auth failures directly.
            raise
        except UpdateFailed:
            # Propagate known update failures
            raise
        except Exception as err:
            # Log and wrap unknown exceptions into CoordinatorUpdateFailed
            _LOGGER.error(
                "Unhandled error during coordinator update: %s (%s)",
                err,
                err.__class__.__name__,
            )
            raise CoordinatorUpdateFailed(
                f"Coordinator update failed: {err}",
            ) from err

        # Synchronize module states separately; log but do not raise on failure
        try:
            await self._synchronize_module_states(data)
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.warning(
                "Failed to synchronize module states: %s (%s)",
                err,
                err.__class__.__name__,
            )

        self._data = data
        # BUG FIX: Do NOT call async_set_updated_data here.
        # DataUpdateCoordinator._async_refresh already sets self.data from the
        # return value of _async_update_data and notifies all listeners.
        # Calling async_set_updated_data manually caused a DOUBLE notification:
        #   1) premature broadcast inside this method
        #   2) second broadcast by the base class after we return
        # This doubled every entity state-write and recorder write each cycle.
        # Tests that call _async_update_data() directly should patch the method or
        # invoke coordinator.async_request_refresh() through the full HA harness.
        return self._data

    async def _fetch_dog_data(self, dog_id: str) -> paw_types.CoordinatorDogData:
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

    async def _execute_cycle(
        self,
        dog_ids: Sequence[str],
    ) -> tuple[paw_types.CoordinatorDataPayload, RuntimeCycleInfo]:
        _LOGGER.debug(
            "Update cycle starting (event=update_cycle_start dogs=%d)",
            len(dog_ids),
        )
        cycle_start = perf_counter()
        data, cycle = await self._runtime.execute_cycle(
            dog_ids,
            self._data,
            empty_payload_factory=self.registry.empty_payload,
        )
        duration = perf_counter() - cycle_start
        _LOGGER.debug(
            "Update cycle completed (event=update_cycle_end dogs=%d duration_ms=%.2f interval_s=%.2f)",  # noqa: E501
            len(dog_ids),
            duration * 1000,
            cycle.new_interval,
        )
        self._apply_adaptive_interval(cycle.new_interval)
        self._last_cycle = cycle
        return data, cycle

    async def _refresh_subset(self, dog_ids: Sequence[str]) -> None:
        if not dog_ids:
            return
        data, _cycle = await self._execute_cycle(dog_ids)
        await self._synchronize_module_states(data)
        for dog_id in dog_ids:
            if dog_id in data:
                self._data[dog_id] = data[dog_id]

        self.async_set_updated_data(dict(self._data))

    async def async_refresh_dog(self, dog_id: str) -> None:
        """Refresh data for a specific dog on demand."""
        if dog_id not in self.registry.ids():
            _LOGGER.debug("Ignoring refresh for unknown dog_id: %s", dog_id)
            return
        await self._refresh_subset([dog_id])

    async def async_patch_gps_update(self, dog_id: str) -> None:
        """Patch only GPS-related coordinator payload for ``dog_id``.

        This is used by push-style GPS updates (webhooks/BLE/etc.) to avoid a full
        coordinator refresh cycle. It updates the `gps` and derived `geofencing`
        module payloads in-place and notifies subscribed entities.
        """

        if dog_id not in self.registry.ids():
            _LOGGER.debug("Ignoring GPS patch for unknown dog_id: %s", dog_id)
            return
        if not self._setup_complete or not self._data or not self.last_update_success:
            _LOGGER.debug(
                "Deferring GPS patch for %s because coordinator data is not ready",
                dog_id,
            )
            await self.async_request_refresh()
            return
        current = self._data.get(dog_id)
        if not isinstance(current, Mapping):
            _LOGGER.warning(
                "Cannot patch GPS data for %s because no payload is available",
                dog_id,
            )
            return
        gps_payload = await self._modules.gps.async_get_data(dog_id)
        geofencing_payload = await self._modules.geofencing.async_get_data(dog_id)

        patched: paw_types.CoordinatorDogData = cast(
            paw_types.CoordinatorDogData, dict(current)
        )
        patched["gps"] = cast(paw_types.CoordinatorModuleState, gps_payload)
        # `geofencing` is a derived payload that is executed whenever GPS is enabled.
        patched["geofencing"] = cast(
            paw_types.CoordinatorModuleState, geofencing_payload
        )

        self._data[dog_id] = patched
        self.async_set_updated_data(dict(self._data))

    async def async_request_selective_refresh(
        self,
        dog_ids: Iterable[str] | None = None,
    ) -> None:
        """Refresh a subset of dogs while keeping existing payloads."""

        if dog_ids is None:
            await self.async_request_refresh()
            return
        unique_ids = [dog_id for dog_id in dict.fromkeys(dog_ids) if dog_id]
        if not unique_ids:
            return
        await self._refresh_subset(unique_ids)

    def get_dog_config(self, dog_id: str) -> paw_types.DogConfigData | None:
        """Return the raw configuration for the specified dog."""

        return CoordinatorDataAccessMixin.get_dog_config(self, dog_id)

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
        """Return the modules enabled for the given dog."""
        return self.registry.enabled_modules(dog_id)

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        """Return True if the module is enabled for the dog."""
        return module in self.registry.enabled_modules(dog_id)

    def get_dog_ids(self) -> list[str]:
        """Return identifiers for all configured dogs."""

        return CoordinatorDataAccessMixin.get_dog_ids(self)

    def get_dog_data(self, dog_id: str) -> paw_types.CoordinatorDogData | None:
        """Return the coordinator data payload for the dog."""

        return CoordinatorDataAccessMixin.get_dog_data(self, dog_id)

    async def async_apply_module_updates(
        self,
        dog_id: str,
        module: str,
        updates: Mapping[str, paw_types.JSONValue],
    ) -> None:
        """Apply module updates to the coordinator data cache."""

        if dog_id not in self.registry.ids():
            _LOGGER.debug(
                "Ignoring module update for unknown dog_id: %s",
                dog_id,
            )
            return
        if not isinstance(module, str) or not module:
            _LOGGER.debug(
                "Ignoring module update for %s because module is invalid",
                dog_id,
            )
            return
        current = self._data.get(dog_id)
        if isinstance(current, Mapping):
            dog_payload: paw_types.JSONMutableMapping = cast(
                paw_types.JSONMutableMapping, dict(current)
            )
        else:
            dog_payload = cast(
                paw_types.JSONMutableMapping, self.registry.empty_payload()
            )
        existing_module = dog_payload.get(module)
        base_payload: paw_types.JSONMutableMapping = (
            dict(existing_module) if isinstance(existing_module, Mapping) else {}
        )
        merged = deep_merge_dicts(base_payload, updates)
        dog_payload[module] = merged
        self._data[dog_id] = cast(paw_types.CoordinatorDogData, dog_payload)

        updated_payload = dict(self._data)
        setter = getattr(self, "async_set_updated_data", None)
        if callable(setter):
            result = setter(updated_payload)
            if isawaitable(result):
                await result
        else:  # pragma: no cover - exercised via lightweight test stubs
            self.data = updated_payload

    async def _synchronize_module_states(
        self, data: paw_types.CoordinatorDataPayload
    ) -> None:
        """Synchronize conflicting module states across managers."""

        garden_manager = self.garden_manager
        if garden_manager is None:
            return
        for dog_id, dog_payload in data.items():
            if not isinstance(dog_payload, Mapping):
                continue
            mutable_payload = dict(dog_payload)
            walk_state = mutable_payload.get(MODULE_WALK)
            walk_active = False
            if isinstance(walk_state, Mapping):
                walk_active = bool(walk_state.get("walk_in_progress"))

            if not walk_active:
                continue

            active_session = garden_manager.get_active_session(dog_id)
            if active_session is None:
                continue

            await garden_manager.async_end_garden_session(
                dog_id,
                notes="Paused due to active walk",
                suppress_notifications=True,
            )
            mutable_payload[GARDEN_MODULE_FIELD] = cast(
                paw_types.CoordinatorModuleState,
                garden_manager.build_garden_snapshot(dog_id),
            )
            data[dog_id] = cast(paw_types.CoordinatorDogData, mutable_payload)

    @property
    def available(self) -> bool:
        """Return True if the coordinator considers itself healthy."""
        return self.last_update_success and self._metrics.consecutive_errors < 5

    def get_update_statistics(self) -> paw_types.CoordinatorStatisticsPayload:
        """Return statistics for the most recent update cycle."""
        return coordinator_tasks.build_update_statistics(self)

    def get_statistics(self) -> paw_types.CoordinatorRuntimeStatisticsPayload:
        """Return cumulative runtime statistics for diagnostics."""
        start = perf_counter()
        stats = coordinator_tasks.build_runtime_statistics(self)
        duration = perf_counter() - start
        self._metrics.record_statistics_timing(duration)
        self.logger.debug(
            "Runtime statistics generated in %.3f ms (avg %.3f ms over %d samples)",
            duration * 1000,
            self._metrics.average_statistics_runtime_ms,
            len(self._metrics.statistics_timings),
        )
        return stats

    def get_performance_snapshot(self) -> paw_types.CoordinatorPerformanceSnapshot:
        """Return a comprehensive performance snapshot for diagnostics surfaces."""

        adaptive = self._adaptive_polling.as_diagnostics()
        entity_budget = self._entity_budget.summary()
        update_interval = (
            self.update_interval.total_seconds() if self.update_interval else 0.0
        )
        # Use HA's native last_update_success_time — the custom last_update_time
        # attribute was never updated after init and always returned None.
        last_update_time = getattr(self, "last_update_success_time", None)

        resilience = coordinator_tasks.collect_resilience_diagnostics(self)

        base_snapshot = coordinator_observability.build_performance_snapshot(
            metrics=self._metrics,
            adaptive=adaptive,
            entity_budget=entity_budget,
            update_interval=update_interval,
            last_update_time=last_update_time,
            last_update_success=self.last_update_success,
            webhook_status=self._webhook_security_status(),
            resilience=resilience.get("summary") if resilience else None,
        )
        snapshot = cast(paw_types.CoordinatorPerformanceSnapshot, dict(base_snapshot))

        if resilience:
            snapshot["resilience"] = resilience
        rejection_metrics = snapshot.get("rejection_metrics")
        if not isinstance(rejection_metrics, Mapping):
            rejection_metrics = coordinator_tasks.default_rejection_metrics()
            snapshot["rejection_metrics"] = rejection_metrics
        runtime_data = getattr(self.config_entry, "runtime_data", None)
        performance_stats_payload = get_runtime_performance_stats(
            runtime_data,
        )
        guard_metrics = coordinator_tasks.resolve_service_guard_metrics(
            performance_stats_payload,
        )
        entity_factory_guard = coordinator_tasks.resolve_entity_factory_guard_metrics(
            performance_stats_payload,
        )
        snapshot["service_execution"] = {
            "guard_metrics": guard_metrics,
            "entity_factory_guard": entity_factory_guard,
            "rejection_metrics": rejection_metrics,
        }

        if self._last_cycle is not None:
            snapshot["last_cycle"] = self._last_cycle.to_dict()
        return snapshot

    def get_security_scorecard(self) -> paw_types.CoordinatorSecurityScorecard:
        """Return aggregated pass/fail status for security critical checks."""

        adaptive = self._adaptive_polling.as_diagnostics()
        entity_summary = self._entity_budget.summary()
        webhook_status = self._webhook_security_status()
        return coordinator_observability.build_security_scorecard(
            adaptive=cast(paw_types.JSONMapping, adaptive),
            entity_summary=cast(paw_types.JSONMapping, entity_summary),
            webhook_status=webhook_status,
        )

    @callback  # type: ignore[untyped-decorator,misc]
    def async_start_background_tasks(self) -> None:
        """Start recurring background maintenance tasks."""
        coordinator_tasks.ensure_background_task(self, MAINTENANCE_INTERVAL)

    async def _async_maintenance(self, *_: Any) -> None:
        await coordinator_tasks.run_maintenance(self)

    async def async_shutdown(self) -> None:
        """Stop background tasks and release resources."""
        await coordinator_tasks.shutdown(self)

    def _webhook_security_status(self) -> paw_types.WebhookSecurityStatus:
        """Return normalised webhook security information."""

        manager = getattr(self, "notification_manager", None)
        return coordinator_observability.normalise_webhook_status(manager)
