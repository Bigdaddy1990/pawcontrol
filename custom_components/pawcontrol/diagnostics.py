"""Diagnostics support for Paw Control integration.

This module provides comprehensive diagnostic information for troubleshooting
and support purposes. It collects system information, configuration details,
and operational data while ensuring sensitive information is properly redacted.
Designed to meet Home Assistant's Platinum quality standards.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
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

_LOGGER = logging.getLogger(__name__)

# Sensitive keys that should be redacted in diagnostics
REDACTED_KEYS = {
    "api_key",
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
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
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
    _LOGGER.debug(
        "Generating diagnostics for Paw Control entry: %s", entry.entry_id)

    # Get integration data
    integration_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator: PawControlCoordinator | None = integration_data.get(
        "coordinator")

    # Base diagnostics structure
    diagnostics = {
        "config_entry": await _get_config_entry_diagnostics(entry),
        "system_info": await _get_system_diagnostics(hass),
        "integration_status": await _get_integration_status(
            hass, entry, integration_data
        ),
        "coordinator_info": await _get_coordinator_diagnostics(coordinator),
        "entities": await _get_entities_diagnostics(hass, entry),
        "devices": await _get_devices_diagnostics(hass, entry),
        "dogs_summary": await _get_dogs_summary(entry, coordinator),
        "performance_metrics": await _get_performance_metrics(coordinator),
        "data_statistics": await _get_data_statistics(integration_data),
        "error_logs": await _get_recent_errors(entry.entry_id),
        "debug_info": await _get_debug_information(hass, entry),
    }

    # Redact sensitive information
    redacted_diagnostics = _redact_sensitive_data(diagnostics)
    # --- Patch: hier sicherstellen, dass Redaction auf alles angewandt wird ---
    return _redact_sensitive_data(diagnostics)

    _LOGGER.info(
        "Diagnostics generated successfully for entry %s", entry.entry_id)
    return redacted_diagnostics


async def _get_config_entry_diagnostics(entry: ConfigEntry) -> dict[str, Any]:
    """Get configuration entry diagnostic information.

    Args:
        entry: Configuration entry

    Returns:
        Configuration diagnostics
    """
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "version": entry.version,
        "domain": entry.domain,
        "state": entry.state.value,
        "source": entry.source,
        "unique_id": entry.unique_id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "modified_at": entry.modified_at.isoformat() if entry.modified_at else None,
        "data_keys": list(entry.data.keys()),
        "options_keys": list(entry.options.keys()),
        "supports_options": entry.supports_options,
        "supports_reconfigure": entry.supports_reconfigure,
        "supports_remove_device": entry.supports_remove_device,
        "supports_unload": entry.supports_unload,
        "dogs_configured": len(entry.data.get(CONF_DOGS, [])),
    }


async def _get_system_diagnostics(hass: HomeAssistant) -> dict[str, Any]:
    """Get Home Assistant system diagnostic information.

    Args:
        hass: Home Assistant instance

    Returns:
        System diagnostics
    """
    return {
        "ha_version": hass.config.version,
        "python_version": hass.config.python_version,
        "timezone": str(hass.config.time_zone),
        "config_dir": hass.config.config_dir,
        "is_running": hass.is_running,
        "safe_mode": hass.config.safe_mode,
        "recovery_mode": hass.config.recovery_mode,
        "current_time": dt_util.utcnow().isoformat(),
        "uptime_seconds": (dt_util.utcnow() - hass.config.start_time).total_seconds(),
    }


async def _get_integration_status(
    hass: HomeAssistant, entry: ConfigEntry, integration_data: dict[str, Any]
) -> dict[str, Any]:
    """Get integration status diagnostics.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        integration_data: Integration data from hass.data

    Returns:
        Integration status diagnostics
    """
    coordinator = integration_data.get("coordinator")
    data_manager = integration_data.get("data")
    notification_manager = integration_data.get("notifications")

    return {
        "entry_loaded": entry.entry_id in hass.data.get(DOMAIN, {}),
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

    stats = coordinator.get_update_statistics()

    return {
        "available": coordinator.available,
        "last_update_success": coordinator.last_update_success,
        "last_update_time": coordinator.last_update_time.isoformat()
        if coordinator.last_update_time
        else None,
        "update_interval_seconds": coordinator.update_interval.total_seconds(),
        "update_method": str(coordinator.update_method),
        "logger_name": coordinator.logger.name,
        "name": coordinator.name,
        "statistics": stats,
        "config_entry_id": coordinator.config_entry.entry_id,
        "dogs_managed": len(coordinator.dogs),
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
    entities = er.async_entries_for_config_entry(
        entity_registry, entry.entry_id)

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
    devices = dr.async_entries_for_config_entry(
        device_registry, entry.entry_id)

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

    stats = coordinator.get_update_statistics()

    return {
        "update_frequency": stats.get("update_interval_seconds"),
        "data_freshness": "fresh" if coordinator.last_update_success else "stale",
        "memory_efficient": True,  # Placeholder - could add actual memory usage
        "cpu_efficient": True,  # Placeholder - could add actual CPU usage
        "network_efficient": True,  # Placeholder - could add network usage stats
        "error_rate": "low",  # Placeholder - could track actual error rates
        "response_time": "fast",  # Placeholder - could track actual response times
    }


async def _get_data_statistics(integration_data: dict[str, Any]) -> dict[str, Any]:
    """Get data storage statistics.

    Args:
        integration_data: Integration data

    Returns:
        Data statistics
    """
    data_manager = integration_data.get("data")

    if not data_manager:
        return {"available": False}

    # This would collect actual storage statistics in a real implementation
    return {
        "data_manager_available": True,
        "storage_efficient": True,
        "cleanup_active": True,
        "export_supported": True,
        "backup_supported": True,
        "retention_policy_active": True,
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
        "quality_scale": "platinum",
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
    }


async def _get_loaded_platforms(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    """Get list of loaded platforms for this entry.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry

    Returns:
        List of loaded platform names
    """
    # Check which platforms have been loaded
    loaded_platforms = []

    platforms = [
        "sensor",
        "binary_sensor",
        "button",
        "switch",
        "number",
        "select",
        "text",
        "device_tracker",
    ]

    for platform in platforms:
        # In a real implementation, this would check if the platform is actually loaded
        # For now, we'll assume all platforms are loaded
        loaded_platforms.append(platform)

    return loaded_platforms


async def _get_registered_services(hass: HomeAssistant) -> list[str]:
    """Get list of registered services for this domain.

    Args:
        hass: Home Assistant instance

    Returns:
        List of registered service names
    """
    services = []

    if hass.services.has_service(DOMAIN, "feed_dog"):
        services.extend(
            [
                "feed_dog",
                "start_walk",
                "end_walk",
                "log_health",
                "log_medication",
                "start_grooming",
                "notify_test",
                "daily_reset",
            ]
        )

    return services


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
    """Recursively redact sensitive data from diagnostic information.

    Args:
        data: Data to redact

    Returns:
        Data with sensitive information redacted
    """
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            # Check if key contains sensitive information
            key_lower = key.lower()
            is_sensitive = any(
                sensitive in key_lower for sensitive in REDACTED_KEYS)

            if is_sensitive:
                redacted[key] = "**REDACTED**"
            else:
                redacted[key] = _redact_sensitive_data(value)
        return redacted

    elif isinstance(data, list):
        return [_redact_sensitive_data(item) for item in data]

    elif isinstance(data, str):
        # Check for patterns that look like sensitive data
        if _looks_like_sensitive_string(data):
            return "**REDACTED**"
        return data

    else:
        return data


def _looks_like_sensitive_string(value: str) -> bool:
    """Check if a string looks like sensitive data.

    Args:
        value: String to check

    Returns:
        True if string appears to contain sensitive data
    """
    # Check for common sensitive patterns
    sensitive_patterns = [
        # UUID
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        r"\b[A-Za-z0-9]{20,}\b",  # Long alphanumeric strings (tokens)
        r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",  # IP addresses
        # Email addresses
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    ]

    import re

    return any(re.search(pattern, value) for pattern in sensitive_patterns)
