"""Helper structures that keep :mod:`coordinator` lean and maintainable."""
from __future__ import annotations

import logging
import sys
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import cast
from typing import Protocol
from typing import runtime_checkable
from typing import TYPE_CHECKING

from .const import ALL_MODULES
from .const import CONF_DOGS
from .const import CONF_GPS_UPDATE_INTERVAL
from .const import CONF_MODULES
from .const import MAX_IDLE_POLL_INTERVAL
from .const import MAX_POLLING_INTERVAL_SECONDS
from .const import MODULE_FEEDING
from .const import MODULE_GARDEN
from .const import MODULE_GPS
from .const import MODULE_HEALTH
from .const import MODULE_WALK
from .const import MODULE_WEATHER
from .const import UPDATE_INTERVALS
from .exceptions import ValidationError
from .types import CacheRepairAggregate
from .types import CacheRepairIssue
from .types import coerce_dog_modules_config
from .types import CoordinatorDogData
from .types import CoordinatorModuleState
from .types import CoordinatorModuleTask
from .types import CoordinatorRepairsSummary
from .types import CoordinatorRuntimeManagers
from .types import CoordinatorRuntimeStatisticsPayload
from .types import CoordinatorStatisticsPayload
from .types import DOG_ID_FIELD
from .types import DOG_NAME_FIELD
from .types import DogConfigData
from .types import DogModulesMapping
from .types import ensure_dog_config_data
from .types import JSONValue
from .types import ModuleCacheMetrics
from .types import PawControlConfigEntry

_LOGGER = logging.getLogger(__name__)

