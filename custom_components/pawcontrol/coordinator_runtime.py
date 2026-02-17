"""Runtime helpers that keep :mod:`coordinator` focused on orchestration."""

import asyncio
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from statistics import fmean
import time
from typing import cast

from .exceptions import ConfigEntryAuthFailed, UpdateFailed

try:  # pragma: no cover - prefer Home Assistant's timezone helpers when available
  from homeassistant.util import dt as dt_util  # noqa: E111
except (ImportError, ModuleNotFoundError):

  class _DateTimeModule:  # noqa: E111
    """Minimal subset of :mod:`homeassistant.util.dt` used in tests."""

    @staticmethod
    def utcnow() -> datetime:
      return datetime.now(UTC)  # noqa: E111

  dt_util = _DateTimeModule()  # noqa: E111

from .coordinator_support import CoordinatorMetrics, DogConfigRegistry
from .dog_status import build_dog_status_snapshot
from .exceptions import (
  GPSUnavailableError,
  NetworkError,
  RateLimitError,
  ValidationError,
)
from .module_adapters import CoordinatorModuleAdapters
from .resilience import ResilienceManager, RetryConfig
from .types import (
  AdaptivePollingDiagnostics,
  CoordinatorDataPayload,
  CoordinatorDogData,
  CoordinatorModuleErrorPayload,
  CoordinatorModuleTask,
  CoordinatorRuntimeCycleSnapshot,
  CoordinatorTypedModuleName,
  EntityBudgetSummary,
  ModuleAdapterPayload,
  ensure_dog_modules_mapping,
)

CoordinatorUpdateFailed = UpdateFailed

API_TIMEOUT = 30.0


@dataclass(slots=True)
class EntityBudgetSnapshot:
  """Snapshot of entity budget utilisation for a single dog."""  # noqa: E111

  dog_id: str  # noqa: E111
  profile: str  # noqa: E111
  capacity: int  # noqa: E111
  base_allocation: int  # noqa: E111
  dynamic_allocation: int  # noqa: E111
  requested_entities: tuple[str, ...]  # noqa: E111
  denied_requests: tuple[str, ...]  # noqa: E111
  recorded_at: datetime  # noqa: E111

  @property  # noqa: E111
  def total_allocated(self) -> int:  # noqa: E111
    """Return the total number of allocated entities."""

    return self.base_allocation + self.dynamic_allocation

  @property  # noqa: E111
  def remaining(self) -> int:  # noqa: E111
    """Return the remaining capacity within the budget."""

    return max(self.capacity - self.total_allocated, 0)

  @property  # noqa: E111
  def saturation(self) -> float:  # noqa: E111
    """Return the saturation ratio for the entity budget."""

    if self.capacity <= 0:
      return 0.0  # noqa: E111
    return max(0.0, min(1.0, self.total_allocated / self.capacity))


