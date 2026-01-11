"""Sensor platform for the PawControl integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from numbers import Real
from typing import TYPE_CHECKING, Any, Final, Protocol, TypeGuard, cast

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    STATE_UNKNOWN,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfMass,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    MODULE_GARDEN,
)
from .coordinator import PawControlCoordinator
from .diagnostics import _normalise_json as _normalise_diagnostics_json
from .entity import PawControlEntity
from .entity_factory import EntityFactory, EntityProfileDefinition
from .runtime_data import get_runtime_data
from .types import (
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    CoordinatorDogData,
    CoordinatorModuleLookupResult,
    CoordinatorModuleState,
    CoordinatorTypedModuleName,
    CoordinatorUntypedModuleState,
    DogConfigData,
    FeedingDietValidationSummary,
    FeedingModulePayload,
    GardenModulePayload,
    GPSModulePayload,
    HealthModulePayload,
    JSONMutableMapping,
    JSONValue,
    PawControlConfigEntry,
    WalkModuleTelemetry,
    ensure_dog_modules_mapping,
    ensure_gps_payload,
    ensure_json_mapping,
)
from .utils import (
    async_call_add_entities,
    ensure_utc_datetime,
    is_number,
)

if TYPE_CHECKING:

    class SensorEntityProtocol(Protocol):
        """Typed protocol for Home Assistant sensor entities."""

        _attr_has_entity_name: bool
        _attr_should_poll: bool

else:
    from homeassistant.components.sensor import SensorEntity as SensorEntityProtocol

_LOGGER = logging.getLogger(__name__)

# Type aliases for better readability
SensorValue = str | int | float | datetime | None
type AttributeDict = JSONMutableMapping
_STATE_UNKNOWN: Final[str] = cast(str, STATE_UNKNOWN)

# Home Assistant platform configuration
PARALLEL_UPDATES = 0

# OPTIMIZED: Performance constants for Platinum profiles
ENTITY_CREATION_DELAY = 0.005  # 5ms between batches (optimized for profiles)
MAX_ENTITIES_PER_BATCH = 6  # Smaller batches for profile-based creation
PARALLEL_THRESHOLD = 12  # Lower threshold for profile-optimized entity counts

_TYPED_SENSOR_MODULES: Final[frozenset[CoordinatorTypedModuleName]] = frozenset(
    {"feeding", "garden", "geofencing", "gps", "health", "walk", "weather"}
)


def _is_typed_sensor_module(module: str) -> TypeGuard[CoordinatorTypedModuleName]:
    """Return True when ``module`` stores structured coordinator payloads."""

    return module in _TYPED_SENSOR_MODULES


# Gracefully handle Home Assistant constant backports in the test harness
try:  # pragma: no cover - executed indirectly during import
    _SPEED_UNIT = UnitOfSpeed.KILOMETERS_PER_HOUR
except AttributeError:  # pragma: no cover - fallback for older constant sets
    _SPEED_UNIT = getattr(UnitOfSpeed, "METERS_PER_SECOND", "km/h")

try:  # pragma: no cover - executed indirectly during import
    _CALORIE_UNIT = UnitOfEnergy.KILO_CALORIE
except AttributeError:  # pragma: no cover - fallback for older constant sets
    _CALORIE_UNIT = "kcal"


def _normalise_attributes(attrs: Mapping[str, object]) -> AttributeDict:
    """Return JSON-serialisable attributes for sensor entities."""

    payload = ensure_json_mapping(attrs)
    return cast(AttributeDict, _normalise_diagnostics_json(payload))


# PLATINUM: Dynamic cache TTL based on coordinator update interval
def get_activity_score_cache_ttl(coordinator: PawControlCoordinator) -> int:
    """Calculate dynamic cache TTL based on coordinator update interval."""

    update_interval = getattr(coordinator, "update_interval", None)
    if not update_interval:
        return 300  # Default 5 minutes

    interval_seconds: float | None

    if hasattr(update_interval, "total_seconds"):
        try:
            interval_seconds = float(update_interval.total_seconds())
        except (TypeError, ValueError):
            interval_seconds = None
    else:
        try:
            interval_seconds = float(update_interval)
        except (TypeError, ValueError):
            interval_seconds = None

    if not interval_seconds or interval_seconds <= 0:
        return 300

    # Cache for 2.5x the update interval, minimum 60s, maximum 600s
    return max(60, min(600, int(interval_seconds * 2.5)))


# Sensor mapping for profile-based creation
SENSOR_MAPPING: dict[str, type[PawControlSensorBase]] = {}


def register_sensor(
    name: str,
) -> Callable[[type[PawControlSensorBase]], type[PawControlSensorBase]]:
    """Decorator to register sensor classes."""

    def decorator(
        cls: type[PawControlSensorBase],
    ) -> type[PawControlSensorBase]:
        """Register the decorated sensor class in the mapping."""

        SENSOR_MAPPING[name] = cls
        return cls

    return decorator


def _copy_base_docstring(
    *,
    attribute_name: str,
    cls: type[PawControlSensorBase],
    attribute: Any,
) -> None:
    """Copy a docstring from a base implementation to the given attribute."""

    for base in cls.__mro__[1:]:
        base_attribute = getattr(base, attribute_name, None)
        if base_attribute is None:
            continue

        base_doc = getattr(base_attribute, "__doc__", None)
        if not base_doc:
            continue

        if isinstance(attribute, property):
            setattr(
                cls,
                attribute_name,
                property(
                    attribute.fget,
                    attribute.fset,
                    attribute.fdel,
                    base_doc,
                ),
            )
            return

        if isinstance(attribute, classmethod | staticmethod):
            func = attribute.__func__
            if getattr(func, "__doc__", None):
                return
            func.__doc__ = base_doc
            return

        with contextlib.suppress(AttributeError):
            attribute.__doc__ = base_doc
        return


def inherit_missing_docstrings() -> None:
    """Ensure all PawControl sensor overrides provide a docstring."""

    for obj in list(globals().values()):
        if not isinstance(obj, type) or not issubclass(obj, PawControlSensorBase):
            continue

        for name, attr in vars(obj).items():
            if getattr(attr, "__doc__", None):
                continue

            _copy_base_docstring(
                attribute_name=name,
                cls=obj,
                attribute=attr,
            )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control sensor platform with profile optimization."""

    # OPTIMIZED: Consistent runtime_data usage for Platinum readiness
    runtime_data = get_runtime_data(hass, entry)
    if runtime_data is None:
        _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
        return
    coordinator = runtime_data.coordinator
    dogs: list[DogConfigData] = runtime_data.dogs
    entity_factory = runtime_data.entity_factory
    profile = runtime_data.entity_profile

    if not dogs:
        _LOGGER.warning("No dogs configured for sensor platform")
        return

    _LOGGER.info("Setting up sensors with profile '%s' for %d dogs", profile, len(dogs))

    # Create profile-optimized entities
    all_entities = await _create_profile_entities(
        coordinator, entity_factory, dogs, profile
    )

    # Performance-optimized entity addition
    await _add_entities_optimized(async_add_entities, all_entities, profile)

    # Log performance metrics
    _log_setup_metrics(all_entities, dogs, profile, entity_factory)


async def _create_profile_entities(
    coordinator: PawControlCoordinator,
    entity_factory: EntityFactory,
    dogs: list[DogConfigData],
    profile: str,
) -> list[PawControlSensorBase]:
    """Create entities based on profile requirements."""
    all_entities = []

    for dog in dogs:
        dog_id = dog[DOG_ID_FIELD]
        dog_name = dog[DOG_NAME_FIELD]
        modules = ensure_dog_modules_mapping(cast(Mapping[str, object], dog))

        # Create core entities (always included)
        core_entities = _create_core_entities(coordinator, dog_id, dog_name)
        entity_factory.begin_budget(
            dog_id,
            profile,
            base_allocation=len(core_entities),
        )
        all_entities.extend(core_entities)

        # Create module-specific entities based on profile
        try:
            module_entities = await _create_module_entities(
                coordinator, entity_factory, dog_id, dog_name, modules, profile
            )
            all_entities.extend(module_entities)
        finally:
            entity_factory.finalize_budget(dog_id, profile)

    return all_entities


def _create_core_entities(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSensorBase]:
    """Create core entities that are always present."""
    return [
        PawControlDogStatusSensor(coordinator, dog_id, dog_name),
        PawControlLastActionSensor(coordinator, dog_id, dog_name),
        PawControlActivityScoreSensor(coordinator, dog_id, dog_name),
        PawControlActivityLevelSensor(
            coordinator, dog_id, dog_name
        ),  # NEW: Critical missing sensor
    ]


