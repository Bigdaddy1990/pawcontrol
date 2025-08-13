"""Switch platform for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
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

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control switch entities."""
    coordinator = entry.runtime_data.coordinator

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

        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})

        # Module enable/disable switches
        entities.extend(
            [
                ModuleSwitch(
                    hass,
                    coordinator,
                    dog_id,
                    dog_name,
                    MODULE_WALK,
                    "Walk Module",
                    "mdi:dog-side",
                    modules.get(MODULE_WALK, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    dog_id,
                    dog_name,
                    MODULE_FEEDING,
                    "Feeding Module",
                    "mdi:food",
                    modules.get(MODULE_FEEDING, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    dog_id,
                    dog_name,
                    MODULE_HEALTH,
                    "Health Module",
                    "mdi:heart",
                    modules.get(MODULE_HEALTH, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    dog_id,
                    dog_name,
                    MODULE_GROOMING,
                    "Grooming Module",
                    "mdi:content-cut",
                    modules.get(MODULE_GROOMING, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    dog_id,
                    dog_name,
                    MODULE_TRAINING,
                    "Training Module",
                    "mdi:school",
                    modules.get(MODULE_TRAINING, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    dog_id,
                    dog_name,
                    MODULE_NOTIFICATIONS,
                    "Notifications",
                    "mdi:bell",
                    modules.get(MODULE_NOTIFICATIONS, False),
                ),
                ModuleSwitch(
                    hass,
                    coordinator,
                    dog_id,
                    dog_name,
                    MODULE_GPS,
                    "GPS Tracking",
                    "mdi:map-marker",
                    modules.get(MODULE_GPS, False),
                ),
            ]
        )

        # Feature switches
        if modules.get(MODULE_WALK):
            entities.append(
                AutoWalkDetectionSwitch(hass, coordinator, dog_id, dog_name)
            )

        if modules.get(MODULE_FEEDING):
            entities.append(
                OverfeedingProtectionSwitch(hass, coordinator, dog_id, dog_name)
            )

        if modules.get(MODULE_NOTIFICATIONS):
            entities.append(
                NotificationEnabledSwitch(hass, coordinator, dog_id, dog_name)
            )

    # Global switches
    entities.extend(
        [
            VisitorModeSwitch(hass, coordinator),
            EmergencyModeSwitch(hass, coordinator),
            QuietHoursSwitch(hass, coordinator, entry),
            DailyReportSwitch(hass, coordinator, entry),
        ]
    )

    async_add_entities(entities, True)


class PawControlSwitchBase(SwitchEntity):
    """Base class for Paw Control switches."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: Any,
        dog_id: str,
        dog_name: str,
        switch_type: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the switch."""
        self.hass = hass
        self.coordinator = coordinator
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._switch_type = switch_type
        self._is_on = False

        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.switch.{switch_type}"
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
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._is_on = False
        self.async_write_ha_state()


class ModuleSwitch(PawControlSwitchBase):
    """Switch to enable or disable a module.

    The initial enabled state is supplied via the ``enabled`` argument so the
    switch can be created without querying the coordinator's config entry.
    """

    def __init__(
        self,
        hass,
        coordinator,
        dog_id,
        dog_name,
        module_id,
        module_name,
        icon,
        enabled: bool = False,
    ) -> None:
        """Initialize the switch.

        Args:
            enabled: If ``True`` the module starts enabled and the switch will
                report as on.
        """
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            f"module_{module_id}",
            module_name,
            icon,
        )
        self._module_id = module_id
        # Store the initial enabled state directly rather than asking the
        # coordinator or config entry. Test coordinators may lack an ``entry``
        # attribute and the coordinator does not persist per-module state,
        # making such lookups unreliable and causing attribute errors during
        # entity setup. Keeping the value in ``_is_on`` ensures consistent
        # startup behavior.
        self._is_on = enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the module."""
        _LOGGER.info(f"Enabling {self._module_id} module for {self._dog_name}")
        # Would update config entry
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the module."""
        _LOGGER.info(f"Disabling {self._module_id} module for {self._dog_name}")
        # Would update config entry
        self._is_on = False
        self.async_write_ha_state()


class AutoWalkDetectionSwitch(PawControlSwitchBase):
    """Switch for auto walk detection."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the switch."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "auto_walk_detection",
            "Auto Walk Detection",
            "mdi:walk",
        )
        self._is_on = True

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable auto walk detection."""
        _LOGGER.info(f"Enabling auto walk detection for {self._dog_name}")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable auto walk detection."""
        _LOGGER.info(f"Disabling auto walk detection for {self._dog_name}")
        self._is_on = False
        self.async_write_ha_state()


class OverfeedingProtectionSwitch(PawControlSwitchBase):
    """Switch for overfeeding protection."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the switch."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "overfeeding_protection",
            "Overfeeding Protection",
            "mdi:shield-check",
        )
        self._is_on = True

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable overfeeding protection."""
        _LOGGER.info(f"Enabling overfeeding protection for {self._dog_name}")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable overfeeding protection."""
        _LOGGER.warning(f"Disabling overfeeding protection for {self._dog_name}")
        self._is_on = False
        self.async_write_ha_state()


class NotificationEnabledSwitch(PawControlSwitchBase):
    """Switch to enable/disable notifications for a dog."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the switch."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "notifications_enabled",
            "Notifications Enabled",
            "mdi:bell",
        )
        self._is_on = True

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable notifications."""
        _LOGGER.info(f"Enabling notifications for {self._dog_name}")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable notifications."""
        _LOGGER.info(f"Disabling notifications for {self._dog_name}")
        self._is_on = False
        self.async_write_ha_state()


class VisitorModeSwitch(SwitchEntity):
    """Switch for visitor mode."""

    _attr_has_entity_name = True
    _attr_name = "Visitor Mode"
    _attr_icon = "mdi:account-group"

    def __init__(self, hass: HomeAssistant, coordinator: Any):
        """Initialize the switch."""
        self.hass = hass
        self.coordinator = coordinator

        self._attr_unique_id = f"{DOMAIN}.global.switch.visitor_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    @property
    def is_on(self) -> bool:
        """Return true if visitor mode is on."""
        return self.coordinator.visitor_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on visitor mode."""
        await self.hass.services.async_call(
            DOMAIN,
            "toggle_visitor_mode",
            {"enabled": True},
            blocking=False,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off visitor mode."""
        await self.hass.services.async_call(
            DOMAIN,
            "toggle_visitor_mode",
            {"enabled": False},
            blocking=False,
        )


class EmergencyModeSwitch(SwitchEntity):
    """Switch for emergency mode."""

    _attr_has_entity_name = True
    _attr_name = "Emergency Mode"
    _attr_icon = "mdi:alert-circle"

    def __init__(self, hass: HomeAssistant, coordinator: Any):
        """Initialize the switch."""
        self.hass = hass
        self.coordinator = coordinator

        self._attr_unique_id = f"{DOMAIN}.global.switch.emergency_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    @property
    def is_on(self) -> bool:
        """Return true if emergency mode is on."""
        return self.coordinator.emergency_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on emergency mode."""
        await self.hass.services.async_call(
            DOMAIN,
            "activate_emergency_mode",
            {"level": "critical", "note": "Emergency mode activated"},
            blocking=False,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off emergency mode."""
        # Reset emergency mode
        self.coordinator._emergency_mode = False
        await self.coordinator.async_request_refresh()


class QuietHoursSwitch(SwitchEntity):
    """Switch for quiet hours."""

    _attr_has_entity_name = True
    _attr_name = "Quiet Hours"
    _attr_icon = "mdi:bell-sleep"

    def __init__(self, hass: HomeAssistant, coordinator: Any, entry: ConfigEntry):
        """Initialize the switch."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._is_on = True

        self._attr_unique_id = f"{DOMAIN}.global.switch.quiet_hours"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

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


class DailyReportSwitch(SwitchEntity):
    """Switch for daily report."""

    _attr_has_entity_name = True
    _attr_name = "Daily Report"
    _attr_icon = "mdi:file-document-clock"

    def __init__(self, hass: HomeAssistant, coordinator: Any, entry: ConfigEntry):
        """Initialize the switch."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._is_on = bool(entry.options.get("export_path"))

        self._attr_unique_id = f"{DOMAIN}.global.switch.daily_report"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

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
