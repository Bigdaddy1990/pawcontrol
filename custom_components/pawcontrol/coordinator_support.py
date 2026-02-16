"""Helper structures that keep :mod:`coordinator` lean and maintainable."""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import sys
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from .const import (
  ALL_MODULES,
  CONF_DOGS,
  CONF_GPS_SOURCE,
  CONF_GPS_UPDATE_INTERVAL,
  CONF_MODULES,
  CONF_WEBHOOK_ENABLED,
  DEFAULT_WEBHOOK_ENABLED,
  MAX_IDLE_POLL_INTERVAL,
  MAX_POLLING_INTERVAL_SECONDS,
  MODULE_FEEDING,
  MODULE_GARDEN,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_WALK,
  MODULE_WEATHER,
  UPDATE_INTERVALS,
)
from .exceptions import ValidationError
from .types import (
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  CacheRepairAggregate,
  CacheRepairIssue,
  CoordinatorDogData,
  CoordinatorModuleState,
  CoordinatorModuleTask,
  CoordinatorRepairsSummary,
  CoordinatorRuntimeManagers,
  CoordinatorRuntimeStatisticsPayload,
  CoordinatorStatisticsPayload,
  DogConfigData,
  DogModulesMapping,
  JSONValue,
  ModuleCacheMetrics,
  PawControlConfigEntry,
  coerce_dog_modules_config,
  ensure_dog_config_data,
)

_LOGGER = logging.getLogger(__name__)

_STATUS_DEFAULT_MODULES: frozenset[str] = frozenset(
  {
    MODULE_FEEDING,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    MODULE_WEATHER,
    "geofencing",
  },
)

if TYPE_CHECKING:
  from homeassistant.core import HomeAssistant  # noqa: E111

  from .data_manager import PawControlDataManager  # noqa: E111
  from .feeding_manager import FeedingManager  # noqa: E111
  from .garden_manager import GardenManager  # noqa: E111
  from .geofencing import PawControlGeofencing  # noqa: E111
  from .gps_manager import GPSGeofenceManager  # noqa: E111
  from .notifications import PawControlNotificationManager  # noqa: E111
  from .walk_manager import WalkManager  # noqa: E111
  from .weather_manager import WeatherHealthManager  # noqa: E111


class SupportsCoordinatorSnapshot(Protocol):
  """Protocol for caches that expose coordinator diagnostics snapshots."""  # noqa: E111

  def coordinator_snapshot(self) -> Mapping[str, object]:  # noqa: E111
    """Return a diagnostics snapshot consumable by coordinators."""


class SupportsCacheTelemetry(Protocol):
  """Protocol for caches exposing discrete stats/diagnostics callables."""  # noqa: E111

  def get_stats(self) -> Mapping[str, object]:  # noqa: E111
    """Return cache statistics used by diagnostics exporters."""

  def get_diagnostics(self) -> Mapping[str, object]:  # noqa: E111
    """Return cache diagnostics used by coordinator panels."""


CacheMonitorTarget = SupportsCoordinatorSnapshot | SupportsCacheTelemetry


def _build_repair_telemetry(
  summary: CacheRepairAggregate | None,
) -> CoordinatorRepairsSummary | None:
  """Return a condensed repairs payload derived from cache health metadata."""  # noqa: E111

  if not summary:  # noqa: E111
    return None

  def _count_strings(values: list[str] | None) -> int:  # noqa: E111
    if not values:
      return 0  # noqa: E111
    return sum(1 for value in values if isinstance(value, str) and value)

  def _count_issues(values: list[CacheRepairIssue] | None) -> int:  # noqa: E111
    if not values:
      return 0  # noqa: E111
    return sum(1 for issue in values if issue is not None)

  severity = summary.severity or "info"  # noqa: E111
  anomaly_count = int(summary.anomaly_count)  # noqa: E111
  total_caches = int(summary.total_caches)  # noqa: E111
  generated_at = summary.generated_at  # noqa: E111

  telemetry: CoordinatorRepairsSummary = {  # noqa: E111
    "severity": severity,
    "anomaly_count": anomaly_count,
    "total_caches": total_caches,
    "generated_at": generated_at,
    "issues": _count_issues(summary.issues),
  }

  errors_count = _count_strings(summary.caches_with_errors)  # noqa: E111
  if errors_count:  # noqa: E111
    telemetry["caches_with_errors"] = errors_count

  expired_count = _count_strings(summary.caches_with_expired_entries)  # noqa: E111
  if expired_count:  # noqa: E111
    telemetry["caches_with_expired_entries"] = expired_count

  pending_count = _count_strings(summary.caches_with_pending_expired_entries)  # noqa: E111
  if pending_count:  # noqa: E111
    telemetry["caches_with_pending_expired_entries"] = pending_count

  override_count = _count_strings(summary.caches_with_override_flags)  # noqa: E111
  if override_count:  # noqa: E111
    telemetry["caches_with_override_flags"] = override_count

  low_hit_rate_count = _count_strings(summary.caches_with_low_hit_rate)  # noqa: E111
  if low_hit_rate_count:  # noqa: E111
    telemetry["caches_with_low_hit_rate"] = low_hit_rate_count

  return telemetry  # noqa: E111


