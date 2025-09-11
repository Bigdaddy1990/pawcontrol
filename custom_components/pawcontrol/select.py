"""Select platform for Paw Control integration.

This module provides comprehensive select entities for dog monitoring configuration
including mode selections, option choices, and status settings. All select entities
are designed to meet Home Assistant's Platinum quality standards with full type
annotations, async operations, and robust validation.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ACTIVITY_LEVELS
from .const import ATTR_DOG_ID
from .const import ATTR_DOG_NAME
from .const import CONF_DOG_ID
from .const import CONF_DOG_NAME
from .const import CONF_DOG_SIZE
from .const import CONF_DOGS
from .const import DOG_SIZES
from .const import DOMAIN
from .const import FOOD_TYPES
from .const import GPS_SOURCES
from .const import HEALTH_STATUS_OPTIONS
from .const import MEAL_TYPES
from .const import MODULE_FEEDING
from .const import MODULE_GPS
from .const import MODULE_HEALTH
from .const import MODULE_WALK
from .const import MOOD_OPTIONS
from .const import PERFORMANCE_MODES
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Type aliases for better code readability
AttributeDict = Dict[str, Any]

# Additional option lists for selects
WALK_MODES = [
    "automatic",
    "manual",
    "hybrid",
]

NOTIFICATION_PRIORITIES = [
    "low",
    "normal",
    "high",
    "urgent",
]

TRACKING_MODES = [
    "continuous",
    "interval",
    "on_demand",
    "battery_saver",
]

FEEDING_SCHEDULES = [
    "flexible",
    "strict",
    "custom",
]

GROOMING_TYPES = [
    "bath",
    "brush",
    "nails",
    "teeth",
    "trim",
    "full_grooming",
]

WEATHER_CONDITIONS = [
    "any",
    "sunny",
    "cloudy",
    "light_rain",
    "no_rain",
    "warm",
    "cool",
]


async def _async_add_entities_in_batches(
    async_add_entities_func,
    entities: list[PawControlSelectBase],
    batch_size: int = 10,
    delay_between_batches: float = 0.1,
) -> None:
    """Add select entities in small batches to prevent Entity Registry overload.

    The Entity Registry logs warnings when >200 messages occur rapidly.
    By batching entities and adding delays, we prevent registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of select entities to add
        batch_size: Number of entities per batch (default: 10)
        delay_between_batches: Seconds to wait between batches (default: 0.1s)
    """
    total_entities = len(entities)

    _LOGGER.debug(
        "Adding %d select entities in batches of %d to prevent Registry overload",
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
        batch = entities[i: i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            "Processing select batch %d/%d with %d entities",
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
    """Set up Paw Control select platform.

    Creates select entities for all configured dogs to control various
    options and modes. Selects provide dropdown choices for configuration
    and operational settings.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry containing dog configurations
        async_add_entities: Callback to add select entities
    """
    runtime_data = getattr(entry, "runtime_data", None)

    if runtime_data:
        coordinator: PawControlCoordinator = runtime_data["coordinator"]
        dogs: list[dict[str, Any]] = runtime_data.get("dogs", [])
    else:
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        dogs = entry.data.get(CONF_DOGS, [])

    entities: list[PawControlSelectBase] = []

    # Create select entities for each configured dog
    for dog in dogs:
        dog_id: str = dog[CONF_DOG_ID]
        dog_name: str = dog[CONF_DOG_NAME]
        modules: dict[str, bool] = dog.get("modules", {})

        _LOGGER.debug("Creating select entities for dog: %s (%s)",
                      dog_name, dog_id)

        # Base selects - always created for every dog
        entities.extend(_create_base_selects(
            coordinator, dog_id, dog_name, dog))

        # Module-specific selects
        if modules.get(MODULE_FEEDING, False):
            entities.extend(_create_feeding_selects(
                coordinator, dog_id, dog_name))

        if modules.get(MODULE_WALK, False):
            entities.extend(_create_walk_selects(
                coordinator, dog_id, dog_name))

        if modules.get(MODULE_GPS, False):
            entities.extend(_create_gps_selects(coordinator, dog_id, dog_name))

        if modules.get(MODULE_HEALTH, False):
            entities.extend(_create_health_selects(
                coordinator, dog_id, dog_name))

    # Add entities in smaller batches to prevent Entity Registry overload
    # With 32+ select entities (2 dogs), batching prevents Registry flooding
    await _async_add_entities_in_batches(async_add_entities, entities, batch_size=10)

    _LOGGER.info(
        "Created %d select entities for %d dogs using batched approach",
        len(entities),
        len(dogs),
    )


def _create_base_selects(
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    dog_config: dict[str, Any],
) -> list[PawControlSelectBase]:
    """Create base selects that are always present for every dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        dog_config: Dog configuration data

    Returns:
        List of base select entities
    """
    return [
        PawControlDogSizeSelect(coordinator, dog_id, dog_name, dog_config),
        PawControlPerformanceModeSelect(coordinator, dog_id, dog_name),
        PawControlNotificationPrioritySelect(coordinator, dog_id, dog_name),
    ]


def _create_feeding_selects(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSelectBase]:
    """Create feeding-related selects for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of feeding select entities
    """
    return [
        PawControlFoodTypeSelect(coordinator, dog_id, dog_name),
        PawControlFeedingScheduleSelect(coordinator, dog_id, dog_name),
        PawControlDefaultMealTypeSelect(coordinator, dog_id, dog_name),
        PawControlFeedingModeSelect(coordinator, dog_id, dog_name),
    ]


def _create_walk_selects(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSelectBase]:
    """Create walk-related selects for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of walk select entities
    """
    return [
        PawControlWalkModeSelect(coordinator, dog_id, dog_name),
        PawControlWeatherPreferenceSelect(coordinator, dog_id, dog_name),
        PawControlWalkIntensitySelect(coordinator, dog_id, dog_name),
    ]


def _create_gps_selects(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSelectBase]:
    """Create GPS and location-related selects for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of GPS select entities
    """
    return [
        PawControlGPSSourceSelect(coordinator, dog_id, dog_name),
        PawControlTrackingModeSelect(coordinator, dog_id, dog_name),
        PawControlLocationAccuracySelect(coordinator, dog_id, dog_name),
    ]


def _create_health_selects(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSelectBase]:
    """Create health and medical-related selects for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of health select entities
    """
    return [
        PawControlHealthStatusSelect(coordinator, dog_id, dog_name),
        PawControlActivityLevelSelect(coordinator, dog_id, dog_name),
        PawControlMoodSelect(coordinator, dog_id, dog_name),
        PawControlGroomingTypeSelect(coordinator, dog_id, dog_name),
    ]


class PawControlSelectBase(
    CoordinatorEntity[PawControlCoordinator], SelectEntity, RestoreEntity
):
    """Base class for all Paw Control select entities.

    Provides common functionality and ensures consistent behavior across
    all select types. Includes proper device grouping, state persistence,
    validation, and error handling.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        select_type: str,
        *,
        options: list[str],
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
        initial_option: str | None = None,
    ) -> None:
        """Initialize the select entity.

        Args:
            coordinator: Data coordinator for updates
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
            select_type: Type identifier for the select
            options: List of available options
            icon: Material Design icon
            entity_category: Entity category for organization
            initial_option: Initial selected option
        """
        super().__init__(coordinator)

        self._dog_id = dog_id
        self._dog_name = dog_name
        self._select_type = select_type
        self._current_option = initial_option

        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{select_type}"
        self._attr_name = f"{dog_name} {select_type.replace('_', ' ').title()}"
        self._attr_options = options
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

        Restores the previous option and sets up any required listeners.
        """
        await super().async_added_to_hass()

        # Restore previous option
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self.options:
            self._current_option = last_state.state
            _LOGGER.debug(
                "Restored select option for %s %s: %s",
                self._dog_name,
                self._select_type,
                self._current_option,
            )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option.

        Returns:
            Currently selected option
        """
        return self._current_option

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for the select.

        Provides information about the select's function and available options.

        Returns:
            Dictionary of additional state attributes
        """
        attrs: AttributeDict = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "select_type": self._select_type,
            "available_options": self.options,
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

    async def async_select_option(self, option: str) -> None:
        """Select an option.

        Args:
            option: Option to select

        Raises:
            HomeAssistantError: If option is invalid or cannot be set
        """
        if option not in self.options:
            raise HomeAssistantError(
                f"Invalid option '{option}' for {self._select_type}"
            )

        try:
            await self._async_set_select_option(option)
            self._current_option = option
            self.async_write_ha_state()

            _LOGGER.info(
                "Set %s for %s (%s) to '%s'",
                self._select_type,
                self._dog_name,
                self._dog_id,
                option,
            )

        except Exception as err:
            _LOGGER.error(
                "Failed to set %s for %s: %s", self._select_type, self._dog_name, err
            )
            raise HomeAssistantError(
                f"Failed to set {self._select_type}") from err

    async def _async_set_select_option(self, option: str) -> None:
        """Set the select option implementation.

        This method should be overridden by subclasses to implement
        specific select functionality.

        Args:
            option: Option to set
        """
        # Base implementation - subclasses should override
        pass

    def _get_dog_data(self) -> dict[str, Any] | None:
        """Get data for this select's dog from the coordinator.

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
        """Return if the select is available.

        A select is available when the coordinator is available and
        the dog data can be retrieved.

        Returns:
            True if select is available, False otherwise
        """
        return self.coordinator.available and self._get_dog_data() is not None


