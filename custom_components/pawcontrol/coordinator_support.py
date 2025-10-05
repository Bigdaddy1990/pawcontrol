"""Helper structures that keep :mod:`coordinator` lean and maintainable."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from collections.abc import Mapping as TypingMapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .const import (
    ALL_MODULES,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_MODULES,
    MAX_IDLE_POLL_INTERVAL,
    MAX_POLLING_INTERVAL_SECONDS,
    MODULE_GPS,
    MODULE_WEATHER,
    UPDATE_INTERVALS,
)
from .exceptions import ValidationError
from .types import DogConfigData, PawControlConfigEntry


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
            if not isinstance(raw_config, dict):
                continue

            config = dict(raw_config)
            modules = config.get(CONF_MODULES)
            if not isinstance(modules, dict):
                config[CONF_MODULES] = {}

            dog_id = config.get(CONF_DOG_ID)
            if not isinstance(dog_id, str):
                continue

            normalized = dog_id.strip()
            if not normalized or normalized in self._by_id:
                continue

            config[CONF_DOG_ID] = normalized
            self._by_id[normalized] = config
            self._ids.append(normalized)
            cleaned.append(config)

        self.configs = cleaned

    @classmethod
    def from_entry(cls, entry: PawControlConfigEntry) -> DogConfigRegistry:
        """Build registry from a config entry."""

        raw_dogs = entry.data.get(CONF_DOGS, [])
        if raw_dogs in (None, ""):
            raw_dogs = []
        if not isinstance(raw_dogs, list):
            raise ValidationError(
                "dogs_config",
                type(raw_dogs).__name__,
                "Must be a list of dog configurations",
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
        dog_name = config.get(CONF_DOG_NAME)
        if isinstance(dog_name, str) and dog_name.strip():
            return dog_name
        return None

    def enabled_modules(self, dog_id: str) -> frozenset[str]:
        """Return the enabled modules for the specified dog."""
        config = self.get(dog_id)
        if not config:
            return frozenset()
        modules = config.get(CONF_MODULES, {})
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

    def empty_payload(self) -> dict[str, Any]:
        """Return an empty coordinator payload for a dog."""
        payload: dict[str, Any] = {
            "dog_info": {},
            "status": "unknown",
            "last_update": None,
        }
        for module in sorted(ALL_MODULES):
            payload[module] = {}
        return payload

    def calculate_update_interval(self, options: Mapping[str, Any]) -> int:
        """Derive the polling interval from configuration options."""
        if not self._ids:
            interval = UPDATE_INTERVALS.get("minimal", 300)
            return self._enforce_polling_limits(interval)

        if self.has_module(MODULE_GPS):
            gps_interval = options.get(
                CONF_GPS_UPDATE_INTERVAL, UPDATE_INTERVALS.get("frequent", 60)
            )
            if not isinstance(gps_interval, int) or gps_interval <= 0:
                raise ValidationError(
                    "gps_update_interval",
                    gps_interval,
                    "Invalid GPS update interval",
                )
            return self._enforce_polling_limits(gps_interval)

        interval: int
        if self.has_module(MODULE_WEATHER):
            interval = UPDATE_INTERVALS.get("frequent", 60)
        else:
            total_modules = self.module_count()
            if total_modules > 15:
                interval = UPDATE_INTERVALS.get("real_time", 30)
            elif total_modules > 8:
                interval = UPDATE_INTERVALS.get("balanced", 120)
            else:
                interval = UPDATE_INTERVALS.get("minimal", 300)

        return self._enforce_polling_limits(interval)


@staticmethod
def _enforce_polling_limits(interval: int | None) -> int:
    """Clamp polling intervals to Bronze quality requirements."""

    def _enforce_polling_limits(interval: int | None) -> int:
        """Clamp polling intervals to Bronze quality requirements."""

        if not isinstance(interval, int):
            raise ValidationError(
                "update_interval", interval, "Polling interval must be an integer"
            )

        if interval <= 0:
            raise ValidationError(
                "update_interval", interval, "Polling interval must be positive"
            )

        return min(interval, MAX_IDLE_POLL_INTERVAL, MAX_POLLING_INTERVAL_SECONDS)


@dataclass(slots=True)
class CoordinatorMetrics:
    """Tracks coordinator level metrics for diagnostics."""

    update_count: int = 0
    failed_cycles: int = 0
    consecutive_errors: int = 0
    statistics_timings: deque[float] = field(default_factory=lambda: deque(maxlen=50))
    visitor_mode_timings: deque[float] = field(default_factory=lambda: deque(maxlen=50))

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
    ) -> dict[str, Any]:
        """Return a statistics snapshot for diagnostics panels."""
        update_interval = (interval or timedelta()).total_seconds()
        return {
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

    def runtime_statistics(
        self,
        *,
        cache_metrics: Any,
        total_dogs: int,
        last_update: Any,
        interval: timedelta | None,
    ) -> dict[str, Any]:
        """Return runtime statistics derived from cached metrics."""
        update_interval = (interval or timedelta()).total_seconds()
        raw_hit_rate = getattr(cache_metrics, "hit_rate", 0.0)
        try:
            cache_hit_rate = float(raw_hit_rate)
        except (TypeError, ValueError):
            cache_hit_rate = 0.0
        cache_hit_rate = min(max(cache_hit_rate, 0.0), 100.0)
        return {
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
                "hits": getattr(cache_metrics, "hits", 0),
                "misses": getattr(cache_metrics, "misses", 0),
                "entries": getattr(cache_metrics, "entries", 0),
                "hit_rate": cache_hit_rate,
            },
        }


MANAGER_ATTRIBUTES: tuple[str, ...] = (
    "data_manager",
    "feeding_manager",
    "garden_manager",
    "geofencing_manager",
    "gps_geofence_manager",
    "notification_manager",
    "walk_manager",
    "weather_health_manager",
)


def bind_runtime_managers(
    coordinator: Any,
    modules: Any,
    managers: TypingMapping[str, Any],
) -> None:
    """Bind runtime managers to the coordinator and adapters."""

    for attr in MANAGER_ATTRIBUTES:
        setattr(coordinator, attr, managers.get(attr))

    gps_manager = managers.get("gps_geofence_manager")
    notification_manager = managers.get("notification_manager")
    if (
        gps_manager
        and notification_manager
        and hasattr(gps_manager, "set_notification_manager")
    ):
        gps_manager.set_notification_manager(notification_manager)

    modules.attach_managers(
        data_manager=managers.get("data_manager"),
        feeding_manager=managers.get("feeding_manager"),
        walk_manager=managers.get("walk_manager"),
        gps_geofence_manager=managers.get("gps_geofence_manager"),
        weather_health_manager=managers.get("weather_health_manager"),
        garden_manager=managers.get("garden_manager"),
    )


def clear_runtime_managers(coordinator: Any, modules: Any) -> None:
    """Clear bound runtime managers from the coordinator."""

    for attr in MANAGER_ATTRIBUTES:
        setattr(coordinator, attr, None)
    modules.detach_managers()