_STATUS_DEFAULT_MODULES: frozenset[str] = frozenset(
    {
        MODULE_FEEDING,
        MODULE_GARDEN,
        MODULE_GPS,
        MODULE_HEALTH,
        MODULE_WALK,
        MODULE_WEATHER,
        'geofencing',
    },
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data_manager import PawControlDataManager
    from .feeding_manager import FeedingManager
    from .garden_manager import GardenManager
    from .geofencing import PawControlGeofencing
    from .gps_manager import GPSGeofenceManager
    from .notifications import PawControlNotificationManager
    from .walk_manager import WalkManager
    from .weather_manager import WeatherHealthManager


class SupportsCoordinatorSnapshot(Protocol):
    """Protocol for caches that expose coordinator diagnostics snapshots."""

    def coordinator_snapshot(self) -> Mapping[str, object]:
        """Return a diagnostics snapshot consumable by coordinators."""


class SupportsCacheTelemetry(Protocol):
    """Protocol for caches exposing discrete stats/diagnostics callables."""

    def get_stats(self) -> Mapping[str, object]:
        """Return cache statistics used by diagnostics exporters."""

    def get_diagnostics(self) -> Mapping[str, object]:
        """Return cache diagnostics used by coordinator panels."""


CacheMonitorTarget = SupportsCoordinatorSnapshot | SupportsCacheTelemetry


def _build_repair_telemetry(
    summary: CacheRepairAggregate | None,
) -> CoordinatorRepairsSummary | None:
    """Return a condensed repairs payload derived from cache health metadata."""

    if not summary:
        return None

    def _count_strings(values: list[str] | None) -> int:
        if not values:
            return 0
        return sum(1 for value in values if isinstance(value, str) and value)

    def _count_issues(values: list[CacheRepairIssue] | None) -> int:
        if not values:
            return 0
        return sum(1 for issue in values if issue is not None)

    severity = summary.severity or 'info'
    anomaly_count = int(summary.anomaly_count)
    total_caches = int(summary.total_caches)
    generated_at = summary.generated_at

    telemetry: CoordinatorRepairsSummary = {
        'severity': severity,
        'anomaly_count': anomaly_count,
        'total_caches': total_caches,
        'generated_at': generated_at,
        'issues': _count_issues(summary.issues),
    }

    errors_count = _count_strings(summary.caches_with_errors)
    if errors_count:
        telemetry['caches_with_errors'] = errors_count

    expired_count = _count_strings(summary.caches_with_expired_entries)
    if expired_count:
        telemetry['caches_with_expired_entries'] = expired_count

    pending_count = _count_strings(summary.caches_with_pending_expired_entries)
    if pending_count:
        telemetry['caches_with_pending_expired_entries'] = pending_count

    override_count = _count_strings(summary.caches_with_override_flags)
    if override_count:
        telemetry['caches_with_override_flags'] = override_count

    low_hit_rate_count = _count_strings(summary.caches_with_low_hit_rate)
    if low_hit_rate_count:
        telemetry['caches_with_low_hit_rate'] = low_hit_rate_count

    return telemetry


def ensure_cache_repair_aggregate(
    summary: Any,
) -> CacheRepairAggregate | None:
    """Return ``summary`` when it matches the active dataclass implementation."""

    if summary is None:
        return None

    types_module = sys.modules.get('custom_components.pawcontrol.types')
    aggregate_cls = getattr(
        types_module,
        'CacheRepairAggregate',
        CacheRepairAggregate,
    )

    candidate_classes: list[type[CacheRepairAggregate]] = []
    if isinstance(aggregate_cls, type):
        candidate_classes.append(aggregate_cls)
    candidate_classes.append(CacheRepairAggregate)

    for candidate in dict.fromkeys(candidate_classes):
        if isinstance(summary, candidate):
            return cast(CacheRepairAggregate, summary)

    return None


@runtime_checkable
class CacheMonitorRegistrar(Protocol):
    """Objects that can register cache diagnostics providers."""

    def register_cache_monitor(self, name: str, cache: CacheMonitorTarget) -> None:
        """Expose ``cache`` under ``name`` for coordinator diagnostics."""


@runtime_checkable
class CoordinatorBindingTarget(Protocol):
    """Coordinator interface required for runtime manager binding."""

    hass: HomeAssistant
    config_entry: PawControlConfigEntry
    data_manager: PawControlDataManager | None
    feeding_manager: FeedingManager | None
    walk_manager: WalkManager | None
    notification_manager: PawControlNotificationManager | None
    gps_geofence_manager: GPSGeofenceManager | None
    geofencing_manager: PawControlGeofencing | None
    weather_health_manager: WeatherHealthManager | None
    garden_manager: GardenManager | None


@runtime_checkable
class CoordinatorModuleAdapter(Protocol):
    """Protocol describing the coordinator module adapter surface."""

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
        """Attach runtime managers used by module adapters."""

    def detach_managers(self) -> None:
        """Detach previously bound runtime managers."""

    def build_tasks(
        self,
        dog_id: str,
        modules: DogModulesMapping,
    ) -> list[CoordinatorModuleTask]:
        """Return coroutine tasks for each enabled module."""

    def cleanup_expired(self, now: datetime) -> int:
        """Expire cached module payloads and return the eviction count."""

    def clear_caches(self) -> None:
        """Clear all module caches, typically during manual refreshes."""

    def cache_metrics(self) -> ModuleCacheMetrics:
        """Return aggregate cache metrics across all module adapters."""


@dataclass(slots=True)
class DogConfigRegistry:
    """Normalised view onto the configured dogs."""

    configs: list[DogConfigData]
    _by_id: dict[str, DogConfigData] = field(init=False, default_factory=dict)
    _ids: list[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        """Normalise the provided dog configuration list."""
        cleaned: list[DogConfigData] = []
        for raw_config in self.configs:
            if not isinstance(raw_config, Mapping):
                continue

            candidate = ensure_dog_config_data(
                cast(Mapping[str, JSONValue], raw_config),
            )
            if candidate is None:
                continue

            dog_id = candidate[DOG_ID_FIELD]
            normalized = dog_id.strip()
            if not normalized or normalized in self._by_id:
                continue

            config = cast(DogConfigData, dict(candidate))
            config[DOG_ID_FIELD] = normalized
            dog_name = config.get(DOG_NAME_FIELD, '')
            if isinstance(dog_name, str):
                stripped_name = dog_name.strip()
                if not stripped_name:
                    continue
                config[DOG_NAME_FIELD] = stripped_name

            self._by_id[normalized] = config
            self._ids.append(normalized)
            cleaned.append(config)

        self.configs = cleaned

    @classmethod
    def from_entry(cls, entry: PawControlConfigEntry) -> DogConfigRegistry:
        """Build registry from a config entry."""

        raw_dogs = entry.data.get(CONF_DOGS, [])
        if raw_dogs in (None, ''):
            raw_dogs = []
        if not isinstance(raw_dogs, list):
            raise ValidationError(
                'dogs_config',
                type(raw_dogs).__name__,
                'Must be a list of dog configurations',
            )
        return cls(list(raw_dogs))

    def __len__(self) -> int:  # pragma: no cover - trivial
        """Return the number of configured dogs."""
        return len(self._ids)

    def ids(self) -> list[str]:
        """Return all configured dog identifiers."""
        return list(self._ids)

    def get(self, dog_id: str | None) -> DogConfigData | None:
        """Return the raw configuration for the requested dog."""
        if not isinstance(dog_id, str):
            return None
        return self._by_id.get(dog_id.strip())

    def get_name(self, dog_id: str) -> str | None:
        """Return the configured name for the dog if available."""
        config = self.get(dog_id)
        if not config:
            return None
        dog_name = config.get(DOG_NAME_FIELD)
        if isinstance(dog_name, str) and dog_name.strip():
            return dog_name
        return None

    def enabled_modules(self, dog_id: str) -> frozenset[str]:
        """Return the enabled modules for the specified dog."""
        config = self.get(dog_id)
        if not config:
            return frozenset()
        modules_payload = cast(
            Mapping[str, object] | None,
            config.get(CONF_MODULES),
        )
        modules = coerce_dog_modules_config(modules_payload)
        return frozenset(module for module, enabled in modules.items() if bool(enabled))

    def has_module(self, module: str) -> bool:
        """Return True if any dog has the requested module enabled."""
        return any(module in self.enabled_modules(dog_id) for dog_id in self._ids)

    def module_count(self) -> int:
        """Return the total number of enabled modules across all dogs."""
        total = 0
        for dog_id in self._ids:
            total += len(self.enabled_modules(dog_id))
        return total

    def empty_payload(self) -> CoordinatorDogData:
        """Return an empty coordinator payload for a dog."""

        payload: dict[str, object] = {
            'dog_info': cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: '',
                    DOG_NAME_FIELD: '',
                },
            ),
            'status': 'unknown',
            'last_update': None,
        }

        for module in sorted(ALL_MODULES):
            if module in _STATUS_DEFAULT_MODULES:
                payload[module] = cast(
                    CoordinatorModuleState,
                    {
                        'status': 'unknown',
                    },
                )
            else:
                payload[module] = cast(CoordinatorModuleState, {})

        return cast(CoordinatorDogData, payload)

    def calculate_update_interval(self, options: Mapping[str, object]) -> int:
        """Derive the polling interval from configuration options."""
        provided_interval = options.get(CONF_GPS_UPDATE_INTERVAL)
        validated_interval: int | None = None

        if provided_interval not in (None, ''):
            validated_interval = self._validate_gps_interval(provided_interval)

        if not self._ids:
            return self._enforce_polling_limits(UPDATE_INTERVALS.get('minimal', 300))

        if self.has_module(MODULE_GPS):
            gps_interval = (
                validated_interval
                if validated_interval is not None
                else UPDATE_INTERVALS.get('frequent', 60)
            )
            return self._enforce_polling_limits(gps_interval)

        interval: int
        if self.has_module(MODULE_WEATHER):
            interval = UPDATE_INTERVALS.get('frequent', 60)
        else:
            total_modules = self.module_count()
            if total_modules > 15:
                interval = UPDATE_INTERVALS.get('real_time', 30)
            elif total_modules > 8:
                interval = UPDATE_INTERVALS.get('balanced', 120)
            else:
                interval = UPDATE_INTERVALS.get('minimal', 300)

        return self._enforce_polling_limits(interval)

    @staticmethod
    def _enforce_polling_limits(interval: int | None) -> int:
        """Clamp polling intervals to Platinum quality requirements."""

        if not isinstance(interval, int):
            raise ValidationError(
                'update_interval',
                interval,
                'Polling interval must be an integer',
            )

        if interval <= 0:
            raise ValidationError(
                'update_interval',
                interval,
                'Polling interval must be positive',
            )

        return min(interval, MAX_IDLE_POLL_INTERVAL, MAX_POLLING_INTERVAL_SECONDS)

    @staticmethod
    def _validate_gps_interval(value: Any) -> int:
        """Validate the GPS interval option and return a positive integer."""

        if isinstance(value, bool):
            raise ValidationError(
                'gps_update_interval',
                value,
                'Invalid GPS update interval',
            )

        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                raise ValidationError(
                    'gps_update_interval',
                    value,
                    'Invalid GPS update interval',
                )
            try:
                value = int(candidate)
            except ValueError as err:  # pragma: no cover - defensive casting
                raise ValidationError(
                    'gps_update_interval',
                    value,
                    'Invalid GPS update interval',
                ) from err

        if not isinstance(value, int):
            raise ValidationError(
                'gps_update_interval',
                value,
                'Invalid GPS update interval',
            )

        if value <= 0:
            raise ValidationError(
                'gps_update_interval',
                value,
                'Invalid GPS update interval',
            )

        return value