async def _create_module_entities(
    coordinator: PawControlCoordinator,
    entity_factory: EntityFactory,
    dog_id: str,
    dog_name: str,
    modules: Mapping[str, bool],
    profile: str,
) -> list[PawControlSensorBase]:
    """Create module-specific entities based on profile and enabled modules."""
    entities = []
    budget = entity_factory.get_budget(dog_id, profile)

    # Define entity creation rules per module and profile
    module_entity_rules = {
        "feeding": {
            "basic": [
                ("last_feeding", PawControlLastFeedingSensor, 9),
                ("daily_portions", PawControlDailyPortionsSensor, 8),
            ],
            "standard": [
                ("last_feeding", PawControlLastFeedingSensor, 9),
                ("daily_portions", PawControlDailyPortionsSensor, 8),
                ("portions_today", PawControlPortionsTodaySensor, 7),
                ("daily_calories", PawControlDailyCaloriesSensor, 7),
                ("last_feeding_hours", PawControlLastFeedingHoursSensor, 6),
                (
                    "feeding_schedule_adherence",
                    PawControlFeedingScheduleAdherenceSensor,
                    5,
                ),
                ("total_feedings_today", PawControlTotalFeedingsTodaySensor, 4),
                ("calorie_goal_progress", PawControlCalorieGoalProgressSensor, 3),
                ("health_feeding_status", PawControlHealthFeedingStatusSensor, 2),
            ],
            "advanced": [
                ("last_feeding", PawControlLastFeedingSensor, 9),
                ("daily_calories", PawControlDailyCaloriesSensor, 8),
                ("daily_portions", PawControlDailyPortionsSensor, 7),
                ("portions_today", PawControlPortionsTodaySensor, 7),
                ("food_consumption", PawControlFoodConsumptionSensor, 6),
                ("last_feeding_hours", PawControlLastFeedingHoursSensor, 6),
                (
                    "feeding_schedule_adherence",
                    PawControlFeedingScheduleAdherenceSensor,
                    5,
                ),
                ("calorie_goal_progress", PawControlCalorieGoalProgressSensor, 4),
                ("total_feedings_today", PawControlTotalFeedingsTodaySensor, 3),
                ("health_aware_portion", PawControlHealthAwarePortionSensor, 2),
                ("daily_calorie_target", PawControlDailyCalorieTargetSensor, 2),
                ("calories_consumed_today", PawControlCaloriesConsumedTodaySensor, 2),
                (
                    "portion_adjustment_factor",
                    PawControlPortionAdjustmentFactorSensor,
                    1,
                ),
                ("feeding_recommendation", PawControlFeedingRecommendationSensor, 1),
                ("diet_validation_status", PawControlDietValidationStatusSensor, 1),
                ("diet_conflict_count", PawControlDietConflictCountSensor, 0),
                ("diet_warning_count", PawControlDietWarningCountSensor, 0),
                ("diet_vet_consultation", PawControlDietVetConsultationSensor, 0),
                (
                    "diet_validation_adjustment",
                    PawControlDietValidationAdjustmentSensor,
                    0,
                ),
                ("diet_compatibility_score", PawControlDietCompatibilityScoreSensor, 0),
            ],
            "gps_focus": [
                ("last_feeding", PawControlLastFeedingSensor, 9),
                ("daily_portions", PawControlDailyPortionsSensor, 8),
                ("portions_today", PawControlPortionsTodaySensor, 7),
                ("daily_calories", PawControlDailyCaloriesSensor, 7),
                ("food_consumption", PawControlFoodConsumptionSensor, 5),
            ],
            "health_focus": [
                ("health_feeding_status", PawControlHealthFeedingStatusSensor, 9),
                ("daily_calorie_target", PawControlDailyCalorieTargetSensor, 8),
                ("calories_consumed_today", PawControlCaloriesConsumedTodaySensor, 7),
                (
                    "portion_adjustment_factor",
                    PawControlPortionAdjustmentFactorSensor,
                    6,
                ),
                ("health_aware_portion", PawControlHealthAwarePortionSensor, 5),
                ("daily_calories", PawControlDailyCaloriesSensor, 4),
                ("daily_portions", PawControlDailyPortionsSensor, 3),
                ("portions_today", PawControlPortionsTodaySensor, 3),
                (
                    "last_feeding_hours",
                    PawControlLastFeedingHoursSensor,
                    2,
                ),
                (
                    "feeding_schedule_adherence",
                    PawControlFeedingScheduleAdherenceSensor,
                    1,
                ),
                ("calorie_goal_progress", PawControlCalorieGoalProgressSensor, 1),
                ("diet_validation_status", PawControlDietValidationStatusSensor, 0),
                ("diet_conflict_count", PawControlDietConflictCountSensor, 0),
                ("diet_warning_count", PawControlDietWarningCountSensor, 0),
                (
                    "diet_vet_consultation",
                    PawControlDietVetConsultationSensor,
                    0,
                ),
                (
                    "diet_validation_adjustment",
                    PawControlDietValidationAdjustmentSensor,
                    0,
                ),
                (
                    "diet_compatibility_score",
                    PawControlDietCompatibilityScoreSensor,
                    0,
                ),
            ],
        },
        "walk": {
            "basic": [
                ("last_walk", PawControlLastWalkSensor, 9),
                ("last_walk_hours", PawControlLastWalkHoursSensor, 8),
                ("walks_today", PawControlWalksTodaySensor, 7),
            ],
            "standard": [
                ("last_walk", PawControlLastWalkSensor, 9),
                ("last_walk_hours", PawControlLastWalkHoursSensor, 8),
                ("walks_today", PawControlWalksTodaySensor, 7),
                (
                    "current_walk_duration",
                    PawControlCurrentWalkDurationSensor,
                    7,
                ),
                (
                    "walk_distance_today",
                    PawControlWalkDistanceTodaySensor,
                    7,
                ),
                (
                    "calories_burned_today",
                    PawControlCaloriesBurnedTodaySensor,
                    6,
                ),
                ("last_walk_duration", PawControlLastWalkDurationSensor, 5),
                ("total_walk_time_today", PawControlTotalWalkTimeTodaySensor, 4),
            ],
            "gps_focus": [
                ("last_walk", PawControlLastWalkSensor, 9),
                (
                    "walk_distance_today",
                    PawControlWalkDistanceTodaySensor,
                    8,
                ),
                (
                    "total_walk_distance",
                    PawControlTotalWalkDistanceSensor,
                    7,
                ),
                ("last_walk_hours", PawControlLastWalkHoursSensor, 7),
                ("walks_today", PawControlWalksTodaySensor, 6),
                (
                    "walks_this_week",
                    PawControlWalksThisWeekSensor,
                    5,
                ),
                (
                    "calories_burned_today",
                    PawControlCaloriesBurnedTodaySensor,
                    4,
                ),
            ],
        },
        MODULE_GARDEN: {
            "basic": [
                (
                    "garden_time_today",
                    PawControlGardenTimeTodaySensor,
                    8,
                ),
                (
                    "garden_sessions_today",
                    PawControlGardenSessionsTodaySensor,
                    7,
                ),
            ],
            "standard": [
                (
                    "garden_time_today",
                    PawControlGardenTimeTodaySensor,
                    8,
                ),
                (
                    "garden_sessions_today",
                    PawControlGardenSessionsTodaySensor,
                    7,
                ),
                (
                    "garden_poop_count_today",
                    PawControlGardenPoopCountTodaySensor,
                    6,
                ),
                (
                    "garden_activities_today",
                    PawControlGardenActivitiesTodaySensor,
                    5,
                ),
                (
                    "garden_activities_count",
                    PawControlGardenActivitiesCountSensor,
                    4,
                ),
                (
                    "last_garden_session_hours",
                    PawControlLastGardenSessionHoursSensor,
                    3,
                ),
                (
                    "last_garden_duration",
                    PawControlLastGardenDurationSensor,
                    2,
                ),
            ],
            "advanced": [
                (
                    "garden_time_today",
                    PawControlGardenTimeTodaySensor,
                    7,
                ),
                (
                    "garden_sessions_today",
                    PawControlGardenSessionsTodaySensor,
                    6,
                ),
                (
                    "garden_poop_count_today",
                    PawControlGardenPoopCountTodaySensor,
                    5,
                ),
                (
                    "garden_activities_today",
                    PawControlGardenActivitiesTodaySensor,
                    4,
                ),
                (
                    "garden_activities_count",
                    PawControlGardenActivitiesCountSensor,
                    3,
                ),
                (
                    "last_garden_duration",
                    PawControlLastGardenDurationSensor,
                    3,
                ),
                (
                    "last_garden_session_hours",
                    PawControlLastGardenSessionHoursSensor,
                    2,
                ),
                (
                    "avg_garden_duration",
                    PawControlAverageGardenDurationSensor,
                    2,
                ),
                (
                    "garden_stats_weekly",
                    PawControlGardenStatsWeeklySensor,
                    1,
                ),
                (
                    "favorite_garden_activities",
                    PawControlFavoriteGardenActivitiesSensor,
                    1,
                ),
                (
                    "garden_activities_last_session",
                    PawControlGardenActivitiesLastSessionSensor,
                    1,
                ),
            ],
            "gps_focus": [
                (
                    "garden_time_today",
                    PawControlGardenTimeTodaySensor,
                    6,
                ),
                (
                    "garden_sessions_today",
                    PawControlGardenSessionsTodaySensor,
                    5,
                ),
                (
                    "garden_activities_today",
                    PawControlGardenActivitiesTodaySensor,
                    4,
                ),
                (
                    "last_garden_session_hours",
                    PawControlLastGardenSessionHoursSensor,
                    3,
                ),
            ],
            "health_focus": [
                (
                    "garden_time_today",
                    PawControlGardenTimeTodaySensor,
                    6,
                ),
                (
                    "garden_sessions_today",
                    PawControlGardenSessionsTodaySensor,
                    5,
                ),
                (
                    "avg_garden_duration",
                    PawControlAverageGardenDurationSensor,
                    4,
                ),
                (
                    "garden_stats_weekly",
                    PawControlGardenStatsWeeklySensor,
                    3,
                ),
                (
                    "favorite_garden_activities",
                    PawControlFavoriteGardenActivitiesSensor,
                    2,
                ),
            ],
        },
        "gps": {
            "standard": [
                ("current_zone", PawControlCurrentZoneSensor, 8),
                ("current_location", PawControlCurrentLocationSensor, 8),
                ("distance_from_home", PawControlDistanceFromHomeSensor, 7),
            ],
            "gps_focus": [
                ("current_zone", PawControlCurrentZoneSensor, 9),
                ("current_location", PawControlCurrentLocationSensor, 9),
                ("distance_from_home", PawControlDistanceFromHomeSensor, 8),
                ("speed", PawControlSpeedSensor, 7),
                ("gps_accuracy", PawControlGPSAccuracySensor, 6),
                ("gps_battery_level", PawControlGPSBatteryLevelSensor, 5),
            ],
        },
        "health": {
            "basic": [
                ("health_status", PawControlHealthStatusSensor, 8),
                ("weight", PawControlWeightSensor, 7),
            ],
            "standard": [
                ("health_status", PawControlHealthStatusSensor, 8),
                ("weight", PawControlWeightSensor, 7),
                ("weight_trend", PawControlWeightTrendSensor, 6),
            ],
            "health_focus": [
                ("health_status", PawControlHealthStatusSensor, 9),
                ("weight", PawControlWeightSensor, 8),
                ("weight_trend", PawControlWeightTrendSensor, 7),
                ("body_condition_score", PawControlBodyConditionScoreSensor, 6),
                ("last_vet_visit", PawControlLastVetVisitSensor, 5),
                ("health_conditions", PawControlHealthConditionsSensor, 4),
                ("weight_goal_progress", PawControlWeightGoalProgressSensor, 3),
                ("daily_activity_level", PawControlDailyActivityLevelSensor, 2),
            ],
        },
    }

    # Create entities based on rules
    for module, enabled in modules.items():
        if not enabled or module not in module_entity_rules:
            continue

        if _is_budget_exhausted(budget):
            _LOGGER.debug(
                "Entity budget depleted for %s/%s; skipping remaining modules",
                dog_id,
                profile,
            )
            break

        # Get rules for this profile (with fallback to standard)
        profile_rules = module_entity_rules[module].get(
            profile, module_entity_rules[module].get("standard", [])
        )

        for entity_key, entity_class, priority in profile_rules:
            if _is_budget_exhausted(budget):
                _LOGGER.debug(
                    "Entity budget exhausted while building %s entities for %s/%s",
                    module,
                    dog_id,
                    profile,
                )
                break
            # Use entity factory to determine if entity should be created
            config = entity_factory.create_entity_config(
                dog_id=dog_id,
                entity_type="sensor",
                module=module,
                profile=profile,
                priority=priority,
                entity_key=entity_key,
            )

            if config:
                entity = entity_class(coordinator, dog_id, dog_name)
                entities.append(entity)

    return entities


async def _add_entities_optimized(
    async_add_entities: AddEntitiesCallback,
    all_entities: list[PawControlSensorBase],
    profile: str,
) -> None:
    """Add entities with profile-optimized batching."""
    total_entities = len(all_entities)

    if total_entities <= PARALLEL_THRESHOLD:
        # Small setup: Create all at once
        await async_call_add_entities(
            async_add_entities, all_entities, update_before_add=False
        )
    else:
        # Large setup: Use optimized batching
        for i in range(0, total_entities, MAX_ENTITIES_PER_BATCH):
            batch = all_entities[i : i + MAX_ENTITIES_PER_BATCH]
            await async_call_add_entities(
                async_add_entities, batch, update_before_add=False
            )

            # Small delay between batches for system stability
            if i + MAX_ENTITIES_PER_BATCH < total_entities:
                await asyncio.sleep(ENTITY_CREATION_DELAY)


def _log_setup_metrics(
    all_entities: list[PawControlSensorBase],
    dogs: list[DogConfigData],
    profile: str,
    entity_factory: EntityFactory,
) -> None:
    """Log setup performance metrics."""
    total_entities = len(all_entities)
    avg_entities_per_dog = total_entities / len(dogs) if dogs else 0

    profile_info: EntityProfileDefinition | None = None
    if hasattr(entity_factory, "get_profile_info"):
        try:
            profile_info = entity_factory.get_profile_info(profile)
        except Exception:  # pragma: no cover - defensive for mock objects
            profile_info = None

    raw_max_entities: object = (
        getattr(profile_info, "max_entities", 0) if profile_info is not None else 0
    )
    if isinstance(raw_max_entities, (int, float, str)):
        try:
            max_entities = int(raw_max_entities)
        except (TypeError, ValueError):
            max_entities = 0
    else:
        max_entities = 0

    max_possible = max_entities * len(dogs)
    efficiency = (
        (max_possible - total_entities) / max_possible * 100 if max_possible > 0 else 0
    )

    _LOGGER.info(
        "Sensor setup complete: %d entities for %d dogs (avg %.1f/dog) - "
        "Profile: %s, Efficiency: %.1f%% resource savings",
        total_entities,
        len(dogs),
        avg_entities_per_dog,
        profile,
        efficiency,
    )


