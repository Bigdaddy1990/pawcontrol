"""Switch platform for Paw Control integration.

This module provides comprehensive switch entities for dog monitoring control
including module toggles, feature switches, and system controls. All switches
are designed to meet Home Assistant's Platinum quality standards with full
type annotations, async operations, and robust error handling.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Type aliases for better code readability
AttributeDict = dict[str, Any]


async def _async_add_entities_in_batches(
    async_add_entities_func,
    entities: list[PawControlSwitchBase],
    batch_size: int = 14,
    delay_between_batches: float = 0.1,
) -> None:
    """Add switch entities in small batches to prevent Entity Registry overload.

    The Entity Registry logs warnings when >200 messages occur rapidly.
    By batching entities and adding delays, we prevent registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of switch entities to add
        batch_size: Number of entities per batch (default: 14)
        delay_between_batches: Seconds to wait between batches (default: 0.1s)
    """
    total_entities = len(entities)

    _LOGGER.debug(
        "Adding %d switch entities in batches of %d to prevent Registry overload",
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
        batch = entities[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            "Processing switch batch %d/%d with %d entities",
            batch_num,
            total_batches,
            len(batch),
        )

        # Add batch without update_before_add to reduce Registry load
        async_add_entities_func(batch, update_before_add=False)

        # Small delay between batches to prevent Registry flooding
        if i + batch_size < total_entities:  # No delay after last batch
            await asyncio.sleep(delay_between_batches)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control switch platform.

    Creates switch entities for all configured dogs to control various
    aspects of dog monitoring and care. Switches provide toggle controls
    for modules, features, and system settings.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry containing dog configurations
        async_add_entities: Callback to add switch entities
    """
    runtime_data = getattr(entry, "runtime_data", None)

    if runtime_data:
        coordinator: PawControlCoordinator = runtime_data["coordinator"]
        dogs: list[dict[str, Any]] = runtime_data.get("dogs", [])
    else:
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        dogs = entry.data.get(CONF_DOGS, [])

    entities: list[PawControlSwitchBase] = []

    # Create switch entities for each configured dog
    for dog in dogs:
        dog_id: str = dog[CONF_DOG_ID]
        dog_name: str = dog[CONF_DOG_NAME]
        modules: dict[str, bool] = dog.get("modules", {})

        _LOGGER.debug("Creating switch entities for dog: %s (%s)", dog_name, dog_id)

        # Base switches - always created for every dog
        entities.extend(_create_base_switches(coordinator, dog_id, dog_name))

        # Module control switches
        entities.extend(_create_module_switches(coordinator, dog_id, dog_name, modules))

        # Feature switches based on enabled modules
        if modules.get(MODULE_FEEDING, False):
            entities.extend(_create_feeding_switches(coordinator, dog_id, dog_name))

        if modules.get(MODULE_GPS, False):
            entities.extend(_create_gps_switches(coordinator, dog_id, dog_name))

        if modules.get(MODULE_HEALTH, False):
            entities.extend(_create_health_switches(coordinator, dog_id, dog_name))

        if modules.get(MODULE_NOTIFICATIONS, False):
            entities.extend(
                _create_notification_switches(coordinator, dog_id, dog_name)
            )

    # Add entities in smaller batches to prevent Entity Registry overload
    # With 56+ switch entities (2 dogs), batching prevents Registry flooding
    await _async_add_entities_in_batches(async_add_entities, entities, batch_size=14)

    _LOGGER.info(
        "Created %d switch entities for %d dogs using batched approach",
        len(entities),
        len(dogs),
    )


def _create_base_switches(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSwitchBase]:
    """Create base switches that are always present for every dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of base switch entities
    """
    return [
        PawControlMainPowerSwitch(coordinator, dog_id, dog_name),
        PawControlVisitorModeSwitch(coordinator, dog_id, dog_name),
        PawControlDoNotDisturbSwitch(coordinator, dog_id, dog_name),
    ]


