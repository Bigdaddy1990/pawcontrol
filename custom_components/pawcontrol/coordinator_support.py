"""Helper structures that keep :mod:`coordinator` lean and maintainable."""

from __future__ import annotations

from collections.abc import Mapping
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
    def from_entry(cls, entry: PawControlConfigEntry) -> "DogConfigRegistry":
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
        return len(self._ids)

    def ids(self) -> list[str]:
        return list(self._ids)

    def get(self, dog_id: str | None) -> DogConfigData | None:
        if not isinstance(dog_id, str):
            return None
        return self._by_id.get(dog_id.strip())

    def get_name(self, dog_id: str) -> str | None:
        config = self.get(dog_id)
        if not config:
            return None
        dog_name = config.get(CONF_DOG_NAME)
        if isinstance(dog_name, str) and dog_name.strip():
            return dog_name
        return None

    def enabled_modules(self, dog_id: str) -> frozenset[str]:
        config = self.get(dog_id)
        if not config:
            return frozenset()
        modules = config.get(CONF_MODULES, {})
        return frozenset(
            module for module, enabled in modules.items() if bool(enabled)
        )

    def has_module(self, module: str) -> bool:
        return any(module in self.enabled_modules(dog_id) for dog_id in self._ids)

    def module_count(self) -> int:
        total = 0
        for dog_id in self._ids:
            total += len(self.enabled_modules(dog_id))
        return total

    def empty_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "dog_info": {},
            "status": "unknown",
            "last_update": None,
        }
        for module in sorted(ALL_MODULES):
            payload[module] = {}
        return payload

    def calculate_update_interval(self, options: Mapping[str, Any]) -> int:
        if not self._ids:
            return UPDATE_INTERVALS.get("minimal", 300)

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
            return gps_interval

        if self.has_module(MODULE_WEATHER):
            return UPDATE_INTERVALS.get("frequent", 60)

        total_modules = self.module_count()
        if total_modules > 15:
            return UPDATE_INTERVALS.get("real_time", 30)
        if total_modules > 8:
            return UPDATE_INTERVALS.get("balanced", 120)
        return UPDATE_INTERVALS.get("minimal", 300)


@dataclass(slots=True)
class CoordinatorMetrics:
    """Tracks coordinator level metrics for diagnostics."""

    update_count: int = 0
    failed_cycles: int = 0
    consecutive_errors: int = 0

    def start_cycle(self) -> None:
        self.update_count += 1

    def record_cycle(self, total: int, errors: int) -> tuple[float, bool]:
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
        self.consecutive_errors = 0

    @property
    def successful_cycles(self) -> int:
        return max(self.update_count - self.failed_cycles, 0)

    @property
    def success_rate_percent(self) -> float:
        if self.update_count == 0:
            return 100.0
        return (self.successful_cycles / self.update_count) * 100

    def update_statistics(self, cache_entries: int, cache_hit_rate: float, last_update: Any, interval: timedelta | None) -> dict[str, Any]:
        return {
            "total_updates": self.update_count,
            "successful_updates": self.successful_cycles,
            "failed": self.failed_cycles,
            "success_rate": self.success_rate_percent,
            "cache_entries": cache_entries,
            "cache_hit_rate": cache_hit_rate,
            "consecutive_errors": self.consecutive_errors,
            "last_update": last_update,
            "update_interval": (interval or timedelta()).total_seconds(),
        }

    def runtime_statistics(self, cache_metrics: Any, total_dogs: int, last_update: Any, interval: timedelta | None) -> dict[str, Any]:
        return {
            "total_dogs": total_dogs,
            "update_count": self.update_count,
            "error_count": self.failed_cycles,
            "consecutive_errors": self.consecutive_errors,
            "error_rate": (
                self.failed_cycles / self.update_count if self.update_count else 0.0
            ),
            "last_update": last_update,
            "update_interval": (interval or timedelta()).total_seconds(),
            "cache_performance": {
                "hits": getattr(cache_metrics, "hits", 0),
                "misses": getattr(cache_metrics, "misses", 0),
                "entries": getattr(cache_metrics, "entries", 0),
                "hit_rate": getattr(cache_metrics, "hit_rate", 0.0) / 100,
            },
        }


@dataclass(slots=True)
class UpdateResult:
    """Container for update outcomes."""

    payload: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: int = 0

    def add_success(self, dog_id: str, data: dict[str, Any]) -> None:
        self.payload[dog_id] = data

    def add_error(self, dog_id: str, data: dict[str, Any]) -> None:
        self.errors += 1
        self.payload[dog_id] = data
