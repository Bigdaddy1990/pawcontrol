"""Select platform for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    HEALTH_STATUS_OPTIONS,
    MOOD_OPTIONS,
    ACTIVITY_LEVELS,
    SIZE_OPTIONS,
    FOOD_TYPES,
    WALK_TYPES,
    SERVICE_SET_MOOD,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl select entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for dog_name, dog_data in entry_data.items():
        coordinator = dog_data["coordinator"]
        config = dog_data["config"]
        
        # Always add basic selects
        entities.extend([
            PawControlHealthStatusSelect(hass, coordinator, config),
            PawControlMoodSelect(hass, coordinator, config),
            PawControlActivityLevelSelect(hass, coordinator, config),
            PawControlSizeCategorySelect(hass, coordinator, config),
        ])
        
        # Add module-specific selects
        modules = config.get("modules", {})
        
        if modules.get("feeding", {}).get("enabled", False):
            entities.append(PawControlFoodTypeSelect(hass, coordinator, config))
        
        if modules.get("walk", {}).get("enabled", False):
            entities.append(PawControlPreferredWalkTypeSelect(hass, coordinator, config))
    
    async_add_entities(entities)


class PawControlSelectBase(CoordinatorEntity, SelectEntity):
    """Base class for PawControl select entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        config: dict[str, Any],
    ) -> None:
        """Initialize the select entity."""
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


class PawControlHealthStatusSelect(PawControlSelectBase):
    """Select entity for health status."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_health_status_select"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gesundheitsstatus"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:medical-bag"

    @property
    def options(self):
        """Return the list of options."""
        return HEALTH_STATUS_OPTIONS

    @property
    def current_option(self):
        """Return the current option."""
        return self.coordinator.data.get("profile", {}).get("health_status", HEALTH_STATUS_OPTIONS[2])

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        self.coordinator._data["profile"]["health_status"] = option
        await self.coordinator.async_request_refresh()


class PawControlMoodSelect(PawControlSelectBase):
    """Select entity for mood."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_mood_select"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Stimmung"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:emoticon"

    @property
    def options(self):
        """Return the list of options."""
        return MOOD_OPTIONS

    @property
    def current_option(self):
        """Return the current option."""
        return self.coordinator.data.get("profile", {}).get("mood", MOOD_OPTIONS[0])

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_SET_MOOD,
            {
                "dog_name": self._dog_name,
                "mood": option,
            },
            blocking=False,
        )


class PawControlActivityLevelSelect(PawControlSelectBase):
    """Select entity for activity level."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_activity_level_select"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Aktivitätslevel"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:run"

    @property
    def options(self):
        """Return the list of options."""
        return ACTIVITY_LEVELS

    @property
    def current_option(self):
        """Return the current option."""
        return self.coordinator.data.get("profile", {}).get("activity_level", ACTIVITY_LEVELS[2])

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        self.coordinator._data["profile"]["activity_level"] = option
        await self.coordinator.async_request_refresh()


class PawControlSizeCategorySelect(PawControlSelectBase):
    """Select entity for size category."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_size_category_select"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Größenkategorie"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:arrow-expand-vertical"

    @property
    def options(self):
        """Return the list of options."""
        return SIZE_OPTIONS

    @property
    def current_option(self):
        """Return the current option."""
        return self.coordinator.data.get("profile", {}).get("size", SIZE_OPTIONS[2])

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        self.coordinator._data["profile"]["size"] = option
        await self.coordinator.async_request_refresh()


class PawControlFoodTypeSelect(PawControlSelectBase):
    """Select entity for food type."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_food_type_select"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Futterart"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:food-drumstick"

    @property
    def options(self):
        """Return the list of options."""
        return FOOD_TYPES

    @property
    def current_option(self):
        """Return the current option."""
        return self.coordinator.data.get("feeding", {}).get("food_type", FOOD_TYPES[0])

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        self.coordinator._data["feeding"]["food_type"] = option
        await self.coordinator.async_request_refresh()


class PawControlPreferredWalkTypeSelect(PawControlSelectBase):
    """Select entity for preferred walk type."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_preferred_walk_type_select"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Bevorzugter Spaziergang"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:dog-service"

    @property
    def options(self):
        """Return the list of options."""
        return WALK_TYPES

    @property
    def current_option(self):
        """Return the current option."""
        return self.coordinator.data.get("settings", {}).get("preferred_walk_type", WALK_TYPES[1])

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        self.coordinator._data.setdefault("settings", {})["preferred_walk_type"] = option
        await self.coordinator.async_request_refresh()