def _create_module_switches(
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    modules: dict[str, bool],
) -> list[PawControlSwitchBase]:
    """Create module control switches for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        modules: Currently enabled modules

    Returns:
        List of module switch entities
    """
    switches = []

    # Create switches for all possible modules
    module_configs = [
        (MODULE_FEEDING, "Feeding Tracking", "mdi:food-drumstick"),
        (MODULE_WALK, "Walk Tracking", "mdi:walk"),
        (MODULE_GPS, "GPS Tracking", "mdi:map-marker"),
        (MODULE_HEALTH, "Health Monitoring", "mdi:heart-pulse"),
        (MODULE_NOTIFICATIONS, "Notifications", "mdi:bell"),
        (MODULE_VISITOR, "Visitor Mode", "mdi:account-group"),
    ]

    for module_id, module_name, icon in module_configs:
        switches.append(
            PawControlModuleSwitch(
                coordinator,
                dog_id,
                dog_name,
                module_id,
                module_name,
                icon,
                modules.get(module_id, False),
            )
        )

    return switches


def _create_feeding_switches(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSwitchBase]:
    """Create feeding-related switches for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of feeding switch entities
    """
    return [
        PawControlAutoFeedingRemindersSwitch(coordinator, dog_id, dog_name),
        PawControlFeedingScheduleSwitch(coordinator, dog_id, dog_name),
        PawControlPortionControlSwitch(coordinator, dog_id, dog_name),
        PawControlFeedingAlertsSwitch(coordinator, dog_id, dog_name),
    ]


def _create_gps_switches(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSwitchBase]:
    """Create GPS and location-related switches for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of GPS switch entities
    """
    return [
        PawControlGPSTrackingSwitch(coordinator, dog_id, dog_name),
        PawControlGeofencingSwitch(coordinator, dog_id, dog_name),
        PawControlRouteRecordingSwitch(coordinator, dog_id, dog_name),
        PawControlAutoWalkDetectionSwitch(coordinator, dog_id, dog_name),
        PawControlLocationSharingSwitch(coordinator, dog_id, dog_name),
    ]


def _create_health_switches(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSwitchBase]:
    """Create health and medical-related switches for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of health switch entities
    """
    return [
        PawControlHealthMonitoringSwitch(coordinator, dog_id, dog_name),
        PawControlWeightTrackingSwitch(coordinator, dog_id, dog_name),
        PawControlMedicationRemindersSwitch(coordinator, dog_id, dog_name),
        PawControlVetRemindersSwitch(coordinator, dog_id, dog_name),
        PawControlActivityTrackingSwitch(coordinator, dog_id, dog_name),
    ]


def _create_notification_switches(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSwitchBase]:
    """Create notification-related switches for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of notification switch entities
    """
    return [
        PawControlNotificationsSwitch(coordinator, dog_id, dog_name),
        PawControlUrgentNotificationsSwitch(coordinator, dog_id, dog_name),
        PawControlDailyReportsSwitch(coordinator, dog_id, dog_name),
        PawControlWeeklyReportsSwitch(coordinator, dog_id, dog_name),
        PawControlSoundAlertsSwitch(coordinator, dog_id, dog_name),
    ]


