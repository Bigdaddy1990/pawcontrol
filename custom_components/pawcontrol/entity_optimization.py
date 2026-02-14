"""Entity update optimization for PawControl integration.

This module provides utilities to minimize unnecessary entity updates and
state writes, reducing database load and improving performance.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

if TYPE_CHECKING:
  pass

_LOGGER = logging.getLogger(__name__)


@dataclass
class UpdateBatch:
  """Represents a batch of entity updates.

  Attributes:
      entities: List of entities to update
      timestamp: When batch was created
      scheduled: Whether update is scheduled
  """

  entities: set[str]
  timestamp: datetime
  scheduled: bool = False


class EntityUpdateBatcher:
  """Batches entity updates to reduce state writes.

  Instead of updating entities immediately, this collects updates
  over a short time window and processes them together.

  Examples:
      >>> batcher = EntityUpdateBatcher(hass, batch_window_ms=100)
      >>> await batcher.async_setup()
      >>> await batcher.schedule_update("sensor.dog_gps")
  """

  def __init__(
    self,
    hass: HomeAssistant,
    *,
    batch_window_ms: float = 100.0,
    max_batch_size: int = 50,
  ) -> None:
    """Initialize entity update batcher.

    Args:
        hass: Home Assistant instance
        batch_window_ms: Batch window in milliseconds
        max_batch_size: Maximum entities per batch
    """
    self._hass = hass
    self._batch_window_ms = batch_window_ms
    self._max_batch_size = max_batch_size
    self._pending: set[str] = set()
    self._batch_task: asyncio.Task[Any] | None = None
    self._entity_registry: dict[str, Any] = {}
    self._update_count = 0
    self._batch_count = 0

  async def async_setup(self) -> None:
    """Set up the batcher."""
    _LOGGER.debug("Entity update batcher initialized")

  def register_entity(self, entity_id: str, entity: Any) -> None:
    """Register an entity for batched updates.

    Args:
        entity_id: Entity ID
        entity: Entity instance
    """
    self._entity_registry[entity_id] = entity

  def unregister_entity(self, entity_id: str) -> None:
    """Unregister an entity.

    Args:
        entity_id: Entity ID
    """
    self._entity_registry.pop(entity_id, None)
    self._pending.discard(entity_id)

  async def schedule_update(self, entity_id: str) -> None:
    """Schedule an entity update.

    Args:
        entity_id: Entity ID to update
    """
    self._pending.add(entity_id)

    # Start batch task if not running
    if self._batch_task is None or self._batch_task.done():
      self._batch_task = asyncio.create_task(self._process_batch())

  async def _process_batch(self) -> None:
    """Process pending updates after batch window."""
    # Wait for batch window
    await asyncio.sleep(self._batch_window_ms / 1000)

    # Collect pending updates
    if not self._pending:
      return

    batch = list(self._pending)[: self._max_batch_size]
    self._pending.difference_update(batch)

    # Process batch
    for entity_id in batch:
      entity = self._entity_registry.get(entity_id)
      if entity and hasattr(entity, "async_write_ha_state"):
        try:
          entity.async_write_ha_state()
          self._update_count += 1
        except Exception as e:
          _LOGGER.error("Failed to update entity %s: %s", entity_id, e)

    self._batch_count += 1
    _LOGGER.debug(
      "Processed batch %d with %d entities (%d pending)",
      self._batch_count,
      len(batch),
      len(self._pending),
    )

    # Schedule next batch if more pending
    if self._pending:
      self._batch_task = asyncio.create_task(self._process_batch())

  def get_stats(self) -> dict[str, Any]:
    """Get batcher statistics.

    Returns:
        Statistics dictionary
    """
    return {
      "update_count": self._update_count,
      "batch_count": self._batch_count,
      "pending_updates": len(self._pending),
      "registered_entities": len(self._entity_registry),
      "avg_batch_size": (
        self._update_count / self._batch_count if self._batch_count > 0 else 0.0
      ),
    }


class SignificantChangeTracker:
  """Tracks significant changes to avoid redundant updates.

  Only triggers entity updates when values change significantly.

  Examples:
      >>> tracker = SignificantChangeTracker()
      >>> if tracker.is_significant_change("sensor.gps", 45.5231, 45.5232):
      ...   entity.async_write_ha_state()
  """

  def __init__(self) -> None:
    """Initialize significant change tracker."""
    self._last_values: dict[str, Any] = {}
    self._thresholds: dict[str, dict[str, Any]] = defaultdict(dict)

  def set_threshold(
    self,
    entity_id: str,
    attribute: str,
    *,
    absolute: float | None = None,
    percentage: float | None = None,
  ) -> None:
    """Set significance threshold for an attribute.

    Args:
        entity_id: Entity ID
        attribute: Attribute name
        absolute: Absolute change threshold
        percentage: Percentage change threshold (0.0-1.0)
    """
    key = f"{entity_id}.{attribute}"
    self._thresholds[key] = {
      "absolute": absolute,
      "percentage": percentage,
    }

  def is_significant_change(
    self,
    entity_id: str,
    attribute: str,
    new_value: Any,
    *,
    absolute_threshold: float | None = None,
    percentage_threshold: float | None = None,
  ) -> bool:
    """Check if change is significant.

    Args:
        entity_id: Entity ID
        attribute: Attribute name
        new_value: New value
        absolute_threshold: Override absolute threshold
        percentage_threshold: Override percentage threshold

    Returns:
        True if change is significant
    """
    key = f"{entity_id}.{attribute}"

    # First update is always significant
    if key not in self._last_values:
      self._last_values[key] = new_value
      return True

    old_value = self._last_values[key]

    # Different types always significant
    if type(old_value) != type(new_value):  # noqa: E721
      self._last_values[key] = new_value
      return True

    # Strings/bools: any change is significant
    if not isinstance(old_value, (int, float)):
      significant = old_value != new_value
      if significant:
        self._last_values[key] = new_value
      return significant

    # Numeric comparison
    thresholds = self._thresholds.get(key, {})
    abs_threshold = absolute_threshold or thresholds.get("absolute")
    pct_threshold = percentage_threshold or thresholds.get("percentage")

    # Absolute threshold
    if abs_threshold is not None and abs(new_value - old_value) < abs_threshold:
      return False

    # Percentage threshold
    if pct_threshold is not None and old_value != 0:
      change_pct = abs((new_value - old_value) / old_value)
      if change_pct < pct_threshold:
        return False

    # Change is significant
    self._last_values[key] = new_value
    return True

  def reset(self, entity_id: str | None = None) -> None:
    """Reset tracked values.

    Args:
        entity_id: Optional entity ID to reset (all if None)
    """
    if entity_id is None:
      self._last_values.clear()
    else:
      # Remove all keys for this entity
      keys_to_remove = [k for k in self._last_values if k.startswith(f"{entity_id}.")]
      for key in keys_to_remove:
        del self._last_values[key]


class EntityUpdateScheduler:
  """Schedules entity updates at optimal intervals.

  Different entity types update at different rates based on
  data volatility and user needs.

  Examples:
      >>> scheduler = EntityUpdateScheduler(hass)
      >>> await scheduler.async_setup()
      >>> scheduler.register_entity("sensor.gps", update_interval=30)
  """

  def __init__(self, hass: HomeAssistant) -> None:
    """Initialize entity update scheduler.

    Args:
        hass: Home Assistant instance
    """
    self._hass = hass
    self._entities: dict[str, dict[str, Any]] = {}
    self._intervals: dict[int, set[str]] = defaultdict(set)
    self._unsub_functions: list[Any] = []

  async def async_setup(self) -> None:
    """Set up the scheduler."""
    # Register common intervals
    for interval in [10, 30, 60, 300, 900]:
      self._setup_interval(interval)

  def _setup_interval(self, interval_seconds: int) -> None:
    """Set up update interval.

    Args:
        interval_seconds: Interval in seconds
    """

    @callback
    def update_entities(now: datetime) -> None:
      """Update entities at this interval."""
      entities = self._intervals.get(interval_seconds, set())
      for entity_id in entities:
        entity_data = self._entities.get(entity_id)
        if entity_data and entity_data.get("entity"):
          try:
            entity_data["entity"].async_write_ha_state()
          except Exception as e:
            _LOGGER.error("Failed to update entity %s: %s", entity_id, e)

    unsub = async_track_time_interval(
      self._hass,
      update_entities,
      timedelta(seconds=interval_seconds),
    )
    self._unsub_functions.append(unsub)

  def register_entity(
    self,
    entity_id: str,
    entity: Any,
    *,
    update_interval: int = 60,
  ) -> None:
    """Register entity for scheduled updates.

    Args:
        entity_id: Entity ID
        entity: Entity instance
        update_interval: Update interval in seconds
    """
    self._entities[entity_id] = {
      "entity": entity,
      "interval": update_interval,
    }
    self._intervals[update_interval].add(entity_id)

  def unregister_entity(self, entity_id: str) -> None:
    """Unregister entity.

    Args:
        entity_id: Entity ID
    """
    if entity_id in self._entities:
      interval = self._entities[entity_id]["interval"]
      self._intervals[interval].discard(entity_id)
      del self._entities[entity_id]

  def async_shutdown(self) -> None:
    """Shut down the scheduler."""
    for unsub in self._unsub_functions:
      unsub()
    self._unsub_functions.clear()

  def get_stats(self) -> dict[str, Any]:
    """Get scheduler statistics.

    Returns:
        Statistics dictionary
    """
    return {
      "total_entities": len(self._entities),
      "intervals": {
        f"{interval}s": len(entities) for interval, entities in self._intervals.items()
      },
    }


# Optimization decorators for entities


def skip_redundant_update(
  tracker: SignificantChangeTracker,
  attribute: str,
  **thresholds: Any,
) -> Any:
  """Decorator to skip redundant entity updates.

  Args:
      tracker: SignificantChangeTracker instance
      attribute: Attribute to track
      **thresholds: Threshold parameters

  Returns:
      Decorated method

  Examples:
      >>> tracker = SignificantChangeTracker()
      >>> class MySensor(SensorEntity):
      ...   @skip_redundant_update(tracker, "latitude", absolute=0.0001)
      ...   async def async_update(self):
      ...     self._attr_latitude = await get_latitude()
  """

  def decorator(func: Any) -> Any:
    async def wrapper(self: Any) -> Any:
      # Get old value
      old_value = getattr(self, f"_attr_{attribute}", None)

      # Call original update
      await func(self)

      # Get new value
      new_value = getattr(self, f"_attr_{attribute}", None)

      # Check significance
      if not tracker.is_significant_change(
        self.entity_id,
        attribute,
        new_value,
        **thresholds,
      ):
        # Restore old value to prevent state write
        setattr(self, f"_attr_{attribute}", old_value)

    return wrapper

  return decorator


# Helper functions


def calculate_optimal_update_interval(
  data_type: str,
  volatility: str = "medium",
) -> int:
  """Calculate optimal update interval for data type.

  Args:
      data_type: Type of data (gps, walk, feeding, etc.)
      volatility: Data volatility (low, medium, high)

  Returns:
      Optimal interval in seconds

  Examples:
      >>> interval = calculate_optimal_update_interval("gps", "high")
      >>> assert interval == 10
  """
  # Base intervals by data type
  base_intervals = {
    "gps": 30,
    "walk": 60,
    "feeding": 300,
    "health": 900,
    "weather": 900,
  }

  # Volatility multipliers
  multipliers = {
    "low": 2.0,
    "medium": 1.0,
    "high": 0.5,
  }

  base = base_intervals.get(data_type, 60)
  multiplier = multipliers.get(volatility, 1.0)

  return int(base * multiplier)


def estimate_state_write_reduction(
  update_count_before: int,
  update_count_after: int,
) -> dict[str, Any]:
  """Estimate state write reduction.

  Args:
      update_count_before: Updates before optimization
      update_count_after: Updates after optimization

  Returns:
      Reduction statistics
  """
  reduction = update_count_before - update_count_after
  reduction_pct = (
    (reduction / update_count_before * 100) if update_count_before > 0 else 0.0
  )

  return {
    "updates_before": update_count_before,
    "updates_after": update_count_after,
    "reduction": reduction,
    "reduction_percentage": round(reduction_pct, 1),
  }
