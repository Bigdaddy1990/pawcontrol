"""Activity logging for Paw Control."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util.dt import now

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_log_activity(
    hass: HomeAssistant, 
    dog_name: str, 
    activity_type: str,
    notes: str | None = None
) -> None:
    """Log a dog activity for statistics purposes."""
    
    dog_id = dog_name.lower().replace(" ", "_")
    timestamp = now()
    
    try:
        # Update counter if it exists
        counter_entity = f"counter.{dog_id}_{activity_type}_count"
        if hass.states.get(counter_entity):
            await hass.services.async_call(
                "counter", 
                "increment", 
                {"entity_id": counter_entity}
            )
            _LOGGER.debug("Incremented counter %s", counter_entity)
        
        # Update datetime for specific activities
        if activity_type in ["walk", "feeding", "outside", "poop"]:
            datetime_entity = f"input_datetime.{dog_id}_last_{activity_type}"
            if hass.states.get(datetime_entity):
                await hass.services.async_call(
                    "input_datetime",
                    "set_datetime",
                    {
                        "entity_id": datetime_entity,
                        "datetime": timestamp.isoformat()
                    }
                )
                _LOGGER.debug("Updated datetime %s", datetime_entity)
        
        # Update last activity text
        readable_activities = {
            "walk": "Walk",
            "feeding": "Feeding",
            "outside": "Outside",
            "poop": "Potty",
            "play": "Play",
            "training": "Training",
            "medication": "Medication",
            "health_check": "Health check",
        }
        
        activity_label = readable_activities.get(activity_type, activity_type.title())
        time_str = timestamp.strftime("%H:%M")
        
        last_activity_text = f"{time_str} – {activity_label}"
        if notes:
            last_activity_text += f" ({notes})"
        
        last_activity_entity = f"input_text.{dog_id}_last_activity"
        if hass.states.get(last_activity_entity):
            await hass.services.async_call(
                "input_text",
                "set_value",
                {
                    "entity_id": last_activity_entity,
                    "value": last_activity_text
                }
            )
            _LOGGER.debug("Updated last activity: %s", last_activity_text)
        
        # Log activity history in notes if available
        activity_notes_entity = f"input_text.{dog_id}_activity_history"
        if hass.states.get(activity_notes_entity):
            current_notes = hass.states.get(activity_notes_entity).state or ""
            
            # Keep only last 10 activities to prevent overflow
            lines = current_notes.split("\n") if current_notes else []
            lines.insert(0, last_activity_text)
            
            # Limit to 10 entries
            if len(lines) > 10:
                lines = lines[:10]
            
            new_notes = "\n".join(lines)
            
            await hass.services.async_call(
                "input_text",
                "set_value",
                {
                    "entity_id": activity_notes_entity,
                    "value": new_notes
                }
            )
        
        _LOGGER.info("Activity logged for %s: %s", dog_name, activity_label)
        
    except Exception as e:
        _LOGGER.error("Failed to log activity %s for %s: %s", activity_type, dog_name, e)


async def async_log_feeding(
    hass: HomeAssistant,
    dog_name: str,
    meal_type: str,
    amount: int | None = None
) -> None:
    """Log a feeding activity with specific meal type."""
    
    notes = f"{meal_type}"
    if amount:
        notes += f" ({amount}g)"
    
    await async_log_activity(hass, dog_name, "feeding", notes)
    
    # Also log specific meal type
    await async_log_activity(hass, dog_name, f"feeding_{meal_type}")


async def async_log_walk(
    hass: HomeAssistant,
    dog_name: str,
    duration: int | None = None,
    walk_type: str | None = None
) -> None:
    """Log a walk activity with duration and type."""
    
    notes = ""
    if walk_type:
        notes += walk_type
    if duration:
        notes += f" ({duration} min)" if notes else f"{duration} min"
    
    await async_log_activity(hass, dog_name, "walk", notes or None)


async def async_log_health_event(
    hass: HomeAssistant,
    dog_name: str,
    event_type: str,
    details: str | None = None
) -> None:
    """Log a health-related event."""
    
    health_events = {
        "medication": "Medication given",
        "vet_visit": "Vet visit",
        "health_check": "Health check",
        "vaccination": "Vaccination",
        "weight_check": "Weight check",
    }
    
    event_label = health_events.get(event_type, event_type)
    await async_log_activity(hass, dog_name, "health_event", f"{event_label}: {details}" if details else event_label)


async def async_get_daily_summary(hass: HomeAssistant, dog_name: str) -> str:
    """Get a summary of today's activities."""
    
    dog_id = dog_name.lower().replace(" ", "_")
    
    try:
        # Collect today's stats
        activities = {}
        
        activity_counters = [
            ("feeding_morning", "Breakfast"),
            ("feeding_lunch", "Lunch"),
            ("feeding_evening", "Dinner"),
            ("feeding_snack", "Snacks"),
            ("outside", "Outside"),
            ("walk", "Walk"),
            ("play", "Play"),
            ("training", "Training"),
            ("poop", "Potty"),
        ]

        for counter_suffix, label in activity_counters:
            counter_entity = f"counter.{dog_id}_{counter_suffix}_count"
            state = hass.states.get(counter_entity)
            if state and state.state != "0":
                activities[label] = state.state

        if not activities:
            return f"{dog_name.title()}: No activities recorded today"

        # Format summary
        summary_parts = []
        for activity, count in activities.items():
            summary_parts.append(f"{activity}: {count}x")

        return f"{dog_name.title()}: " + ", ".join(summary_parts)
        
    except Exception as e:
        _LOGGER.error("Failed to generate daily summary for %s: %s", dog_name, e)
        return f"{dog_name.title()}: Summary not available"
