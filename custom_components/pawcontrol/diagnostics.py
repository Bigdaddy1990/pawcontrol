"""Diagnostics support for Paw Control integration.

This module provides comprehensive diagnostic information for troubleshooting
and support purposes. It collects system information, configuration details,
and operational data while ensuring sensitive information is properly redacted.
The current focus is reaching the Home Assistant Bronze quality baseline.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry, ConfigEntryState
from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .coordinator_tasks import default_rejection_metrics
from .diagnostics_redaction import compile_redaction_patterns, redact_sensitive_data
from .runtime_data import get_runtime_data
from .types import (
    CacheDiagnosticsMap,
    CacheDiagnosticsSnapshot,
    PawControlConfigEntry,
    PawControlRuntimeData,
)

_LOGGER = logging.getLogger(__name__)

# Sensitive keys that should be redacted in diagnostics
REDACTED_KEYS = {
    "api_key",
    "api_token",
    "password",
    "token",
    "secret",
    "webhook_url",
    "email",
    "phone",
    "address",
    "latitude",
    "longitude",
    "coordinates",
    "gps_position",
    "location",
    "personal_info",
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
}

_REDACTED_KEY_PATTERNS = compile_redaction_patterns(REDACTED_KEYS)


def _entity_registry_entries_for_config_entry(
    entity_registry: er.EntityRegistry, entry_id: str
) -> list[er.RegistryEntry]:
    """Return registry entries associated with a config entry."""

    module_helper = getattr(er, "async_entries_for_config_entry", None)
    if callable(module_helper):
        return list(module_helper(entity_registry, entry_id))

    entities = getattr(entity_registry, "entities", {})
    return [
        entry
        for entry in entities.values()
        if getattr(entry, "config_entry_id", None) == entry_id
    ]


def _device_registry_entries_for_config_entry(
    device_registry: dr.DeviceRegistry, entry_id: str
) -> list[dr.DeviceEntry]:
    """Return device registry entries associated with a config entry."""

    module_helper = getattr(dr, "async_entries_for_config_entry", None)
    if callable(module_helper):
        return list(module_helper(device_registry, entry_id))

    devices = getattr(device_registry, "devices", {})
    return [
        entry
        for entry in devices.values()
        if getattr(entry, "config_entry_id", None) == entry_id
        or (
            isinstance(getattr(entry, "config_entries", None), set)
            and entry_id in entry.config_entries
        )
    ]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PawControlConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    This function collects comprehensive diagnostic information including
    configuration details, system status, entity information, and operational
    metrics while ensuring sensitive data is properly redacted.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry to diagnose

    Returns:
        Dictionary containing diagnostic information
    """
    _LOGGER.debug("Generating diagnostics for Paw Control entry: %s", entry.entry_id)

    # Get runtime data using the shared helper (runtime adoption still being proven)
    runtime_data = get_runtime_data(hass, entry)
    coordinator = runtime_data.coordinator if runtime_data else None

    # Base diagnostics structure
    cache_snapshots = _collect_cache_diagnostics(runtime_data)

    diagnostics = {
        "config_entry": await _get_config_entry_diagnostics(entry),
        "system_info": await _get_system_diagnostics(hass),
        "integration_status": await _get_integration_status(hass, entry, runtime_data),
        "coordinator_info": await _get_coordinator_diagnostics(coordinator),
        "entities": await _get_entities_diagnostics(hass, entry),
        "devices": await _get_devices_diagnostics(hass, entry),
        "dogs_summary": await _get_dogs_summary(entry, coordinator),
        "performance_metrics": await _get_performance_metrics(coordinator),
        "data_statistics": await _get_data_statistics(runtime_data, cache_snapshots),
        "error_logs": await _get_recent_errors(entry.entry_id),
        "debug_info": await _get_debug_information(hass, entry),
    }

    if cache_snapshots is not None:
        diagnostics["cache_diagnostics"] = cache_snapshots

    # Redact sensitive information
    redacted_diagnostics = _redact_sensitive_data(diagnostics)

    _LOGGER.info("Diagnostics generated successfully for entry %s", entry.entry_id)
    return redacted_diagnostics


