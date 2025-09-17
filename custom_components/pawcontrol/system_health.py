"""System health support for the PawControl integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


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
    api_calls = stats["performance_metrics"].get("api_calls", 0)

    if coordinator.use_external_api:
        quota = entry.options.get("external_api_quota")
        remaining_quota: int | str
        if isinstance(quota, int) and quota >= 0:
            remaining_quota = max(quota - api_calls, 0)
        else:
            remaining_quota = "untracked"
    else:
        remaining_quota = "unlimited"

    return {
        "can_reach_backend": coordinator.last_update_success,
        "remaining_quota": remaining_quota,
    }


def _async_get_first_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the first loaded PawControl config entry."""

    return next(iter(hass.config_entries.async_entries(DOMAIN)), None)


def _async_resolve_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> Any | None:
    """Resolve the coordinator for system health lookups."""

    runtime = getattr(entry, "runtime_data", None)
    if runtime and getattr(runtime, "coordinator", None) is not None:
        return runtime.coordinator

    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return None

    if (entry_store := domain_data.get(entry.entry_id)) and isinstance(
        entry_store, dict
    ):
        coordinator = entry_store.get("coordinator")
        if coordinator is not None:
            return coordinator

        runtime = entry_store.get("runtime_data")
        if runtime and getattr(runtime, "coordinator", None) is not None:
            return runtime.coordinator

    return domain_data.get("coordinator")
