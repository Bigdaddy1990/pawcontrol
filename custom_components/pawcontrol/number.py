"""Number platform for Paw Control integration.

This module provides comprehensive number entities for dog monitoring configuration
including weight settings, timing controls, thresholds, and system parameters.
All number entities are designed to meet Home Assistant's Platinum quality ambitions
with full type annotations, async operations, and robust validation.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import cast

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.number import NumberEntity
from homeassistant.components.number import NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.const import UnitOfEnergy
from homeassistant.const import UnitOfLength
from homeassistant.const import UnitOfMass
from homeassistant.const import UnitOfSpeed
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry
from .compat import HomeAssistantError
from .const import MAX_DOG_AGE
from .const import MAX_DOG_WEIGHT
from .const import MIN_DOG_AGE
from .const import MIN_DOG_WEIGHT
from .const import MODULE_FEEDING
from .const import MODULE_GPS
from .const import MODULE_HEALTH
from .const import MODULE_WALK
from .coordinator import PawControlCoordinator
from .diagnostics import normalize_value
from .entity import PawControlDogEntityBase
from .runtime_data import get_runtime_data
from .types import CoordinatorDogData
from .types import CoordinatorModuleState
from .types import DOG_AGE_FIELD
from .types import DOG_ID_FIELD
from .types import DOG_NAME_FIELD
from .types import DOG_WEIGHT_FIELD
from .types import DogConfigData
from .types import DogModulesMapping
from .types import DogProfileSnapshot
from .types import ensure_dog_modules_mapping
from .types import ensure_json_mapping
from .types import NumberExtraAttributes
from .utils import async_call_add_entities

_LOGGER = logging.getLogger(__name__)

# Many number entities trigger write operations (service calls). The
# coordinator applies its own throttling so we can keep Home Assistant's
# parallel scheduling fully enabled.
PARALLEL_UPDATES = 0

# Configuration limits and defaults
DEFAULT_WALK_DURATION_TARGET = 60  # minutes
DEFAULT_FEEDING_REMINDER_HOURS = 8  # hours
DEFAULT_GPS_ACCURACY_THRESHOLD = 50  # meters
DEFAULT_ACTIVITY_GOAL = 100  # percentage


def _normalise_attributes(attrs: Mapping[str, object]) -> NumberExtraAttributes:
    """Return JSON-serialisable attributes for number entities."""

    payload = ensure_json_mapping(attrs)
    return cast(NumberExtraAttributes, normalize_value(payload))


async def _async_add_entities_in_batches(
    async_add_entities_func: AddEntitiesCallback,
    entities: list[PawControlNumberBase],
    batch_size: int = 12,
    delay_between_batches: float = 0.1,
) -> None:
    """Add number entities in small batches to prevent Entity Registry overload.

    The Entity Registry logs warnings when >200 messages occur rapidly.
    By batching entities and adding delays, we prevent registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of number entities to add
        batch_size: Number of entities per batch (default: 12)
        delay_between_batches: Seconds to wait between batches (default: 0.1s)
    """
    total_entities = len(entities)

    _LOGGER.debug(
        'Adding %d number entities in batches of %d to prevent Registry overload',
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
        batch = entities[i: i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            'Processing number batch %d/%d with %d entities',
            batch_num,
            total_batches,
            len(batch),
        )

        # Add batch without update_before_add to reduce Registry load
        await async_call_add_entities(
            async_add_entities_func, batch, update_before_add=False,
        )

        # Small delay between batches to prevent Registry flooding
        if i + batch_size < total_entities:  # No delay after last batch
            await asyncio.sleep(delay_between_batches)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control number platform.

    Creates number entities for all configured dogs to control various
    numerical settings and thresholds. Numbers provide precise control
    over monitoring parameters and goals.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry containing dog configurations
        async_add_entities: Callback to add number entities
    """
    runtime_data = get_runtime_data(hass, entry)
    if runtime_data is None:
        _LOGGER.error('Runtime data missing for entry %s', entry.entry_id)
        return

    coordinator: PawControlCoordinator = runtime_data.coordinator
    dogs: list[DogConfigData] = runtime_data.dogs

    entities: list[PawControlNumberBase] = []

    # Create number entities for each configured dog
    for dog in dogs:
        dog_id: str = dog[DOG_ID_FIELD]
        dog_name: str = dog[DOG_NAME_FIELD]
        modules: DogModulesMapping = ensure_dog_modules_mapping(dog)

        _LOGGER.debug(
            'Creating number entities for dog: %s (%s)',
            dog_name, dog_id,
        )

        # Base numbers - always created for every dog
        entities.extend(
            _create_base_numbers(
            coordinator, dog_id, dog_name, dog,
            ),
        )

        # Module-specific numbers
        if modules.get(MODULE_FEEDING, False):
            entities.extend(
                _create_feeding_numbers(
                coordinator, dog_id, dog_name,
                ),
            )

        if modules.get(MODULE_WALK, False):
            entities.extend(
                _create_walk_numbers(
                coordinator, dog_id, dog_name,
                ),
            )

        if modules.get(MODULE_GPS, False):
            entities.extend(_create_gps_numbers(coordinator, dog_id, dog_name))

        if modules.get(MODULE_HEALTH, False):
            entities.extend(
                _create_health_numbers(
                coordinator, dog_id, dog_name,
                ),
            )

    # Add entities in smaller batches to prevent Entity Registry overload
    # With 46+ number entities (2 dogs), batching prevents Registry flooding
    await _async_add_entities_in_batches(async_add_entities, entities, batch_size=12)

    _LOGGER.info(
        'Created %d number entities for %d dogs using batched approach',
        len(entities),
        len(dogs),
    )