# Base selects
class PawControlDogSizeSelect(PawControlSelectBase):
    """Select entity for the dog's size category."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        dog_config: dict[str, Any],
    ) -> None:
        """Initialize the dog size select."""
        current_size = dog_config.get(CONF_DOG_SIZE, "medium")

        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "size",
            options=DOG_SIZES,
            icon="mdi:dog",
            entity_category=EntityCategory.CONFIG,
            initial_option=current_size,
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the dog's size."""
        # This would update the dog's size in the configuration
        # and trigger size-related calculations
        await self.coordinator.async_refresh_dog(self._dog_id)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for the size select."""
        attrs = super().extra_state_attributes

        # Add size-specific information
        size_info = self._get_size_info(self.current_option)
        attrs.update(size_info)

        return attrs

    def _get_size_info(self, size: str | None) -> dict[str, Any]:
        """Get information about the selected size.

        Args:
            size: Selected size category

        Returns:
            Size information dictionary
        """
        size_data = {
            "toy": {
                "weight_range": "1-6kg",
                "exercise_needs": "low",
                "food_portion": "small",
            },
            "small": {
                "weight_range": "6-12kg",
                "exercise_needs": "moderate",
                "food_portion": "small",
            },
            "medium": {
                "weight_range": "12-27kg",
                "exercise_needs": "moderate",
                "food_portion": "medium",
            },
            "large": {
                "weight_range": "27-45kg",
                "exercise_needs": "high",
                "food_portion": "large",
            },
            "giant": {
                "weight_range": "45-90kg",
                "exercise_needs": "high",
                "food_portion": "extra_large",
            },
        }

        return size_data.get(size, {})


class PawControlPerformanceModeSelect(PawControlSelectBase):
    """Select entity for system performance mode."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the performance mode select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "performance_mode",
            options=PERFORMANCE_MODES,
            icon="mdi:speedometer",
            entity_category=EntityCategory.CONFIG,
            initial_option="balanced",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the performance mode."""
        # This would update system performance settings
        pass

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for performance mode."""
        attrs = super().extra_state_attributes

        mode_info = self._get_performance_mode_info(self.current_option)
        attrs.update(mode_info)

        return attrs

    def _get_performance_mode_info(self, mode: str | None) -> dict[str, Any]:
        """Get information about the selected performance mode.

        Args:
            mode: Selected performance mode

        Returns:
            Performance mode information
        """
        mode_data = {
            "minimal": {
                "description": "Minimal resource usage, longer update intervals",
                "update_interval": "5 minutes",
                "battery_impact": "minimal",
            },
            "balanced": {
                "description": "Balanced performance and resource usage",
                "update_interval": "2 minutes",
                "battery_impact": "moderate",
            },
            "full": {
                "description": "Maximum performance, frequent updates",
                "update_interval": "30 seconds",
                "battery_impact": "high",
            },
        }

        return mode_data.get(mode, {})


