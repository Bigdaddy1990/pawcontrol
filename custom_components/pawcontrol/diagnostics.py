"""Diagnostics support for Paw Control."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "lat",
    "latitude", 
    "lon",
    "longitude",
    "gps",
    "location",
    "email",
    "phone",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
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
            dog_data["health"]["health_notes"] = f"[{len(dog_data['health']['health_notes'])} notes]"
        
        if "training" in dog_data and "training_history" in dog_data["training"]:
            dog_data["training"]["training_history"] = f"[{len(dog_data['training']['training_history'])} sessions]"
            
        if "grooming" in dog_data and "grooming_history" in dog_data["grooming"]:
            dog_data["grooming"]["grooming_history"] = f"[{len(dog_data['grooming']['grooming_history'])} sessions]"
        
        dogs_data[dog_id] = dog_data
    
    return async_redact_data(
        {
            "entry": {
                "entry_id": entry.entry_id,
                "version": entry.version,
                "domain": entry.domain,
                "title": entry.title,
                "options": entry.options,
                "pref_disable_new_entities": entry.pref_disable_new_entities,
                "pref_disable_polling": entry.pref_disable_polling,
                "source": entry.source,
                "unique_id": entry.unique_id,
                "disabled_by": entry.disabled_by,
            },
            "coordinator_data": {
                "visitor_mode": coordinator.visitor_mode,
                "emergency_mode": coordinator.emergency_mode,
                "emergency_level": coordinator.emergency_level,
                "dogs": dogs_data,
            },
            "integration_manifest": hass.data[DOMAIN].get("manifest", {}),
        },
        TO_REDACT,
    )