def ensure_cache_repair_aggregate(
  summary: Any,
) -> CacheRepairAggregate | None:
  """Return ``summary`` when it matches the active dataclass implementation."""  # noqa: E111

  if summary is None:  # noqa: E111
    return None

  types_module = sys.modules.get("custom_components.pawcontrol.types")  # noqa: E111
  aggregate_cls = getattr(  # noqa: E111
    types_module,
    "CacheRepairAggregate",
    CacheRepairAggregate,
  )

  candidate_classes: list[type[CacheRepairAggregate]] = []  # noqa: E111
  if isinstance(aggregate_cls, type):  # noqa: E111
    candidate_classes.append(aggregate_cls)
  candidate_classes.append(CacheRepairAggregate)  # noqa: E111

  for candidate in dict.fromkeys(candidate_classes):  # noqa: E111
    if isinstance(summary, candidate):
      return summary  # noqa: E111

  return None  # noqa: E111


@runtime_checkable
class CacheMonitorRegistrar(Protocol):
  """Objects that can register cache diagnostics providers."""  # noqa: E111

  def register_cache_monitor(self, name: str, cache: CacheMonitorTarget) -> None:  # noqa: E111
    """Expose ``cache`` under ``name`` for coordinator diagnostics."""


@runtime_checkable
class CoordinatorBindingTarget(Protocol):
  """Coordinator interface required for runtime manager binding."""  # noqa: E111

  hass: HomeAssistant  # noqa: E111
  config_entry: PawControlConfigEntry  # noqa: E111
  data_manager: PawControlDataManager | None  # noqa: E111
  feeding_manager: FeedingManager | None  # noqa: E111
  walk_manager: WalkManager | None  # noqa: E111
  notification_manager: PawControlNotificationManager | None  # noqa: E111
  gps_geofence_manager: GPSGeofenceManager | None  # noqa: E111
  geofencing_manager: PawControlGeofencing | None  # noqa: E111
  weather_health_manager: WeatherHealthManager | None  # noqa: E111
  garden_manager: GardenManager | None  # noqa: E111


@runtime_checkable
class CoordinatorModuleAdapter(Protocol):
  """Protocol describing the coordinator module adapter surface."""  # noqa: E111

  def attach_managers(  # noqa: E111
    self,
    *,
    data_manager: PawControlDataManager | None,
    feeding_manager: FeedingManager | None,
    walk_manager: WalkManager | None,
    gps_geofence_manager: GPSGeofenceManager | None,
    weather_health_manager: WeatherHealthManager | None,
    garden_manager: GardenManager | None,
  ) -> None:
    """Attach runtime managers used by module adapters."""

  def detach_managers(self) -> None:  # noqa: E111
    """Detach previously bound runtime managers."""

  def build_tasks(  # noqa: E111
    self,
    dog_id: str,
    modules: DogModulesMapping,
  ) -> list[CoordinatorModuleTask]:
    """Return coroutine tasks for each enabled module."""

  def cleanup_expired(self, now: datetime) -> int:  # noqa: E111
    """Expire cached module payloads and return the eviction count."""

  def clear_caches(self) -> None:  # noqa: E111
    """Clear all module caches, typically during manual refreshes."""

  def cache_metrics(self) -> ModuleCacheMetrics:  # noqa: E111
    """Return aggregate cache metrics across all module adapters."""