class PawControlSwitchBase(
    CoordinatorEntity[PawControlCoordinator], SwitchEntity, RestoreEntity
):
    """Base class for all Paw Control switch entities.

    Provides common functionality and ensures consistent behavior across
    all switch types. Includes proper device grouping, state persistence,
    and error handling.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        switch_type: str,
        *,
        device_class: SwitchDeviceClass | None = None,
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
        initial_state: bool = False,
    ) -> None:
        """Initialize the switch entity.

        Args:
            coordinator: Data coordinator for updates
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
            switch_type: Type identifier for the switch
            device_class: Home Assistant device class
            icon: Material Design icon
            entity_category: Entity category for organization
            initial_state: Initial state of the switch
        """
        super().__init__(coordinator)

        self._dog_id = dog_id
        self._dog_name = dog_name
        self._switch_type = switch_type
        self._is_on = initial_state

        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{switch_type}"
        self._attr_name = f"{dog_name} {switch_type.replace('_', ' ').title()}"
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_entity_category = entity_category

        # Device info for proper grouping - HA 2025.8+ compatible with configuration_url
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog_id)},
            "name": dog_name,
            "manufacturer": "Paw Control",
            "model": "Smart Dog Monitoring",
            "sw_version": "1.0.0",
            "configuration_url": "https://github.com/BigDaddy1990/pawcontrol",
        }

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant.

        Restores the previous state and sets up any required listeners.
        """
        await super().async_added_to_hass()

        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self._is_on = last_state.state == "on"
            _LOGGER.debug(
                "Restored switch state for %s %s: %s",
                self._dog_name,
                self._switch_type,
                self._is_on,
            )

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on.

        Returns:
            Current switch state
        """
        return self._is_on

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for the switch.

        Provides information about the switch's function and the dog
        it controls.

        Returns:
            Dictionary of additional state attributes
        """
        attrs: AttributeDict = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "switch_type": self._switch_type,
            "last_changed": dt_util.utcnow().isoformat(),
        }

        # Add dog-specific information
        dog_data = self._get_dog_data()
        if dog_data and "dog_info" in dog_data:
            dog_info = dog_data["dog_info"]
            attrs.update(
                {
                    "dog_breed": dog_info.get("dog_breed", ""),
                    "dog_age": dog_info.get("dog_age"),
                    "dog_size": dog_info.get("dog_size"),
                }
            )

        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on.

        Args:
            **kwargs: Additional service parameters
        """
        try:
            await self._async_set_switch_state(True)
            self._is_on = True
            self.async_write_ha_state()

            _LOGGER.info(
                "Turned on %s for %s (%s)",
                self._switch_type,
                self._dog_name,
                self._dog_id,
            )

        except Exception as err:
            _LOGGER.error(
                "Failed to turn on %s for %s: %s",
                self._switch_type,
                self._dog_name,
                err,
            )
            raise HomeAssistantError(f"Failed to turn on {self._switch_type}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off.

        Args:
            **kwargs: Additional service parameters
        """
        try:
            await self._async_set_switch_state(False)
            self._is_on = False
            self.async_write_ha_state()

            _LOGGER.info(
                "Turned off %s for %s (%s)",
                self._switch_type,
                self._dog_name,
                self._dog_id,
            )

        except Exception as err:
            _LOGGER.error(
                "Failed to turn off %s for %s: %s",
                self._switch_type,
                self._dog_name,
                err,
            )
            raise HomeAssistantError(f"Failed to turn off {self._switch_type}") from err

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the switch state implementation.

        This method should be overridden by subclasses to implement
        specific switch functionality.

        Args:
            state: Desired switch state
        """
        # Base implementation - subclasses should override
        pass

    def _get_dog_data(self) -> dict[str, Any] | None:
        """Get data for this switch's dog from the coordinator.

        Returns:
            Dog data dictionary or None if not available
        """
        if not self.coordinator.available:
            return None

        return self.coordinator.get_dog_data(self._dog_id)

    def _get_module_data(self, module: str) -> dict[str, Any] | None:
        """Get specific module data for this dog.

        Args:
            module: Module name to retrieve data for

        Returns:
            Module data dictionary or None if not available
        """
        return self.coordinator.get_module_data(self._dog_id, module)

    @property
    def available(self) -> bool:
        """Return if the switch is available.

        A switch is available when the coordinator is available and
        the dog data can be retrieved.

        Returns:
            True if switch is available, False otherwise
        """
        return self.coordinator.available and self._get_dog_data() is not None


# Base switches
class PawControlMainPowerSwitch(PawControlSwitchBase):
    """Main power switch to enable/disable all monitoring for a dog."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the main power switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "main_power",
            device_class=SwitchDeviceClass.SWITCH,
            icon="mdi:power",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the main power state."""
        # Update main power state through data manager
        try:
            runtime_data = self.hass.data[DOMAIN][
                self.coordinator.config_entry.entry_id
            ]
            data_manager = runtime_data.get("data_manager")

            if data_manager:
                await data_manager.async_set_dog_power_state(self._dog_id, state)

            # Trigger coordinator refresh to update all entities
            await self.coordinator.async_refresh_dog(self._dog_id)

        except Exception as err:
            _LOGGER.warning(
                "Failed to update power state through data manager: %s", err
            )
            # Fallback to coordinator refresh only
            await self.coordinator.async_refresh_dog(self._dog_id)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for the main power switch."""
        attrs = super().extra_state_attributes
        dog_data = self._get_dog_data()

        if dog_data:
            attrs.update(
                {
                    "enabled_modules": dog_data.get("enabled_modules", []),
                    "system_status": dog_data.get("status", "unknown"),
                    "last_activity": dog_data.get("last_update"),
                }
            )

        return attrs


