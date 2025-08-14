"""Number platform for Paw Control integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .compat import EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOGS,
    DEFAULT_GROOMING_INTERVAL_DAYS,
    DEFAULT_MIN_WALK_DURATION_MIN,
    DEFAULT_WALK_THRESHOLD_HOURS,
    DOMAIN,
    MAX_DOG_WEIGHT_KG,
    MIN_DOG_WEIGHT_KG,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .entity import PawControlNumberEntity

PARALLEL_UPDATES = 0
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_number_settings"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control number entities."""
    coordinator: PawControlCoordinator = entry.runtime_data.coordinator

    if not coordinator.last_update_success:
        await coordinator.async_refresh()
        if not coordinator.last_update_success:
            raise PlatformNotReady

    # Load stored values
    store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
    stored_values = await store.async_load() or {}

    entities = []
    dogs = entry.options.get(CONF_DOGS, [])

    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue

        modules = dog.get(CONF_DOG_MODULES, {})
        dog_stored = stored_values.get(dog_id, {})

        # Walk module numbers
        if modules.get(MODULE_WALK):
            entities.extend(
                [
                    WalkThresholdNumber(coordinator, entry, dog_id, store, dog_stored),
                    MinWalkDurationNumber(
                        coordinator, entry, dog_id, store, dog_stored
                    ),
                ]
            )

        # Feeding module numbers
        if modules.get(MODULE_FEEDING):
            entities.extend(
                [
                    BreakfastPortionNumber(
                        coordinator, entry, dog_id, store, dog_stored
                    ),
                    LunchPortionNumber(coordinator, entry, dog_id, store, dog_stored),
                    DinnerPortionNumber(coordinator, entry, dog_id, store, dog_stored),
                    SnackPortionNumber(coordinator, entry, dog_id, store, dog_stored),
                ]
            )

        # Health module numbers
        if modules.get(MODULE_HEALTH):
            entities.append(
                TargetWeightNumber(coordinator, entry, dog_id, store, dog_stored)
            )

        # Grooming module numbers
        if modules.get(MODULE_GROOMING):
            entities.append(
                GroomingIntervalNumber(coordinator, entry, dog_id, store, dog_stored)
            )

        # Training module numbers
        if modules.get(MODULE_TRAINING):
            entities.append(
                TrainingDurationNumber(coordinator, entry, dog_id, store, dog_stored)
            )

    async_add_entities(entities, True)


class PawControlNumberWithStorage(PawControlNumberEntity, NumberEntity):
    """Base class for number entities with persistent storage."""

    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict,
        entity_key: str,
        translation_key: str,
        icon: str,
        min_value: float,
        max_value: float,
        step: float,
        unit: str | None = None,
        default_value: float | None = None,
    ) -> None:
        """Initialize the number entity with storage."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            entity_key,
            translation_key=translation_key,
            entity_category=EntityCategory.CONFIG,
            min_value=min_value,
            max_value=max_value,
            step=step,
        )
        self._store = store
        self._stored_values = stored_values
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._default_value = default_value
        self._current_value = stored_values.get(entity_key, default_value)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._current_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the value and persist it."""
        self._current_value = value

        # Load current storage
        all_stored = await self._store.async_load() or {}

        # Update value for this dog and entity
        if self.dog_id not in all_stored:
            all_stored[self.dog_id] = {}
        all_stored[self.dog_id][self.entity_key] = value

        # Save to storage
        await self._store.async_save(all_stored)

        _LOGGER.debug(f"Set {self.entity_key} for {self.dog_name} to {value}")
        self.async_write_ha_state()


class WalkThresholdNumber(PawControlNumberWithStorage):
    """Number entity for walk threshold hours."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the number entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "walk_threshold_hours",
            "walk_threshold",
            "mdi:timer-sand",
            1,
            24,
            0.5,
            "hours",
            DEFAULT_WALK_THRESHOLD_HOURS,
        )


class MinWalkDurationNumber(PawControlNumberWithStorage):
    """Number entity for minimum walk duration."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the number entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "min_walk_duration",
            "min_walk_duration",
            "mdi:timer",
            5,
            120,
            5,
            UnitOfTime.MINUTES,
            DEFAULT_MIN_WALK_DURATION_MIN,
        )


class BreakfastPortionNumber(PawControlNumberWithStorage):
    """Number entity for breakfast portion size."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the number entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "breakfast_portion",
            "breakfast_portion",
            "mdi:food-apple",
            10,
            1000,
            10,
            UnitOfMass.GRAMS,
            200,
        )


class LunchPortionNumber(PawControlNumberWithStorage):
    """Number entity for lunch portion size."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the number entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "lunch_portion",
            "lunch_portion",
            "mdi:food",
            10,
            1000,
            10,
            UnitOfMass.GRAMS,
            150,
        )


class DinnerPortionNumber(PawControlNumberWithStorage):
    """Number entity for dinner portion size."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the number entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "dinner_portion",
            "dinner_portion",
            "mdi:food-variant",
            10,
            1000,
            10,
            UnitOfMass.GRAMS,
            200,
        )


class SnackPortionNumber(PawControlNumberWithStorage):
    """Number entity for snack portion size."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the number entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "snack_portion",
            "snack_portion",
            "mdi:cookie",
            5,
            200,
            5,
            UnitOfMass.GRAMS,
            50,
        )


class TargetWeightNumber(PawControlNumberWithStorage):
    """Number entity for target weight."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the number entity."""
        # Get initial weight from dog info
        dog_data = coordinator.get_dog_data(dog_id)
        current_weight = dog_data.get("info", {}).get("weight", 20)

        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "target_weight",
            "target_weight",
            "mdi:weight",
            MIN_DOG_WEIGHT_KG,
            MAX_DOG_WEIGHT_KG,
            0.1,
            UnitOfMass.KILOGRAMS,
            current_weight,
        )

    async def async_set_native_value(self, value: float) -> None:
        """Update the value and also update in coordinator."""
        await super().async_set_native_value(value)

        # Also update in coordinator for immediate effect
        dog_data = self.coordinator.get_dog_data(self.dog_id)
        if dog_data and "health" in dog_data:
            dog_data["health"]["target_weight_kg"] = value
            await self.coordinator.async_request_refresh()


class GroomingIntervalNumber(PawControlNumberWithStorage):
    """Number entity for grooming interval."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the number entity."""
        # Get current interval from coordinator
        dog_data = coordinator.get_dog_data(dog_id)
        current_interval = dog_data.get("grooming", {}).get(
            "grooming_interval_days", DEFAULT_GROOMING_INTERVAL_DAYS
        )

        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "grooming_interval",
            "grooming_interval",
            "mdi:calendar-repeat",
            1,
            365,
            1,
            "days",
            current_interval,
        )

    async def async_set_native_value(self, value: float) -> None:
        """Update the value and also update in coordinator."""
        await super().async_set_native_value(value)

        # Update in coordinator for immediate effect
        dog_data = self.coordinator.get_dog_data(self.dog_id)
        if dog_data and "grooming" in dog_data:
            dog_data["grooming"]["grooming_interval_days"] = int(value)
            # Recalculate needs_grooming
            await self.coordinator.async_request_refresh()


class TrainingDurationNumber(PawControlNumberWithStorage):
    """Number entity for default training duration."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the number entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "training_duration",
            "training_duration",
            "mdi:timer-outline",
            5,
            120,
            5,
            UnitOfTime.MINUTES,
            15,
        )