def _create_base_numbers(
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    dog_config: DogConfigData,
) -> list[PawControlNumberBase]:
    """Create base numbers that are always present for every dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        dog_config: Dog configuration data

    Returns:
        List of base number entities
    """
    return [
        PawControlDogWeightNumber(coordinator, dog_id, dog_name, dog_config),
        PawControlDogAgeNumber(coordinator, dog_id, dog_name, dog_config),
        PawControlActivityGoalNumber(coordinator, dog_id, dog_name),
    ]


def _create_feeding_numbers(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
) -> list[PawControlNumberBase]:
    """Create feeding-related numbers for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of feeding number entities
    """
    return [
        PawControlDailyFoodAmountNumber(coordinator, dog_id, dog_name),
        PawControlFeedingReminderHoursNumber(coordinator, dog_id, dog_name),
        PawControlMealsPerDayNumber(coordinator, dog_id, dog_name),
        PawControlPortionSizeNumber(coordinator, dog_id, dog_name),
        PawControlCalorieTargetNumber(coordinator, dog_id, dog_name),
    ]


def _create_walk_numbers(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
) -> list[PawControlNumberBase]:
    """Create walk-related numbers for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of walk number entities
    """
    return [
        PawControlDailyWalkTargetNumber(coordinator, dog_id, dog_name),
        PawControlWalkDurationTargetNumber(coordinator, dog_id, dog_name),
        PawControlWalkDistanceTargetNumber(coordinator, dog_id, dog_name),
        PawControlWalkReminderHoursNumber(coordinator, dog_id, dog_name),
        PawControlMaxWalkSpeedNumber(coordinator, dog_id, dog_name),
    ]


def _create_gps_numbers(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
) -> list[PawControlNumberBase]:
    """Create GPS and location-related numbers for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of GPS number entities
    """
    return [
        PawControlGPSAccuracyThresholdNumber(coordinator, dog_id, dog_name),
        PawControlGPSUpdateIntervalNumber(coordinator, dog_id, dog_name),
        PawControlGeofenceRadiusNumber(coordinator, dog_id, dog_name),
        PawControlLocationUpdateDistanceNumber(coordinator, dog_id, dog_name),
        PawControlGPSBatteryThresholdNumber(coordinator, dog_id, dog_name),
    ]