class PawControlNotificationPrioritySelect(PawControlSelectBase):
    """Select entity for default notification priority."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the notification priority select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "notification_priority",
            options=NOTIFICATION_PRIORITIES,
            icon="mdi:bell-ring",
            initial_option="normal",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the notification priority."""
        # This would update notification settings
        entry_data = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        notification_manager = entry_data.get("notifications")

        if notification_manager:
            # Update default priority settings
            pass


# Feeding selects
class PawControlFoodTypeSelect(PawControlSelectBase):
    """Select entity for primary food type."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the food type select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "food_type",
            options=FOOD_TYPES,
            icon="mdi:food",
            initial_option="dry_food",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the food type."""
        # This would update feeding calculations and nutritional data
        pass

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for food type."""
        attrs = super().extra_state_attributes

        food_info = self._get_food_type_info(self.current_option)
        attrs.update(food_info)

        return attrs

    def _get_food_type_info(self, food_type: str | None) -> dict[str, Any]:
        """Get information about the selected food type.

        Args:
            food_type: Selected food type

        Returns:
            Food type information
        """
        food_data = {
            "dry_food": {
                "calories_per_gram": 3.5,
                "moisture_content": "10%",
                "storage": "dry place",
                "shelf_life": "12-18 months",
            },
            "wet_food": {
                "calories_per_gram": 1.2,
                "moisture_content": "75%",
                "storage": "refrigerate after opening",
                "shelf_life": "2-3 days opened",
            },
            "barf": {
                "calories_per_gram": 2.0,
                "moisture_content": "70%",
                "storage": "frozen until use",
                "shelf_life": "3-6 months frozen",
            },
            "home_cooked": {
                "calories_per_gram": 1.8,
                "moisture_content": "65%",
                "storage": "refrigerate",
                "shelf_life": "2-3 days",
            },
            "mixed": {
                "calories_per_gram": 2.5,
                "moisture_content": "40%",
                "storage": "varies",
                "shelf_life": "varies",
            },
        }

        return food_data.get(food_type, {})


class PawControlFeedingScheduleSelect(PawControlSelectBase):
    """Select entity for feeding schedule type."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the feeding schedule select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_schedule",
            options=FEEDING_SCHEDULES,
            icon="mdi:calendar-clock",
            initial_option="flexible",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the feeding schedule."""
        # This would update feeding schedule enforcement
        pass


class PawControlDefaultMealTypeSelect(PawControlSelectBase):
    """Select entity for default meal type."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the default meal type select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "default_meal_type",
            options=MEAL_TYPES,
            icon="mdi:food-drumstick",
            initial_option="dinner",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the default meal type."""
        # This would update default feeding behavior
        pass


class PawControlFeedingModeSelect(PawControlSelectBase):
    """Select entity for feeding mode."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the feeding mode select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_mode",
            options=["manual", "scheduled", "automatic"],
            icon="mdi:cog",
            initial_option="manual",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the feeding mode."""
        # This would configure feeding automation level
        pass


# Walk selects
class PawControlWalkModeSelect(PawControlSelectBase):
    """Select entity for walk tracking mode."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the walk mode select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walk_mode",
            options=WALK_MODES,
            icon="mdi:walk",
            initial_option="automatic",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the walk mode."""
        # This would configure walk detection and tracking
        pass

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for walk mode."""
        attrs = super().extra_state_attributes

        mode_info = self._get_walk_mode_info(self.current_option)
        attrs.update(mode_info)

        return attrs

    def _get_walk_mode_info(self, mode: str | None) -> dict[str, Any]:
        """Get information about the selected walk mode.

        Args:
            mode: Selected walk mode

        Returns:
            Walk mode information
        """
        mode_data = {
            "automatic": {
                "description": "Automatically detect walk start/end",
                "gps_required": True,
                "accuracy": "high",
            },
            "manual": {
                "description": "Manually start and end walks",
                "gps_required": False,
                "accuracy": "user-dependent",
            },
            "hybrid": {
                "description": "Automatic detection with manual override",
                "gps_required": True,
                "accuracy": "very high",
            },
        }

        return mode_data.get(mode, {})


