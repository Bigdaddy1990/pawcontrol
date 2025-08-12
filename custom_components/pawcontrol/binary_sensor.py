
from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    dogs = (entry.options or {}).get("dogs", [])
    ents: list[SafeZoneBinarySensor] = []
    for d in dogs:
        dog_id = d.get("dog_id") or d.get("name")
        name = d.get("name") or dog_id or "Dog"
        if not dog_id:
            continue
        ents.append(SafeZoneBinarySensor(hass, dog_id, name))
    if ents:
        async_add_entities(ents, update_before_add=False)

class SafeZoneBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY  # ON = inside (occupied)

    def __init__(self, hass: HomeAssistant, dog_id: str, title: str):
        self.hass = hass
        self._dog = dog_id
        self._title = title
        self._inside: bool | None = None
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.binary_sensor.safe_zone"
        self._attr_name = "In Sicherheitszone"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, dog_id)}, name=f"Hund {title}", manufacturer="Paw Control", model="Safe Zone")
        self._last_dist = None
        self._radius = None

    async def async_added_to_hass(self) -> None:
        sig = f"pawcontrol_safe_zone_update_{self._dog}"
        self.async_on_remove(async_dispatcher_connect(self.hass, sig, self._on_update))

    def _on_update(self, inside: bool, distance_m: float, radius_m: float):
        self._inside = bool(inside)
        self._last_dist = distance_m
        self._radius = radius_m
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        return self._inside

    @property
    def extra_state_attributes(self):
        return {"distance_m": self._last_dist, "radius_m": self._radius}
