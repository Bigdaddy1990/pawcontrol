
"""Text entities for Paw Control medication names/notes."""
from __future__ import annotations
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.text import TextEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    dogs = (entry.options or {}).get("dogs", [])
    entities: list[TextEntity] = []
    for d in dogs:
        dog_id = d.get("dog_id") or d.get("name")
        title = d.get("name") or dog_id or "Dog"
        if not dog_id:
            continue
        entities.append(MedicationNameText(hass, dog_id, title))
        entities.append(MedicationNotesText(hass, dog_id, title))
        for i in (1,2,3):
            entities.append(MedicationNameTextSlot(hass, dog_id, title, i))
            entities.append(MedicationNotesTextSlot(hass, dog_id, title, i))
    if entities:
        async_add_entities(entities)

class _BaseDogText(TextEntity, RestoreEntity):
    _attr_has_entity_name = True
    def __init__(self, hass: HomeAssistant, dog_id: str, title: str, key: str):
        self.hass = hass
        self._dog = dog_id
        self._name = title
        self._key = key
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.text.{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, dog_id)}, name=f"Hund {title}", manufacturer="Paw Control", model="Text" )
        self._attr_entity_category = "config"
        self._attr_native_value: str | None = None

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown","unavailable", None):
            self._attr_native_value = last.state

    @property
    def native_value(self) -> str | None:
        return self._attr_native_value

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value or ""
        self.async_write_ha_state()

class MedicationNameText(_BaseDogText):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "medication_name")

class MedicationNotesText(_BaseDogText):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "medication_notes")

class MedicationNameTextSlot(_BaseDogText):
    def __init__(self, hass, dog_id, title, index: int): super().__init__(hass, dog_id, title, f"medication_name_{index}")

class MedicationNotesTextSlot(_BaseDogText):
    def __init__(self, hass, dog_id, title, index: int): super().__init__(hass, dog_id, title, f"medication_notes_{index}")
