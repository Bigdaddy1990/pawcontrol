"""Service handlers for Paw Control integration."""
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

from .utils import safe_service_call

_LOGGER = logging.getLogger(__name__)


async def _svc(
    hass: HomeAssistant, domain: str, service: str, entity_id: str, **data: Any
) -> None:
    """Wrapper around ``safe_service_call`` accepting an ``entity_id`` argument."""
    await safe_service_call(hass, domain, service, {"entity_id": entity_id, **data})


async def update_feeding_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update feeding-related entities."""
    try:
        food_type = data.get(SERVICE_FOOD_TYPE, "Trockenfutter")
        amount = data.get(SERVICE_FOOD_AMOUNT, 100)
        
        # Update feeding boolean based on current time
        now = datetime.now()
        if now.hour < 10:
            feeding_entity = f"input_boolean.{dog_name}_feeding_morning"
        elif now.hour < 16:
            feeding_entity = f"input_boolean.{dog_name}_feeding_lunch"
        else:
            feeding_entity = f"input_boolean.{dog_name}_feeding_evening"
        
        # Turn on feeding boolean
        await _svc(hass, "input_boolean", "turn_on", feeding_entity)

        # Update counter
        counter_entity = (
            feeding_entity.replace("input_boolean", "counter")
            .replace("feeding_", "feeding_")
            + "_count"
        )
        await _svc(hass, "counter", "increment", counter_entity)

        # Update last feeding datetime
        datetime_entity = feeding_entity.replace(
            "input_boolean", "input_datetime"
        ).replace("feeding_", "last_feeding_")
        await _svc(
            hass,
            "input_datetime",
            "set_datetime",
            datetime_entity,
            datetime=now.isoformat(),
        )

        # Update daily food amount
        daily_amount_entity = f"input_number.{dog_name}_daily_food_amount"
        current_state = hass.states.get(daily_amount_entity)
        if current_state:
            current_amount = float(current_state.state)
            new_amount = current_amount + amount
            await _svc(
                hass,
                "input_number",
                "set_value",
                daily_amount_entity,
                value=new_amount,
            )
        
        _LOGGER.debug("Updated feeding entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating feeding entities for %s: %s", dog_name, e)


async def update_walk_start_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update entities when walk starts."""
    try:
        # Set walk in progress
        await _svc(
            hass,
            "input_boolean",
            "turn_on",
            f"input_boolean.{dog_name}_walk_in_progress",
        )

        # Update walk start time
        await _svc(
            hass,
            "input_datetime",
            "set_datetime",
            f"input_datetime.{dog_name}_last_walk",
            datetime=datetime.now().isoformat(),
        )
        
        _LOGGER.debug("Updated walk start entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating walk start entities for %s: %s", dog_name, e)


async def update_walk_end_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update entities when walk ends."""
    try:
        # Turn off walk in progress
        await _svc(
            hass,
            "input_boolean",
            "turn_off",
            f"input_boolean.{dog_name}_walk_in_progress",
        )

        # Set outside and walked_today to true
        await _svc(hass, "input_boolean", "turn_on", f"input_boolean.{dog_name}_outside")
        await _svc(
            hass,
            "input_boolean",
            "turn_on",
            f"input_boolean.{dog_name}_walked_today",
        )

        # Increment walk counter
        await _svc(hass, "counter", "increment", f"counter.{dog_name}_walk_count")

        # Update walk duration if provided
        duration = data.get(SERVICE_DURATION)
        if duration:
            await _svc(
                hass,
                "input_number",
                "set_value",
                f"input_number.{dog_name}_daily_walk_duration",
                value=duration,
            )
        
        _LOGGER.debug("Updated walk end entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating walk end entities for %s: %s", dog_name, e)


async def update_health_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update health-related entities."""
    try:
        # Update weight if provided
        if weight := data.get(SERVICE_WEIGHT):
            await _svc(
                hass,
                "input_number",
                "set_value",
                f"input_number.{dog_name}_weight",
                value=weight,
            )

        # Update temperature if provided
        if temperature := data.get(SERVICE_TEMPERATURE):
            await _svc(
                hass,
                "input_number",
                "set_value",
                f"input_number.{dog_name}_temperature",
                value=temperature,
            )

        # Update energy level if provided
        if energy_level := data.get(SERVICE_ENERGY_LEVEL):
            await _svc(
                hass,
                "input_select",
                "select_option",
                f"input_select.{dog_name}_energy_level_category",
                option=energy_level,
            )

        # Update health notes if provided
        symptoms = data.get(SERVICE_SYMPTOMS)
        notes = data.get(SERVICE_NOTES)
        if symptoms or notes:
            health_notes = f"{symptoms or ''} {notes or ''}".strip()
            await _svc(
                hass,
                "input_text",
                "set_value",
                f"input_text.{dog_name}_health_notes",
                value=health_notes,
            )
        
        _LOGGER.debug("Updated health entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating health entities for %s: %s", dog_name, e)