@dataclass(slots=True)
class CoordinatorMetrics:
    """Tracks coordinator level metrics for diagnostics."""

    update_count: int = 0
    failed_cycles: int = 0
    consecutive_errors: int = 0
    statistics_timings: deque[float] = field(
        default_factory=lambda: deque(maxlen=50),
    )
    visitor_mode_timings: deque[float] = field(
        default_factory=lambda: deque(maxlen=50),
    )

    def start_cycle(self) -> None:
        """Record the start of a coordinator update cycle."""
        self.update_count += 1

    def record_cycle(self, total: int, errors: int) -> tuple[float, bool]:
        """Record a completed cycle and return its success rate and failure flag."""
        if total == 0:
            return 1.0, False

        success_rate = (total - errors) / total
        if errors == total:
            self.failed_cycles += 1
            self.consecutive_errors += 1
            return success_rate, True

        if success_rate < 0.5:
            self.consecutive_errors += 1
        else:
            self.consecutive_errors = 0
        return success_rate, False

    def reset_consecutive(self) -> None:
        """Reset the counter that tracks consecutive error cycles."""
        self.consecutive_errors = 0

    @property
    def successful_cycles(self) -> int:
        """Return how many cycles finished without total failure."""
        return max(self.update_count - self.failed_cycles, 0)

    @property
    def success_rate_percent(self) -> float:
        """Return the success rate as a percentage."""
        if self.update_count == 0:
            return 100.0
        return (self.successful_cycles / self.update_count) * 100

    def record_statistics_timing(self, duration: float) -> None:
        """Track how long runtime statistics generation took in seconds."""

        self.statistics_timings.append(max(duration, 0.0))

    def record_visitor_timing(self, duration: float) -> None:
        """Track how long visitor-mode persistence took in seconds."""

        self.visitor_mode_timings.append(max(duration, 0.0))

    @property
    def average_statistics_runtime_ms(self) -> float:
        """Return the rolling average runtime for statistics generation."""

        if not self.statistics_timings:
            return 0.0
        return (sum(self.statistics_timings) / len(self.statistics_timings)) * 1000

    @property
    def average_visitor_runtime_ms(self) -> float:
        """Return the rolling average runtime for visitor mode persistence."""

        if not self.visitor_mode_timings:
            return 0.0
        return (sum(self.visitor_mode_timings) / len(self.visitor_mode_timings)) * 1000

    def update_statistics(
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
            'update_counts': {
                'total': self.update_count,
                'successful': self.successful_cycles,
                'failed': self.failed_cycles,
            },
            'performance_metrics': {
                'success_rate': round(self.success_rate_percent, 2),
                'cache_entries': cache_entries,
                'cache_hit_rate': round(cache_hit_rate, 2),
                'consecutive_errors': self.consecutive_errors,
                'last_update': last_update,
                'update_interval': update_interval,
                'api_calls': 0,
            },
            'health_indicators': {
                'consecutive_errors': self.consecutive_errors,
                'stability_window_ok': self.consecutive_errors < 5,
            },
        }

        telemetry = _build_repair_telemetry(repair_summary)
        if telemetry:
            payload['repairs'] = telemetry

        return payload

    def runtime_statistics(
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
            'update_counts': {
                'total': self.update_count,
                'successful': self.successful_cycles,
                'failed': self.failed_cycles,
            },
            'context': {
                'total_dogs': total_dogs,
                'last_update': last_update,
                'update_interval': update_interval,
            },
            'error_summary': {
                'consecutive_errors': self.consecutive_errors,
                'error_rate': (
                    self.failed_cycles / self.update_count if self.update_count else 0.0
                ),
            },
            'cache_performance': {
                'hits': cache_metrics.hits,
                'misses': cache_metrics.misses,
                'entries': cache_metrics.entries,
                'hit_rate': cache_hit_rate,
            },
        }

        telemetry = _build_repair_telemetry(repair_summary)
        if telemetry:
            payload['repairs'] = telemetry

        return payload


