"""Button platform for Paw Control - REPARIERT UND VEREINFACHT."""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PawControlCoordinator
from .entities import PawControlButtonEntity
from .helpers.entity import get_icon

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    dog_name = coordinator.dog_name
    
    entities = [
        # Feeding buttons
        PawControlFeedMorningButton(coordinator, dog_name),
        PawControlFeedEveningButton(coordinator, dog_name),

        # Activity buttons
        PawControlMarkOutsideButton(coordinator, dog_name),
        PawControlMarkPoopDoneButton(coordinator, dog_name),

        # System buttons
        PawControlResetDailyDataButton(coordinator, dog_name),
        PawControlEmergencyButton(coordinator, dog_name),
        PawControlVisitorModeButton(coordinator, dog_name),

        # GPS buttons
        PawControlUpdateGPSButton(coordinator, dog_name),
    ]
    
    async_add_entities(entities)


# FEEDING BUTTONS

class PawControlFeedMorningButton(PawControlButtonEntity):
    """Button to mark morning feeding."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the button."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="feed_morning",
            icon=get_icon("morning"),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._safe_service_call("input_boolean", "turn_on", {
                "entity_id": f"input_boolean.{self._dog_name}_feeding_morning"
            })
            await self._safe_service_call("counter", "increment", {
                "entity_id": f"counter.{self._dog_name}_feeding_count"
            })
            await self._safe_service_call("input_datetime", "set_datetime", {
                "entity_id": f"input_datetime.{self._dog_name}_last_feeding",
                "datetime": datetime.now().isoformat()
            })
            
            _LOGGER.info("Morning feeding recorded for %s", self._dog_name)
        except Exception as e:
            _LOGGER.error("Failed to record morning feeding for %s: %s", self._dog_name, e)


class PawControlFeedEveningButton(PawControlButtonEntity):
    """Button to mark evening feeding."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the button."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="feed_evening",
            icon=get_icon("evening"),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._safe_service_call("input_boolean", "turn_on", {
                "entity_id": f"input_boolean.{self._dog_name}_feeding_evening"
            })
            await self._safe_service_call("counter", "increment", {
                "entity_id": f"counter.{self._dog_name}_feeding_count"
            })
            await self._safe_service_call("input_datetime", "set_datetime", {
                "entity_id": f"input_datetime.{self._dog_name}_last_feeding",
                "datetime": datetime.now().isoformat()
            })
            
            _LOGGER.info("Evening feeding recorded for %s", self._dog_name)
        except Exception as e:
            _LOGGER.error("Failed to record evening feeding for %s: %s", self._dog_name, e)


# ACTIVITY BUTTONS

class PawControlMarkOutsideButton(PawControlButtonEntity):
    """Button to mark dog as outside."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the button."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="mark_outside",
            icon=get_icon("outside"),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._safe_service_call("input_boolean", "turn_on", {
                "entity_id": f"input_boolean.{self._dog_name}_outside"
            })
            await self._safe_service_call("counter", "increment", {
                "entity_id": f"counter.{self._dog_name}_outside_count"
            })
            await self._safe_service_call("input_datetime", "set_datetime", {
                "entity_id": f"input_datetime.{self._dog_name}_last_outside",
                "datetime": datetime.now().isoformat()
            })
            
            _LOGGER.info("Marked %s as outside", self._dog_name)
        except Exception as e:
            _LOGGER.error("Failed to mark %s as outside: %s", self._dog_name, e)


class PawControlMarkPoopDoneButton(PawControlButtonEntity):
    """Button to mark poop as done."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the button."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="mark_poop_done",
            icon=get_icon("poop"),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._safe_service_call("input_boolean", "turn_on", {
                "entity_id": f"input_boolean.{self._dog_name}_poop_done"
            })
            await self._safe_service_call("input_boolean", "turn_on", {
                "entity_id": f"input_boolean.{self._dog_name}_walked_today"
            })
            await self._safe_service_call("counter", "increment", {
                "entity_id": f"counter.{self._dog_name}_walk_count"
            })
            
            _LOGGER.info("Poop marked as done for %s", self._dog_name)
        except Exception as e:
            _LOGGER.error("Failed to mark poop done for %s: %s", self._dog_name, e)