async def update_mood_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update mood-related entities."""
    try:
        if mood := data.get(SERVICE_MOOD):
            await _svc(
                hass,
                "input_select",
                "select_option",
                f"input_select.{dog_name}_mood",
                option=mood,
            )
        
        _LOGGER.debug("Updated mood entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating mood entities for %s: %s", dog_name, e)


async def update_training_start_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update entities when training starts."""
    try:
        await _svc(
            hass,
            "input_boolean",
            "turn_on",
            f"input_boolean.{dog_name}_training_session",
        )
        
        _LOGGER.debug("Updated training start entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating training start entities for %s: %s", dog_name, e)


async def update_training_end_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update entities when training ends."""
    try:
        await _svc(
            hass,
            "input_boolean",
            "turn_off",
            f"input_boolean.{dog_name}_training_session",
        )

        await _svc(
            hass,
            "counter",
            "increment",
            f"counter.{dog_name}_training_count",
        )
        
        _LOGGER.debug("Updated training end entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating training end entities for %s: %s", dog_name, e)


async def update_medication_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update medication-related entities."""
    try:
        await _svc(
            hass,
            "input_boolean",
            "turn_on",
            f"input_boolean.{dog_name}_medication_given",
        )

        await _svc(
            hass,
            "counter",
            "increment",
            f"counter.{dog_name}_medication_count",
        )

        await _svc(
            hass,
            "input_datetime",
            "set_datetime",
            f"input_datetime.{dog_name}_last_medication",
            datetime=datetime.now().isoformat(),
        )
        
        _LOGGER.debug("Updated medication entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating medication entities for %s: %s", dog_name, e)


async def update_vet_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update veterinary-related entities."""
    try:
        if vet_date := data.get(SERVICE_VET_DATE):
            await _svc(
                hass,
                "input_datetime",
                "set_datetime",
                f"input_datetime.{dog_name}_next_vet_appointment",
                datetime=vet_date,
            )
        
        _LOGGER.debug("Updated vet entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating vet entities for %s: %s", dog_name, e)


async def update_playtime_start_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update entities when playtime starts."""
    try:
        await _svc(
            hass,
            "input_boolean",
            "turn_on",
            f"input_boolean.{dog_name}_playtime_session",
        )
        
        _LOGGER.debug("Updated playtime start entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating playtime start entities for %s: %s", dog_name, e)


async def update_playtime_end_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update entities when playtime ends."""
    try:
        await _svc(
            hass,
            "input_boolean",
            "turn_off",
            f"input_boolean.{dog_name}_playtime_session",
        )

        await _svc(
            hass,
            "counter",
            "increment",
            f"counter.{dog_name}_playtime_count",
        )
        
        _LOGGER.debug("Updated playtime end entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating playtime end entities for %s: %s", dog_name, e)


async def reset_all_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Reset all daily entities."""
    try:
        # Reset boolean entities
        boolean_entities = [
            f"input_boolean.{dog_name}_feeding_morning",
            f"input_boolean.{dog_name}_feeding_lunch", 
            f"input_boolean.{dog_name}_feeding_evening",
            f"input_boolean.{dog_name}_walked_today",
            f"input_boolean.{dog_name}_outside",
            f"input_boolean.{dog_name}_medication_given",
        ]
        
        for entity in boolean_entities:
            await _svc(hass, "input_boolean", "turn_off", entity)
        
        # Reset counters
        counter_entities = [
            f"counter.{dog_name}_walk_count",
            f"counter.{dog_name}_training_count",
            f"counter.{dog_name}_playtime_count",
            f"counter.{dog_name}_medication_count",
        ]
        
        for entity in counter_entities:
            await _svc(hass, "counter", "reset", entity)
        
        # Reset number entities
        number_entities = [
            f"input_number.{dog_name}_daily_food_amount",
            f"input_number.{dog_name}_daily_walk_duration",
        ]
        
        for entity in number_entities:
            await _svc(hass, "input_number", "set_value", entity, value=0)
        
        _LOGGER.info("Reset all entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error resetting entities for %s: %s", dog_name, e)


