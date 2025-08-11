"""Text platform for Paw Control integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.text import TextEntity
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
    MODULE_HEALTH,
    MODULE_TRAINING,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control text entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    entities = []
    dogs = entry.options.get(CONF_DOGS, [])
    
    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue
        
        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})
        
        # Health module text entities
        if modules.get(MODULE_HEALTH):
            entities.extend([
                HealthNotesText(hass, coordinator, dog_id, dog_name),
                MedicationNotesText(hass, coordinator, dog_id, dog_name),
                VetNotesText(hass, coordinator, dog_id, dog_name),
            ])
        
        # Training module text entities
        if modules.get(MODULE_TRAINING):
            entities.append(
                TrainingNotesText(hass, coordinator, dog_id, dog_name)
            )
        
        # Always add general notes
        entities.append(
            GeneralNotesText(hass, coordinator, dog_id, dog_name)
        )
    
    # Global text entities
    entities.append(
        ExportPathText(hass, coordinator, entry)
    )
    
    async_add_entities(entities, True)


class PawControlTextBase(TextEntity):
    """Base class for Paw Control text entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: Any,
        dog_id: str,
        dog_name: str,
        text_type: str,
        name: str,
        icon: str,
        max_length: int = 255,
    ) -> None:
        """Initialize the text entity."""
        self.hass = hass
        self.coordinator = coordinator
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._text_type = text_type
        self._stored_value = ""
        
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_max = max_length
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.text.{text_type}"
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

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        return self._stored_value

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        self._stored_value = value
        _LOGGER.info(f"{self._attr_name} for {self._dog_name} updated")


class HealthNotesText(PawControlTextBase):
    """Text entity for health notes."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the text entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "health_notes",
            "Health Notes",
            "mdi:note-medical",
            1000,
        )

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        notes = self.dog_data.get("health", {}).get("health_notes", [])
        if notes:
            # Return the most recent note
            return notes[-1].get("note", "")
        return ""

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        await self.hass.services.async_call(
            DOMAIN,
            "log_health_data",
            {
                "dog_id": self._dog_id,
                "note": value,
            },
            blocking=False,
        )


class MedicationNotesText(PawControlTextBase):
    """Text entity for medication notes."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the text entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "medication_notes",
            "Medication Notes",
            "mdi:pill",
            500,
        )

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        return f"{self.dog_data.get('health', {}).get('medication_name', '')} - {self.dog_data.get('health', {}).get('medication_dose', '')}"


class VetNotesText(PawControlTextBase):
    """Text entity for vet notes."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the text entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "vet_notes",
            "Vet Notes",
            "mdi:hospital-box",
            1000,
        )


class TrainingNotesText(PawControlTextBase):
    """Text entity for training notes."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the text entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "training_notes",
            "Training Notes",
            "mdi:school",
            500,
        )

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        history = self.dog_data.get("training", {}).get("training_history", [])
        if history:
            # Return the most recent training note
            return history[-1].get("notes", "")
        return ""


class GeneralNotesText(PawControlTextBase):
    """Text entity for general notes."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the text entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "general_notes",
            "General Notes",
            "mdi:note-text",
            1000,
        )


class ExportPathText(TextEntity):
    """Text entity for export path."""

    _attr_has_entity_name = True
    _attr_name = "Export Path"
    _attr_icon = "mdi:folder-export"
    _attr_native_max = 255

    def __init__(self, hass: HomeAssistant, coordinator: Any, entry: ConfigEntry):
        """Initialize the text entity."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        
        self._attr_unique_id = f"{DOMAIN}.global.text.export_path"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        return self.entry.options.get("export_path", "")

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        _LOGGER.info(f"Export path set to {value}")
        # Would update the config entry options
