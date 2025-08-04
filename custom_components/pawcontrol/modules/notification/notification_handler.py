"""Notification handler for Paw Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def send_push_notification(
    hass: HomeAssistant, 
    dog_name: str, 
    message: str, 
    actions: list[dict[str, Any]] | None = None
) -> None:
    """Send a targeted notification only to present persons/devices."""
    
    dog_id = slugify(dog_name)
    
    # Find home persons and their mobile devices
    recipients = []
    persons = hass.states.async_entity_ids("person")
    
    for person_entity in persons:
        person_state = hass.states.get(person_entity)
        if person_state and person_state.state == "home":
            person_id = person_entity.split(".")[1]
            notify_entity = f"notify.mobile_app_{person_id}"
            
            # Check if notify service exists
            notify_services = hass.services.async_services().get("notify", {})
            if notify_entity.replace("notify.", "") in notify_services:
                recipients.append(notify_entity)
    
    # Send notifications
    if not recipients:
        _LOGGER.warning("No home persons with mobile app found for notification")
        # Fallback to default notify service
        recipients = ["notify.notify"]
    
    for target in recipients:
        try:
            service_name = target.replace("notify.", "")
            data = {
                "title": f"Paw Control: {dog_name.title()}",
                "message": message,
            }
            
            if actions:
                data["data"] = {"actions": actions}
            
            await hass.services.async_call("notify", service_name, data)
            _LOGGER.debug("Notification sent to %s for %s", service_name, dog_name)
            
        except Exception as e:
            _LOGGER.error("Failed to send notification to %s: %s", target, e)


async def send_feeding_reminder(hass: HomeAssistant, dog_name: str, meal_type: str) -> None:
    """Send a feeding reminder notification."""
    
    meal_names = {
        "morning": "Frühstück",
        "lunch": "Mittagessen", 
        "evening": "Abendessen",
        "snack": "Leckerli"
    }
    
    meal_name = meal_names.get(meal_type, meal_type)
    message = f"Zeit für {meal_name} für {dog_name.title()}! 🍽️"
    
    actions = [
        {
            "action": f"FEED_{dog_name.upper()}_{meal_type.upper()}",
            "title": "Gefüttert ✅"
        },
        {
            "action": f"SNOOZE_{dog_name.upper()}_{meal_type.upper()}",
            "title": "10 Min später ⏰"
        }
    ]
    
    await send_push_notification(hass, dog_name, message, actions)


async def send_walk_reminder(hass: HomeAssistant, dog_name: str) -> None:
    """Send a walk reminder notification."""
    
    message = f"{dog_name.title()} braucht einen Spaziergang! 🚶"
    
    actions = [
        {
            "action": f"WALK_START_{dog_name.upper()}",
            "title": "Gassi starten 🚶"
        },
        {
            "action": f"WALK_LATER_{dog_name.upper()}",
            "title": "Später 🕐"
        }
    ]
    
    await send_push_notification(hass, dog_name, message, actions)


async def send_health_alert(hass: HomeAssistant, dog_name: str, alert_type: str) -> None:
    """Send a health alert notification."""
    
    alert_messages = {
        "sick": f"⚠️ {dog_name.title()} zeigt Krankheitssymptome!",
        "medication": f"💊 Zeit für Medikamente für {dog_name.title()}!",
        "vet_appointment": f"🏥 Tierarzttermin für {dog_name.title()} steht an!",
        "emergency": f"🚨 NOTFALL - {dog_name.title()} braucht sofortige Hilfe!"
    }
    
    message = alert_messages.get(alert_type, f"Gesundheitsalert für {dog_name.title()}")
    
    actions = [
        {
            "action": f"HEALTH_CHECK_{dog_name.upper()}",
            "title": "Überprüft ✅"
        }
    ]
    
    if alert_type == "emergency":
        actions.append({
            "action": f"CALL_VET_{dog_name.upper()}",
            "title": "Tierarzt anrufen 📞"
        })
    
    await send_push_notification(hass, dog_name, message, actions)


async def send_test_notification(hass: HomeAssistant, dog_name: str) -> None:
    """Send a test notification."""
    
    message = f"Test-Benachrichtigung für {dog_name.title()} - System funktioniert! 🧪"
    
    actions = [
        {
            "action": f"TEST_OK_{dog_name.upper()}",
            "title": "Test erfolgreich ✅"
        }
    ]
    
    await send_push_notification(hass, dog_name, message, actions)
