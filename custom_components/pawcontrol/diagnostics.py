"""Diagnostics support for Paw Control."""

from __future__ import annotations

from copy import deepcopy
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


def _sanitize_dog_data(dog_data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of dog data with sensitive fields redacted."""
    data = deepcopy(dog_data)

    if "location" in data:
        data["location"] = {
            "is_home": data["location"].get("is_home", True),
            "current_location": "REDACTED",
        }

    if "health" in data and "health_notes" in data["health"]:
        data["health"]["health_notes"] = (
            f"[{len(data['health']['health_notes'])} notes]"
        )

    if "training" in data and "training_history" in data["training"]:
        data["training"]["training_history"] = (
            f"[{len(data['training']['training_history'])} sessions]"
        )

    if "grooming" in data and "grooming_history" in data["grooming"]:
        data["grooming"]["grooming_history"] = (
            f"[{len(data['grooming']['grooming_history'])} sessions]"
        )

    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = getattr(
        getattr(entry, "runtime_data", None),
        "coordinator",
        hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator"),
    )

    dogs_data = {}
    for dog_id in getattr(coordinator, "_dog_data", {}):
        dogs_data[dog_id] = _sanitize_dog_data(
            coordinator.get_dog_data(dog_id)
        )

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
