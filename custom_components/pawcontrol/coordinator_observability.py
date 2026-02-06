"""Observability helpers (simplified compatibility layer)."""

from __future__ import annotations

from typing import Any, TypedDict


class EntityBudgetSnapshot(TypedDict):
  """Legacy type definition kept for compatibility."""

  dog_id: str
  capacity: int
  total_allocated: int


class EntityBudgetTracker:
  """Minimal no-op tracker kept for compatibility with older call sites."""

  def __init__(self) -> None:
    self._snapshots: dict[str, EntityBudgetSnapshot] = {}

  def record(self, snapshot: EntityBudgetSnapshot) -> None:
    self._snapshots[snapshot["dog_id"]] = snapshot

  def saturation(self) -> float:
    return 0.0

  def summary(self) -> dict[str, Any]:
    return {
      "dog_count": len(self._snapshots),
      "peak_utilization": 0.0,
      "average_utilization": 0.0,
      "snapshots": list(self._snapshots.values()),
    }

  def snapshots(self) -> tuple[EntityBudgetSnapshot, ...]:
    return tuple(self._snapshots.values())


def build_performance_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
  """Return empty performance snapshot."""
  return {}


def build_security_scorecard(*args: Any, **kwargs: Any) -> dict[str, Any]:
  """Return default passing scorecard."""
  return {"status": "pass", "checks": {}}


def normalise_webhook_status(manager: Any) -> dict[str, Any]:
  """Return default status."""
  if manager is None:
    return {"configured": False, "secure": True}
  return {"configured": True, "secure": True}
