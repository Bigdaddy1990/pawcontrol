"""Coordinator for the PawControl integration."""

from __future__ import annotations

import logging
import asyncio
from collections.abc import Iterable, Mapping, Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
  CONF_API_ENDPOINT,
  CONF_API_TOKEN,
  CONF_EXTERNAL_INTEGRATIONS,
  CONF_MODULES,
  MODULE_GARDEN,
  MODULE_WALK,
  UPDATE_INTERVALS,
)
from .coordinator_accessors import CoordinatorDataAccessMixin
from .coordinator_observability import (
  build_performance_snapshot,
  build_security_scorecard,
  normalise_webhook_status,
)
from .coordinator_runtime import EntityBudgetSnapshot, RuntimeCycleInfo
from .coordinator_support import (
  DogConfigRegistry,
  bind_runtime_managers,
  clear_runtime_managers as unbind_runtime_managers,
)
from .device_api import PawControlDeviceClient
from .exceptions import ValidationError
from .http_client import ensure_shared_client_session
from .module_adapters import CoordinatorModuleAdapters
from .resilience import ResilienceManager
from .types import (
  CoordinatorDataPayload,
  CoordinatorDogData,
  CoordinatorModuleState,
  CoordinatorRuntimeManagers,
  CoordinatorRuntimeStatisticsPayload,
  CoordinatorSecurityScorecard,
  CoordinatorStatisticsPayload,
  ConfigEntryOptionsPayload,
  DogConfigData,
  PawControlConfigEntry,
)

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
GARDEN_MODULE_FIELD: Final[Literal["garden"]] = cast(Literal["garden"], MODULE_GARDEN)
DEFAULT_UPDATE_INTERVAL = 120

__all__ = ["EntityBudgetSnapshot", "PawControlCoordinator", "RuntimeCycleInfo"]


