
"""Number entities for Paw Control (weight & medication doses)."""
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    dogs = (entry.options or {}).get("dogs", [])
    entities: list[NumberEntity] = []
    for d in dogs:
        dog_id = d.get("dog_id") or d.get("name")
        title = d.get("name") or dog_id or "Dog"
        if not dog_id:
            continue
        entities.append(WeightNumber(hass, dog_id, title))
        entities.append(MedicationDoseNumber(hass, dog_id, title))
        entities.append(MedicationFrequencyHoursNumber(hass, dog_id, title))
        for i in (1,2,3):
            entities.append(MedicationDoseNumberSlot(hass, dog_id, title, i))
    if entities:
        async_add_entities(entities)

class _BaseDogNumber(NumberEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.AUTO

    def __init__(self, hass: HomeAssistant, dog_id: str, title: str, key: str):
        self.hass = hass
        self._dog = dog_id
        self._name = title
        self._key = key
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.number.{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, dog_id)}, name=f"Hund {title}", manufacturer="Paw Control", model="Number" )
        self._attr_entity_category = "config"
        self._attr_native_value: float | None = None

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown","unavailable", None):
            try:
                self._attr_native_value = float(last.state)
            except Exception:
                pass

    @property
    def native_value(self) -> float | None:
        return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = float(value)
        self.async_write_ha_state()

class WeightNumber(_BaseDogNumber):
    _attr_native_min_value = 0.5
    _attr_native_max_value = 120.0
    _attr_native_step = 0.1
    _attr_unit_of_measurement = "kg"
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "weight")

class MedicationDoseNumber(_BaseDogNumber):
    _attr_native_min_value = 0.0
    _attr_native_max_value = 5000.0
    _attr_native_step = 0.1
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "medication_dose")

class MedicationFrequencyHoursNumber(_BaseDogNumber):
    _attr_native_min_value = 1
    _attr_native_max_value = 48
    _attr_native_step = 1
    _attr_unit_of_measurement = "h"
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "medication_frequency_hours")

class MedicationDoseNumberSlot(_BaseDogNumber):
    _attr_native_min_value = 0.0
    _attr_native_max_value = 5000.0
    _attr_native_step = 0.1
    def __init__(self, hass, dog_id, title, index: int):
        super().__init__(hass, dog_id, title, f"medication_dose_{index}")
        self._idx = index