class PawControlSensorBase(PawControlEntity, SensorEntityProtocol):
    """Base sensor class with optimized data access and thread-safe caching."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        sensor_type: str,
        *,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        unit_of_measurement: str | None = None,
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
        translation_key: str | None = None,
    ) -> None:
        """Initialize base sensor with performance optimizations."""
        super().__init__(coordinator, dog_id, dog_name)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"pawcontrol_{dog_id}_{sensor_type}"
        self._pending_translation_key = translation_key or sensor_type
        self._attr_translation_key: str | None = None
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_unit_of_measurement_translation_key = None
        self._attr_icon = icon
        self._attr_entity_category = entity_category

        # Link entity to PawControl device entry for the dog
        self.update_device_metadata(model="Virtual Dog", sw_version="1.0.0")

        # OPTIMIZED: Thread-safe instance-level caching system
        self._data_cache: dict[str, CoordinatorDogData | None] = {}
        self._cache_timestamp: datetime | None = None
        self._cache_ttl = 30  # 30 seconds cache TTL

    def _get_dog_data(self) -> CoordinatorDogData | None:
        """Get dog data from coordinator with thread-safe caching."""
        cache_key = f"dog_data_{self._dog_id}"
        now = dt_util.utcnow()

        # Check cache validity
        if (
            self._cache_timestamp
            and cache_key in self._data_cache
            and (now - self._cache_timestamp).total_seconds() < self._cache_ttl
        ):
            return self._data_cache[cache_key]

        # Fetch fresh data
        if not self.coordinator.available:
            return None

        dog_data = self.coordinator.get_dog_data(self._dog_id)
        if not isinstance(dog_data, Mapping):
            dog_data = cast(CoordinatorDogData | None, dog_data)

        # Update cache
        self._data_cache[cache_key] = cast(CoordinatorDogData | None, dog_data)
        self._cache_timestamp = now

        return cast(CoordinatorDogData | None, dog_data)

    @staticmethod
    def _coerce_module_payload(
        module_data: object | None,
    ) -> CoordinatorModuleLookupResult:
        """Return a mapping payload regardless of adapter state."""

        if isinstance(module_data, Mapping):
            return cast(CoordinatorModuleLookupResult, module_data)
        return cast(CoordinatorUntypedModuleState, {})

    @staticmethod
    def _coerce_float(value: object, default: float = 0.0) -> float:
        """Return a float converted from ``value`` when possible."""

        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return default
        return default

    @staticmethod
    def _coerce_int(value: object, default: int = 0) -> int:
        """Return an int converted from ``value`` when possible."""

        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return default
        return default

    @staticmethod
    def _coerce_utc_datetime(value: object | None) -> datetime | None:
        """Return an aware UTC datetime when ``value`` is convertible."""

        if isinstance(value, (datetime, date, str, int, float, Real)) or value is None:
            return ensure_utc_datetime(value)
        return None

    @staticmethod
    def _coerce_feeding_payload(
        payload: CoordinatorModuleLookupResult,
    ) -> FeedingModulePayload | None:
        """Return a feeding payload when the mapping is compatible."""

        if isinstance(payload, Mapping):
            return cast(FeedingModulePayload, payload)
        return None

    @staticmethod
    def _coerce_walk_payload(
        payload: CoordinatorModuleLookupResult,
    ) -> WalkModuleTelemetry | None:
        """Return a walk payload when the mapping is compatible."""

        if isinstance(payload, Mapping):
            return cast(WalkModuleTelemetry, payload)
        return None

    @staticmethod
    def _coerce_gps_payload(
        payload: CoordinatorModuleLookupResult,
    ) -> GPSModulePayload | None:
        """Return a GPS payload when the mapping is compatible."""

        return ensure_gps_payload(payload) if isinstance(payload, Mapping) else None

    @staticmethod
    def _coerce_health_payload(
        payload: CoordinatorModuleLookupResult,
    ) -> HealthModulePayload | None:
        """Return a health payload when the mapping is compatible."""

        if isinstance(payload, Mapping):
            return cast(HealthModulePayload, payload)
        return None

    def _get_feeding_module(self) -> FeedingModulePayload | None:
        """Return the feeding module payload when available."""

        return self._coerce_feeding_payload(self._get_module_data("feeding"))

    def _get_walk_module(self) -> WalkModuleTelemetry | None:
        """Return the walk module payload when available."""

        return self._coerce_walk_payload(self._get_module_data("walk"))

    def _get_gps_module(self) -> GPSModulePayload | None:
        """Return the GPS module payload when available."""

        return self._coerce_gps_payload(self._get_module_data("gps"))

    def _get_health_module(self) -> HealthModulePayload | None:
        """Return the health module payload when available."""

        return self._coerce_health_payload(self._get_module_data("health"))

    async def async_added_to_hass(self) -> None:
        """Populate translation data after the entity is registered."""

        await super().async_added_to_hass()

        if self._pending_translation_key and self._attr_translation_key is None:
            self._attr_translation_key = self._pending_translation_key

    def _base_attributes(self) -> AttributeDict:
        """Return a copy of the base extra state attributes."""

        base = cast(
            AttributeDict,
            PawControlSensorBase.extra_state_attributes.__get__(self, type(self)),
        )
        return cast(AttributeDict, dict(base) if base else {})

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Expose the configured device class for test doubles."""

        return getattr(self, "_attr_device_class", None)

    @property
    def state_class(self) -> SensorStateClass | None:
        """Expose the configured state class for test doubles."""

        return getattr(self, "_attr_state_class", None)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Expose the configured native unit for test doubles."""

        return getattr(self, "_attr_native_unit_of_measurement", None)

    @property
    def state(self) -> Any:
        """Expose the sensor state for compatibility with legacy inspectors."""

        return self.native_value

    def _get_module_data(self, module: str) -> CoordinatorModuleLookupResult:
        """Return coordinator module data with strict mapping validation."""

        if not isinstance(module, str) or not module:
            return cast(CoordinatorUntypedModuleState, {})

        try:
            payload = self.coordinator.get_module_data(self._dog_id, module)
        except Exception as err:  # pragma: no cover - defensive log path
            _LOGGER.error(
                "Error fetching module data for %s/%s: %s", self._dog_id, module, err
            )
            return cast(CoordinatorUntypedModuleState, {})

        if not isinstance(payload, Mapping):
            _LOGGER.warning(
                "Invalid module payload for %s/%s: expected mapping, got %s",
                self._dog_id,
                module,
                type(payload).__name__,
            )
            return cast(CoordinatorUntypedModuleState, {})

        if _is_typed_sensor_module(module):
            return cast(CoordinatorModuleState, payload)

        return cast(CoordinatorModuleLookupResult, payload)

    @property
    def available(self) -> bool:
        """Return True if the coordinator and dog data are available."""
        return self.coordinator.available and self._get_dog_data() is not None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for the sensor."""
        attrs: AttributeDict = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "sensor_type": self._sensor_type,
        }

        try:
            dog_data = self._get_dog_data()
            if dog_data and "dog_info" in dog_data:
                dog_info = dog_data["dog_info"]
                attrs.update(
                    {
                        "dog_breed": dog_info.get("dog_breed", ""),
                        "dog_age": dog_info.get("dog_age"),
                        "dog_size": dog_info.get("dog_size"),
                        "dog_weight": dog_info.get("dog_weight"),
                    }
                )
        except Exception as err:
            _LOGGER.debug("Could not fetch dog info for attributes: %s", err)

        last_update = getattr(self.coordinator, "last_update_success_time", None)
        if isinstance(last_update, datetime):
            attrs["last_updated"] = dt_util.as_local(last_update).isoformat()
        else:
            attrs["last_updated"] = None

        return _normalise_attributes(attrs)


class PawControlGardenSensorBase(PawControlSensorBase):
    """Base class for garden tracking sensors."""

    _module_name = "garden"

    def _get_garden_data(self) -> GardenModulePayload:
        """Return garden snapshot data for the current dog."""

        module_data = self._get_module_data(self._module_name)
        if module_data:
            return cast(GardenModulePayload, module_data)

        garden_manager = self._get_runtime_managers().garden_manager
        if garden_manager is not None:
            try:
                return garden_manager.build_garden_snapshot(self._dog_id)
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.debug(
                    "Garden snapshot fallback failed for %s: %s", self._dog_id, err
                )

        return cast(GardenModulePayload, {})

    def _garden_attributes(self) -> AttributeDict:
        """Build shared garden attributes for subclasses."""

        data = self._get_garden_data()
        attrs: AttributeDict = {
            "garden_status": data.get("status"),
            "sessions_today": data.get("sessions_today"),
            "time_today_minutes": data.get("time_today_minutes"),
            "poop_today": data.get("poop_today"),
            "activities_today": data.get("activities_today"),
            "activities_total": data.get("activities_total"),
        }

        last_session = data.get("last_session") or {}
        if last_session:
            attrs.update(
                {
                    "last_session_id": last_session.get("session_id"),
                    "last_session_start": last_session.get("start_time"),
                    "last_session_end": last_session.get("end_time"),
                    "last_session_duration": last_session.get("duration_minutes"),
                    "last_session_activities": last_session.get("activity_count"),
                    "last_session_poop": last_session.get("poop_count"),
                    "last_session_status": last_session.get("status"),
                    "last_session_weather": last_session.get("weather_conditions"),
                }
            )

        stats = data.get("stats") or {}
        if stats:
            attrs["last_garden_visit"] = stats.get("last_garden_visit")
            attrs["favorite_garden_activities"] = cast(
                JSONValue, stats.get("favorite_activities")
            )
            attrs["weekly_summary"] = cast(JSONValue, stats.get("weekly_summary"))

        weather_summary = data.get("weather_summary")
        if weather_summary:
            attrs["weather_summary"] = cast(JSONValue, weather_summary)

        pending = data.get("pending_confirmations")
        if pending is not None:
            attrs["pending_confirmations"] = cast(JSONValue, pending)

        attrs["hours_since_last_session"] = data.get("hours_since_last_session")

        return _normalise_attributes(attrs)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        attrs.update(self._garden_attributes())
        return _normalise_attributes(attrs)


class PawControlDietValidationSensorBase(PawControlSensorBase):
    """Base class for diet validation sensors."""

    _module_name = "feeding"

    def _get_validation_summary(self) -> FeedingDietValidationSummary | None:
        """Return diet validation summary for the current dog."""

        module_data = self._get_module_data(self._module_name)
        if not module_data:
            return None

        summary = module_data.get("diet_validation_summary")
        if isinstance(summary, Mapping):
            return cast(FeedingDietValidationSummary, dict(summary))
        return None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        summary = self._get_validation_summary()
        if summary:
            attrs.update(
                {
                    "diet_validation_available": True,
                    "diet_conflict_count": summary.get("conflict_count", 0),
                    "diet_warning_count": summary.get("warning_count", 0),
                    "diet_total_special_requirements": summary.get("total_diets", 0),
                    "diet_compatibility_score": summary.get("compatibility_score"),
                    "diet_compatibility_level": summary.get("compatibility_level"),
                    "diet_validation_adjustment": summary.get(
                        "diet_validation_adjustment", 1.0
                    ),
                    "diet_adjustment_direction": summary.get("adjustment_direction"),
                    "diet_adjustment_safety_factor": summary.get("safety_factor"),
                    "diet_vet_consultation": summary.get(
                        "vet_consultation_state", "not_needed"
                    ),
                    "diet_consultation_urgency": summary.get(
                        "consultation_urgency", "none"
                    ),
                }
            )
        else:
            attrs["diet_validation_available"] = False

        return _normalise_attributes(attrs)


# Core Sensor Implementations


@register_sensor("last_action")
class PawControlLastActionSensor(PawControlSensorBase):
    """Sensor for tracking the last action timestamp."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Action Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_action",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:clock-outline",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the most recent action timestamp."""
        dog_data = self._get_dog_data()
        if not dog_data:
            return None

        timestamps: list[datetime] = []

        # Collect timestamps from all modules
        for module in ["feeding", "walk", "health"]:
            module_data = dog_data.get(module, {})
            if not isinstance(module_data, dict):
                continue

            timestamp_key = (
                f"last_{module}" if module != "health" else "last_health_entry"
            )
            timestamp_value = module_data.get(timestamp_key)

            if timestamp_value:
                timestamp = self._coerce_utc_datetime(timestamp_value)
                if timestamp is not None:
                    timestamps.append(timestamp)
                else:
                    _LOGGER.debug(
                        "Invalid timestamp in %s: %s", module, timestamp_value
                    )

        return max(timestamps) if timestamps else None


@register_sensor("status")
class PawControlDogStatusSensor(PawControlSensorBase):
    """Sensor for overall dog status with enhanced logic."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Dog Status Sensor."""
        super().__init__(coordinator, dog_id, dog_name, "status", icon="mdi:dog")

    @property
    def native_value(self) -> str:
        """Return the current status of the dog."""
        dog_data = self._get_dog_data()
        if not dog_data:
            return _STATE_UNKNOWN

        try:
            walk_data: WalkModuleTelemetry = cast(
                WalkModuleTelemetry, self._get_walk_module() or {}
            )
            feeding_data: FeedingModulePayload = cast(
                FeedingModulePayload, self._get_feeding_module() or {}
            )
            gps_data: GPSModulePayload = cast(
                GPSModulePayload, self._get_gps_module() or {}
            )

            # Priority-based status determination
            if walk_data.get("walk_in_progress", False):
                return "walking"

            current_zone = gps_data.get("zone", STATE_UNKNOWN)

            if current_zone == "home":
                if feeding_data.get("is_hungry", False):
                    return "hungry"
                if walk_data.get("needs_walk", False):
                    return "needs_walk"
                return "home"
            if (
                isinstance(current_zone, str)
                and current_zone
                and current_zone != _STATE_UNKNOWN
            ):
                return f"at_{current_zone}"
            return "away"

        except Exception as err:
            _LOGGER.warning(
                "Error determining dog status for %s: %s", self._dog_id, err
            )
            return _STATE_UNKNOWN


