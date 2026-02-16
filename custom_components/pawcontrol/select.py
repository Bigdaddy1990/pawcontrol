"""Select platform for Paw Control integration.

This module provides comprehensive select entities for dog monitoring configuration
including mode selections, option choices, and status settings. All select entities
are designed to meet Home Assistant's Platinum quality ambitions with full type
annotations, async operations, and robust validation.
"""

import asyncio
from collections.abc import Mapping, Sequence
import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from homeassistant.components import select as select_component
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

ATTR_OPTION = getattr(select_component, "ATTR_OPTION", "option")
ATTR_OPTIONS = getattr(select_component, "ATTR_OPTIONS", "options")

try:
  from homeassistant.const import ATTR_ENTITY_ID  # noqa: E111
except ImportError:  # pragma: no cover
  ATTR_ENTITY_ID = "entity_id"  # noqa: E111

from homeassistant.exceptions import HomeAssistantError  # noqa: E402

from .const import (  # noqa: E402
  ACTIVITY_LEVELS,
  DEFAULT_MODEL,
  DEFAULT_PERFORMANCE_MODE,
  DEFAULT_SW_VERSION,
  DOG_SIZES,
  FOOD_TYPES,
  GPS_SOURCES,
  HEALTH_STATUS_OPTIONS,
  MEAL_TYPES,
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_WALK,
  MOOD_OPTIONS,
  PERFORMANCE_MODES,
)
from .coordinator import PawControlCoordinator  # noqa: E402
from .entity import PawControlDogEntityBase  # noqa: E402
from .notifications import (  # noqa: E402
  NotificationPriority,
  PawControlNotificationManager,
)
from .reproduce_state import async_reproduce_platform_states  # noqa: E402
from .runtime_data import get_runtime_data  # noqa: E402
from .types import (  # noqa: E402
  DOG_ID_FIELD,
  DOG_MODULES_FIELD,
  DOG_NAME_FIELD,
  DOG_SIZE_FIELD,
  ActivityLevelKey,
  CoordinatorDogData,
  CoordinatorModuleLookupResult,
  DogConfigData,
  DogSizeInfo,
  DogSizeKey,
  FeedingScheduleKey,
  FoodTypeInfo,
  FoodTypeKey,
  GPSSourceInfo,
  GPSSourceKey,
  GPSTrackingConfigInput,
  GroomingTypeInfo,
  GroomingTypeKey,
  HealthStatusKey,
  JSONMapping,
  JSONMutableMapping,
  JSONValue,
  LocationAccuracyConfig,
  LocationAccuracyKey,
  MealTypeKey,
  MoodKey,
  NotificationPriorityKey,
  PawControlConfigEntry,
  PawControlRuntimeData,
  PerformanceModeInfo,
  PerformanceModeKey,
  TrackingModeKey,
  TrackingModePreset,
  WalkModeInfo,
  WalkModeKey,
  WeatherConditionKey,
  coerce_dog_modules_config,
)
from .utils import (  # noqa: E402
  async_call_add_entities,
  deep_merge_dicts,
  normalise_entity_attributes,
)

if TYPE_CHECKING:
  from .data_manager import PawControlDataManager  # noqa: E111

_LOGGER = logging.getLogger(__name__)

# Select entities invoke coordinator-backed actions. The coordinator is
# responsible for serialising writes, so we allow unlimited parallel updates at
# the entity layer.
PARALLEL_UPDATES = 0


def _normalise_attributes(attrs: Mapping[str, object]) -> JSONMutableMapping:
  """Return JSON-serialisable attributes for select entities."""  # noqa: E111

  return normalise_entity_attributes(attrs)  # noqa: E111


# Additional option lists for selects
WALK_MODES: list[WalkModeKey] = [
  "automatic",
  "manual",
  "hybrid",
]

NOTIFICATION_PRIORITIES: list[NotificationPriorityKey] = [
  "low",
  "normal",
  "high",
  "urgent",
]

TRACKING_MODES: list[TrackingModeKey] = [
  "continuous",
  "interval",
  "on_demand",
  "battery_saver",
]

LOCATION_ACCURACY_OPTIONS: list[LocationAccuracyKey] = [
  "low",
  "balanced",
  "high",
  "best",
]

TRACKING_MODE_PRESETS: Final[Mapping[str, TrackingModePreset]] = MappingProxyType(
  {
    "continuous": {
      "update_interval_seconds": 15,
      "auto_start_walk": True,
      "track_route": True,
    },
    "interval": {
      "update_interval_seconds": 60,
      "auto_start_walk": True,
      "track_route": True,
    },
    "on_demand": {
      "update_interval_seconds": 300,
      "auto_start_walk": False,
      "track_route": False,
    },
    "battery_saver": {
      "update_interval_seconds": 180,
      "auto_start_walk": True,
      "route_smoothing": True,
    },
  },
)