@dataclass(slots=True)
class DogConfigRegistry:
  """Normalised view onto the configured dogs."""  # noqa: E111

  configs: list[DogConfigData]  # noqa: E111
  _by_id: dict[str, DogConfigData] = field(init=False, default_factory=dict)  # noqa: E111
  _ids: list[str] = field(init=False, default_factory=list)  # noqa: E111

  def __post_init__(self) -> None:  # noqa: E111
    """Normalise the provided dog configuration list."""
    cleaned: list[DogConfigData] = []
    for raw_config in self.configs:
      if not isinstance(raw_config, Mapping):  # noqa: E111
        continue

      candidate = ensure_dog_config_data(  # noqa: E111
        cast(Mapping[str, JSONValue], raw_config),
      )
      if candidate is None:  # noqa: E111
        continue

      dog_id = candidate[DOG_ID_FIELD]  # noqa: E111
      normalized = dog_id.strip()  # noqa: E111
      if not normalized or normalized in self._by_id:  # noqa: E111
        continue

      config = cast(DogConfigData, dict(candidate))  # noqa: E111
      config[DOG_ID_FIELD] = normalized  # noqa: E111
      dog_name = config.get(DOG_NAME_FIELD, "")  # noqa: E111
      if isinstance(dog_name, str):  # noqa: E111
        stripped_name = dog_name.strip()
        if not stripped_name:
          continue  # noqa: E111
        config[DOG_NAME_FIELD] = stripped_name

      self._by_id[normalized] = config  # noqa: E111
      self._ids.append(normalized)  # noqa: E111
      cleaned.append(config)  # noqa: E111

    self.configs = cleaned

  @classmethod  # noqa: E111
  def from_entry(cls, entry: PawControlConfigEntry) -> DogConfigRegistry:  # noqa: E111
    """Build registry from a config entry."""

    raw_dogs = entry.data.get(CONF_DOGS, [])
    if raw_dogs in (None, ""):
      raw_dogs = []  # noqa: E111
    if not isinstance(raw_dogs, list):
      raise ValidationError(  # noqa: E111
        "dogs_config",
        type(raw_dogs).__name__,
        "Must be a list of dog configurations",
      )
    return cls(list(raw_dogs))

  def __len__(self) -> int:  # pragma: no cover - trivial  # noqa: E111
    """Return the number of configured dogs."""
    return len(self._ids)

  def ids(self) -> list[str]:  # noqa: E111
    """Return all configured dog identifiers."""
    return list(self._ids)

  def get(self, dog_id: str | None) -> DogConfigData | None:  # noqa: E111
    """Return the raw configuration for the requested dog."""
    if not isinstance(dog_id, str):
      return None  # noqa: E111
    return self._by_id.get(dog_id.strip())

  def get_name(self, dog_id: str) -> str | None:  # noqa: E111
    """Return the configured name for the dog if available."""
    config = self.get(dog_id)
    if not config:
      return None  # noqa: E111
    dog_name = config.get(DOG_NAME_FIELD)
    if isinstance(dog_name, str) and dog_name.strip():
      return dog_name  # noqa: E111
    return None

  def enabled_modules(self, dog_id: str) -> frozenset[str]:  # noqa: E111
    """Return the enabled modules for the specified dog."""
    config = self.get(dog_id)
    if not config:
      return frozenset()  # noqa: E111
    modules_payload = cast(
      Mapping[str, object] | None,
      config.get(CONF_MODULES),
    )
    modules = coerce_dog_modules_config(modules_payload)
    return frozenset(module for module, enabled in modules.items() if bool(enabled))

  def has_module(self, module: str) -> bool:  # noqa: E111
    """Return True if any dog has the requested module enabled."""
    return any(module in self.enabled_modules(dog_id) for dog_id in self._ids)

  def module_count(self) -> int:  # noqa: E111
    """Return the total number of enabled modules across all dogs."""
    total = 0
    for dog_id in self._ids:
      total += len(self.enabled_modules(dog_id))  # noqa: E111
    return total

  def empty_payload(self) -> CoordinatorDogData:  # noqa: E111
    """Return an empty coordinator payload for a dog."""

    payload: dict[str, object] = {
      "dog_info": cast(
        DogConfigData,
        {
          DOG_ID_FIELD: "",
          DOG_NAME_FIELD: "",
        },
      ),
      "status": "unknown",
      "last_update": None,
    }

    for module in sorted(ALL_MODULES):
      if module in _STATUS_DEFAULT_MODULES:  # noqa: E111
        payload[module] = cast(
          CoordinatorModuleState,
          {
            "status": "unknown",
          },
        )
      else:  # noqa: E111
        payload[module] = cast(CoordinatorModuleState, {})

    return cast(CoordinatorDogData, payload)

  def calculate_update_interval(self, options: Mapping[str, object]) -> int:  # noqa: E111
    """Derive the polling interval from configuration options."""
    provided_interval = options.get(CONF_GPS_UPDATE_INTERVAL)
    validated_interval: int | None = None

    if provided_interval not in (None, ""):
      validated_interval = self._validate_gps_interval(provided_interval)  # noqa: E111

    if not self._ids:
      return self._enforce_polling_limits(UPDATE_INTERVALS.get("minimal", 300))  # noqa: E111

    if self.has_module(MODULE_GPS):
      gps_source = options.get(CONF_GPS_SOURCE)  # noqa: E111
      webhook_enabled = bool(options.get(CONF_WEBHOOK_ENABLED, DEFAULT_WEBHOOK_ENABLED))  # noqa: E111

      # When GPS is driven by webhook push, keep periodic polling low and rely on push events.  # noqa: E114, E501
      if gps_source == "webhook" and webhook_enabled:  # noqa: E111
        baseline = UPDATE_INTERVALS.get("minimal", 300)
        if validated_interval is not None:
          baseline = max(baseline, int(validated_interval))  # noqa: E111
        return self._enforce_polling_limits(baseline)

      gps_interval = (  # noqa: E111
        validated_interval
        if validated_interval is not None
        else UPDATE_INTERVALS.get("frequent", 60)
      )
      return self._enforce_polling_limits(gps_interval)  # noqa: E111

    interval: int
    if self.has_module(MODULE_WEATHER):
      interval = UPDATE_INTERVALS.get("frequent", 60)  # noqa: E111
    else:
      total_modules = self.module_count()  # noqa: E111
      if total_modules > 15:  # noqa: E111
        interval = UPDATE_INTERVALS.get("real_time", 30)
      elif total_modules > 8:  # noqa: E111
        interval = UPDATE_INTERVALS.get("balanced", 120)
      else:  # noqa: E111
        interval = UPDATE_INTERVALS.get("minimal", 300)

    return self._enforce_polling_limits(interval)

  @staticmethod  # noqa: E111
  def _enforce_polling_limits(interval: int | None) -> int:  # noqa: E111
    """Clamp polling intervals to Platinum quality requirements."""

    if not isinstance(interval, int):
      raise ValidationError(  # noqa: E111
        "update_interval",
        interval,
        "Polling interval must be an integer",
      )

    if interval <= 0:
      raise ValidationError(  # noqa: E111
        "update_interval",
        interval,
        "Polling interval must be positive",
      )

    return min(interval, MAX_IDLE_POLL_INTERVAL, MAX_POLLING_INTERVAL_SECONDS)

  @staticmethod  # noqa: E111
  def _validate_gps_interval(value: Any) -> int:  # noqa: E111
    """Validate the GPS interval option and return a positive integer."""

    if isinstance(value, bool):
      raise ValidationError(  # noqa: E111
        "gps_update_interval",
        value,
        "Invalid GPS update interval",
      )

    if isinstance(value, str):
      candidate = value.strip()  # noqa: E111
      if not candidate:  # noqa: E111
        raise ValidationError(
          "gps_update_interval",
          value,
          "Invalid GPS update interval",
        )
      try:  # noqa: E111
        value = int(candidate)
      except ValueError as err:  # pragma: no cover - defensive casting  # noqa: E111
        raise ValidationError(
          "gps_update_interval",
          value,
          "Invalid GPS update interval",
        ) from err

    if not isinstance(value, int):
      raise ValidationError(  # noqa: E111
        "gps_update_interval",
        value,
        "Invalid GPS update interval",
      )

    if value <= 0:
      raise ValidationError(  # noqa: E111
        "gps_update_interval",
        value,
        "Invalid GPS update interval",
      )

    return value