@register_sensor("activity_score")
class PawControlActivityScoreSensor(PawControlSensorBase):
    """Sensor for calculating activity score with optimized performance."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Activity Score Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "activity_score",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:chart-line",
        )
        # PLATINUM: Dynamic cache TTL based on coordinator update interval
        self._dynamic_cache_ttl = get_activity_score_cache_ttl(coordinator)
        self._cached_score: float | None = None
        self._score_cache_time: datetime | None = None

    @property
    def native_value(self) -> float | None:
        """Calculate and return the activity score with optimized caching."""
        now = dt_util.utcnow()

        # Check cache validity with dynamic TTL
        if (
            self._cached_score is not None
            and self._score_cache_time is not None
            and (now - self._score_cache_time).total_seconds() < self._dynamic_cache_ttl
        ):
            return self._cached_score

        dog_data = self._get_dog_data()
        if not dog_data:
            return None

        try:
            score = self._compute_activity_score_optimized(dog_data)

            if score is not None:
                self._cached_score = score
                self._score_cache_time = now

            return score

        except Exception as err:
            _LOGGER.warning(
                "Error calculating activity score for %s: %s", self._dog_id, err
            )
            return None

    def _compute_activity_score_optimized(
        self, dog_data: CoordinatorDogData
    ) -> float | None:
        """PLATINUM: Compute activity score with memory-efficient single-pass algorithm."""
        weighted_sum = 0.0
        total_weight = 0.0

        walk_payload = self._coerce_module_payload(dog_data.get("walk"))
        if walk_payload:
            try:
                score = self._calculate_walk_score(
                    cast(WalkModuleTelemetry, walk_payload)
                )
                if score is not None:
                    weighted_sum += score * 0.4
                    total_weight += 0.4
            except (TypeError, ValueError, KeyError) as err:
                _LOGGER.debug(
                    "Activity score calculation error for %s module %s: %s",
                    self._dog_id,
                    "walk",
                    err,
                )

        feeding_payload = self._coerce_module_payload(dog_data.get("feeding"))
        if feeding_payload:
            try:
                score = self._calculate_feeding_score(
                    cast(FeedingModulePayload, feeding_payload)
                )
                if score is not None:
                    weighted_sum += score * 0.2
                    total_weight += 0.2
            except (TypeError, ValueError, KeyError) as err:
                _LOGGER.debug(
                    "Activity score calculation error for %s module %s: %s",
                    self._dog_id,
                    "feeding",
                    err,
                )

        gps_payload = self._coerce_module_payload(dog_data.get("gps"))
        if gps_payload:
            try:
                score = self._calculate_gps_score(cast(GPSModulePayload, gps_payload))
                if score is not None:
                    weighted_sum += score * 0.25
                    total_weight += 0.25
            except (TypeError, ValueError, KeyError) as err:
                _LOGGER.debug(
                    "Activity score calculation error for %s module %s: %s",
                    self._dog_id,
                    "gps",
                    err,
                )

        health_payload = self._coerce_module_payload(dog_data.get("health"))
        if health_payload:
            try:
                score = self._calculate_health_score(
                    cast(HealthModulePayload, health_payload)
                )
                if score is not None:
                    weighted_sum += score * 0.15
                    total_weight += 0.15
            except (TypeError, ValueError, KeyError) as err:
                _LOGGER.debug(
                    "Activity score calculation error for %s module %s: %s",
                    self._dog_id,
                    "health",
                    err,
                )

        return round(weighted_sum / total_weight, 1) if total_weight > 0 else None

    def _calculate_walk_score(self, walk_data: WalkModuleTelemetry) -> float | None:
        """Calculate walk activity score with validation."""
        try:
            walks_today = int(walk_data.get("walks_today", 0))
            total_duration = float(walk_data.get("total_duration_today", 0))

            if walks_today == 0:
                return 0.0

            # OPTIMIZED: Simplified scoring algorithm
            walk_count_score = min(walks_today * 25, 75)  # Max 75 points for frequency
            duration_score = min(
                total_duration / 60 * 10, 25
            )  # Max 25 points for duration

            return walk_count_score + duration_score

        except (TypeError, ValueError):
            return None

    def _calculate_feeding_score(
        self, feeding_data: FeedingModulePayload
    ) -> float | None:
        """Calculate feeding regularity score."""
        try:
            adherence = self._coerce_float(
                feeding_data.get("feeding_schedule_adherence", 0), default=0.0
            )
            target_met = bool(feeding_data.get("daily_target_met", False))

            score = adherence
            if target_met:
                score += 20

            return min(score, 100)

        except (TypeError, ValueError):
            return None

    def _calculate_gps_score(self, gps_data: GPSModulePayload) -> float | None:
        """Calculate GPS activity score."""
        try:
            if not gps_data.get("last_seen"):
                return 0.0
            return 80.0 if gps_data.get("zone") else 0.0

        except (TypeError, ValueError):
            return None

    def _calculate_health_score(self, health_data: HealthModulePayload) -> float | None:
        """Calculate health maintenance score."""
        try:
            status = health_data.get("health_status", "good")
            if not isinstance(status, str):
                status = "good"
            # OPTIMIZED: Pre-calculated score mapping
            score_map = {
                "excellent": 100,
                "very_good": 90,
                "good": 80,
                "normal": 70,
                "unwell": 40,
                "sick": 20,
            }
            return float(score_map.get(status, 70))

        except (TypeError, ValueError):
            return None


# NEW: Critical missing sensor per requirements inventory
@register_sensor("activity_level")
class PawControlActivityLevelSensor(PawControlSensorBase):
    """Sensor for current activity level classification.

    NEW: This sensor was identified as missing in requirements_inventory.md
    and marked as critical. Provides categorical activity level (low/medium/high).
    """

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Activity Level Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "activity_level",
            icon="mdi:speedometer",
        )

    @property
    def native_value(self) -> str:
        """Return current activity level classification."""
        dog_data = self._get_dog_data()
        if not dog_data:
            return _STATE_UNKNOWN

        try:
            health_data: HealthModulePayload = cast(
                HealthModulePayload, self._get_health_module() or {}
            )
            activity_state = health_data.get("activity_level")
            if isinstance(activity_state, str) and activity_state:
                return activity_state

            # Get current activity metrics
            walk_data: WalkModuleTelemetry = cast(
                WalkModuleTelemetry, self._get_walk_module() or {}
            )
            gps_data: GPSModulePayload = cast(
                GPSModulePayload, self._get_gps_module() or {}
            )

            # Check if currently walking
            if walk_data.get("walk_in_progress", False):
                current_speed = self._coerce_float(
                    gps_data.get("current_speed", 0), default=0.0
                )
                if current_speed > 8:  # km/h - running
                    return "high"
                if current_speed > 3:  # km/h - fast walk
                    return "medium"
                return "low"

            # Calculate based on recent activity (today)
            walks_today = self._coerce_int(walk_data.get("walks_today", 0))
            total_duration = self._coerce_float(
                walk_data.get("total_duration_today", 0)
            )
            total_distance = self._coerce_float(
                walk_data.get("total_distance_today", 0)
            )

            # Calculate activity intensity score
            if walks_today == 0:
                return activity_state if isinstance(activity_state, str) else "inactive"

            # Weighted scoring: walks * duration * distance
            activity_score = (
                (walks_today * 0.3)
                + (total_duration / 60 * 0.4)
                + (total_distance / 1000 * 0.3)
            )

            if activity_score >= 3:
                return "high"
            if activity_score >= 1.5:
                return "medium"
            if activity_score > 0:
                return "low"
            return "inactive"

        except (TypeError, ValueError) as err:
            _LOGGER.debug(
                "Error calculating activity level for %s: %s", self._dog_id, err
            )
            if isinstance(activity_state, str) and activity_state:
                return activity_state
            return _STATE_UNKNOWN

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for activity level sensor."""
        attrs: AttributeDict = self._base_attributes()

        dog_data = self._get_dog_data()
        if dog_data:
            walk_data = self._coerce_module_payload(dog_data.get("walk"))
            gps_data = self._coerce_module_payload(dog_data.get("gps"))

            with contextlib.suppress(TypeError, ValueError):
                speed_value = gps_data.get("current_speed", 0)
                duration_value = walk_data.get("total_duration_today", 0)
                distance_value = walk_data.get("total_distance_today", 0)
                walks_today = walk_data.get("walks_today", 0)
                walk_payload = cast(WalkModuleTelemetry, walk_data)
                attrs.update(
                    {
                        "walk_in_progress": bool(
                            walk_data.get("walk_in_progress", False)
                        ),
                        "current_speed_kmh": self._coerce_float(speed_value),
                        "walks_today": self._coerce_int(walks_today),
                        "total_duration_minutes": self._coerce_float(duration_value),
                        "total_distance_meters": self._coerce_float(distance_value),
                        "activity_recommendation": self._get_activity_recommendation(
                            walk_payload
                        ),
                    }
                )

        return _normalise_attributes(attrs)

    def _get_activity_recommendation(self, walk_data: WalkModuleTelemetry) -> str:
        """Get activity recommendation based on current level."""
        try:
            walks_today = int(walk_data.get("walks_today", 0))
            total_duration = float(walk_data.get("total_duration_today", 0))

            if walks_today == 0:
                return "schedule_first_walk"
            if walks_today < 2:
                return "needs_more_walks"
            if total_duration < 30:
                return "extend_walk_duration"
            return "activity_goals_met"

        except (TypeError, ValueError):
            return "unable_to_assess"


# Garden Sensors


@register_sensor("garden_time_today")
class PawControlGardenTimeTodaySensor(PawControlGardenSensorBase):
    """Sensor for tracking garden time today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Garden Time Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "garden_time_today",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:timer-sand",
            translation_key="garden_time_today",
        )

    @property
    def native_value(self) -> float | None:
        """Return the native value reported by this sensor."""
        data = self._get_garden_data()
        value = data.get("time_today_minutes")
        if is_number(value):
            numeric_value = cast(float | int | str, value)
            return round(float(numeric_value), 2)
        return None


@register_sensor("garden_sessions_today")
class PawControlGardenSessionsTodaySensor(PawControlGardenSensorBase):
    """Sensor for counting garden sessions today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Garden Sessions Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "garden_sessions_today",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:flower",
            translation_key="garden_sessions_today",
        )

    @property
    def native_value(self) -> int | None:
        """Return the native value reported by this sensor."""
        data = self._get_garden_data()
        value = data.get("sessions_today")
        if is_number(value):
            return int(float(value))
        return None


@register_sensor("garden_poop_count_today")
class PawControlGardenPoopCountTodaySensor(PawControlGardenSensorBase):
    """Sensor for poop events recorded in the garden today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Garden Poop Count Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "garden_poop_count_today",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:emoticon-poop",
            translation_key="garden_poop_count_today",
        )

    @property
    def native_value(self) -> int | None:
        """Return the native value reported by this sensor."""
        data = self._get_garden_data()
        value = data.get("poop_today")
        if is_number(value):
            return int(float(value))
        return None


@register_sensor("last_garden_session")
class PawControlLastGardenSessionSensor(PawControlGardenSensorBase):
    """Sensor reporting the end of the last garden session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Garden Session Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_garden_session",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:calendar-clock",
            translation_key="last_garden_session",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the native value reported by this sensor."""
        data = self._get_garden_data()
        last_session = data.get("last_session")
        if not last_session:
            return None

        timestamp = last_session.get("end_time") or last_session.get("start_time")
        return ensure_utc_datetime(timestamp)


@register_sensor("garden_activities_count")
class PawControlGardenActivitiesCountSensor(PawControlGardenSensorBase):
    """Sensor tracking the total number of garden activities."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Garden Activities Count Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "garden_activities_count",
            icon="mdi:counter",
            translation_key="garden_activities_count",
        )

    @property
    def native_value(self) -> int | None:
        """Return the native value reported by this sensor."""
        data = self._get_garden_data()
        value = data.get("activities_total")
        if is_number(value):
            return int(float(value))
        return None


@register_sensor("avg_garden_duration")
class PawControlAverageGardenDurationSensor(PawControlGardenSensorBase):
    """Sensor reporting the average garden session duration."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Average Garden Duration Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "avg_garden_duration",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:chart-arc",
            translation_key="avg_garden_duration",
        )

    @property
    def native_value(self) -> float | None:
        """Return the native value reported by this sensor."""
        stats = self._get_garden_data().get("stats") or {}
        value = stats.get("average_session_duration")
        if is_number(value):
            numeric_value = cast(float | int | str, value)
            return round(float(numeric_value), 2)
        return None


@register_sensor("garden_stats_weekly")
class PawControlGardenStatsWeeklySensor(PawControlGardenSensorBase):
    """Sensor summarizing weekly garden statistics."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Garden Stats Weekly Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "garden_stats_weekly",
            icon="mdi:calendar-week",
            translation_key="garden_stats_weekly",
        )

    @property
    def native_value(self) -> str | None:
        """Return the native value reported by this sensor."""
        summary = self._get_garden_data().get("stats", {}).get("weekly_summary")
        if not summary or not summary.get("session_count"):
            return None

        session_count = summary.get("session_count", 0)
        total_time = summary.get("total_time_minutes", 0)
        return f"{session_count} sessions / {total_time:.1f} min"