class AdaptivePollingController:
  """Manage dynamic polling intervals based on runtime performance."""  # noqa: E111

  __slots__ = (  # noqa: E111
    "_current_interval",
    "_entity_saturation",
    "_error_streak",
    "_history",
    "_idle_grace",
    "_idle_interval",
    "_last_activity",
    "_max_interval",
    "_min_interval",
    "_target_cycle",
  )

  def __init__(  # noqa: E111
    self,
    *,
    initial_interval_seconds: float,
    target_cycle_ms: float = 200.0,
    min_interval_seconds: float | None = None,
    max_interval_seconds: float | None = None,
    idle_interval_seconds: float = 900.0,
    idle_grace_seconds: float = 300.0,
  ) -> None:
    """Initialise the adaptive polling controller."""

    base_interval = max(initial_interval_seconds, 1.0)
    calculated_min = (
      base_interval * 0.25 if min_interval_seconds is None else min_interval_seconds
    )
    calculated_max = (
      base_interval * 4 if max_interval_seconds is None else max_interval_seconds
    )

    self._history: deque[float] = deque(maxlen=32)
    self._min_interval = max(calculated_min, 15.0)
    idle_target = max(idle_interval_seconds, self._min_interval)
    self._max_interval = max(calculated_max, idle_target)
    self._idle_interval = idle_target
    self._idle_grace = max(idle_grace_seconds, 0.0)
    self._target_cycle = max(target_cycle_ms / 1000.0, self._min_interval)
    self._current_interval = min(base_interval, self._max_interval)
    self._error_streak = 0
    self._entity_saturation = 0.0
    self._last_activity = time.monotonic()

  @property  # noqa: E111
  def current_interval(self) -> float:  # noqa: E111
    """Return the current polling interval in seconds."""

    return self._current_interval

  def update_entity_saturation(self, saturation: float) -> None:  # noqa: E111
    """Update entity saturation feedback for adaptive decisions."""

    self._entity_saturation = max(0.0, min(1.0, saturation))

  def record_cycle(  # noqa: E111
    self,
    *,
    duration: float,
    success: bool,
    error_ratio: float,
  ) -> float:
    """Record an update cycle and return the next interval in seconds."""

    self._history.append(max(duration, 0.0))
    if success:
      self._error_streak = 0  # noqa: E111
    else:
      self._error_streak += 1  # noqa: E111

    average_duration = self._history[-1]
    if len(self._history) > 1:
      average_duration = fmean(self._history)  # noqa: E111

    next_interval = self._current_interval

    now = time.monotonic()

    if success and (error_ratio > 0.01 or self._entity_saturation > 0.3):
      self._last_activity = now  # noqa: E111

    if not success:
      # Back off quickly when consecutive errors occur.  # noqa: E114
      penalty_factor = 1.0 + min(0.5, 0.15 * self._error_streak + error_ratio)  # noqa: E111
      next_interval = min(  # noqa: E111
        self._max_interval,
        next_interval * penalty_factor,
      )
    else:
      load_factor = 1.0 + (self._entity_saturation * 0.5)  # noqa: E111
      if average_duration < self._target_cycle * 0.8:  # noqa: E111
        reduction_factor = min(
          2.0,
          (self._target_cycle / average_duration) * 0.5,
        )
        next_interval = max(
          self._min_interval,
          next_interval / max(1.0, reduction_factor * load_factor),
        )
      elif average_duration > self._target_cycle * 1.1:  # noqa: E111
        increase_factor = min(
          2.5,
          average_duration / self._target_cycle,
        )
        next_interval = min(
          self._max_interval,
          next_interval * (increase_factor * load_factor),
        )

      idle_candidate = self._entity_saturation < 0.1 and error_ratio < 0.01 and success  # noqa: E111
      if idle_candidate:  # noqa: E111
        idle_elapsed = now - self._last_activity
        if idle_elapsed >= self._idle_grace:
          ramp_target = max(  # noqa: E111
            next_interval,
            self._current_interval * 1.5,
          )
          next_interval = min(self._idle_interval, ramp_target)  # noqa: E111
        else:
          gentle_target = max(  # noqa: E111
            next_interval,
            self._current_interval * (1.0 + load_factor / 4),
          )
          next_interval = min(self._idle_interval, gentle_target)  # noqa: E111
      else:  # noqa: E111
        self._last_activity = now

    self._current_interval = max(
      self._min_interval,
      min(self._max_interval, next_interval),
    )
    return self._current_interval

  def as_diagnostics(self) -> AdaptivePollingDiagnostics:  # noqa: E111
    """Return diagnostics for adaptive polling behaviour."""

    history_count = len(self._history)
    average_duration = fmean(self._history) if history_count else 0.0
    diagnostics: AdaptivePollingDiagnostics = {
      "target_cycle_ms": round(self._target_cycle * 1000, 2),
      "current_interval_ms": round(self._current_interval * 1000, 2),
      "average_cycle_ms": round(average_duration * 1000, 2),
      "history_samples": history_count,
      "error_streak": self._error_streak,
      "entity_saturation": round(self._entity_saturation, 3),
      "idle_interval_ms": round(self._idle_interval * 1000, 2),
      "idle_grace_ms": round(self._idle_grace * 1000, 2),
    }
    return diagnostics


@dataclass(slots=True)
class RuntimeCycleInfo:
  """Summary of a coordinator update cycle."""  # noqa: E111

  dog_count: int  # noqa: E111
  errors: int  # noqa: E111
  success_rate: float  # noqa: E111
  duration: float  # noqa: E111
  new_interval: float  # noqa: E111
  error_ratio: float  # noqa: E111
  success: bool  # noqa: E111

  def to_dict(self) -> CoordinatorRuntimeCycleSnapshot:  # noqa: E111
    """Return a serialisable representation of the cycle."""

    snapshot: CoordinatorRuntimeCycleSnapshot = {
      "dog_count": self.dog_count,
      "errors": self.errors,
      "success_rate": round(self.success_rate * 100, 2),
      "duration_ms": round(self.duration * 1000, 2),
      "next_interval_s": round(self.new_interval, 3),
      "error_ratio": round(self.error_ratio, 3),
      "success": self.success,
    }
    return snapshot


