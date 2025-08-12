
"""Select entities for Paw Control medication units/types."""
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN

UNITS = ["mg","ml","pcs"]
TYPES = ["pill","liquid","powder"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    dogs = (entry.options or {}).get("dogs", [])
    entities: list[SelectEntity] = []
    for d in dogs:
        dog_id = d.get("dog_id") or d.get("name")
        title = d.get("name") or dog_id or "Dog"
        if not dog_id:
            continue
        entities.append(MedicationUnitSelect(hass, dog_id, title))
        entities.append(MedicationTypeSelect(hass, dog_id, title))
        for i in (1,2,3):
            entities.append(MedicationUnitSelectSlot(hass, dog_id, title, i))
            entities.append(MedicationTypeSelectSlot(hass, dog_id, title, i))
    if entities:
        async_add_entities(entities)

class _BaseDogSelect(SelectEntity, RestoreEntity):
    _attr_has_entity_name = True
    def __init__(self, hass: HomeAssistant, dog_id: str, title: str, key: str, options: list[str]):
        self.hass = hass
        self._dog = dog_id
        self._name = title
        self._key = key
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.select.{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, dog_id)}, name=f"Hund {title}", manufacturer="Paw Control", model="Select" )
        self._attr_entity_category = "config"
        self._attr_options = options
        self._attr_current_option: str | None = None

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown","unavailable", None):
            self._attr_current_option = last.state

    @property
    def current_option(self) -> str | None:
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        if option in self._attr_options:
            self._attr_current_option = option
            self.async_write_ha_state()

class MedicationUnitSelect(_BaseDogSelect):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "medication_unit", UNITS)

class MedicationTypeSelect(_BaseDogSelect):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "medication_type", TYPES)

class MedicationUnitSelectSlot(_BaseDogSelect):
    def __init__(self, hass, dog_id, title, index: int): super().__init__(hass, dog_id, title, f"medication_unit_{index}", UNITS)

class MedicationTypeSelectSlot(_BaseDogSelect):
    def __init__(self, hass, dog_id, title, index: int): super().__init__(hass, dog_id, title, f"medication_type_{index}", TYPES)
