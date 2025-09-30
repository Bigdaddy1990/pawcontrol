"""Runtime helpers that keep :mod:`coordinator` focused on orchestration."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean
from typing import Any, Callable, Iterable, Mapping, Sequence

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import CoordinatorUpdateFailed
from homeassistant.util import dt as dt_util

from .coordinator_support import CoordinatorMetrics, DogConfigRegistry
from .exceptions import GPSUnavailableError, NetworkError, ValidationError
from .module_adapters import CoordinatorModuleAdapters
from .resilience import ResilienceManager, RetryConfig

API_TIMEOUT = 30.0


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
        """Initialise the adaptive polling controller."""

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
        if success:
            self._error_streak = 0
        else:
            self._error_streak += 1

        average_duration = self._history[-1]
        if len(self._history) > 1:
            average_duration = fmean(self._history)

        next_interval = self._current_interval

        if not success:
            # Back off quickly when consecutive errors occur.
            penalty_factor = 1.0 + min(0.5, 0.15 * self._error_streak + error_ratio)
            next_interval = min(self._max_interval, next_interval * penalty_factor)
        else:
            load_factor = 1.0 + (self._entity_saturation * 0.5)
            if average_duration < self._target_cycle * 0.8:
                reduction_factor = min(
                    2.0, (self._target_cycle / average_duration) * 0.5
                )
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


@dataclass(slots=True)
class RuntimeCycleInfo:
    """Summary of a coordinator update cycle."""

    dog_count: int
    errors: int
    success_rate: float
    duration: float
    new_interval: float
    error_ratio: float
    success: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a serialisable representation of the cycle."""

        return {
            "dog_count": self.dog_count,
            "errors": self.errors,
            "success_rate": round(self.success_rate * 100, 2),
            "duration_ms": round(self.duration * 1000, 2),
            "next_interval_s": round(self.new_interval, 3),
            "error_ratio": round(self.error_ratio, 3),
            "success": self.success,
        }


def summarize_entity_budgets(
    snapshots: Iterable[EntityBudgetSnapshot],
) -> dict[str, Any]:
    """Summarise entity budget usage for diagnostics."""

    snapshots = list(snapshots)
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

    total_capacity = sum(snapshot.capacity for snapshot in snapshots)
    total_allocated = sum(snapshot.total_allocated for snapshot in snapshots)
    total_remaining = sum(snapshot.remaining for snapshot in snapshots)
    denied_requests = sum(len(snapshot.denied_requests) for snapshot in snapshots)
    average_utilisation = (total_allocated / total_capacity) if total_capacity else 0.0
    peak_utilisation = max((snapshot.saturation for snapshot in snapshots), default=0.0)

    return {
        "active_dogs": len(snapshots),
        "total_capacity": total_capacity,
        "total_allocated": total_allocated,
        "total_remaining": total_remaining,
        "average_utilization": round(average_utilisation * 100, 1),
        "peak_utilization": round(peak_utilisation * 100, 1),
        "denied_requests": denied_requests,
    }