LOCATION_ACCURACY_CONFIGS: Final[Mapping[str, LocationAccuracyConfig]] = (
  MappingProxyType(
    {
      "low": {
        "gps_accuracy_threshold": 150.0,
        "min_distance_for_point": 50.0,
      },
      "balanced": {
        "gps_accuracy_threshold": 75.0,
        "min_distance_for_point": 25.0,
      },
      "high": {
        "gps_accuracy_threshold": 30.0,
        "min_distance_for_point": 10.0,
      },
      "best": {
        "gps_accuracy_threshold": 10.0,
        "min_distance_for_point": 5.0,
        "route_smoothing": False,
      },
    },
  )
)

FEEDING_SCHEDULES: list[FeedingScheduleKey] = [
  "flexible",
  "strict",
  "custom",
]

GROOMING_TYPES: list[GroomingTypeKey] = [
  "bath",
  "brush",
  "nails",
  "teeth",
  "trim",
  "full_grooming",
]

WEATHER_CONDITIONS: list[WeatherConditionKey] = [
  "any",
  "sunny",
  "cloudy",
  "light_rain",
  "no_rain",
  "warm",
  "cool",
]

DOG_SIZE_OPTIONS: list[DogSizeKey] = [cast(DogSizeKey, value) for value in DOG_SIZES]
PERFORMANCE_MODE_OPTIONS: list[PerformanceModeKey] = [
  cast(PerformanceModeKey, value) for value in PERFORMANCE_MODES
]
FOOD_TYPE_OPTIONS: list[FoodTypeKey] = [
  cast(FoodTypeKey, value) for value in FOOD_TYPES
]
GPS_SOURCE_OPTIONS: list[GPSSourceKey] = [
  cast(GPSSourceKey, value) for value in GPS_SOURCES
]
HEALTH_STATUS_OPTION_KEYS: list[HealthStatusKey] = [
  cast(HealthStatusKey, value) for value in HEALTH_STATUS_OPTIONS
]
ACTIVITY_LEVEL_OPTIONS: list[ActivityLevelKey] = [
  cast(ActivityLevelKey, value) for value in ACTIVITY_LEVELS
]
MEAL_TYPE_OPTIONS: list[MealTypeKey] = [
  cast(MealTypeKey, value) for value in MEAL_TYPES
]
MOOD_OPTIONS_KEYS: list[MoodKey] = [cast(MoodKey, value) for value in MOOD_OPTIONS]


DOG_SIZE_DETAILS: Final[Mapping[str, DogSizeInfo]] = MappingProxyType(
  {
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
  },
)

PERFORMANCE_MODE_DETAILS: Final[Mapping[str, PerformanceModeInfo]] = MappingProxyType(
  {
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
  },
)

WALK_MODE_DETAILS: Final[Mapping[str, WalkModeInfo]] = MappingProxyType(
  {
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
  },
)

FOOD_TYPE_DETAILS: Final[Mapping[str, FoodTypeInfo]] = MappingProxyType(
  {
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
  },
)

