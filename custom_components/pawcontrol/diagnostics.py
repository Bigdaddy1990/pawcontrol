"""Diagnostics support for Paw Control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

try:  # pragma: no cover - Home Assistant provides these in runtime
    from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
except Exception:  # pragma: no cover - tests without full Home Assistant
    CONF_PASSWORD = "password"
    CONF_USERNAME = "username"

from .const import DOMAIN

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "lat",
    "latitude",
    "lon",
    "longitude",
    "gps",
    "email",
    "phone",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = getattr(
        getattr(entry, "runtime_data", None),
        "coordinator",
        hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator"),
    )

    # Get all dog data but redact sensitive information
    dogs_data = {}
    for dog_id in coordinator._dog_data:
        dog_data = coordinator.get_dog_data(dog_id).copy()

        # Remove location data
        if "location" in dog_data:
            dog_data["location"] = {
                "is_home": dog_data["location"].get("is_home", True),
                "current_location": "REDACTED",
            }

        # Remove any notes that might contain personal info
        if "health" in dog_data and "health_notes" in dog_data["health"]:
            dog_data["health"]["health_notes"] = (
                f"[{len(dog_data['health']['health_notes'])} notes]"
            )

        if "training" in dog_data and "training_history" in dog_data["training"]:
            dog_data["training"]["training_history"] = (
                f"[{len(dog_data['training']['training_history'])} sessions]"
            )

        if "grooming" in dog_data and "grooming_history" in dog_data["grooming"]:
            dog_data["grooming"]["grooming_history"] = (
                f"[{len(dog_data['grooming']['grooming_history'])} sessions]"
            )

        dogs_data[dog_id] = dog_data

    return async_redact_data(
        {
            "entry": {
                "entry_id": getattr(entry, "entry_id", ""),
                "version": getattr(entry, "version", 1),
                "domain": getattr(entry, "domain", DOMAIN),
                "title": getattr(entry, "title", ""),
                "options": getattr(entry, "options", {}),
                "pref_disable_new_entities": getattr(
                    entry, "pref_disable_new_entities", False
                ),
                "pref_disable_polling": getattr(entry, "pref_disable_polling", False),
                "source": getattr(entry, "source", ""),
                "unique_id": getattr(entry, "unique_id", None),
                "disabled_by": getattr(entry, "disabled_by", None),
            },
            "coordinator": {
                "visitor_mode": getattr(coordinator, "visitor_mode", False),
                "emergency_mode": getattr(coordinator, "emergency_mode", False),
                "emergency_level": getattr(coordinator, "emergency_level", 0),
            },
            "dogs": dogs_data,
            "integration_manifest": hass.data[DOMAIN].get("manifest", {}),
        },
        TO_REDACT,
    )
