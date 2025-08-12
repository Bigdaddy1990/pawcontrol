"""Notification router for Paw Control integration."""
from __future__ import annotations
import logging
from typing import List
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class NotificationRouter:
    """Handle notification routing for Paw Control."""
    
    def __init__(self, hass: HomeAssistant, notify_target: str | None = None):
        """Initialize the notification router."""
        self.hass = hass
        self.notify_target = notify_target or "notify.notify"
    
    async def send_generic(self, title: str, message: str, dog_id: str | None = None, 
                          kind: str = "info", actions: List[dict] | None = None) -> None:
        """Send a generic notification."""
        try:
            data = {
                "message": message,
                "title": title,
            }
            
            if actions:
                data["data"] = {"actions": actions}
            
            # Try to send via configured notify service
            if self.notify_target and "." in self.notify_target:
                domain, service = self.notify_target.split(".", 1)
                await self.hass.services.async_call(domain, service, data, blocking=False)
            else:
                # Fallback to persistent notification
                await self._send_persistent_notification(title, message)
                
        except Exception as exc:
            _LOGGER.warning("Failed to send notification: %s", exc)
            # Always try persistent notification as final fallback
            try:
                await self._send_persistent_notification(title, message)
            except Exception:
                pass
    
    async def _send_persistent_notification(self, title: str, message: str) -> None:
        """Send a persistent notification as fallback."""
        try:
            from homeassistant.components.persistent_notification import create as pn
            pn(self.hass, message, title=title)
        except Exception as exc:
            _LOGGER.error("Failed to send persistent notification: %s", exc)
    
    async def send_feeding_reminder(self, dog_id: str, meal_type: str) -> None:
        """Send feeding reminder."""
        title = f"Fütterungserinnerung - {dog_id}"
        message = f"Zeit für {meal_type} für {dog_id}!"
        
        actions = [
            {"action": f"FED_{dog_id}_{meal_type}", "title": "Gefüttert ✅"},
            {"action": f"SNOOZE_{dog_id}_{meal_type}", "title": "10 Min später ⏰"},
        ]
        
        await self.send_generic(title, message, dog_id, "feeding", actions)
    
    async def send_walk_reminder(self, dog_id: str) -> None:
        """Send walk reminder."""
        title = f"Gassi-Erinnerung - {dog_id}"
        message = f"{dog_id} braucht einen Spaziergang!"
        
        actions = [
            {"action": f"WALK_START_{dog_id}", "title": "Gassi starten 🚶"},
            {"action": f"WALK_LATER_{dog_id}", "title": "Später ⏰"},
        ]
        
        await self.send_generic(title, message, dog_id, "walk", actions)
    
    async def send_medication_reminder(self, dog_id: str, medication: str, slot: int) -> None:
        """Send medication reminder."""
        title = f"Medikationserinnerung - {dog_id}"
        message = f"Zeit für Medikament (Slot {slot}) für {dog_id}!"
        
        actions = [
            {"action": f"MED_GIVEN_{dog_id}_{slot}", "title": "Gegeben ✅"},
            {"action": f"MED_SNOOZE_{dog_id}_{slot}", "title": "15 Min später ⏰"},
        ]
        
        await self.send_generic(title, message, dog_id, "medication", actions)
