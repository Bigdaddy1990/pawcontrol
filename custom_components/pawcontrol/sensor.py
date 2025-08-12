"""Sensors for Paw Control."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .sensor_factory import create_dog_sensors

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for each configured dog."""
    dogs = (entry.options or {}).get("dogs", [])
    entities: list = []

    for dog_config in dogs:
        dog_id = dog_config.get("dog_id") or dog_config.get("name")
        title = dog_config.get("name") or dog_id or "Dog"

        if not dog_id:
            continue

        # Use factory pattern to create all sensors
        dog_sensors = create_dog_sensors(hass, dog_id, title)
        entities.extend(dog_sensors)

    if entities:
        async_add_entities(entities)