def _create_health_numbers(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
) -> list[PawControlNumberBase]:
    """Create health and medical-related numbers for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of health number entities
    """
    return [
        PawControlTargetWeightNumber(coordinator, dog_id, dog_name),
        PawControlWeightChangeThresholdNumber(coordinator, dog_id, dog_name),
        PawControlGroomingIntervalNumber(coordinator, dog_id, dog_name),
        PawControlVetCheckupIntervalNumber(coordinator, dog_id, dog_name),
        PawControlHealthScoreThresholdNumber(coordinator, dog_id, dog_name),
    ]


class PawControlNumberBase(PawControlDogEntityBase, NumberEntity, RestoreEntity):
    """Base class for all Paw Control number entities.

    Provides common functionality and ensures consistent behavior across
    all number types. Includes proper device grouping, state persistence,
    validation, and error handling.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        number_type: str,
        *,
        device_class: NumberDeviceClass | None = None,
        mode: NumberMode = NumberMode.AUTO,
        native_unit_of_measurement: str | None = None,
        native_min_value: float = 0,
        native_max_value: float = 100,
        native_step: float = 1,
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
        initial_value: float | None = None,
        translation_key: str | None = None,
    ) -> None:
        """Initialize the number entity.

        Args:
            coordinator: Data coordinator for updates
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
            number_type: Type identifier for the number
            device_class: Home Assistant device class
            mode: Number input mode (auto, box, slider)
            native_unit_of_measurement: Unit of measurement
            native_min_value: Minimum allowed value
            native_max_value: Maximum allowed value
            native_step: Step size for value changes
            icon: Material Design icon
            entity_category: Entity category for organization
            initial_value: Initial value for the number
        """
        super().__init__(coordinator, dog_id, dog_name)
        self._number_type = number_type
        self._value = initial_value

        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{number_type}"
        self._attr_translation_key = translation_key or number_type
        self._attr_device_class = device_class
        self._attr_mode = mode
        self._attr_native_unit_of_measurement = native_unit_of_measurement
        self._attr_native_min_value = native_min_value
        self._attr_native_max_value = native_max_value
        self._attr_native_step = native_step
        self._attr_icon = icon
        self._attr_entity_category = entity_category

        # Link entity to PawControl device entry for the dog
        self.update_device_metadata(
            model='Smart Dog Monitoring',
            sw_version='1.0.0',
            configuration_url='https://github.com/BigDaddy1990/pawcontrol',
        )

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant.

        Restores the previous value and sets up any required listeners.
        """
        await super().async_added_to_hass()

        # Restore previous value
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in (
            'unknown',
            'unavailable',
        ):
            try:
                self._value = float(last_state.state)
                _LOGGER.debug(
                    'Restored number value for %s %s: %s',
                    self._dog_name,
                    self._number_type,
                    self._value,
                )
            except (ValueError, TypeError):
                _LOGGER.warning(
                    'Could not restore number value for %s %s: %s',
                    self._dog_name,
                    self._number_type,
                    last_state.state,
                )

    @property
    def native_value(self) -> float | None:
        """Return the current value of the number.

        Returns:
            Current number value
        """
        return self._value

    @property
    def extra_state_attributes(self) -> NumberExtraAttributes:
        """Return additional state attributes for the number.

        Provides information about the number's function and constraints.

        Returns:
            Dictionary of additional state attributes
        """
        attrs = cast(
            NumberExtraAttributes,
            self._build_base_state_attributes(
                {
                    'number_type': self._number_type,
                    'min_value': self.native_min_value,
                    'max_value': self.native_max_value,
                    'step': self.native_step,
                    'last_changed': dt_util.utcnow().isoformat(),
                },
            ),
        )

        return _normalise_attributes(attrs)

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value.

        Args:
            value: New value to set

        Raises:
            HomeAssistantError: If value is invalid or cannot be set
        """
        # Validate value range
        if not (self.native_min_value <= value <= self.native_max_value):
            raise HomeAssistantError(
                f"Value {value} is outside allowed range "
                f"({self.native_min_value}-{self.native_max_value})",
            )

        try:
            await self._async_set_number_value(value)
            self._value = value
            self.async_write_ha_state()

            _LOGGER.info(
                'Set %s for %s (%s) to %s',
                self._number_type,
                self._dog_name,
                self._dog_id,
                value,
            )

        except Exception as err:
            _LOGGER.error(
                'Failed to set %s for %s: %s', self._number_type, self._dog_name, err,
            )
            raise HomeAssistantError(
                f"Failed to set {self._number_type}",
            ) from err

    async def _async_set_number_value(self, value: float) -> None:
        """Set the number value implementation.

        This method should be overridden by subclasses to implement
        specific number functionality.

        Args:
            value: New value to set
        """
        # Base implementation - subclasses should override
        pass

    def _get_dog_data(self) -> CoordinatorDogData | None:
        """Get data for this number's dog from the coordinator."""

        return self._get_dog_data_cached()

    def _get_module_data(self, module: str) -> CoordinatorModuleState | None:
        """Get specific module data for this dog.

        Args:
            module: Module name to retrieve data for

        Returns:
            Module data dictionary or None if not available
        """
        return self.coordinator.get_module_data(self._dog_id, module)

    @property
    def available(self) -> bool:
        """Return if the number is available.

        A number is available when the coordinator is available and
        the dog data can be retrieved.

        Returns:
            True if number is available, False otherwise
        """
        return self.coordinator.available and self._get_dog_data() is not None


