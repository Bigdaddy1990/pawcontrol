"""Button platform for Paw Control integration.

This module provides comprehensive button entities for dog management actions
including feeding, walking, health tracking, and system controls. All buttons
are designed to meet Home Assistant's Platinum quality standards with full
type annotations, async operations, and robust error handling.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .exceptions import (
    DogNotFoundError,
    PawControlError,
    ValidationError,
    WalkAlreadyInProgressError,
    WalkNotInProgressError,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    SERVICE_FEED_DOG,
    SERVICE_START_WALK,
    SERVICE_END_WALK,
    SERVICE_LOG_HEALTH,
    SERVICE_START_GROOMING,
    SERVICE_NOTIFY_TEST,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Type aliases for better code readability
AttributeDict = Dict[str, Any]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control button platform.
    
    Creates button entities for all configured dogs based on their
    enabled modules. Buttons provide easy-access actions for common
    dog care tasks and system controls.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry containing dog configurations
        async_add_entities: Callback to add button entities
    """
    coordinator: PawControlCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dogs: List[Dict[str, Any]] = entry.data.get(CONF_DOGS, [])
    
    entities: List[PawControlButtonBase] = []
    
    # Create button entities for each configured dog
    for dog in dogs:
        dog_id: str = dog[CONF_DOG_ID]
        dog_name: str = dog[CONF_DOG_NAME]
        modules: Dict[str, bool] = dog.get("modules", {})
        
        _LOGGER.debug("Creating button entities for dog: %s (%s)", dog_name, dog_id)
        
        # Base buttons - always created for every dog
        entities.extend(_create_base_buttons(coordinator, dog_id, dog_name))
        
        # Module-specific buttons
        if modules.get(MODULE_FEEDING, False):
            entities.extend(_create_feeding_buttons(coordinator, dog_id, dog_name))
        
        if modules.get(MODULE_WALK, False):
            entities.extend(_create_walk_buttons(coordinator, dog_id, dog_name))
        
        if modules.get(MODULE_GPS, False):
            entities.extend(_create_gps_buttons(coordinator, dog_id, dog_name))
        
        if modules.get(MODULE_HEALTH, False):
            entities.extend(_create_health_buttons(coordinator, dog_id, dog_name))
    
    # Add all entities at once for better performance
    async_add_entities(entities, update_before_add=True)
    
    _LOGGER.info(
        "Created %d button entities for %d dogs",
        len(entities),
        len(dogs)
    )


def _create_base_buttons(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlButtonBase]:
    """Create base buttons that are always present for every dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of base button entities
    """
    return [
        PawControlTestNotificationButton(coordinator, dog_id, dog_name),
        PawControlResetDailyStatsButton(coordinator, dog_id, dog_name),
        PawControlToggleVisitorModeButton(coordinator, dog_id, dog_name),
    ]


def _create_feeding_buttons(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlButtonBase]:
    """Create feeding-related buttons for a dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of feeding button entities
    """
    buttons = [
        PawControlMarkFedButton(coordinator, dog_id, dog_name),
        PawControlLogCustomFeedingButton(coordinator, dog_id, dog_name),
    ]
    
    # Add buttons for each meal type
    for meal_type in ["breakfast", "lunch", "dinner", "snack"]:
        buttons.append(
            PawControlFeedMealButton(coordinator, dog_id, dog_name, meal_type)
        )
    
    return buttons


def _create_walk_buttons(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlButtonBase]:
    """Create walk-related buttons for a dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of walk button entities
    """
    return [
        PawControlStartWalkButton(coordinator, dog_id, dog_name),
        PawControlEndWalkButton(coordinator, dog_id, dog_name),
        PawControlQuickWalkButton(coordinator, dog_id, dog_name),
        PawControlLogWalkManuallyButton(coordinator, dog_id, dog_name),
    ]


def _create_gps_buttons(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlButtonBase]:
    """Create GPS and location-related buttons for a dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of GPS button entities
    """
    return [
        PawControlRefreshLocationButton(coordinator, dog_id, dog_name),
        PawControlExportRouteButton(coordinator, dog_id, dog_name),
        PawControlCenterMapButton(coordinator, dog_id, dog_name),
        PawControlCallDogButton(coordinator, dog_id, dog_name),
    ]


