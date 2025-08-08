"""Service registration for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    SERVICE_FEED_DOG,
    SERVICE_START_WALK,
    SERVICE_END_WALK,
    SERVICE_LOG_HEALTH,
    SERVICE_UPDATE_GPS,
    SERVICE_SET_MOOD,
    SERVICE_LOG_MEDICATION,
    SERVICE_EMERGENCY,
    SERVICE_RESET_DATA,
    MOOD_OPTIONS,
    WALK_TYPES,
)

_LOGGER = logging.getLogger(__name__)

# Service schemas
FEED_DOG_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Optional("meal_type", default="auto"): vol.In(["breakfast", "lunch", "dinner", "snack", "auto"]),
    vol.Optional("amount"): vol.Coerce(float),
    vol.Optional("food_type"): cv.string,
    vol.Optional("notes"): cv.string,
})

START_WALK_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Optional("walk_type", default="Normal"): vol.In(WALK_TYPES),
    vol.Optional("location"): cv.string,
    vol.Optional("with_gps", default=False): cv.boolean,
})

END_WALK_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Required("duration"): vol.Coerce(int),  # minutes
    vol.Optional("distance"): vol.Coerce(float),  # km
    vol.Optional("rating"): vol.In([1, 2, 3, 4, 5]),
    vol.Optional("notes"): cv.string,
    vol.Optional("route"): cv.ensure_list,
})

LOG_HEALTH_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Optional("weight"): vol.Coerce(float),
    vol.Optional("temperature"): vol.Coerce(float),
    vol.Optional("symptoms"): cv.ensure_list_csv,
    vol.Optional("energy_level"): vol.In(["Sehr niedrig", "Niedrig", "Normal", "Hoch", "Sehr hoch"]),
    vol.Optional("notes"): cv.string,
})

UPDATE_GPS_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Required("latitude"): vol.Coerce(float),
    vol.Required("longitude"): vol.Coerce(float),
    vol.Optional("accuracy"): vol.Coerce(float),
    vol.Optional("source"): cv.string,
})

SET_MOOD_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Required("mood"): vol.In(MOOD_OPTIONS),
    vol.Optional("reason"): cv.string,
})

LOG_MEDICATION_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Required("medication_name"): cv.string,
    vol.Optional("dosage"): cv.string,
    vol.Optional("time"): cv.string,
    vol.Optional("notes"): cv.string,
})

EMERGENCY_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Required("activate"): cv.boolean,
    vol.Optional("reason"): cv.string,
    vol.Optional("contact_vet", default=False): cv.boolean,
})

RESET_DATA_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Required("confirm"): vol.In(["RESET"]),
    vol.Optional("reset_type", default="daily"): vol.In(["daily", "all"]),
})


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all PawControl services."""
    if hass.services.has_service(DOMAIN, SERVICE_FEED_DOG):
        return  # Services already registered
    
    async def handle_feed_dog(call: ServiceCall) -> None:
        """Handle feed dog service."""
        dog_name = call.data["dog_name"]
        coordinator = _get_coordinator(hass, dog_name)
        
        if not coordinator:
            _LOGGER.error(f"Dog {dog_name} not found")
            return
        
        meal_type = call.data.get("meal_type", "auto")
        amount = call.data.get("amount")
        
        # Determine meal type based on time if auto
        if meal_type == "auto":
            from datetime import datetime
            hour = datetime.now().hour
            if 5 <= hour < 11:
                meal_type = "breakfast"
            elif 11 <= hour < 15:
                meal_type = "lunch"
            elif 15 <= hour < 21:
                meal_type = "dinner"
            else:
                meal_type = "snack"
        
        await coordinator.async_update_feeding(meal_type, amount)
        
        # Update input helpers if they exist
        dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_fed_{meal_type}", True)
        await _update_helper(hass, f"counter.pawcontrol_{dog_id}_meals_today", "increment")
        
        # Update last feeding time
        from datetime import datetime
        import homeassistant.util.dt as dt_util
        await _update_helper(hass, f"input_datetime.pawcontrol_{dog_id}_last_feeding", dt_util.now().isoformat())
        
        _LOGGER.info(f"Fed {dog_name} - {meal_type}")

    async def handle_start_walk(call: ServiceCall) -> None:
        """Handle start walk service."""
        dog_name = call.data["dog_name"]
        coordinator = _get_coordinator(hass, dog_name)
        
        if not coordinator:
            _LOGGER.error(f"Dog {dog_name} not found")
            return
        
        walk_type = call.data.get("walk_type", "Normal")
        with_gps = call.data.get("with_gps", False)
        
        # Update coordinator status
        coordinator._data["status"]["is_outside"] = True
        coordinator._data["status"]["walk_in_progress"] = True
        
        # Update helpers
        dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_is_outside", True)
        await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_walk_in_progress", True)
        
        if with_gps:
            await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_gps_tracking", True)
        
        await coordinator.async_request_refresh()
        _LOGGER.info(f"Started {walk_type} walk for {dog_name}")

    async def handle_end_walk(call: ServiceCall) -> None:
        """Handle end walk service."""
        dog_name = call.data["dog_name"]
        coordinator = _get_coordinator(hass, dog_name)
        
        if not coordinator:
            _LOGGER.error(f"Dog {dog_name} not found")
            return
        
        duration = call.data["duration"]
        distance = call.data.get("distance")
        route = call.data.get("route")
        
        await coordinator.async_update_walk(duration, distance, route)
        
        # Update helpers
        dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_walk_in_progress", False)
        await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_walk_completed", True)
        await _update_helper(hass, f"counter.pawcontrol_{dog_id}_walks_today", "increment")
        
        # Update last walk time
        import homeassistant.util.dt as dt_util
        await _update_helper(hass, f"input_datetime.pawcontrol_{dog_id}_last_walk", dt_util.now().isoformat())
        
        # Update walk distance if provided
        if distance:
            current_distance_state = hass.states.get(f"input_number.pawcontrol_{dog_id}_walk_distance_today")
            if current_distance_state:
                current = float(current_distance_state.state or 0)
                await _update_helper(hass, f"input_number.pawcontrol_{dog_id}_walk_distance_today", current + distance)
        
        _LOGGER.info(f"Ended walk for {dog_name} - {duration} minutes")

    async def handle_log_health(call: ServiceCall) -> None:
        """Handle log health data service."""
        dog_name = call.data["dog_name"]
        coordinator = _get_coordinator(hass, dog_name)
        
        if not coordinator:
            _LOGGER.error(f"Dog {dog_name} not found")
            return
        
        temperature = call.data.get("temperature")
        weight = call.data.get("weight")
        symptoms = call.data.get("symptoms", [])
        
        await coordinator.async_update_health(temperature, weight, symptoms)
        
        # Update helpers
        dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        if temperature:
            await _update_helper(hass, f"input_number.pawcontrol_{dog_id}_temperature", temperature)
        if weight:
            await _update_helper(hass, f"input_number.pawcontrol_{dog_id}_weight", weight)
        if symptoms:
            await _update_helper(hass, f"input_text.pawcontrol_{dog_id}_symptoms", ", ".join(symptoms))
        
        _LOGGER.info(f"Logged health data for {dog_name}")

    async def handle_update_gps(call: ServiceCall) -> None:
        """Handle GPS update service."""
        dog_name = call.data["dog_name"]
        coordinator = _get_coordinator(hass, dog_name)
        
        if not coordinator:
            _LOGGER.error(f"Dog {dog_name} not found")
            return
        
        latitude = call.data["latitude"]
        longitude = call.data["longitude"]
        accuracy = call.data.get("accuracy")
        
        await coordinator.async_update_location(latitude, longitude, accuracy)
        
        # Update helper
        dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        location_str = f"{latitude:.5f}, {longitude:.5f}"
        await _update_helper(hass, f"input_text.pawcontrol_{dog_id}_current_location", location_str)
        
        # Update GPS signal strength if provided
        if accuracy:
            # Convert accuracy to signal strength (inverse relationship)
            signal_strength = max(0, min(100, 100 - (accuracy * 2)))
            await _update_helper(hass, f"input_number.pawcontrol_{dog_id}_gps_signal", signal_strength)
        
        _LOGGER.info(f"Updated GPS for {dog_name}: {location_str}")

    async def handle_set_mood(call: ServiceCall) -> None:
        """Handle set mood service."""
        dog_name = call.data["dog_name"]
        coordinator = _get_coordinator(hass, dog_name)
        
        if not coordinator:
            _LOGGER.error(f"Dog {dog_name} not found")
            return
        
        mood = call.data["mood"]
        coordinator._data["profile"]["mood"] = mood
        
        # Update helper
        dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        # Check if the select entity exists first
        select_entity = hass.states.get(f"input_select.pawcontrol_{dog_id}_mood")
        if select_entity:
            await _update_helper(hass, f"input_select.pawcontrol_{dog_id}_mood", mood)
        else:
            # Try to update a text entity instead
            await _update_helper(hass, f"input_text.pawcontrol_{dog_id}_mood", mood)
        
        await coordinator.async_request_refresh()
        _LOGGER.info(f"Set mood for {dog_name}: {mood}")

    async def handle_log_medication(call: ServiceCall) -> None:
        """Handle log medication service."""
        dog_name = call.data["dog_name"]
        coordinator = _get_coordinator(hass, dog_name)
        
        if not coordinator:
            _LOGGER.error(f"Dog {dog_name} not found")
            return
        
        medication_name = call.data["medication_name"]
        
        # Update status
        import homeassistant.util.dt as dt_util
        coordinator._data["status"]["last_medication"] = dt_util.now().isoformat()
        
        # Update helper
        dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_needs_medication", False)
        
        # Update last medication time
        import homeassistant.util.dt as dt_util
        await _update_helper(hass, f"input_datetime.pawcontrol_{dog_id}_last_medication", dt_util.now().isoformat())
        
        # Store medication in notes
        dosage = call.data.get("dosage", "")
        notes = f"{medication_name} - {dosage}" if dosage else medication_name
        await _update_helper(hass, f"input_text.pawcontrol_{dog_id}_medication_notes", notes)
        
        await coordinator.async_request_refresh()
        _LOGGER.info(f"Logged medication for {dog_name}: {medication_name}")

    async def handle_emergency(call: ServiceCall) -> None:
        """Handle emergency mode service."""
        dog_name = call.data["dog_name"]
        coordinator = _get_coordinator(hass, dog_name)
        
        if not coordinator:
            _LOGGER.error(f"Dog {dog_name} not found")
            return
        
        activate = call.data["activate"]
        reason = call.data.get("reason")
        
        await coordinator.async_set_emergency(activate, reason)
        
        if activate:
            _LOGGER.warning(f"EMERGENCY MODE ACTIVATED for {dog_name}: {reason}")
            # Send notification
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": f"🚨 NOTFALL - {dog_name}",
                    "message": f"Notfallmodus aktiviert! Grund: {reason or 'Nicht angegeben'}",
                    "notification_id": f"pawcontrol_emergency_{dog_name}",
                },
            )
        else:
            _LOGGER.info(f"Emergency mode deactivated for {dog_name}")

    async def handle_reset_data(call: ServiceCall) -> None:
        """Handle reset data service."""
        dog_name = call.data["dog_name"]
        confirm = call.data["confirm"]
        reset_type = call.data.get("reset_type", "daily")
        
        if confirm != "RESET":
            _LOGGER.error("Reset not confirmed")
            return
        
        coordinator = _get_coordinator(hass, dog_name)
        if not coordinator:
            _LOGGER.error(f"Dog {dog_name} not found")
            return
        
        if reset_type == "daily":
            # Reset daily counters
            coordinator._data["activity"]["daily_walks"] = 0
            coordinator._data["activity"]["daily_meals"] = 0
            coordinator._data["activity"]["daily_playtime"] = 0
            coordinator._data["activity"]["walk_distance_today"] = 0
            coordinator._data["activity"]["calories_burned"] = 0
            
            # Reset daily helpers
            dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
            await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_fed_breakfast", False)
            await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_fed_lunch", False)
            await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_fed_dinner", False)
            await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_walk_completed", False)
            await _update_helper(hass, f"input_boolean.pawcontrol_{dog_id}_needs_walk", True)
            await _update_helper(hass, f"counter.pawcontrol_{dog_id}_meals_today", "reset")
            await _update_helper(hass, f"counter.pawcontrol_{dog_id}_walks_today", "reset")
            await _update_helper(hass, f"input_number.pawcontrol_{dog_id}_walk_distance_today", 0)
            
            _LOGGER.info(f"Reset daily data for {dog_name}")
        else:
            # Reset all data
            _LOGGER.warning(f"Full data reset for {dog_name}")
        
        await coordinator.async_request_refresh()

    # Register services
    hass.services.async_register(DOMAIN, SERVICE_FEED_DOG, handle_feed_dog, schema=FEED_DOG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_START_WALK, handle_start_walk, schema=START_WALK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_END_WALK, handle_end_walk, schema=END_WALK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_LOG_HEALTH, handle_log_health, schema=LOG_HEALTH_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_GPS, handle_update_gps, schema=UPDATE_GPS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_MOOD, handle_set_mood, schema=SET_MOOD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_LOG_MEDICATION, handle_log_medication, schema=LOG_MEDICATION_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_EMERGENCY, handle_emergency, schema=EMERGENCY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESET_DATA, handle_reset_data, schema=RESET_DATA_SCHEMA)
    
    _LOGGER.info("PawControl services registered")


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister all PawControl services."""
    services = [
        SERVICE_FEED_DOG,
        SERVICE_START_WALK,
        SERVICE_END_WALK,
        SERVICE_LOG_HEALTH,
        SERVICE_UPDATE_GPS,
        SERVICE_SET_MOOD,
        SERVICE_LOG_MEDICATION,
        SERVICE_EMERGENCY,
        SERVICE_RESET_DATA,
    ]
    
    for service in services:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    
    _LOGGER.info("PawControl services unregistered")


def _get_coordinator(hass: HomeAssistant, dog_name: str):
    """Get coordinator for a specific dog."""
    dog_name_clean = dog_name.lower().replace(" ", "_").replace("-", "_")
    
    for entry_data in hass.data.get(DOMAIN, {}).values():
        for name, data in entry_data.items():
            if name.lower().replace(" ", "_").replace("-", "_") == dog_name_clean:
                return data.get("coordinator")
    
    return None


async def _update_helper(hass: HomeAssistant, entity_id: str, value: Any) -> None:
    """Update a helper entity."""
    try:
        # Check if entity exists first
        entity_registry = hass.states.get(entity_id)
        if not entity_registry:
            _LOGGER.debug(f"Helper {entity_id} does not exist yet")
            return
        
        if entity_id.startswith("input_boolean"):
            await hass.services.async_call(
                "input_boolean",
                "turn_on" if value else "turn_off",
                {"entity_id": entity_id},
                blocking=False,
            )
        elif entity_id.startswith("input_number"):
            await hass.services.async_call(
                "input_number",
                "set_value",
                {"entity_id": entity_id, "value": value},
                blocking=False,
            )
        elif entity_id.startswith("input_text"):
            await hass.services.async_call(
                "input_text",
                "set_value",
                {"entity_id": entity_id, "value": str(value)},
                blocking=False,
            )
        elif entity_id.startswith("input_select"):
            await hass.services.async_call(
                "input_select",
                "select_option",
                {"entity_id": entity_id, "option": value},
                blocking=False,
            )
        elif entity_id.startswith("input_datetime"):
            # Handle datetime updates
            if isinstance(value, str):
                # ISO format datetime string
                await hass.services.async_call(
                    "input_datetime",
                    "set_datetime",
                    {"entity_id": entity_id, "datetime": value},
                    blocking=False,
                )
            else:
                # Datetime object
                await hass.services.async_call(
                    "input_datetime",
                    "set_datetime",
                    {"entity_id": entity_id, "datetime": value.isoformat() if hasattr(value, 'isoformat') else str(value)},
                    blocking=False,
                )
        elif entity_id.startswith("counter"):
            if value == "increment":
                await hass.services.async_call(
                    "counter",
                    "increment",
                    {"entity_id": entity_id},
                    blocking=False,
                )
            elif value == "reset":
                await hass.services.async_call(
                    "counter",
                    "reset",
                    {"entity_id": entity_id},
                    blocking=False,
                )
            elif isinstance(value, (int, float)):
                # Set specific value
                await hass.services.async_call(
                    "counter",
                    "set_value",
                    {"entity_id": entity_id, "value": int(value)},
                    blocking=False,
                )
    except Exception as err:
        _LOGGER.debug(f"Could not update helper {entity_id}: {err}")
