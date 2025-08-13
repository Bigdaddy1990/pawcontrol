from __future__ import annotations

from datetime import datetime, timezone
from typing import Final

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .compat import DeviceInfo
from .const import DOMAIN

PARALLEL_UPDATES: Final = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up datetime entities from a config entry."""
    dogs = entry.options.get("dogs", [])
    entities = [
        NextMedicationDateTime(
            hass,
            d.get("dog_id") or d.get("name"),
            d.get("name") or (d.get("dog_id") or "dog"),
        )
        for d in dogs
    ]
    async_add_entities(entities, update_before_add=False)


class NextMedicationDateTime(DateTimeEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, dog_id: str, title: str):
        self.hass = hass
        self._dog = dog_id
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.datetime.next_medication"
        self._attr_name = "Nächste Medikation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)}, name=f"Hund {title}"
        )
        st = hass.states.get(f"datetime.{DOMAIN}_{dog_id}_next_medication")
        try:
            self._dt = (
                datetime.fromisoformat(st.state.replace("Z", "+00:00"))
                if st and st.state and st.state not in ("unknown", "unavailable")
                else None
            )
        except (AttributeError, TypeError, ValueError):
            # Invalid or unexpected state format
            self._dt = None

    @property
    def native_value(self) -> datetime | None:
        return self._dt

    async def async_set_value(self, value: datetime) -> None:
        # Store as ISO string in HA state (UTC)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        self._dt = value
        self.hass.states.async_set(
            f"datetime.{DOMAIN}_{self._dog}_next_medication", value.isoformat()
        )
        self.async_write_ha_state()