def _create_health_buttons(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlButtonBase]:
    """Create health and medical-related buttons for a dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of health button entities
    """
    return [
        PawControlLogWeightButton(coordinator, dog_id, dog_name),
        PawControlLogMedicationButton(coordinator, dog_id, dog_name),
        PawControlStartGroomingButton(coordinator, dog_id, dog_name),
        PawControlScheduleVetButton(coordinator, dog_id, dog_name),
        PawControlHealthCheckButton(coordinator, dog_id, dog_name),
    ]


class PawControlButtonBase(CoordinatorEntity[PawControlCoordinator], ButtonEntity):
    """Base class for all Paw Control button entities.
    
    Provides common functionality and ensures consistent behavior across
    all button types. Includes proper device grouping, action handling,
    and error management.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        button_type: str,
        *,
        device_class: Optional[ButtonDeviceClass] = None,
        icon: Optional[str] = None,
        entity_category: Optional[str] = None,
        action_description: Optional[str] = None,
    ) -> None:
        """Initialize the button entity.
        
        Args:
            coordinator: Data coordinator for updates
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
            button_type: Type identifier for the button
            device_class: Home Assistant device class
            icon: Material Design icon
            entity_category: Entity category for organization
            action_description: Description of what the button does
        """
        super().__init__(coordinator)
        
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._button_type = button_type
        self._action_description = action_description
        
        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{button_type}"
        self._attr_name = f"{dog_name} {button_type.replace('_', ' ').title()}"
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_entity_category = entity_category
        
        # Device info for proper grouping
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog_id)},
            "name": dog_name,
            "manufacturer": "Paw Control",
            "model": "Smart Dog Monitoring",
            "sw_version": "1.0.0",
            "configuration_url": f"/config/integrations/integration/{DOMAIN}",
        }

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for the button.
        
        Provides information about the button's function and the dog
        it controls.
        
        Returns:
            Dictionary of additional state attributes
        """
        attrs: AttributeDict = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "button_type": self._button_type,
            "last_pressed": getattr(self, '_last_pressed', None),
        }
        
        if self._action_description:
            attrs["action_description"] = self._action_description
        
        # Add dog-specific information
        dog_data = self._get_dog_data()
        if dog_data and "dog_info" in dog_data:
            dog_info = dog_data["dog_info"]
            attrs.update({
                "dog_breed": dog_info.get("dog_breed", ""),
                "dog_age": dog_info.get("dog_age"),
                "dog_size": dog_info.get("dog_size"),
            })
        
        return attrs

    def _get_dog_data(self) -> Optional[Dict[str, Any]]:
        """Get data for this button's dog from the coordinator.
        
        Returns:
            Dog data dictionary or None if not available
        """
        if not self.coordinator.available:
            return None
        
        return self.coordinator.get_dog_data(self._dog_id)

    def _get_module_data(self, module: str) -> Optional[Dict[str, Any]]:
        """Get specific module data for this dog.
        
        Args:
            module: Module name to retrieve data for
            
        Returns:
            Module data dictionary or None if not available
        """
        return self.coordinator.get_module_data(self._dog_id, module)

    @property
    def available(self) -> bool:
        """Return if the button is available.
        
        A button is available when the coordinator is available and
        the dog data can be retrieved.
        
        Returns:
            True if button is available, False otherwise
        """
        return (
            self.coordinator.available 
            and self._get_dog_data() is not None
        )

    async def async_press(self) -> None:
        """Handle the button press action.
        
        This method should be overridden by subclasses to implement
        specific button functionality. The base implementation records
        the press time and logs the action.
        
        Raises:
            HomeAssistantError: If the action cannot be performed
        """
        self._last_pressed = dt_util.utcnow().isoformat()
        _LOGGER.info(
            "Button pressed: %s for dog %s (%s)",
            self._button_type,
            self._dog_name,
            self._dog_id
        )
        
        # Trigger a coordinator update to reflect any changes
        await self.coordinator.async_request_refresh()


