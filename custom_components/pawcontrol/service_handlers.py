"""Service handlers for Paw Control integration (mit Helper-Integration)."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    SERVICE_FOOD_TYPE,
    SERVICE_FOOD_AMOUNT,
    SERVICE_DURATION,
    SERVICE_WEIGHT,
    SERVICE_TEMPERATURE,
    SERVICE_ENERGY_LEVEL,
    SERVICE_SYMPTOMS,
    SERVICE_NOTES,
    SERVICE_MOOD,
    SERVICE_VET_DATE,
)
from .helpers.utils import UtilsHelper
from .helpers.datetime import DateTimeHelper
from .helpers.entity import EntityHelper

_LOGGER = logging.getLogger(__name__)

async def update_feeding_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update feeding-related entities using helpers."""
    try:
        utils_helper = UtilsHelper(hass)
        datetime_helper = DateTimeHelper(hass)
        entity_helper = EntityHelper(hass, dog_name)
        
        food_type = data.get(SERVICE_FOOD_TYPE, "morning")
        amount = data.get(SERVICE_FOOD_AMOUNT, 100)
        
        # Determine feeding time entity based on current time
        current_time = datetime_helper.get_current_datetime()
        if current_time.hour < 10:
            feeding_type = "morning"
        elif current_time.hour < 16:
            feeding_type = "lunch"
        else:
            feeding_type = "evening"
        
        # Update feeding boolean
        feeding_entity = entity_helper.get_entity_id("input_boolean", f"feeding_{feeding_type}")
        await utils_helper.safe_service_call("input_boolean", "turn_on", {"entity_id": feeding_entity})

        # Update counter
        counter_entity = entity_helper.get_entity_id("counter", f"feeding_{feeding_type}_count")
        await utils_helper.safe_service_call("counter", "increment", {"entity_id": counter_entity})

        # Update last feeding datetime
        datetime_entity = entity_helper.get_entity_id("input_datetime", f"last_feeding_{feeding_type}")
        await utils_helper.safe_service_call("input_datetime", "set_datetime", {
            "entity_id": datetime_entity,
            "datetime": current_time.isoformat()
        })
        
        _LOGGER.debug("Updated feeding entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating feeding entities for %s: %s", dog_name, e)

async def update_walk_start_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update entities when walk starts using helpers."""
    try:
        utils_helper = UtilsHelper(hass)
        datetime_helper = DateTimeHelper(hass)
        entity_helper = EntityHelper(hass, dog_name)
        
        # Set walk in progress
        walk_entity = entity_helper.get_entity_id("input_boolean", "walk_in_progress")
        await utils_helper.safe_service_call("input_boolean", "turn_on", {"entity_id": walk_entity})

        # Update walk start time
        datetime_entity = entity_helper.get_entity_id("input_datetime", "last_walk")
        current_time = datetime_helper.get_current_datetime()
        await utils_helper.safe_service_call("input_datetime", "set_datetime", {
            "entity_id": datetime_entity,
            "datetime": current_time.isoformat()
        })
        
        _LOGGER.debug("Updated walk start entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating walk start entities for %s: %s", dog_name, e)

async def update_walk_end_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update entities when walk ends using helpers."""
    try:
        utils_helper = UtilsHelper(hass)
        entity_helper = EntityHelper(hass, dog_name)
        
        # Turn off walk in progress
        walk_entity = entity_helper.get_entity_id("input_boolean", "walk_in_progress")
        await utils_helper.safe_service_call("input_boolean", "turn_off", {"entity_id": walk_entity})

        # Increment walk counter
        counter_entity = entity_helper.get_entity_id("counter", "walk_count")
        await utils_helper.safe_service_call("counter", "increment", {"entity_id": counter_entity})

        # Update walk duration if provided
        duration = data.get(SERVICE_DURATION)
        if duration:
            duration_entity = entity_helper.get_entity_id("input_number", "daily_walk_duration")
            await utils_helper.safe_service_call("input_number", "set_value", {
                "entity_id": duration_entity,
                "value": duration
            })
        
        _LOGGER.debug("Updated walk end entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating walk end entities for %s: %s", dog_name, e)

async def update_health_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update health-related entities using helpers."""
    try:
        utils_helper = UtilsHelper(hass)
        entity_helper = EntityHelper(hass, dog_name)
        
        # Update weight if provided
        if weight := data.get(SERVICE_WEIGHT):
            weight_entity = entity_helper.get_entity_id("input_number", "weight")
            await utils_helper.safe_service_call("input_number", "set_value", {
                "entity_id": weight_entity,
                "value": weight
            })

        # Update health notes if provided
        notes = data.get(SERVICE_NOTES)
        if notes:
            notes_entity = entity_helper.get_entity_id("input_text", "notes")
            await utils_helper.safe_service_call("input_text", "set_value", {
                "entity_id": notes_entity,
                "value": notes
            })
        
        _LOGGER.debug("Updated health entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating health entities for %s: %s", dog_name, e)

async def reset_all_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Reset all daily entities using helpers."""
    try:
        utils_helper = UtilsHelper(hass)
        entity_helper = EntityHelper(hass, dog_name)
        
        # Reset boolean entities
        boolean_entities = [
            "feeding_morning", "feeding_lunch", "feeding_evening",
            "walked_today", "outside", "medication_given"
        ]
        
        for entity_type in boolean_entities:
            entity_id = entity_helper.get_entity_id("input_boolean", entity_type)
            await utils_helper.safe_service_call("input_boolean", "turn_off", {"entity_id": entity_id})
        
        # Reset counters
        counter_entities = [
            "walk_count", "training_count", "playtime_count", "medication_count"
        ]
        
        for entity_type in counter_entities:
            entity_id = entity_helper.get_entity_id("counter", entity_type)
            await utils_helper.safe_service_call("counter", "reset", {"entity_id": entity_id})
        
        _LOGGER.info("Reset all entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error resetting entities for %s: %s", dog_name, e)

# GPS Entity Update Functions (mit GPS Helper)
async def update_gps_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update GPS-related entities using GPS helper."""
    try:
        from .helpers.gps import GPSHelper
        
        gps_helper = GPSHelper(hass)
        entity_helper = EntityHelper(hass, dog_name)
        
        latitude = data.get("latitude")
        longitude = data.get("longitude") 
        accuracy = data.get("accuracy", 0)
        
        # Validate coordinates using GPS helper
        if not await gps_helper.validate_coordinates(latitude, longitude):
            _LOGGER.error("Invalid GPS coordinates: %f, %f", latitude, longitude)
            return
        
        # Update location using GPS helper
        await gps_helper.update_location(dog_name, latitude, longitude, accuracy)
        
        _LOGGER.debug("Updated GPS entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating GPS entities for %s: %s", dog_name, e)
