"""Select platform for Paw Control integration.

This module provides comprehensive select entities for dog monitoring configuration
including mode selections, option choices, and status settings. All select entities
are designed to meet Home Assistant's Platinum quality ambitions with full type
annotations, async operations, and robust validation.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .compat import HomeAssistantError
from .const import (
    ACTIVITY_LEVELS,
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    DEFAULT_PERFORMANCE_MODE,
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
from .coordinator import PawControlCoordinator
from .entity import PawControlEntity
from .notifications import NotificationPriority, PawControlNotificationManager
from .runtime_data import get_runtime_data
from .types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DOG_SIZE_FIELD,
    CoordinatorDogData,
    DogConfigData,
    DogSizeInfo,
    FoodTypeInfo,
    GPSSourceInfo,
    GroomingTypeInfo,
    JSONMapping,
    JSONMutableMapping,
    JSONValue,
    LocationAccuracyConfig,
    PawControlConfigEntry,
    PawControlRuntimeData,
    PerformanceModeInfo,
    SelectExtraAttributes,
    TrackingModePreset,
    WalkModeInfo,
    coerce_dog_modules_config,
)
from .utils import async_call_add_entities, deep_merge_dicts

if TYPE_CHECKING:
    from .data_manager import PawControlDataManager

_LOGGER = logging.getLogger(__name__)

# Select entities invoke coordinator-backed actions. The coordinator is
# responsible for serialising writes, so we allow unlimited parallel updates at
# the entity layer.
PARALLEL_UPDATES = 0


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
    }
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
        }
    )
)

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
    }
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
    }
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
    }
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
    }
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
    }
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
    }
)


def _merge_json_mappings(
    base: Mapping[str, JSONValue] | None, updates: Mapping[str, JSONValue]
) -> JSONMutableMapping:
    """Return a JSON-compatible mapping that merges base and updates."""

    base_payload: dict[str, JSONValue] = dict(base) if base is not None else {}
    merged = deep_merge_dicts(base_payload, dict(updates))
    return cast(JSONMutableMapping, merged)


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
    """
    total_entities = len(entities)

    _LOGGER.debug(
        "Adding %d select entities in batches of %d to prevent Registry overload",
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
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
            async_add_entities_func, batch, update_before_add=False
        )

        # Small delay between batches to prevent Registry flooding
        if i + batch_size < total_entities:  # No delay after last batch
            await asyncio.sleep(delay_between_batches)


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
    """
    runtime_data = get_runtime_data(hass, entry)
    if runtime_data is None:
        _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
        return

    coordinator: PawControlCoordinator = runtime_data.coordinator
    dogs: list[DogConfigData] = runtime_data.dogs

    entities: list[PawControlSelectBase] = []

    # Create select entities for each configured dog
    for dog in dogs:
        dog_id = dog[DOG_ID_FIELD]
        dog_name = dog[DOG_NAME_FIELD]
        modules = coerce_dog_modules_config(dog.get(DOG_MODULES_FIELD))

        _LOGGER.debug("Creating select entities for dog: %s (%s)", dog_name, dog_id)

        # Base selects - always created for every dog
        entities.extend(_create_base_selects(coordinator, dog_id, dog_name, dog))

        # Module-specific selects
        if modules.get(MODULE_FEEDING, False):
            entities.extend(_create_feeding_selects(coordinator, dog_id, dog_name))

        if modules.get(MODULE_WALK, False):
            entities.extend(_create_walk_selects(coordinator, dog_id, dog_name))

        if modules.get(MODULE_GPS, False):
            entities.extend(_create_gps_selects(coordinator, dog_id, dog_name))

        if modules.get(MODULE_HEALTH, False):
            entities.extend(_create_health_selects(coordinator, dog_id, dog_name))

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


class PawControlSelectBase(PawControlEntity, SelectEntity, RestoreEntity):
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
        super().__init__(coordinator, dog_id, dog_name)
        self._select_type = select_type
        self._current_option = initial_option

        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{select_type}"
        self._apply_name_suffix(select_type.replace("_", " ").title())
        self._attr_options = options
        self._attr_icon = icon
        self._attr_entity_category = entity_category

        # Link entity to PawControl device entry for the dog
        self.update_device_metadata(
            model="Smart Dog Monitoring",
            sw_version="1.0.0",
            configuration_url="https://github.com/BigDaddy1990/pawcontrol",
        )

    def _get_runtime_data(self) -> PawControlRuntimeData | None:
        """Return runtime data associated with the config entry."""

        if self.hass is None:
            return None

        return get_runtime_data(self.hass, self.coordinator.config_entry)

    def _get_domain_entry_data(self) -> JSONMutableMapping:
        """Return the hass.data payload for this config entry."""

        runtime_data = self._get_runtime_data()
        if runtime_data is not None:
            return cast(JSONMutableMapping, runtime_data.as_dict())

        return {}

    def _get_data_manager(self) -> PawControlDataManager | None:
        """Return the data manager for persistence if available."""

        runtime_data = self._get_runtime_data()
        if runtime_data is not None:
            manager_container = getattr(runtime_data, "runtime_managers", None)
            if manager_container is not None:
                return getattr(manager_container, "data_manager", None)

        entry_data = self._get_domain_entry_data()
        managers = entry_data.get("runtime_managers")
        if managers is None:
            return None

        manager_obj = getattr(managers, "data_manager", None)
        if manager_obj is not None:
            return cast(PawControlDataManager | None, manager_obj)

        if isinstance(managers, Mapping):
            candidate = managers.get("data_manager")
            if candidate is not None:
                return cast(PawControlDataManager | None, candidate)

        return None

    def _get_current_gps_config(self) -> JSONMutableMapping:
        """Return the currently stored GPS configuration."""

        dog_data = self._get_dog_data()
        if dog_data is None:
            return cast(JSONMutableMapping, {})

        gps_data = dog_data.get("gps")
        if isinstance(gps_data, Mapping):
            config = gps_data.get("config")
            if isinstance(config, Mapping):
                return cast(JSONMutableMapping, dict(config))

        return cast(JSONMutableMapping, {})

    async def _async_update_module_settings(
        self,
        module: str,
        updates: JSONMutableMapping,
    ) -> None:
        """Persist updates for a module and refresh coordinator data."""

        data_manager = self._get_data_manager()
        if data_manager:
            try:
                await data_manager.async_update_dog_data(
                    self._dog_id, {module: updates}
                )
            except Exception as err:  # pragma: no cover - defensive log
                _LOGGER.warning(
                    "Failed to persist %s updates for %s: %s",
                    module,
                    self._dog_name,
                    err,
                )

        coordinator_payload = cast(
            Mapping[str, JSONMutableMapping] | None, self.coordinator.data
        )
        coordinator_data: dict[str, JSONMutableMapping] = (
            dict(coordinator_payload) if coordinator_payload else {}
        )
        existing_dog = coordinator_data.get(self._dog_id)
        dog_data: JSONMutableMapping = (
            dict(existing_dog) if isinstance(existing_dog, Mapping) else {}
        )
        existing_module = cast(Mapping[str, JSONValue] | None, dog_data.get(module))
        merged = _merge_json_mappings(existing_module, updates)
        dog_data[module] = merged
        coordinator_data[self._dog_id] = dog_data
        update_result = self.coordinator.async_set_updated_data(coordinator_data)
        if asyncio.iscoroutine(update_result):
            await update_result

    async def _async_update_gps_settings(
        self,
        *,
        state_updates: JSONMutableMapping | None = None,
        config_updates: JSONMutableMapping | None = None,
    ) -> None:
        """Update stored GPS settings and apply them to the GPS manager."""

        gps_updates: JSONMutableMapping = {}
        merged_config: JSONMutableMapping | None = None

        if state_updates:
            gps_updates.update(state_updates)

        if config_updates:
            current_config = self._get_current_gps_config()
            merged_config = _merge_json_mappings(current_config, config_updates)
            gps_updates.setdefault("config", merged_config)

        if gps_updates:
            await self._async_update_module_settings("gps", gps_updates)

        if merged_config:
            runtime_data = self._get_runtime_data()
            gps_manager = (
                getattr(runtime_data, "gps_geofence_manager", None)
                if runtime_data
                else None
            )
            if gps_manager:
                try:
                    await gps_manager.async_configure_dog_gps(
                        self._dog_id, merged_config
                    )
                except Exception as err:  # pragma: no cover - defensive log
                    _LOGGER.warning(
                        "Failed to apply GPS configuration for %s: %s",
                        self._dog_name,
                        err,
                    )

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
    def extra_state_attributes(self) -> SelectExtraAttributes:
        """Return additional state attributes for the select.

        Provides information about the select's function and available options.

        Returns:
            Dictionary of additional state attributes
        """
        base_attrs = super().extra_state_attributes
        attrs: SelectExtraAttributes = {}
        if base_attrs:
            attrs.update(cast(SelectExtraAttributes, base_attrs))

        attrs[ATTR_DOG_ID] = self._dog_id
        attrs[ATTR_DOG_NAME] = self._dog_name
        attrs["select_type"] = self._select_type
        attrs["available_options"] = list(self.options)
        attrs["last_changed"] = dt_util.utcnow().isoformat()

        dog_data = self._get_dog_data()
        if isinstance(dog_data, Mapping):
            dog_info = dog_data.get("dog_info")
            if isinstance(dog_info, Mapping):
                breed = dog_info.get("dog_breed")
                if isinstance(breed, str):
                    attrs["dog_breed"] = breed

                age = dog_info.get("dog_age")
                if isinstance(age, int | float):
                    attrs["dog_age"] = age

                size = dog_info.get("dog_size")
                if isinstance(size, str):
                    attrs["dog_size"] = size

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
            raise HomeAssistantError(f"Failed to set {self._select_type}") from err

    async def _async_set_select_option(self, option: str) -> None:
        """Set the select option implementation.

        This method should be overridden by subclasses to implement
        specific select functionality.

        Args:
            option: Option to set
        """
        # Base implementation - subclasses should override
        pass

    def _get_dog_data(self) -> CoordinatorDogData | None:
        """Get data for this select's dog from the coordinator.

        Returns:
            Dog data dictionary or None if not available
        """
        if not self.coordinator.available:
            return None

        return self.coordinator.get_dog_data(self._dog_id)

    def _get_module_data(self, module: str) -> JSONMapping | None:
        """Get specific module data for this dog.

        Args:
            module: Module name to retrieve data for

        Returns:
            Module data dictionary or None if not available
        """
        module_data = self.coordinator.get_module_data(self._dog_id, module)
        if isinstance(module_data, Mapping):
            return cast(JSONMapping, module_data)
        return None

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
        dog_config: DogConfigData,
    ) -> None:
        """Initialize the dog size select."""
        current_size = dog_config.get(DOG_SIZE_FIELD, "medium")

        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "size",
            options=list(DOG_SIZES),
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
    def extra_state_attributes(self) -> SelectExtraAttributes:
        """Return additional attributes for the size select."""
        attrs = super().extra_state_attributes

        size_info = self._get_size_info(self.current_option)
        attrs.update(cast(JSONMapping, size_info))

        return attrs

    def _get_size_info(self, size: str | None) -> DogSizeInfo:
        """Get information about the selected size.

        Args:
            size: Selected size category

        Returns:
            Size information dictionary
        """
        if size is None:
            return cast(DogSizeInfo, {})

        info = DOG_SIZE_DETAILS.get(size)
        if info is None:
            return cast(DogSizeInfo, {})

        return cast(DogSizeInfo, dict(info))


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
            options=list(PERFORMANCE_MODES),
            icon="mdi:speedometer",
            entity_category=EntityCategory.CONFIG,
            initial_option=DEFAULT_PERFORMANCE_MODE,
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the performance mode."""
        # This would update system performance settings
        pass

    @property
    def extra_state_attributes(self) -> SelectExtraAttributes:
        """Return additional attributes for performance mode."""
        attrs = super().extra_state_attributes

        mode_info = self._get_performance_mode_info(self.current_option)
        attrs.update(cast(JSONMapping, mode_info))

        return attrs

    def _get_performance_mode_info(self, mode: str | None) -> PerformanceModeInfo:
        """Get information about the selected performance mode.

        Args:
            mode: Selected performance mode

        Returns:
            Performance mode information
        """
        if mode is None:
            return cast(PerformanceModeInfo, {})

        info = PERFORMANCE_MODE_DETAILS.get(mode)
        if info is None:
            return cast(PerformanceModeInfo, {})

        return cast(PerformanceModeInfo, dict(info))


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

        try:
            priority = NotificationPriority(option)
        except ValueError as err:
            raise HomeAssistantError(
                f"Unsupported notification priority '{option}'"
            ) from err

        runtime_data = self._get_runtime_data()
        notification_manager: PawControlNotificationManager | None = (
            runtime_data.notification_manager if runtime_data else None
        )

        if notification_manager is None:
            entry_data = self._get_domain_entry_data()
            fallback = entry_data.get("notification_manager")
            if isinstance(fallback, PawControlNotificationManager):
                notification_manager = fallback
            else:
                legacy = entry_data.get("notifications")
                if isinstance(legacy, PawControlNotificationManager):
                    notification_manager = legacy

        if notification_manager is not None:
            await notification_manager.async_set_priority_threshold(
                self._dog_id, priority
            )
        else:
            _LOGGER.debug(
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
            options=list(FOOD_TYPES),
            icon="mdi:food",
            initial_option="dry_food",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the food type."""
        # This would update feeding calculations and nutritional data
        pass

    @property
    def extra_state_attributes(self) -> SelectExtraAttributes:
        """Return additional attributes for food type."""
        attrs = super().extra_state_attributes

        food_info = self._get_food_type_info(self.current_option)
        attrs.update(cast(JSONMapping, food_info))

        return attrs

    def _get_food_type_info(self, food_type: str | None) -> FoodTypeInfo:
        """Get information about the selected food type.

        Args:
            food_type: Selected food type

        Returns:
            Food type information
        """
        if food_type is None:
            return cast(FoodTypeInfo, {})

        info = FOOD_TYPE_DETAILS.get(food_type)
        if info is None:
            return cast(FoodTypeInfo, {})

        return cast(FoodTypeInfo, dict(info))


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
            options=list(MEAL_TYPES),
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
    def extra_state_attributes(self) -> SelectExtraAttributes:
        """Return additional attributes for walk mode."""
        attrs = super().extra_state_attributes

        mode_info = self._get_walk_mode_info(self.current_option)
        attrs.update(cast(JSONMapping, mode_info))

        return attrs

    def _get_walk_mode_info(self, mode: str | None) -> WalkModeInfo:
        """Get information about the selected walk mode.

        Args:
            mode: Selected walk mode

        Returns:
            Walk mode information
        """
        if mode is None:
            return cast(WalkModeInfo, {})

        info = WALK_MODE_DETAILS.get(mode)
        if info is None:
            return cast(WalkModeInfo, {})

        return cast(WalkModeInfo, dict(info))


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
            options=list(GPS_SOURCES),
            icon="mdi:crosshairs-gps",
            entity_category=EntityCategory.CONFIG,
            initial_option="device_tracker",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the GPS source."""

        timestamp = dt_util.utcnow().isoformat()
        await self._async_update_gps_settings(
            state_updates={
                "source": option,
                "source_updated_at": timestamp,
            }
        )

    @property
    def extra_state_attributes(self) -> SelectExtraAttributes:
        """Return additional attributes for GPS source."""
        attrs = super().extra_state_attributes

        source_info = self._get_gps_source_info(self.current_option)
        attrs.update(cast(JSONMapping, source_info))

        return attrs

    def _get_gps_source_info(self, source: str | None) -> GPSSourceInfo:
        """Get information about the selected GPS source.

        Args:
            source: Selected GPS source

        Returns:
            GPS source information
        """
        if source is None:
            return cast(GPSSourceInfo, {})

        info = GPS_SOURCE_DETAILS.get(source)
        if info is None:
            return cast(GPSSourceInfo, {})

        return cast(GPSSourceInfo, dict(info))


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
            options=list(TRACKING_MODES),
            icon="mdi:map-marker",
            initial_option="interval",
        )

    async def _async_set_select_option(self, option: str) -> None:
        """Set the tracking mode."""

        timestamp = dt_util.utcnow().isoformat()
        preset = TRACKING_MODE_PRESETS.get(option)
        config_updates: JSONMutableMapping | None = (
            cast(JSONMutableMapping, dict(preset)) if preset is not None else None
        )
        await self._async_update_gps_settings(
            state_updates={
                "tracking_mode": option,
                "tracking_mode_updated_at": timestamp,
            },
            config_updates=config_updates,
        )


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
            options=list(HEALTH_STATUS_OPTIONS),
            icon="mdi:heart-pulse",
            initial_option="good",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current health status from data."""
        health_data = self._get_module_data("health")
        if health_data:
            value = health_data.get("health_status")
            if isinstance(value, str):
                return value

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
            options=list(ACTIVITY_LEVELS),
            icon="mdi:run",
            initial_option="normal",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current activity level from data."""
        health_data = self._get_module_data("health")
        if health_data:
            value = health_data.get("activity_level")
            if isinstance(value, str):
                return value

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
            options=list(MOOD_OPTIONS),
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
    def extra_state_attributes(self) -> SelectExtraAttributes:
        """Return additional attributes for grooming type."""
        attrs = super().extra_state_attributes

        grooming_info = self._get_grooming_type_info(self.current_option)
        attrs.update(cast(JSONMapping, grooming_info))

        return attrs

    def _get_grooming_type_info(self, grooming_type: str | None) -> GroomingTypeInfo:
        """Get information about the selected grooming type.

        Args:
            grooming_type: Selected grooming type

        Returns:
            Grooming type information
        """
        if grooming_type is None:
            return cast(GroomingTypeInfo, {})

        info = GROOMING_TYPE_DETAILS.get(grooming_type)
        if info is None:
            return cast(GroomingTypeInfo, {})

        return cast(GroomingTypeInfo, dict(info))