class PawControlVisitorModeSwitch(PawControlSwitchBase):
    """Switch to enable/disable visitor mode."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the visitor mode switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "visitor_mode",
            icon="mdi:account-group",
            initial_state=False,
        )

    @property
    def is_on(self) -> bool:
        """Return True if visitor mode is active."""
        dog_data = self._get_dog_data()
        if dog_data:
            return dog_data.get("visitor_mode_active", False)

        return self._is_on

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the visitor mode state."""
        # Call the visitor mode service with appropriate parameters
        await self.hass.services.async_call(
            DOMAIN,
            "set_visitor_mode",
            {
                "dog_id": self._dog_id,
                "enabled": state,
                "visitor_name": "Switch Toggle" if state else None,
                "reduced_alerts": state,
                "modified_schedule": state,
                "notes": f"Visitor mode {'enabled' if state else 'disabled'} via switch",
            },
            blocking=True,
        )

        _LOGGER.info(
            "Visitor mode %s for %s", "enabled" if state else "disabled", self._dog_name
        )

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for visitor mode."""
        attrs = super().extra_state_attributes
        dog_data = self._get_dog_data()

        if dog_data and dog_data.get("visitor_mode_active"):
            attrs.update(
                {
                    "visitor_mode_started": dog_data.get("visitor_mode_started"),
                    "visitor_name": dog_data.get("visitor_name"),
                    "modified_settings": dog_data.get("visitor_mode_settings", {}),
                }
            )

        return attrs


class PawControlDoNotDisturbSwitch(PawControlSwitchBase):
    """Switch to enable/disable do not disturb mode."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the do not disturb switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "do_not_disturb",
            icon="mdi:sleep",
            initial_state=False,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the do not disturb state."""
        # Update notification settings based on DND state
        try:
            # Update DND settings via notification manager directly
            entry_data = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
            notification_manager = entry_data.get("notifications")

            if notification_manager and hasattr(
                notification_manager, "async_set_dnd_mode"
            ):
                await notification_manager.async_set_dnd_mode(self._dog_id, state)
                _LOGGER.info(
                    "DND mode %s for %s via notification manager",
                    "enabled" if state else "disabled",
                    self._dog_name,
                )
            else:
                _LOGGER.warning(
                    "Notification manager not available for DND mode update for %s",
                    self._dog_name,
                )

        except Exception as err:
            _LOGGER.error(
                "Failed to update DND settings for %s: %s", self._dog_name, err
            )


# Module switches
class PawControlModuleSwitch(PawControlSwitchBase):
    """Switch to enable/disable a specific module."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        module_id: str,
        module_name: str,
        icon: str,
        initial_state: bool,
    ) -> None:
        """Initialize the module switch."""
        self._module_id = module_id
        self._module_name = module_name

        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            f"module_{module_id}",
            icon=icon,
            initial_state=initial_state,
            entity_category=EntityCategory.CONFIG,
        )
        self._attr_name = f"{dog_name} {module_name}"

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the module state."""
        # Update module configuration through config entry
        try:
            # Get current config data
            new_data = dict(self.coordinator.config_entry.data)

            # Update the specific dog's module configuration
            for i, dog in enumerate(new_data.get("dogs", [])):
                if dog.get("dog_id") == self._dog_id:
                    if "modules" not in new_data["dogs"][i]:
                        new_data["dogs"][i]["modules"] = {}
                    new_data["dogs"][i]["modules"][self._module_id] = state
                    break

            # Update the config entry
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry, data=new_data
            )

            _LOGGER.info(
                "Module %s %s for %s",
                self._module_name,
                "enabled" if state else "disabled",
                self._dog_name,
            )

            # Update coordinator configuration and trigger refresh
            await self.coordinator.async_update_config(new_data)

        except Exception as err:
            _LOGGER.error("Failed to update module configuration: %s", err)
            # Fallback to coordinator refresh only
            await self.coordinator.async_refresh_dog(self._dog_id)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for the module switch."""
        attrs = super().extra_state_attributes
        attrs.update(
            {
                "module_id": self._module_id,
                "module_name": self._module_name,
                "configuration_required": self._is_configuration_required(),
                "dependencies": self._get_module_dependencies(),
            }
        )

        return attrs

    def _is_configuration_required(self) -> bool:
        """Check if additional configuration is required for this module.

        Returns:
            True if configuration is needed
        """
        # GPS module typically requires additional setup
        return self._module_id == MODULE_GPS

    def _get_module_dependencies(self) -> list[str]:
        """Get list of modules this module depends on.

        Returns:
            List of dependent module IDs
        """
        dependencies = {
            MODULE_GPS: [],
            MODULE_WALK: [MODULE_GPS],  # Walk tracking can benefit from GPS
            MODULE_FEEDING: [],
            MODULE_HEALTH: [],
            MODULE_NOTIFICATIONS: [],
            MODULE_VISITOR: [MODULE_NOTIFICATIONS],
        }

        return dependencies.get(self._module_id, [])