# Base numbers
class PawControlDogWeightNumber(PawControlNumberBase):
    """Number entity for the dog's current weight."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        dog_config: DogConfigData,
    ) -> None:
        """Initialize the dog weight number."""
        current_weight = cast(float | None, dog_config.get(DOG_WEIGHT_FIELD))
        if current_weight is None:
            current_weight = 20.0

        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'weight',
            device_class=NumberDeviceClass.WEIGHT,
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfMass.KILOGRAMS,
            native_min_value=MIN_DOG_WEIGHT,
            native_max_value=MAX_DOG_WEIGHT,
            native_step=0.1,
            icon='mdi:scale',
            initial_value=current_weight,
            translation_key='weight',
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the dog's weight."""
        # This would update the dog's weight in the configuration
        # and trigger health calculations

        # Update the coordinator with the new weight
        await self.coordinator.async_refresh_dog(self._dog_id)

    @property
    def extra_state_attributes(self) -> NumberExtraAttributes:
        """Return additional attributes for the weight number."""
        attrs = super().extra_state_attributes
        health_data = self._get_module_data('health')

        if isinstance(health_data, Mapping):
            weight_trend = health_data.get('weight_trend')
            if isinstance(weight_trend, str):
                attrs['weight_trend'] = weight_trend

            weight_change_percent = health_data.get('weight_change_percent')
            if isinstance(weight_change_percent, int | float):
                attrs['weight_change_percent'] = float(weight_change_percent)

            last_weight_date = health_data.get('last_weight_date')
            if isinstance(last_weight_date, str):
                attrs['last_weight_date'] = last_weight_date

            target_weight = health_data.get('target_weight')
            if isinstance(target_weight, int | float):
                attrs['target_weight'] = float(target_weight)

        return _normalise_attributes(attrs)


