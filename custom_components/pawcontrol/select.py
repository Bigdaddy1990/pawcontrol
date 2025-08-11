"""Select platform for Paw Control integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_MODULES,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_GROOMING,
    MODULE_TRAINING,
    FOOD_DRY,
    FOOD_WET,
    FOOD_BARF,
    FOOD_TREAT,
    GROOMING_BATH,
    GROOMING_BRUSH,
    GROOMING_TRIM,
    GROOMING_NAILS,
    GROOMING_EARS,
    GROOMING_TEETH,
    GROOMING_EYES,
    INTENSITY_LOW,
    INTENSITY_MEDIUM,
    INTENSITY_HIGH,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control select entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    entities = []
    dogs = entry.options.get(CONF_DOGS, [])
    
    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue
        
        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})
        
        # Feeding module selects
        if modules.get(MODULE_FEEDING):
            entities.extend([
                DefaultFoodTypeSelect(hass, coordinator, dog_id, dog_name),
                PreferredMealTimeSelect(hass, coordinator, dog_id, dog_name),
            ])
        
        # Grooming module selects
        if modules.get(MODULE_GROOMING):
            entities.append(
                DefaultGroomingTypeSelect(hass, coordinator, dog_id, dog_name)
            )
        
        # Training module selects
        if modules.get(MODULE_TRAINING):
            entities.extend([
                TrainingTopicSelect(hass, coordinator, dog_id, dog_name),
                TrainingIntensitySelect(hass, coordinator, dog_id, dog_name),
            ])
        
        # Activity level select (always available)
        entities.append(
            ActivityLevelSelect(hass, coordinator, dog_id, dog_name)
        )
    
    # Global selects
    entities.append(
        ExportFormatSelect(hass, coordinator, entry)
    )
    
    async_add_entities(entities, True)


class PawControlSelectBase(SelectEntity):
    """Base class for Paw Control select entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: Any,
        dog_id: str,
        dog_name: str,
        select_type: str,
        name: str,
        icon: str,
        options: list[str],
    ) -> None:
        """Initialize the select entity."""
        self.hass = hass
        self.coordinator = coordinator
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._select_type = select_type
        
        self._attr_name = name
        self._attr_icon = icon
        self._attr_options = options
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.select.{select_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=f"🐕 {dog_name}",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    @property
    def dog_data(self) -> dict:
        """Get dog data from coordinator."""
        return self.coordinator.get_dog_data(self._dog_id)


class DefaultFoodTypeSelect(PawControlSelectBase):
    """Select entity for default food type."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the select entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "default_food_type",
            "Default Food Type",
            "mdi:food",
            [FOOD_DRY, FOOD_WET, FOOD_BARF, FOOD_TREAT],
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return FOOD_DRY

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        _LOGGER.info(f"Default food type for {self._dog_name} set to {option}")


class PreferredMealTimeSelect(PawControlSelectBase):
    """Select entity for preferred meal schedule."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the select entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "meal_schedule",
            "Meal Schedule",
            "mdi:clock-outline",
            ["2 meals", "3 meals", "Free feeding"],
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return "3 meals"

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        _LOGGER.info(f"Meal schedule for {self._dog_name} set to {option}")


class DefaultGroomingTypeSelect(PawControlSelectBase):
    """Select entity for default grooming type."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the select entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "default_grooming_type",
            "Default Grooming Type",
            "mdi:content-cut",
            [GROOMING_BATH, GROOMING_BRUSH, GROOMING_TRIM, GROOMING_NAILS, 
             GROOMING_EARS, GROOMING_TEETH, GROOMING_EYES],
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.dog_data.get("grooming", {}).get("grooming_type", GROOMING_BRUSH)

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        _LOGGER.info(f"Default grooming type for {self._dog_name} set to {option}")
        self.dog_data["grooming"]["grooming_type"] = option
        await self.coordinator.async_request_refresh()


class TrainingTopicSelect(PawControlSelectBase):
    """Select entity for training topic."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the select entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "training_topic",
            "Training Topic",
            "mdi:school",
            ["Basic Commands", "Leash Training", "Tricks", "Agility", 
             "Socialization", "House Training", "Behavior Correction"],
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.dog_data.get("training", {}).get("last_topic", "Basic Commands")

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        _LOGGER.info(f"Training topic for {self._dog_name} set to {option}")


class TrainingIntensitySelect(PawControlSelectBase):
    """Select entity for training intensity."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the select entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "training_intensity",
            "Training Intensity",
            "mdi:speedometer",
            [INTENSITY_LOW, INTENSITY_MEDIUM, INTENSITY_HIGH],
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return INTENSITY_MEDIUM

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        _LOGGER.info(f"Training intensity for {self._dog_name} set to {option}")


class ActivityLevelSelect(PawControlSelectBase):
    """Select entity for activity level."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the select entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "activity_level_setting",
            "Activity Level Setting",
            "mdi:run",
            [INTENSITY_LOW, INTENSITY_MEDIUM, INTENSITY_HIGH],
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.dog_data.get("activity", {}).get("activity_level", INTENSITY_MEDIUM)

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        _LOGGER.info(f"Activity level for {self._dog_name} set to {option}")
        self.dog_data["activity"]["activity_level"] = option
        await self.coordinator.async_request_refresh()


class ExportFormatSelect(SelectEntity):
    """Select entity for export format.

    The available formats are defined as an immutable tuple to prevent
    accidental modification.
    """

    _attr_has_entity_name = True
    _attr_name = "Export Format"
    _attr_icon = "mdi:file-export"
    _attr_options = ("csv", "json", "pdf")

    def __init__(self, hass: HomeAssistant, coordinator: Any, entry: ConfigEntry):
        """Initialize the select entity."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry

        self._attr_unique_id = f"{DOMAIN}.global.select.export_format"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.entry.options.get("export_format", "csv")

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        _LOGGER.info("Export format set to %s", option)