# Feeding switches
class PawControlAutoFeedingRemindersSwitch(PawControlSwitchBase):
    """Switch to enable/disable automatic feeding reminders."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the auto feeding reminders switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "auto_feeding_reminders",
            icon="mdi:clock-alert",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the auto feeding reminders state."""
        # Configure feeding reminder automations through service
        await self.hass.services.async_call(
            DOMAIN,
            "configure_alerts",
            {
                "dog_id": self._dog_id,
                "feeding_alerts": state,
            },
            blocking=True,
        )


class PawControlFeedingScheduleSwitch(PawControlSwitchBase):
    """Switch to enable/disable feeding schedule enforcement."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the feeding schedule switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_schedule",
            icon="mdi:calendar-check",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the feeding schedule state."""
        # Configure feeding schedule tracking
        await self.hass.services.async_call(
            DOMAIN,
            "set_feeding_schedule",
            {
                "dog_id": self._dog_id,
                "enabled": state,
            },
            blocking=True,
        )


class PawControlPortionControlSwitch(PawControlSwitchBase):
    """Switch to enable/disable portion size tracking."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the portion control switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "portion_control",
            icon="mdi:scale",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the portion control state."""
        # This would enable/disable portion tracking features
        pass


class PawControlFeedingAlertsSwitch(PawControlSwitchBase):
    """Switch to enable/disable feeding alerts."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the feeding alerts switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_alerts",
            icon="mdi:alert-circle",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the feeding alerts state."""
        # This would configure feeding alert notifications
        pass