async def _get_config_entry_diagnostics(entry: ConfigEntry) -> dict[str, Any]:
    """Get configuration entry diagnostic information.

    Args:
        entry: Configuration entry

    Returns:
        Configuration diagnostics
    """
    version = getattr(entry, "version", None)
    state = getattr(entry, "state", None)
    if isinstance(state, ConfigEntryState):
        state_value: str | None = state.value
    elif state is None:
        state_value = None
    else:
        state_value = str(state)

    created_at = getattr(entry, "created_at", None)
    modified_at = getattr(entry, "modified_at", None)

    supports_options = getattr(entry, "supports_options", False)
    supports_reconfigure = getattr(entry, "supports_reconfigure", False)
    supports_remove_device = getattr(entry, "supports_remove_device", False)
    supports_unload = getattr(entry, "supports_unload", False)

    return {
        "entry_id": entry.entry_id,
        "title": getattr(entry, "title", entry.entry_id),
        "version": version,
        "domain": entry.domain,
        "state": state_value,
        "source": getattr(entry, "source", None),
        "unique_id": getattr(entry, "unique_id", None),
        "created_at": created_at.isoformat() if created_at else None,
        "modified_at": modified_at.isoformat() if modified_at else None,
        "data_keys": list(entry.data.keys()),
        "options_keys": list(getattr(entry, "options", {})),
        "supports_options": supports_options,
        "supports_reconfigure": supports_reconfigure,
        "supports_remove_device": supports_remove_device,
        "supports_unload": supports_unload,
        "dogs_configured": len(entry.data.get(CONF_DOGS, [])),
    }


async def _get_system_diagnostics(hass: HomeAssistant) -> dict[str, Any]:
    """Get Home Assistant system diagnostic information.

    Args:
        hass: Home Assistant instance

    Returns:
        System diagnostics
    """
    config = hass.config
    time_zone = getattr(config, "time_zone", None)
    safe_mode = getattr(config, "safe_mode", False)
    recovery_mode = getattr(config, "recovery_mode", False)
    start_time = getattr(config, "start_time", None)
    uptime_seconds: float | None = None
    if start_time:
        uptime_seconds = (dt_util.utcnow() - start_time).total_seconds()

    return {
        "ha_version": getattr(config, "version", None),
        "python_version": getattr(config, "python_version", None),
        "timezone": str(time_zone) if time_zone else None,
        "config_dir": getattr(config, "config_dir", None),
        "is_running": getattr(hass, "is_running", False),
        "safe_mode": safe_mode,
        "recovery_mode": recovery_mode,
        "current_time": dt_util.utcnow().isoformat(),
        "uptime_seconds": uptime_seconds,
    }


def _collect_cache_diagnostics(
    runtime_data: PawControlRuntimeData | None,
) -> CacheDiagnosticsMap | None:
    """Return cache diagnostics captured by the data manager when available."""

    if runtime_data is None:
        return None

    data_manager = getattr(runtime_data, "data_manager", None)
    if data_manager is None:
        return None

    snapshot_method = getattr(data_manager, "cache_snapshots", None)
    if not callable(snapshot_method):
        return None

    try:
        raw_snapshots = snapshot_method()
    except Exception as err:  # pragma: no cover - defensive guard
        _LOGGER.debug("Unable to collect cache diagnostics: %s", err)
        return None

    if isinstance(raw_snapshots, Mapping):
        snapshots = dict(raw_snapshots)
    elif isinstance(raw_snapshots, dict):
        snapshots = raw_snapshots
    else:
        _LOGGER.debug(
            "Unexpected cache diagnostics payload type: %s",
            type(raw_snapshots).__name__,
        )
        return None

    normalised: CacheDiagnosticsMap = {}
    for name, payload in snapshots.items():
        if not isinstance(name, str) or not name:
            _LOGGER.debug(
                "Skipping cache diagnostics entry with invalid name: %s", name
            )
            continue

        normalised[name] = _normalise_cache_snapshot(payload)

    return normalised or None