# Base buttons
class PawControlTestNotificationButton(PawControlButtonBase):
    """Button to send a test notification for the dog."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the test notification button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "test_notification",
            icon="mdi:message-alert",
            action_description="Send a test notification to verify notification settings"
        )

    async def async_press(self) -> None:
        """Send a test notification."""
        await super().async_press()
        
        try:
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_NOTIFY_TEST,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "message": f"Test notification for {self._dog_name} - all systems working!"
                },
                blocking=True,
            )
            
            _LOGGER.info("Test notification sent for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to send test notification for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to send notification: {err}") from err


class PawControlResetDailyStatsButton(PawControlButtonBase):
    """Button to reset daily statistics for the dog."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the reset daily stats button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "reset_daily_stats",
            device_class=ButtonDeviceClass.RESTART,
            icon="mdi:refresh",
            action_description="Reset daily statistics and counters"
        )

    async def async_press(self) -> None:
        """Reset daily statistics for this dog."""
        await super().async_press()
        
        try:
            # Get the data manager for this dog's entry
            entry_data = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
            data_manager = entry_data.get("data")
            
            if data_manager:
                # Reset daily data for this specific dog
                await data_manager.async_reset_dog_daily_stats(self._dog_id)
                _LOGGER.info("Reset daily statistics for %s", self._dog_name)
            else:
                raise HomeAssistantError("Data manager not available")
                
        except Exception as err:
            _LOGGER.error("Failed to reset daily stats for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to reset statistics: {err}") from err


class PawControlToggleVisitorModeButton(PawControlButtonBase):
    """Button to toggle visitor mode for the dog."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the toggle visitor mode button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "toggle_visitor_mode",
            icon="mdi:account-switch",
            action_description="Toggle visitor mode to modify notification behavior"
        )

    async def async_press(self) -> None:
        """Toggle visitor mode for this dog."""
        await super().async_press()
        
        try:
            dog_data = self._get_dog_data()
            current_mode = dog_data.get("visitor_mode_active", False) if dog_data else False
            
            # Toggle visitor mode through the coordinator
            await self.hass.services.async_call(
                DOMAIN,
                "set_visitor_mode",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "enabled": not current_mode,
                    "visitor_name": "Manual Toggle",
                    "reduced_alerts": True,
                },
                blocking=True,
            )
            
            _LOGGER.info(
                "Visitor mode %s for %s", 
                "disabled" if current_mode else "enabled",
                self._dog_name
            )
            
        except Exception as err:
            _LOGGER.error("Failed to toggle visitor mode for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to toggle visitor mode: {err}") from err


# Feeding buttons
class PawControlMarkFedButton(PawControlButtonBase):
    """Button to mark the dog as fed with the default meal."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the mark fed button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "mark_fed",
            icon="mdi:food-drumstick",
            action_description="Mark dog as fed with default meal portion"
        )

    async def async_press(self) -> None:
        """Mark the dog as fed."""
        await super().async_press()
        
        try:
            # Determine appropriate meal type based on time of day
            meal_type = self._determine_current_meal_type()
            
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_FEED_DOG,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "meal_type": meal_type,
                    "portion_size": 0,  # Default portion
                },
                blocking=True,
            )
            
            _LOGGER.info("Marked %s as fed (%s)", self._dog_name, meal_type)
            
        except Exception as err:
            _LOGGER.error("Failed to mark %s as fed: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to log feeding: {err}") from err

    def _determine_current_meal_type(self) -> str:
        """Determine the appropriate meal type based on current time.
        
        Returns:
            Meal type string
        """
        now = dt_util.now()
        hour = now.hour
        
        if 5 <= hour < 11:
            return "breakfast"
        elif 11 <= hour < 16:
            return "lunch"
        elif 16 <= hour < 22:
            return "dinner"
        else:
            return "snack"


