"""Coordinator for Paw Control integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_DOG_NAME, ENTITIES
from .helpers.entity import EntityHelper
from .helpers.datetime import DateTimeHelper
from .helpers.config import ConfigHelper

_LOGGER = logging.getLogger(__name__)

class PawControlCoordinator(DataUpdateCoordinator):
    """Coordinator for Paw Control."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )
        self.dog_name = entry.data[CONF_DOG_NAME].lower().replace(" ", "_")
        self.entry = entry
        
        # Initialize helpers
        self.entity_helper = EntityHelper(hass, self.dog_name)
        self.datetime_helper = DateTimeHelper(hass)
        self.config_helper = ConfigHelper(hass, entry)

    async def async_setup_entities(self) -> None:
        """Setup all required entities."""
        _LOGGER.info("Setting up entities for %s", self.dog_name)
        
        try:
            # Verwende EntityHelper für die Erstellung
            await self.entity_helper.setup_all_entities()
                
        except Exception as e:
            _LOGGER.error("Error setting up entities for %s: %s", self.dog_name, e)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from entities."""
        try:
            data = {
                "dog_name": self.dog_name,
                "last_updated": self.datetime_helper.get_current_datetime_iso(),
                "feeding_status": await self._get_feeding_status(),
                "activity_status": await self._get_activity_status(),
                "health_status": await self._get_health_status(),
            }
            
            return data
            
        except Exception as e:
            _LOGGER.error("Error updating data for %s: %s", self.dog_name, e)
            return {}

    async def _get_feeding_status(self) -> Dict[str, Any]:
        """Get feeding status."""
        try:
            feeding_entities = {
                "morning": f"input_boolean.{self.dog_name}_feeding_morning",
                "lunch": f"input_boolean.{self.dog_name}_feeding_lunch", 
                "evening": f"input_boolean.{self.dog_name}_feeding_evening",
            }
            
            status = {}
            needs_feeding = True
            
            for meal_time, entity_id in feeding_entities.items():
                state = self.hass.states.get(entity_id)
                fed = state.state == "on" if state else False
                status[f"{meal_time}_fed"] = fed
                if fed:
                    needs_feeding = False
            
            status["needs_feeding"] = needs_feeding
            return status
            
        except Exception as e:
            _LOGGER.error("Error getting feeding status: %s", e)
            return {}

    async def _get_activity_status(self) -> Dict[str, Any]:
        """Get activity status."""
        try:
            walk_count_state = self.hass.states.get(f"counter.{self.dog_name}_walk_count")
            last_walk_state = self.hass.states.get(f"input_datetime.{self.dog_name}_last_walk")
            
            walk_count = int(walk_count_state.state) if walk_count_state else 0
            
            return {
                "walk_count": walk_count,
                "last_walk": last_walk_state.state if last_walk_state else None,
                "needs_walk": walk_count == 0,
            }
        except Exception as e:
            _LOGGER.error("Error getting activity status: %s", e)
            return {}

    async def _get_health_status(self) -> Dict[str, Any]:
        """Get health status."""
        try:
            weight_state = self.hass.states.get(f"input_number.{self.dog_name}_weight")
            health_status_state = self.hass.states.get(f"input_select.{self.dog_name}_health_status")
            
            return {
                "weight": float(weight_state.state) if weight_state else None,
                "health_status": health_status_state.state if health_status_state else "gut",
            }
        except Exception as e:
            _LOGGER.error("Error getting health status: %s", e)
            return {}

    def get_status_summary(self) -> str:
        """Get a simple status summary."""
        if not self.data:
            return "⏳ Initialisierung..."
        
        try:
            feeding = self.data.get("feeding_status", {})
            activity = self.data.get("activity_status", {})
            
            needs_feeding = feeding.get("needs_feeding", True)
            needs_walk = activity.get("needs_walk", True)
            
            if not needs_feeding and not needs_walk:
                return "✅ Alles erledigt"
            elif needs_feeding and needs_walk:
                return "⏰ Fütterung & Spaziergang ausstehend"
            elif needs_feeding:
                return "🍽️ Fütterung ausstehend"
            elif needs_walk:
                return "🚶 Spaziergang ausstehend"
            else:
                return "👍 Gut"
                
        except Exception as e:
            _LOGGER.error("Error getting status summary: %s", e)
            return "❓ Unbekannt"
