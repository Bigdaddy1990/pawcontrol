"""System health support for Paw Control."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import IntegrationNotFound, async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(async_system_health_info)


async def async_system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Get system health information."""
    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = integration.version or "unknown"
    except IntegrationNotFound:
        version = "unknown"
    entries = hass.config_entries.async_entries(DOMAIN)

    health_info = {
        "version": version,
        "entries": len(entries),
    }

    # Add detailed information for each entry
    for entry in entries:
        runtime_data = getattr(entry, "runtime_data", None)
        if not runtime_data:
            continue

        coordinator = getattr(runtime_data, "coordinator", None)
        if not coordinator:
            continue

        # Get dogs count and active modules
        dogs_count = len(entry.options.get("dogs", []))
        active_modules = set()

        for dog in entry.options.get("dogs", []):
            modules = dog.get("dog_modules", {})
            for module, enabled in modules.items():
                if enabled:
                    active_modules.add(module)

        # Get coordinator health
        coordinator_health = (
            "healthy" if coordinator.last_update_success else "unhealthy"
        )
        last_update = (
            coordinator.last_update_time.isoformat()
            if hasattr(coordinator, "last_update_time")
            else "never"
        )

        # Get GPS handler status
        gps_handler = getattr(runtime_data, "gps_handler", None)
        gps_status = "not_configured"
        active_walks = 0

        if gps_handler:
            gps_status = "active"
            # Count active walks
            for dog_id in coordinator._dog_data:
                dog_data = coordinator.get_dog_data(dog_id)
                if dog_data and dog_data.get("walk", {}).get("is_walking"):
                    active_walks += 1

        # Storage status
        route_store = getattr(runtime_data, "route_store", None)
        storage_status = "active" if route_store else "not_configured"

        # Notification status
        notification_router = getattr(runtime_data, "notification_router", None)
        notification_status = "active" if notification_router else "not_configured"

        entry_info = {
            f"entry_{entry.entry_id[:8]}": {
                "dogs": dogs_count,
                "active_modules": (
                    ", ".join(sorted(active_modules)) if active_modules else "none"
                ),
                "coordinator": coordinator_health,
                "last_update": last_update,
                "gps": gps_status,
                "active_walks": active_walks,
                "storage": storage_status,
                "notifications": notification_status,
                "visitor_mode": (
                    coordinator.visitor_mode
                    if hasattr(coordinator, "visitor_mode")
                    else False
                ),
                "emergency_mode": (
                    coordinator.emergency_mode
                    if hasattr(coordinator, "emergency_mode")
                    else False
                ),
            }
        }

        health_info.update(entry_info)

    # Check for common issues
    if not entries:
        health_info["setup_status"] = "not_configured"
    else:
        all_healthy = all(
            getattr(getattr(entry, "runtime_data", None), "coordinator", None)
            and getattr(
                getattr(entry, "runtime_data", None), "coordinator", None
            ).last_update_success
            for entry in entries
        )
        health_info["setup_status"] = "healthy" if all_healthy else "needs_attention"

    # Add system recommendations
    recommendations = []

    for entry in entries:
        if not entry.options.get("notify_fallback"):
            recommendations.append("Configure notification service for alerts")

        if not any(
            dog.get("dog_modules", {}).get("module_gps")
            for dog in entry.options.get("dogs", [])
        ):
            recommendations.append("Enable GPS module for walk tracking")

        if len(entry.options.get("dogs", [])) == 0:
            recommendations.append("Add at least one dog to the integration")

    if recommendations:
        health_info["recommendations"] = " | ".join(
            recommendations[:3]
        )  # Limit to 3 recommendations

    return health_info