class PawControlDogAgeNumber(PawControlNumberBase):
    """Number entity for the dog's age."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        dog_config: DogConfigData,
    ) -> None:
        """Initialize the dog age number."""
        current_age = cast(int | None, dog_config.get(DOG_AGE_FIELD))
        if current_age is None:
            current_age = 3

        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'age',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfTime.YEARS,
            native_min_value=MIN_DOG_AGE,
            native_max_value=MAX_DOG_AGE,
            native_step=1,
            icon='mdi:calendar',
            entity_category=EntityCategory.CONFIG,
            initial_value=current_age,
            translation_key='age',
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the dog's age."""
        int_value = int(value)

        # Update coordinator cache so other entities see the new value immediately
        dog_data = self._get_dog_data()
        if dog_data is not None:
            profile_data = cast(
                DogProfileSnapshot,
                dog_data.setdefault('profile', cast(DogProfileSnapshot, {})),
            )
            profile_data[DOG_AGE_FIELD] = int_value

        # Persist the change if the data manager is available
        data_manager = self._get_data_manager()
        if data_manager is not None:
            try:
                await data_manager.async_update_dog_data(
                    self._dog_id, {'profile': {DOG_AGE_FIELD: int_value}},
                )
            except Exception as err:  # pragma: no cover - best effort only
                _LOGGER.debug(
                    'Could not persist dog age for %s: %s', self._dog_name, err,
                )

        _LOGGER.info('Set age for %s to %s', self._dog_name, int_value)


class PawControlActivityGoalNumber(PawControlNumberBase):
    """Number entity for the dog's daily activity goal."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the activity goal number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'activity_goal',
            mode=NumberMode.SLIDER,
            native_unit_of_measurement=PERCENTAGE,
            native_min_value=50,
            native_max_value=200,
            native_step=5,
            icon='mdi:target',
            initial_value=DEFAULT_ACTIVITY_GOAL,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the activity goal."""
        # This would update activity tracking goals
        pass


# Feeding numbers
class PawControlDailyFoodAmountNumber(PawControlNumberBase):
    """Number entity for daily food amount in grams."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the daily food amount number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'daily_food_amount',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            native_min_value=50,
            native_max_value=2000,
            native_step=10,
            icon='mdi:food',
            initial_value=300,
            translation_key='daily_food_amount',
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the daily food amount."""
        # This would update feeding calculations and portion sizes
        pass

    @property
    def extra_state_attributes(self) -> NumberExtraAttributes:
        """Return additional attributes for daily food amount."""
        attrs = super().extra_state_attributes

        # Calculate recommended amount based on dog size/weight
        dog_data = self._get_dog_data()
        if dog_data and 'dog_info' in dog_data:
            info = dog_data['dog_info']
            weight_value = info.get('dog_weight')
            if isinstance(weight_value, int | float):
                weight = float(weight_value)
            else:
                weight = 20.0
            recommended = self._calculate_recommended_amount(weight)
            attrs['recommended_amount'] = recommended
            current_value = self.native_value
            if current_value is None or recommended <= 0:
                attrs['current_vs_recommended'] = 'N/A'
            else:
                attrs['current_vs_recommended'] = (
                    f"{(current_value / recommended * 100):.0f}%"
                )

        return _normalise_attributes(attrs)

    def _calculate_recommended_amount(self, weight: float) -> float:
        """Calculate recommended daily food amount based on weight.

        Args:
            weight: Dog weight in kg

        Returns:
            Recommended daily food amount in grams
        """
        # Simplified calculation: ~20-25g per kg of body weight
        return weight * 22.5


class PawControlFeedingReminderHoursNumber(PawControlNumberBase):
    """Number entity for feeding reminder interval in hours."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the feeding reminder hours number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'feeding_reminder_hours',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfTime.HOURS,
            native_min_value=2,
            native_max_value=24,
            native_step=1,
            icon='mdi:clock-alert',
            initial_value=DEFAULT_FEEDING_REMINDER_HOURS,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the feeding reminder hours."""
        # This would update feeding reminder automations
        pass


