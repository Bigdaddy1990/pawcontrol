"""Switch platform for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .compat import DeviceInfo, EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_TRAINING,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .entity import PawControlSwitchEntity

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control switch entities."""
    coordinator: PawControlCoordinator = entry.runtime_data.coordinator

    if not coordinator.last_update_success:
        await coordinator.async_refresh()
        if not coordinator.last_update_success:
            raise PlatformNotReady

    entities = []
    dogs = entry.options.get(CONF_DOGS, [])

    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue

        modules = dog.get(CONF_DOG_MODULES, {})

        # Module enable/disable switches
        entities.extend(
            [
                ModuleSwitch(
                    hass,
                    coordinator,
                    entry,
                    dog_id,
                    MODULE_WALK,
                    "Walk Module",
                    "mdi:dog-side",
                    modules.get(MODULE_WALK, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    entry,
                    dog_id,
                    MODULE_FEEDING,
                    "Feeding Module",
                    "mdi:food",
                    modules.get(MODULE_FEEDING, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    entry,
                    dog_id,
                    MODULE_HEALTH,
                    "Health Module",
                    "mdi:heart",
                    modules.get(MODULE_HEALTH, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    entry,
                    dog_id,
                    MODULE_GROOMING,
                    "Grooming Module",
                    "mdi:content-cut",
                    modules.get(MODULE_GROOMING, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    entry,
                    dog_id,
                    MODULE_TRAINING,
                    "Training Module",
                    "mdi:school",
                    modules.get(MODULE_TRAINING, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    entry,
                    dog_id,
                    MODULE_NOTIFICATIONS,
                    "Notifications",
                    "mdi:bell",
                    modules.get(MODULE_NOTIFICATIONS, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    entry,
                    dog_id,
                    MODULE_GPS,
                    "GPS Tracking",
                    "mdi:map-marker",
                    modules.get(MODULE_GPS, False),
                ),
            ]
        )

        # Feature switches
        if modules.get(MODULE_WALK):
            entities.append(AutoWalkDetectionSwitch(hass, coordinator, entry, dog_id))

        if modules.get(MODULE_FEEDING):
            entities.append(
                OverfeedingProtectionSwitch(hass, coordinator, entry, dog_id)
            )

        if modules.get(MODULE_NOTIFICATIONS):
            entities.append(NotificationEnabledSwitch(hass, coordinator, entry, dog_id))

    # Global switches
    entities.extend(
        [
            VisitorModeSwitch(hass, coordinator, entry),
            EmergencyModeSwitch(hass, coordinator, entry),
            QuietHoursSwitch(hass, coordinator, entry),
            DailyReportSwitch(hass, coordinator, entry),
        ]
    )

    async_add_entities(entities, True)


class ModuleSwitch(PawControlSwitchEntity, SwitchEntity):
    """Switch to enable or disable a module."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        module_id: str,
        module_name: str,
        icon: str,
        enabled: bool = False,
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            f"module_{module_id}",
            entity_category=EntityCategory.CONFIG,
        )
        self.hass = hass
        self._module_id = module_id
        self._module_name = module_name
        self._attr_icon = icon
        self._is_on = enabled

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return f"{self.dog_name} - {self._module_name}"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the module."""
        _LOGGER.info(f"Enabling {self._module_id} module for {self.dog_name}")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the module."""
        _LOGGER.info(f"Disabling {self._module_id} module for {self.dog_name}")
        self._is_on = False
        self.async_write_ha_state()


class AutoWalkDetectionSwitch(PawControlSwitchEntity, SwitchEntity):
    """Switch for auto walk detection."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "auto_walk_detection",
            entity_category=EntityCategory.CONFIG,
        )
        self.hass = hass
        self._attr_icon = "mdi:walk"
        self._is_on = True

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return f"{self.dog_name} - Auto Walk Detection"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable auto walk detection."""
        _LOGGER.info(f"Enabling auto walk detection for {self.dog_name}")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable auto walk detection."""
        _LOGGER.info(f"Disabling auto walk detection for {self.dog_name}")
        self._is_on = False
        self.async_write_ha_state()


class OverfeedingProtectionSwitch(PawControlSwitchEntity, SwitchEntity):
    """Switch for overfeeding protection."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "overfeeding_protection",
            entity_category=EntityCategory.CONFIG,
        )
        self.hass = hass
        self._attr_icon = "mdi:shield-check"
        self._is_on = True

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return f"{self.dog_name} - Overfeeding Protection"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable overfeeding protection."""
        _LOGGER.info(f"Enabling overfeeding protection for {self.dog_name}")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable overfeeding protection."""
        _LOGGER.warning(f"Disabling overfeeding protection for {self.dog_name}")
        self._is_on = False
        self.async_write_ha_state()


class NotificationEnabledSwitch(PawControlSwitchEntity, SwitchEntity):
    """Switch to enable/disable notifications for a dog."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "notifications_enabled",
            entity_category=EntityCategory.CONFIG,
        )
        self.hass = hass
        self._attr_icon = "mdi:bell"
        self._is_on = True

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return f"{self.dog_name} - Notifications"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable notifications."""
        _LOGGER.info(f"Enabling notifications for {self.dog_name}")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable notifications."""
        _LOGGER.info(f"Disabling notifications for {self.dog_name}")
        self._is_on = False
        self.async_write_ha_state()


# Global Switches
class VisitorModeSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for visitor mode."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:account-group"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_visitor_mode"
        self._attr_translation_key = "visitor_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Visitor Mode"

    @property
    def is_on(self) -> bool:
        """Return true if visitor mode is on."""
        return self.coordinator.visitor_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on visitor mode."""
        await self.hass.services.async_call(
            DOMAIN,
            "toggle_visitor",
            {"enabled": True},
            blocking=False,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off visitor mode."""
        await self.hass.services.async_call(
            DOMAIN,
            "toggle_visitor",
            {"enabled": False},
            blocking=False,
        )


class EmergencyModeSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for emergency mode."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:alert-circle"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_emergency_mode"
        self._attr_translation_key = "emergency_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Emergency Mode"

    @property
    def is_on(self) -> bool:
        """Return true if emergency mode is on."""
        return self.coordinator.emergency_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on emergency mode."""
        await self.hass.services.async_call(
            DOMAIN,
            "emergency_mode",
            {"level": "critical", "note": "Emergency mode activated via switch"},
            blocking=False,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off emergency mode."""
        # Use coordinator method to properly reset
        await self.coordinator.activate_emergency_mode(
            "info", "Emergency mode deactivated"
        )


class QuietHoursSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for quiet hours."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bell-sleep"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self._is_on = bool(entry.options.get("quiet_hours", {}).get("enabled", True))
        self._attr_unique_id = f"{entry.entry_id}_global_quiet_hours"
        self._attr_translation_key = "quiet_hours"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Quiet Hours"

    @property
    def is_on(self) -> bool:
        """Return true if quiet hours are enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable quiet hours."""
        _LOGGER.info("Enabling quiet hours")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable quiet hours."""
        _LOGGER.info("Disabling quiet hours")
        self._is_on = False
        self.async_write_ha_state()


class DailyReportSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for daily report."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:file-document-clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self._is_on = bool(entry.options.get("export_path"))
        self._attr_unique_id = f"{entry.entry_id}_global_daily_report"
        self._attr_translation_key = "daily_report"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Daily Report"

    @property
    def is_on(self) -> bool:
        """Return true if daily report is enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable daily report."""
        _LOGGER.info("Enabling daily report")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable daily report."""
        _LOGGER.info("Disabling daily report")
        self._is_on = False
        self.async_write_ha_state()