MANAGER_ATTRIBUTES: tuple[str, ...] = CoordinatorRuntimeManagers.attribute_names(
)


def bind_runtime_managers(
    coordinator: CoordinatorBindingTarget,
    modules: CoordinatorModuleAdapter,
    managers: CoordinatorRuntimeManagers,
) -> None:
    """Bind runtime managers to the coordinator and adapters."""

    coordinator.data_manager = managers.data_manager
    coordinator.feeding_manager = managers.feeding_manager
    coordinator.garden_manager = managers.garden_manager
    coordinator.geofencing_manager = managers.geofencing_manager
    coordinator.gps_geofence_manager = managers.gps_geofence_manager
    coordinator.notification_manager = managers.notification_manager
    coordinator.walk_manager = managers.walk_manager
    coordinator.weather_health_manager = managers.weather_health_manager

    data_manager = managers.data_manager
    gps_manager = managers.gps_geofence_manager
    notification_manager = managers.notification_manager
    if (
        gps_manager
        and notification_manager
        and hasattr(gps_manager, 'set_notification_manager')
    ):
        gps_manager.set_notification_manager(notification_manager)

    modules.attach_managers(
        data_manager=managers.data_manager,
        feeding_manager=managers.feeding_manager,
        walk_manager=managers.walk_manager,
        gps_geofence_manager=managers.gps_geofence_manager,
        weather_health_manager=managers.weather_health_manager,
        garden_manager=managers.garden_manager,
    )

    if (
        data_manager is not None
        and notification_manager is not None
        and isinstance(data_manager, CacheMonitorRegistrar)
    ):
        register_method = getattr(
            notification_manager,
            'register_cache_monitors',
            None,
        )
        if callable(register_method):
            register_method(data_manager)


def clear_runtime_managers(
    coordinator: CoordinatorBindingTarget,
    modules: CoordinatorModuleAdapter,
) -> None:
    """Clear bound runtime managers from the coordinator."""

    for attr in MANAGER_ATTRIBUTES:
        setattr(coordinator, attr, None)
    modules.detach_managers()
