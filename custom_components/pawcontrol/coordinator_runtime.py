"""Runtime helpers that keep the coordinator compact and testable."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean
from typing import Any, Mapping


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
        """Return the total number of allocated entities."""

        return self.base_allocation + self.dynamic_allocation

    @property
    def remaining(self) -> int:
        """Return the remaining capacity within the budget."""

        return max(self.capacity - self.total_allocated, 0)

    @property
    def saturation(self) -> float:
        """Return the saturation ratio for the entity budget."""

        if self.capacity <= 0:
            return 0.0
        return max(0.0, min(1.0, self.total_allocated / self.capacity))


def summarize_entity_budgets(
    snapshots: Mapping[str, EntityBudgetSnapshot]
) -> dict[str, Any]:
    """Aggregate entity budget information for diagnostics."""

    if not snapshots:
        return {
            "active_dogs": 0,
            "total_capacity": 0,
            "total_allocated": 0,
            "total_remaining": 0,
            "average_utilization": 0.0,
            "peak_utilization": 0.0,
            "denied_requests": 0,
        }

    values = list(snapshots.values())
    total_capacity = sum(snapshot.capacity for snapshot in values)
    total_allocated = sum(snapshot.total_allocated for snapshot in values)
    total_remaining = sum(snapshot.remaining for snapshot in values)
    denied_requests = sum(len(snapshot.denied_requests) for snapshot in values)
    average_utilization = (total_allocated / total_capacity) if total_capacity else 0.0
    peak_utilization = max((snapshot.saturation for snapshot in values), default=0.0)

    return {
        "active_dogs": len(values),
        "total_capacity": total_capacity,
        "total_allocated": total_allocated,
        "total_remaining": total_remaining,
        "average_utilization": round(average_utilization * 100, 1),
        "peak_utilization": round(peak_utilization * 100, 1),
        "denied_requests": denied_requests,
    }


class AdaptivePollingController:
    """Manage dynamic polling intervals based on runtime performance."""

    __slots__ = (
        "_history",
        "_min_interval",
        "_max_interval",
        "_target_cycle",
        "_current_interval",
        "_error_streak",
        "_entity_saturation",
    )

    def __init__(
        self,
        *,
        initial_interval_seconds: float,
        target_cycle_ms: float = 200.0,
        min_interval_seconds: float = 0.2,
        max_interval_seconds: float = 5.0,
    ) -> None:
        """Initialize the adaptive polling controller."""

        self._history: deque[float] = deque(maxlen=32)
        self._min_interval = max(min_interval_seconds, 0.05)
        self._max_interval = max(max_interval_seconds, self._min_interval)
        self._target_cycle = max(target_cycle_ms / 1000.0, self._min_interval)
        self._current_interval = min(
            max(initial_interval_seconds, self._min_interval), self._max_interval
        )
        self._error_streak = 0
        self._entity_saturation = 0.0

    @property
    def current_interval(self) -> float:
        """Return the current polling interval in seconds."""

        return self._current_interval

    def update_entity_saturation(self, saturation: float) -> None:
        """Update entity saturation feedback for adaptive decisions."""

        self._entity_saturation = max(0.0, min(1.0, saturation))

    def record_cycle(
        self,
        *,
        duration: float,
        success: bool,
        error_ratio: float,
    ) -> float:
        """Record an update cycle and return the next interval in seconds."""

        self._history.append(max(duration, 0.0))
        self._error_streak = 0 if success else self._error_streak + 1

        average_duration = fmean(self._history) if len(self._history) > 1 else self._history[0]
        next_interval = self._current_interval

        if not success:
            penalty_factor = 1.0 + min(0.5, 0.15 * self._error_streak + error_ratio)
            next_interval = min(self._max_interval, next_interval * penalty_factor)
        else:
            load_factor = 1.0 + (self._entity_saturation * 0.5)
            if average_duration < self._target_cycle * 0.8:
                reduction_factor = min(2.0, (self._target_cycle / average_duration) * 0.5)
                next_interval = max(
                    self._min_interval,
                    next_interval / max(1.0, reduction_factor * load_factor),
                )
            elif average_duration > self._target_cycle * 1.1:
                increase_factor = min(2.5, average_duration / self._target_cycle)
                next_interval = min(
                    self._max_interval,
                    next_interval * (increase_factor * load_factor),
                )

        self._current_interval = max(
            self._min_interval, min(self._max_interval, next_interval)
        )
        return self._current_interval

    def as_diagnostics(self) -> dict[str, Any]:
        """Return diagnostics for adaptive polling behaviour."""

        history_count = len(self._history)
        average_duration = fmean(self._history) if history_count else 0.0
        return {
            "target_cycle_ms": round(self._target_cycle * 1000, 2),
            "current_interval_ms": round(self._current_interval * 1000, 2),
            "average_cycle_ms": round(average_duration * 1000, 2),
            "history_samples": history_count,
            "error_streak": self._error_streak,
            "entity_saturation": round(self._entity_saturation, 3),
        }