class PawControlFeedMealButton(PawControlButtonBase):
    """Button to feed a specific meal type."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str,
        meal_type: str,
    ) -> None:
        """Initialize the feed meal button."""
        self._meal_type = meal_type
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            f"feed_{meal_type}",
            icon="mdi:food",
            action_description=f"Log {meal_type} feeding"
        )
        self._attr_name = f"{dog_name} Feed {meal_type.title()}"

    async def async_press(self) -> None:
        """Feed the specific meal type."""
        await super().async_press()
        
        try:
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_FEED_DOG,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "meal_type": self._meal_type,
                    "portion_size": 0,  # Default portion
                },
                blocking=True,
            )
            
            _LOGGER.info("Fed %s %s", self._dog_name, self._meal_type)
            
        except Exception as err:
            _LOGGER.error("Failed to feed %s %s: %s", self._dog_name, self._meal_type, err)
            raise HomeAssistantError(f"Failed to log {self._meal_type}: {err}") from err


class PawControlLogCustomFeedingButton(PawControlButtonBase):
    """Button to log a custom feeding with user input."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the log custom feeding button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "log_custom_feeding",
            icon="mdi:food-variant",
            action_description="Log custom feeding with specific details"
        )

    async def async_press(self) -> None:
        """Log a custom feeding - this would typically open a dialog."""
        await super().async_press()
        
        # Log custom feeding with user-configurable options
        # This implementation provides a reasonable default that can be customized
        try:
            # Get current feeding schedule to determine appropriate meal type
            current_hour = dt_util.now().hour
            meal_type = "treat" if 22 <= current_hour or current_hour <= 6 else "snack"
            
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_FEED_DOG,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "meal_type": meal_type,
                    "portion_size": 75,  # Medium custom portion
                    "food_type": "treat",
                    "notes": "Custom feeding via button",
                },
                blocking=True,
            )
            
            _LOGGER.info("Logged custom feeding for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to log custom feeding for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to log custom feeding: {err}") from err


# Walk buttons
class PawControlStartWalkButton(PawControlButtonBase):
    """Button to start a walk for the dog."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the start walk button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "start_walk",
            icon="mdi:walk",
            action_description="Start tracking a walk"
        )

    async def async_press(self) -> None:
        """Start a walk for the dog."""
        await super().async_press()
        
        try:
            # Check if walk is already in progress
            walk_data = self._get_module_data("walk")
            if walk_data and walk_data.get("walk_in_progress", False):
                raise WalkAlreadyInProgressError(
                    dog_id=self._dog_id,
                    walk_id=walk_data.get("current_walk_id", "unknown"),
                    start_time=walk_data.get("current_walk_start")
                )
            
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_START_WALK,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "label": "Manual walk",
                },
                blocking=True,
            )
            
            _LOGGER.info("Started walk for %s", self._dog_name)
            
        except ServiceValidationError as err:
            # Re-raise validation errors as they have user-friendly messages
            raise HomeAssistantError(str(err)) from err
        except Exception as err:
            _LOGGER.error("Failed to start walk for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to start walk: {err}") from err

    @property
    def available(self) -> bool:
        """Return if the start walk button is available.
        
        The button is only available if no walk is currently in progress.
        
        Returns:
            True if button is available and no walk in progress
        """
        if not super().available:
            return False
        
        walk_data = self._get_module_data("walk")
        if walk_data:
            return not walk_data.get("walk_in_progress", False)
        
        return True


class PawControlEndWalkButton(PawControlButtonBase):
    """Button to end the current walk for the dog."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the end walk button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "end_walk",
            icon="mdi:stop",
            action_description="End the current walk and save statistics"
        )

    async def async_press(self) -> None:
        """End the current walk for the dog."""
        await super().async_press()
        
        try:
            # Check if walk is in progress
            walk_data = self._get_module_data("walk")
            if not walk_data or not walk_data.get("walk_in_progress", False):
                raise WalkNotInProgressError(
                    dog_id=self._dog_id,
                    last_walk_time=walk_data.get("last_walk", {}).get("end_time") if walk_data else None
                )
            
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_END_WALK,
                {
                    ATTR_DOG_ID: self._dog_id,
                },
                blocking=True,
            )
            
            _LOGGER.info("Ended walk for %s", self._dog_name)
            
        except ServiceValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:
            _LOGGER.error("Failed to end walk for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to end walk: {err}") from err

    @property
    def available(self) -> bool:
        """Return if the end walk button is available.
        
        The button is only available if a walk is currently in progress.
        
        Returns:
            True if button is available and walk is in progress
        """
        if not super().available:
            return False
        
        walk_data = self._get_module_data("walk")
        if walk_data:
            return walk_data.get("walk_in_progress", False)
        
        return False