# GPS switches
class PawControlGPSTrackingSwitch(PawControlSwitchBase):
    """Switch to enable/disable GPS tracking."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the GPS tracking switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_tracking",
            icon="mdi:crosshairs-gps",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the GPS tracking state."""
        # Configure GPS data collection through data manager
        try:
            runtime_data = self.hass.data[DOMAIN][
                self.coordinator.config_entry.entry_id
            ]
            data_manager = runtime_data.get("data_manager")

            if data_manager:
                await data_manager.async_set_gps_tracking(self._dog_id, state)

            # Update coordinator to reflect changes
            await self.coordinator.async_refresh_dog(self._dog_id)

        except Exception as err:
            _LOGGER.warning("Failed to configure GPS tracking: %s", err)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for GPS tracking."""
        attrs = super().extra_state_attributes
        gps_data = self._get_module_data("gps")

        if gps_data:
            attrs.update(
                {
                    "gps_accuracy": gps_data.get("accuracy"),
                    "last_location_update": gps_data.get("last_seen"),
                    "battery_level": gps_data.get("battery_level"),
                    "signal_quality": self._assess_signal_quality(gps_data),
                }
            )

        return attrs

    def _assess_signal_quality(self, gps_data: dict[str, Any]) -> str:
        """Assess GPS signal quality."""
        accuracy = gps_data.get("accuracy")
        if accuracy is None:
            return "unknown"

        if accuracy <= 10:
            return "excellent"
        elif accuracy <= 25:
            return "good"
        elif accuracy <= 50:
            return "fair"
        else:
            return "poor"


class PawControlGeofencingSwitch(PawControlSwitchBase):
    """Switch to enable/disable geofencing alerts."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the geofencing switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "geofencing",
            icon="mdi:map-marker-circle",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the geofencing state."""
        # This would enable/disable geofence monitoring
        pass


class PawControlRouteRecordingSwitch(PawControlSwitchBase):
    """Switch to enable/disable route recording."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the route recording switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "route_recording",
            icon="mdi:map-marker-path",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the route recording state."""
        # This would enable/disable GPS route recording
        pass


class PawControlAutoWalkDetectionSwitch(PawControlSwitchBase):
    """Switch to enable/disable automatic walk detection."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the auto walk detection switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "auto_walk_detection",
            icon="mdi:walk",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the auto walk detection state."""
        # This would enable/disable automatic walk start/end detection
        pass


class PawControlLocationSharingSwitch(PawControlSwitchBase):
    """Switch to enable/disable location sharing."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the location sharing switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "location_sharing",
            icon="mdi:share-variant",
            initial_state=False,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the location sharing state."""
        # This would control sharing location data with external services
        pass


# Health switches
class PawControlHealthMonitoringSwitch(PawControlSwitchBase):
    """Switch to enable/disable health monitoring."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the health monitoring switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_monitoring",
            icon="mdi:heart-pulse",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the health monitoring state."""
        # This would enable/disable health data collection
        pass


class PawControlWeightTrackingSwitch(PawControlSwitchBase):
    """Switch to enable/disable weight tracking."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the weight tracking switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weight_tracking",
            icon="mdi:scale",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the weight tracking state."""
        # This would enable/disable weight monitoring and trends
        pass


class PawControlMedicationRemindersSwitch(PawControlSwitchBase):
    """Switch to enable/disable medication reminders."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the medication reminders switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "medication_reminders",
            icon="mdi:pill",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the medication reminders state."""
        # This would enable/disable medication alert notifications
        pass


class PawControlVetRemindersSwitch(PawControlSwitchBase):
    """Switch to enable/disable veterinary reminders."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the vet reminders switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "vet_reminders",
            icon="mdi:medical-bag",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the vet reminders state."""
        # This would enable/disable vet appointment reminders
        pass


class PawControlActivityTrackingSwitch(PawControlSwitchBase):
    """Switch to enable/disable activity tracking."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the activity tracking switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "activity_tracking",
            icon="mdi:run",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the activity tracking state."""
        # This would enable/disable activity level monitoring
        pass


# Notification switches
class PawControlNotificationsSwitch(PawControlSwitchBase):
    """Switch to enable/disable notifications."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the notifications switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "notifications",
            icon="mdi:bell",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the notifications state."""
        # Configure all notifications for this dog
        await self.hass.services.async_call(
            DOMAIN,
            "configure_alerts",
            {
                "dog_id": self._dog_id,
                "feeding_alerts": state,
                "walk_alerts": state,
                "health_alerts": state,
                "gps_alerts": state,
            },
            blocking=True,
        )


class PawControlUrgentNotificationsSwitch(PawControlSwitchBase):
    """Switch to enable/disable urgent notifications only."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the urgent notifications switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "urgent_notifications",
            icon="mdi:bell-alert",
            initial_state=True,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the urgent notifications state."""
        # This would configure to only send urgent/critical notifications
        pass


class PawControlDailyReportsSwitch(PawControlSwitchBase):
    """Switch to enable/disable daily reports."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the daily reports switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "daily_reports",
            icon="mdi:file-chart",
            initial_state=False,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the daily reports state."""
        # This would enable/disable daily summary notifications
        pass


class PawControlWeeklyReportsSwitch(PawControlSwitchBase):
    """Switch to enable/disable weekly reports."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the weekly reports switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weekly_reports",
            icon="mdi:calendar-week",
            initial_state=False,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the weekly reports state."""
        # This would enable/disable weekly summary notifications
        pass


class PawControlSoundAlertsSwitch(PawControlSwitchBase):
    """Switch to enable/disable sound alerts."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sound alerts switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "sound_alerts",
            icon="mdi:volume-high",
            initial_state=False,
        )

    async def _async_set_switch_state(self, state: bool) -> None:
        """Set the sound alerts state."""
        # This would enable/disable audio notifications/TTS
        pass
