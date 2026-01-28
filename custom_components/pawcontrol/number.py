"""Number platform for Paw Control integration.

This module provides comprehensive number entities for dog monitoring configuration
including weight settings, timing controls, thresholds, and system parameters.
All number entities are designed to meet Home Assistant's Platinum quality ambitions
with full type annotations, async operations, and robust validation.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import cast

from homeassistant import const as ha_const
from homeassistant.components import number as number_component
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import (
  ATTR_VALUE,
  PERCENTAGE,
  STATE_UNAVAILABLE,
  STATE_UNKNOWN,
  UnitOfEnergy,
  UnitOfLength,
  UnitOfTime,
)
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry, HomeAssistantError, MASS_GRAMS, MASS_KILOGRAMS
from .const import (
  CONF_DAILY_FOOD_AMOUNT,
  CONF_GPS_ACCURACY_FILTER,
  CONF_GPS_DISTANCE_FILTER,
  CONF_GPS_UPDATE_INTERVAL,
  CONF_GROOMING_INTERVAL,
  CONF_HOME_ZONE_RADIUS,
  CONF_MEALS_PER_DAY,
  DEFAULT_MODEL,
  DEFAULT_SW_VERSION,
  MAX_DOG_AGE,
  MAX_DOG_WEIGHT,
  MIN_DOG_AGE,
  MIN_DOG_WEIGHT,
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .diagnostics import _normalise_json as _normalise_diagnostics_json
from .entity import PawControlDogEntityBase
from .reproduce_state import async_reproduce_platform_states
from .runtime_data import get_runtime_data
from .types import (
  DOG_AGE_FIELD,
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  DOG_WEIGHT_FIELD,
  CoordinatorModuleLookupResult,
  CoordinatorDogData,
  DogConfigData,
  DOG_FEEDING_CONFIG_FIELD,
  DOG_GPS_CONFIG_FIELD,
  DOG_HEALTH_CONFIG_FIELD,
  DOG_WALK_CONFIG_FIELD,
  DogModulesMapping,
  GPSTrackingConfigInput,
  JSONMutableMapping,
  JSONValue,
  ensure_dog_modules_mapping,
  ensure_json_mapping,
)
from .utils import async_call_add_entities

# ``ATTR_ENTITY_ID`` moved/changed over time; fall back to the canonical key.
ATTR_ENTITY_ID = getattr(ha_const, "ATTR_ENTITY_ID", "entity_id")

_LOGGER = logging.getLogger(__name__)

# Many number entities trigger write operations (service calls). The
# coordinator applies its own throttling so we can keep Home Assistant's
# parallel scheduling fully enabled.
PARALLEL_UPDATES = 0

UnitOfSpeed = getattr(ha_const, "UnitOfSpeed", None)
if UnitOfSpeed is None:  # pragma: no cover - fallback for test harness constants

  class _FallbackUnitOfSpeed:
    KILOMETERS_PER_HOUR = "km/h"
    METERS_PER_SECOND = "m/s"

  UnitOfSpeed = _FallbackUnitOfSpeed


DEFAULT_NUMBER_MODE = getattr(NumberMode, "AUTO", NumberMode.BOX)
_WEIGHT_DEVICE_CLASS = cast(
  NumberDeviceClass,
  getattr(NumberDeviceClass, "WEIGHT", "weight"),
)


# Configuration limits and defaults
DEFAULT_WALK_DURATION_TARGET = 60  # minutes
DEFAULT_FEEDING_REMINDER_HOURS = 8  # hours
DEFAULT_GPS_ACCURACY_THRESHOLD = 50  # meters
DEFAULT_ACTIVITY_GOAL = 100  # percentage


def _merge_config_updates(
  current: Mapping[str, JSONValue] | None,
  updates: Mapping[str, JSONValue],
) -> JSONMutableMapping:
  """Return a merged mapping for configuration updates."""

  merged: JSONMutableMapping = dict(current) if isinstance(current, Mapping) else {}
  merged.update(dict(updates))
  return merged


def _build_gps_tracking_input(
  config: Mapping[str, JSONValue],
) -> GPSTrackingConfigInput:
  """Build GPS manager input from stored GPS configuration."""

  tracking_input: GPSTrackingConfigInput = {}

  accuracy_value = config.get(CONF_GPS_ACCURACY_FILTER)
  if isinstance(accuracy_value, int | float):
    tracking_input["gps_accuracy_threshold"] = float(accuracy_value)
  elif isinstance((legacy_accuracy := config.get("accuracy_threshold")), int | float):
    tracking_input["gps_accuracy_threshold"] = float(legacy_accuracy)

  update_interval_value = config.get(CONF_GPS_UPDATE_INTERVAL)
  if isinstance(update_interval_value, int | float):
    tracking_input["update_interval_seconds"] = int(update_interval_value)
  elif isinstance((legacy_interval := config.get("update_interval")), int | float):
    tracking_input["update_interval_seconds"] = int(legacy_interval)

  distance_value = config.get(CONF_GPS_DISTANCE_FILTER)
  if isinstance(distance_value, int | float):
    tracking_input["min_distance_for_point"] = float(distance_value)
  elif isinstance(
    (legacy_distance := config.get("min_distance_for_point")),
    int | float,
  ):
    tracking_input["min_distance_for_point"] = float(legacy_distance)

  return tracking_input


def _normalise_attributes(attrs: Mapping[str, object]) -> JSONMutableMapping:
  """Return JSON-serialisable attributes for number entities."""

  payload = ensure_json_mapping(attrs)
  return cast(JSONMutableMapping, _normalise_diagnostics_json(payload))


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
    "Adding %d number entities in batches of %d to prevent Registry overload",
    total_entities,
    batch_size,
  )

  # Process entities in batches
  for i in range(0, total_entities, batch_size):
    batch = entities[i : i + batch_size]
    batch_num = (i // batch_size) + 1
    total_batches = (total_entities + batch_size - 1) // batch_size

    _LOGGER.debug(
      "Processing number batch %d/%d with %d entities",
      batch_num,
      total_batches,
      len(batch),
    )

    # Add batch without update_before_add to reduce Registry load
    await async_call_add_entities(
      async_add_entities_func,
      batch,
      update_before_add=False,
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
    _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
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
      "Creating number entities for dog: %s (%s)",
      dog_name,
      dog_id,
    )

    # Base numbers - always created for every dog
    entities.extend(
      _create_base_numbers(
        coordinator,
        dog_id,
        dog_name,
        dog,
      ),
    )

    # Module-specific numbers
    if modules.get(MODULE_FEEDING, False):
      entities.extend(
        _create_feeding_numbers(
          coordinator,
          dog_id,
          dog_name,
        ),
      )

    if modules.get(MODULE_WALK, False):
      entities.extend(
        _create_walk_numbers(
          coordinator,
          dog_id,
          dog_name,
        ),
      )

    if modules.get(MODULE_GPS, False):
      entities.extend(_create_gps_numbers(coordinator, dog_id, dog_name))

    if modules.get(MODULE_HEALTH, False):
      entities.extend(
        _create_health_numbers(
          coordinator,
          dog_id,
          dog_name,
        ),
      )

  # Add entities in smaller batches to prevent Entity Registry overload
  # With 46+ number entities (2 dogs), batching prevents Registry flooding
  await _async_add_entities_in_batches(async_add_entities, entities, batch_size=12)

  _LOGGER.info(
    "Created %d number entities for %d dogs using batched approach",
    len(entities),
    len(dogs),
  )


async def async_reproduce_state(
  hass: HomeAssistant,
  states: Sequence[State],
  *,
  context: Context | None = None,
) -> None:
  """Reproduce number states for PawControl entities."""
  await async_reproduce_platform_states(
    hass,
    states,
    "number",
    _preprocess_number_state,
    _async_reproduce_number_state,
    context=context,
  )


def _preprocess_number_state(state: State) -> float | None:
  try:
    return float(state.state)
  except (TypeError, ValueError):
    _LOGGER.warning(
      "Invalid number state for %s: %s",
      state.entity_id,
      state.state,
    )
    return None


async def _async_reproduce_number_state(
  hass: HomeAssistant,
  state: State,
  current_state: State,
  target_value: float,
  context: Context | None,
) -> None:
  if current_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
    try:
      current_value = float(current_state.state)
    except (TypeError, ValueError):
      current_value = None
    else:
      if current_value == target_value:
        return

  await hass.services.async_call(
    number_component.DOMAIN,
    number_component.SERVICE_SET_VALUE,
    {ATTR_ENTITY_ID: state.entity_id, ATTR_VALUE: target_value},
    context=context,
    blocking=True,
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
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
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
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
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
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
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
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
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
    mode: NumberMode = DEFAULT_NUMBER_MODE,
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
      model=DEFAULT_MODEL,
      sw_version=DEFAULT_SW_VERSION,
    )

  async def async_added_to_hass(self) -> None:
    """Called when entity is added to Home Assistant.

    Restores the previous value and sets up any required listeners.
    """
    await super().async_added_to_hass()

    # Restore previous value
    last_state = await self.async_get_last_state()
    if last_state is not None and last_state.state not in (
      "unknown",
      "unavailable",
    ):
      try:
        self._value = float(last_state.state)
        _LOGGER.debug(
          "Restored number value for %s %s: %s",
          self._dog_name,
          self._number_type,
          self._value,
        )
      except (ValueError, TypeError):
        _LOGGER.warning(
          "Could not restore number value for %s %s: %s",
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
  def extra_state_attributes(self) -> JSONMutableMapping:
    """Return additional state attributes for the number.

    Provides information about the number's function and constraints.

    Returns:
        Dictionary of additional state attributes
    """
    attrs = self._build_base_state_attributes(
      {
        "number_type": self._number_type,
        "min_value": getattr(self, "_attr_native_min_value", None),
        "max_value": getattr(self, "_attr_native_max_value", None),
        "step": getattr(self, "_attr_native_step", None),
        "last_changed": dt_util.utcnow().isoformat(),
      },
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
        "Set %s for %s (%s) to %s",
        self._number_type,
        self._dog_name,
        self._dog_id,
        value,
      )

    except Exception as err:
      _LOGGER.error(
        "Failed to set %s for %s: %s",
        self._number_type,
        self._dog_name,
        err,
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

  def _get_dog_config_section(self, section: str) -> JSONMutableMapping:
    """Return a copy of the stored configuration section."""

    config = (
      self.coordinator.get_dog_config(self._dog_id)
      if hasattr(self.coordinator, "get_dog_config")
      else None
    )
    if not isinstance(config, Mapping):
      return {}

    section_data = config.get(section)
    if isinstance(section_data, Mapping):
      return dict(section_data)
    return {}

  async def _async_persist_config_update(
    self,
    updates: Mapping[str, JSONValue],
    *,
    section: str | None = None,
  ) -> None:
    """Persist configuration updates via the data manager when available."""

    data_manager = self._get_data_manager()
    if data_manager is None:
      return

    payload: Mapping[str, JSONValue | Mapping[str, JSONValue]]
    payload = updates if section is None else {section: updates}

    try:
      await data_manager.async_update_dog_data(self._dog_id, payload)
    except Exception as err:  # pragma: no cover - defensive log
      _LOGGER.warning(
        "Failed to persist %s update for %s: %s",
        self._number_type,
        self._dog_name,
        err,
      )

  async def _async_update_feeding_manager(
    self,
    updates: Mapping[str, JSONValue],
  ) -> None:
    """Push feeding configuration updates into the feeding manager."""

    feeding_manager = self._get_runtime_managers().feeding_manager
    if feeding_manager is None:
      return

    current = self._get_dog_config_section(DOG_FEEDING_CONFIG_FIELD)
    merged = _merge_config_updates(current, updates)
    try:
      await feeding_manager.async_update_config(self._dog_id, merged)
    except Exception as err:  # pragma: no cover - defensive log
      _LOGGER.warning(
        "Failed to apply feeding updates for %s: %s",
        self._dog_name,
        err,
      )

  async def _async_update_gps_manager(
    self,
    updates: Mapping[str, JSONValue],
  ) -> None:
    """Push GPS configuration updates into the GPS manager."""

    gps_manager = self._get_runtime_managers().gps_geofence_manager
    if gps_manager is None:
      return

    current = self._get_dog_config_section(DOG_GPS_CONFIG_FIELD)
    merged = _merge_config_updates(current, updates)
    tracking_input = _build_gps_tracking_input(merged)
    if not tracking_input:
      return

    try:
      await gps_manager.async_configure_dog_gps(
        self._dog_id,
        tracking_input,
      )
    except Exception as err:  # pragma: no cover - defensive log
      _LOGGER.warning(
        "Failed to apply GPS updates for %s: %s",
        self._dog_name,
        err,
      )

  async def _async_refresh_after_update(self) -> None:
    """Refresh coordinator data after a configuration update."""

    await self.coordinator.async_refresh_dog(self._dog_id)

  def _get_dog_data(self) -> CoordinatorDogData | None:
    """Get data for this number's dog from the coordinator."""

    return self._get_dog_data_cached()

  def _get_module_data(self, module: str) -> CoordinatorModuleLookupResult:
    """Get specific module data for this dog.

    Args:
        module: Module name to retrieve data for

    Returns:
        Module data dictionary or None if not available
    """
    return super()._get_module_data(module)

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
    dog_config: DogConfigData | None = None,
  ) -> None:
    """Initialize the dog weight number."""
    config: DogConfigData = cast(DogConfigData, dog_config or {})
    current_weight = cast(float | None, config.get(DOG_WEIGHT_FIELD))
    if current_weight is None:
      current_weight = 20.0

    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "weight",
      device_class=_WEIGHT_DEVICE_CLASS,
      mode=NumberMode.BOX,
      native_unit_of_measurement=MASS_KILOGRAMS,
      native_min_value=MIN_DOG_WEIGHT,
      native_max_value=MAX_DOG_WEIGHT,
      native_step=0.1,
      icon="mdi:scale",
      initial_value=current_weight,
      translation_key="weight",
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the dog's weight."""
    weight_value = float(value)

    dog_data = self._get_dog_data()
    if isinstance(dog_data, Mapping):
      dog_info = cast(
        DogConfigData,
        dog_data.setdefault("dog_info", cast(DogConfigData, {})),
      )
      dog_info[DOG_WEIGHT_FIELD] = weight_value

    await self._async_persist_config_update({DOG_WEIGHT_FIELD: weight_value})
    await self._async_refresh_after_update()

  @property
  def extra_state_attributes(self) -> JSONMutableMapping:
    """Return additional attributes for the weight number."""
    attrs = super().extra_state_attributes
    health_data = self._get_module_data("health")

    if isinstance(health_data, Mapping):
      weight_trend = health_data.get("weight_trend")
      if isinstance(weight_trend, str):
        attrs["weight_trend"] = weight_trend

      weight_change_percent = health_data.get("weight_change_percent")
      if isinstance(weight_change_percent, int | float):
        attrs["weight_change_percent"] = float(weight_change_percent)

      last_weight_date = health_data.get("last_weight_date")
      if isinstance(last_weight_date, str):
        attrs["last_weight_date"] = last_weight_date

      target_weight = health_data.get("target_weight")
      if isinstance(target_weight, int | float):
        attrs["target_weight"] = float(target_weight)

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
      "age",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfTime.YEARS,
      native_min_value=MIN_DOG_AGE,
      native_max_value=MAX_DOG_AGE,
      native_step=1,
      icon="mdi:calendar",
      entity_category=EntityCategory.CONFIG,
      initial_value=current_age,
      translation_key="age",
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the dog's age."""
    int_value = int(value)

    dog_data = self._get_dog_data()
    if isinstance(dog_data, Mapping):
      dog_info = cast(
        DogConfigData,
        dog_data.setdefault("dog_info", cast(DogConfigData, {})),
      )
      dog_info[DOG_AGE_FIELD] = int_value

    await self._async_persist_config_update({DOG_AGE_FIELD: int_value})
    await self._async_refresh_after_update()

    _LOGGER.info("Set age for %s to %s", self._dog_name, int_value)


