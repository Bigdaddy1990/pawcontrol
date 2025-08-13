"""Number platform for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DEFAULT_GROOMING_INTERVAL_DAYS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
    MODULE_WALK,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control number entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []
    dogs = entry.options.get(CONF_DOGS, [])

    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue

        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})

        # Walk module numbers
        if modules.get(MODULE_WALK):
            entities.extend(
                [
                    WalkThresholdNumber(hass, coordinator, dog_id, dog_name),
                    MinWalkDurationNumber(hass, coordinator, dog_id, dog_name),
                ]
            )

        # Feeding module numbers
        if modules.get(MODULE_FEEDING):
            entities.extend(
                [
                    BreakfastPortionNumber(hass, coordinator, dog_id, dog_name),
                    LunchPortionNumber(hass, coordinator, dog_id, dog_name),
                    DinnerPortionNumber(hass, coordinator, dog_id, dog_name),
                    SnackPortionNumber(hass, coordinator, dog_id, dog_name),
                ]
            )

        # Health module numbers
        if modules.get(MODULE_HEALTH):
            entities.append(TargetWeightNumber(hass, coordinator, dog_id, dog_name))

        # Grooming module numbers
        if modules.get(MODULE_GROOMING):
            entities.append(GroomingIntervalNumber(hass, coordinator, dog_id, dog_name))

        # Training module numbers
        if modules.get(MODULE_TRAINING):
            entities.append(TrainingDurationNumber(hass, coordinator, dog_id, dog_name))

    async_add_entities(entities, True)


class PawControlNumberBase(NumberEntity):
    """Base class for Paw Control number entities."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: Any,
        dog_id: str,
        dog_name: str,
        number_type: str,
        name: str,
        icon: str,
        min_value: float,
        max_value: float,
        step: float,
        unit: str | None = None,
    ) -> None:
        """Initialize the number entity."""
        self.hass = hass
        self.coordinator = coordinator
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._number_type = number_type

        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.number.{number_type}"
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


class WalkThresholdNumber(PawControlNumberBase):
    """Number entity for walk threshold hours."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the number entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "walk_threshold_hours",
            "Walk Threshold",
            "mdi:timer-sand",
            1,
            24,
            0.5,
            "hours",
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        # Default to 8 hours
        return 8

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.info(f"Walk threshold for {self._dog_name} set to {value} hours")
        # Store in coordinator or helper entity
        # Implementation would store this value persistently


class MinWalkDurationNumber(PawControlNumberBase):
    """Number entity for minimum walk duration."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the number entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "min_walk_duration",
            "Min Walk Duration",
            "mdi:timer",
            5,
            120,
            5,
            UnitOfTime.MINUTES,
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return 30

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.info(f"Min walk duration for {self._dog_name} set to {value} minutes")


class BreakfastPortionNumber(PawControlNumberBase):
    """Number entity for breakfast portion size."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the number entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "breakfast_portion",
            "Breakfast Portion",
            "mdi:food-apple",
            10,
            1000,
            10,
            "g",
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return 200

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.info(f"Breakfast portion for {self._dog_name} set to {value}g")


class LunchPortionNumber(PawControlNumberBase):
    """Number entity for lunch portion size."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the number entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "lunch_portion",
            "Lunch Portion",
            "mdi:food",
            10,
            1000,
            10,
            "g",
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return 150

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.info(f"Lunch portion for {self._dog_name} set to {value}g")


class DinnerPortionNumber(PawControlNumberBase):
    """Number entity for dinner portion size."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the number entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "dinner_portion",
            "Dinner Portion",
            "mdi:food-variant",
            10,
            1000,
            10,
            "g",
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return 200

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.info(f"Dinner portion for {self._dog_name} set to {value}g")


class SnackPortionNumber(PawControlNumberBase):
    """Number entity for snack portion size."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the number entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "snack_portion",
            "Snack Portion",
            "mdi:cookie",
            5,
            200,
            5,
            "g",
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return 50

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.info(f"Snack portion for {self._dog_name} set to {value}g")


class TargetWeightNumber(PawControlNumberBase):
    """Number entity for target weight."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the number entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "target_weight",
            "Target Weight",
            "mdi:weight",
            1,
            200,
            0.1,
            UnitOfMass.KILOGRAMS,
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        # Get from dog info or default
        return self.dog_data.get("info", {}).get("weight", 20)

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.info(f"Target weight for {self._dog_name} set to {value}kg")


class GroomingIntervalNumber(PawControlNumberBase):
    """Number entity for grooming interval."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the number entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "grooming_interval",
            "Grooming Interval",
            "mdi:calendar-repeat",
            1,
            365,
            1,
            "days",
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.dog_data.get("grooming", {}).get(
            "grooming_interval_days", DEFAULT_GROOMING_INTERVAL_DAYS
        )

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.info(f"Grooming interval for {self._dog_name} set to {value} days")
        # Update in coordinator
        self.dog_data["grooming"]["grooming_interval_days"] = int(value)
        await self.coordinator.async_request_refresh()


class TrainingDurationNumber(PawControlNumberBase):
    """Number entity for default training duration."""

    def __init__(self, hass, coordinator, dog_id, dog_name):
        """Initialize the number entity."""
        super().__init__(
            hass,
            coordinator,
            dog_id,
            dog_name,
            "training_duration",
            "Training Duration",
            "mdi:timer-outline",
            5,
            120,
            5,
            UnitOfTime.MINUTES,
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return 15

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.info(f"Training duration for {self._dog_name} set to {value} minutes")
