"""Helper structures for coordinator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol, cast, runtime_checkable

from .config_entry_helpers import get_entry_dogs
from .const import CONF_MODULES, DOG_ID_FIELD, DOG_NAME_FIELD
from .types import (
  CacheRepairAggregate,
  CoordinatorRuntimeManagers,
  CoordinatorRuntimeStatisticsPayload,
  CoordinatorStatisticsPayload,
  DogConfigData,
  ModuleCacheMetrics,
  PawControlConfigEntry,
  coerce_dog_modules_config,
)


@dataclass(slots=True)
class DogConfigRegistry:
  """Registry for configured dogs."""

  configs: list[DogConfigData]
  _by_id: dict[str, DogConfigData] = field(init=False, default_factory=dict)

  def __post_init__(self) -> None:
    for config in self.configs:
      if dog_id := config.get(DOG_ID_FIELD):
        self._by_id[str(dog_id).strip()] = config

  @classmethod
  def from_entry(cls, entry: PawControlConfigEntry) -> DogConfigRegistry:
    raw = get_entry_dogs(entry)
    return cls([cast(DogConfigData, d) for d in raw if isinstance(d, dict)])

  def __len__(self) -> int:
    return len(self._by_id)

  def ids(self) -> list[str]:
    return list(self._by_id.keys())

  def get(self, dog_id: str | None) -> DogConfigData | None:
    if not dog_id:
      return None
    return self._by_id.get(dog_id)

  def get_name(self, dog_id: str) -> str | None:
    config = self.get(dog_id)
    if not config:
      return None
    name = config.get(DOG_NAME_FIELD)
    return name if isinstance(name, str) and name else None

  def enabled_modules(self, dog_id: str) -> frozenset[str]:
    config = self.get(dog_id)
    if not config:
      return frozenset()
    modules = coerce_dog_modules_config(config.get(CONF_MODULES))
    return frozenset(k for k, v in modules.items() if v)

  def empty_payload(self) -> dict[str, Any]:
    return {
      "dog_info": {DOG_ID_FIELD: "", DOG_NAME_FIELD: ""},
      "status": "unknown",
      "last_update": None,
    }

  def calculate_update_interval(self, options: Mapping[str, object]) -> int:
    del options
    return 120


def ensure_cache_repair_aggregate(summary: Any) -> CacheRepairAggregate | None:
  """Return cache repair aggregate when available."""

  if isinstance(summary, CacheRepairAggregate):
    return summary
  return None


@runtime_checkable
class CoordinatorBindingTarget(Protocol):
  """Coordinator interface required for runtime manager binding."""


@runtime_checkable
class CoordinatorModuleAdapter(Protocol):
  """Protocol describing minimal adapter interface."""

  def attach_managers(self, **kwargs: Any) -> None: ...

  def detach_managers(self) -> None: ...


@dataclass(slots=True)
class CoordinatorMetrics:
  """Simple metrics tracking."""

  update_count: int = 0
  failed_cycles: int = 0
  consecutive_errors: int = 0

  def start_cycle(self) -> None:
    self.update_count += 1

  def record_cycle(self, total: int, errors: int) -> tuple[float, bool]:
    if total == 0:
      return 1.0, False
    failed = errors == total
    if failed:
      self.failed_cycles += 1
      self.consecutive_errors += 1
    else:
      self.consecutive_errors = 0
    return (total - errors) / total, failed

  def reset_consecutive_errors(self) -> None:
    self.consecutive_errors = 0

  @property
  def successful_cycles(self) -> int:
    return max(self.update_count - self.failed_cycles, 0)

  def update_statistics(
    self,
    *,
    cache_entries: int,
    cache_hit_rate: float,
    last_update: Any,
    interval: timedelta | None,
    repair_summary: CacheRepairAggregate | None = None,
  ) -> CoordinatorStatisticsPayload:
    del repair_summary
    return {
      "update_counts": {
        "total": self.update_count,
        "successful": self.successful_cycles,
        "failed": self.failed_cycles,
      },
      "performance_metrics": {
        "success_rate": 0.0,
        "cache_entries": cache_entries,
        "cache_hit_rate": cache_hit_rate,
        "consecutive_errors": self.consecutive_errors,
        "last_update": last_update,
        "update_interval": (interval or timedelta()).total_seconds(),
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
    cache_metrics: ModuleCacheMetrics,
    total_dogs: int,
    last_update: Any,
    interval: timedelta | None,
    repair_summary: CacheRepairAggregate | None = None,
  ) -> CoordinatorRuntimeStatisticsPayload:
    del repair_summary
    return {
      "update_counts": {
        "total": self.update_count,
        "successful": self.successful_cycles,
        "failed": self.failed_cycles,
      },
      "context": {
        "total_dogs": total_dogs,
        "last_update": last_update,
        "update_interval": (interval or timedelta()).total_seconds(),
      },
      "error_summary": {
        "consecutive_errors": self.consecutive_errors,
        "error_rate": 0.0,
      },
      "cache_performance": {
        "hits": cache_metrics.hits,
        "misses": cache_metrics.misses,
        "entries": cache_metrics.entries,
        "hit_rate": cache_metrics.hit_rate,
      },
    }


MANAGER_ATTRIBUTES: tuple[str, ...] = CoordinatorRuntimeManagers.attribute_names()


def bind_runtime_managers(
  coordinator: Any,
  modules: CoordinatorModuleAdapter,
  managers: CoordinatorRuntimeManagers,
) -> None:
  """Bind runtime managers with minimal attribute assignment."""

  for attr in MANAGER_ATTRIBUTES:
    setattr(coordinator, attr, getattr(managers, attr, None))
  modules.attach_managers(
    **{attr: getattr(managers, attr, None) for attr in MANAGER_ATTRIBUTES}
  )


def clear_runtime_managers(coordinator: Any, modules: CoordinatorModuleAdapter) -> None:
  """Clear bound runtime managers."""

  for attr in MANAGER_ATTRIBUTES:
    setattr(coordinator, attr, None)
  modules.detach_managers()