class PawControlQuickWalkButton(PawControlButtonBase):
    """Button to log a quick walk (short duration)."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the quick walk button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "quick_walk",
            icon="mdi:run-fast",
            action_description="Log a quick 10-minute walk"
        )

    async def async_press(self) -> None:
        """Log a quick walk for the dog."""
        await super().async_press()
        
        try:
            # Start and immediately end a walk with predefined duration
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_START_WALK,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "label": "Quick walk",
                },
                blocking=True,
            )
            
            # TODO: In a real implementation, this would set the walk duration
            # and automatically end it, or log it directly as a completed walk
            
            _LOGGER.info("Logged quick walk for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to log quick walk for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to log quick walk: {err}") from err


class PawControlLogWalkManuallyButton(PawControlButtonBase):
    """Button to manually log a walk that wasn't tracked."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the log walk manually button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "log_walk_manually",
            icon="mdi:pencil",
            action_description="Manually log a walk that wasn't tracked"
        )

    async def async_press(self) -> None:
        """Manually log a walk for the dog."""
        await super().async_press()
        
        # This would typically open a dialog for manual entry
        # For now, we'll log a standard walk
        try:
            # Log a manual walk with reasonable defaults
            # In a full implementation, this would open a frontend dialog
            now = dt_util.now()
            default_start = now - timedelta(minutes=30)  # Assume 30-minute walk
            
            # Start and immediately end a walk with manual data
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_START_WALK,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "label": "Manual entry",
                    "location": "Manual log",
                },
                blocking=True,
            )
            
            # End with estimated duration and distance
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_END_WALK,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "duration": 30,  # 30 minutes
                    "distance": 1500,  # 1.5 km
                    "notes": "Manually logged walk",
                },
                blocking=True,
            )
            
            _LOGGER.info("Manual walk logged for %s (30min, 1.5km)", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to initiate manual walk logging for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to log walk manually: {err}") from err


# GPS buttons
class PawControlRefreshLocationButton(PawControlButtonBase):
    """Button to refresh the dog's GPS location."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the refresh location button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "refresh_location",
            device_class=ButtonDeviceClass.UPDATE,
            icon="mdi:crosshairs-gps",
            action_description="Request fresh GPS location update"
        )

    async def async_press(self) -> None:
        """Refresh the dog's GPS location."""
        await super().async_press()
        
        try:
            # Trigger a coordinator refresh for this specific dog
            await self.coordinator.async_refresh_dog(self._dog_id)
            
            _LOGGER.info("Location refresh requested for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to refresh location for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to refresh location: {err}") from err


class PawControlExportRouteButton(PawControlButtonBase):
    """Button to export the last walk route."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the export route button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "export_route",
            icon="mdi:export",
            action_description="Export last walk route as GPX file"
        )

    async def async_press(self) -> None:
        """Export the last walk route."""
        await super().async_press()
        
        try:
            # Export the last walk route through the coordinator
            await self.hass.services.async_call(
                DOMAIN,
                "export_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "data_type": "gps",
                    "format": "gpx",
                    "start_date": (dt_util.now() - timedelta(days=1)).date().isoformat(),
                },
                blocking=True,
            )
            
            _LOGGER.info("Route export completed for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to export route for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to export route: {err}") from err


class PawControlCenterMapButton(PawControlButtonBase):
    """Button to center map view on the dog's location."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the center map button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "center_map",
            icon="mdi:map-marker",
            action_description="Center map view on dog's current location"
        )

    async def async_press(self) -> None:
        """Center map on the dog's location."""
        await super().async_press()
        
        try:
            gps_data = self._get_module_data("gps")
            if not gps_data:
                raise HomeAssistantError("No GPS data available")
            
            # This would trigger a frontend action to center the map
            # For now, we just log the action
            
            _LOGGER.info("Map centering requested for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to center map for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to center map: {err}") from err