@register_sensor("favorite_garden_activities")
class PawControlFavoriteGardenActivitiesSensor(PawControlGardenSensorBase):
    """Sensor listing favorite garden activities."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Favorite Garden Activities Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "favorite_garden_activities",
            icon="mdi:format-list-bulleted",
            translation_key="favorite_garden_activities",
        )

    @property
    def native_value(self) -> str | None:
        """Return the native value reported by this sensor."""
        favorites = (
            self._get_garden_data().get("stats", {}).get("favorite_activities", [])
        )
        if not favorites:
            return None

        names = [item.get("activity", "unknown") for item in favorites]
        return ", ".join(names)


@register_sensor("last_garden_duration")
class PawControlLastGardenDurationSensor(PawControlGardenSensorBase):
    """Sensor reporting the duration of the last garden session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Garden Duration Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_garden_duration",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:timer",
            translation_key="last_garden_duration",
        )

    @property
    def native_value(self) -> float | None:
        """Return the native value reported by this sensor."""
        last_session = self._get_garden_data().get("last_session")
        if not last_session:
            return None

        duration = last_session.get("duration_minutes")
        if is_number(duration):
            return round(float(duration), 2)
        return None


@register_sensor("garden_activities_last_session")
class PawControlGardenActivitiesLastSessionSensor(PawControlGardenSensorBase):
    """Sensor counting activities recorded in the last session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Garden Activities Last Session Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "garden_activities_last_session",
            icon="mdi:chart-bubble",
            translation_key="garden_activities_last_session",
        )

    @property
    def native_value(self) -> int | None:
        """Return the native value reported by this sensor."""
        last_session = self._get_garden_data().get("last_session")
        if not last_session:
            return None

        activity_count = last_session.get("activity_count")
        if is_number(activity_count):
            return int(float(activity_count))
        return None


@register_sensor("garden_activities_today")
class PawControlGardenActivitiesTodaySensor(PawControlGardenSensorBase):
    """Sensor tracking garden activities for the current day."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Garden Activities Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "garden_activities_today",
            icon="mdi:paw",
            translation_key="garden_activities_today",
        )

    @property
    def native_value(self) -> int | None:
        """Return the native value reported by this sensor."""
        data = self._get_garden_data()
        value = data.get("activities_today")
        if is_number(value):
            return int(float(value))
        return None


@register_sensor("last_garden_session_hours")
class PawControlLastGardenSessionHoursSensor(PawControlGardenSensorBase):
    """Sensor reporting hours since the last garden session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Garden Session Hours Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_garden_session_hours",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:timer-sand-complete",
            translation_key="last_garden_session_hours",
        )

    @property
    def native_value(self) -> float | None:
        """Return the native value reported by this sensor."""
        data = self._get_garden_data()
        value = data.get("hours_since_last_session")
        if is_number(value):
            numeric_value = cast(float | int | str, value)
            return round(float(numeric_value), 2)
        return None


# Feeding Sensors


@register_sensor("last_feeding")
class PawControlLastFeedingSensor(PawControlSensorBase):
    """Sensor for last feeding timestamp."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Feeding Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_feeding",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:food-drumstick",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the last feeding timestamp."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return None

        last_feeding = feeding_data.get("last_feeding")
        if not last_feeding:
            return None

        timestamp = self._coerce_utc_datetime(last_feeding)
        if timestamp is not None:
            return timestamp

        _LOGGER.debug("Invalid last_feeding timestamp: %s", last_feeding)

        return None


# NEW: Critical missing sensor per requirements inventory
@register_sensor("last_feeding_hours")
class PawControlLastFeedingHoursSensor(PawControlSensorBase):
    """Sensor for hours since last feeding.

    NEW: This sensor was identified as missing in requirements_inventory.md
    and marked as critical for automation purposes.
    """

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Feeding Hours Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_feeding_hours",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-outline",
            translation_key="last_feeding_hours",
        )

    @property
    def native_value(self) -> float | None:
        """Return hours since last feeding."""
        feeding_payload = self._get_feeding_module()
        if not feeding_payload:
            return None

        last_feeding = feeding_payload.get("last_feeding")
        if not last_feeding:
            return None

        try:
            last_feeding_dt = self._coerce_utc_datetime(last_feeding)
            if last_feeding_dt is None:
                return None

            now: datetime = dt_util.utcnow()
            time_delta: timedelta = now - last_feeding_dt
            hours_since = time_delta.total_seconds() / 3600

            return round(hours_since, 1)

        except (TypeError, ValueError) as err:
            _LOGGER.debug(
                "Error calculating hours since last feeding for %s: %s",
                self._dog_id,
                err,
            )
            return None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for hours since feeding sensor."""
        attrs: AttributeDict = self._base_attributes()

        feeding_payload = self._get_feeding_module()
        if feeding_payload:
            with contextlib.suppress(TypeError, ValueError):
                last_feeding = feeding_payload.get("last_feeding")
                if last_feeding:
                    last_feeding_dt = self._coerce_utc_datetime(last_feeding)
                    if last_feeding_dt:
                        now = dt_util.utcnow()
                        time_delta = now - last_feeding_dt

                        attrs.update(
                            {
                                "last_feeding_timestamp": last_feeding_dt.isoformat(),
                                "minutes_since_feeding": round(
                                    time_delta.total_seconds() / 60, 1
                                ),
                                "feeding_status": self._get_feeding_status(time_delta),
                                "next_feeding_due": self._calculate_next_feeding_due(
                                    feeding_payload, last_feeding_dt
                                ),
                            }
                        )

        return _normalise_attributes(attrs)

    def _get_feeding_status(self, time_delta: timedelta) -> str:
        """Get feeding status based on time since last feeding."""
        hours_since = time_delta.total_seconds() / 3600

        if hours_since < 2:
            return "recently_fed"
        if hours_since < 6:
            return "normal_interval"
        if hours_since < 12:
            return "getting_hungry"
        return "overdue"

    def _calculate_next_feeding_due(
        self, feeding_data: FeedingModulePayload, last_feeding: datetime
    ) -> str | None:
        """Calculate when next feeding is due."""
        try:
            config = feeding_data.get("config")
            if isinstance(config, Mapping):
                meals_per_day = self._coerce_int(config.get("meals_per_day", 2), 2)
            else:
                meals_per_day = 2
            if meals_per_day <= 0:
                return None

            hours_between_meals = 24 / meals_per_day
            next_feeding = last_feeding + timedelta(hours=hours_between_meals)

            return next_feeding.isoformat()

        except (TypeError, ValueError, KeyError):
            return None


@register_sensor("daily_calories")
class PawControlDailyCaloriesSensor(PawControlSensorBase):
    """Sensor for daily calorie intake."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Daily Calories Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "daily_calories",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=_CALORIE_UNIT,
            icon="mdi:fire",
            translation_key="daily_calories",
        )

    @property
    def native_value(self) -> float:
        """Return daily calorie intake."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return 0.0

        try:
            return self._coerce_float(feeding_data.get("total_calories_today", 0.0))
        except (TypeError, ValueError):
            return 0.0


@register_sensor("feeding_schedule_adherence")
class PawControlFeedingScheduleAdherenceSensor(PawControlSensorBase):
    """Sensor for feeding schedule adherence."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Feeding Schedule Adherence Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_schedule_adherence",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:calendar-check",
        )

    @property
    def native_value(self) -> float:
        """Return feeding schedule adherence percentage."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return 100.0

        try:
            return self._coerce_float(
                feeding_data.get("feeding_schedule_adherence", 100.0), default=100.0
            )
        except (TypeError, ValueError):
            return 100.0


@register_sensor("total_feedings_today")
class PawControlTotalFeedingsTodaySensor(PawControlSensorBase):
    """Sensor for total feedings today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Total Feedings Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "total_feedings_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
        )

    @property
    def native_value(self) -> int:
        """Return total feedings today."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return 0

        try:
            return self._coerce_int(feeding_data.get("total_feedings_today", 0))
        except (TypeError, ValueError):
            return 0


@register_sensor("health_aware_portion")
class PawControlHealthAwarePortionSensor(PawControlSensorBase):
    """Sensor for health-aware calculated portion size."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Health Aware Portion Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_aware_portion",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfMass.GRAMS,
            icon="mdi:scale",
            translation_key="health_aware_portion",
        )

    @property
    def native_value(self) -> float | None:
        """Return health-aware calculated portion size."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return None

        try:
            # Try health-aware portion first
            health_portion = feeding_data.get("health_aware_portion")
            if health_portion is not None:
                return round(self._coerce_float(health_portion), 1)

            # Fallback to basic calculation
            daily_amount = self._coerce_float(
                feeding_data.get("daily_amount_target", 500), default=500.0
            )
            config = feeding_data.get("config")
            meals_per_day = (
                self._coerce_int(config.get("meals_per_day", 2))
                if isinstance(config, Mapping)
                else 2
            )

            if meals_per_day > 0:
                return round(daily_amount / meals_per_day, 1)

        except (TypeError, ValueError, ZeroDivisionError):
            pass

        return None


@register_sensor("feeding_recommendation")
class PawControlFeedingRecommendationSensor(PawControlSensorBase):
    """Sensor for feeding recommendations based on health analysis."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Feeding Recommendation Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_recommendation",
            icon="mdi:lightbulb",
        )

    @property
    def native_value(self) -> str:
        """Return primary feeding recommendation."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return "No data available"

        try:
            # Get feeding analysis
            analysis = feeding_data.get("feeding_analysis")
            analysis_mapping = analysis if isinstance(analysis, Mapping) else {}
            recommendations = analysis_mapping.get("recommendations", [])

            if recommendations and isinstance(recommendations, list):
                return str(recommendations[0])  # Primary recommendation

            # Default based on adherence
            adherence = self._coerce_float(
                feeding_data.get("schedule_adherence", 100), default=100.0
            )
            if adherence >= 90:
                return "Feeding schedule is well maintained"
            if adherence >= 70:
                return "Consider improving meal timing consistency"
            return "Feeding schedule needs attention"

        except (TypeError, ValueError):
            return "Unable to generate recommendation"


@register_sensor("diet_validation_status")
class PawControlDietValidationStatusSensor(PawControlDietValidationSensorBase):
    """Sensor for overall diet validation status."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Diet Validation Status Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "diet_validation_status",
            icon="mdi:food-apple",
            translation_key="diet_validation_status",
        )

    @property
    def native_value(self) -> str:
        """Return diet validation status."""
        summary = self._get_validation_summary()
        if not summary:
            return "no_data"

        try:
            conflict_count = int(summary.get("conflict_count", 0))
            warning_count = int(summary.get("warning_count", 0))

            if conflict_count > 0:
                return "conflicts_detected"
            if warning_count > 0:
                return "warnings_present"
            return "validated_safe"

        except (TypeError, ValueError):
            return "validation_error"


@register_sensor("diet_conflict_count")
class PawControlDietConflictCountSensor(PawControlDietValidationSensorBase):
    """Sensor tracking the number of diet conflicts detected."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Diet Conflict Count Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "diet_conflict_count",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:alert-circle",
            translation_key="diet_conflict_count",
        )

    @property
    def native_value(self) -> int:
        """Return the native value reported by this sensor."""
        summary = self._get_validation_summary()
        if not summary:
            return 0
        try:
            return int(summary.get("conflict_count", 0))
        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        summary = self._get_validation_summary()
        if summary and summary.get("conflicts"):
            attrs["conflicts"] = summary.get("conflicts")
        return _normalise_attributes(attrs)


@register_sensor("diet_warning_count")
class PawControlDietWarningCountSensor(PawControlDietValidationSensorBase):
    """Sensor tracking warning count for diet combinations."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Diet Warning Count Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "diet_warning_count",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:alert",
            translation_key="diet_warning_count",
        )

    @property
    def native_value(self) -> int:
        """Return the native value reported by this sensor."""
        summary = self._get_validation_summary()
        if not summary:
            return 0
        try:
            return int(summary.get("warning_count", 0))
        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        summary = self._get_validation_summary()
        if summary and summary.get("warnings"):
            attrs["warnings"] = summary.get("warnings")
        return _normalise_attributes(attrs)


@register_sensor("diet_vet_consultation")
class PawControlDietVetConsultationSensor(PawControlDietValidationSensorBase):
    """Sensor indicating if veterinary consultation is recommended."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Diet Vet Consultation Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "diet_vet_consultation",
            icon="mdi:stethoscope",
            translation_key="diet_vet_consultation",
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> str:
        """Return the native value reported by this sensor."""
        summary = self._get_validation_summary()
        if not summary:
            return "not_needed"
        return str(summary.get("vet_consultation_state", "not_needed"))

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        summary = self._get_validation_summary()
        if summary:
            attrs.update(
                {
                    "vet_consultation_recommended": summary.get(
                        "vet_consultation_recommended", False
                    ),
                    "consultation_urgency": summary.get("consultation_urgency"),
                    "has_conflicts": summary.get("conflict_count", 0) > 0,
                }
            )
        return _normalise_attributes(attrs)


@register_sensor("diet_validation_adjustment")
class PawControlDietValidationAdjustmentSensor(PawControlDietValidationSensorBase):
    """Sensor reporting the diet validation adjustment factor."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Diet Validation Adjustment Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "diet_validation_adjustment",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:scale-balance",
            translation_key="diet_validation_adjustment",
        )

    @property
    def native_value(self) -> float:
        """Return the native value reported by this sensor."""
        summary = self._get_validation_summary()
        if not summary:
            return 1.0
        try:
            value = float(summary.get("diet_validation_adjustment", 1.0))
            return round(value, 3)
        except (TypeError, ValueError):
            return 1.0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        summary = self._get_validation_summary()
        if summary:
            attrs.update(
                {
                    "percentage_adjustment": summary.get("percentage_adjustment"),
                    "adjustment_info": summary.get("adjustment_info"),
                    "has_adjustments": summary.get("has_adjustments", False),
                }
            )
        return _normalise_attributes(attrs)


