"""Button platform for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    ICON_FOOD,
    ICON_WALK,
    ICON_EMERGENCY,
    SERVICE_FEED_DOG,
    SERVICE_START_WALK,
    SERVICE_EMERGENCY,
    SERVICE_RESET_DATA,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl button entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for dog_name, dog_data in entry_data.items():
        coordinator = dog_data["coordinator"]
        config = dog_data["config"]
        
        # Add module-specific buttons
        modules = config.get("modules", {})
        
        if modules.get("feeding", {}).get("enabled", False):
            entities.extend([
                PawControlFeedBreakfastButton(hass, coordinator, config),
                PawControlFeedDinnerButton(hass, coordinator, config),
                PawControlQuickFeedButton(hass, coordinator, config),
            ])
        
        if modules.get("walk", {}).get("enabled", False):
            entities.extend([
                PawControlStartWalkButton(hass, coordinator, config),
                PawControlMarkOutsideButton(hass, coordinator, config),
            ])
        
        # Always add emergency and reset buttons
        entities.extend([
            PawControlEmergencyButton(hass, coordinator, config),
            PawControlResetDailyDataButton(hass, coordinator, config),
        ])
        
        if modules.get("gps", {}).get("enabled", False):
            entities.append(PawControlUpdateGPSButton(hass, coordinator, config))
    
    async_add_entities(entities)


class PawControlButtonBase(CoordinatorEntity, ButtonEntity):
    """Base class for PawControl buttons."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        config: dict[str, Any],
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.hass = hass
        self._config = config
        self._dog_name = config.get(CONF_DOG_NAME, "Unknown")
        self._dog_id = self._dog_name.lower().replace(" ", "_")

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._dog_id)},
            "name": f"PawControl - {self._dog_name}",
            "manufacturer": "PawControl",
            "model": "Dog Management System",
            "sw_version": "1.0.0",
        }


class PawControlFeedBreakfastButton(PawControlButtonBase):
    """Button to mark breakfast feeding."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_feed_breakfast"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Frühstück füttern"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_FOOD

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_FEED_DOG,
            {
                "dog_name": self._dog_name,
                "meal_type": "breakfast",
            },
            blocking=False,
        )
        _LOGGER.info(f"Marked breakfast feeding for {self._dog_name}")


class PawControlFeedDinnerButton(PawControlButtonBase):
    """Button to mark dinner feeding."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_feed_dinner"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Abendessen füttern"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_FOOD

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_FEED_DOG,
            {
                "dog_name": self._dog_name,
                "meal_type": "dinner",
            },
            blocking=False,
        )
        _LOGGER.info(f"Marked dinner feeding for {self._dog_name}")


class PawControlQuickFeedButton(PawControlButtonBase):
    """Button for quick feeding (auto-detect meal type)."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_quick_feed"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Jetzt füttern"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:food-drumstick-outline"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_FEED_DOG,
            {
                "dog_name": self._dog_name,
                "meal_type": "auto",
            },
            blocking=False,
        )
        _LOGGER.info(f"Quick feed for {self._dog_name}")


class PawControlStartWalkButton(PawControlButtonBase):
    """Button to start a walk."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_start_walk"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Spaziergang starten"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_WALK

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_START_WALK,
            {
                "dog_name": self._dog_name,
                "walk_type": "Normal",
            },
            blocking=False,
        )
        _LOGGER.info(f"Started walk for {self._dog_name}")


class PawControlMarkOutsideButton(PawControlButtonBase):
    """Button to mark dog as outside."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_mark_outside"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Als draußen markieren"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:nature"

    async def async_press(self) -> None:
        """Handle the button press."""
        # Update coordinator status
        self.coordinator._data["status"]["is_outside"] = True
        await self.coordinator.async_request_refresh()
        
        # Update helper if exists
        entity_id = f"input_boolean.pawcontrol_{self._dog_id}_is_outside"
        await self.hass.services.async_call(
            "input_boolean",
            "turn_on",
            {"entity_id": entity_id},
            blocking=False,
        )
        _LOGGER.info(f"Marked {self._dog_name} as outside")


class PawControlEmergencyButton(PawControlButtonBase):
    """Button to trigger emergency mode."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_emergency"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} NOTFALL"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_EMERGENCY

    async def async_press(self) -> None:
        """Handle the button press."""
        # Toggle emergency mode
        current_state = self.coordinator.data.get("status", {}).get("emergency_mode", False)
        
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_EMERGENCY,
            {
                "dog_name": self._dog_name,
                "activate": not current_state,
                "reason": "Manuell ausgelöst" if not current_state else None,
            },
            blocking=False,
        )
        _LOGGER.warning(f"Emergency mode {'activated' if not current_state else 'deactivated'} for {self._dog_name}")


class PawControlResetDailyDataButton(PawControlButtonBase):
    """Button to reset daily data."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_reset_daily"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Tagesdaten zurücksetzen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:restart"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_RESET_DATA,
            {
                "dog_name": self._dog_name,
                "confirm": "RESET",
                "reset_type": "daily",
            },
            blocking=False,
        )
        _LOGGER.info(f"Reset daily data for {self._dog_name}")


class PawControlUpdateGPSButton(PawControlButtonBase):
    """Button to update GPS location."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_update_gps"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} GPS aktualisieren"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:crosshairs-gps"

    async def async_press(self) -> None:
        """Handle the button press."""
        # This would trigger a GPS update
        # For now, just log it
        _LOGGER.info(f"GPS update requested for {self._dog_name}")
        
        # Could integrate with actual GPS tracking here
        # For example, get home location and update
        home = self.hass.states.get("zone.home")
        if home:
            lat = home.attributes.get("latitude")
            lon = home.attributes.get("longitude")
            
            await self.hass.services.async_call(
                DOMAIN,
                "update_gps",
                {
                    "dog_name": self._dog_name,
                    "latitude": lat,
                    "longitude": lon,
                    "accuracy": 10,
                    "source": "Home Zone",
                },
                blocking=False,
            )