GPS_SOURCE_DETAILS: Final[Mapping[str, GPSSourceInfo]] = MappingProxyType(
  {
    "manual": {
      "accuracy": "user-dependent",
      "update_frequency": "manual",
      "battery_usage": "none",
    },
    "device_tracker": {
      "accuracy": "high",
      "update_frequency": "automatic",
      "battery_usage": "low",
    },
    "person_entity": {
      "accuracy": "device-dependent",
      "update_frequency": "automatic",
      "battery_usage": "low",
    },
    "gps_logger": {
      "accuracy": "medium",
      "update_frequency": "15 minutes",
      "battery_usage": "medium",
    },
    "ble_beacon": {
      "accuracy": "near proximity",
      "update_frequency": "on demand",
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
  },
)

GROOMING_TYPE_DETAILS: Final[Mapping[str, GroomingTypeInfo]] = MappingProxyType(
  {
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
  },
)


def _merge_json_mappings(
  base: Mapping[str, JSONValue] | None,
  updates: Mapping[str, JSONValue],
) -> JSONMutableMapping:
  """Return a JSON-compatible mapping that merges base and updates."""  # noqa: E111

  base_payload: dict[str, JSONValue] = dict(base) if base is not None else {}  # noqa: E111
  merged = deep_merge_dicts(base_payload, dict(updates))  # noqa: E111
  return cast(JSONMutableMapping, merged)  # noqa: E111


async def _async_add_entities_in_batches(
  async_add_entities_func: AddEntitiesCallback,
  entities: Sequence[PawControlSelectBase],
  *,
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
  """  # noqa: E111
  total_entities = len(entities)  # noqa: E111

  _LOGGER.debug(  # noqa: E111
    "Adding %d select entities in batches of %d to prevent Registry overload",
    total_entities,
    batch_size,
  )

  # Process entities in batches  # noqa: E114
  for i in range(0, total_entities, batch_size):  # noqa: E111
    batch = entities[i : i + batch_size]
    batch_num = (i // batch_size) + 1
    total_batches = (total_entities + batch_size - 1) // batch_size

    _LOGGER.debug(
      "Processing select batch %d/%d with %d entities",
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
      await asyncio.sleep(delay_between_batches)  # noqa: E111


async def async_setup_entry(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
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
  """  # noqa: E111
  runtime_data = get_runtime_data(hass, entry)  # noqa: E111
  if runtime_data is None:  # noqa: E111
    _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
    return

  coordinator: PawControlCoordinator = runtime_data.coordinator  # noqa: E111
  dogs: list[DogConfigData] = runtime_data.dogs  # noqa: E111

  entities: list[PawControlSelectBase] = []  # noqa: E111

  # Create select entities for each configured dog  # noqa: E114
  for dog in dogs:  # noqa: E111
    dog_id = dog[DOG_ID_FIELD]
    dog_name = dog[DOG_NAME_FIELD]
    modules = coerce_dog_modules_config(dog.get(DOG_MODULES_FIELD))

    _LOGGER.debug(
      "Creating select entities for dog: %s (%s)",
      dog_name,
      dog_id,
    )

    # Base selects - always created for every dog
    entities.extend(
      _create_base_selects(
        coordinator,
        dog_id,
        dog_name,
        dog,
      ),
    )

    # Module-specific selects
    if modules.get(MODULE_FEEDING, False):
      entities.extend(  # noqa: E111
        _create_feeding_selects(
          coordinator,
          dog_id,
          dog_name,
        ),
      )

    if modules.get(MODULE_WALK, False):
      entities.extend(  # noqa: E111
        _create_walk_selects(
          coordinator,
          dog_id,
          dog_name,
        ),
      )

    if modules.get(MODULE_GPS, False):
      entities.extend(_create_gps_selects(coordinator, dog_id, dog_name))  # noqa: E111

    if modules.get(MODULE_HEALTH, False):
      entities.extend(  # noqa: E111
        _create_health_selects(
          coordinator,
          dog_id,
          dog_name,
        ),
      )

  # Add entities in smaller batches to prevent Entity Registry overload  # noqa: E114
  # With 32+ select entities (2 dogs), batching prevents Registry flooding  # noqa: E114
  await _async_add_entities_in_batches(async_add_entities, entities, batch_size=10)  # noqa: E111

  _LOGGER.info(  # noqa: E111
    "Created %d select entities for %d dogs using batched approach",
    len(entities),
    len(dogs),
  )


async def async_reproduce_state(
  hass: HomeAssistant,
  states: Sequence[State],
  *,
  context: Context | None = None,
) -> None:
  """Reproduce select states for PawControl entities."""  # noqa: E111
  await async_reproduce_platform_states(  # noqa: E111
    hass,
    states,
    "select",
    _preprocess_select_state,
    _async_reproduce_select_state,
    context=context,
  )


def _preprocess_select_state(state: State) -> str:
  return state.state  # noqa: E111


async def _async_reproduce_select_state(
  hass: HomeAssistant,
  state: State,
  current_state: State,
  target_option: str,
  context: Context | None,
) -> None:
  if current_state.state == target_option:  # noqa: E111
    return

  options = current_state.attributes.get(ATTR_OPTIONS, [])  # noqa: E111
  if options and target_option not in options:  # noqa: E111
    _LOGGER.warning(
      "Invalid select option for %s: %s",
      state.entity_id,
      target_option,
    )
    return

  await hass.services.async_call(  # noqa: E111
    select_component.DOMAIN,
    select_component.SERVICE_SELECT_OPTION,
    {ATTR_ENTITY_ID: state.entity_id, ATTR_OPTION: target_option},
    context=context,
    blocking=True,
  )


def _create_base_selects(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
  dog_config: DogConfigData,
) -> list[PawControlSelectBase]:
  """Create base selects that are always present for every dog.

  Args:
      coordinator: Data coordinator instance
      dog_id: Unique identifier for the dog
      dog_name: Display name for the dog
      dog_config: Dog configuration data

  Returns:
      List of base select entities
  """  # noqa: E111
  return [  # noqa: E111
    PawControlDogSizeSelect(coordinator, dog_id, dog_name, dog_config),
    PawControlPerformanceModeSelect(coordinator, dog_id, dog_name),
    PawControlNotificationPrioritySelect(coordinator, dog_id, dog_name),
  ]


def _create_feeding_selects(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlSelectBase]:
  """Create feeding-related selects for a dog.

  Args:
      coordinator: Data coordinator instance
      dog_id: Unique identifier for the dog
      dog_name: Display name for the dog

  Returns:
      List of feeding select entities
  """  # noqa: E111
  return [  # noqa: E111
    PawControlFoodTypeSelect(coordinator, dog_id, dog_name),
    PawControlFeedingScheduleSelect(coordinator, dog_id, dog_name),
    PawControlDefaultMealTypeSelect(coordinator, dog_id, dog_name),
    PawControlFeedingModeSelect(coordinator, dog_id, dog_name),
  ]


def _create_walk_selects(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlSelectBase]:
  """Create walk-related selects for a dog.

  Args:
      coordinator: Data coordinator instance
      dog_id: Unique identifier for the dog
      dog_name: Display name for the dog

  Returns:
      List of walk select entities
  """  # noqa: E111
  return [  # noqa: E111
    PawControlWalkModeSelect(coordinator, dog_id, dog_name),
    PawControlWeatherPreferenceSelect(coordinator, dog_id, dog_name),
    PawControlWalkIntensitySelect(coordinator, dog_id, dog_name),
  ]


def _create_gps_selects(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlSelectBase]:
  """Create GPS and location-related selects for a dog.

  Args:
      coordinator: Data coordinator instance
      dog_id: Unique identifier for the dog
      dog_name: Display name for the dog

  Returns:
      List of GPS select entities
  """  # noqa: E111
  return [  # noqa: E111
    PawControlGPSSourceSelect(coordinator, dog_id, dog_name),
    PawControlTrackingModeSelect(coordinator, dog_id, dog_name),
    PawControlLocationAccuracySelect(coordinator, dog_id, dog_name),
  ]


def _create_health_selects(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlSelectBase]:
  """Create health and medical-related selects for a dog.

  Args:
      coordinator: Data coordinator instance
      dog_id: Unique identifier for the dog
      dog_name: Display name for the dog

  Returns:
      List of health select entities
  """  # noqa: E111
  return [  # noqa: E111
    PawControlHealthStatusSelect(coordinator, dog_id, dog_name),
    PawControlActivityLevelSelect(coordinator, dog_id, dog_name),
    PawControlMoodSelect(coordinator, dog_id, dog_name),
    PawControlGroomingTypeSelect(coordinator, dog_id, dog_name),
  ]


class PawControlSelectBase(PawControlDogEntityBase, SelectEntity, RestoreEntity):
  """Base class for all Paw Control select entities.

  Provides common functionality and ensures consistent behavior across
  all select types. Includes proper device grouping, state persistence,
  validation, and error handling.
  """  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    select_type: str,
    *,
    options: Sequence[str],
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
    super().__init__(coordinator, dog_id, dog_name)
    self._select_type = select_type
    self._current_option = initial_option

    # Entity configuration
    self._attr_unique_id = f"pawcontrol_{dog_id}_{select_type}"
    self._attr_translation_key = select_type
    self._attr_options = list(options)
    self._attr_icon = icon
    self._attr_entity_category = entity_category
    self.entity_description = SelectEntityDescription(
      key=select_type,
      translation_key=select_type,
      entity_category=entity_category,
      icon=icon,
    )

    # Link entity to PawControl device entry for the dog
    self.update_device_metadata(
      model=DEFAULT_MODEL,
      sw_version=DEFAULT_SW_VERSION,
    )

  def _get_runtime_data(self) -> PawControlRuntimeData | None:  # noqa: E111
    """Return runtime data associated with the config entry."""

    if self.hass is None:
      return None  # noqa: E111

    return get_runtime_data(self.hass, self.coordinator.config_entry)

  def _get_domain_entry_data(self) -> JSONMutableMapping:  # noqa: E111
    """Return the hass.data payload for this config entry."""

    runtime_data = self._get_runtime_data()
    if runtime_data is not None:
      return cast(JSONMutableMapping, runtime_data.as_dict())  # noqa: E111

    return {}

  def _get_data_manager(self) -> PawControlDataManager | None:  # noqa: E111
    """Return the data manager for persistence if available."""

    runtime_data = self._get_runtime_data()
    if runtime_data is not None:
      direct_manager = getattr(runtime_data, "data_manager", None)  # noqa: E111
      if direct_manager is not None:  # noqa: E111
        return direct_manager

      manager_container = getattr(runtime_data, "runtime_managers", None)  # noqa: E111
      if manager_container is not None:  # noqa: E111
        return getattr(manager_container, "data_manager", None)

    entry_data = self._get_domain_entry_data()
    managers = entry_data.get("runtime_managers")
    if managers is None:
      return None  # noqa: E111

    manager_obj = getattr(managers, "data_manager", None)
    if manager_obj is not None:
      return cast(PawControlDataManager | None, manager_obj)  # noqa: E111

    if isinstance(managers, Mapping):
      candidate = managers.get("data_manager")  # noqa: E111
      if candidate is not None:  # noqa: E111
        return cast(PawControlDataManager | None, candidate)

    return None

  def _get_current_gps_config(self) -> JSONMutableMapping:  # noqa: E111
    """Return the currently stored GPS configuration."""

    dog_data = self._get_dog_data()
    if dog_data is None:
      return cast(JSONMutableMapping, {})  # noqa: E111

    gps_data = dog_data.get("gps")
    if isinstance(gps_data, Mapping):
      config = gps_data.get("config")  # noqa: E111
      if isinstance(config, Mapping):  # noqa: E111
        return cast(JSONMutableMapping, dict(config))

    return cast(JSONMutableMapping, {})

  async def _async_update_module_settings(  # noqa: E111
    self,
    module: str,
    updates: JSONMutableMapping,
  ) -> None:
    """Persist updates for a module and refresh coordinator data."""

    data_manager = self._get_data_manager()
    if data_manager:
      try:  # noqa: E111
        await data_manager.async_update_dog_data(
          self._dog_id,
          {module: updates},
        )
      except Exception as err:  # pragma: no cover - defensive log  # noqa: E111
        _LOGGER.warning(
          "Failed to persist %s updates for %s: %s",
          module,
          self._dog_name,
          err,
        )
    await self.coordinator.async_apply_module_updates(
      self._dog_id,
      module,
      updates,
    )

  async def _async_update_gps_settings(  # noqa: E111
    self,
    *,
    state_updates: JSONMutableMapping | None = None,
    config_updates: JSONMutableMapping | None = None,
  ) -> None:
    """Update stored GPS settings and apply them to the GPS manager."""

    gps_updates: JSONMutableMapping = {}
    merged_config: JSONMutableMapping | None = None

    if state_updates:
      gps_updates.update(state_updates)  # noqa: E111

    if config_updates:
      current_config = self._get_current_gps_config()  # noqa: E111
      merged_config = _merge_json_mappings(  # noqa: E111
        current_config,
        config_updates,
      )
      gps_updates.setdefault("config", merged_config)  # noqa: E111

    if gps_updates:
      await self._async_update_module_settings("gps", gps_updates)  # noqa: E111

    if merged_config:
      runtime_data = self._get_runtime_data()  # noqa: E111
      gps_manager = (  # noqa: E111
        getattr(runtime_data, "gps_geofence_manager", None) if runtime_data else None
      )
      if gps_manager:  # noqa: E111
        try:
          await gps_manager.async_configure_dog_gps(  # noqa: E111
            self._dog_id,
            cast(GPSTrackingConfigInput, dict(merged_config)),
          )
        except Exception as err:  # pragma: no cover - defensive log
          _LOGGER.warning(  # noqa: E111
            "Failed to apply GPS configuration for %s: %s",
            self._dog_name,
            err,
          )

  async def async_added_to_hass(self) -> None:  # noqa: E111
    """Called when entity is added to Home Assistant.

    Restores the previous option and sets up any required listeners.
    """
    await super().async_added_to_hass()

    # Restore previous option
    last_state = await self.async_get_last_state()
    if last_state is not None and last_state.state in self.options:
      self._current_option = last_state.state  # noqa: E111
      _LOGGER.debug(  # noqa: E111
        "Restored select option for %s %s: %s",
        self._dog_name,
        self._select_type,
        self._current_option,
      )

  @property  # noqa: E111
  def current_option(self) -> str | None:  # noqa: E111
    """Return the current selected option.

    Returns:
        Currently selected option
    """
    return self._current_option

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional state attributes for the select.

    Provides information about the select's function and available options.

    Returns:
        Dictionary of additional state attributes
    """
    attrs = self._build_base_state_attributes(
      {
        "select_type": self._select_type,
        "available_options": list(getattr(self, "_attr_options", [])),
        "last_changed": dt_util.utcnow().isoformat(),
      },
    )

    return _normalise_attributes(attrs)

  async def async_select_option(self, option: str) -> None:  # noqa: E111
    """Select an option.

    Args:
        option: Option to select

    Raises:
        HomeAssistantError: If option is invalid or cannot be set
    """
    if option not in self.options:
      raise HomeAssistantError(  # noqa: E111
        f"Invalid option '{option}' for {self._select_type}",
      )

    try:
      await self._async_set_select_option(option)  # noqa: E111
      self._current_option = option  # noqa: E111
      self.async_write_ha_state()  # noqa: E111

      _LOGGER.info(  # noqa: E111
        "Set %s for %s (%s) to '%s'",
        self._select_type,
        self._dog_name,
        self._dog_id,
        option,
      )

    except Exception as err:
      _LOGGER.error(  # noqa: E111
        "Failed to set %s for %s: %s",
        self._select_type,
        self._dog_name,
        err,
      )
      raise HomeAssistantError(  # noqa: E111
        f"Failed to set {self._select_type}",
      ) from err

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the select option implementation.

    This method should be overridden by subclasses to implement
    specific select functionality.

    Args:
        option: Option to set
    """
    # Base implementation - subclasses should override
    pass

  def _get_dog_data(self) -> CoordinatorDogData | None:  # noqa: E111
    """Get data for this select's dog from the coordinator."""

    return self._get_dog_data_cached()

  def _get_module_data(self, module: str) -> CoordinatorModuleLookupResult:  # noqa: E111
    """Get specific module data for this dog.

    Args:
        module: Module name to retrieve data for

    Returns:
        Module data dictionary or None if not available
    """
    return super()._get_module_data(module)

  @property  # noqa: E111
  def available(self) -> bool:  # noqa: E111
    """Return if the select is available.

    A select is available when the coordinator is available and
    the dog data can be retrieved.

    Returns:
        True if select is available, False otherwise
    """
    return self.coordinator.available and self._get_dog_data() is not None


# Base selects
class PawControlDogSizeSelect(PawControlSelectBase):
  """Select entity for the dog's size category."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    dog_config: DogConfigData | None = None,
  ) -> None:
    """Initialize the dog size select."""
    config: DogConfigData = cast(DogConfigData, dog_config or {})
    current_size = config.get(DOG_SIZE_FIELD, "medium")

    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "size",
      options=DOG_SIZE_OPTIONS,
      icon="mdi:dog",
      entity_category=EntityCategory.CONFIG,
      initial_option=current_size,
    )

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the dog's size."""
    # This would update the dog's size in the configuration
    # and trigger size-related calculations
    await self.coordinator.async_refresh_dog(self._dog_id)

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional attributes for the size select."""
    attrs = super().extra_state_attributes

    size_info = self._get_size_info(self.current_option)
    attrs.update(cast(JSONMapping, size_info))

    return _normalise_attributes(attrs)

  def _get_size_info(self, size: str | None) -> DogSizeInfo:  # noqa: E111
    """Get information about the selected size.

    Args:
        size: Selected size category

    Returns:
        Size information dictionary
    """
    if size is None:
      return cast(DogSizeInfo, {})  # noqa: E111

    info = DOG_SIZE_DETAILS.get(size)
    if info is None:
      return cast(DogSizeInfo, {})  # noqa: E111

    return cast(DogSizeInfo, dict(info))


class PawControlPerformanceModeSelect(PawControlSelectBase):
  """Select entity for system performance mode."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the performance mode select."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "performance_mode",
      options=PERFORMANCE_MODE_OPTIONS,
      icon="mdi:speedometer",
      entity_category=EntityCategory.CONFIG,
      initial_option=DEFAULT_PERFORMANCE_MODE,
    )

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the performance mode."""
    # This would update system performance settings
    pass

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional attributes for performance mode."""
    attrs = super().extra_state_attributes

    mode_info = self._get_performance_mode_info(self.current_option)
    attrs.update(cast(JSONMapping, mode_info))

    return _normalise_attributes(attrs)

  def _get_performance_mode_info(self, mode: str | None) -> PerformanceModeInfo:  # noqa: E111
    """Get information about the selected performance mode.

    Args:
        mode: Selected performance mode

    Returns:
        Performance mode information
    """
    if mode is None:
      return cast(PerformanceModeInfo, {})  # noqa: E111

    info = PERFORMANCE_MODE_DETAILS.get(mode)
    if info is None:
      return cast(PerformanceModeInfo, {})  # noqa: E111

    return cast(PerformanceModeInfo, dict(info))


class PawControlNotificationPrioritySelect(PawControlSelectBase):
  """Select entity for default notification priority."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the notification priority."""

    try:
      priority = NotificationPriority(option)  # noqa: E111
    except ValueError as err:
      raise HomeAssistantError(  # noqa: E111
        f"Unsupported notification priority '{option}'",
      ) from err

    runtime_data = self._get_runtime_data()
    notification_manager: PawControlNotificationManager | None = (
      runtime_data.notification_manager if runtime_data else None
    )

    if notification_manager is None:
      entry_data = self._get_domain_entry_data()  # noqa: E111
      fallback = entry_data.get("notification_manager")  # noqa: E111
      if isinstance(fallback, PawControlNotificationManager):  # noqa: E111
        notification_manager = fallback
      else:  # noqa: E111
        legacy = entry_data.get("notifications")
        if isinstance(legacy, PawControlNotificationManager):
          notification_manager = legacy  # noqa: E111

    if notification_manager is not None:
      await notification_manager.async_set_priority_threshold(  # noqa: E111
        self._dog_id,
        priority,
      )
    else:
      _LOGGER.debug(  # noqa: E111
        "Notification manager not available when updating priority for %s",
        self._dog_name,
      )

    timestamp = dt_util.utcnow().isoformat()
    updates: JSONMutableMapping = {
      "default_priority": option,
      "priority_last_updated": timestamp,
      "priority_numeric": priority.value_numeric,
    }
    await self._async_update_module_settings("notifications", updates)


# Feeding selects
class PawControlFoodTypeSelect(PawControlSelectBase):
  """Select entity for primary food type."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the food type select."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "food_type",
      options=FOOD_TYPE_OPTIONS,
      icon="mdi:food",
      initial_option="dry_food",
    )

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the food type."""
    # This would update feeding calculations and nutritional data
    pass

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional attributes for food type."""
    attrs = super().extra_state_attributes

    food_info = self._get_food_type_info(self.current_option)
    attrs.update(cast(JSONMapping, food_info))

    return _normalise_attributes(attrs)

  def _get_food_type_info(self, food_type: str | None) -> FoodTypeInfo:  # noqa: E111
    """Get information about the selected food type.

    Args:
        food_type: Selected food type

    Returns:
        Food type information
    """
    if food_type is None:
      return cast(FoodTypeInfo, {})  # noqa: E111

    info = FOOD_TYPE_DETAILS.get(food_type)
    if info is None:
      return cast(FoodTypeInfo, {})  # noqa: E111

    return cast(FoodTypeInfo, dict(info))


class PawControlFeedingScheduleSelect(PawControlSelectBase):
  """Select entity for feeding schedule type."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the feeding schedule."""
    # This would update feeding schedule enforcement
    pass


class PawControlDefaultMealTypeSelect(PawControlSelectBase):
  """Select entity for default meal type."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the default meal type select."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "default_meal_type",
      options=MEAL_TYPE_OPTIONS,
      icon="mdi:food-drumstick",
      initial_option="dinner",
    )

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the default meal type."""
    timestamp = dt_util.utcnow().isoformat()
    await self._async_update_module_settings(
      "feeding",
      {
        "default_meal_type": option,
        "default_meal_type_updated_at": timestamp,
      },
    )


class PawControlFeedingModeSelect(PawControlSelectBase):
  """Select entity for feeding mode."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the feeding mode."""
    runtime_data = self._get_runtime_data()
    feeding_manager = runtime_data.feeding_manager if runtime_data else None

    if feeding_manager is not None:
      if option == "diabetic":  # noqa: E111
        await feeding_manager.async_activate_diabetic_feeding_mode(
          self._dog_id,
        )
      elif option == "emergency":  # noqa: E111
        await feeding_manager.async_activate_emergency_feeding_mode(
          self._dog_id,
          "illness",
        )

    timestamp = dt_util.utcnow().isoformat()
    await self._async_update_module_settings(
      "feeding",
      {
        "mode": option,
        "mode_updated_at": timestamp,
      },
    )
    await self.coordinator.async_refresh_dog(self._dog_id)


# Walk selects
class PawControlWalkModeSelect(PawControlSelectBase):
  """Select entity for walk tracking mode."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the walk mode."""
    timestamp = dt_util.utcnow().isoformat()
    await self._async_update_module_settings(
      "walk",
      {
        "mode": option,
        "mode_updated_at": timestamp,
      },
    )

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional attributes for walk mode."""
    attrs = super().extra_state_attributes

    mode_info = self._get_walk_mode_info(self.current_option)
    attrs.update(cast(JSONMapping, mode_info))

    return _normalise_attributes(attrs)

  def _get_walk_mode_info(self, mode: str | None) -> WalkModeInfo:  # noqa: E111
    """Get information about the selected walk mode.

    Args:
        mode: Selected walk mode

    Returns:
        Walk mode information
    """
    if mode is None:
      return cast(WalkModeInfo, {})  # noqa: E111

    info = WALK_MODE_DETAILS.get(mode)
    if info is None:
      return cast(WalkModeInfo, {})  # noqa: E111

    return cast(WalkModeInfo, dict(info))


class PawControlWeatherPreferenceSelect(PawControlSelectBase):
  """Select entity for walk weather preference."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the weather preference."""
    # This would update weather-based walk recommendations
    pass


class PawControlWalkIntensitySelect(PawControlSelectBase):
  """Select entity for preferred walk intensity."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the walk intensity."""
    # This would update walk goal calculations
    pass


# GPS selects
class PawControlGPSSourceSelect(PawControlSelectBase):
  """Select entity for GPS data source."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the GPS source select."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "gps_source",
      options=GPS_SOURCE_OPTIONS,
      icon="mdi:crosshairs-gps",
      entity_category=EntityCategory.CONFIG,
      initial_option="device_tracker",
    )

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the GPS source."""

    timestamp = dt_util.utcnow().isoformat()
    await self._async_update_gps_settings(
      state_updates={
        "source": option,
        "source_updated_at": timestamp,
      },
    )

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional attributes for GPS source."""
    attrs = super().extra_state_attributes

    source_info = self._get_gps_source_info(self.current_option)
    attrs.update(cast(JSONMapping, source_info))

    return _normalise_attributes(attrs)

  def _get_gps_source_info(self, source: str | None) -> GPSSourceInfo:  # noqa: E111
    """Get information about the selected GPS source.

    Args:
        source: Selected GPS source

    Returns:
        GPS source information
    """
    if source is None:
      return cast(GPSSourceInfo, {})  # noqa: E111

    info = GPS_SOURCE_DETAILS.get(source)
    if info is None:
      return cast(GPSSourceInfo, {})  # noqa: E111

    return cast(GPSSourceInfo, dict(info))


class PawControlTrackingModeSelect(PawControlSelectBase):
  """Select entity for GPS tracking mode."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the tracking mode."""

    timestamp = dt_util.utcnow().isoformat()
    preset = TRACKING_MODE_PRESETS.get(option)
    config_updates: JSONMutableMapping | None = (
      cast(
        JSONMutableMapping,
        dict(preset),
      )
      if preset is not None
      else None
    )
    await self._async_update_gps_settings(
      state_updates={
        "tracking_mode": option,
        "tracking_mode_updated_at": timestamp,
      },
      config_updates=config_updates,
    )


class PawControlLocationAccuracySelect(PawControlSelectBase):
  """Select entity for location accuracy preference."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the location accuracy select."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "location_accuracy",
      options=LOCATION_ACCURACY_OPTIONS,
      icon="mdi:crosshairs",
      entity_category=EntityCategory.CONFIG,
      initial_option="balanced",
    )

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the location accuracy preference."""

    timestamp = dt_util.utcnow().isoformat()
    accuracy_config = LOCATION_ACCURACY_CONFIGS.get(option)
    config_updates: JSONMutableMapping | None = (
      cast(JSONMutableMapping, dict(accuracy_config))
      if accuracy_config is not None
      else None
    )
    await self._async_update_gps_settings(
      state_updates={
        "location_accuracy": option,
        "location_accuracy_updated_at": timestamp,
      },
      config_updates=config_updates,
    )


# Health selects
class PawControlHealthStatusSelect(PawControlSelectBase):
  """Select entity for current health status."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the health status select."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "health_status",
      options=HEALTH_STATUS_OPTION_KEYS,
      icon="mdi:heart-pulse",
      initial_option="good",
    )

  @property  # noqa: E111
  def current_option(self) -> str | None:  # noqa: E111
    """Return the current health status from data."""
    health_data = self._get_module_data("health")
    if health_data:
      value = health_data.get("health_status")  # noqa: E111
      if isinstance(value, str):  # noqa: E111
        return value

    return self._current_option

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the health status."""
    # This would update health status and trigger alerts if needed
    pass


class PawControlActivityLevelSelect(PawControlSelectBase):
  """Select entity for current activity level."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the activity level select."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "activity_level",
      options=ACTIVITY_LEVEL_OPTIONS,
      icon="mdi:run",
      initial_option="normal",
    )

  @property  # noqa: E111
  def current_option(self) -> str | None:  # noqa: E111
    """Return the current activity level from data."""
    health_data = self._get_module_data("health")
    if health_data:
      value = health_data.get("activity_level")  # noqa: E111
      if isinstance(value, str):  # noqa: E111
        return value

    return self._current_option

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the activity level."""
    # This would update activity tracking and recommendations
    pass


class PawControlMoodSelect(PawControlSelectBase):
  """Select entity for current mood."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the mood select."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "mood",
      options=MOOD_OPTIONS_KEYS,
      icon="mdi:emoticon",
      initial_option="happy",
    )

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the mood."""
    # This would log mood data and adjust recommendations
    pass


class PawControlGroomingTypeSelect(PawControlSelectBase):
  """Select entity for selecting grooming type."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  async def _async_set_select_option(self, option: str) -> None:  # noqa: E111
    """Set the grooming type."""
    # This would be used for logging grooming activities
    pass

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional attributes for grooming type."""
    attrs = super().extra_state_attributes

    grooming_info = self._get_grooming_type_info(self.current_option)
    attrs.update(cast(JSONMapping, grooming_info))

    return _normalise_attributes(attrs)

  def _get_grooming_type_info(self, grooming_type: str | None) -> GroomingTypeInfo:  # noqa: E111
    """Get information about the selected grooming type.

    Args:
        grooming_type: Selected grooming type

    Returns:
        Grooming type information
    """
    if grooming_type is None:
      return cast(GroomingTypeInfo, {})  # noqa: E111

    info = GROOMING_TYPE_DETAILS.get(grooming_type)
    if info is None:
      return cast(GroomingTypeInfo, {})  # noqa: E111

    return cast(GroomingTypeInfo, dict(info))
