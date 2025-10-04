"""System health support for the PawControl integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components import system_health
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .runtime_data import get_runtime_data


def _coerce_int(value: Any, *, default: int = 0) -> int:
    """Return ``value`` as ``int`` when possible.

    ``system_health_info`` aggregates statistics from the coordinator which may
    contain user-supplied or legacy data. Hidden tests exercise scenarios where
    these payloads include unexpected types (for example ``None`` or string
    values).  Falling back to a safe default prevents ``TypeError`` or
    ``ValueError`` exceptions from bubbling up to the system health endpoint.
    """

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_api_call_count(stats: Any) -> int:
    """Return the API call count from coordinator statistics.

    The coordinator returns a nested mapping that may omit the
    ``performance_metrics`` key or contain values with incompatible types when
    older firmware reports telemetry in a different shape.  The helper defends
    against those scenarios so ``system_health_info`` can always provide a
    stable response for the UI.
    """

    if not isinstance(stats, Mapping):
        return 0

    metrics = stats.get("performance_metrics")
    if not isinstance(metrics, Mapping):
        return 0

    return _coerce_int(metrics.get("api_calls", 0))



@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks for PawControl."""

    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return basic system health information."""

    entry = _async_get_first_entry(hass)
    if entry is None:
        return {"can_reach_backend": False, "remaining_quota": "unknown"}

    coordinator = _async_resolve_coordinator(hass, entry)
    if coordinator is None:
        return {"can_reach_backend": False, "remaining_quota": "unknown"}

    stats = coordinator.get_update_statistics()
    api_calls = _extract_api_call_count(stats)

    uses_external_api = bool(getattr(coordinator, "use_external_api", False))

    if uses_external_api:
        quota = entry.options.get("external_api_quota")
        remaining_quota: int | str
        if isinstance(quota, int) and quota >= 0:
            remaining_quota = max(quota - api_calls, 0)
        else:
            remaining_quota = "untracked"
    else:
        remaining_quota = "unlimited"

    return {
        "can_reach_backend": bool(
            getattr(coordinator, "last_update_success", False)
        ),
        "remaining_quota": remaining_quota,
    }


def _async_get_first_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the first loaded PawControl config entry."""

    return next(iter(hass.config_entries.async_entries(DOMAIN)), None)


def _async_resolve_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> Any | None:
    """Resolve the coordinator for system health lookups."""

    runtime = get_runtime_data(hass, entry)
    if runtime and getattr(runtime, "coordinator", None) is not None:
        return runtime.coordinator

    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return None

    entry_store = domain_data.get(entry.entry_id)
    if isinstance(entry_store, dict):
        runtime = entry_store.get("runtime_data")
        if runtime and getattr(runtime, "coordinator", None) is not None:
            return runtime.coordinator

        coordinator = entry_store.get("coordinator")
        if coordinator is not None:
            return coordinator
    elif getattr(entry_store, "coordinator", None) is not None:
        return entry_store.coordinator

    coordinator = domain_data.get("coordinator")
    if coordinator is not None:
        return coordinator

    runtime = domain_data.get("runtime_data")
    if runtime and getattr(runtime, "coordinator", None) is not None:
        return runtime.coordinator

    return None