def _normalise_cache_snapshot(payload: Any) -> CacheDiagnosticsSnapshot:
    """Coerce arbitrary cache payloads into diagnostics-friendly snapshots."""

    if isinstance(payload, Mapping):
        mapping_payload = dict(payload)
    else:
        return cast(
            CacheDiagnosticsSnapshot,
            {
                "error": f"Unsupported diagnostics payload: {type(payload).__name__}",
                "snapshot": {"value": _normalise_json(payload)},
            },
        )

    snapshot: CacheDiagnosticsSnapshot = {}

    stats = mapping_payload.get("stats")
    if stats is not None:
        snapshot["stats"] = cast(dict[str, Any], _normalise_json(stats))

    diagnostics = mapping_payload.get("diagnostics")
    if diagnostics is not None:
        snapshot["diagnostics"] = cast(
            dict[str, Any],
            _normalise_json(diagnostics),
        )

    details = mapping_payload.get("snapshot")
    if details is not None:
        snapshot["snapshot"] = cast(dict[str, Any], _normalise_json(details))

    error = mapping_payload.get("error")
    if isinstance(error, str):
        snapshot["error"] = error

    if not snapshot:
        snapshot["snapshot"] = {"value": _normalise_json(mapping_payload)}

    return snapshot


def _normalise_json(value: Any) -> Any:
    """Normalise diagnostics payloads into JSON-serialisable data."""

    if isinstance(value, Mapping):
        return {str(key): _normalise_json(item) for key, item in value.items()}

    if isinstance(value, list | tuple | set | frozenset | Sequence) and not isinstance(
        value, str | bytes | bytearray
    ):
        return [_normalise_json(item) for item in value]

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, int | float | str | bool) or value is None:
        return value

    if isinstance(value, timedelta):
        return value.total_seconds()

    return repr(value)


async def _get_integration_status(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime_data: PawControlRuntimeData | None,
) -> dict[str, Any]:
    """Get integration status diagnostics.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        runtime_data: Runtime data from entry

    Returns:
        Integration status diagnostics
    """
    if runtime_data:
        coordinator = runtime_data.coordinator
        data_manager = getattr(runtime_data, "data_manager", None)
        notification_manager = getattr(runtime_data, "notification_manager", None)
    else:
        coordinator = None
        data_manager = None
        notification_manager = None

    entry_loaded = entry.state is ConfigEntryState.LOADED

    return {
        "entry_loaded": entry_loaded,
        "coordinator_available": coordinator is not None,
        "coordinator_success": coordinator.last_update_success
        if coordinator
        else False,
        "coordinator_last_update": coordinator.last_update_time.isoformat()
        if coordinator and coordinator.last_update_time
        else None,
        "data_manager_available": data_manager is not None,
        "notification_manager_available": notification_manager is not None,
        "platforms_loaded": await _get_loaded_platforms(hass, entry),
        "services_registered": await _get_registered_services(hass),
        "setup_completed": True,  # If we're here, setup completed
    }


async def _get_coordinator_diagnostics(
    coordinator: PawControlCoordinator | None,
) -> dict[str, Any]:
    """Get coordinator diagnostic information.

    Args:
        coordinator: Data coordinator instance

    Returns:
        Coordinator diagnostics
    """
    if not coordinator:
        return {"available": False, "reason": "Coordinator not initialized"}

    try:
        stats = coordinator.get_update_statistics()
    except Exception as err:
        _LOGGER.debug("Could not get coordinator statistics: %s", err)
        stats = {}

    return {
        "available": coordinator.available,
        "last_update_success": coordinator.last_update_success,
        "last_update_time": coordinator.last_update_time.isoformat()
        if coordinator.last_update_time
        else None,
        "update_interval_seconds": coordinator.update_interval.total_seconds(),
        "update_method": str(coordinator.update_method)
        if hasattr(coordinator, "update_method")
        else "unknown",
        "logger_name": coordinator.logger.name,
        "name": coordinator.name,
        "statistics": stats,
        "config_entry_id": coordinator.config_entry.entry_id,
        "dogs_managed": len(getattr(coordinator, "dogs", [])),
    }