# SYSTEM BUTTONS

class PawControlResetDailyDataButton(PawControlButtonEntity):
    """Button to reset daily data."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the button."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="reset_daily_data",
            icon="mdi:refresh",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            # Reset boolean entities
            boolean_entities = [
                f"input_boolean.{self._dog_name}_feeding_morning",
                f"input_boolean.{self._dog_name}_feeding_evening",
                f"input_boolean.{self._dog_name}_outside",
                f"input_boolean.{self._dog_name}_walked_today",
                f"input_boolean.{self._dog_name}_poop_done",
            ]
            
            for entity_id in boolean_entities:
                await self._safe_service_call("input_boolean", "turn_off", {"entity_id": entity_id})
            
            # Reset counters
            counter_entities = [
                f"counter.{self._dog_name}_walk_count",
                f"counter.{self._dog_name}_outside_count",
                f"counter.{self._dog_name}_feeding_count",
            ]
            
            for entity_id in counter_entities:
                await self._safe_service_call("counter", "reset", {"entity_id": entity_id})
            
            _LOGGER.info("Daily data reset for %s", self._dog_name)
        except Exception as e:
            _LOGGER.error("Failed to reset daily data for %s: %s", self._dog_name, e)


class PawControlEmergencyButton(PawControlButtonEntity):
    """Button for emergency situations."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the button."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="emergency",
            icon=get_icon("emergency"),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._safe_service_call("input_boolean", "turn_on", {
                "entity_id": f"input_boolean.{self._dog_name}_emergency_mode"
            })
            
            # Add emergency note
            await self._safe_service_call("input_text", "set_value", {
                "entity_id": f"input_text.{self._dog_name}_notes",
                "value": f"NOTFALL aktiviert um {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            })
            
            _LOGGER.warning("EMERGENCY activated for %s", self._dog_name)
        except Exception as e:
            _LOGGER.error("Failed to activate emergency for %s: %s", self._dog_name, e)


class PawControlVisitorModeButton(PawControlButtonEntity):
    """Button to toggle visitor mode."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the button."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="visitor_mode",
            icon=get_icon("visitor"),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            # Toggle visitor mode
            visitor_state = self.hass.states.get(f"input_boolean.{self._dog_name}_visitor_mode")
            current_state = visitor_state.state == "on" if visitor_state else False
            
            if current_state:
                await self._safe_service_call("input_boolean", "turn_off", {
                    "entity_id": f"input_boolean.{self._dog_name}_visitor_mode"
                })
                await self._safe_service_call("input_text", "set_value", {
                    "entity_id": f"input_text.{self._dog_name}_notes",
                    "value": f"Besuchsmodus deaktiviert um {datetime.now().strftime('%H:%M')}"
                })
                _LOGGER.info("Visitor mode deactivated for %s", self._dog_name)
            else:
                await self._safe_service_call("input_boolean", "turn_on", {
                    "entity_id": f"input_boolean.{self._dog_name}_visitor_mode"
                })
                await self._safe_service_call("input_text", "set_value", {
                    "entity_id": f"input_text.{self._dog_name}_notes",
                    "value": f"Besuchsmodus aktiviert um {datetime.now().strftime('%H:%M')}"
                })
                _LOGGER.info("Visitor mode activated for %s", self._dog_name)
                
        except Exception as e:
            _LOGGER.error("Failed to toggle visitor mode for %s: %s", self._dog_name, e)


# GPS BUTTONS

class PawControlUpdateGPSButton(PawControlButtonEntity):
    """Button to update GPS location."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the button."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="update_gps",
            icon=get_icon("gps"),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            # Set GPS signal to 100% (simulated manual update)
            await self._safe_service_call("input_number", "set_value", {
                "entity_id": f"input_number.{self._dog_name}_gps_signal_strength",
                "value": 100
            })
            
            # Update location with placeholder
            await self._safe_service_call("input_text", "set_value", {
                "entity_id": f"input_text.{self._dog_name}_current_location",
                "value": f"Manuell aktualisiert um {datetime.now().strftime('%H:%M')}"
            })
            
            _LOGGER.info("GPS updated for %s", self._dog_name)
        except Exception as e:
            _LOGGER.error("Failed to update GPS for %s: %s", self._dog_name, e)