class PawControlWeatherPreferenceSelect(PawControlSelectBase):
    """Select entity for walk weather preference."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the weather preference select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weather_preference",
            options=WEATHER_CONDITIONS,
            icon="mdi:weather-partly-cloudy",
            initial_option="any",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the weather preference."""
        # This would update weather-based walk recommendations
        pass


class PawControlWalkIntensitySelect(PawControlSelectBase):
    """Select entity for preferred walk intensity."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the walk intensity select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walk_intensity",
            options=["relaxed", "moderate", "vigorous", "mixed"],
            icon="mdi:run",
            initial_option="moderate",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the walk intensity."""
        # This would update walk goal calculations
        pass


# GPS selects
class PawControlGPSSourceSelect(PawControlSelectBase):
    """Select entity for GPS data source."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the GPS source select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_source",
            options=GPS_SOURCES,
            icon="mdi:crosshairs-gps",
            entity_category=EntityCategory.CONFIG,
            initial_option="device_tracker",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the GPS source."""
        # This would configure GPS data source
        pass

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for GPS source."""
        attrs = super().extra_state_attributes

        source_info = self._get_gps_source_info(self.current_option)
        attrs.update(source_info)

        return attrs

    def _get_gps_source_info(self, source: str | None) -> dict[str, Any]:
        """Get information about the selected GPS source.

        Args:
            source: Selected GPS source

        Returns:
            GPS source information
        """
        source_data = {
            "manual": {
                "accuracy": "user-dependent",
                "update_frequency": "manual",
                "battery_usage": "none",
            },
            "device_tracker": {
                "accuracy": "device-dependent",
                "update_frequency": "automatic",
                "battery_usage": "low",
            },
            "person_entity": {
                "accuracy": "device-dependent",
                "update_frequency": "automatic",
                "battery_usage": "low",
            },
            "smartphone": {
                "accuracy": "high",
                "update_frequency": "real-time",
                "battery_usage": "medium",
            },
            "tractive": {
                "accuracy": "very high",
                "update_frequency": "real-time",
                "battery_usage": "device-dependent",
            },
            "webhook": {
                "accuracy": "source-dependent",
                "update_frequency": "real-time",
                "battery_usage": "none",
            },
            "mqtt": {
                "accuracy": "source-dependent",
                "update_frequency": "real-time",
                "battery_usage": "none",
            },
        }

        return source_data.get(source, {})


class PawControlTrackingModeSelect(PawControlSelectBase):
    """Select entity for GPS tracking mode."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the tracking mode select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "tracking_mode",
            options=TRACKING_MODES,
            icon="mdi:map-marker",
            initial_option="interval",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the tracking mode."""
        # This would configure GPS tracking behavior
        pass


class PawControlLocationAccuracySelect(PawControlSelectBase):
    """Select entity for location accuracy preference."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the location accuracy select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "location_accuracy",
            options=["low", "balanced", "high", "best"],
            icon="mdi:crosshairs",
            entity_category=EntityCategory.CONFIG,
            initial_option="balanced",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the location accuracy preference."""
        # This would configure GPS accuracy vs battery trade-off
        pass


# Health selects
class PawControlHealthStatusSelect(PawControlSelectBase):
    """Select entity for current health status."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the health status select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_status",
            options=HEALTH_STATUS_OPTIONS,
            icon="mdi:heart-pulse",
            initial_option="good",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current health status from data."""
        health_data = self._get_module_data("health")
        if health_data:
            return health_data.get("health_status", self._current_option)

        return self._current_option

    async def _async_set_select_option(self, option: str) -> None:
        """Set the health status."""
        # This would update health status and trigger alerts if needed
        pass


class PawControlActivityLevelSelect(PawControlSelectBase):
    """Select entity for current activity level."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the activity level select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "activity_level",
            options=ACTIVITY_LEVELS,
            icon="mdi:run",
            initial_option="normal",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current activity level from data."""
        health_data = self._get_module_data("health")
        if health_data:
            return health_data.get("activity_level", self._current_option)

        return self._current_option

    async def _async_set_select_option(self, option: str) -> None:
        """Set the activity level."""
        # This would update activity tracking and recommendations
        pass


class PawControlMoodSelect(PawControlSelectBase):
    """Select entity for current mood."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the mood select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "mood",
            options=MOOD_OPTIONS,
            icon="mdi:emoticon",
            initial_option="happy",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the mood."""
        # This would log mood data and adjust recommendations
        pass


class PawControlGroomingTypeSelect(PawControlSelectBase):
    """Select entity for selecting grooming type."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the grooming type select."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "grooming_type",
            options=GROOMING_TYPES,
            icon="mdi:content-cut",
            initial_option="brush",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the grooming type."""
        # This would be used for logging grooming activities
        pass

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for grooming type."""
        attrs = super().extra_state_attributes

        grooming_info = self._get_grooming_type_info(self.current_option)
        attrs.update(grooming_info)

        return attrs

    def _get_grooming_type_info(self, grooming_type: str | None) -> dict[str, Any]:
        """Get information about the selected grooming type.

        Args:
            grooming_type: Selected grooming type

        Returns:
            Grooming type information
        """
        grooming_data = {
            "bath": {
                "frequency": "4-6 weeks",
                "duration": "30-60 minutes",
                "difficulty": "medium",
            },
            "brush": {
                "frequency": "daily",
                "duration": "5-15 minutes",
                "difficulty": "easy",
            },
            "nails": {
                "frequency": "2-4 weeks",
                "duration": "10-20 minutes",
                "difficulty": "medium",
            },
            "teeth": {
                "frequency": "daily",
                "duration": "2-5 minutes",
                "difficulty": "easy",
            },
            "trim": {
                "frequency": "6-8 weeks",
                "duration": "60-90 minutes",
                "difficulty": "hard",
            },
            "full_grooming": {
                "frequency": "6-8 weeks",
                "duration": "120-180 minutes",
                "difficulty": "hard",
            },
        }

        return grooming_data.get(grooming_type, {})