async def _get_entities_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Get entities diagnostic information.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry

    Returns:
        Entities diagnostics
    """
    entity_registry = er.async_get(hass)

    # Get all entities for this integration
    entities = _entity_registry_entries_for_config_entry(
        entity_registry, entry.entry_id
    )

    # Group entities by platform
    entities_by_platform: dict[str, list[dict[str, Any]]] = {}

    for entity in entities:
        platform = entity.platform
        if platform not in entities_by_platform:
            entities_by_platform[platform] = []

        entity_info = {
            "entity_id": entity.entity_id,
            "unique_id": entity.unique_id,
            "platform": entity.platform,
            "device_id": entity.device_id,
            "disabled": entity.disabled,
            "disabled_by": entity.disabled_by.value if entity.disabled_by else None,
            "hidden": entity.hidden,
            "entity_category": entity.entity_category.value
            if entity.entity_category
            else None,
            "has_entity_name": entity.has_entity_name,
            "original_name": entity.original_name,
            "capabilities": entity.capabilities,
        }

        # Get current state
        state = hass.states.get(entity.entity_id)
        if state:
            entity_info.update(
                {
                    "state": state.state,
                    "available": state.state != "unavailable",
                    "last_changed": state.last_changed.isoformat(),
                    "last_updated": state.last_updated.isoformat(),
                    "attributes_count": len(state.attributes),
                }
            )

        entities_by_platform[platform].append(entity_info)

    return {
        "total_entities": len(entities),
        "entities_by_platform": entities_by_platform,
        "platform_counts": {
            platform: len(entities)
            for platform, entities in entities_by_platform.items()
        },
        "disabled_entities": len([e for e in entities if e.disabled]),
        "hidden_entities": len([e for e in entities if e.hidden]),
    }


async def _get_devices_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Get devices diagnostic information.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry

    Returns:
        Devices diagnostics
    """
    device_registry = dr.async_get(hass)

    # Get all devices for this integration
    devices = _device_registry_entries_for_config_entry(device_registry, entry.entry_id)

    devices_info = []
    for device in devices:
        device_info = {
            "id": device.id,
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.sw_version,
            "hw_version": device.hw_version,
            "via_device_id": device.via_device_id,
            "disabled": device.disabled,
            "disabled_by": device.disabled_by.value if device.disabled_by else None,
            "entry_type": device.entry_type.value if device.entry_type else None,
            "identifiers": list(device.identifiers),
            "connections": list(device.connections),
            "configuration_url": device.configuration_url,
        }
        devices_info.append(device_info)

    return {
        "total_devices": len(devices),
        "devices": devices_info,
        "disabled_devices": len([d for d in devices if d.disabled]),
    }


async def _get_dogs_summary(
    entry: ConfigEntry, coordinator: PawControlCoordinator | None
) -> dict[str, Any]:
    """Get summary of configured dogs.

    Args:
        entry: Configuration entry
        coordinator: Data coordinator

    Returns:
        Dogs summary diagnostics
    """
    dogs = entry.data.get(CONF_DOGS, [])

    dogs_summary = []
    for dog in dogs:
        dog_id = dog[CONF_DOG_ID]
        dog_summary = {
            "dog_id": dog_id,
            "dog_name": dog[CONF_DOG_NAME],
            "dog_breed": dog.get("dog_breed", ""),
            "dog_age": dog.get("dog_age"),
            "dog_weight": dog.get("dog_weight"),
            "dog_size": dog.get("dog_size"),
            "enabled_modules": dog.get("modules", {}),
            "module_count": len(
                [m for m, enabled in dog.get("modules", {}).items() if enabled]
            ),
        }

        # Add coordinator data if available
        if coordinator:
            try:
                dog_data = coordinator.get_dog_data(dog_id)
                if dog_data:
                    dog_summary.update(
                        {
                            "coordinator_data_available": True,
                            "last_activity": dog_data.get("last_update"),
                            "status": dog_data.get("status"),
                        }
                    )
                else:
                    dog_summary["coordinator_data_available"] = False
            except Exception as err:
                _LOGGER.debug(
                    "Could not get coordinator data for dog %s: %s", dog_id, err
                )
                dog_summary["coordinator_data_available"] = False

        dogs_summary.append(dog_summary)

    return {
        "total_dogs": len(dogs),
        "dogs": dogs_summary,
        "module_usage": _calculate_module_usage(dogs),
    }


