"""Switch platform for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    ICON_EMERGENCY,
    SERVICE_EMERGENCY,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl switch entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for dog_name, dog_data in entry_data.items():
        coordinator = dog_data["coordinator"]
        config = dog_data["config"]
        
        # Always add these switches
        entities.extend([
            PawControlEmergencyModeSwitch(hass, coordinator, config),
            PawControlVisitorModeSwitch(hass, coordinator, config),
        ])
        
        # Add module-specific switches
        modules = config.get("modules", {})
        
        if modules.get("walk", {}).get("enabled", False):
            entities.extend([
                PawControlWalkInProgressSwitch(hass, coordinator, config),
                PawControlAutoWalkDetectionSwitch(hass, coordinator, config),
            ])
        
        if modules.get("training", {}).get("enabled", False):
            entities.append(PawControlTrainingSessionSwitch(hass, coordinator, config))
        
        if modules.get("health", {}).get("enabled", False):
            entities.extend([
                PawControlMedicationReminderSwitch(hass, coordinator, config),
                PawControlHealthMonitoringSwitch(hass, coordinator, config),
            ])
    
    async_add_entities(entities)


class PawControlSwitchBase(CoordinatorEntity, SwitchEntity):
    """Base class for PawControl switches."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        config: dict[str, Any],
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.hass = hass
        self._config = config
        self._dog_name = config.get(CONF_DOG_NAME, "Unknown")
        self._dog_id = self._dog_name.lower().replace(" ", "_")
        self._attr_has_entity_name = True

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


class PawControlEmergencyModeSwitch(PawControlSwitchBase):
    """Switch for emergency mode."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_emergency_mode_switch"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Notfallmodus"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_EMERGENCY

    @property
    def is_on(self):
        """Return true if emergency mode is on."""
        return self.coordinator.data.get("status", {}).get("emergency_mode", False)

    async def async_turn_on(self, **kwargs):
        """Turn on emergency mode."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_EMERGENCY,
            {
                "dog_name": self._dog_name,
                "activate": True,
                "reason": "Manuell aktiviert",
            },
            blocking=False,
        )

    async def async_turn_off(self, **kwargs):
        """Turn off emergency mode."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_EMERGENCY,
            {
                "dog_name": self._dog_name,
                "activate": False,
            },
            blocking=False,
        )


class PawControlVisitorModeSwitch(PawControlSwitchBase):
    """Switch for visitor mode."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_visitor_mode_switch"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Besuchermodus"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:account-group"

    @property
    def is_on(self):
        """Return true if visitor mode is on."""
        return self.coordinator.data.get("status", {}).get("visitor_mode", False)

    async def async_turn_on(self, **kwargs):
        """Turn on visitor mode."""
        await self.coordinator.async_set_visitor_mode(True, "Besucher", "Standard-Anweisungen")

    async def async_turn_off(self, **kwargs):
        """Turn off visitor mode."""
        await self.coordinator.async_set_visitor_mode(False)


class PawControlWalkInProgressSwitch(PawControlSwitchBase):
    """Switch for walk in progress."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_walk_in_progress_switch"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Spaziergang läuft"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:dog-service"

    @property
    def is_on(self):
        """Return true if walk is in progress."""
        return self.coordinator.data.get("status", {}).get("walk_in_progress", False)

    async def async_turn_on(self, **kwargs):
        """Start a walk."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_walk",
            {
                "dog_name": self._dog_name,
                "walk_type": "Normal",
            },
            blocking=False,
        )

    async def async_turn_off(self, **kwargs):
        """End a walk."""
        await self.hass.services.async_call(
            DOMAIN,
            "end_walk",
            {
                "dog_name": self._dog_name,
                "duration": 30,  # Default 30 minutes
            },
            blocking=False,
        )


class PawControlAutoWalkDetectionSwitch(PawControlSwitchBase):
    """Switch for automatic walk detection."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_auto_walk_detection"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Auto Spaziergang-Erkennung"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:motion-sensor"

    @property
    def is_on(self):
        """Return true if auto walk detection is on."""
        return self.coordinator.data.get("settings", {}).get("auto_walk_detection", False)

    async def async_turn_on(self, **kwargs):
        """Turn on auto walk detection."""
        self.coordinator._data.setdefault("settings", {})["auto_walk_detection"] = True
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn off auto walk detection."""
        self.coordinator._data.setdefault("settings", {})["auto_walk_detection"] = False
        await self.coordinator.async_request_refresh()


class PawControlTrainingSessionSwitch(PawControlSwitchBase):
    """Switch for training session."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_training_session"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Trainingseinheit"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:whistle"

    @property
    def is_on(self):
        """Return true if training is in progress."""
        return self.coordinator.data.get("status", {}).get("training_in_progress", False)

    async def async_turn_on(self, **kwargs):
        """Start training session."""
        self.coordinator._data.setdefault("status", {})["training_in_progress"] = True
        from datetime import datetime
        self.coordinator._data["status"]["training_start"] = datetime.now().isoformat()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """End training session."""
        self.coordinator._data.setdefault("status", {})["training_in_progress"] = False
        from datetime import datetime
        self.coordinator._data["status"]["last_training"] = datetime.now().isoformat()
        self.coordinator._data["activity"]["daily_training"] = \
            self.coordinator._data.get("activity", {}).get("daily_training", 0) + 1
        await self.coordinator.async_request_refresh()


class PawControlMedicationReminderSwitch(PawControlSwitchBase):
    """Switch for medication reminders."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_medication_reminder"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Medikations-Erinnerung"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:pill"

    @property
    def is_on(self):
        """Return true if medication reminders are on."""
        return self.coordinator.data.get("settings", {}).get("medication_reminder", False)

    async def async_turn_on(self, **kwargs):
        """Turn on medication reminders."""
        self.coordinator._data.setdefault("settings", {})["medication_reminder"] = True
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn off medication reminders."""
        self.coordinator._data.setdefault("settings", {})["medication_reminder"] = False
        await self.coordinator.async_request_refresh()


class PawControlHealthMonitoringSwitch(PawControlSwitchBase):
    """Switch for health monitoring."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_health_monitoring"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gesundheitsüberwachung"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:heart-pulse"

    @property
    def is_on(self):
        """Return true if health monitoring is on."""
        return self.coordinator.data.get("settings", {}).get("health_monitoring", True)

    async def async_turn_on(self, **kwargs):
        """Turn on health monitoring."""
        self.coordinator._data.setdefault("settings", {})["health_monitoring"] = True
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn off health monitoring."""
        self.coordinator._data.setdefault("settings", {})["health_monitoring"] = False
        await self.coordinator.async_request_refresh()
