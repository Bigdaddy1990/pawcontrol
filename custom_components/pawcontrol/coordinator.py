"""Coordinator for the PawControl integration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import timedelta
from inspect import isawaitable
import logging
from time import perf_counter
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
  CONF_API_ENDPOINT,
  CONF_API_TOKEN,
  CONF_EXTERNAL_INTEGRATIONS,
  MODULE_GARDEN,
  MODULE_WALK,
  UPDATE_INTERVALS,
)
from .coordinator_accessors import CoordinatorDataAccessMixin
from .coordinator_observability import (
  EntityBudgetTracker,
  build_performance_snapshot as build_observability_snapshot,
  build_security_scorecard as build_observability_scorecard,
  normalise_webhook_status,
)
from .coordinator_runtime import (
  AdaptivePollingController,
  CoordinatorRuntime,
  EntityBudgetSnapshot,
  RuntimeCycleInfo,
)
from .coordinator_support import (
  CoordinatorMetrics,
  DogConfigRegistry,
  bind_runtime_managers,
  clear_runtime_managers as unbind_runtime_managers,
)
from .coordinator_tasks import (
  build_runtime_statistics,
  build_update_statistics,
  collect_resilience_diagnostics,
  default_rejection_metrics,
  ensure_background_task,
  resolve_entity_factory_guard_metrics,
  resolve_service_guard_metrics,
  run_maintenance,
  shutdown as shutdown_tasks,
)
from .device_api import PawControlDeviceClient
from .exceptions import ConfigEntryAuthFailed, UpdateFailed, ValidationError
from .http_client import ensure_shared_client_session
from .module_adapters import CoordinatorModuleAdapters
from .resilience import ResilienceManager, RetryConfig
from .telemetry import get_runtime_performance_stats
from .types import (
  ConfigEntryOptionsPayload,
  CoordinatorDataPayload,
  CoordinatorDogData,
  CoordinatorModuleState,
  CoordinatorPerformanceSnapshot,
  CoordinatorRuntimeManagers,
  CoordinatorRuntimeStatisticsPayload,
  CoordinatorSecurityScorecard,
  CoordinatorStatisticsPayload,
  DogConfigData,
  JSONMapping,
  JSONMutableMapping,
  JSONValue,
  PawControlConfigEntry,
  PawControlRuntimeData,
  WebhookSecurityStatus,
)
from .utils import deep_merge_dicts

# Maintain the legacy name to avoid touching the rest of the module logic
CoordinatorUpdateFailed = UpdateFailed

if TYPE_CHECKING:
  from .data_manager import PawControlDataManager  # noqa: E111
  from .feeding_manager import FeedingManager  # noqa: E111
  from .garden_manager import GardenManager  # noqa: E111
  from .geofencing import PawControlGeofencing  # noqa: E111
  from .gps_manager import GPSGeofenceManager  # noqa: E111
  from .notifications import PawControlNotificationManager  # noqa: E111
  from .walk_manager import WalkManager  # noqa: E111
  from .weather_manager import WeatherHealthManager  # noqa: E111


_LOGGER = logging.getLogger(__name__)
GARDEN_MODULE_FIELD: Final[Literal["garden"]] = cast(
  Literal["garden"],
  MODULE_GARDEN,
)

CACHE_TTL_SECONDS = 300
MAINTENANCE_INTERVAL = timedelta(hours=1)

__all__ = ["EntityBudgetSnapshot", "PawControlCoordinator", "RuntimeCycleInfo"]


class PawControlCoordinator(
  CoordinatorDataAccessMixin,
  DataUpdateCoordinator[CoordinatorDataPayload],
):
  """Central orchestrator that keeps runtime logic in dedicated helpers."""  # noqa: E111

  _options: ConfigEntryOptionsPayload  # noqa: E111

  def __init__(  # noqa: E111
    self,
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    session: ClientSession,
  ) -> None:
    """Initialise the coordinator with Home Assistant runtime context."""
    self.config_entry = entry
    self._options = cast(ConfigEntryOptionsPayload, entry.options)
    self.session = ensure_shared_client_session(
      session,
      owner="PawControlCoordinator",
    )
    self.registry = DogConfigRegistry.from_entry(entry)
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
    self._adaptive_polling = AdaptivePollingController(
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
    self.last_update_time = None

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

    self._data: CoordinatorDataPayload = {
      dog_id: self.registry.empty_payload() for dog_id in self.registry.ids()
    }
    self._metrics = CoordinatorMetrics()
    self._entity_budget = EntityBudgetTracker()
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

    self._runtime_managers = CoordinatorRuntimeManagers()

    # resilience_manager and _retry_config are initialised earlier

    self._runtime = CoordinatorRuntime(
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

  def _initial_update_interval(self, entry: PawControlConfigEntry) -> int:  # noqa: E111
    try:
      return self.registry.calculate_update_interval(entry.options)  # noqa: E111
    except ValidationError as err:
      _LOGGER.warning("Invalid update interval configuration: %s", err)  # noqa: E111
      return UPDATE_INTERVALS.get("balanced", 120)  # noqa: E111

  def _build_api_client(  # noqa: E111
    self,
    *,
    endpoint: str,
    token: str,
    resilience_manager: ResilienceManager | None,
  ) -> PawControlDeviceClient | None:
    if not endpoint:
      return None  # noqa: E111

    try:
      return PawControlDeviceClient(  # noqa: E111
        session=self.session,
        endpoint=endpoint.strip(),
        api_key=token.strip() or None,
        resilience_manager=resilience_manager,
      )
    except ValueError as err:
      _LOGGER.warning(  # noqa: E111
        "Invalid Paw Control API endpoint '%s': %s",
        endpoint,
        err,
      )
      return None  # noqa: E111

  @property  # noqa: E111
  def use_external_api(self) -> bool:  # noqa: E111
    """Return whether the external Paw Control API is enabled."""
    return self._use_external_api

  @use_external_api.setter  # noqa: E111
  def use_external_api(self, value: bool) -> None:  # noqa: E111
    self._use_external_api = bool(value)

  @property  # noqa: E111
  def api_client(self) -> PawControlDeviceClient | None:  # noqa: E111
    """Return the device API client when configured."""
    return self._api_client

  def report_entity_budget(self, snapshot: EntityBudgetSnapshot) -> None:  # noqa: E111
    """Receive entity budget metrics from the entity factory."""

    self._entity_budget.record(snapshot)
    self._adaptive_polling.update_entity_saturation(
      self._entity_budget.saturation(),
    )

  def attach_runtime_managers(  # noqa: E111
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
    managers = CoordinatorRuntimeManagers(
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

    bind_runtime_managers(self, self._modules, managers)

    if hasattr(data_manager, "set_metrics_sink"):
      data_manager.set_metrics_sink(self._metrics)  # noqa: E111

  def clear_runtime_managers(self) -> None:  # noqa: E111
    """Detach runtime managers during teardown or reload."""
    unbind_runtime_managers(self, self._modules)
    self._runtime_managers = CoordinatorRuntimeManagers()

  @property  # noqa: E111
  def runtime_managers(self) -> CoordinatorRuntimeManagers:  # noqa: E111
    """Return the currently attached runtime managers."""

    return self._runtime_managers

  @runtime_managers.setter  # noqa: E111
  def runtime_managers(self, managers: CoordinatorRuntimeManagers) -> None:  # noqa: E111
    """Replace the cached runtime manager container."""

    self._runtime_managers = managers

  async def async_prepare_entry(self) -> None:  # noqa: E111
    """Public hook to initialize coordinator state for a config entry."""

    if self._setup_complete:
      return  # noqa: E111

    self._data = {
      dog_id: self.registry.empty_payload() for dog_id in self.registry.ids()
    }
    self._modules.clear_caches()
    self._setup_complete = True

  async def _async_update_data(self) -> CoordinatorDataPayload:  # noqa: E111
    if len(self.registry) == 0:
      return {}  # noqa: E111

    # async_prepare_entry is idempotent; setup logic runs only once per entry.
    await self.async_prepare_entry()
    dog_ids = self.registry.ids()
    if not dog_ids:
      raise CoordinatorUpdateFailed("No valid dogs configured")  # noqa: E111

    try:
      data, _cycle = await self._execute_cycle(dog_ids)  # noqa: E111
    except ConfigEntryAuthFailed:
      # Propagate configuration auth failures directly to Home Assistant  # noqa: E114
      raise  # noqa: E111
    except UpdateFailed:
      # Propagate known update failures  # noqa: E114
      raise  # noqa: E111
    except Exception as err:
      # Log and wrap unknown exceptions into CoordinatorUpdateFailed  # noqa: E114
      _LOGGER.error(  # noqa: E111
        "Unhandled error during coordinator update: %s (%s)",
        err,
        err.__class__.__name__,
      )
      raise CoordinatorUpdateFailed(  # noqa: E111
        f"Coordinator update failed: {err}",
      ) from err

    # Synchronize module states separately; log but do not raise on failure
    try:
      await self._synchronize_module_states(data)  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive logging
      _LOGGER.warning(  # noqa: E111
        "Failed to synchronize module states: %s (%s)",
        err,
        err.__class__.__name__,
      )

    self._data = data
    # Keep the DataUpdateCoordinator state in sync when callers invoke the
    # private helper directly during tests.  Home Assistant normally calls
    # :meth:`async_set_updated_data` after awaiting ``_async_update_data``
    # but the focused unit tests exercise the method in isolation.  Updating
    # the coordinator here ensures ``coordinator.data`` mirrors the most
    # recent payload even when the surrounding refresh workflow is bypassed.
    updated_payload = dict(self._data)
    setter = getattr(self, "async_set_updated_data", None)
    if callable(setter):
      result = setter(updated_payload)  # noqa: E111
      if isawaitable(result):  # noqa: E111
        await result
    else:  # pragma: no cover - exercised via the lightweight test stubs
      self.data = updated_payload  # noqa: E111
    return self._data

  async def _fetch_dog_data(self, dog_id: str) -> CoordinatorDogData:  # noqa: E111
    """Delegate to the runtime fetch implementation."""

    return await self._runtime._fetch_dog_data(dog_id)

  def _apply_adaptive_interval(self, new_interval: float) -> None:  # noqa: E111
    current_seconds = self.update_interval.total_seconds()
    if abs(current_seconds - new_interval) < 0.01:
      return  # noqa: E111

    _LOGGER.debug(
      "Adaptive polling adjusted interval from %.3fs to %.3fs",
      current_seconds,
      new_interval,
    )
    self.update_interval = timedelta(seconds=new_interval)

  async def _execute_cycle(  # noqa: E111
    self,
    dog_ids: Sequence[str],
  ) -> tuple[CoordinatorDataPayload, RuntimeCycleInfo]:
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

  async def _refresh_subset(self, dog_ids: Sequence[str]) -> None:  # noqa: E111
    if not dog_ids:
      return  # noqa: E111

    data, _cycle = await self._execute_cycle(dog_ids)
    await self._synchronize_module_states(data)
    for dog_id in dog_ids:
      if dog_id in data:  # noqa: E111
        self._data[dog_id] = data[dog_id]

    self.async_set_updated_data(dict(self._data))

  async def async_refresh_dog(self, dog_id: str) -> None:  # noqa: E111
    """Refresh data for a specific dog on demand."""
    if dog_id not in self.registry.ids():
      _LOGGER.debug("Ignoring refresh for unknown dog_id: %s", dog_id)  # noqa: E111
      return  # noqa: E111

    await self._refresh_subset([dog_id])

  async def async_patch_gps_update(self, dog_id: str) -> None:  # noqa: E111
    """Patch only GPS-related coordinator payload for ``dog_id``.

    This is used by push-style GPS updates (webhooks/BLE/etc.) to avoid a full
    coordinator refresh cycle. It updates the `gps` and derived `geofencing`
    module payloads in-place and notifies subscribed entities.
    """

    if dog_id not in self.registry.ids():
      _LOGGER.debug("Ignoring GPS patch for unknown dog_id: %s", dog_id)  # noqa: E111
      return  # noqa: E111

    if not self._setup_complete or not self._data or not self.last_update_success:
      _LOGGER.debug(  # noqa: E111
        "Deferring GPS patch for %s because coordinator data is not ready",
        dog_id,
      )
      await self.async_request_refresh()  # noqa: E111
      return  # noqa: E111

    current = self._data.get(dog_id)
    if not isinstance(current, Mapping):
      _LOGGER.warning(  # noqa: E111
        "Cannot patch GPS data for %s because no payload is available",
        dog_id,
      )
      return  # noqa: E111

    gps_payload = await self._modules.gps.async_get_data(dog_id)
    geofencing_payload = await self._modules.geofencing.async_get_data(dog_id)

    patched: CoordinatorDogData = cast(CoordinatorDogData, dict(current))
    patched["gps"] = cast(CoordinatorModuleState, gps_payload)
    # `geofencing` is a derived payload that is executed whenever GPS is enabled.
    patched["geofencing"] = cast(CoordinatorModuleState, geofencing_payload)

    self._data[dog_id] = patched
    self.async_set_updated_data(dict(self._data))

  async def async_request_selective_refresh(  # noqa: E111
    self,
    dog_ids: Iterable[str] | None = None,
  ) -> None:
    """Refresh a subset of dogs while keeping existing payloads."""

    if dog_ids is None:
      await self.async_request_refresh()  # noqa: E111
      return  # noqa: E111

    unique_ids = [dog_id for dog_id in dict.fromkeys(dog_ids) if dog_id]
    if not unique_ids:
      return  # noqa: E111

    await self._refresh_subset(unique_ids)

  def get_dog_config(self, dog_id: str) -> DogConfigData | None:  # noqa: E111
    """Return the raw configuration for the specified dog."""

    return CoordinatorDataAccessMixin.get_dog_config(self, dog_id)

  def get_enabled_modules(self, dog_id: str) -> frozenset[str]:  # noqa: E111
    """Return the modules enabled for the given dog."""
    return self.registry.enabled_modules(dog_id)

  def is_module_enabled(self, dog_id: str, module: str) -> bool:  # noqa: E111
    """Return True if the module is enabled for the dog."""
    return module in self.registry.enabled_modules(dog_id)

  def get_dog_ids(self) -> list[str]:  # noqa: E111
    """Return identifiers for all configured dogs."""

    return CoordinatorDataAccessMixin.get_dog_ids(self)

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:  # noqa: E111
    """Return the coordinator data payload for the dog."""

    return CoordinatorDataAccessMixin.get_dog_data(self, dog_id)

  async def async_apply_module_updates(  # noqa: E111
    self,
    dog_id: str,
    module: str,
    updates: Mapping[str, JSONValue],
  ) -> None:
    """Apply module updates to the coordinator data cache."""

    if dog_id not in self.registry.ids():
      _LOGGER.debug(  # noqa: E111
        "Ignoring module update for unknown dog_id: %s",
        dog_id,
      )
      return  # noqa: E111

    if not isinstance(module, str) or not module:
      _LOGGER.debug(  # noqa: E111
        "Ignoring module update for %s because module is invalid",
        dog_id,
      )
      return  # noqa: E111

    current = self._data.get(dog_id)
    if isinstance(current, Mapping):
      dog_payload: JSONMutableMapping = cast(JSONMutableMapping, dict(current))  # noqa: E111
    else:
      dog_payload = cast(JSONMutableMapping, self.registry.empty_payload())  # noqa: E111

    existing_module = dog_payload.get(module)
    base_payload: JSONMutableMapping = (
      dict(cast(Mapping[str, JSONValue], existing_module))
      if isinstance(existing_module, Mapping)
      else {}
    )
    merged = deep_merge_dicts(base_payload, updates)
    dog_payload[module] = merged
    self._data[dog_id] = cast(CoordinatorDogData, dog_payload)

    updated_payload = dict(self._data)
    setter = getattr(self, "async_set_updated_data", None)
    if callable(setter):
      result = setter(updated_payload)  # noqa: E111
      if isawaitable(result):  # noqa: E111
        await result
    else:  # pragma: no cover - exercised via lightweight test stubs
      self.data = updated_payload  # noqa: E111

  async def _synchronize_module_states(self, data: CoordinatorDataPayload) -> None:  # noqa: E111
    """Synchronize conflicting module states across managers."""

    garden_manager = self.garden_manager
    if garden_manager is None:
      return  # noqa: E111

    for dog_id, dog_payload in data.items():
      if not isinstance(dog_payload, Mapping):  # noqa: E111
        continue

      walk_state = dog_payload.get(MODULE_WALK)  # noqa: E111
      walk_active = False  # noqa: E111
      if isinstance(walk_state, Mapping):  # noqa: E111
        walk_active = bool(walk_state.get("walk_in_progress"))

      if not walk_active:  # noqa: E111
        continue

      active_session = garden_manager.get_active_session(dog_id)  # noqa: E111
      if active_session is None:  # noqa: E111
        continue

      await garden_manager.async_end_garden_session(  # noqa: E111
        dog_id,
        notes="Paused due to active walk",
        suppress_notifications=True,
      )
      dog_payload[GARDEN_MODULE_FIELD] = cast(  # noqa: E111
        CoordinatorModuleState,
        garden_manager.build_garden_snapshot(dog_id),
      )

  @property  # noqa: E111
  def available(self) -> bool:  # noqa: E111
    """Return True if the coordinator considers itself healthy."""
    return self.last_update_success and self._metrics.consecutive_errors < 5

  def get_update_statistics(self) -> CoordinatorStatisticsPayload:  # noqa: E111
    """Return statistics for the most recent update cycle."""
    return build_update_statistics(self)

  def get_statistics(self) -> CoordinatorRuntimeStatisticsPayload:  # noqa: E111
    """Return cumulative runtime statistics for diagnostics."""
    start = perf_counter()
    stats = build_runtime_statistics(self)
    duration = perf_counter() - start
    self._metrics.record_statistics_timing(duration)
    self.logger.debug(
      "Runtime statistics generated in %.3f ms (avg %.3f ms over %d samples)",
      duration * 1000,
      self._metrics.average_statistics_runtime_ms,
      len(self._metrics.statistics_timings),
    )
    return stats

  def get_performance_snapshot(self) -> CoordinatorPerformanceSnapshot:  # noqa: E111
    """Return a comprehensive performance snapshot for diagnostics surfaces."""

    adaptive = self._adaptive_polling.as_diagnostics()
    entity_budget = self._entity_budget.summary()
    update_interval = (
      self.update_interval.total_seconds() if self.update_interval else 0.0
    )
    last_update_time = getattr(self, "last_update_time", None)

    resilience = collect_resilience_diagnostics(self)

    base_snapshot = build_observability_snapshot(
      metrics=self._metrics,
      adaptive=adaptive,
      entity_budget=entity_budget,
      update_interval=update_interval,
      last_update_time=last_update_time,
      last_update_success=self.last_update_success,
      webhook_status=self._webhook_security_status(),
      resilience=resilience.get("summary") if resilience else None,
    )
    snapshot = cast(CoordinatorPerformanceSnapshot, dict(base_snapshot))

    if resilience:
      snapshot["resilience"] = resilience  # noqa: E111

    rejection_metrics = snapshot.get("rejection_metrics")
    if not isinstance(rejection_metrics, Mapping):
      rejection_metrics = default_rejection_metrics()  # noqa: E111
      snapshot["rejection_metrics"] = rejection_metrics  # noqa: E111

    runtime_data = getattr(self.config_entry, "runtime_data", None)
    performance_stats_payload = get_runtime_performance_stats(
      cast(PawControlRuntimeData | None, runtime_data),
    )
    guard_metrics = resolve_service_guard_metrics(
      performance_stats_payload,
    )
    entity_factory_guard = resolve_entity_factory_guard_metrics(
      performance_stats_payload,
    )
    snapshot["service_execution"] = {
      "guard_metrics": guard_metrics,
      "entity_factory_guard": entity_factory_guard,
      "rejection_metrics": rejection_metrics,
    }

    if self._last_cycle is not None:
      snapshot["last_cycle"] = self._last_cycle.to_dict()  # noqa: E111

    return snapshot

  def get_security_scorecard(self) -> CoordinatorSecurityScorecard:  # noqa: E111
    """Return aggregated pass/fail status for security critical checks."""

    adaptive = self._adaptive_polling.as_diagnostics()
    entity_summary = self._entity_budget.summary()
    webhook_status = self._webhook_security_status()
    return build_observability_scorecard(
      adaptive=cast(JSONMapping, adaptive),
      entity_summary=cast(JSONMapping, entity_summary),
      webhook_status=webhook_status,
    )

  @callback  # noqa: E111
  def async_start_background_tasks(self) -> None:  # noqa: E111
    """Start recurring background maintenance tasks."""
    ensure_background_task(self, MAINTENANCE_INTERVAL)

  async def _async_maintenance(self, *_: Any) -> None:  # noqa: E111
    await run_maintenance(self)

  async def async_shutdown(self) -> None:  # noqa: E111
    """Stop background tasks and release resources."""
    await shutdown_tasks(self)

  def _webhook_security_status(self) -> WebhookSecurityStatus:  # noqa: E111
    """Return normalised webhook security information."""

    manager = getattr(self, "notification_manager", None)
    return normalise_webhook_status(manager)