class PawControlActivityGoalNumber(PawControlNumberBase):
  """Number entity for the dog's daily activity goal."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the activity goal number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "activity_goal",
      mode=NumberMode.SLIDER,
      native_unit_of_measurement=PERCENTAGE,
      native_min_value=50,
      native_max_value=200,
      native_step=5,
      icon="mdi:target",
      initial_value=DEFAULT_ACTIVITY_GOAL,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the activity goal."""
    int_value = int(value)
    await self._async_persist_config_update(
      {"activity_goal": int_value},
      section=DOG_HEALTH_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


# Feeding numbers
class PawControlDailyFoodAmountNumber(PawControlNumberBase):
  """Number entity for daily food amount in grams."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the daily food amount number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "daily_food_amount",
      mode=NumberMode.BOX,
      native_unit_of_measurement=MASS_GRAMS,
      native_min_value=50,
      native_max_value=2000,
      native_step=10,
      icon="mdi:food",
      initial_value=300,
      translation_key="daily_food_amount",
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the daily food amount."""
    amount = float(value)
    updates = {CONF_DAILY_FOOD_AMOUNT: amount}
    await self._async_persist_config_update(
      updates,
      section=DOG_FEEDING_CONFIG_FIELD,
    )
    await self._async_update_feeding_manager(updates)
    await self._async_refresh_after_update()

  @property
  def extra_state_attributes(self) -> JSONMutableMapping:
    """Return additional attributes for daily food amount."""
    attrs = super().extra_state_attributes

    # Calculate recommended amount based on dog size/weight
    dog_data = self._get_dog_data()
    if dog_data and "dog_info" in dog_data:
      info = dog_data["dog_info"]
      weight_value = info.get("dog_weight")
      weight = float(weight_value) if isinstance(weight_value, int | float) else 20.0
      recommended = self._calculate_recommended_amount(weight)
      attrs["recommended_amount"] = recommended
      current_value = self.native_value
      if current_value is None or recommended <= 0:
        attrs["current_vs_recommended"] = "N/A"
      else:
        attrs["current_vs_recommended"] = f"{(current_value / recommended * 100):.0f}%"

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
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the feeding reminder hours number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "feeding_reminder_hours",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfTime.HOURS,
      native_min_value=2,
      native_max_value=24,
      native_step=1,
      icon="mdi:clock-alert",
      initial_value=DEFAULT_FEEDING_REMINDER_HOURS,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the feeding reminder hours."""
    int_value = int(value)
    updates = {"reminder_hours": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_FEEDING_CONFIG_FIELD,
    )
    await self._async_update_feeding_manager(updates)
    await self._async_refresh_after_update()


class PawControlMealsPerDayNumber(PawControlNumberBase):
  """Number entity for number of meals per day."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the meals per day number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "meals_per_day",
      mode=NumberMode.BOX,
      native_min_value=1,
      native_max_value=6,
      native_step=1,
      icon="mdi:numeric",
      initial_value=2,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the meals per day."""
    int_value = int(value)
    updates = {CONF_MEALS_PER_DAY: int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_FEEDING_CONFIG_FIELD,
    )
    await self._async_update_feeding_manager(updates)
    await self._async_refresh_after_update()


class PawControlPortionSizeNumber(PawControlNumberBase):
  """Number entity for default portion size in grams."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the portion size number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "portion_size",
      mode=NumberMode.BOX,
      native_unit_of_measurement=MASS_GRAMS,
      native_min_value=10,
      native_max_value=500,
      native_step=5,
      icon="mdi:food-variant",
      initial_value=150,
      translation_key="portion_size",
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the portion size."""
    portion_size = float(value)
    updates = {"portion_size": portion_size}
    await self._async_persist_config_update(
      updates,
      section=DOG_FEEDING_CONFIG_FIELD,
    )
    await self._async_update_feeding_manager(updates)
    await self._async_refresh_after_update()


class PawControlCalorieTargetNumber(PawControlNumberBase):
  """Number entity for daily calorie target."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the calorie target number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "calorie_target",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
      native_min_value=200,
      native_max_value=3000,
      native_step=50,
      icon="mdi:fire",
      initial_value=800,
      translation_key="calorie_target",
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the calorie target."""
    int_value = int(value)
    updates = {"calorie_target": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_FEEDING_CONFIG_FIELD,
    )
    await self._async_update_feeding_manager(updates)
    await self._async_refresh_after_update()


# Walk numbers
class PawControlDailyWalkTargetNumber(PawControlNumberBase):
  """Number entity for daily walk target count."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the daily walk target number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "daily_walk_target",
      mode=NumberMode.BOX,
      native_min_value=1,
      native_max_value=10,
      native_step=1,
      icon="mdi:walk",
      initial_value=3,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the daily walk target."""
    int_value = int(value)
    updates = {"daily_walk_target": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_WALK_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


class PawControlWalkDurationTargetNumber(PawControlNumberBase):
  """Number entity for walk duration target in minutes."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the walk duration target number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "walk_duration_target",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfTime.MINUTES,
      native_min_value=10,
      native_max_value=180,
      native_step=5,
      icon="mdi:timer",
      initial_value=DEFAULT_WALK_DURATION_TARGET,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the walk duration target."""
    int_value = int(value)
    updates = {"walk_duration_target": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_WALK_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


class PawControlWalkDistanceTargetNumber(PawControlNumberBase):
  """Number entity for walk distance target in meters."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the walk distance target number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "walk_distance_target",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfLength.METERS,
      native_min_value=100,
      native_max_value=10000,
      native_step=100,
      icon="mdi:map-marker-distance",
      initial_value=2000,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the walk distance target."""
    int_value = int(value)
    updates = {"walk_distance_target": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_WALK_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


class PawControlWalkReminderHoursNumber(PawControlNumberBase):
  """Number entity for walk reminder interval in hours."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the walk reminder hours number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "walk_reminder_hours",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfTime.HOURS,
      native_min_value=2,
      native_max_value=24,
      native_step=1,
      icon="mdi:clock-alert",
      initial_value=8,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the walk reminder hours."""
    int_value = int(value)
    updates = {"reminder_hours": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_WALK_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


class PawControlMaxWalkSpeedNumber(PawControlNumberBase):
  """Number entity for maximum expected walk speed."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the max walk speed number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "max_walk_speed",
      mode=NumberMode.BOX,
      native_unit_of_measurement=getattr(
        UnitOfSpeed,
        "KILOMETERS_PER_HOUR",
        "km/h",
      ),
      native_min_value=2,
      native_max_value=30,
      native_step=1,
      icon="mdi:speedometer",
      initial_value=15,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the max walk speed."""
    int_value = int(value)
    updates = {"max_walk_speed": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_WALK_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


# GPS numbers
class PawControlGPSAccuracyThresholdNumber(PawControlNumberBase):
  """Number entity for GPS accuracy threshold in meters."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the GPS accuracy threshold number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "gps_accuracy_threshold",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfLength.METERS,
      native_min_value=5,
      native_max_value=500,
      native_step=5,
      icon="mdi:crosshairs-gps",
      entity_category=EntityCategory.CONFIG,
      initial_value=DEFAULT_GPS_ACCURACY_THRESHOLD,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the GPS accuracy threshold."""
    accuracy_value = float(value)
    updates = {CONF_GPS_ACCURACY_FILTER: accuracy_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_GPS_CONFIG_FIELD,
    )
    await self._async_update_gps_manager(updates)
    await self._async_refresh_after_update()


class PawControlGPSUpdateIntervalNumber(PawControlNumberBase):
  """Number entity for GPS update interval in seconds."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the GPS update interval number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "gps_update_interval",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfTime.SECONDS,
      native_min_value=30,
      native_max_value=600,
      native_step=30,
      icon="mdi:update",
      entity_category=EntityCategory.CONFIG,
      initial_value=60,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the GPS update interval."""
    interval = int(value)
    updates = {CONF_GPS_UPDATE_INTERVAL: interval}
    await self._async_persist_config_update(
      updates,
      section=DOG_GPS_CONFIG_FIELD,
    )
    await self._async_update_gps_manager(updates)
    await self._async_refresh_after_update()


class PawControlGeofenceRadiusNumber(PawControlNumberBase):
  """Number entity for geofence radius in meters."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the geofence radius number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "geofence_radius",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfLength.METERS,
      native_min_value=10,
      native_max_value=1000,
      native_step=10,
      icon="mdi:map-marker-circle",
      initial_value=100,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the geofence radius."""
    radius = float(value)
    updates = {CONF_HOME_ZONE_RADIUS: radius}
    await self._async_persist_config_update(
      updates,
      section=DOG_GPS_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


class PawControlLocationUpdateDistanceNumber(PawControlNumberBase):
  """Number entity for minimum distance for location updates."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the location update distance number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "location_update_distance",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfLength.METERS,
      native_min_value=1,
      native_max_value=100,
      native_step=1,
      icon="mdi:map-marker-path",
      entity_category=EntityCategory.CONFIG,
      initial_value=10,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the location update distance."""
    distance = float(value)
    updates = {CONF_GPS_DISTANCE_FILTER: distance}
    await self._async_persist_config_update(
      updates,
      section=DOG_GPS_CONFIG_FIELD,
    )
    await self._async_update_gps_manager(updates)
    await self._async_refresh_after_update()


class PawControlGPSBatteryThresholdNumber(PawControlNumberBase):
  """Number entity for GPS battery alert threshold."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the GPS battery threshold number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "gps_battery_threshold",
      mode=NumberMode.SLIDER,
      native_unit_of_measurement=PERCENTAGE,
      native_min_value=5,
      native_max_value=50,
      native_step=5,
      icon="mdi:battery-alert",
      initial_value=20,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the GPS battery threshold."""
    int_value = int(value)
    updates = {"gps_battery_threshold": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_GPS_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


# Health numbers
class PawControlTargetWeightNumber(PawControlNumberBase):
  """Number entity for target weight in kg."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the target weight number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "target_weight",
      device_class=_WEIGHT_DEVICE_CLASS,
      mode=NumberMode.BOX,
      native_unit_of_measurement=MASS_KILOGRAMS,
      native_min_value=MIN_DOG_WEIGHT,
      native_max_value=MAX_DOG_WEIGHT,
      native_step=0.1,
      icon="mdi:target",
      initial_value=20.0,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the target weight."""
    weight_value = float(value)
    updates = {"target_weight": weight_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_HEALTH_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


class PawControlWeightChangeThresholdNumber(PawControlNumberBase):
  """Number entity for weight change alert threshold."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the weight change threshold number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "weight_change_threshold",
      mode=NumberMode.SLIDER,
      native_unit_of_measurement=PERCENTAGE,
      native_min_value=5,
      native_max_value=25,
      native_step=1,
      icon="mdi:scale-unbalanced",
      initial_value=10,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the weight change threshold."""
    int_value = int(value)
    updates = {"weight_change_threshold": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_HEALTH_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


class PawControlGroomingIntervalNumber(PawControlNumberBase):
  """Number entity for grooming interval in days."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the grooming interval number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "grooming_interval",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfTime.DAYS,
      native_min_value=7,
      native_max_value=90,
      native_step=7,
      icon="mdi:content-cut",
      initial_value=28,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the grooming interval."""
    int_value = int(value)
    updates = {CONF_GROOMING_INTERVAL: int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_HEALTH_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


class PawControlVetCheckupIntervalNumber(PawControlNumberBase):
  """Number entity for vet checkup interval in months."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the vet checkup interval number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "vet_checkup_interval",
      mode=NumberMode.BOX,
      native_unit_of_measurement=UnitOfTime.MONTHS,
      native_min_value=3,
      native_max_value=24,
      native_step=3,
      icon="mdi:medical-bag",
      initial_value=12,
      translation_key="vet_checkup_interval",
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the vet checkup interval."""
    int_value = int(value)
    updates = {"vet_checkup_interval": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_HEALTH_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()


class PawControlHealthScoreThresholdNumber(PawControlNumberBase):
  """Number entity for health score alert threshold."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the health score threshold number."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "health_score_threshold",
      mode=NumberMode.SLIDER,
      native_unit_of_measurement=PERCENTAGE,
      native_min_value=30,
      native_max_value=90,
      native_step=5,
      icon="mdi:heart-pulse",
      initial_value=70,
    )

  async def _async_set_number_value(self, value: float) -> None:
    """Set the health score threshold."""
    int_value = int(value)
    updates = {"health_score_threshold": int_value}
    await self._async_persist_config_update(
      updates,
      section=DOG_HEALTH_CONFIG_FIELD,
    )
    await self._async_refresh_after_update()