async def _get_performance_metrics(
    coordinator: PawControlCoordinator | None,
) -> dict[str, Any]:
    """Get performance metrics.

    Args:
        coordinator: Data coordinator

    Returns:
        Performance metrics
    """
    if not coordinator:
        return {"available": False}

    try:
        stats = coordinator.get_update_statistics()
        error_rate = 0.0
        total_updates = stats.get("total_updates")
        if total_updates:
            error_rate = stats.get("failed", 0) / total_updates

        rejection_metrics = default_rejection_metrics()
        rejection_payload = stats.get("rejection_metrics")
        if isinstance(rejection_payload, Mapping):
            rejected_raw = rejection_payload.get("rejected_call_count")
            if isinstance(rejected_raw, int):
                rejection_metrics["rejected_call_count"] = rejected_raw

            breaker_count_raw = rejection_payload.get("rejection_breaker_count")
            if isinstance(breaker_count_raw, int):
                rejection_metrics["rejection_breaker_count"] = breaker_count_raw

            rate_raw = rejection_payload.get("rejection_rate")
            if isinstance(rate_raw, int | float):
                rejection_metrics["rejection_rate"] = float(rate_raw)

            time_raw = rejection_payload.get("last_rejection_time")
            if isinstance(time_raw, int | float):
                rejection_metrics["last_rejection_time"] = float(time_raw)

            breaker_id_raw = rejection_payload.get("last_rejection_breaker_id")
            if isinstance(breaker_id_raw, str):
                rejection_metrics["last_rejection_breaker_id"] = breaker_id_raw

            breaker_name_raw = rejection_payload.get("last_rejection_breaker_name")
            if isinstance(breaker_name_raw, str):
                rejection_metrics["last_rejection_breaker_name"] = breaker_name_raw

            schema_raw = rejection_payload.get("schema_version")
            if schema_raw == 1:
                rejection_metrics["schema_version"] = 1
        stats["rejection_metrics"] = rejection_metrics

        performance_metrics = stats.get("performance_metrics")
        if isinstance(performance_metrics, dict):
            performance_metrics.update(
                {
                    key: value
                    for key, value in rejection_metrics.items()
                    if key != "schema_version"
                }
            )

        return {
            "update_frequency": stats.get("update_interval"),
            "data_freshness": "fresh" if coordinator.last_update_success else "stale",
            "memory_efficient": True,  # Placeholder - could add actual memory usage
            "cpu_efficient": True,  # Placeholder - could add actual CPU usage
            "network_efficient": True,  # Placeholder - could add network usage stats
            "error_rate": error_rate,
            "response_time": "fast",  # Placeholder - could track actual response times
            "rejection_metrics": rejection_metrics,
            "statistics": stats,
        }
    except Exception as err:
        _LOGGER.debug("Could not get performance metrics: %s", err)
        return {"available": False, "error": str(err)}