@register_sensor("diet_compatibility_score")
class PawControlDietCompatibilityScoreSensor(PawControlDietValidationSensorBase):
    """Sensor showing the overall diet compatibility score."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Diet Compatibility Score Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "diet_compatibility_score",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:heart-pulse",
            translation_key="diet_compatibility_score",
        )

    @property
    def native_value(self) -> float:
        """Return the native value reported by this sensor."""
        summary = self._get_validation_summary()
        if not summary:
            return 100.0
        try:
            score = float(summary.get("compatibility_score", 100.0))
            return round(score, 1)
        except (TypeError, ValueError):
            return 100.0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        summary = self._get_validation_summary()
        if summary:
            attrs["compatibility_level"] = summary.get("compatibility_level")
        return _normalise_attributes(attrs)


@register_sensor("daily_portions")
class PawControlDailyPortionsSensor(PawControlSensorBase):
    """Sensor for daily portions count."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Daily Portions Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "daily_portions",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
            translation_key="daily_portions",
        )

    @property
    def native_value(self) -> int:
        """Return number of portions given today."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return 0

        try:
            # Use total feedings as portions count
            portions = feeding_data.get(
                "total_portions_today", feeding_data.get("total_feedings_today", 0)
            )
            return self._coerce_int(portions)
        except (TypeError, ValueError):
            return 0


@register_sensor("portions_today")
class PawControlPortionsTodaySensor(PawControlSensorBase):
    """Sensor that reports the recorded portions served today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Portions Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "portions_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:bowl",
            translation_key="portions_today",
        )

    @property
    def native_value(self) -> int:
        """Return number of configured feeding portions completed today."""

        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return 0

        try:
            return self._coerce_int(feeding_data.get("portions_today", 0))
        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for portions sensor."""
        attrs: AttributeDict = self._base_attributes()

        feeding_data = self._get_feeding_module()
        if feeding_data:
            with contextlib.suppress(TypeError, ValueError):
                attrs.update(
                    {
                        "target_portions": self._coerce_int(
                            feeding_data.get("target_portions_per_day", 2)
                        ),
                        "remaining_portions": max(
                            0,
                            self._coerce_int(
                                feeding_data.get("target_portions_per_day", 2)
                            )
                            - self._coerce_int(
                                feeding_data.get("total_portions_today", 0)
                            ),
                        ),
                        "last_portion_time": feeding_data.get("last_feeding"),
                        "portion_schedule_adherence": self._coerce_float(
                            feeding_data.get("feeding_schedule_adherence", 100.0),
                            default=100.0,
                        ),
                    }
                )

        return _normalise_attributes(attrs)


@register_sensor("calorie_goal_progress")
class PawControlCalorieGoalProgressSensor(PawControlSensorBase):
    """Sensor for calorie goal progress percentage."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Calorie Goal Progress Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "calorie_goal_progress",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:progress-check",
            translation_key="calorie_goal_progress",
        )

    @property
    def native_value(self) -> float:
        """Return percentage progress towards daily calorie goal."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return 0.0

        try:
            calories_consumed = self._coerce_float(
                feeding_data.get("total_calories_today", 0.0)
            )
            calorie_target = self._coerce_float(
                feeding_data.get(
                    "daily_calorie_target",
                    feeding_data.get("target_calories_per_day", 1000.0),
                ),
                default=0.0,
            )

            if calorie_target <= 0:
                return 0.0

            progress = (calories_consumed / calorie_target) * 100
            return round(min(progress, 150.0), 1)  # Cap at 150% to show overfeeding

        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for calorie progress sensor."""
        attrs: AttributeDict = self._base_attributes()

        feeding_snapshot = self._get_feeding_module()
        if feeding_snapshot:
            with contextlib.suppress(TypeError, ValueError, ZeroDivisionError):
                calories_consumed = self._coerce_float(
                    feeding_snapshot.get("total_calories_today", 0.0)
                )
                calorie_target = self._coerce_float(
                    feeding_snapshot.get(
                        "daily_calorie_target",
                        feeding_snapshot.get("target_calories_per_day", 1000.0),
                    ),
                    default=0.0,
                )

                attrs.update(
                    {
                        "calories_consumed": calories_consumed,
                        "calorie_target": calorie_target,
                        "calories_remaining": max(
                            0, calorie_target - calories_consumed
                        ),
                        "over_target": calories_consumed > calorie_target,
                        "over_target_amount": max(
                            0, calories_consumed - calorie_target
                        ),
                        "target_met": calories_consumed >= calorie_target,
                        "progress_status": (
                            "over_target"
                            if calories_consumed > calorie_target * 1.1
                            else "on_target"
                            if calories_consumed >= calorie_target * 0.9
                            else "under_target"
                        ),
                    }
                )

        return _normalise_attributes(attrs)


@register_sensor("health_feeding_status")
class PawControlHealthFeedingStatusSensor(PawControlSensorBase):
    """Sensor reflecting overall health-aware feeding status."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Health Feeding Status Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_feeding_status",
            icon="mdi:heart-pulse",
            translation_key="health_feeding_status",
        )

    @property
    def native_value(self) -> str:
        """Return current health feeding status."""

        feeding_data = self._get_module_data("feeding")
        status = feeding_data.get("health_feeding_status") if feeding_data else None
        if not status:
            return "unknown"
        return str(status)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return diagnostic attributes for the health feeding status."""

        attrs: AttributeDict = self._base_attributes()
        feeding_payload = self._get_feeding_module()
        feeding_data: FeedingModulePayload = feeding_payload or cast(
            FeedingModulePayload, {}
        )
        attrs.update(
            {
                "daily_calorie_target": cast(
                    JSONValue, feeding_data.get("daily_calorie_target")
                ),
                "total_calories_today": cast(
                    JSONValue, feeding_data.get("total_calories_today")
                ),
                "portion_adjustment_factor": cast(
                    JSONValue, feeding_data.get("portion_adjustment_factor")
                ),
                "weight_goal": cast(JSONValue, feeding_data.get("weight_goal")),
                "emergency_active": bool(feeding_data.get("health_emergency", False)),
            }
        )
        emergency_details = feeding_data.get("health_emergency_details")
        if emergency_details is not None:
            attrs["emergency_details"] = cast(JSONValue, emergency_details)
        return _normalise_attributes(attrs)


@register_sensor("daily_calorie_target")
class PawControlDailyCalorieTargetSensor(PawControlSensorBase):
    """Sensor reporting the calculated daily calorie target."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Daily Calorie Target Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "daily_calorie_target",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=_CALORIE_UNIT,
            icon="mdi:fire",
            translation_key="daily_calorie_target",
        )

    @property
    def native_value(self) -> float | None:
        """Return the current calorie target in kcal."""

        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return None

        value = feeding_data.get("daily_calorie_target")
        if value is None:
            return None
        with contextlib.suppress(TypeError, ValueError):
            return round(self._coerce_float(value), 1)
        return None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        feeding_payload = self._get_feeding_module() or cast(FeedingModulePayload, {})
        health_summary = feeding_payload.get("health_summary")
        health_mapping = health_summary if isinstance(health_summary, Mapping) else {}
        attrs.update(
            {
                "calories_per_gram": cast(
                    JSONValue, feeding_payload.get("calories_per_gram")
                ),
                "health_source": cast(JSONValue, health_mapping.get("life_stage")),
            }
        )
        return _normalise_attributes(attrs)


@register_sensor("calories_consumed_today")
class PawControlCaloriesConsumedTodaySensor(PawControlSensorBase):
    """Sensor for calories consumed today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Calories Consumed Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "calories_consumed_today",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=_CALORIE_UNIT,
            icon="mdi:food-drumstick",
            translation_key="calories_consumed_today",
        )

    @property
    def native_value(self) -> float | None:
        """Return the native value reported by this sensor."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return None

        value = feeding_data.get("total_calories_today")
        if value is None:
            return None
        with contextlib.suppress(TypeError, ValueError):
            return round(self._coerce_float(value), 1)
        return None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        feeding_payload = self._get_feeding_module() or cast(FeedingModulePayload, {})
        attrs.update(
            {
                "daily_calorie_target": cast(
                    JSONValue, feeding_payload.get("daily_calorie_target")
                ),
                "calorie_goal_progress": cast(
                    JSONValue, feeding_payload.get("calorie_goal_progress")
                ),
            }
        )
        return _normalise_attributes(attrs)


@register_sensor("portion_adjustment_factor")
class PawControlPortionAdjustmentFactorSensor(PawControlSensorBase):
    """Sensor exposing the calculated portion adjustment factor."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Portion Adjustment Factor Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "portion_adjustment_factor",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:scale-balance",
            translation_key="portion_adjustment_factor",
        )

    @property
    def native_value(self) -> float | None:
        """Return the native value reported by this sensor."""
        feeding_data = self._get_feeding_module()
        if not feeding_data:
            return None

        factor = feeding_data.get("portion_adjustment_factor")
        if factor is None:
            return None
        with contextlib.suppress(TypeError, ValueError):
            return round(self._coerce_float(factor), 2)
        return None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        feeding_payload = self._get_feeding_module()
        if feeding_payload:
            attrs.update(
                {
                    "weight_goal": cast(JSONValue, feeding_payload.get("weight_goal")),
                    "health_conditions": cast(
                        JSONValue, feeding_payload.get("health_conditions", [])
                    ),
                    "calories_per_gram": cast(
                        JSONValue, feeding_payload.get("calories_per_gram")
                    ),
                }
            )

        return _normalise_attributes(attrs)


@register_sensor("food_consumption")
class PawControlFoodConsumptionSensor(PawControlSensorBase):
    """Sensor for food consumption tracking."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Food Consumption Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "food_consumption",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfMass.GRAMS,
            icon="mdi:food-drumstick",
            translation_key="food_consumption",
        )

    @property
    def native_value(self) -> float:
        """Return total food consumption today in grams."""
        feeding_payload = self._get_feeding_module()
        if not feeding_payload:
            return 0.0

        total_consumption = self._coerce_float(
            feeding_payload.get("total_food_consumed_today", 0.0)
        )

        # Fallback calculation from feedings if total not available
        if total_consumption == 0.0:
            feedings_today = feeding_payload.get("feedings_today")
            if isinstance(feedings_today, list):
                for feeding in feedings_today:
                    if isinstance(feeding, Mapping):
                        amount = self._coerce_float(feeding.get("amount", 0.0))
                        total_consumption += amount

        return round(total_consumption, 1)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for food consumption sensor."""
        attrs: AttributeDict = self._base_attributes()

        feeding_payload = self._get_feeding_module()
        if feeding_payload:
            feedings = feeding_payload.get("feedings_today")
            feedings_list: list[Mapping[str, object]] = (
                [feeding for feeding in feedings if isinstance(feeding, Mapping)]
                if isinstance(feedings, list)
                else []
            )
            food_types: set[str] = set()
            meal_types: set[str] = set()

            for feeding in feedings_list:
                food_type = feeding.get("food_type")
                meal_type = feeding.get("meal_type")
                if isinstance(food_type, str) and food_type:
                    food_types.add(food_type)
                if isinstance(meal_type, str) and meal_type:
                    meal_types.add(meal_type)

            target_daily = self._coerce_float(
                feeding_payload.get("daily_amount_target", 500.0), default=500.0
            )
            consumed = self._coerce_float(
                feeding_payload.get("total_food_consumed_today", 0.0)
            )

            remaining = max(0.0, target_daily - consumed)
            feedings_count = len(feedings_list)
            average_portion = (
                round(consumed / feedings_count, 1) if feedings_count else 0.0
            )

            attrs.update(
                {
                    "target_daily_grams": target_daily,
                    "remaining_grams": remaining,
                    "consumption_percentage": round((consumed / target_daily) * 100, 1)
                    if target_daily > 0
                    else 0.0,
                    "food_types_today": sorted(list(food_types)),
                    "meal_types_today": sorted(list(meal_types)),
                    "feedings_count": feedings_count,
                    "average_portion_size": average_portion,
                }
            )

        return _normalise_attributes(attrs)


# Walk Sensors