@dataclass(slots=True)
class CoordinatorMetrics:
  """Tracks coordinator level metrics for diagnostics."""  # noqa: E111

  update_count: int = 0  # noqa: E111
  failed_cycles: int = 0  # noqa: E111
  consecutive_errors: int = 0  # noqa: E111
  statistics_timings: deque[float] = field(  # noqa: E111
    default_factory=lambda: deque(maxlen=50),
  )
  visitor_mode_timings: deque[float] = field(  # noqa: E111
    default_factory=lambda: deque(maxlen=50),
  )

  def start_cycle(self) -> None:  # noqa: E111
    """Record the start of a coordinator update cycle."""
    self.update_count += 1

  def record_cycle(self, total: int, errors: int) -> tuple[float, bool]:  # noqa: E111
    """Record a completed cycle and return its success rate and failure flag."""
    if total == 0:
      return 1.0, False  # noqa: E111

    success_rate = (total - errors) / total
    if errors == total:
      self.failed_cycles += 1  # noqa: E111
      self.consecutive_errors += 1  # noqa: E111
      return success_rate, True  # noqa: E111

    if success_rate < 0.5:
      self.consecutive_errors += 1  # noqa: E111
    else:
      self.consecutive_errors = 0  # noqa: E111
    return success_rate, False

  def reset_consecutive(self) -> None:  # noqa: E111
    """Reset the counter that tracks consecutive error cycles."""
    self.consecutive_errors = 0

  @property  # noqa: E111
  def successful_cycles(self) -> int:  # noqa: E111
    """Return how many cycles finished without total failure."""
    return max(self.update_count - self.failed_cycles, 0)

  @property  # noqa: E111
  def success_rate_percent(self) -> float:  # noqa: E111
    """Return the success rate as a percentage."""
    if self.update_count == 0:
      return 100.0  # noqa: E111
    return (self.successful_cycles / self.update_count) * 100

  def record_statistics_timing(self, duration: float) -> None:  # noqa: E111
    """Track how long runtime statistics generation took in seconds."""

    self.statistics_timings.append(max(duration, 0.0))

  def record_visitor_timing(self, duration: float) -> None:  # noqa: E111
    """Track how long visitor-mode persistence took in seconds."""

    self.visitor_mode_timings.append(max(duration, 0.0))

  @property  # noqa: E111
  def average_statistics_runtime_ms(self) -> float:  # noqa: E111
    """Return the rolling average runtime for statistics generation."""

    if not self.statistics_timings:
      return 0.0  # noqa: E111
    return (sum(self.statistics_timings) / len(self.statistics_timings)) * 1000

  @property  # noqa: E111
  def average_visitor_runtime_ms(self) -> float:  # noqa: E111
    """Return the rolling average runtime for visitor mode persistence."""

    if not self.visitor_mode_timings:
      return 0.0  # noqa: E111
    return (sum(self.visitor_mode_timings) / len(self.visitor_mode_timings)) * 1000

  def update_statistics(  # noqa: E111
    self,
    *,
    cache_entries: int,
    cache_hit_rate: float,
    last_update: Any,
    interval: timedelta | None,
    repair_summary: CacheRepairAggregate | None = None,
  ) -> CoordinatorStatisticsPayload:
    """Return a statistics snapshot for diagnostics panels."""
    update_interval = (interval or timedelta()).total_seconds()
    payload: CoordinatorStatisticsPayload = {
      "update_counts": {
        "total": self.update_count,
        "successful": self.successful_cycles,
        "failed": self.failed_cycles,
      },
      "performance_metrics": {
        "success_rate": round(self.success_rate_percent, 2),
        "cache_entries": cache_entries,
        "cache_hit_rate": round(cache_hit_rate, 2),
        "consecutive_errors": self.consecutive_errors,
        "last_update": last_update,
        "update_interval": update_interval,
        "api_calls": 0,
      },
      "health_indicators": {
        "consecutive_errors": self.consecutive_errors,
        "stability_window_ok": self.consecutive_errors < 5,
      },
    }

    telemetry = _build_repair_telemetry(repair_summary)
    if telemetry:
      payload["repairs"] = telemetry  # noqa: E111

    return payload

  def runtime_statistics(  # noqa: E111
    self,
    *,
    cache_metrics: ModuleCacheMetrics,
    total_dogs: int,
    last_update: Any,
    interval: timedelta | None,
    repair_summary: CacheRepairAggregate | None = None,
  ) -> CoordinatorRuntimeStatisticsPayload:
    """Return runtime statistics derived from cached metrics."""
    update_interval = (interval or timedelta()).total_seconds()
    cache_hit_rate = max(min(cache_metrics.hit_rate, 100.0), 0.0)
    payload: CoordinatorRuntimeStatisticsPayload = {
      "update_counts": {
        "total": self.update_count,
        "successful": self.successful_cycles,
        "failed": self.failed_cycles,
      },
      "context": {
        "total_dogs": total_dogs,
        "last_update": last_update,
        "update_interval": update_interval,
      },
      "error_summary": {
        "consecutive_errors": self.consecutive_errors,
        "error_rate": (
          self.failed_cycles / self.update_count if self.update_count else 0.0
        ),
      },
      "cache_performance": {
        "hits": cache_metrics.hits,
        "misses": cache_metrics.misses,
        "entries": cache_metrics.entries,
        "hit_rate": cache_hit_rate,
      },
    }

    telemetry = _build_repair_telemetry(repair_summary)
    if telemetry:
      payload["repairs"] = telemetry  # noqa: E111

    return payload