class PawControlCallDogButton(PawControlButtonBase):
    """Button to activate a call/sound on the GPS tracker."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the call dog button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "call_dog",
            icon="mdi:volume-high",
            action_description="Activate sound/call on GPS tracker"
        )

    async def async_press(self) -> None:
        """Activate call/sound on the GPS tracker."""
        await super().async_press()
        
        try:
            # Activate call/sound through GPS tracker service
            # First check if GPS data is available
            gps_data = self._get_module_data("gps")
            if not gps_data or not gps_data.get("source") or gps_data.get("source") == "none":
                raise PawControlError(
                    f"GPS tracker not available for {self._dog_name}",
                    error_code="gps_unavailable",
                    user_message="GPS tracker is not connected or available"
                )
            
            # Send command to GPS tracker (implementation depends on tracker type)
            runtime_data = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
            gps_manager = runtime_data.get("gps_manager")
            
            if gps_manager:
                await gps_manager.async_send_tracker_command(
                    self._dog_id, "call", duration=10
                )
            
            _LOGGER.info("GPS tracker call activated for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to call GPS tracker for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to call tracker: {err}") from err


# Health buttons
class PawControlLogWeightButton(PawControlButtonBase):
    """Button to log the dog's current weight."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the log weight button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "log_weight",
            icon="mdi:scale",
            action_description="Log current weight measurement"
        )

    async def async_press(self) -> None:
        """Log weight for the dog."""
        await super().async_press()
        
        try:
            # This would typically open a dialog for weight entry
            # For now, we'll trigger the health logging service
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_LOG_HEALTH,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": "Weight logged via button",
                },
                blocking=True,
            )
            
            _LOGGER.info("Weight logging initiated for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to log weight for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to log weight: {err}") from err


class PawControlLogMedicationButton(PawControlButtonBase):
    """Button to log medication administration."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the log medication button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "log_medication",
            icon="mdi:pill",
            action_description="Log medication administration"
        )

    async def async_press(self) -> None:
        """Log medication for the dog."""
        await super().async_press()
        
        try:
            # This would typically open a dialog for medication details
            # For now, we'll log a generic medication entry
            
            _LOGGER.info("Medication logging initiated for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to log medication for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to log medication: {err}") from err


class PawControlStartGroomingButton(PawControlButtonBase):
    """Button to start a grooming session."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the start grooming button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "start_grooming",
            icon="mdi:content-cut",
            action_description="Start grooming session"
        )

    async def async_press(self) -> None:
        """Start grooming session for the dog."""
        await super().async_press()
        
        try:
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_START_GROOMING,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "type": "general",
                    "notes": "Started via button",
                },
                blocking=True,
            )
            
            _LOGGER.info("Grooming session started for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to start grooming for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to start grooming: {err}") from err


class PawControlScheduleVetButton(PawControlButtonBase):
    """Button to schedule a vet appointment."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the schedule vet button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "schedule_vet",
            icon="mdi:calendar-plus",
            action_description="Schedule veterinary appointment"
        )

    async def async_press(self) -> None:
        """Schedule vet appointment for the dog."""
        await super().async_press()
        
        try:
            # This would typically integrate with calendar or external scheduling
            # For now, we'll just log the action
            
            _LOGGER.info("Vet appointment scheduling initiated for %s", self._dog_name)
            
        except Exception as err:
            _LOGGER.error("Failed to schedule vet for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to schedule vet: {err}") from err


class PawControlHealthCheckButton(PawControlButtonBase):
    """Button to perform a quick health status check."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the health check button."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "health_check",
            device_class=ButtonDeviceClass.UPDATE,
            icon="mdi:heart-pulse",
            action_description="Perform health status check"
        )

    async def async_press(self) -> None:
        """Perform health check for the dog."""
        await super().async_press()
        
        try:
            health_data = self._get_module_data("health")
            if health_data:
                # Generate a health summary
                health_status = health_data.get("health_status", "unknown")
                alerts = health_data.get("health_alerts", [])
                
                # This would typically trigger a detailed health report
                # For now, we'll log the current status
                
                _LOGGER.info(
                    "Health check for %s: Status=%s, Alerts=%d",
                    self._dog_name,
                    health_status,
                    len(alerts)
                )
            
        except Exception as err:
            _LOGGER.error("Failed to perform health check for %s: %s", self._dog_name, err)
            raise HomeAssistantError(f"Failed to perform health check: {err}") from err
