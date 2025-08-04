"""Simplified coordinator for Paw Control - REPARIERT."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_DOG_NAME

_LOGGER = logging.getLogger(__name__)


class PawControlCoordinator(DataUpdateCoordinator):
    """Simplified coordinator for Paw Control."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )
        self.dog_name = entry.data[CONF_DOG_NAME]
        self.entry = entry

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from entities."""
        try:
            data = {
                "dog_name": self.dog_name,
                "last_updated": datetime.now().isoformat(),
                "feeding_status": await self._get_feeding_status(),
                "activity_status": await self._get_activity_status(),
                "health_status": await self._get_health_status(),
                "location_status": await self._get_location_status(),
            }
            
            return data
            
        except Exception as e:
            _LOGGER.error("Error updating data for %s: %s", self.dog_name, e)
            return {}

    async def _get_feeding_status(self) -> Dict[str, Any]:
        """Get feeding status."""
        try:
            morning_state = self.hass.states.get(f"input_boolean.{self.dog_name}_feeding_morning")
            evening_state = self.hass.states.get(f"input_boolean.{self.dog_name}_feeding_evening")
            last_feeding_state = self.hass.states.get(f"input_datetime.{self.dog_name}_last_feeding")
            
            return {
                "morning_fed": morning_state.state == "on" if morning_state else False,
                "evening_fed": evening_state.state == "on" if evening_state else False,
                "last_feeding": last_feeding_state.state if last_feeding_state else None,
                "needs_feeding": not (morning_state and morning_state.state == "on"),
            }
        except Exception as e:
            _LOGGER.error("Error getting feeding status: %s", e)
            return {}

    async def _get_activity_status(self) -> Dict[str, Any]:
        """Get activity status."""
        try:
            outside_state = self.hass.states.get(f"input_boolean.{self.dog_name}_outside")
            walked_state = self.hass.states.get(f"input_boolean.{self.dog_name}_walked_today")
            poop_state = self.hass.states.get(f"input_boolean.{self.dog_name}_poop_done")
            last_walk_state = self.hass.states.get(f"input_datetime.{self.dog_name}_last_walk")
            walk_count_state = self.hass.states.get(f"counter.{self.dog_name}_walk_count")
            
            return {
                "was_outside": outside_state.state == "on" if outside_state else False,
                "walked_today": walked_state.state == "on" if walked_state else False,
                "poop_done": poop_state.state == "on" if poop_state else False,
                "last_walk": last_walk_state.state if last_walk_state else None,
                "walk_count": int(walk_count_state.state) if walk_count_state else 0,
                "needs_walk": not (walked_state and walked_state.state == "on"),
            }
        except Exception as e:
            _LOGGER.error("Error getting activity status: %s", e)
            return {}

    async def _get_health_status(self) -> Dict[str, Any]:
        """Get health status."""
        try:
            weight_state = self.hass.states.get(f"input_number.{self.dog_name}_weight")
            health_notes_state = self.hass.states.get(f"input_text.{self.dog_name}_health_notes")
            
            return {
                "weight": float(weight_state.state) if weight_state else None,
                "health_notes": health_notes_state.state if health_notes_state else "",
                "status": "good",  # Simplified status
            }
        except Exception as e:
            _LOGGER.error("Error getting health status: %s", e)
            return {}

    async def _get_location_status(self) -> Dict[str, Any]:
        """Get location status."""
        try:
            location_state = self.hass.states.get(f"input_text.{self.dog_name}_current_location")
            signal_state = self.hass.states.get(f"input_number.{self.dog_name}_gps_signal_strength")
            
            return {
                "current_location": location_state.state if location_state else "Unknown",
                "gps_signal": float(signal_state.state) if signal_state else 0,
                "gps_available": bool(location_state and location_state.state),
            }
        except Exception as e:
            _LOGGER.error("Error getting location status: %s", e)
            return {}

    def get_status_summary(self) -> str:
        """Get a simple status summary."""
        if not self.data:
            return "⏳ Initialisierung..."
        
        try:
            feeding = self.data.get("feeding_status", {})
            activity = self.data.get("activity_status", {})
            
            fed = feeding.get("morning_fed", False) or feeding.get("evening_fed", False)
            walked = activity.get("walked_today", False)
            outside = activity.get("was_outside", False)
            
            if fed and walked and outside:
                return "✅ Alles erledigt"
            elif fed and (walked or outside):
                return "📝 Teilweise erledigt"
            elif not fed and not walked:
                return "⏰ Fütterung & Spaziergang ausstehend"
            elif not fed:
                return "🍽️ Fütterung ausstehend"
            elif not walked:
                return "🚶 Spaziergang ausstehend"
            else:
                return "👍 Gut"
                
        except Exception as e:
            _LOGGER.error("Error getting status summary: %s", e)
            return "❓ Unbekannt"