def summarize_entity_budgets(
  snapshots: Iterable[EntityBudgetSnapshot],
) -> EntityBudgetSummary:
  """Summarise entity budget usage for diagnostics."""  # noqa: E111

  snapshots = list(snapshots)  # noqa: E111
  if not snapshots:  # noqa: E111
    return {
      "active_dogs": 0,
      "total_capacity": 0,
      "total_allocated": 0,
      "total_remaining": 0,
      "average_utilization": 0.0,
      "peak_utilization": 0.0,
      "denied_requests": 0,
    }

  total_capacity = sum(snapshot.capacity for snapshot in snapshots)  # noqa: E111
  total_allocated = sum(snapshot.total_allocated for snapshot in snapshots)  # noqa: E111
  total_remaining = sum(snapshot.remaining for snapshot in snapshots)  # noqa: E111
  denied_requests = sum(len(snapshot.denied_requests) for snapshot in snapshots)  # noqa: E111
  average_utilisation = (total_allocated / total_capacity) if total_capacity else 0.0  # noqa: E111
  peak_utilisation = max(  # noqa: E111
    (snapshot.saturation for snapshot in snapshots),
    default=0.0,
  )

  summary: EntityBudgetSummary = {  # noqa: E111
    "active_dogs": len(snapshots),
    "total_capacity": total_capacity,
    "total_allocated": total_allocated,
    "total_remaining": total_remaining,
    "average_utilization": round(average_utilisation * 100, 1),
    "peak_utilization": round(peak_utilisation * 100, 1),
    "denied_requests": denied_requests,
  }
  return summary  # noqa: E111


