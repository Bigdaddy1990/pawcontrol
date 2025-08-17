"""Select platform for Paw Control integration.

This module provides dropdown selection entities for the Paw Control integration,
allowing users to choose from predefined options for various dog care settings
like food types, grooming preferences, training topics, and system configurations.

The select entities follow Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations
- Robust error handling
- Persistent storage management
- Efficient option validation
- Comprehensive categorization
- Translation support
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .compat import DeviceInfo, EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    FEEDING_TYPES,
    FOOD_BARF,
    FOOD_DRY,
    FOOD_TREAT,
    FOOD_WET,
    GROOMING_BATH,
    GROOMING_BRUSH,
    GROOMING_EARS,
    GROOMING_EYES,
    GROOMING_NAILS,
    GROOMING_TEETH,
    GROOMING_TRIM,
    GROOMING_TYPES,
    ICONS,
    INTENSITY_HIGH,
    INTENSITY_LOW,
    INTENSITY_MEDIUM,
    INTENSITY_TYPES,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
)
from .entity import PawControlSelectEntity

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# No parallel updates to avoid storage conflicts
PARALLEL_UPDATES = 0

# Storage configuration
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_select_settings"
# Special key for system-wide values in storage
SYSTEM_STORAGE_KEY = "system"

# Option lists for various select entities
FOOD_TYPE_OPTIONS = [FOOD_DRY, FOOD_WET, FOOD_BARF, FOOD_TREAT]
INTENSITY_OPTIONS = [INTENSITY_LOW, INTENSITY_MEDIUM, INTENSITY_HIGH]
GROOMING_TYPE_OPTIONS = [
    GROOMING_BRUSH,
    GROOMING_BATH,
    GROOMING_TRIM,
    GROOMING_NAILS,
    GROOMING_EARS,
    GROOMING_TEETH,
    GROOMING_EYES,
]
TRAINING_TOPIC_OPTIONS = [
    "Basic Commands",
    "Leash Training",
    "Tricks",
    "Agility",
    "Socialization",
    "House Training",
    "Behavior Correction",
    "Recall Training",
    "Create Training",
    "Impulse Control",
]
MEAL_SCHEDULE_OPTIONS = ["1 meal", "2 meals", "3 meals", "Free feeding"]
EXPORT_FORMAT_OPTIONS = ["csv", "json", "pdf", "xlsx"]
DOG_SIZE_OPTIONS = ["small", "medium", "large", "xlarge"]
NOTIFICATION_PRIORITY_OPTIONS = ["low", "normal", "high", "critical"]

# Default values for select entities
DEFAULT_VALUES = {
    "default_food_type": FOOD_DRY,
    "meal_schedule": "2 meals",
    "default_grooming_type": GROOMING_BRUSH,
    "training_topic": "Basic Commands",
    "training_intensity": INTENSITY_MEDIUM,
    "activity_level_setting": INTENSITY_MEDIUM,
    "export_format": "csv",
    "dog_size": "medium",
    "notification_priority": "normal",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control select entities from config entry.

    Creates select entities based on configured dogs and enabled modules.
    Only creates entities for modules that are enabled for each dog.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        async_add_entities: Callback to add entities

    Raises:
        PlatformNotReady: If coordinator hasn't completed initial data refresh
    """
    try:
        runtime_data = entry.runtime_data
        coordinator: PawControlCoordinator = runtime_data.coordinator

        # Ensure coordinator has completed initial refresh
        if not coordinator.last_update_success:
            _LOGGER.warning("Coordinator not ready, attempting refresh")
            await coordinator.async_refresh()
            if not coordinator.last_update_success:
                raise PlatformNotReady

        # Initialize persistent storage
        store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        stored_values = await _load_stored_values(store)

        dogs = entry.options.get(CONF_DOGS, [])
        entities: list[SelectEntity] = []

        _LOGGER.debug("Setting up select entities for %d dogs", len(dogs))

        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            dog_name = dog.get(CONF_DOG_NAME, dog_id)

            if not dog_id:
                _LOGGER.warning("Skipping dog with missing ID: %s", dog)
                continue

            # Get enabled modules for this dog
            dog_modules = dog.get(CONF_DOG_MODULES, {})
            dog_stored = stored_values.get(dog_id, {})

            _LOGGER.debug(
                "Creating select entities for dog %s (%s) with modules: %s",
                dog_name,
                dog_id,
                list(dog_modules.keys()),
            )

            # Core select entities (always available)
            entities.extend(
                _create_core_selects(coordinator, entry, dog_id, store, dog_stored)
            )

            # Feeding module selects
            if dog_modules.get(MODULE_FEEDING, True):
                entities.extend(
                    _create_feeding_selects(
                        coordinator, entry, dog_id, store, dog_stored
                    )
                )

            # Grooming module selects
            if dog_modules.get(MODULE_GROOMING, False):
                entities.extend(
                    _create_grooming_selects(
                        coordinator, entry, dog_id, store, dog_stored
                    )
                )

            # Training module selects
            if dog_modules.get(MODULE_TRAINING, False):
                entities.extend(
                    _create_training_selects(
                        coordinator, entry, dog_id, store, dog_stored
                    )
                )

            # Health module selects
            if dog_modules.get(MODULE_HEALTH, True):
                entities.extend(
                    _create_health_selects(
                        coordinator, entry, dog_id, store, dog_stored
                    )
                )

        # System-wide select entities
        system_stored = stored_values.get(SYSTEM_STORAGE_KEY, {})
        entities.extend(
            _create_system_selects(hass, coordinator, entry, store, system_stored)
        )

        _LOGGER.info("Created %d select entities", len(entities))

        if entities:
            async_add_entities(entities, update_before_add=True)

    except Exception as err:
        _LOGGER.error("Failed to setup select entities: %s", err)
        raise


