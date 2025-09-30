"""Helper routines that keep the coordinator file compact."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .coordinator_runtime import summarize_entity_budgets

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from datetime import timedelta

    from .coordinator import PawControlCoordinator


def build_update_statistics(coordinator: PawControlCoordinator) -> dict[str, Any]:
    """Return lightweight update statistics for diagnostics endpoints."""

    cache_metrics = coordinator._modules.cache_metrics()
    stats = coordinator._metrics.update_statistics(
        cache_entries=cache_metrics.entries,
        cache_hit_rate=cache_metrics.hit_rate,
        last_update=coordinator.last_update_time,
        interval=coordinator.update_interval,
    )
    stats["entity_budget"] = summarize_entity_budgets(
        coordinator._entity_budget_snapshots
    )
    stats["adaptive_polling"] = coordinator._adaptive_polling.as_diagnostics()
    return stats


def build_runtime_statistics(coordinator: PawControlCoordinator) -> dict[str, Any]:
    """Return expanded statistics for diagnostics pages."""

    cache_metrics = coordinator._modules.cache_metrics()
    stats = coordinator._metrics.runtime_statistics(
        cache_metrics=cache_metrics,
        total_dogs=len(coordinator.registry),
        last_update=coordinator.last_update_time,
        interval=coordinator.update_interval,
    )
    stats["entity_budget"] = summarize_entity_budgets(
        coordinator._entity_budget_snapshots
    )
    stats["adaptive_polling"] = coordinator._adaptive_polling.as_diagnostics()
    stats["resilience"] = coordinator.resilience_manager.get_all_circuit_breakers()
    return stats


@callback
def ensure_background_task(
    coordinator: PawControlCoordinator, interval: timedelta
) -> None:
    """Start the maintenance task if not already running."""

    if coordinator._maintenance_unsub is None:
        coordinator._maintenance_unsub = async_track_time_interval(
            coordinator.hass, coordinator._async_maintenance, interval
        )


async def run_maintenance(coordinator: PawControlCoordinator) -> None:
    """Perform periodic maintenance work for caches and metrics."""

    now = dt_util.utcnow()
    expired = coordinator._modules.cleanup_expired(now)
    if expired:
        coordinator.logger().debug("Cleaned %d expired cache entries", expired)

    if coordinator._metrics.consecutive_errors > 0 and coordinator.last_update_success:
        hours_since_last_update = (
            now - (coordinator.last_update_time or now)
        ).total_seconds() / 3600
        if hours_since_last_update > 1:
            previous = coordinator._metrics.consecutive_errors
            coordinator._metrics.reset_consecutive()
            coordinator.logger().info(
                "Reset consecutive error count (%d) after %d hours of stability",
                previous,
                int(hours_since_last_update),
            )


async def shutdown(coordinator: PawControlCoordinator) -> None:
    """Shutdown hook for coordinator teardown."""

    if coordinator._maintenance_unsub:
        coordinator._maintenance_unsub()
        coordinator._maintenance_unsub = None

    coordinator._data.clear()
    coordinator._modules.clear_caches()
    coordinator.logger().info("Coordinator shutdown completed successfully")