class PawControlMealsPerDayNumber(PawControlNumberBase):
    """Number entity for number of meals per day."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the meals per day number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'meals_per_day',
            mode=NumberMode.BOX,
            native_min_value=1,
            native_max_value=6,
            native_step=1,
            icon='mdi:numeric',
            initial_value=2,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the meals per day."""
        # This would update feeding schedule calculations
        pass


class PawControlPortionSizeNumber(PawControlNumberBase):
    """Number entity for default portion size in grams."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the portion size number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'portion_size',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            native_min_value=10,
            native_max_value=500,
            native_step=5,
            icon='mdi:food-variant',
            initial_value=150,
            translation_key='portion_size',
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the portion size."""
        # This would update default portion calculations
        pass


class PawControlCalorieTargetNumber(PawControlNumberBase):
    """Number entity for daily calorie target."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the calorie target number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'calorie_target',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
            native_min_value=200,
            native_max_value=3000,
            native_step=50,
            icon='mdi:fire',
            initial_value=800,
            translation_key='calorie_target',
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the calorie target."""
        # This would update calorie tracking and goals
        pass


# Walk numbers
class PawControlDailyWalkTargetNumber(PawControlNumberBase):
    """Number entity for daily walk target count."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the daily walk target number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'daily_walk_target',
            mode=NumberMode.BOX,
            native_min_value=1,
            native_max_value=10,
            native_step=1,
            icon='mdi:walk',
            initial_value=3,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the daily walk target."""
        # This would update walk goal tracking
        pass


class PawControlWalkDurationTargetNumber(PawControlNumberBase):
    """Number entity for walk duration target in minutes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the walk duration target number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'walk_duration_target',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfTime.MINUTES,
            native_min_value=10,
            native_max_value=180,
            native_step=5,
            icon='mdi:timer',
            initial_value=DEFAULT_WALK_DURATION_TARGET,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the walk duration target."""
        # This would update walk duration goals
        pass


class PawControlWalkDistanceTargetNumber(PawControlNumberBase):
    """Number entity for walk distance target in meters."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the walk distance target number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'walk_distance_target',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfLength.METERS,
            native_min_value=100,
            native_max_value=10000,
            native_step=100,
            icon='mdi:map-marker-distance',
            initial_value=2000,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the walk distance target."""
        # This would update walk distance goals
        pass


class PawControlWalkReminderHoursNumber(PawControlNumberBase):
    """Number entity for walk reminder interval in hours."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the walk reminder hours number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'walk_reminder_hours',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfTime.HOURS,
            native_min_value=2,
            native_max_value=24,
            native_step=1,
            icon='mdi:clock-alert',
            initial_value=8,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the walk reminder hours."""
        # This would update walk reminder automations
        pass


class PawControlMaxWalkSpeedNumber(PawControlNumberBase):
    """Number entity for maximum expected walk speed."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the max walk speed number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'max_walk_speed',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
            native_min_value=2,
            native_max_value=30,
            native_step=1,
            icon='mdi:speedometer',
            initial_value=15,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the max walk speed."""
        # This would update speed thresholds for walk detection
        pass


# GPS numbers
class PawControlGPSAccuracyThresholdNumber(PawControlNumberBase):
    """Number entity for GPS accuracy threshold in meters."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the GPS accuracy threshold number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'gps_accuracy_threshold',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfLength.METERS,
            native_min_value=5,
            native_max_value=500,
            native_step=5,
            icon='mdi:crosshairs-gps',
            entity_category=EntityCategory.CONFIG,
            initial_value=DEFAULT_GPS_ACCURACY_THRESHOLD,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the GPS accuracy threshold."""
        # This would update GPS filtering settings
        pass


class PawControlGPSUpdateIntervalNumber(PawControlNumberBase):
    """Number entity for GPS update interval in seconds."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the GPS update interval number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'gps_update_interval',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            native_min_value=30,
            native_max_value=600,
            native_step=30,
            icon='mdi:update',
            entity_category=EntityCategory.CONFIG,
            initial_value=60,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the GPS update interval."""
        # This would update GPS polling frequency
        pass


