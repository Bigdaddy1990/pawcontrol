"""Entity update optimization for PawControl integration.

This module provides utilities to minimize unnecessary entity updates and
state writes, reducing database load and improving performance.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

if TYPE_CHECKING:
    pass  # noqa: E111

_LOGGER = logging.getLogger(__name__)


@dataclass
class UpdateBatch:
    """Represents a batch of entity updates.

    Attributes:
        entities: List of entities to update
        timestamp: When batch was created
        scheduled: Whether update is scheduled
    """  # noqa: E111

    entities: set[str]  # noqa: E111
    timestamp: datetime  # noqa: E111
    scheduled: bool = False  # noqa: E111


class EntityUpdateBatcher:
    """Batches entity updates to reduce state writes.

    Instead of updating entities immediately, this collects updates
    over a short time window and processes them together.

    Examples:
        >>> batcher = EntityUpdateBatcher(hass, batch_window_ms=100)
        >>> await batcher.async_setup()
        >>> await batcher.schedule_update("sensor.dog_gps")
    """  # noqa: E111

    def __init__(  # noqa: E111
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

    async def async_setup(self) -> None:  # noqa: E111
        """Set up the batcher."""
        _LOGGER.debug("Entity update batcher initialized")

    def register_entity(self, entity_id: str, entity: Any) -> None:  # noqa: E111
        """Register an entity for batched updates.

        Args:
            entity_id: Entity ID
            entity: Entity instance
        """
        self._entity_registry[entity_id] = entity

    def unregister_entity(self, entity_id: str) -> None:  # noqa: E111
        """Unregister an entity.

        Args:
            entity_id: Entity ID
        """
        self._entity_registry.pop(entity_id, None)
        self._pending.discard(entity_id)

    async def schedule_update(self, entity_id: str) -> None:  # noqa: E111
        """Schedule an entity update.

        Args:
            entity_id: Entity ID to update
        """
        self._pending.add(entity_id)

        # Start batch task if not running
        if self._batch_task is None or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._process_batch())  # noqa: E111

    async def _process_batch(self) -> None:  # noqa: E111
        """Process pending updates after batch window."""
        # Wait for batch window
        await asyncio.sleep(self._batch_window_ms / 1000)

        # Collect pending updates
        if not self._pending:
            return  # noqa: E111

        batch = list(self._pending)[: self._max_batch_size]
        self._pending.difference_update(batch)

        # Process batch
        for entity_id in batch:
            entity = self._entity_registry.get(entity_id)  # noqa: E111
            if entity and hasattr(entity, "async_write_ha_state"):  # noqa: E111
                try:
                    entity.async_write_ha_state()  # noqa: E111
                    self._update_count += 1  # noqa: E111
                except Exception as e:
                    _LOGGER.error("Failed to update entity %s: %s", entity_id, e)  # noqa: E111

        self._batch_count += 1
        _LOGGER.debug(
            "Processed batch %d with %d entities (%d pending)",
            self._batch_count,
            len(batch),
            len(self._pending),
        )

        # Schedule next batch if more pending
        if self._pending:
            self._batch_task = asyncio.create_task(self._process_batch())  # noqa: E111

    def get_stats(self) -> dict[str, Any]:  # noqa: E111
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
        ...     entity.async_write_ha_state()
    """  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        """Initialize significant change tracker."""
        self._last_values: dict[str, Any] = {}
        self._thresholds: dict[str, dict[str, Any]] = defaultdict(dict)

    def set_threshold(  # noqa: E111
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

    def is_significant_change(  # noqa: E111
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
            self._last_values[key] = new_value  # noqa: E111
            return True  # noqa: E111

        old_value = self._last_values[key]

        # Different types always significant
        if not isinstance(new_value, type(old_value)):
            self._last_values[key] = new_value  # noqa: E111
            return True  # noqa: E111

        # Strings/bools: any change is significant
        if not isinstance(old_value, (int, float)):
            significant = old_value != new_value  # noqa: E111
            if significant:  # noqa: E111
                self._last_values[key] = new_value
            return significant  # noqa: E111

        # Numeric comparison
        thresholds = self._thresholds.get(key, {})
        abs_threshold = absolute_threshold or thresholds.get("absolute")
        pct_threshold = percentage_threshold or thresholds.get("percentage")

        # Absolute threshold
        if abs_threshold is not None and abs(new_value - old_value) < abs_threshold:
            return False  # noqa: E111

        # Percentage threshold
        if pct_threshold is not None and old_value != 0:
            change_pct = abs((new_value - old_value) / old_value)  # noqa: E111
            if change_pct < pct_threshold:  # noqa: E111
                return False

        # Change is significant
        self._last_values[key] = new_value
        return True

    def reset(self, entity_id: str | None = None) -> None:  # noqa: E111
        """Reset tracked values.

        Args:
            entity_id: Optional entity ID to reset (all if None)
        """
        if entity_id is None:
            self._last_values.clear()  # noqa: E111
        else:
            # Remove all keys for this entity  # noqa: E114
            keys_to_remove = [
                k for k in self._last_values if k.startswith(f"{entity_id}.")
            ]  # noqa: E111
            for key in keys_to_remove:  # noqa: E111
                del self._last_values[key]


class EntityUpdateScheduler:
    """Schedules entity updates at optimal intervals.

    Different entity types update at different rates based on
    data volatility and user needs.

    Examples:
        >>> scheduler = EntityUpdateScheduler(hass)
        >>> await scheduler.async_setup()
        >>> scheduler.register_entity("sensor.gps", update_interval=30)
    """  # noqa: E111

    def __init__(self, hass: HomeAssistant) -> None:  # noqa: E111
        """Initialize entity update scheduler.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._entities: dict[str, dict[str, Any]] = {}
        self._intervals: dict[int, set[str]] = defaultdict(set)
        self._unsub_functions: list[Any] = []

    async def async_setup(self) -> None:  # noqa: E111
        """Set up the scheduler."""
        # Register common intervals
        for interval in [10, 30, 60, 300, 900]:
            self._setup_interval(interval)  # noqa: E111

    def _setup_interval(self, interval_seconds: int) -> None:  # noqa: E111
        """Set up update interval.

        Args:
            interval_seconds: Interval in seconds
        """

        @callback
        def update_entities(now: datetime) -> None:
            """Update entities at this interval."""  # noqa: E111
            entities = self._intervals.get(interval_seconds, set())  # noqa: E111
            for entity_id in entities:  # noqa: E111
                entity_data = self._entities.get(entity_id)
                if entity_data and entity_data.get("entity"):
                    try:  # noqa: E111
                        entity_data["entity"].async_write_ha_state()
                    except Exception as e:  # noqa: E111
                        _LOGGER.error("Failed to update entity %s: %s", entity_id, e)

        unsub = async_track_time_interval(
            self._hass,
            update_entities,
            timedelta(seconds=interval_seconds),
        )
        self._unsub_functions.append(unsub)

    def register_entity(  # noqa: E111
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

    def unregister_entity(self, entity_id: str) -> None:  # noqa: E111
        """Unregister entity.

        Args:
            entity_id: Entity ID
        """
        if entity_id in self._entities:
            interval = self._entities[entity_id]["interval"]  # noqa: E111
            self._intervals[interval].discard(entity_id)  # noqa: E111
            del self._entities[entity_id]  # noqa: E111

    def async_shutdown(self) -> None:  # noqa: E111
        """Shut down the scheduler."""
        for unsub in self._unsub_functions:
            unsub()  # noqa: E111
        self._unsub_functions.clear()

    def get_stats(self) -> dict[str, Any]:  # noqa: E111
        """Get scheduler statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_entities": len(self._entities),
            "intervals": {
                f"{interval}s": len(entities)
                for interval, entities in self._intervals.items()
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
        ...     @skip_redundant_update(tracker, "latitude", absolute=0.0001)
        ...     async def async_update(self):
        ...         self._attr_latitude = await get_latitude()
    """  # noqa: E111

    def decorator(func: Any) -> Any:  # noqa: E111
        async def wrapper(self: Any) -> Any:
            # Get old value  # noqa: E114
            old_value = getattr(self, f"_attr_{attribute}", None)  # noqa: E111

            # Call original update  # noqa: E114
            await func(self)  # noqa: E111

            # Get new value  # noqa: E114
            new_value = getattr(self, f"_attr_{attribute}", None)  # noqa: E111

            # Check significance  # noqa: E114
            if not tracker.is_significant_change(  # noqa: E111
                self.entity_id,
                attribute,
                new_value,
                **thresholds,
            ):
                # Restore old value to prevent state write
                setattr(self, f"_attr_{attribute}", old_value)

        return wrapper

    return decorator  # noqa: E111


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
    """  # noqa: E111
    # Base intervals by data type  # noqa: E114
    base_intervals = {  # noqa: E111
        "gps": 30,
        "walk": 60,
        "feeding": 300,
        "health": 900,
        "weather": 900,
    }

    # Volatility multipliers  # noqa: E114
    multipliers = {  # noqa: E111
        "low": 2.0,
        "medium": 1.0,
        "high": 0.5,
    }

    base = base_intervals.get(data_type, 60)  # noqa: E111
    multiplier = multipliers.get(volatility, 1.0)  # noqa: E111

    return int(base * multiplier)  # noqa: E111


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
    """  # noqa: E111
    reduction = update_count_before - update_count_after  # noqa: E111
    reduction_pct = (  # noqa: E111
        (reduction / update_count_before * 100) if update_count_before > 0 else 0.0
    )

    return {  # noqa: E111
        "updates_before": update_count_before,
        "updates_after": update_count_after,
        "reduction": reduction,
        "reduction_percentage": round(reduction_pct, 1),
    }