class CoordinatorRuntime:
    """Encapsulates the heavy lifting of coordinator update cycles."""

    def __init__(
        self,
        *,
        registry: DogConfigRegistry,
        modules: CoordinatorModuleAdapters,
        resilience_manager: ResilienceManager,
        retry_config: RetryConfig,
        metrics: CoordinatorMetrics,
        adaptive_polling: AdaptivePollingController,
        logger: logging.Logger,
    ) -> None:
        self._registry = registry
        self._modules = modules
        self._resilience = resilience_manager
        self._retry = retry_config
        self._metrics = metrics
        self._adaptive_polling = adaptive_polling
        self._logger = logger

    async def execute_cycle(
        self,
        dog_ids: Sequence[str],
        current_data: Mapping[str, dict[str, Any]],
        *,
        empty_payload_factory: Callable[[], dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], RuntimeCycleInfo]:
        """Fetch data for all configured dogs and return diagnostics."""

        if not dog_ids:
            raise CoordinatorUpdateFailed("No valid dogs configured")

        self._metrics.start_cycle()
        all_data: dict[str, dict[str, Any]] = {}
        errors = 0
        cycle_start = time.perf_counter()

        async def fetch_and_store(dog_id: str) -> None:
            nonlocal errors

            try:
                result = await self._resilience.execute_with_resilience(
                    self._fetch_dog_data_protected,
                    dog_id,
                    circuit_breaker_name=f"dog_data_{dog_id}",
                    retry_config=self._retry,
                )
            except ConfigEntryAuthFailed:
                errors += 1
                raise
            except ValidationError as err:
                errors += 1
                self._logger.error("Invalid configuration for dog %s: %s", dog_id, err)
                all_data[dog_id] = empty_payload_factory()
            except Exception as err:
                errors += 1
                self._logger.error(
                    "Resilience patterns exhausted for dog %s: %s (%s)",
                    dog_id,
                    err,
                    err.__class__.__name__,
                )
                all_data[dog_id] = current_data.get(dog_id, empty_payload_factory())
            else:
                all_data[dog_id] = result

        try:
            async with asyncio.TaskGroup() as task_group:
                for dog_id in dog_ids:
                    task_group.create_task(fetch_and_store(dog_id))
        except* ConfigEntryAuthFailed as auth_error_group:
            raise auth_error_group.exceptions[0]  # noqa: B904
        except* Exception as error_group:  # pragma: no cover - defensive logging
            for exc in error_group.exceptions:
                self._logger.error("Task group error: %s", exc)

        total_dogs = len(dog_ids)
        success_rate, all_failed = self._metrics.record_cycle(total_dogs, errors)

        if all_failed:
            raise CoordinatorUpdateFailed(
                f"All {total_dogs} dogs failed to update"
            )

        if success_rate < 0.5:
            self._logger.warning(
                "Low success rate: %d/%d dogs updated successfully",
                total_dogs - errors,
                total_dogs,
            )

        duration = max(time.perf_counter() - cycle_start, 0.0)
        error_ratio = errors / total_dogs if total_dogs else 0.0
        success = errors < total_dogs
        new_interval = self._adaptive_polling.record_cycle(
            duration=duration,
            success=success,
            error_ratio=error_ratio,
        )

        return all_data, RuntimeCycleInfo(
            dog_count=total_dogs,
            errors=errors,
            success_rate=success_rate,
            duration=duration,
            new_interval=new_interval,
            error_ratio=error_ratio,
            success=success,
        )

    async def _fetch_dog_data_protected(self, dog_id: str) -> dict[str, Any]:
        async with asyncio.timeout(API_TIMEOUT):
            return await self._fetch_dog_data(dog_id)

    async def _fetch_dog_data(self, dog_id: str) -> dict[str, Any]:
        dog_config = self._registry.get(dog_id)
        if not dog_config:
            raise ValidationError("dog_id", dog_id, "Dog configuration not found")

        payload: dict[str, Any] = {
            "dog_info": dog_config,
            "status": "online",
            "last_update": dt_util.utcnow().isoformat(),
        }

        modules = dog_config.get("modules", {})
        module_tasks = self._modules.build_tasks(dog_id, modules)
        if not module_tasks:
            return payload

        results = await asyncio.gather(
            *(task for _, task in module_tasks), return_exceptions=True
        )

        for (module_name, _), result in zip(module_tasks, results, strict=True):
            if isinstance(result, GPSUnavailableError):
                self._logger.debug("GPS unavailable for %s: %s", dog_id, result)
                payload[module_name] = {
                    "status": "unavailable",
                    "reason": str(result),
                }
            elif isinstance(result, NetworkError):
                self._logger.warning(
                    "Network error fetching %s data for %s: %s",
                    module_name,
                    dog_id,
                    result,
                )
                payload[module_name] = {"status": "network_error"}
            elif isinstance(result, Exception):
                self._logger.warning(
                    "Failed to fetch %s data for %s: %s (%s)",
                    module_name,
                    dog_id,
                    result,
                    result.__class__.__name__,
                )
                payload[module_name] = {"status": "error"}
            else:
                payload[module_name] = result

        return payload