async def _get_data_statistics(
    runtime_data: PawControlRuntimeData | None,
    cache_snapshots: CacheDiagnosticsMap | None,
) -> dict[str, Any]:
    """Get data storage statistics.

    Args:
        runtime_data: Runtime data

    Returns:
        Data statistics
    """
    if runtime_data is None:
        return {"available": False}

    data_manager = getattr(runtime_data, "data_manager", None)
    if data_manager is None:
        return {"available": False}

    metrics_payload: dict[str, Any] | None = None
    metrics_method = getattr(data_manager, "get_metrics", None)
    if callable(metrics_method):
        try:
            metrics_payload = metrics_method()
        except Exception as err:  # pragma: no cover - defensive guard
            _LOGGER.debug("Failed to gather data manager metrics: %s", err)

    if isinstance(metrics_payload, Mapping):
        metrics = {
            str(key): _normalise_json(value) for key, value in metrics_payload.items()
        }
    else:
        metrics = {}

    if cache_snapshots is None:
        cache_payload = _collect_cache_diagnostics(runtime_data)
    else:
        cache_payload = cache_snapshots

    if cache_payload is not None:
        metrics["cache_diagnostics"] = cache_payload

    metrics.setdefault("dogs", len(getattr(runtime_data, "dogs", [])))

    return {
        "data_manager_available": True,
        "metrics": metrics,
    }


async def _get_recent_errors(entry_id: str) -> list[dict[str, Any]]:
    """Get recent error logs for this integration.

    Args:
        entry_id: Configuration entry ID

    Returns:
        List of recent error information
    """
    # In a real implementation, this would collect actual error logs
    # from the Home Assistant logging system
    return [
        {
            "note": "Error collection not implemented in this version",
            "suggestion": "Check Home Assistant logs for detailed error information",
            "entry_id": entry_id,
        }
    ]


async def _get_debug_information(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Get debug information.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry

    Returns:
        Debug information
    """

    return {
        "debug_logging_enabled": _LOGGER.isEnabledFor(logging.DEBUG),
        "integration_version": "1.0.0",
        "quality_scale": "bronze",
        "supported_features": [
            "config_flow",
            "options_flow",
            "diagnostics",
            "repairs",
            "device_registry",
            "entity_registry",
            "services",
            "events",
            "multi_dog_support",
            "gps_tracking",
            "health_monitoring",
            "feeding_tracking",
            "notifications",
        ],
        "documentation_url": "https://github.com/BigDaddy1990/pawcontrol",
        "issue_tracker": "https://github.com/BigDaddy1990/pawcontrol/issues",
        "entry_id": entry.entry_id,
        "ha_version": hass.config.version,
    }


async def _get_loaded_platforms(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    """Get list of loaded platforms for this entry.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry

    Returns:
        List of loaded platform names
    """
    # Check which platforms have been loaded by checking entity registry
    entity_registry = er.async_get(hass)
    entities = _entity_registry_entries_for_config_entry(
        entity_registry, entry.entry_id
    )

    # Get unique platforms
    loaded_platforms = list(set(entity.platform for entity in entities))

    return loaded_platforms


async def _get_registered_services(hass: HomeAssistant) -> list[str]:
    """Get list of registered services for this domain.

    Args:
        hass: Home Assistant instance

    Returns:
        List of registered service names
    """
    domain_services = hass.services.async_services().get(DOMAIN, {})

    return list(domain_services.keys())


def _calculate_module_usage(dogs: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate module usage statistics across all dogs.

    Args:
        dogs: List of dog configurations

    Returns:
        Module usage statistics
    """
    module_counts = {
        MODULE_FEEDING: 0,
        MODULE_WALK: 0,
        MODULE_GPS: 0,
        MODULE_HEALTH: 0,
        MODULE_NOTIFICATIONS: 0,
    }

    total_dogs = len(dogs)

    for dog in dogs:
        modules = dog.get("modules", {})
        for module in module_counts:
            if modules.get(module, False):
                module_counts[module] += 1

    # Calculate percentages
    module_percentages = {}
    for module, count in module_counts.items():
        percentage = (count / total_dogs * 100) if total_dogs > 0 else 0
        module_percentages[f"{module}_percentage"] = round(percentage, 1)

    return {
        "counts": module_counts,
        "percentages": module_percentages,
        "most_used_module": max(module_counts, key=module_counts.get)
        if module_counts
        else None,
        "least_used_module": min(module_counts, key=module_counts.get)
        if module_counts
        else None,
    }


def _redact_sensitive_data(data: Any) -> Any:
    """Recursively redact sensitive data from diagnostic information."""

    return redact_sensitive_data(data, patterns=_REDACTED_KEY_PATTERNS)
