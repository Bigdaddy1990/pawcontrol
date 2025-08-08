"""Text platform for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl text entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for dog_name, dog_data in entry_data.items():
        coordinator = dog_data["coordinator"]
        config = dog_data["config"]
        
        # Always add basic text entities
        entities.extend([
            PawControlBreedText(coordinator, config),
            PawControlNotesText(coordinator, config),
            PawControlDailyNotesText(coordinator, config),
        ])
        
        # Add module-specific text entities
        modules = config.get("modules", {})
        
        if modules.get("health", {}).get("enabled", False):
            entities.extend([
                PawControlHealthNotesText(coordinator, config),
                PawControlMedicationNotesText(coordinator, config),
                PawControlVetContactText(coordinator, config),
                PawControlSymptomsText(coordinator, config),
            ])
        
        if modules.get("gps", {}).get("enabled", False):
            entities.extend([
                PawControlCurrentLocationText(coordinator, config),
                PawControlHomeCoordinatesText(coordinator, config),
            ])
        
        if modules.get("walk", {}).get("enabled", False):
            entities.extend([
                PawControlWalkNotesText(coordinator, config),
                PawControlFavoriteRoutesText(coordinator, config),
            ])
        
        if modules.get("visitor", {}).get("enabled", False):
            entities.extend([
                PawControlVisitorNameText(coordinator, config),
                PawControlVisitorInstructionsText(coordinator, config),
            ])
    
    async_add_entities(entities)


class PawControlTextBase(CoordinatorEntity, TextEntity):
    """Base class for PawControl text entities."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        config: dict[str, Any],
        max_length: int = 255,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator)
        self._config = config
        self._dog_name = config.get(CONF_DOG_NAME, "Unknown")
        self._dog_id = self._dog_name.lower().replace(" ", "_")
        self._attr_native_max = max_length

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


class PawControlBreedText(PawControlTextBase):
    """Text entity for dog breed."""

    def __init__(self, coordinator: PawControlCoordinator, config: dict[str, Any]):
        """Initialize the breed text entity."""
        super().__init__(coordinator, config, max_length=100)

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_breed"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Rasse"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:dog"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("profile", {}).get("breed", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data["profile"]["breed"] = value
        await self.coordinator.async_request_refresh()


class PawControlNotesText(PawControlTextBase):
    """Text entity for general notes."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_notes"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Notizen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:note-text"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("notes", {}).get("general", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("notes", {})["general"] = value
        await self.coordinator.async_request_refresh()


class PawControlDailyNotesText(PawControlTextBase):
    """Text entity for daily notes."""

    def __init__(self, coordinator: PawControlCoordinator, config: dict[str, Any]):
        """Initialize the daily notes text entity."""
        super().__init__(coordinator, config, max_length=500)

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_daily_notes"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Tägliche Notizen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-text"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("notes", {}).get("daily", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("notes", {})["daily"] = value
        await self.coordinator.async_request_refresh()


class PawControlHealthNotesText(PawControlTextBase):
    """Text entity for health notes."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_health_notes"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gesundheitsnotizen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:medical-bag"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("health", {}).get("notes", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data["health"]["notes"] = value
        await self.coordinator.async_request_refresh()


class PawControlMedicationNotesText(PawControlTextBase):
    """Text entity for medication notes."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_medication_notes"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Medikationsnotizen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:pill"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("health", {}).get("medication_notes", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data["health"]["medication_notes"] = value
        await self.coordinator.async_request_refresh()


class PawControlVetContactText(PawControlTextBase):
    """Text entity for vet contact."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_vet_contact"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Tierarztkontakt"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:hospital-box"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("health", {}).get("vet_contact", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data["health"]["vet_contact"] = value
        await self.coordinator.async_request_refresh()


class PawControlSymptomsText(PawControlTextBase):
    """Text entity for symptoms."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_symptoms"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Symptome"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:thermometer-alert"

    @property
    def native_value(self):
        """Return the current value."""
        symptoms = self.coordinator.data.get("health", {}).get("symptoms", [])
        return ", ".join(symptoms) if symptoms else ""

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        symptoms = [s.strip() for s in value.split(",") if s.strip()] if value else []
        await self.coordinator.async_update_health(symptoms=symptoms)


class PawControlCurrentLocationText(PawControlTextBase):
    """Text entity for current location."""

    def __init__(self, coordinator: PawControlCoordinator, config: dict[str, Any]):
        """Initialize the location text entity."""
        super().__init__(coordinator, config, max_length=100)

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_current_location"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Aktueller Standort"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:map-marker"

    @property
    def native_value(self):
        """Return the current value."""
        location = self.coordinator.data.get("location", {}).get("current")
        if location:
            lat = location.get("latitude", 0)
            lon = location.get("longitude", 0)
            return f"{lat:.5f}, {lon:.5f}"
        return ""

    async def async_set_value(self, value: str) -> None:
        """Set the value (parse coordinates)."""
        try:
            parts = value.split(",")
            if len(parts) == 2:
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                await self.coordinator.async_update_location(lat, lon)
        except (ValueError, IndexError):
            _LOGGER.error(f"Invalid coordinates format: {value}")


class PawControlHomeCoordinatesText(PawControlTextBase):
    """Text entity for home coordinates."""

    def __init__(self, coordinator: PawControlCoordinator, config: dict[str, Any]):
        """Initialize the home coordinates text entity."""
        super().__init__(coordinator, config, max_length=50)

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_home_coordinates"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Heimkoordinaten"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:home-map-marker"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("location", {}).get("home", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data["location"]["home"] = value
        await self.coordinator.async_request_refresh()


class PawControlWalkNotesText(PawControlTextBase):
    """Text entity for walk notes."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_walk_notes"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Spaziergang-Notizen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:dog-service"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("notes", {}).get("walk", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("notes", {})["walk"] = value
        await self.coordinator.async_request_refresh()


class PawControlFavoriteRoutesText(PawControlTextBase):
    """Text entity for favorite routes."""

    def __init__(self, coordinator: PawControlCoordinator, config: dict[str, Any]):
        """Initialize the favorite routes text entity."""
        super().__init__(coordinator, config, max_length=1000)

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_favorite_routes"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Lieblingsrouten"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:map-marker-path"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("walk", {}).get("favorite_routes", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("walk", {})["favorite_routes"] = value
        await self.coordinator.async_request_refresh()


class PawControlVisitorNameText(PawControlTextBase):
    """Text entity for visitor name."""

    def __init__(self, coordinator: PawControlCoordinator, config: dict[str, Any]):
        """Initialize the visitor name text entity."""
        super().__init__(coordinator, config, max_length=100)

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_visitor_name"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Besuchername"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:account"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("status", {}).get("visitor_name", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data["status"]["visitor_name"] = value
        await self.coordinator.async_request_refresh()


class PawControlVisitorInstructionsText(PawControlTextBase):
    """Text entity for visitor instructions."""

    def __init__(self, coordinator: PawControlCoordinator, config: dict[str, Any]):
        """Initialize the visitor instructions text entity."""
        super().__init__(coordinator, config, max_length=500)

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_visitor_instructions"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Besucheranweisungen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:clipboard-text"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("status", {}).get("visitor_instructions", "")

    async def async_set_value(self, value: str) -> None:
        """Set the value."""
        self.coordinator._data["status"]["visitor_instructions"] = value
        await self.coordinator.async_request_refresh()
