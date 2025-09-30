"""Helper routines that keep the coordinator file compact."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .coordinator_runtime import summarize_entity_budgets
from .coordinator_support import UpdateResult
from .exceptions import GPSUnavailableError, NetworkError, ValidationError

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from datetime import timedelta

    from .coordinator import PawControlCoordinator


async def fetch_all_dogs(
    coordinator: PawControlCoordinator, dog_ids: list[str]
) -> UpdateResult:
    """Fetch all dog payloads with resilience handling."""

    result = UpdateResult()
    tasks = [coordinator._fetch_with_resilience(dog_id) for dog_id in dog_ids]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for dog_id, response in zip(dog_ids, responses, strict=True):
        if isinstance(response, ConfigEntryAuthFailed):
            raise response

        if isinstance(response, ValidationError):
            coordinator.logger().error(
                "Invalid configuration for dog %s: %s", dog_id, response
            )
            result.add_error(dog_id, coordinator.registry.empty_payload())
            continue

        if isinstance(response, Exception):
            coordinator.logger().error(
                "Resilience exhausted for dog %s: %s (%s)",
                dog_id,
                response,
                response.__class__.__name__,
            )
            result.add_error(
                dog_id,
                coordinator._data.get(dog_id, coordinator.registry.empty_payload()),
            )
            continue

        result.add_success(dog_id, response)

    return result


async def fetch_single_dog(
    coordinator: PawControlCoordinator, dog_id: str
) -> dict[str, Any]:
    """Fetch data for a single dog across all modules."""

    dog_config = coordinator.registry.get(dog_id)
    if not dog_config:
        raise ValidationError("dog_id", dog_id, "Dog configuration not found")

    payload = {
        "dog_info": dog_config,
        "status": "online",
        "last_update": dt_util.utcnow().isoformat(),
    }

    modules = dog_config.get("modules", {})
    module_tasks = coordinator._modules.build_tasks(dog_id, modules)
    if not module_tasks:
        return payload

    results = await asyncio.gather(
        *(task for _, task in module_tasks), return_exceptions=True
    )

    for (module_name, _), result in zip(module_tasks, results, strict=True):
        if isinstance(result, GPSUnavailableError):
            coordinator.logger().debug("GPS unavailable for %s: %s", dog_id, result)
            payload[module_name] = {"status": "unavailable", "reason": str(result)}
        elif isinstance(result, NetworkError):
            coordinator.logger().warning(
                "Network error fetching %s data for %s: %s",
                module_name,
                dog_id,
                result,
            )
            payload[module_name] = {"status": "network_error"}
        elif isinstance(result, Exception):
            coordinator.logger().warning(
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
    coordinator: PawControlCoordinator, interval: "timedelta"
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