class PawControlGeofenceRadiusNumber(PawControlNumberBase):
    """Number entity for geofence radius in meters."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the geofence radius number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'geofence_radius',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfLength.METERS,
            native_min_value=10,
            native_max_value=1000,
            native_step=10,
            icon='mdi:map-marker-circle',
            initial_value=100,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the geofence radius."""
        # This would update geofencing calculations
        pass


class PawControlLocationUpdateDistanceNumber(PawControlNumberBase):
    """Number entity for minimum distance for location updates."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the location update distance number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'location_update_distance',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfLength.METERS,
            native_min_value=1,
            native_max_value=100,
            native_step=1,
            icon='mdi:map-marker-path',
            entity_category=EntityCategory.CONFIG,
            initial_value=10,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the location update distance."""
        # This would update location filtering settings
        pass


class PawControlGPSBatteryThresholdNumber(PawControlNumberBase):
    """Number entity for GPS battery alert threshold."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the GPS battery threshold number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'gps_battery_threshold',
            mode=NumberMode.SLIDER,
            native_unit_of_measurement=PERCENTAGE,
            native_min_value=5,
            native_max_value=50,
            native_step=5,
            icon='mdi:battery-alert',
            initial_value=20,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the GPS battery threshold."""
        # This would update battery alert settings
        pass


# Health numbers
class PawControlTargetWeightNumber(PawControlNumberBase):
    """Number entity for target weight in kg."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the target weight number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'target_weight',
            device_class=NumberDeviceClass.WEIGHT,
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfMass.KILOGRAMS,
            native_min_value=MIN_DOG_WEIGHT,
            native_max_value=MAX_DOG_WEIGHT,
            native_step=0.1,
            icon='mdi:target',
            initial_value=20.0,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the target weight."""
        # This would update weight tracking goals
        pass


class PawControlWeightChangeThresholdNumber(PawControlNumberBase):
    """Number entity for weight change alert threshold."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the weight change threshold number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'weight_change_threshold',
            mode=NumberMode.SLIDER,
            native_unit_of_measurement=PERCENTAGE,
            native_min_value=5,
            native_max_value=25,
            native_step=1,
            icon='mdi:scale-unbalanced',
            initial_value=10,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the weight change threshold."""
        # This would update weight alert settings
        pass


class PawControlGroomingIntervalNumber(PawControlNumberBase):
    """Number entity for grooming interval in days."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the grooming interval number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'grooming_interval',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfTime.DAYS,
            native_min_value=7,
            native_max_value=90,
            native_step=7,
            icon='mdi:content-cut',
            initial_value=28,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the grooming interval."""
        # This would update grooming reminder schedule
        pass


class PawControlVetCheckupIntervalNumber(PawControlNumberBase):
    """Number entity for vet checkup interval in months."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the vet checkup interval number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'vet_checkup_interval',
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfTime.MONTHS,
            native_min_value=3,
            native_max_value=24,
            native_step=3,
            icon='mdi:medical-bag',
            initial_value=12,
            translation_key='vet_checkup_interval',
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the vet checkup interval."""
        # This would update vet appointment reminders
        pass


class PawControlHealthScoreThresholdNumber(PawControlNumberBase):
    """Number entity for health score alert threshold."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str,
    ) -> None:
        """Initialize the health score threshold number."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'health_score_threshold',
            mode=NumberMode.SLIDER,
            native_unit_of_measurement=PERCENTAGE,
            native_min_value=30,
            native_max_value=90,
            native_step=5,
            icon='mdi:heart-pulse',
            initial_value=70,
        )

    async def _async_set_number_value(self, value: float) -> None:
        """Set the health score threshold."""
        # This would update health alert settings
        pass
