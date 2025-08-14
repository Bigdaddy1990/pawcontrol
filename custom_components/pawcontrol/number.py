"""Number platform for Paw Control integration.

This module provides configurable number entities for the Paw Control integration,
allowing users to set thresholds, portions, intervals, and other numeric values
for personalized dog care management.

The number entities follow Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations
- Robust error handling
- Persistent storage management
- Efficient value validation
- Comprehensive device classes
- Translation support
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .compat import EntityCategory, UnitOfLength, UnitOfMass, UnitOfTime
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DEFAULT_GROOMING_INTERVAL_DAYS,
    DEFAULT_MIN_WALK_DURATION_MIN,
    DEFAULT_WALK_THRESHOLD_HOURS,
    DOMAIN,
    ICONS,
    MAX_DOG_WEIGHT_KG,
    MIN_DOG_WEIGHT_KG,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
    MODULE_WALK,
)
from .entity import PawControlNumberEntity

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# No parallel updates to avoid storage conflicts
PARALLEL_UPDATES = 0

# Storage configuration
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_number_settings"

# Default values for number entities
DEFAULT_VALUES = {
    "walk_threshold_hours": DEFAULT_WALK_THRESHOLD_HOURS,
    "min_walk_duration": DEFAULT_MIN_WALK_DURATION_MIN,
    "breakfast_portion": 200,
    "lunch_portion": 150,
    "dinner_portion": 200,
    "snack_portion": 50,
    "grooming_interval": DEFAULT_GROOMING_INTERVAL_DAYS,
    "training_duration": 15,
    "play_duration": 20,
    "geofence_radius": 50,
    "medication_reminder_hours": 12,
    "weight_check_days": 7,
}

# Value ranges and constraints
VALUE_CONSTRAINTS = {
    "walk_threshold_hours": {"min": 1, "max": 48, "step": 0.5},
    "min_walk_duration": {"min": 5, "max": 240, "step": 5},
    "breakfast_portion": {"min": 10, "max": 2000, "step": 10},
    "lunch_portion": {"min": 10, "max": 2000, "step": 10},
    "dinner_portion": {"min": 10, "max": 2000, "step": 10},
    "snack_portion": {"min": 5, "max": 500, "step": 5},
    "target_weight": {"min": MIN_DOG_WEIGHT_KG, "max": MAX_DOG_WEIGHT_KG, "step": 0.1},
    "grooming_interval": {"min": 1, "max": 365, "step": 1},
    "training_duration": {"min": 5, "max": 120, "step": 5},
    "play_duration": {"min": 5, "max": 180, "step": 5},
    "geofence_radius": {"min": 5, "max": 2000, "step": 5},
    "medication_reminder_hours": {"min": 1, "max": 72, "step": 1},
    "weight_check_days": {"min": 1, "max": 90, "step": 1},
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control number entities from config entry.
    
    Creates number entities based on configured dogs and enabled modules.
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
        entities: list[PawControlNumberEntity] = []

        _LOGGER.debug("Setting up number entities for %d dogs", len(dogs))

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
                "Creating number entities for dog %s (%s) with modules: %s",
                dog_name,
                dog_id,
                list(dog_modules.keys())
            )

            # Walk module numbers
            if dog_modules.get(MODULE_WALK, True):
                entities.extend(_create_walk_numbers(coordinator, entry, dog_id, store, dog_stored))

            # Feeding module numbers
            if dog_modules.get(MODULE_FEEDING, True):
                entities.extend(_create_feeding_numbers(coordinator, entry, dog_id, store, dog_stored))

            # Health module numbers
            if dog_modules.get(MODULE_HEALTH, True):
                entities.extend(_create_health_numbers(coordinator, entry, dog_id, store, dog_stored))

            # Grooming module numbers
            if dog_modules.get(MODULE_GROOMING, False):
                entities.extend(_create_grooming_numbers(coordinator, entry, dog_id, store, dog_stored))

            # Training module numbers
            if dog_modules.get(MODULE_TRAINING, False):
                entities.extend(_create_training_numbers(coordinator, entry, dog_id, store, dog_stored))

            # GPS module numbers
            if dog_modules.get(MODULE_GPS, False):
                entities.extend(_create_gps_numbers(coordinator, entry, dog_id, store, dog_stored))

        _LOGGER.info("Created %d number entities", len(entities))
        
        if entities:
            async_add_entities(entities, update_before_add=True)

    except Exception as err:
        _LOGGER.error("Failed to setup number entities: %s", err)
        raise


async def _load_stored_values(store: Store) -> dict[str, dict[str, float]]:
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


def _create_walk_numbers(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, float],
) -> list[PawControlNumberEntity]:
    """Create walk-related number entities.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of walk number entities
    """
    return [
        WalkThresholdNumber(coordinator, entry, dog_id, store, dog_stored),
        MinWalkDurationNumber(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_feeding_numbers(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, float],
) -> list[PawControlNumberEntity]:
    """Create feeding-related number entities.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of feeding number entities
    """
    return [
        BreakfastPortionNumber(coordinator, entry, dog_id, store, dog_stored),
        LunchPortionNumber(coordinator, entry, dog_id, store, dog_stored),
        DinnerPortionNumber(coordinator, entry, dog_id, store, dog_stored),
        SnackPortionNumber(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_health_numbers(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, float],
) -> list[PawControlNumberEntity]:
    """Create health-related number entities.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of health number entities
    """
    return [
        TargetWeightNumber(coordinator, entry, dog_id, store, dog_stored),
        MedicationReminderNumber(coordinator, entry, dog_id, store, dog_stored),
        WeightCheckIntervalNumber(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_grooming_numbers(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, float],
) -> list[PawControlNumberEntity]:
    """Create grooming-related number entities.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of grooming number entities
    """
    return [
        GroomingIntervalNumber(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_training_numbers(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, float],
) -> list[PawControlNumberEntity]:
    """Create training-related number entities.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of training number entities
    """
    return [
        TrainingDurationNumber(coordinator, entry, dog_id, store, dog_stored),
        PlayDurationNumber(coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_gps_numbers(
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, float],
) -> list[PawControlNumberEntity]:
    """Create GPS-related number entities.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of GPS number entities
    """
    return [
        GeofenceRadiusNumber(coordinator, entry, dog_id, store, dog_stored),
    ]

# ==============================================================================
# BASE NUMBER ENTITY WITH STORAGE
# ==============================================================================

class PawControlNumberWithStorage(PawControlNumberEntity, NumberEntity):
    """Base class for number entities with persistent storage.
    
    Provides common functionality for number entities that need to persist
    their values across Home Assistant restarts. Values are stored per-dog
    and per-entity using Home Assistant's storage system.
    """

    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
        entity_key: str,
        translation_key: str,
        icon: str,
        min_value: float,
        max_value: float,
        step: float,
        unit: str | None = None,
        default_value: float | None = None,
        mode: NumberMode = NumberMode.BOX,
    ) -> None:
        """Initialize the number entity with storage.
        
        Args:
            coordinator: Data coordinator
            entry: Config entry
            dog_id: Dog identifier
            store: Storage instance
            stored_values: Pre-loaded stored values for this dog
            entity_key: Unique key for this entity
            translation_key: Translation key for localization
            icon: Material Design icon
            min_value: Minimum allowed value
            max_value: Maximum allowed value
            step: Step size for value changes
            unit: Unit of measurement
            default_value: Default value if not stored
            mode: Number input mode (box or slider)
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            entity_category=EntityCategory.CONFIG,
            min_value=min_value,
            max_value=max_value,
            step=step,
            unit_of_measurement=unit,
            icon=icon,
            mode=mode,
        )
        
        self._store = store
        self._stored_values = stored_values
        self._default_value = default_value or DEFAULT_VALUES.get(entity_key, min_value)
        
        # Load current value from storage or use default
        self._current_value = stored_values.get(entity_key, self._default_value)
        
        # Validate current value is within constraints
        self._current_value = self._validate_value(self._current_value)

    def _validate_value(self, value: float) -> float:
        """Validate and clamp value to acceptable range.
        
        Args:
            value: Value to validate
            
        Returns:
            Validated and clamped value
        """
        try:
            # Clamp to min/max range
            if self._attr_native_min_value is not None:
                value = max(value, self._attr_native_min_value)
            if self._attr_native_max_value is not None:
                value = min(value, self._attr_native_max_value)
            
            # Round to step precision
            if self._attr_native_step is not None:
                value = round(value / self._attr_native_step) * self._attr_native_step
            
            return value
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Invalid value %s for %s, using default %s",
                value,
                self.entity_id,
                self._default_value,
            )
            return self._default_value

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._current_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the value and persist it to storage.
        
        Args:
            value: New value to set
        """
        try:
            # Validate the new value
            validated_value = self._validate_value(value)
            
            if validated_value != value:
                _LOGGER.debug(
                    "Value %s for %s clamped to %s",
                    value,
                    self.entity_id,
                    validated_value,
                )
            
            self._current_value = validated_value

            # Update storage
            await self._save_value_to_storage(validated_value)
            
            # Apply value to coordinator if applicable
            await self._apply_value_to_coordinator(validated_value)

            _LOGGER.debug(
                "Set %s for %s to %s",
                self.entity_key,
                self.dog_name,
                validated_value,
            )
            
            # Update entity state
            self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error(
                "Failed to set value %s for %s: %s",
                value,
                self.entity_id,
                err,
            )

    async def _save_value_to_storage(self, value: float) -> None:
        """Save value to persistent storage.
        
        Args:
            value: Value to save
        """
        try:
            # Load current storage data
            all_stored = await self._store.async_load() or {}

            # Update value for this dog and entity
            if self.dog_id not in all_stored:
                all_stored[self.dog_id] = {}
            all_stored[self.dog_id][self.entity_key] = value

            # Save to storage
            await self._store.async_save(all_stored)
            
        except Exception as err:
            _LOGGER.error("Failed to save value to storage: %s", err)

    async def _apply_value_to_coordinator(self, value: float) -> None:
        """Apply value to coordinator data if applicable.
        
        This method can be overridden by subclasses to immediately
        apply the new value to coordinator data for instant effects.
        
        Args:
            value: Value to apply
        """
        # Default implementation does nothing
        # Subclasses can override to update coordinator data
        pass

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        try:
            attributes = super().extra_state_attributes or {}
            attributes.update({
                "default_value": self._default_value,
                "is_default": self._current_value == self._default_value,
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting extra attributes for %s: %s", self.entity_id, err)
            return super().extra_state_attributes

# ==============================================================================
# WALK NUMBER ENTITIES
# ==============================================================================

class WalkThresholdNumber(PawControlNumberWithStorage):
    """Number entity for configuring walk threshold in hours.
    
    Determines when a dog is considered to need a walk based on time
    since the last walk. Used by binary sensors and notifications.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the walk threshold number entity."""
        constraints = VALUE_CONSTRAINTS["walk_threshold_hours"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="walk_threshold_hours",
            translation_key="walk_threshold",
            icon=ICONS.get("walk", "mdi:timer-sand"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit="h",
            default_value=DEFAULT_VALUES["walk_threshold_hours"],
        )

    async def _apply_value_to_coordinator(self, value: float) -> None:
        """Apply walk threshold to coordinator logic."""
        try:
            # Update coordinator configuration for immediate effect
            # This would update walk need calculations
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply walk threshold to coordinator: %s", err)


class MinWalkDurationNumber(PawControlNumberWithStorage):
    """Number entity for configuring minimum walk duration in minutes.
    
    Determines the minimum duration for a walk to be considered complete
    and count towards daily statistics.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the minimum walk duration number entity."""
        constraints = VALUE_CONSTRAINTS["min_walk_duration"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="min_walk_duration",
            translation_key="min_walk_duration",
            icon=ICONS.get("walk", "mdi:timer"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit=UnitOfTime.MINUTES,
            default_value=DEFAULT_VALUES["min_walk_duration"],
        )

# ==============================================================================
# FEEDING NUMBER ENTITIES
# ==============================================================================

class BreakfastPortionNumber(PawControlNumberWithStorage):
    """Number entity for configuring default breakfast portion size."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the breakfast portion number entity."""
        constraints = VALUE_CONSTRAINTS["breakfast_portion"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="breakfast_portion",
            translation_key="breakfast_portion",
            icon=ICONS.get("feeding", "mdi:coffee"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit=UnitOfMass.GRAMS,
            default_value=DEFAULT_VALUES["breakfast_portion"],
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional feeding information."""
        try:
            attributes = super().extra_state_attributes or {}
            feeding_data = self.dog_data.get("feeding", {})
            feedings_today = feeding_data.get("feedings_today", {})
            
            attributes.update({
                "meal_type": "breakfast",
                "feedings_today": feedings_today.get("breakfast", 0),
                "last_feeding": feeding_data.get("last_feeding"),
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting breakfast attributes: %s", err)
            return super().extra_state_attributes


class LunchPortionNumber(PawControlNumberWithStorage):
    """Number entity for configuring default lunch portion size."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the lunch portion number entity."""
        constraints = VALUE_CONSTRAINTS["lunch_portion"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="lunch_portion",
            translation_key="lunch_portion",
            icon=ICONS.get("feeding", "mdi:silverware-fork-knife"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit=UnitOfMass.GRAMS,
            default_value=DEFAULT_VALUES["lunch_portion"],
        )


class DinnerPortionNumber(PawControlNumberWithStorage):
    """Number entity for configuring default dinner portion size."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the dinner portion number entity."""
        constraints = VALUE_CONSTRAINTS["dinner_portion"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="dinner_portion",
            translation_key="dinner_portion",
            icon=ICONS.get("feeding", "mdi:food-turkey"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit=UnitOfMass.GRAMS,
            default_value=DEFAULT_VALUES["dinner_portion"],
        )


class SnackPortionNumber(PawControlNumberWithStorage):
    """Number entity for configuring default snack portion size."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the snack portion number entity."""
        constraints = VALUE_CONSTRAINTS["snack_portion"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="snack_portion",
            translation_key="snack_portion",
            icon=ICONS.get("feeding", "mdi:food-apple"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit=UnitOfMass.GRAMS,
            default_value=DEFAULT_VALUES["snack_portion"],
        )

# ==============================================================================
# HEALTH NUMBER ENTITIES
# ==============================================================================

class TargetWeightNumber(PawControlNumberWithStorage):
    """Number entity for configuring target weight for the dog.
    
    Used for weight trend analysis and health monitoring.
    Automatically initializes with the dog's current weight if available.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the target weight number entity."""
        # Get initial weight from dog data
        try:
            dog_data = coordinator.get_dog_data(dog_id)
            current_weight = dog_data.get("health", {}).get("weight_kg", 20.0)
            if current_weight <= 0:
                current_weight = 20.0  # Fallback default
        except Exception:
            current_weight = 20.0  # Fallback default

        constraints = VALUE_CONSTRAINTS["target_weight"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="target_weight",
            translation_key="target_weight",
            icon=ICONS.get("health", "mdi:weight-kilogram"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit=UnitOfMass.KILOGRAMS,
            default_value=current_weight,
        )

    async def _apply_value_to_coordinator(self, value: float) -> None:
        """Apply target weight to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                health_data = dog_data.setdefault("health", {})
                health_data["target_weight_kg"] = value
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply target weight to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return weight-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})
            
            current_weight = health_data.get("weight_kg", 0)
            if current_weight > 0 and self._current_value:
                weight_diff = current_weight - self._current_value
                attributes.update({
                    "current_weight_kg": current_weight,
                    "weight_difference_kg": round(weight_diff, 1),
                    "at_target": abs(weight_diff) <= 0.5,
                })
            
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting weight attributes: %s", err)
            return super().extra_state_attributes


class MedicationReminderNumber(PawControlNumberWithStorage):
    """Number entity for configuring medication reminder interval in hours."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the medication reminder number entity."""
        constraints = VALUE_CONSTRAINTS["medication_reminder_hours"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="medication_reminder_hours",
            translation_key="medication_reminder_interval",
            icon=ICONS.get("medication", "mdi:pill"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit="h",
            default_value=DEFAULT_VALUES["medication_reminder_hours"],
        )


class WeightCheckIntervalNumber(PawControlNumberWithStorage):
    """Number entity for configuring weight check reminder interval in days."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the weight check interval number entity."""
        constraints = VALUE_CONSTRAINTS["weight_check_days"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="weight_check_days",
            translation_key="weight_check_interval",
            icon=ICONS.get("health", "mdi:scale-bathroom"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit="d",
            default_value=DEFAULT_VALUES["weight_check_days"],
        )

# ==============================================================================
# GROOMING NUMBER ENTITIES
# ==============================================================================

class GroomingIntervalNumber(PawControlNumberWithStorage):
    """Number entity for configuring grooming interval in days.
    
    Determines when grooming reminders are triggered and when the
    dog is considered to need grooming.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the grooming interval number entity."""
        # Get current interval from coordinator data if available
        try:
            dog_data = coordinator.get_dog_data(dog_id)
            current_interval = dog_data.get("grooming", {}).get(
                "grooming_interval_days", DEFAULT_GROOMING_INTERVAL_DAYS
            )
        except Exception:
            current_interval = DEFAULT_GROOMING_INTERVAL_DAYS

        constraints = VALUE_CONSTRAINTS["grooming_interval"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="grooming_interval",
            translation_key="grooming_interval",
            icon=ICONS.get("grooming", "mdi:calendar-repeat"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit="d",
            default_value=current_interval,
        )

    async def _apply_value_to_coordinator(self, value: float) -> None:
        """Apply grooming interval to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                grooming_data = dog_data.setdefault("grooming", {})
                grooming_data["grooming_interval_days"] = int(value)
                # Trigger recalculation of grooming needs
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply grooming interval to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return grooming-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            grooming_data = self.dog_data.get("grooming", {})
            
            attributes.update({
                "last_grooming": grooming_data.get("last_grooming"),
                "needs_grooming": grooming_data.get("needs_grooming", False),
                "grooming_type": grooming_data.get("grooming_type"),
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting grooming attributes: %s", err)
            return super().extra_state_attributes

# ==============================================================================
# TRAINING NUMBER ENTITIES
# ==============================================================================

class TrainingDurationNumber(PawControlNumberWithStorage):
    """Number entity for configuring default training session duration."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the training duration number entity."""
        constraints = VALUE_CONSTRAINTS["training_duration"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="training_duration",
            translation_key="training_duration",
            icon=ICONS.get("training", "mdi:timer-outline"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit=UnitOfTime.MINUTES,
            default_value=DEFAULT_VALUES["training_duration"],
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return training-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            training_data = self.dog_data.get("training", {})
            
            attributes.update({
                "last_training": training_data.get("last_training"),
                "sessions_today": training_data.get("training_sessions_today", 0),
                "last_topic": training_data.get("last_topic"),
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting training attributes: %s", err)
            return super().extra_state_attributes


class PlayDurationNumber(PawControlNumberWithStorage):
    """Number entity for configuring default play session duration."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the play duration number entity."""
        constraints = VALUE_CONSTRAINTS["play_duration"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="play_duration",
            translation_key="play_duration",
            icon=ICONS.get("activity", "mdi:tennis-ball"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit=UnitOfTime.MINUTES,
            default_value=DEFAULT_VALUES["play_duration"],
        )

# ==============================================================================
# GPS NUMBER ENTITIES
# ==============================================================================

class GeofenceRadiusNumber(PawControlNumberWithStorage):
    """Number entity for configuring geofence radius in meters.
    
    Determines the size of the safe zone around the home location
    for GPS tracking and alerts.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, float],
    ) -> None:
        """Initialize the geofence radius number entity."""
        constraints = VALUE_CONSTRAINTS["geofence_radius"]
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="geofence_radius",
            translation_key="geofence_radius",
            icon=ICONS.get("gps", "mdi:map-marker-radius"),
            min_value=constraints["min"],
            max_value=constraints["max"],
            step=constraints["step"],
            unit=UnitOfLength.METERS,
            default_value=DEFAULT_VALUES["geofence_radius"],
            mode=NumberMode.SLIDER,
        )

    async def _apply_value_to_coordinator(self, value: float) -> None:
        """Apply geofence radius to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                location_data = dog_data.setdefault("location", {})
                location_data["radius_m"] = int(value)
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply geofence radius to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return geofence-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            location_data = self.dog_data.get("location", {})
            
            attributes.update({
                "home_lat": location_data.get("home_lat"),
                "home_lon": location_data.get("home_lon"),
                "is_home": location_data.get("is_home", True),
                "distance_from_home": location_data.get("distance_from_home", 0),
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting geofence attributes: %s", err)
            return super().extra_state_attributes