@register_sensor("last_walk")
class PawControlLastWalkSensor(PawControlSensorBase):
    """Sensor for last walk timestamp."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Walk Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:walk",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return timestamp of the last walk."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return None

        last_walk = walk_data.get("last_walk")
        if not last_walk:
            return None

        timestamp = self._coerce_utc_datetime(last_walk)
        if timestamp is not None:
            return timestamp

        _LOGGER.debug("Invalid last_walk timestamp: %s", last_walk)

        return None


@register_sensor("last_walk_hours")
class PawControlLastWalkHoursSensor(PawControlSensorBase):
    """Sensor providing the elapsed hours since the last walk."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Walk Hours Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk_hours",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:timer-outline",
            translation_key="last_walk_hours",
        )

    @property
    def native_value(self) -> float:
        """Return hours elapsed since the most recent walk."""

        walk_data = self._get_walk_module()
        if not walk_data:
            return 0.0

        last_walk_hours = walk_data.get("last_walk_hours", 0.0)
        return self._coerce_float(last_walk_hours, default=0.0)


@register_sensor("walks_today")
class PawControlWalksTodaySensor(PawControlSensorBase):
    """Sensor counting walks completed today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Walks Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walks_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:walk",
            translation_key="walks_today",
        )

    @property
    def native_value(self) -> int:
        """Return the number of walks recorded for today."""

        walk_data = self._get_walk_module()
        if not walk_data:
            return 0

        return self._coerce_int(walk_data.get("walks_today", 0))


@register_sensor("current_walk_duration")
class PawControlCurrentWalkDurationSensor(PawControlSensorBase):
    """Sensor indicating the active walk duration in minutes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Current Walk Duration Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "current_walk_duration",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:clock-outline",
            translation_key="current_walk_duration",
        )

    @property
    def native_value(self) -> int:
        """Return the active walk duration if a walk is in progress."""

        walk_data = self._get_walk_module()
        if not walk_data or not walk_data.get("walk_in_progress"):
            return 0

        return self._coerce_int(walk_data.get("current_walk_duration", 0))


@register_sensor("walk_count_today")
class PawControlWalkCountTodaySensor(PawControlSensorBase):
    """Sensor for walk count today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Walk Count Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walk_count_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
        )

    @property
    def native_value(self) -> int:
        """Return number of walks recorded today."""
        walk_data = self._get_walk_module()
        if not walk_data:
            return 0

        return self._coerce_int(walk_data.get("walks_today", 0))


@register_sensor("walk_distance_today")
class PawControlWalkDistanceTodaySensor(PawControlSensorBase):
    """Sensor for total walk distance today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Walk Distance Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walk_distance_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfLength.METERS,
            icon="mdi:map-marker-path",
            translation_key="walk_distance_today",
        )

    @property
    def native_value(self) -> float:
        """Return total walk distance for today in meters."""
        walk_data = self._get_walk_module()
        if not walk_data:
            return 0.0

        distance_today = walk_data.get("total_distance_today", 0)
        return round(self._coerce_float(distance_today), 1)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for walk distance sensor."""
        attrs: AttributeDict = self._base_attributes()

        walk_data = self._get_walk_module()
        if walk_data:
            with contextlib.suppress(TypeError, ValueError, ZeroDivisionError):
                total_distance_today = self._coerce_float(
                    walk_data.get("total_distance_today", 0)
                )
                walks_today = self._coerce_int(walk_data.get("walks_today", 0))
                attrs.update(
                    {
                        "distance_km": round(total_distance_today / 1000, 2),
                        "walks_today": walks_today,
                        "average_distance_per_walk": round(
                            total_distance_today / max(1, walks_today),
                            1,
                        ),
                    }
                )

        return _normalise_attributes(attrs)


# NEW: Critical missing sensor per requirements inventory
@register_sensor("calories_burned_today")
class PawControlCaloriesBurnedTodaySensor(PawControlSensorBase):
    """Sensor for calories burned today through activity.

    NEW: This sensor was identified as missing in requirements_inventory.md
    and marked as critical for health tracking and automation purposes.
    """

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Calories Burned Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "calories_burned_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=_CALORIE_UNIT,
            icon="mdi:fire",
            translation_key="calories_burned_today",
        )

    @property
    def native_value(self) -> float:
        """Return total calories burned today through activity."""
        walk_data = self._get_walk_module()
        if not walk_data:
            return 0.0

        try:
            # Direct value if available
            calories_burned = walk_data.get("calories_burned_today")
            if calories_burned is not None:
                return round(self._coerce_float(calories_burned), 1)

            # Calculate based on walk activity
            return self._calculate_calories_from_activity(walk_data)

        except (TypeError, ValueError) as err:
            _LOGGER.debug(
                "Error calculating calories burned for %s: %s", self._dog_id, err
            )
            return 0.0

    def _calculate_calories_from_activity(
        self, walk_data: WalkModuleTelemetry
    ) -> float:
        """Calculate calories burned from walk activity data."""
        try:
            # Get dog weight for calculation
            dog_data = self._get_dog_data()
            if not dog_data:
                return 0.0

            dog_weight = self._coerce_float(
                dog_data.get("dog_info", {}).get("dog_weight", 25), default=25.0
            )  # Default 25kg

            # Get walk metrics
            duration_value = walk_data.get("total_duration_today")
            distance_value = walk_data.get("total_distance_today")
            total_duration_minutes = (
                self._coerce_float(duration_value)
                if duration_value is not None
                else 0.0
            )
            total_distance_meters = (
                self._coerce_float(distance_value)
                if distance_value is not None
                else 0.0
            )

            if total_duration_minutes == 0:
                return 0.0

            # Basic calorie calculation for dogs:
            # Approximately 0.8 calories per kg per minute of moderate activity
            # Adjusted by distance (more distance = higher intensity)

            base_calories = dog_weight * total_duration_minutes * 0.8

            # Distance adjustment (higher speed = more calories)
            if total_distance_meters > 0:
                speed_kmh = (total_distance_meters / 1000) / (
                    total_duration_minutes / 60
                )
                intensity_factor = 1.0

                if speed_kmh > 8:  # Running
                    intensity_factor = 1.8
                elif speed_kmh > 5:  # Fast walking
                    intensity_factor = 1.4
                elif speed_kmh > 3:  # Normal walking
                    intensity_factor = 1.0
                else:  # Slow walking
                    intensity_factor = 0.8

                base_calories *= intensity_factor

            return round(base_calories, 1)

        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for calories burned sensor."""
        attrs: AttributeDict = self._base_attributes()

        walk_data = self._get_walk_module()
        if walk_data:
            with contextlib.suppress(TypeError, ValueError):
                dog_data = self._get_dog_data()
                dog_weight = (
                    self._coerce_float(
                        dog_data.get("dog_info", {}).get("dog_weight", 25)
                    )
                    if dog_data
                    else 25.0
                )

                total_duration = self._coerce_float(
                    walk_data.get("total_duration_today", 0)
                )
                total_distance = self._coerce_float(
                    walk_data.get("total_distance_today", 0)
                )

                attrs.update(
                    {
                        "dog_weight_kg": dog_weight,
                        "activity_duration_minutes": total_duration,
                        "activity_distance_meters": total_distance,
                        "average_intensity": (
                            "high"
                            if total_distance / max(1, total_duration) * 60 > 5000
                            else "medium"
                            if total_distance / max(1, total_duration) * 60 > 3000
                            else "low"
                        ),
                        "calories_per_hour": round(
                            (self.native_value or 0) / max(0.1, total_duration / 60), 1
                        )
                        if total_duration > 0
                        else 0,
                    }
                )

        return _normalise_attributes(attrs)


# NEW: Critical missing sensor per requirements inventory
@register_sensor("total_walk_distance")
class PawControlTotalWalkDistanceSensor(PawControlSensorBase):
    """Sensor for total cumulative walk distance.

    NEW: This sensor was identified as missing in requirements_inventory.md
    and marked as critical. Tracks total distance over all recorded walks.
    """

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Total Walk Distance Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "total_walk_distance",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfLength.KILOMETERS,
            icon="mdi:map-marker-path",
            translation_key="total_walk_distance",
        )

    @property
    def native_value(self) -> float:
        """Return total cumulative walk distance in kilometers."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return 0.0

        try:
            # Check for direct total distance value
            total_distance = walk_data.get("total_distance_all_time")
            if total_distance is not None:
                return round(
                    self._coerce_float(total_distance) / 1000, 2
                )  # Convert to km

            # Fallback: use cumulative calculation
            cumulative_distance = walk_data.get("cumulative_distance_meters", 0)
            return round(
                self._coerce_float(cumulative_distance) / 1000, 2
            )  # Convert to km

        except (TypeError, ValueError) as err:
            _LOGGER.debug(
                "Error calculating total walk distance for %s: %s", self._dog_id, err
            )
            return 0.0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for total walk distance sensor."""
        attrs: AttributeDict = self._base_attributes()

        walk_data = self._get_walk_module()
        if walk_data:
            with contextlib.suppress(TypeError, ValueError):
                total_distance_m = self._coerce_float(
                    walk_data.get("cumulative_distance_meters", 0)
                )
                total_walks = self._coerce_int(walk_data.get("total_walks_recorded", 0))

                attrs.update(
                    {
                        "total_distance_meters": total_distance_m,
                        "total_walks_recorded": total_walks,
                        "average_distance_per_walk_km": round(
                            (total_distance_m / 1000) / max(1, total_walks), 2
                        )
                        if total_walks > 0
                        else 0,
                        "distance_this_week_km": round(
                            self._coerce_float(
                                walk_data.get("total_distance_this_week", 0)
                            )
                            / 1000,
                            2,
                        ),
                        "distance_this_month_km": round(
                            self._coerce_float(
                                walk_data.get("total_distance_this_month", 0)
                            )
                            / 1000,
                            2,
                        ),
                    }
                )

        return _normalise_attributes(attrs)


# NEW: Critical missing sensor per requirements inventory
@register_sensor("walks_this_week")
class PawControlWalksThisWeekSensor(PawControlSensorBase):
    """Sensor for walks this week count.

    NEW: This sensor was identified as missing in requirements_inventory.md
    and marked as critical for weekly activity tracking and automation.
    """

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Walks This Week Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walks_this_week",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:calendar-week",
            translation_key="walks_this_week",
        )

    @property
    def native_value(self) -> int:
        """Return number of walks recorded this week."""
        walk_data = self._get_walk_module()
        if not walk_data:
            return 0

        try:
            walks_this_week = walk_data.get("walks_this_week")
            if walks_this_week is not None:
                return self._coerce_int(walks_this_week)

            # Fallback: calculate from daily data if available
            return self._calculate_walks_this_week(walk_data)

        except (TypeError, ValueError) as err:
            _LOGGER.debug(
                "Error calculating walks this week for %s: %s", self._dog_id, err
            )
            return 0

    def _calculate_walks_this_week(self, walk_data: WalkModuleTelemetry) -> int:
        """Calculate walks this week from available data."""
        try:
            # Get current walks today and try to estimate week total
            walks_today = self._coerce_int(walk_data.get("walks_today", 0))

            # If we have daily walk history, sum it up
            daily_walks = walk_data.get("daily_walk_counts", {})
            if isinstance(daily_walks, dict):
                now = dt_util.utcnow()
                week_start = now - timedelta(days=now.weekday())  # Monday start

                total_walks = 0
                for i in range(7):  # 7 days in a week
                    day = week_start + timedelta(days=i)
                    day_key = day.strftime("%Y-%m-%d")
                    total_walks += self._coerce_int(daily_walks.get(day_key, 0))

                return total_walks

            # Fallback: just return today's count (limited info)
            return walks_today

        except (TypeError, ValueError, KeyError):
            return 0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for walks this week sensor."""
        attrs: AttributeDict = self._base_attributes()

        walk_data = self._get_walk_module()
        if walk_data:
            with contextlib.suppress(TypeError, ValueError):
                now = dt_util.utcnow()
                week_start = now - timedelta(days=now.weekday())

                attrs.update(
                    {
                        "week_start_date": week_start.strftime("%Y-%m-%d"),
                        "walks_today": self._coerce_int(
                            walk_data.get("walks_today", 0)
                        ),
                        "walks_yesterday": self._coerce_int(
                            walk_data.get("walks_yesterday", 0)
                        ),
                        "average_walks_per_day": round((self.native_value or 0) / 7, 1),
                        "weekly_walk_goal": self._coerce_int(
                            walk_data.get("weekly_walk_target", 14)
                        ),  # 2 per day default
                        "weekly_goal_progress": round(
                            (self.native_value or 0)
                            / max(
                                1,
                                self._coerce_int(
                                    walk_data.get("weekly_walk_target", 14)
                                ),
                            )
                            * 100,
                            1,
                        ),
                        "total_walk_time_this_week_minutes": self._coerce_float(
                            walk_data.get("total_duration_this_week", 0)
                        ),
                    }
                )

        return _normalise_attributes(attrs)


@register_sensor("last_walk_duration")
class PawControlLastWalkDurationSensor(PawControlSensorBase):
    """Sensor for duration of last walk."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Walk Duration Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk_duration",
            device_class=SensorDeviceClass.DURATION,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:timer",
            translation_key="last_walk_duration",
        )

    @property
    def native_value(self) -> int | None:
        """Return duration of the last walk in minutes."""
        walk_data = self._get_walk_module()
        if not walk_data:
            return None

        duration = walk_data.get("last_walk_duration")
        if duration is None:
            return None
        return self._coerce_int(duration)