MANAGER_ATTRIBUTES: tuple[str, ...] = CoordinatorRuntimeManagers.attribute_names()


def bind_runtime_managers(
  coordinator: CoordinatorBindingTarget,
  modules: CoordinatorModuleAdapter,
  managers: CoordinatorRuntimeManagers,
) -> None:
  """Bind runtime managers to the coordinator and adapters."""  # noqa: E111

  coordinator.data_manager = managers.data_manager  # noqa: E111
  coordinator.feeding_manager = managers.feeding_manager  # noqa: E111
  coordinator.garden_manager = managers.garden_manager  # noqa: E111
  coordinator.geofencing_manager = managers.geofencing_manager  # noqa: E111
  coordinator.gps_geofence_manager = managers.gps_geofence_manager  # noqa: E111
  coordinator.notification_manager = managers.notification_manager  # noqa: E111
  coordinator.walk_manager = managers.walk_manager  # noqa: E111
  coordinator.weather_health_manager = managers.weather_health_manager  # noqa: E111

  data_manager = managers.data_manager  # noqa: E111
  gps_manager = managers.gps_geofence_manager  # noqa: E111
  notification_manager = managers.notification_manager  # noqa: E111
  if (  # noqa: E111
    gps_manager
    and notification_manager
    and hasattr(gps_manager, "set_notification_manager")
  ):
    gps_manager.set_notification_manager(notification_manager)

  modules.attach_managers(  # noqa: E111
    data_manager=managers.data_manager,
    feeding_manager=managers.feeding_manager,
    walk_manager=managers.walk_manager,
    gps_geofence_manager=managers.gps_geofence_manager,
    weather_health_manager=managers.weather_health_manager,
    garden_manager=managers.garden_manager,
  )

  if (  # noqa: E111
    data_manager is not None
    and notification_manager is not None
    and isinstance(data_manager, CacheMonitorRegistrar)
  ):
    register_method = getattr(
      notification_manager,
      "register_cache_monitors",
      None,
    )
    if callable(register_method):
      register_method(data_manager)  # noqa: E111


def clear_runtime_managers(
  coordinator: CoordinatorBindingTarget,
  modules: CoordinatorModuleAdapter,
) -> None:
  """Clear bound runtime managers from the coordinator."""  # noqa: E111

  for attr in MANAGER_ATTRIBUTES:  # noqa: E111
    setattr(coordinator, attr, None)
  modules.detach_managers()  # noqa: E111