# GPS Entity Update Functions
async def update_gps_entities(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Update GPS-related entities."""
    try:
        latitude = data.get("latitude")
        longitude = data.get("longitude") 
        accuracy = data.get("accuracy", 0)
        source_info = data.get("source_info", "manual")
        
        # Update current location
        location_str = f"{latitude:.6f},{longitude:.6f}"
        await safe_service_call(hass, "input_text", "set_value", {
            "entity_id": f"input_text.{dog_name}_current_location",
            "value": location_str
        })
        
        # Update GPS signal strength based on accuracy
        signal_strength = max(0, min(100, 100 - accuracy)) if accuracy > 0 else 100
        await safe_service_call(hass, "input_number", "set_value", {
            "entity_id": f"input_number.{dog_name}_gps_signal_strength",
            "value": signal_strength
        })
        
        # Update GPS tracker status
        await safe_service_call(hass, "input_text", "set_value", {
            "entity_id": f"input_text.{dog_name}_gps_tracker_status",
            "value": f"Active - {source_info}"
        })
        
        _LOGGER.debug("Updated GPS entities for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error updating GPS entities for %s: %s", dog_name, e)


async def setup_gps_automation(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Setup GPS automation entities."""
    try:
        auto_start = data.get("auto_start_walk", True)
        auto_end = data.get("auto_end_walk", True)
        
        # Enable auto walk detection
        await safe_service_call(hass, "input_boolean", "turn_on" if (auto_start or auto_end) else "turn_off", {
            "entity_id": f"input_boolean.{dog_name}_auto_walk_detection"
        })
        
        _LOGGER.debug("Setup GPS automation for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error setting up GPS automation for %s: %s", dog_name, e)


async def start_walk_tracking(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """Start walk tracking entities."""
    try:
        walk_name = data.get("walk_name", "Spaziergang")
        
        # Set walk in progress
        await safe_service_call(hass, "input_boolean", "turn_on", {
            "entity_id": f"input_boolean.{dog_name}_walk_in_progress"
        })
        
        # Reset current walk stats
        await safe_service_call(hass, "input_number", "set_value", {
            "entity_id": f"input_number.{dog_name}_current_walk_distance",
            "value": 0
        })
        
        await safe_service_call(hass, "input_number", "set_value", {
            "entity_id": f"input_number.{dog_name}_current_walk_duration",
            "value": 0
        })
        
        await safe_service_call(hass, "input_number", "set_value", {
            "entity_id": f"input_number.{dog_name}_current_walk_speed",
            "value": 0
        })
        
        await safe_service_call(hass, "input_number", "set_value", {
            "entity_id": f"input_number.{dog_name}_calories_burned_walk",
            "value": 0
        })
        
        # Initialize route tracking
        await safe_service_call(hass, "input_text", "set_value", {
            "entity_id": f"input_text.{dog_name}_current_walk_route",
            "value": "[]"
        })
        
        _LOGGER.debug("Started walk tracking for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error starting walk tracking for %s: %s", dog_name, e)


async def end_walk_tracking(hass: HomeAssistant, dog_name: str, data: dict) -> None:
    """End walk tracking and update statistics."""
    try:
        # Get current walk distance
        distance_entity = f"input_number.{dog_name}_current_walk_distance"
        current_distance_state = hass.states.get(distance_entity)
        current_distance = float(current_distance_state.state) if current_distance_state else 0
        
        # Update daily walk distance
        daily_entity = f"input_number.{dog_name}_walk_distance_today"
        daily_state = hass.states.get(daily_entity)
        daily_distance = float(daily_state.state) if daily_state else 0
        
        await safe_service_call(hass, "input_number", "set_value", {
            "entity_id": daily_entity,
            "value": daily_distance + current_distance
        })
        
        # Update weekly distance
        weekly_entity = f"input_number.{dog_name}_walk_distance_weekly"
        weekly_state = hass.states.get(weekly_entity)
        weekly_distance = float(weekly_state.state) if weekly_state else 0
        
        await safe_service_call(hass, "input_number", "set_value", {
            "entity_id": weekly_entity,
            "value": weekly_distance + current_distance
        })
        
        # Turn off walk in progress
        await safe_service_call(hass, "input_boolean", "turn_off", {
            "entity_id": f"input_boolean.{dog_name}_walk_in_progress"
        })
        
        # Set walked today
        await safe_service_call(hass, "input_boolean", "turn_on", {
            "entity_id": f"input_boolean.{dog_name}_walked_today"
        })
        
        # Add to walk history
        walk_history_entity = f"input_text.{dog_name}_walk_history_today"
        history_state = hass.states.get(walk_history_entity)
        current_history = history_state.state if history_state else ""
        
        walk_entry = f"{datetime.now().strftime('%H:%M')} - {current_distance:.1f}km"
        new_history = f"{current_history}, {walk_entry}" if current_history else walk_entry
        
        await safe_service_call(hass, "input_text", "set_value", {
            "entity_id": walk_history_entity,
            "value": new_history
        })
        
        _LOGGER.debug("Ended walk tracking for %s", dog_name)
        
    except Exception as e:
        _LOGGER.error("Error ending walk tracking for %s: %s", dog_name, e)


"""Service zum Generieren des Dashboards."""
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from .ui.dashboard import write_dashboard_to_inputs

SERVICE_GENERATE_DASHBOARD = "generate_dashboard"

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("dog_name"): cv.string,
    }
)

async def async_setup_services(hass: HomeAssistant) -> None:
    async def handle_generate(call: ServiceCall) -> None:
        dog = call.data["dog_name"]
        await write_dashboard_to_inputs(hass, dog)

    hass.services.async_register(
        "pawcontrol",
        SERVICE_GENERATE_DASHBOARD,
        handle_generate,
        schema=SERVICE_SCHEMA,
    )

    async def handle_generate_all(call: ServiceCall) -> None:
        await write_multi_dashboard_to_input(hass)

    hass.services.async_register(
        "pawcontrol",
        "generate_multi_dashboard",
        handle_generate_all,
    )