class CoordinatorRuntime:
  """Encapsulates the heavy lifting of coordinator update cycles."""  # noqa: E111

  def __init__(  # noqa: E111
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
    """Initialise the runtime executor with all required collaborators."""
    self._registry = registry
    self._modules = modules
    self._resilience = resilience_manager
    self._retry = retry_config
    self._metrics = metrics
    self._adaptive_polling = adaptive_polling
    self._logger = logger

  async def execute_cycle(  # noqa: E111
    self,
    dog_ids: Sequence[str],
    current_data: Mapping[str, CoordinatorDogData],
    *,
    empty_payload_factory: Callable[[], CoordinatorDogData],
  ) -> tuple[CoordinatorDataPayload, RuntimeCycleInfo]:
    """Fetch data for all configured dogs and return diagnostics."""

    if not dog_ids:
      raise CoordinatorUpdateFailed("No valid dogs configured")  # noqa: E111

    self._metrics.start_cycle()
    all_data: CoordinatorDataPayload = {}
    errors = 0
    cycle_start = time.perf_counter()

    async def fetch_and_store(dog_id: str) -> None:
      nonlocal errors  # noqa: E111

      try:  # noqa: E111
        result = await self._resilience.execute_with_resilience(
          self._fetch_dog_data,
          dog_id,
          circuit_breaker_name=f"dog_data_{dog_id}",
          retry_config=self._retry,
        )
      except ConfigEntryAuthFailed:  # noqa: E111
        errors += 1
        raise
      except RateLimitError as err:  # noqa: E111
        errors += 1
        self._logger.warning(
          "Rate limit reached for dog %s: %s",
          dog_id,
          err.user_message,
        )
        all_data[dog_id] = current_data.get(
          dog_id,
          empty_payload_factory(),
        )
      except NetworkError as err:  # noqa: E111
        errors += 1
        self._logger.warning(
          "Network error for dog %s: %s",
          dog_id,
          err.user_message,
        )
        all_data[dog_id] = current_data.get(
          dog_id,
          empty_payload_factory(),
        )
      except ValidationError as err:  # noqa: E111
        errors += 1
        self._logger.error(
          "Invalid configuration for dog %s: %s",
          dog_id,
          err,
        )
        all_data[dog_id] = empty_payload_factory()
      except Exception as err:  # noqa: E111
        errors += 1
        self._logger.error(
          "Resilience patterns exhausted for dog %s: %s (%s)",
          dog_id,
          err,
          err.__class__.__name__,
        )
        all_data[dog_id] = current_data.get(
          dog_id,
          empty_payload_factory(),
        )
      else:  # noqa: E111
        all_data[dog_id] = result

    try:
      async with asyncio.TaskGroup() as task_group:  # noqa: E111
        for dog_id in dog_ids:
          task_group.create_task(fetch_and_store(dog_id))  # noqa: E111
    except* ConfigEntryAuthFailed as auth_error_group:
      raise auth_error_group.exceptions[0] from auth_error_group  # noqa: E111
    except* Exception as error_group:  # pragma: no cover - defensive logging
      for exc in error_group.exceptions:  # noqa: E111
        self._logger.error("Task group error: %s", exc)

    total_dogs = len(dog_ids)
    success_rate, all_failed = self._metrics.record_cycle(
      total_dogs,
      errors,
    )

    if all_failed:
      raise CoordinatorUpdateFailed(  # noqa: E111
        f"All {total_dogs} dogs failed to update",
      )

    if success_rate < 0.5:
      self._logger.warning(  # noqa: E111
        "Low success rate: %d/%d dogs updated successfully",
        total_dogs - errors,
        total_dogs,
      )

    duration = max(time.perf_counter() - cycle_start, 0.0)
    error_ratio = errors / total_dogs if total_dogs else 0.0
    success = errors < total_dogs
    new_interval = self._adaptive_polling.record_cycle(
      duration=duration,
      success=errors == 0,
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

  async def _fetch_dog_data(self, dog_id: str) -> CoordinatorDogData:  # noqa: E111
    async with asyncio.timeout(API_TIMEOUT):
      dog_config = self._registry.get(dog_id)  # noqa: E111
      if not dog_config:  # noqa: E111
        raise ValidationError(
          "dog_id",
          dog_id,
          "Dog configuration not found",
        )

      payload: CoordinatorDogData = {  # noqa: E111
        "dog_info": dog_config,
        "status": "online",
        "last_update": dt_util.utcnow().isoformat(),
      }

      modules = ensure_dog_modules_mapping(dog_config)  # noqa: E111
      module_tasks: list[CoordinatorModuleTask] = self._modules.build_tasks(  # noqa: E111
        dog_id,
        modules,
      )
      if not module_tasks:  # noqa: E111
        return payload

      results = await asyncio.gather(  # noqa: E111
        *(task.coroutine for task in module_tasks),
        return_exceptions=True,
      )

      for task, result in zip(module_tasks, results, strict=True):  # noqa: E111
        module_name: CoordinatorTypedModuleName = task.module
        if isinstance(result, GPSUnavailableError):
          self._logger.debug(  # noqa: E111
            "GPS unavailable for %s: %s",
            dog_id,
            result,
          )
          payload[module_name] = cast(  # noqa: E111
            CoordinatorModuleErrorPayload,
            {
              "status": "unavailable",
              "reason": str(result),
            },
          )
        elif isinstance(result, RateLimitError):
          # Surface rate limits with retry hints for UI  # noqa: E114
          self._logger.warning(  # noqa: E111
            "Rate limit fetching %s data for %s: %s",
            module_name,
            dog_id,
            result.user_message,
          )
          payload[module_name] = cast(  # noqa: E111
            CoordinatorModuleErrorPayload,
            {
              "status": "rate_limited",
              "error": result.user_message,
              "retry_after": result.retry_after,
            },
          )
        elif isinstance(result, NetworkError):
          self._logger.warning(  # noqa: E111
            "Network error fetching %s data for %s: %s",
            module_name,
            dog_id,
            result,
          )
          payload[module_name] = cast(  # noqa: E111
            CoordinatorModuleErrorPayload,
            {
              "status": "network_error",
              "error": str(result),
            },
          )
        elif isinstance(result, Exception):
          self._logger.warning(  # noqa: E111
            "Failed to fetch %s data for %s: %s (%s)",
            module_name,
            dog_id,
            result,
            result.__class__.__name__,
          )
          payload[module_name] = cast(  # noqa: E111
            CoordinatorModuleErrorPayload,
            {
              "status": "error",
              "error": str(result),
              "error_type": result.__class__.__name__,
            },
          )
        else:
          payload[module_name] = cast(ModuleAdapterPayload, result)  # noqa: E111

      payload["status_snapshot"] = build_dog_status_snapshot(dog_id, payload)  # noqa: E111

      return payload  # noqa: E111