async def _load_stored_values(store: Store) -> dict[str, dict[str, str]]:
    """Load stored values from persistent storage.

    Args:
        store: Storage instance

    Returns:
        Dictionary of stored values organized by dog_id and entity_key
    """
    try:
        stored_values = await store.async_load()
        if stored_values is None:
            _LOGGER.debug("No stored values found, using defaults")
            return {}

        # Validate stored values structure
        if not isinstance(stored_values, dict):
            _LOGGER.warning("Invalid stored values structure, resetting")
            return {}

        _LOGGER.debug("Loaded stored values for %d dogs", len(stored_values))
        return stored_values

    except Exception as err:
        _LOGGER.error("Failed to load stored values: %s", err)
        return {}


def _create_core_selects(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlSelectEntity]:
    """Create core select entities available for all dogs.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of core select entities
    """
    return [
        ActivityLevelSelect(coordinator, entry, dog_id, store, dog_stored),
        DogSizeSelect(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_feeding_selects(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlSelectEntity]:
    """Create feeding-related select entities.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of feeding select entities
    """
    return [
        DefaultFoodTypeSelect(coordinator, entry, dog_id, store, dog_stored),
        MealScheduleSelect(coordinator, entry, dog_id, store, dog_stored),
        FeedingLocationSelect(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_grooming_selects(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlSelectEntity]:
    """Create grooming-related select entities.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of grooming select entities
    """
    return [
        DefaultGroomingTypeSelect(coordinator, entry, dog_id, store, dog_stored),
        GroomingLocationSelect(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_training_selects(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlSelectEntity]:
    """Create training-related select entities.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of training select entities
    """
    return [
        TrainingTopicSelect(coordinator, entry, dog_id, store, dog_stored),
        TrainingIntensitySelect(coordinator, entry, dog_id, store, dog_stored),
        TrainingLocationSelect(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_health_selects(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlSelectEntity]:
    """Create health-related select entities.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of health select entities
    """
    return [
        VeterinarianSelect(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_system_selects(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    store: Store,
    stored_values: dict[str, str],
) -> list[SelectEntity]:
    """Create system-wide select entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        store: Storage instance

    Returns:
        List of system select entities
    """
    return [
        ExportFormatSelect(hass, coordinator, entry, store, stored_values),
        NotificationPrioritySelect(hass, coordinator, entry, store, stored_values),
    ]


# ==============================================================================
# BASE SELECT ENTITY WITH STORAGE
# ==============================================================================


class PawControlSelectWithStorage(PawControlSelectEntity):
    """Base class for select entities with persistent storage.

    Provides common functionality for select entities that need to persist
    their values across Home Assistant restarts. Values are stored per-dog
    and per-entity using Home Assistant's storage system.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
        entity_key: str,
        translation_key: str,
        options: list[str],
        icon: str,
        default_option: str | None = None,
    ) -> None:
        """Initialize the select entity with storage.

        Args:
            coordinator: Data coordinator
            entry: Config entry
            dog_id: Dog identifier
            store: Storage instance
            stored_values: Pre-loaded stored values for this dog
            entity_key: Unique key for this entity
            translation_key: Translation key for localization
            options: List of available options
            icon: Material Design icon
            default_option: Default option if not stored
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            options=options,
            translation_key=translation_key,
            entity_category=EntityCategory.CONFIG,
            icon=icon,
        )

        self._store = store
        self._stored_values = stored_values
        self._default_option = default_option or DEFAULT_VALUES.get(
            entity_key, options[0] if options else None
        )

        # Load current option from storage or use default
        stored_option = stored_values.get(entity_key, self._default_option)
        self._current_option = self._validate_option(stored_option)

    def _validate_option(self, option: str | None) -> str | None:
        """Validate that option is in available options list.

        Args:
            option: Option to validate

        Returns:
            Validated option or default if invalid
        """
        if option is None:
            return self._default_option

        if option not in self._attr_options:
            _LOGGER.warning(
                "Invalid option %s for %s, using default %s",
                option,
                self.entity_id,
                self._default_option,
            )
            return self._default_option

        return option

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Update the selected option and persist it to storage.

        Args:
            option: New option to select
        """
        try:
            # Validate the new option
            validated_option = self._validate_option(option)

            if validated_option != option:
                _LOGGER.warning(
                    "Option %s for %s is invalid, using %s",
                    option,
                    self.entity_id,
                    validated_option,
                )

            self._current_option = validated_option

            # Update storage
            await self._save_option_to_storage(validated_option)

            # Apply option to coordinator if applicable
            await self._apply_option_to_coordinator(validated_option)

            _LOGGER.debug(
                "Set %s for %s to %s",
                self.entity_key,
                self.dog_name,
                validated_option,
            )

            # Update entity state
            self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error(
                "Failed to set option %s for %s: %s",
                option,
                self.entity_id,
                err,
            )

    async def _save_option_to_storage(self, option: str) -> None:
        """Save option to persistent storage.

        Args:
            option: Option to save
        """
        try:
            # Load current storage data
            all_stored = await self._store.async_load() or {}

            # Update option for this dog and entity
            if self.dog_id not in all_stored:
                all_stored[self.dog_id] = {}
            all_stored[self.dog_id][self.entity_key] = option

            # Save to storage
            await self._store.async_save(all_stored)

        except Exception as err:
            _LOGGER.error("Failed to save option to storage: %s", err)

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply option to coordinator data if applicable.

        This method can be overridden by subclasses to immediately
        apply the new option to coordinator data for instant effects.

        Args:
            option: Option to apply
        """
        # Default implementation does nothing
        # Subclasses can override to update coordinator data
        pass

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        try:
            attributes = super().extra_state_attributes or {}
            attributes.update(
                {
                    "default_option": self._default_option,
                    "is_default": self._current_option == self._default_option,
                    "available_options": len(self._attr_options),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug(
                "Error getting extra attributes for %s: %s", self.entity_id, err
            )
            return super().extra_state_attributes


# ==============================================================================
# CORE SELECT ENTITIES
# ==============================================================================


class ActivityLevelSelect(PawControlSelectWithStorage):
    """Select entity for configuring dog's activity level.

    Determines the overall activity expectations and calculations
    for calorie burning, exercise needs, and training intensity.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the activity level select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="activity_level_setting",
            translation_key="activity_level_setting",
            options=INTENSITY_OPTIONS,
            icon=ICONS.get("activity", "mdi:run"),
            default_option=DEFAULT_VALUES["activity_level_setting"],
        )

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply activity level to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                activity_data = dog_data.setdefault("activity", {})
                activity_data["activity_level"] = option
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply activity level to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return activity-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            activity_data = self.dog_data.get("activity", {})

            # Add translated display value
            attributes.update(
                {
                    "display_value": INTENSITY_TYPES.get(
                        self._current_option, self._current_option
                    ),
                    "calories_burned_today": activity_data.get(
                        "calories_burned_today", 0
                    ),
                    "play_duration_today": activity_data.get(
                        "play_duration_today_min", 0
                    ),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting activity attributes: %s", err)
            return super().extra_state_attributes


class DogSizeSelect(PawControlSelectWithStorage):
    """Select entity for configuring dog's size category.

    Used for calculating proper portion sizes, exercise needs,
    and health parameter ranges.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the dog size select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="dog_size",
            translation_key="dog_size",
            options=DOG_SIZE_OPTIONS,
            icon=ICONS.get("health", "mdi:dog"),
            default_option=DEFAULT_VALUES["dog_size"],
        )

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply dog size to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                info_data = dog_data.setdefault("info", {})
                info_data["size"] = option
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply dog size to coordinator: %s", err)


# ==============================================================================
# FEEDING SELECT ENTITIES
# ==============================================================================


class DefaultFoodTypeSelect(PawControlSelectWithStorage):
    """Select entity for configuring default food type.

    Sets the default food type used in feeding buttons and calculations.
    Choices include dry, wet, BARF, and treats.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the default food type select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="default_food_type",
            translation_key="default_food_type",
            options=FOOD_TYPE_OPTIONS,
            icon=ICONS.get("feeding", "mdi:food"),
            default_option=DEFAULT_VALUES["default_food_type"],
        )

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply food type to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                feeding_data = dog_data.setdefault("feeding", {})
                feeding_data["default_food_type"] = option
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply food type to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return feeding-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            feeding_data = self.dog_data.get("feeding", {})

            # Add translated display value
            attributes.update(
                {
                    "display_value": FEEDING_TYPES.get(
                        self._current_option, self._current_option
                    ),
                    "last_feeding": feeding_data.get("last_feeding"),
                    "feedings_today": sum(
                        feeding_data.get("feedings_today", {}).values()
                    ),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting food type attributes: %s", err)
            return super().extra_state_attributes


class MealScheduleSelect(PawControlSelectWithStorage):
    """Select entity for configuring meal schedule.

    Determines how many meals per day and feeding expectations.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the meal schedule select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="meal_schedule",
            translation_key="meal_schedule",
            options=MEAL_SCHEDULE_OPTIONS,
            icon=ICONS.get("feeding", "mdi:clock-outline"),
            default_option=DEFAULT_VALUES["meal_schedule"],
        )

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply meal schedule to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                feeding_data = dog_data.setdefault("feeding", {})
                feeding_data["meal_schedule"] = option
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply meal schedule to coordinator: %s", err)


class FeedingLocationSelect(PawControlSelectWithStorage):
    """Select entity for configuring preferred feeding location."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the feeding location select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="feeding_location",
            translation_key="feeding_location",
            options=["Kitchen", "Living Room", "Outdoor", "Utility Room", "Other"],
            icon=ICONS.get("feeding", "mdi:home-map-marker"),
            default_option="Kitchen",
        )


# ==============================================================================
# GROOMING SELECT ENTITIES
# ==============================================================================


class DefaultGroomingTypeSelect(PawControlSelectWithStorage):
    """Select entity for configuring default grooming type.

    Sets the default grooming activity used in buttons and reminders.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the default grooming type select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="default_grooming_type",
            translation_key="default_grooming_type",
            options=GROOMING_TYPE_OPTIONS,
            icon=ICONS.get("grooming", "mdi:content-cut"),
            default_option=DEFAULT_VALUES["default_grooming_type"],
        )

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply grooming type to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                grooming_data = dog_data.setdefault("grooming", {})
                grooming_data["grooming_type"] = option
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply grooming type to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return grooming-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            grooming_data = self.dog_data.get("grooming", {})

            # Add translated display value
            attributes.update(
                {
                    "display_value": GROOMING_TYPES.get(
                        self._current_option, self._current_option
                    ),
                    "last_grooming": grooming_data.get("last_grooming"),
                    "needs_grooming": grooming_data.get("needs_grooming", False),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting grooming type attributes: %s", err)
            return super().extra_state_attributes


class GroomingLocationSelect(PawControlSelectWithStorage):
    """Select entity for configuring preferred grooming location."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the grooming location select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="grooming_location",
            translation_key="grooming_location",
            options=[
                "Bathroom",
                "Outdoor",
                "Professional Groomer",
                "Utility Room",
                "Other",
            ],
            icon=ICONS.get("grooming", "mdi:map-marker"),
            default_option="Bathroom",
        )


# ==============================================================================
# TRAINING SELECT ENTITIES
# ==============================================================================


class TrainingTopicSelect(PawControlSelectWithStorage):
    """Select entity for configuring training topic focus.

    Sets the current training focus area for sessions and progress tracking.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the training topic select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="training_topic",
            translation_key="training_topic",
            options=TRAINING_TOPIC_OPTIONS,
            icon=ICONS.get("training", "mdi:school"),
            default_option=DEFAULT_VALUES["training_topic"],
        )

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply training topic to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                training_data = dog_data.setdefault("training", {})
                training_data["current_topic"] = option
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply training topic to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return training-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            training_data = self.dog_data.get("training", {})

            attributes.update(
                {
                    "last_training": training_data.get("last_training"),
                    "sessions_today": training_data.get("training_sessions_today", 0),
                    "last_topic": training_data.get("last_topic"),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting training topic attributes: %s", err)
            return super().extra_state_attributes


class TrainingIntensitySelect(PawControlSelectWithStorage):
    """Select entity for configuring training intensity level."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the training intensity select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="training_intensity",
            translation_key="training_intensity",
            options=INTENSITY_OPTIONS,
            icon=ICONS.get("activity", "mdi:speedometer"),
            default_option=DEFAULT_VALUES["training_intensity"],
        )

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply training intensity to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                training_data = dog_data.setdefault("training", {})
                training_data["intensity"] = option
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply training intensity to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return intensity-related information."""
        try:
            attributes = super().extra_state_attributes or {}

            # Add translated display value
            attributes.update(
                {
                    "display_value": INTENSITY_TYPES.get(
                        self._current_option, self._current_option
                    ),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting training intensity attributes: %s", err)
            return super().extra_state_attributes


class TrainingLocationSelect(PawControlSelectWithStorage):
    """Select entity for configuring preferred training location."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the training location select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="training_location",
            translation_key="training_location",
            options=["Indoor", "Backyard", "Park", "Dog School", "Beach", "Other"],
            icon=ICONS.get("training", "mdi:map-marker"),
            default_option="Indoor",
        )


# ==============================================================================
# HEALTH SELECT ENTITIES
# ==============================================================================


class VeterinarianSelect(PawControlSelectWithStorage):
    """Select entity for configuring preferred veterinarian."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the veterinarian select entity."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="veterinarian",
            translation_key="veterinarian",
            options=["Dr. Smith", "Dr. Johnson", "Dr. Brown", "Emergency Vet", "Other"],
            icon=ICONS.get("health", "mdi:stethoscope"),
            default_option="Dr. Smith",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return veterinarian-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})

            attributes.update(
                {
                    "last_vet_visit": health_data.get("last_vet_visit"),
                    "next_appointment": health_data.get("next_vet_appointment"),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting veterinarian attributes: %s", err)
            return super().extra_state_attributes


# ==============================================================================
# SYSTEM SELECT ENTITIES
# ==============================================================================


class PawControlSystemSelectWithStorage(SelectEntity):
    """Base class for system-wide select entities with storage."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        store: Store,
        stored_values: dict[str, str],
        entity_key: str,
        translation_key: str,
        options: list[str],
        icon: str,
        default_option: str,
    ) -> None:
        """Initialize the system-wide select entity."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._store = store
        self.entity_key = entity_key
        self._attr_unique_id = f"{entry.entry_id}_global_{entity_key}"
        self._attr_translation_key = translation_key
        self._attr_options = options
        self._attr_icon = icon
        self._default_option = default_option

        stored_option = stored_values.get(entity_key)
        self._current_option = (
            stored_option if stored_option in self._attr_options else default_option
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=f"/config/integrations/integration/{DOMAIN}",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Update the selected option and persist it."""
        try:
            if option not in self._attr_options:
                _LOGGER.warning("Invalid option %s for %s", option, self.entity_id)
                return

            self._current_option = option
            await self._save_option_to_storage(option)
            await self._apply_option_to_coordinator(option)
            self.async_write_ha_state()
        except Exception as err:  # pragma: no cover - unexpected errors
            _LOGGER.error(
                "Failed to set option %s for %s: %s", option, self.entity_id, err
            )

    async def _save_option_to_storage(self, option: str) -> None:
        """Save option to persistent storage."""
        try:
            all_stored = await self._store.async_load() or {}
            system_stored = all_stored.setdefault(SYSTEM_STORAGE_KEY, {})
            system_stored[self.entity_key] = option
            await self._store.async_save(all_stored)
        except Exception as err:
            _LOGGER.error("Failed to save option to storage: %s", err)

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply option to coordinator if needed."""


class ExportFormatSelect(PawControlSystemSelectWithStorage):
    """Select entity for configuring data export format.

    System-wide setting that determines the format used when exporting
    dog data and reports.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the export format select entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            store=store,
            stored_values=stored_values,
            entity_key="export_format",
            translation_key="export_format",
            options=EXPORT_FORMAT_OPTIONS,
            icon=ICONS.get("export", "mdi:file-export"),
            default_option=DEFAULT_VALUES["export_format"],
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Export Format"

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Log export format changes."""
        _LOGGER.info("Export format set to %s", option)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return export-related information."""
        try:
            return {
                "supported_formats": self._attr_options,
                "default_format": DEFAULT_VALUES["export_format"],
            }
        except Exception as err:
            _LOGGER.debug("Error getting export format attributes: %s", err)
            return {}


class NotificationPrioritySelect(PawControlSystemSelectWithStorage):
    """Select entity for configuring default notification priority."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the notification priority select entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            store=store,
            stored_values=stored_values,
            entity_key="notification_priority",
            translation_key="notification_priority",
            options=NOTIFICATION_PRIORITY_OPTIONS,
            icon=ICONS.get("notifications", "mdi:bell-ring"),
            default_option=DEFAULT_VALUES["notification_priority"],
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Notification Priority"

    async def _apply_option_to_coordinator(self, option: str) -> None:
        """Apply priority to coordinator data."""
        self.coordinator.notification_priority = option
        _LOGGER.info("Notification priority set to %s", option)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return notification-related information."""
        try:
            return {
                "supported_priorities": self._attr_options,
                "default_priority": DEFAULT_VALUES["notification_priority"],
                "current_setting": self.current_option,
            }
        except Exception as err:
            _LOGGER.debug("Error getting notification priority attributes: %s", err)
            return {}
