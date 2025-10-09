"""Helper routines that keep the coordinator file compact."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .performance import (
    capture_cache_diagnostics,
    performance_tracker,
    record_maintenance_result,
)
from .runtime_data import get_runtime_data
from .telemetry import (
    get_runtime_reconfigure_summary,
    summarise_reconfigure_options,
    update_runtime_reconfigure_summary,
)
from .types import CacheRepairAggregate, ReconfigureTelemetrySummary

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from datetime import timedelta

    from .coordinator import PawControlCoordinator


def _fetch_cache_repair_summary(
    coordinator: PawControlCoordinator,
) -> CacheRepairAggregate | None:
    """Return the latest cache repair aggregate for coordinator telemetry."""

    runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)
    if runtime_data is None:
        return None

    data_manager = getattr(runtime_data, "data_manager", None)
    if data_manager is None:
        return None

    summary_method = getattr(data_manager, "cache_repair_summary", None)
    if not callable(summary_method):
        return None

    try:
        summary = summary_method()
    except Exception as err:  # pragma: no cover - diagnostics guard
        coordinator.logger.debug("Failed to collect cache repair summary: %s", err)
        return None

    if summary is None:
        return None

    if isinstance(summary, Mapping):
        return cast(CacheRepairAggregate, dict(summary))

    coordinator.logger.debug(
        "Unexpected cache repair summary payload type: %s",
        type(summary).__name__,
    )
    return None


def _fetch_reconfigure_summary(
    coordinator: PawControlCoordinator,
) -> ReconfigureTelemetrySummary | None:
    """Return the latest reconfigure summary for coordinator telemetry."""

    runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)
    if runtime_data is not None:
        summary = get_runtime_reconfigure_summary(runtime_data)
        if summary is None:
            summary = update_runtime_reconfigure_summary(runtime_data)
        if summary is not None:
            return summary

    options = getattr(coordinator.config_entry, "options", None)
    return summarise_reconfigure_options(options)


def build_update_statistics(coordinator: PawControlCoordinator) -> dict[str, Any]:
    """Return lightweight update statistics for diagnostics endpoints."""

    cache_metrics = coordinator._modules.cache_metrics()
    repair_summary = _fetch_cache_repair_summary(coordinator)
    reconfigure_summary = _fetch_reconfigure_summary(coordinator)
    stats = coordinator._metrics.update_statistics(
        cache_entries=cache_metrics.entries,
        cache_hit_rate=cache_metrics.hit_rate,
        last_update=coordinator.last_update_time,
        interval=coordinator.update_interval,
        repair_summary=repair_summary,
    )
    stats["entity_budget"] = coordinator._entity_budget.summary()
    stats["adaptive_polling"] = coordinator._adaptive_polling.as_diagnostics()
    if reconfigure_summary is not None:
        stats["reconfigure"] = reconfigure_summary
    return stats


def build_runtime_statistics(coordinator: PawControlCoordinator) -> dict[str, Any]:
    """Return expanded statistics for diagnostics pages."""

    cache_metrics = coordinator._modules.cache_metrics()
    repair_summary = _fetch_cache_repair_summary(coordinator)
    reconfigure_summary = _fetch_reconfigure_summary(coordinator)
    stats = coordinator._metrics.runtime_statistics(
        cache_metrics=cache_metrics,
        total_dogs=len(coordinator.registry),
        last_update=coordinator.last_update_time,
        interval=coordinator.update_interval,
        repair_summary=repair_summary,
    )
    stats["entity_budget"] = coordinator._entity_budget.summary()
    stats["adaptive_polling"] = coordinator._adaptive_polling.as_diagnostics()
    stats["resilience"] = coordinator.resilience_manager.get_all_circuit_breakers()
    if reconfigure_summary is not None:
        stats["reconfigure"] = reconfigure_summary
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

    runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)
    now = dt_util.utcnow()

    diagnostics = None
    metadata = {
        "schedule": "hourly",
        "runtime_available": runtime_data is not None,
    }
    details: dict[str, Any] = {}

    with performance_tracker(
        runtime_data,
        "analytics_collector_metrics",
        max_samples=50,
    ) as perf:
        try:
            expired = coordinator._modules.cleanup_expired(now)
            if expired:
                coordinator.logger.debug("Cleaned %d expired cache entries", expired)
                details["expired_entries"] = expired

            if (
                coordinator._metrics.consecutive_errors > 0
                and coordinator.last_update_success
            ):
                hours_since_last_update = (
                    now - (coordinator.last_update_time or now)
                ).total_seconds() / 3600
                if hours_since_last_update > 1:
                    previous = coordinator._metrics.consecutive_errors
                    coordinator._metrics.reset_consecutive()
                    coordinator.logger.info(
                        "Reset consecutive error count (%d) after %d hours of stability",
                        previous,
                        int(hours_since_last_update),
                    )
                    details["consecutive_errors_reset"] = previous
                    details["hours_since_last_update"] = round(
                        hours_since_last_update, 2
                    )

            diagnostics = capture_cache_diagnostics(runtime_data)
            if diagnostics is not None:
                details["cache_snapshot"] = True

            record_maintenance_result(
                runtime_data,
                task="coordinator_maintenance",
                status="success",
                diagnostics=diagnostics,
                metadata=metadata,
                details=details,
            )
        except Exception as err:
            perf.mark_failure(err)
            if diagnostics is None:
                diagnostics = capture_cache_diagnostics(runtime_data)
            record_maintenance_result(
                runtime_data,
                task="coordinator_maintenance",
                status="error",
                message=str(err),
                diagnostics=diagnostics,
                metadata=metadata,
                details=details,
            )
            raise


async def shutdown(coordinator: PawControlCoordinator) -> None:
    """Shutdown hook for coordinator teardown."""

    if coordinator._maintenance_unsub:
        coordinator._maintenance_unsub()
        coordinator._maintenance_unsub = None

    coordinator._data.clear()
    coordinator._modules.clear_caches()
    coordinator.logger.info("Coordinator shutdown completed successfully")