@register_sensor("last_walk_distance")
class PawControlLastWalkDistanceSensor(PawControlSensorBase):
    """Sensor for distance of last walk."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Walk Distance Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk_distance",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
            icon="mdi:map-marker-path",
            translation_key="last_walk_distance",
        )

    @property
    def native_value(self) -> float | None:
        """Return the distance of the last walk."""
        walk_data = self._get_walk_module()
        if not walk_data:
            return None

        distance = walk_data.get("last_walk_distance")
        if distance is None:
            return None
        return round(self._coerce_float(distance), 1)


@register_sensor("total_walk_time_today")
class PawControlTotalWalkTimeTodaySensor(PawControlSensorBase):
    """Sensor for total walk time today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Total Walk Time Today Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "total_walk_time_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.DURATION,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:timer-sand",
            translation_key="total_walk_time_today",
        )

    @property
    def native_value(self) -> int:
        """Return total walking time today in minutes."""
        walk_data = self._get_walk_module()
        if not walk_data:
            return 0

        return self._coerce_int(walk_data.get("total_duration_today", 0))


@register_sensor("average_walk_duration")
class PawControlAverageWalkDurationSensor(PawControlSensorBase):
    """Sensor for average walk duration."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Average Walk Duration Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "average_walk_duration",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.DURATION,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:timer-outline",
            translation_key="average_walk_duration",
        )

    @property
    def native_value(self) -> float | None:
        """Return average walk duration in minutes."""
        walk_data = self._get_walk_module()
        if not walk_data:
            return None

        avg_duration = walk_data.get("average_duration")
        if avg_duration is None:
            return None
        return self._coerce_float(avg_duration)


# GPS Sensors


@register_sensor("current_zone")
class PawControlCurrentZoneSensor(PawControlSensorBase):
    """Sensor for current zone."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Current Zone Sensor."""
        super().__init__(coordinator, dog_id, dog_name, "current_zone", icon="mdi:map")

    @property
    def native_value(self) -> str:
        """Return current GPS zone for the dog."""
        gps_data = self._get_gps_module()
        if not gps_data:
            return _STATE_UNKNOWN

        zone = gps_data.get("zone", _STATE_UNKNOWN)
        return zone if isinstance(zone, str) else _STATE_UNKNOWN


@register_sensor("current_location")
class PawControlCurrentLocationSensor(PawControlSensorBase):
    """Sensor exposing the dog's current location label."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Current Location Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "current_location",
            icon="mdi:map-marker",
            translation_key="current_location",
        )

    @property
    def native_value(self) -> str:
        """Return the friendly current location for the dog."""

        gps_data = self._get_gps_module()
        if not gps_data:
            return _STATE_UNKNOWN

        location = gps_data.get("current_location") or gps_data.get("zone")
        if not isinstance(location, str) or not location:
            return _STATE_UNKNOWN

        return location

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        gps_data: GPSModulePayload = cast(
            GPSModulePayload, self._get_gps_module() or {}
        )
        last_seen_raw = gps_data.get("last_seen")
        last_seen = self._coerce_utc_datetime(last_seen_raw)
        attrs["last_seen"] = last_seen.isoformat() if last_seen else None
        attrs["in_safe_zone"] = bool(gps_data.get("in_safe_zone"))
        return _normalise_attributes(attrs)


@register_sensor("distance_from_home")
class PawControlDistanceFromHomeSensor(PawControlSensorBase):
    """Sensor for distance from home."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Distance From Home Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "distance_from_home",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
            icon="mdi:map-marker-distance",
            translation_key="distance_from_home",
        )

    @property
    def native_value(self) -> float | None:
        """Return distance from home in meters."""
        gps_data = self._get_gps_module()
        if not gps_data:
            return None

        distance = gps_data.get("distance_from_home")
        if distance is None:
            return None
        return self._coerce_float(distance)


@register_sensor("current_speed")
class PawControlCurrentSpeedSensor(PawControlSensorBase):
    """Sensor for current speed."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Current Speed Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "current_speed",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=_SPEED_UNIT,
            icon="mdi:speedometer",
            translation_key="current_speed",
        )

    @property
    def native_value(self) -> float | None:
        """Return current speed in km/h."""
        gps_data = self._get_gps_module()
        if not gps_data:
            return None

        speed = gps_data.get("current_speed")
        if speed is None:
            return None
        return self._coerce_float(speed)


@register_sensor("speed")
class PawControlSpeedSensor(PawControlSensorBase):
    """Compatibility sensor exposing GPS speed readings."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Speed Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "speed",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=_SPEED_UNIT,
            icon="mdi:speedometer",
            translation_key="speed",
        )

    @property
    def native_value(self) -> float:
        """Return the current GPS speed reading."""

        gps_data = self._get_gps_module()
        if not gps_data:
            return 0.0

        value = gps_data.get("speed", gps_data.get("current_speed", 0.0))
        return self._coerce_float(value)


@register_sensor("gps_accuracy")
class PawControlGPSAccuracySensor(PawControlSensorBase):
    """Sensor for GPS accuracy."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control G P S Accuracy Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_accuracy",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
            icon="mdi:crosshairs-gps",
            translation_key="gps_accuracy",
        )

    @property
    def native_value(self) -> float | None:
        """Return GPS accuracy in meters."""
        gps_data = self._get_gps_module()
        if not gps_data:
            return None

        accuracy = gps_data.get("accuracy")
        if accuracy is None:
            return None
        return self._coerce_float(accuracy)


@register_sensor("gps_battery_level")
class PawControlGPSBatteryLevelSensor(PawControlSensorBase):
    """Sensor for GPS tracker battery level."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control G P S Battery Level Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_battery_level",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.BATTERY,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:battery",
        )

    @property
    def native_value(self) -> int | None:
        """Return GPS tracker battery level in percent."""
        gps_data = self._get_gps_module()
        if not gps_data:
            return None

        battery = gps_data.get("battery")
        if battery is None:
            return None
        return self._coerce_int(battery)


# Health Sensors


@register_sensor("health_status")
class PawControlHealthStatusSensor(PawControlSensorBase):
    """Sensor for overall health status."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Health Status Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_status",
            icon="mdi:heart-pulse",
        )

    @property
    def native_value(self) -> str:
        """Return overall health status."""
        health_data = self._get_health_module()
        if not health_data:
            return _STATE_UNKNOWN

        status = health_data.get("health_status", "good")
        return status if isinstance(status, str) else "good"


@register_sensor("weight")
class PawControlWeightSensor(PawControlSensorBase):
    """Sensor for dog weight."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Weight Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weight",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            unit_of_measurement=UnitOfMass.KILOGRAMS,
            icon="mdi:scale-bathroom",
            translation_key="weight",
        )

    @property
    def native_value(self) -> float | None:
        """Return current weight in kilograms."""
        health_data = self._get_health_module()
        if not health_data:
            return None

        weight = health_data.get("weight")
        if weight is None:
            return None
        return self._coerce_float(weight)


@register_sensor("weight_trend")
class PawControlWeightTrendSensor(PawControlSensorBase):
    """Sensor for dog weight trend."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Weight Trend Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weight_trend",
            icon="mdi:trending-up",
        )

    @property
    def native_value(self) -> str:
        """Return current weight trend."""
        health_data = self._get_health_module()
        if not health_data:
            return _STATE_UNKNOWN

        trend = health_data.get("weight_trend", "stable")
        return trend if isinstance(trend, str) else "stable"


@register_sensor("body_condition_score")
class PawControlBodyConditionScoreSensor(PawControlSensorBase):
    """Sensor for body condition score (1-9 scale)."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Body Condition Score Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "body_condition_score",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:weight",
        )

    @property
    def native_value(self) -> int | None:
        """Return body condition score."""
        health_data = self._get_health_module()
        if not health_data:
            return None

        score = health_data.get("body_condition_score")
        if score is None:
            return None
        return self._coerce_int(score)


@register_sensor("last_vet_visit")
class PawControlLastVetVisitSensor(PawControlSensorBase):
    """Sensor for last vet visit timestamp."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Last Vet Visit Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_vet_visit",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:stethoscope",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return timestamp of the last veterinary visit."""
        health_data = self._get_health_module()
        if not health_data:
            return None

        last_visit = health_data.get("last_vet_visit")
        if not last_visit:
            return None

        timestamp = self._coerce_utc_datetime(last_visit)
        if timestamp is not None:
            return timestamp

        _LOGGER.debug("Invalid last_vet_visit timestamp: %s", last_visit)

        return None


@register_sensor("health_conditions")
class PawControlHealthConditionsSensor(PawControlSensorBase):
    """Sensor exposing tracked health conditions."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Health Conditions Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_conditions",
            icon="mdi:clipboard-pulse",
            translation_key="health_conditions",
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> str:
        """Return comma separated list of health conditions."""

        conditions: HealthModulePayload = cast(
            HealthModulePayload, self._get_health_module() or {}
        )
        condition_list = conditions.get("health_conditions")
        if not condition_list:
            return "none"
        if isinstance(condition_list, list):
            normalized = [
                str(cond)
                for cond in condition_list
                if isinstance(cond, (str, int, float))
            ]
            return ", ".join(normalized) if normalized else "none"
        return str(condition_list)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        conditions: HealthModulePayload = cast(
            HealthModulePayload, self._get_health_module() or {}
        )
        condition_list = conditions.get("health_conditions")
        normalized_list: list[str] = []
        if isinstance(condition_list, list):
            normalized_list = [
                str(cond)
                for cond in condition_list
                if isinstance(cond, (str, int, float))
            ]
        attrs["conditions"] = normalized_list
        return _normalise_attributes(attrs)


@register_sensor("weight_goal_progress")
class PawControlWeightGoalProgressSensor(PawControlSensorBase):
    """Sensor for weight goal progress percentage."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Weight Goal Progress Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weight_goal_progress",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:bullseye-arrow",
            translation_key="weight_goal_progress",
        )

    @property
    def native_value(self) -> float | None:
        """Return percentage progress toward weight goal."""

        health_data = self._get_health_module()
        if not health_data:
            return None

        progress = health_data.get("weight_goal_progress")
        if progress is None:
            return None
        return self._coerce_float(progress)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        health_data: HealthModulePayload = cast(
            HealthModulePayload, self._get_health_module() or {}
        )
        attrs.update(
            {
                "weight_goal": cast(JSONValue, health_data.get("weight_goal")),
                "current_weight": cast(JSONValue, health_data.get("weight")),
                "ideal_weight": cast(JSONValue, health_data.get("ideal_weight")),
            }
        )
        return _normalise_attributes(attrs)


@register_sensor("daily_activity_level")
class PawControlDailyActivityLevelSensor(PawControlSensorBase):
    """Sensor summarizing the daily health activity level."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the Paw Control Daily Activity Level Sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "daily_activity_level",
            icon="mdi:run",
            translation_key="daily_activity_level",
        )

    @property
    def native_value(self) -> str:
        """Return the activity level for today."""

        health_data = self._get_module_data("health")
        if not health_data:
            return "unknown"

        level = health_data.get("activity_level") or health_data.get(
            "daily_activity_level"
        )
        if not level:
            return "unknown"
        return str(level)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return extra state attributes provided by this sensor."""
        attrs: AttributeDict = self._base_attributes()
        health_data: HealthModulePayload = cast(
            HealthModulePayload, self._get_health_module() or {}
        )
        attrs.update(
            {
                "calorie_target": cast(
                    JSONValue, health_data.get("daily_calorie_target")
                ),
                "calories_consumed": cast(
                    JSONValue, health_data.get("total_calories_today")
                ),
            }
        )
        return _normalise_attributes(attrs)


# Ensure every override inherits a meaningful docstring from its base implementation.
inherit_missing_docstrings()


def _coerce_budget_remaining(budget: Any) -> int | None:
    """Return an integer remaining capacity for arbitrary budget objects."""

    if budget is None:
        return None

    remaining = getattr(budget, "remaining", None)
    if remaining is None:
        return None

    if isinstance(remaining, int | float):
        return int(remaining)

    try:
        return int(remaining)
    except (TypeError, ValueError):
        _LOGGER.debug(
            "Ignoring non-numeric entity budget remaining value for %s",
            type(budget).__name__,
        )
        return None


def _is_budget_exhausted(budget: Any) -> bool:
    """Return True when the provided budget is known to be depleted."""

    remaining = _coerce_budget_remaining(budget)
    return remaining is not None and remaining <= 0
