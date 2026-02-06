"""Runtime definitions for PawControl coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .exceptions import UpdateFailed
from .types import AdaptivePollingDiagnostics, EntityBudgetSummary

CoordinatorUpdateFailed = UpdateFailed


@dataclass(slots=True)
class EntityBudgetSnapshot:
  """Snapshot of entity budget utilisation for a single dog."""

  dog_id: str
  profile: str
  capacity: int
  base_allocation: int
  dynamic_allocation: int
  requested_entities: tuple[str, ...]
  denied_requests: tuple[str, ...]
  recorded_at: datetime

  @property
  def total_allocated(self) -> int:
    return self.base_allocation + self.dynamic_allocation

  @property
  def remaining(self) -> int:
    return max(self.capacity - self.total_allocated, 0)

  @property
  def saturation(self) -> float:
    if self.capacity <= 0:
      return 0.0
    return max(0.0, min(1.0, self.total_allocated / self.capacity))


class AdaptivePollingController:
  """Compatibility controller that keeps polling intervals fixed."""

  __slots__ = ("_current_interval",)

  def __init__(self, *, initial_interval_seconds: float, **_: Any) -> None:
    self._current_interval = max(initial_interval_seconds, 1.0)

  @property
  def current_interval(self) -> float:
    return self._current_interval

  def update_entity_saturation(self, saturation: float) -> None:
    del saturation

  def record_cycle(
    self, *, duration: float, success: bool, error_ratio: float
  ) -> float:
    del duration, success, error_ratio
    return self._current_interval

  def as_diagnostics(self) -> AdaptivePollingDiagnostics:
    return {
      "target_cycle_ms": 0.0,
      "current_interval_ms": round(self._current_interval * 1000, 2),
      "average_cycle_ms": 0.0,
      "history_samples": 0,
      "error_streak": 0,
      "entity_saturation": 0.0,
      "idle_interval_ms": round(self._current_interval * 1000, 2),
      "idle_grace_ms": 0.0,
    }


@dataclass(slots=True)
class RuntimeCycleInfo:
  """Minimal cycle info."""

  dog_count: int
  success: bool

  def to_dict(self) -> dict[str, Any]:
    return {"dog_count": self.dog_count, "success": self.success}


def summarize_entity_budgets(
  snapshots: tuple[EntityBudgetSnapshot, ...] | list[EntityBudgetSnapshot],
) -> EntityBudgetSummary:
  """Summarise entity budget usage for diagnostics."""

  items = list(snapshots)
  if not items:
    return {
      "active_dogs": 0,
      "total_capacity": 0,
      "total_allocated": 0,
      "total_remaining": 0,
      "average_utilization": 0.0,
      "peak_utilization": 0.0,
      "denied_requests": 0,
    }

  total_capacity = sum(item.capacity for item in items)
  total_allocated = sum(item.total_allocated for item in items)
  total_remaining = sum(item.remaining for item in items)
  denied_requests = sum(len(item.denied_requests) for item in items)
  avg = (total_allocated / total_capacity) if total_capacity else 0.0
  peak = max((item.saturation for item in items), default=0.0)
  return {
    "active_dogs": len(items),
    "total_capacity": total_capacity,
    "total_allocated": total_allocated,
    "total_remaining": total_remaining,
    "average_utilization": round(avg * 100, 1),
    "peak_utilization": round(peak * 100, 1),
    "denied_requests": denied_requests,
  }


class CoordinatorRuntime:
  """Compatibility runtime stub."""

  async def execute_cycle(
    self, *args: Any, **kwargs: Any
  ) -> tuple[dict[str, Any], RuntimeCycleInfo]:
    del args, kwargs
    return {}, RuntimeCycleInfo(dog_count=0, success=True)


def _utc_timestamp() -> float:
  return datetime.now(UTC).timestamp()