class PawControlCoordinator(
  CoordinatorDataAccessMixin,
  DataUpdateCoordinator[CoordinatorDataPayload],
):
  """Central data coordinator with fixed-interval polling."""

  def __init__(
    self,
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    session: ClientSession,
  ) -> None:
    """Initialise the coordinator."""
    self.config_entry = entry
    self._options = cast(ConfigEntryOptionsPayload, entry.options)
    self.session = ensure_shared_client_session(session, owner="PawControlCoordinator")
    self.registry = DogConfigRegistry.from_entry(entry)
    self._use_external_api = bool(self._options.get(CONF_EXTERNAL_INTEGRATIONS, False))

    self.resilience_manager = ResilienceManager(hass)

    endpoint = self._options.get(CONF_API_ENDPOINT)
    token = self._options.get(CONF_API_TOKEN)
    self._api_client: PawControlDeviceClient | None = None
    if isinstance(endpoint, str) and endpoint.strip():
      self._api_client = PawControlDeviceClient(
        session=self.session,
        endpoint=endpoint.strip(),
        api_key=token.strip() if isinstance(token, str) and token.strip() else None,
        resilience_manager=self.resilience_manager,
      )

    update_interval_seconds = self._get_update_interval(entry)

    super().__init__(
      hass,
      logger=_LOGGER,
      name="PawControl Data",
      update_interval=timedelta(seconds=update_interval_seconds),
      config_entry=entry,
    )

    self._modules = CoordinatorModuleAdapters(
      session=self.session,
      config_entry=entry,
      use_external_api=self._use_external_api,
      cache_ttl=timedelta(seconds=update_interval_seconds),
      api_client=self._api_client,
    )

    self._runtime_managers = CoordinatorRuntimeManagers()
    self._setup_complete = False

    self.data_manager: PawControlDataManager | None = None
    self.feeding_manager: FeedingManager | None = None
    self.walk_manager: WalkManager | None = None
    self.notification_manager: PawControlNotificationManager | None = None
    self.gps_geofence_manager: GPSGeofenceManager | None = None
    self.geofencing_manager: PawControlGeofencing | None = None
    self.weather_health_manager: WeatherHealthManager | None = None
    self.garden_manager: GardenManager | None = None

  def _get_update_interval(self, entry: PawControlConfigEntry) -> int:
    """Return polling interval in seconds."""
    try:
      return self.registry.calculate_update_interval(entry.options)
    except ValidationError as err:
      _LOGGER.warning(
        "Invalid update interval options; using balanced default: %s",
        err,
      )
      return UPDATE_INTERVALS.get("balanced", DEFAULT_UPDATE_INTERVAL)

  async def async_prepare_entry(self) -> None:
    """Prepare coordinator state."""
    if self._setup_complete:
      return
    self._modules.clear_caches()
    self._setup_complete = True

  async def _async_setup(self) -> None:
    """Compatibility shim for older setup path."""
    await self.async_prepare_entry()

  async def _async_update_data(self) -> CoordinatorDataPayload:
    """Fetch data from API or modules."""
    if len(self.registry) == 0:
      return {}

    await self.async_prepare_entry()

    try:
      data: CoordinatorDataPayload = {}
      for dog_id in self.registry.ids():
        data[dog_id] = await self._fetch_dog_data(dog_id)

      await self._synchronize_module_states(data)
      return data

    except Exception as err:
      _LOGGER.error("Error updating PawControl data: %s", err)
      raise UpdateFailed(f"Update failed: {err}") from err

  async def _fetch_dog_data(self, dog_id: str) -> CoordinatorDogData:
    """Fetch all module data for a dog."""
    payload = self.registry.empty_payload()

    dog_config = self.registry.get(dog_id)
    dog_name = self.registry.get_name(dog_id) or dog_id
    payload["dog_info"] = cast(
      dict[str, Any],
      {
        "dog_id": dog_id,
        "dog_name": dog_name,
        **(dog_config or {}),
      },
    )

    if not dog_config:
      payload["status"] = "missing"
      return payload

    enabled_modules = self._modules.build_tasks(
      dog_id,
      cast(Mapping[str, bool], dog_config.get(CONF_MODULES, {})),
    )
    payload["status"] = "online"

    if enabled_modules:
      results = await asyncio.gather(
        *(task.coroutine for task in enabled_modules),
        return_exceptions=True,
      )

      for task, result in zip(enabled_modules, results, strict=True):
        if isinstance(result, Exception):
          _LOGGER.warning(
            "Failed loading %s data for dog %s: %s",
            task.module,
            dog_id,
            result,
          )
          payload[task.module] = cast(
            CoordinatorModuleState,
            {
              "status": "error",
              "error": str(result),
            },
          )
          continue

        payload[task.module] = cast(CoordinatorModuleState, result)

    return payload

  async def _fetch_dog_data_protected(self, dog_id: str) -> CoordinatorDogData:
    """Compatibility alias for older call sites."""
    return await self._fetch_dog_data(dog_id)

  async def async_refresh_dog(self, dog_id: str) -> None:
    """Refresh data for a specific dog."""
    if dog_id not in self.registry.ids():
      return
    await self.async_request_selective_refresh([dog_id])

  async def async_request_selective_refresh(
    self,
    dog_ids: Iterable[str] | None = None,
  ) -> None:
    """Refresh selected dogs (simplified to full refresh)."""
    if dog_ids is None:
      await self.async_request_refresh()
      return

    unique_ids = [dog_id for dog_id in dict.fromkeys(dog_ids) if dog_id]
    if not unique_ids:
      return

    await self.async_request_refresh()

  async def _refresh_subset(self, dog_ids: Sequence[str]) -> None:
    """Compatibility shim for old selective refresh path."""
    if not dog_ids:
      return
    await self.async_request_refresh()

  async def _execute_cycle(
    self,
    dog_ids: Sequence[str],
  ) -> tuple[CoordinatorDataPayload, RuntimeCycleInfo]:
    """Compatibility wrapper around fixed-interval fetch cycle."""
    data: CoordinatorDataPayload = {}
    for dog_id in dog_ids:
      data[dog_id] = await self._fetch_dog_data(dog_id)

    now = self.hass.loop.time()
    cycle = RuntimeCycleInfo(
      duration_seconds=0.0,
      interval_before=float(self.update_interval.total_seconds()),
      interval_after=float(self.update_interval.total_seconds()),
      errors=0,
      successful_dogs=len(dog_ids),
      failed_dogs=0,
      started_at=now,
      finished_at=now,
    )
    return data, cycle

  async def _synchronize_module_states(self, data: CoordinatorDataPayload) -> None:
    """Handle interactions between modules."""
    if not self.garden_manager:
      return

    for dog_id, dog_payload in data.items():
      if not isinstance(dog_payload, Mapping):
        continue

      walk_data = dog_payload.get(MODULE_WALK, {})
      if (
        isinstance(walk_data, Mapping)
        and walk_data.get("walk_in_progress")
        and self.garden_manager.get_active_session(dog_id)
      ):
        await self.garden_manager.async_end_garden_session(
          dog_id,
          notes="Paused due to active walk",
          suppress_notifications=True,
        )
        dog_payload[GARDEN_MODULE_FIELD] = cast(
          CoordinatorModuleState,
          self.garden_manager.build_garden_snapshot(dog_id),
        )

  def report_entity_budget(self, *_args: Any) -> None:
    """Compatibility no-op."""

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
    """Attach managers to coordinator and module adapters."""
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

  def clear_runtime_managers(self) -> None:
    """Detach managers."""
    unbind_runtime_managers(self, self._modules)
    self._runtime_managers = CoordinatorRuntimeManagers()

  @property
  def runtime_managers(self) -> CoordinatorRuntimeManagers:
    """Return currently attached runtime manager container."""
    return self._runtime_managers

  @runtime_managers.setter
  def runtime_managers(self, managers: CoordinatorRuntimeManagers) -> None:
    """Replace runtime manager container."""
    self._runtime_managers = managers

  def get_dog_config(self, dog_id: str) -> DogConfigData | None:
    """Return raw dog configuration."""
    return CoordinatorDataAccessMixin.get_dog_config(self, dog_id)

  def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
    """Return enabled modules for dog."""
    return self.registry.enabled_modules(dog_id)

  def is_module_enabled(self, dog_id: str, module: str) -> bool:
    """Return True when module is enabled for dog."""
    return module in self.registry.enabled_modules(dog_id)

  def get_dog_ids(self) -> list[str]:
    """Return configured dog IDs."""
    return CoordinatorDataAccessMixin.get_dog_ids(self)

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
    """Return current dog payload."""
    return CoordinatorDataAccessMixin.get_dog_data(self, dog_id)

  async def async_patch_gps_update(self, dog_id: str) -> None:
    """Trigger a refresh for GPS updates."""
    if dog_id not in self.registry.ids():
      return
    await self.async_request_refresh()

  @property
  def available(self) -> bool:
    """Return coordinator health."""
    return self.last_update_success

  def get_update_statistics(self) -> CoordinatorStatisticsPayload:
    """Return lightweight coordinator update statistics."""
    return cast(
      CoordinatorStatisticsPayload,
      {
        "update_count": 0,
        "successful_cycles": 0,
        "failed_cycles": 0,
        "success_rate_percent": 0.0,
        "consecutive_errors": 0,
        "average_cycle_duration_ms": 0.0,
      },
    )

  def get_statistics(self) -> CoordinatorRuntimeStatisticsPayload:
    """Return lightweight runtime statistics."""
    return cast(
      CoordinatorRuntimeStatisticsPayload,
      {
        "coordinator": self.get_update_statistics(),
        "modules": {},
        "cache": {},
      },
    )

  def get_performance_snapshot(self) -> dict[str, Any]:
    """Return simplified diagnostics performance snapshot."""
    return build_performance_snapshot()

  def get_security_scorecard(self) -> CoordinatorSecurityScorecard:
    """Return simplified security scorecard."""
    return cast(CoordinatorSecurityScorecard, build_security_scorecard())

  @callback
  def async_start_background_tasks(self) -> None:
    """No-op background task hook kept for compatibility."""

  async def _async_maintenance(self, *_: Any) -> None:
    """Compatibility no-op maintenance hook."""

  async def async_shutdown(self) -> None:
    """Shutdown hook for compatibility."""
    self.clear_runtime_managers()

  def _webhook_security_status(self) -> dict[str, Any]:
    """Return normalised webhook security information."""
    return normalise_webhook_status(self.notification_manager)
