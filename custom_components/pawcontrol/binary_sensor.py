"""Binary sensor platform for Paw Control integration.

This module provides comprehensive binary sensor entities for dog monitoring
including status indicators, alerts, and automated detection sensors. All
binary sensors are designed to meet Home Assistant's Platinum quality ambitions
with full type annotations, async operations, and robust error handling.

OPTIMIZED: Consistent runtime_data usage, thread-safe caching, reduced code duplication.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    MODULE_FEEDING,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .entity import PawControlEntity
from .runtime_data import get_runtime_data
from .types import (
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    VISITOR_MODE_ACTIVE_FIELD,
    WALK_IN_PROGRESS_FIELD,
    JSONMutableMapping,
    CoordinatorDogData,
    CoordinatorModuleState,
    CoordinatorTypedModuleName,
    DogConfigData,
    FeedingEmergencyState,
    FeedingModulePayload,
    GardenModulePayload,
    GPSModulePayload,
    HealthModulePayload,
    JSONMapping,
    JSONValue,
    PawControlConfigEntry,
    WalkModulePayload,
    ensure_dog_config_data,
    ensure_dog_modules_mapping,
)
from .utils import async_call_add_entities, ensure_utc_datetime

if TYPE_CHECKING:
    from .garden_manager import GardenManager


_LOGGER = logging.getLogger(__name__)


def _coerce_bool_flag(value: object) -> bool | None:
    """Return a strict boolean for 0/1 sentinel payloads."""

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)

    return None


def _as_local(dt_value: datetime) -> datetime:
    """Return a timezone-aware datetime in the local timezone."""

    if hasattr(dt_util, "as_local"):
        return dt_util.as_local(dt_value)

    target = dt_value
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)

    local_tz = getattr(dt_util, "DEFAULT_TIME_ZONE", None)
    if local_tz is None:
        return target

    try:
        return target.astimezone(local_tz)
    except Exception:  # pragma: no cover - defensive fallback
        return target


# Home Assistant platform configuration
PARALLEL_UPDATES = 0

# OPTIMIZATION: Performance constants for batched entity creation
ENTITY_CREATION_BATCH_SIZE = 12  # Optimized for binary sensors
ENTITY_CREATION_DELAY = 0.1  # 100ms between batches
PARALLEL_THRESHOLD = 24  # Threshold for parallel vs batched creation

FEEDING_MODULE = cast(CoordinatorTypedModuleName, MODULE_FEEDING)
GARDEN_MODULE = cast(CoordinatorTypedModuleName, MODULE_GARDEN)
GPS_MODULE = cast(CoordinatorTypedModuleName, MODULE_GPS)
HEALTH_MODULE = cast(CoordinatorTypedModuleName, MODULE_HEALTH)
WALK_MODULE = cast(CoordinatorTypedModuleName, MODULE_WALK)


# OPTIMIZED: Shared logic patterns to reduce code duplication
class BinarySensorLogicMixin:
    """Mixin providing shared logic patterns for binary sensors."""

    @staticmethod
    def _calculate_time_based_status(
        timestamp_value: str | datetime | None,
        threshold_hours: float,
        default_if_none: bool = False,
    ) -> bool:
        """Calculate status based on time threshold.

        Args:
            timestamp_value: Timestamp to evaluate
            threshold_hours: Hours threshold for comparison
            default_if_none: Return value when timestamp is None

        Returns:
            True if within threshold, False otherwise
        """
        if not timestamp_value:
            return default_if_none

        timestamp = ensure_utc_datetime(timestamp_value)
        if timestamp is None:
            return default_if_none

        time_diff = dt_util.utcnow() - timestamp
        return time_diff < timedelta(hours=threshold_hours)

    @staticmethod
    def _evaluate_threshold(
        value: float | int | None,
        threshold: float,
        comparison: str = "greater",
        default_if_none: bool = False,
    ) -> bool:
        """Evaluate value against threshold.

        Args:
            value: Value to compare
            threshold: Threshold value
            comparison: 'greater', 'less', 'greater_equal', 'less_equal'
            default_if_none: Return value when value is None

        Returns:
            Comparison result
        """
        if value is None:
            return default_if_none

        try:
            num_value = float(value)
            if comparison == "greater":
                return num_value > threshold
            if comparison == "less":
                return num_value < threshold
            if comparison == "greater_equal":
                return num_value >= threshold
            if comparison == "less_equal":
                return num_value <= threshold
            raise ValueError(f"Unknown comparison: {comparison}")

        except (TypeError, ValueError):
            return default_if_none


async def _async_add_entities_in_batches(
    async_add_entities_func: AddEntitiesCallback,
    entities: Sequence[PawControlBinarySensorBase],
    batch_size: int = ENTITY_CREATION_BATCH_SIZE,
    delay_between_batches: float = ENTITY_CREATION_DELAY,
) -> None:
    """Add binary sensor entities in optimized batches.

    The Entity Registry logs warnings when >200 messages occur rapidly.
    By batching entities and adding delays, we prevent registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of binary sensor entities to add
        batch_size: Number of entities per batch
        delay_between_batches: Seconds to wait between batches
    """
    total_entities = len(entities)

    _LOGGER.debug(
        "Adding %d binary sensor entities in batches of %d to prevent Registry overload",
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
        batch = entities[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            "Processing binary sensor batch %d/%d with %d entities",
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
    """Set up Paw Control binary sensor platform with optimized performance."""

    # OPTIMIZED: Consistent runtime_data usage for Platinum readiness
    runtime_data = get_runtime_data(hass, entry)
    if runtime_data is None:
        _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
        return
    coordinator = runtime_data.coordinator
    raw_dogs = getattr(runtime_data, "dogs", [])
    dog_configs: list[DogConfigData] = []
    for raw_dog in raw_dogs:
        if not isinstance(raw_dog, Mapping):
            continue

        normalised = ensure_dog_config_data(cast(JSONMapping, raw_dog))
        if normalised is None:
            continue

        dog_configs.append(normalised)

    if not dog_configs:
        _LOGGER.warning("No dogs configured for binary sensor platform")
        return

    entities: list[PawControlBinarySensorBase] = []

    # Create binary sensors for each configured dog
    for dog in dog_configs:
        dog_id: str = dog[DOG_ID_FIELD]
        dog_name: str = dog[DOG_NAME_FIELD]
        modules = ensure_dog_modules_mapping(dog)

        _LOGGER.debug("Creating binary sensors for dog: %s (%s)", dog_name, dog_id)

        # Base binary sensors - always created for every dog
        entities.extend(_create_base_binary_sensors(coordinator, dog_id, dog_name))

        # Module-specific binary sensors
        if modules.get(MODULE_FEEDING, False):
            entities.extend(
                _create_feeding_binary_sensors(coordinator, dog_id, dog_name)
            )

        if modules.get(MODULE_WALK, False):
            entities.extend(_create_walk_binary_sensors(coordinator, dog_id, dog_name))

        if modules.get(MODULE_GPS, False):
            entities.extend(_create_gps_binary_sensors(coordinator, dog_id, dog_name))

        if modules.get(MODULE_HEALTH, False):
            entities.extend(
                _create_health_binary_sensors(coordinator, dog_id, dog_name)
            )

        if modules.get(MODULE_GARDEN, False):
            entities.extend(
                _create_garden_binary_sensors(coordinator, dog_id, dog_name)
            )

    # OPTIMIZED: Smart batching based on entity count
    if len(entities) <= PARALLEL_THRESHOLD:
        # Small setup: Create all at once for better performance

        await async_call_add_entities(
            async_add_entities, entities, update_before_add=False
        )

        _LOGGER.info(
            "Created %d binary sensor entities for %d dogs (single batch)",
            len(entities),
            len(dog_configs),
        )
    else:
        # Large setup: Use optimized batching to prevent registry overload
        await _async_add_entities_in_batches(async_add_entities, entities)
        _LOGGER.info(
            "Created %d binary sensor entities for %d dogs (batched approach)",
            len(entities),
            len(dog_configs),
        )


def _create_base_binary_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlBinarySensorBase]:
    """Create base binary sensors that are always present for every dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of base binary sensor entities
    """
    return [
        PawControlOnlineBinarySensor(coordinator, dog_id, dog_name),
        PawControlAttentionNeededBinarySensor(coordinator, dog_id, dog_name),
        PawControlVisitorModeBinarySensor(coordinator, dog_id, dog_name),
    ]


def _create_feeding_binary_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlBinarySensorBase]:
    """Create feeding-related binary sensors for a dog."""
    return [
        PawControlIsHungryBinarySensor(coordinator, dog_id, dog_name),
        PawControlFeedingDueBinarySensor(coordinator, dog_id, dog_name),
        PawControlFeedingScheduleOnTrackBinarySensor(coordinator, dog_id, dog_name),
        PawControlDailyFeedingGoalMetBinarySensor(coordinator, dog_id, dog_name),
    ]


def _create_walk_binary_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlBinarySensorBase]:
    """Create walk-related binary sensors for a dog."""
    return [
        PawControlWalkInProgressBinarySensor(coordinator, dog_id, dog_name),
        PawControlNeedsWalkBinarySensor(coordinator, dog_id, dog_name),
        PawControlWalkGoalMetBinarySensor(coordinator, dog_id, dog_name),
        PawControlLongWalkOverdueBinarySensor(coordinator, dog_id, dog_name),
    ]


def _create_gps_binary_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlBinarySensorBase]:
    """Create GPS and location-related binary sensors for a dog."""
    return [
        PawControlIsHomeBinarySensor(coordinator, dog_id, dog_name),
        PawControlInSafeZoneBinarySensor(coordinator, dog_id, dog_name),
        PawControlGPSAccuratelyTrackedBinarySensor(coordinator, dog_id, dog_name),
        PawControlMovingBinarySensor(coordinator, dog_id, dog_name),
        PawControlGeofenceAlertBinarySensor(coordinator, dog_id, dog_name),
        PawControlGPSBatteryLowBinarySensor(coordinator, dog_id, dog_name),
    ]


def _create_health_binary_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlBinarySensorBase]:
    """Create health and medical-related binary sensors for a dog."""
    return [
        PawControlHealthAlertBinarySensor(coordinator, dog_id, dog_name),
        PawControlWeightAlertBinarySensor(coordinator, dog_id, dog_name),
        PawControlMedicationDueBinarySensor(coordinator, dog_id, dog_name),
        PawControlVetCheckupDueBinarySensor(coordinator, dog_id, dog_name),
        PawControlGroomingDueBinarySensor(coordinator, dog_id, dog_name),
        PawControlActivityLevelConcernBinarySensor(coordinator, dog_id, dog_name),
        PawControlHealthAwareFeedingBinarySensor(coordinator, dog_id, dog_name),
        PawControlMedicationWithMealsBinarySensor(coordinator, dog_id, dog_name),
        PawControlHealthEmergencyBinarySensor(coordinator, dog_id, dog_name),
    ]


def _create_garden_binary_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlBinarySensorBase]:
    """Create garden-related binary sensors for a dog."""

    return [
        PawControlGardenSessionActiveBinarySensor(coordinator, dog_id, dog_name),
        PawControlInGardenBinarySensor(coordinator, dog_id, dog_name),
        PawControlGardenPoopPendingBinarySensor(coordinator, dog_id, dog_name),
    ]


class PawControlBinarySensorBase(
    PawControlEntity, BinarySensorEntity, BinarySensorLogicMixin
):
    """Base class for all Paw Control binary sensor entities.

    OPTIMIZED: Thread-safe caching, shared logic patterns, improved performance.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        sensor_type: str,
        *,
        device_class: BinarySensorDeviceClass | None = None,
        icon_on: str | None = None,
        icon_off: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize the binary sensor entity."""
        super().__init__(coordinator, dog_id, dog_name)
        self._sensor_type = sensor_type
        self._icon_on = icon_on
        self._icon_off = icon_off

        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{sensor_type}"
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_translation_key = sensor_type
        self._apply_name_suffix(sensor_type.replace("_", " ").title())

        # Link entity to PawControl device entry for the dog
        self.update_device_metadata(model="Virtual Dog", sw_version="1.0.0")

        # OPTIMIZED: Thread-safe instance-level caching
        self._data_cache: dict[str, CoordinatorDogData | None] = {}
        self._cache_timestamp: datetime | None = None
        self._cache_ttl = 30  # 30 seconds cache TTL

    @property
    def is_on(self) -> bool:
        """Return the sensor's state, allowing for test overrides."""
        if hasattr(self, "_test_is_on"):
            return self._test_is_on
        return self._get_is_on_state()

    @is_on.setter
    def is_on(self, value: bool) -> None:
        """Set the sensor's state for testing."""
        if "PYTEST_CURRENT_TEST" not in os.environ:
            raise AttributeError("is_on is read-only")
        self._test_is_on = value

    @is_on.deleter
    def is_on(self) -> None:
        """Delete the test override for the sensor's state."""
        if hasattr(self, "_test_is_on"):
            del self._test_is_on

    def _get_is_on_state(self) -> bool:
        """Return the actual state of the sensor. Subclasses should override."""
        return False

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        if self.is_on and self._icon_on:
            return self._icon_on
        if not self.is_on and self._icon_off:
            return self._icon_off
        return "mdi:information-outline"

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Expose the configured device class for test doubles."""

        return getattr(self, "_attr_device_class", None)

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return additional state attributes for the binary sensor."""
        attrs = cast(
            JSONMutableMapping,
            {
                ATTR_DOG_ID: self._dog_id,
                ATTR_DOG_NAME: self._dog_name,
                "last_update": dt_util.utcnow().isoformat(),
                "sensor_type": self._sensor_type,
            },
        )

        # Add dog-specific information with error handling
        try:
            dog_data = self._get_dog_data_cached()
            if dog_data and "dog_info" in dog_data:
                dog_info = cast(DogConfigData, dog_data["dog_info"])
                attrs.update(
                    {
                        "dog_breed": dog_info.get("dog_breed"),
                        "dog_age": dog_info.get("dog_age"),
                        "dog_size": dog_info.get("dog_size"),
                        "dog_weight": dog_info.get("dog_weight"),
                    }
                )
        except Exception as err:
            _LOGGER.debug("Could not fetch dog info for attributes: %s", err)

        return attrs

    def _get_dog_data_cached(self) -> CoordinatorDogData | None:
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

        # Update cache
        self._data_cache[cache_key] = dog_data
        self._cache_timestamp = now

        return dog_data

    def _get_dog_data(self) -> CoordinatorDogData | None:
        """Get dog data - wrapper for cached access."""
        return self._get_dog_data_cached()

    def _get_module_state(
        self, module: CoordinatorTypedModuleName
    ) -> CoordinatorModuleState | None:
        """Return coordinator state for the provided module."""

        dog_data = self._get_dog_data_cached()
        if not dog_data:
            return None

        module_data = dog_data.get(module)
        if isinstance(module_data, Mapping):
            return cast(CoordinatorModuleState, module_data)

        _LOGGER.debug(
            "Coordinator returned unexpected payload for module %s/%s: %s",
            self._dog_id,
            module,
            type(module_data).__name__ if module_data is not None else "None",
        )
        return None

    def _get_feeding_payload(self) -> FeedingModulePayload | None:
        """Return the structured feeding payload when available."""

        module_state = self._get_module_state(FEEDING_MODULE)
        return cast(FeedingModulePayload, module_state) if module_state else None

    def _get_walk_payload(self) -> WalkModulePayload | None:
        """Return the structured walk payload when available."""

        module_state = self._get_module_state(WALK_MODULE)
        return cast(WalkModulePayload, module_state) if module_state else None

    def _get_gps_payload(self) -> GPSModulePayload | None:
        """Return the structured GPS payload when available."""

        module_state = self._get_module_state(GPS_MODULE)
        return cast(GPSModulePayload, module_state) if module_state else None

    def _get_health_payload(self) -> HealthModulePayload | None:
        """Return the structured health payload when available."""

        module_state = self._get_module_state(HEALTH_MODULE)
        return cast(HealthModulePayload, module_state) if module_state else None

    def _get_garden_payload(self) -> GardenModulePayload | None:
        """Return the structured garden payload when available."""

        module_state = self._get_module_state(GARDEN_MODULE)
        return cast(GardenModulePayload, module_state) if module_state else None

    @property
    def available(self) -> bool:
        """Return if the binary sensor is available."""
        return self.coordinator.available and self._get_dog_data_cached() is not None


# Garden-specific binary sensor base


class PawControlGardenBinarySensorBase(PawControlBinarySensorBase):
    """Base class for garden binary sensors."""

    def _get_garden_manager(self) -> GardenManager | None:
        """Return the configured garden manager when available."""

        return self._get_runtime_managers().garden_manager

    def _get_garden_data(self) -> GardenModulePayload:
        """Return garden snapshot data for the dog."""

        payload = self._get_garden_payload()
        if payload:
            return payload

        garden_manager = self._get_garden_manager()
        if garden_manager is not None:
            try:
                return garden_manager.build_garden_snapshot(self._dog_id)
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.debug(
                    "Garden snapshot fallback failed for %s: %s", self._dog_id, err
                )

        return cast(GardenModulePayload, {})

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Expose the latest garden telemetry for diagnostics dashboards."""
        attrs = super().extra_state_attributes
        data = self._get_garden_data()
        garden_status = data.get("status")
        if garden_status is not None:
            attrs["garden_status"] = garden_status
        sessions_today = data.get("sessions_today")
        if sessions_today is not None:
            attrs["sessions_today"] = sessions_today
        pending_confirmations = data.get("pending_confirmations")
        if pending_confirmations is not None:
            attrs["pending_confirmations"] = cast(JSONValue, pending_confirmations)
        return attrs


# Base binary sensors
class PawControlOnlineBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if the dog monitoring system is online."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the online status binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "online",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            icon_on="mdi:check-network",
            icon_off="mdi:close-network",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if the dog monitoring system is online."""
        dog_data = self._get_dog_data_cached()
        if not dog_data:
            return False

        last_update = dog_data.get("last_update")
        return self._calculate_time_based_status(
            last_update, 10.0 / 60, False
        )  # 10 minutes

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return additional attributes for the online sensor."""
        attrs = super().extra_state_attributes
        dog_data = self._get_dog_data_cached()

        if dog_data:
            last_update = dog_data.get("last_update")
            if last_update:
                attrs["last_update"] = last_update

            attrs["status"] = dog_data.get("status", STATE_UNKNOWN)
            enabled_modules = sorted(self.coordinator.get_enabled_modules(self._dog_id))
            if enabled_modules:
                attrs["enabled_modules"] = list(enabled_modules)
            attrs["system_health"] = "healthy" if self.is_on else "disconnected"

        return attrs


class PawControlAttentionNeededBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if the dog needs immediate attention."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the attention needed binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "attention_needed",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon_on="mdi:alert-circle",
            icon_off="mdi:check-circle",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if the dog needs immediate attention."""
        attention_reasons: list[str] = []

        feeding_data = self._get_feeding_payload()
        if feeding_data and bool(feeding_data.get("is_hungry", False)):
            last_feeding_hours = feeding_data.get("last_feeding_hours")
            if (
                isinstance(last_feeding_hours, int | float)
                and float(last_feeding_hours) > 12
            ):
                attention_reasons.append("critically_hungry")
            else:
                attention_reasons.append("hungry")

        walk_data = self._get_walk_payload()
        if walk_data and bool(walk_data.get("needs_walk", False)):
            last_walk_hours = walk_data.get("last_walk_hours")
            if isinstance(last_walk_hours, int | float) and float(last_walk_hours) > 12:
                attention_reasons.append("urgent_walk_needed")
            else:
                attention_reasons.append("needs_walk")

        health_data = self._get_health_payload()
        if health_data:
            health_alerts = health_data.get("health_alerts", [])
            if isinstance(health_alerts, Sequence) and health_alerts:
                attention_reasons.append("health_alert")

        gps_data = self._get_gps_payload()
        if gps_data is not None:
            geofence_status = gps_data.get("geofence_status")
            in_safe_zone = True
            if isinstance(geofence_status, Mapping):
                in_safe_zone = bool(geofence_status.get("in_safe_zone", True))
            if not in_safe_zone:
                attention_reasons.append("outside_safe_zone")

        self._attention_reasons = attention_reasons

        return bool(attention_reasons)

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return additional attributes explaining why attention is needed."""
        attrs = super().extra_state_attributes

        if hasattr(self, "_attention_reasons"):
            attrs.update(
                {
                    "attention_reasons": self._attention_reasons,
                    "urgency_level": self._calculate_urgency_level(),
                    "recommended_actions": self._get_recommended_actions(),
                }
            )

        return attrs

    def _calculate_urgency_level(self) -> str:
        """Calculate the urgency level based on attention reasons."""
        if not hasattr(self, "_attention_reasons"):
            return "none"

        urgent_conditions = ["critically_hungry", "health_alert"]

        if any(reason in urgent_conditions for reason in self._attention_reasons):
            return "high"
        if len(self._attention_reasons) > 2:
            return "medium"
        if len(self._attention_reasons) > 0:
            return "low"
        return "none"

    def _get_recommended_actions(self) -> list[str]:
        """Get recommended actions based on attention reasons."""
        if not hasattr(self, "_attention_reasons"):
            return []

        actions = []

        if "critically_hungry" in self._attention_reasons:
            actions.append("Feed immediately")
        elif "hungry" in self._attention_reasons:
            actions.append("Consider feeding")

        if "urgent_walk_needed" in self._attention_reasons:
            actions.append("Take for walk immediately")

        if "health_alert" in self._attention_reasons:
            actions.append("Check health status")

        if "outside_safe_zone" in self._attention_reasons:
            actions.append("Check location and safety")

        return actions


class PawControlVisitorModeBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if visitor mode is active."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the visitor mode binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "visitor_mode",
            icon_on="mdi:account-group",
            icon_off="mdi:home",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if visitor mode is active."""
        dog_data = self._get_dog_data_cached()
        if not dog_data:
            return False

        return bool(dog_data.get(VISITOR_MODE_ACTIVE_FIELD, False))

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return additional attributes for visitor mode."""
        attrs = super().extra_state_attributes
        dog_data = self._get_dog_data_cached()

        if dog_data:
            visitor_settings = cast(
                JSONMapping, dog_data.get("visitor_mode_settings", {})
            )
            visitor_mode_started = cast(
                str | None, dog_data.get("visitor_mode_started")
            )
            visitor_name = cast(str | None, dog_data.get("visitor_name"))
            attrs.update(
                {
                    "visitor_mode_started": visitor_mode_started,
                    "visitor_name": visitor_name,
                    "modified_notifications": bool(
                        visitor_settings.get("modified_notifications", True)
                    ),
                    "reduced_alerts": bool(
                        visitor_settings.get("reduced_alerts", True)
                    ),
                }
            )

        return attrs


# Feeding binary sensors
class PawControlIsHungryBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if the dog is hungry."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the hungry binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "is_hungry",
            icon_on="mdi:food-drumstick-off",
            icon_off="mdi:food-drumstick",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if the dog is hungry."""
        feeding_data = self._get_feeding_payload()
        if not feeding_data:
            return False

        return bool(feeding_data.get("is_hungry", False))

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return additional feeding status attributes."""
        attrs = super().extra_state_attributes
        feeding_data = self._get_feeding_payload()

        if not feeding_data:
            return attrs

        last_feeding = feeding_data.get("last_feeding")
        if isinstance(last_feeding, str) or last_feeding is None:
            attrs["last_feeding"] = last_feeding

        last_feeding_hours = feeding_data.get("last_feeding_hours")
        if isinstance(last_feeding_hours, int | float):
            attrs["last_feeding_hours"] = float(last_feeding_hours)
        elif last_feeding_hours is None:
            attrs["last_feeding_hours"] = None

        next_feeding_due = feeding_data.get("next_feeding_due")
        if isinstance(next_feeding_due, str) or next_feeding_due is None:
            attrs["next_feeding_due"] = next_feeding_due

        attrs["hunger_level"] = self._calculate_hunger_level(feeding_data)

        return attrs

    def _calculate_hunger_level(self, feeding_data: FeedingModulePayload) -> str:
        """Calculate hunger level based on time since last feeding."""
        last_feeding_hours = feeding_data.get("last_feeding_hours")

        if not isinstance(last_feeding_hours, int | float):
            return STATE_UNKNOWN

        hours_since_feeding = float(last_feeding_hours)

        if hours_since_feeding > 12:
            return "very_hungry"
        if hours_since_feeding >= 8:
            return "hungry"
        if hours_since_feeding >= 6:
            return "somewhat_hungry"
        return "satisfied"


class PawControlFeedingDueBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if a feeding is due based on schedule."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the feeding due binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_due",
            icon_on="mdi:clock-alert",
            icon_off="mdi:clock-check",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if a feeding is due according to schedule."""
        feeding_data = self._get_feeding_payload()
        if not feeding_data:
            return False

        next_feeding_due = feeding_data.get("next_feeding_due")
        if not isinstance(next_feeding_due, str):
            return False

        due_time = ensure_utc_datetime(next_feeding_due)
        if due_time is None:
            return False

        return dt_util.utcnow() >= due_time


class PawControlFeedingScheduleOnTrackBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if feeding schedule is being followed."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the feeding schedule on track binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_schedule_on_track",
            icon_on="mdi:calendar-check",
            icon_off="mdi:calendar-alert",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if feeding schedule adherence is good."""
        feeding_data = self._get_feeding_payload()
        if not feeding_data:
            return True  # Assume on track if no data

        adherence = feeding_data.get("feeding_schedule_adherence", 100.0)
        if not isinstance(adherence, int | float):
            return True
        return self._evaluate_threshold(float(adherence), 80.0, "greater_equal", True)


class PawControlDailyFeedingGoalMetBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if daily feeding goals are met."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the daily feeding goal met binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "daily_feeding_goal_met",
            icon_on="mdi:target",
            icon_off="mdi:target-variant",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if daily feeding goals are met."""
        feeding_data = self._get_feeding_payload()
        if not feeding_data:
            return False

        return bool(feeding_data.get("daily_target_met", False))


# Walk binary sensors
class PawControlWalkInProgressBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if a walk is currently in progress."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the walk in progress binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walk_in_progress",
            device_class=BinarySensorDeviceClass.RUNNING,
            icon_on="mdi:walk",
            icon_off="mdi:home",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if a walk is currently in progress."""
        walk_data = self._get_walk_payload()
        if not walk_data:
            return False

        return bool(walk_data.get(WALK_IN_PROGRESS_FIELD, False))

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return additional walk progress attributes."""
        attrs = super().extra_state_attributes
        walk_data = self._get_walk_payload()

        if walk_data and walk_data.get(WALK_IN_PROGRESS_FIELD):
            walk_start = walk_data.get("current_walk_start")
            if isinstance(walk_start, str):
                attrs["walk_start_time"] = walk_start

            current_duration = walk_data.get("current_walk_duration")
            if isinstance(current_duration, int | float):
                attrs["walk_duration"] = float(current_duration)

            current_distance = walk_data.get("current_walk_distance")
            if isinstance(current_distance, int | float):
                attrs["walk_distance"] = float(current_distance)

            estimated_remaining = self._estimate_remaining_time(walk_data)
            if estimated_remaining is not None:
                attrs["estimated_remaining"] = estimated_remaining

        return attrs

    def _estimate_remaining_time(self, walk_data: WalkModulePayload) -> int | None:
        """Estimate remaining walk time based on typical patterns."""
        current_duration_value = walk_data.get("current_walk_duration")
        average_duration_value = walk_data.get("average_walk_duration")

        if (
            isinstance(current_duration_value, int | float)
            and isinstance(average_duration_value, int | float)
            and current_duration_value < average_duration_value
        ):
            return int(average_duration_value - current_duration_value)

        return None


class PawControlNeedsWalkBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if the dog needs a walk."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the needs walk binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "needs_walk",
            icon_on="mdi:dog-side",
            icon_off="mdi:sleep",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if the dog needs a walk."""
        walk_data = self._get_walk_payload()
        if not walk_data:
            return False

        return bool(walk_data.get("needs_walk", False))

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return additional walk need attributes."""
        attrs = super().extra_state_attributes
        walk_data = self._get_walk_payload()

        if walk_data:
            last_walk = walk_data.get("last_walk")
            if isinstance(last_walk, str):
                attrs["last_walk"] = last_walk

            last_walk_hours = walk_data.get("last_walk_hours")
            if isinstance(last_walk_hours, int | float):
                attrs["last_walk_hours"] = float(last_walk_hours)

            walks_today = walk_data.get("walks_today")
            if isinstance(walks_today, int):
                attrs["walks_today"] = walks_today

            attrs["urgency_level"] = self._calculate_walk_urgency(walk_data)

        return attrs

    def _calculate_walk_urgency(self, walk_data: WalkModulePayload) -> str:
        """Calculate walk urgency level."""
        last_walk_hours = walk_data.get("last_walk_hours")

        if not isinstance(last_walk_hours, int | float):
            return STATE_UNKNOWN

        if last_walk_hours > 12:
            return "urgent"
        if last_walk_hours > 8:
            return "high"
        if last_walk_hours > 6:
            return "medium"
        return "low"


class PawControlWalkGoalMetBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if daily walk goals are met."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the walk goal met binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walk_goal_met",
            icon_on="mdi:trophy",
            icon_off="mdi:trophy-outline",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if daily walk goals are met."""
        walk_data = self._get_walk_payload()
        if not walk_data:
            return False

        return bool(walk_data.get("walk_goal_met", False))


class PawControlLongWalkOverdueBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if a longer walk is overdue."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the long walk overdue binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "long_walk_overdue",
            icon_on="mdi:timer-alert",
            icon_off="mdi:timer-check",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if a longer walk is overdue."""
        walk_data = self._get_walk_payload()
        if not walk_data:
            return False

        # Check if last long walk (>30 min) was more than 2 days ago
        last_long_walk = walk_data.get("last_long_walk")
        if isinstance(last_long_walk, str | datetime):
            return not self._calculate_time_based_status(
                last_long_walk, 48, False
            )  # 2 days

        return True  # No long walk recorded or invalid payload


# GPS binary sensors
class PawControlIsHomeBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if the dog is at home."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the is home binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "is_home",
            device_class=BinarySensorDeviceClass.PRESENCE,
            icon_on="mdi:home",
            icon_off="mdi:home-outline",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if the dog is at home."""
        gps_data = self._get_gps_payload()
        if not gps_data:
            return True  # Assume home if no GPS data

        current_zone = gps_data.get("zone")
        return isinstance(current_zone, str) and current_zone == "home"

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return additional location attributes."""
        attrs = super().extra_state_attributes
        gps_data = self._get_gps_payload()

        if gps_data:
            current_zone = gps_data.get("zone")
            attrs["current_zone"] = (
                current_zone if isinstance(current_zone, str) else STATE_UNKNOWN
            )

            distance_from_home = gps_data.get("distance_from_home")
            if isinstance(distance_from_home, int | float):
                attrs["distance_from_home"] = float(distance_from_home)

            last_seen_value = gps_data.get("last_seen")
            if isinstance(last_seen_value, datetime):
                attrs["last_seen"] = last_seen_value.isoformat()
            elif isinstance(last_seen_value, str):
                attrs["last_seen"] = last_seen_value

            accuracy = gps_data.get("accuracy")
            if isinstance(accuracy, int | float):
                attrs["accuracy"] = float(accuracy)

        return attrs


class PawControlInSafeZoneBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if the dog is in a safe zone."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the in safe zone binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "in_safe_zone",
            device_class=BinarySensorDeviceClass.SAFETY,
            icon_on="mdi:shield-check",
            icon_off="mdi:shield-alert",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if the dog is in a safe zone."""
        gps_data = self._get_gps_payload()
        if not gps_data:
            return True  # Assume safe if no GPS data

        # Check if in home zone or other defined safe zones
        current_zone = gps_data.get("zone")
        safe_zones = {"home", "park", "vet", "friend_house"}  # Configurable

        return isinstance(current_zone, str) and current_zone in safe_zones


class PawControlGPSAccuratelyTrackedBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if GPS tracking is accurate."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the GPS accurately tracked binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_accurately_tracked",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            icon_on="mdi:crosshairs-gps",
            icon_off="mdi:crosshairs-question",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if GPS tracking is accurate."""
        gps_data = self._get_gps_payload()
        if not gps_data:
            return False

        accuracy = gps_data.get("accuracy")
        accuracy_value: float | None
        accuracy_value = float(accuracy) if isinstance(accuracy, int | float) else None

        last_seen_input = gps_data.get("last_seen")
        last_seen: datetime | str | None
        if isinstance(last_seen_input, datetime | str):
            last_seen = last_seen_input
        else:
            last_seen = None

        # Check accuracy threshold and data freshness
        accuracy_good = self._evaluate_threshold(
            accuracy_value, 50, "less_equal", False
        )
        data_fresh = self._calculate_time_based_status(
            last_seen, 5.0 / 60, False
        )  # 5 minutes

        return accuracy_good and data_fresh


class PawControlMovingBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if the dog is currently moving."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the moving binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "moving",
            device_class=BinarySensorDeviceClass.MOTION,
            icon_on="mdi:run",
            icon_off="mdi:sleep",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if the dog is currently moving."""
        gps_data = self._get_gps_payload()
        if not gps_data:
            return False

        speed = gps_data.get("speed")
        numeric_speed = float(speed) if isinstance(speed, int | float) else 0.0
        return self._evaluate_threshold(
            numeric_speed, 1.0, "greater", False
        )  # 1 km/h threshold


class PawControlGeofenceAlertBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if there's a geofence alert."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the geofence alert binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "geofence_alert",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon_on="mdi:map-marker-alert",
            icon_off="mdi:map-marker-check",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if there's an active geofence alert."""
        gps_data = self._get_gps_payload()
        if not gps_data:
            return False

        flag = _coerce_bool_flag(gps_data.get("geofence_alert"))
        if flag is not None:
            return flag

        return False


class PawControlGPSBatteryLowBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if GPS device battery is low."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the GPS battery low binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_battery_low",
            device_class=BinarySensorDeviceClass.BATTERY,
            icon_on="mdi:battery-alert",
            icon_off="mdi:battery",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if GPS device battery is low."""
        gps_data = self._get_gps_payload()
        if not gps_data:
            return False

        battery_level = gps_data.get("battery_level")
        if not isinstance(battery_level, int | float):
            return False
        return self._evaluate_threshold(
            float(battery_level), 20, "less_equal", False
        )  # 20% threshold


# Health binary sensors
class PawControlHealthAlertBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if there's a health alert."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the health alert binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_alert",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon_on="mdi:medical-bag",
            icon_off="mdi:heart",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if there are active health alerts."""
        health_data = self._get_health_payload()
        if not health_data:
            return False

        health_alerts = health_data.get("health_alerts", [])
        if isinstance(health_alerts, Sequence):
            return len(health_alerts) > 0

        return False

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return health alert details."""
        attrs = super().extra_state_attributes
        health_data = self._get_health_payload()

        if not health_data:
            return attrs

        health_alerts = health_data.get("health_alerts")
        if isinstance(health_alerts, list):
            attrs["health_alerts"] = cast(JSONValue, health_alerts)
            attrs["alert_count"] = len(health_alerts)

        health_status = health_data.get("health_status")
        if isinstance(health_status, str) or health_status is None:
            attrs["health_status"] = health_status or "good"

        if "alert_count" not in attrs:
            attrs["alert_count"] = 0

        return attrs


class PawControlWeightAlertBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if there's a weight-related alert."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the weight alert binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weight_alert",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon_on="mdi:scale-unbalanced",
            icon_off="mdi:scale-balanced",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if there's a weight alert."""
        health_data = self._get_health_payload()
        if not health_data:
            return False

        weight_change_percent = health_data.get("weight_change_percent", 0)
        if not isinstance(weight_change_percent, int | float):
            return False
        return abs(weight_change_percent) > 10  # 10% weight change threshold


class PawControlMedicationDueBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if medication is due."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the medication due binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "medication_due",
            icon_on="mdi:pill",
            icon_off="mdi:pill-off",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if medication is due."""
        health_data = self._get_health_payload()
        if not health_data:
            return False

        medications_due = health_data.get("medications_due", [])
        if isinstance(medications_due, Sequence):
            return len(medications_due) > 0

        return False


class PawControlVetCheckupDueBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if vet checkup is due."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the vet checkup due binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "vet_checkup_due",
            icon_on="mdi:calendar-alert",
            icon_off="mdi:calendar-check",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if vet checkup is due."""
        health_data = self._get_health_payload()
        if not health_data:
            return False

        next_checkup = health_data.get("next_checkup_due")
        if not isinstance(next_checkup, str):
            return False

        checkup_dt = ensure_utc_datetime(next_checkup)
        if checkup_dt is None:
            return False

        return dt_util.utcnow().date() >= _as_local(checkup_dt).date()


class PawControlGroomingDueBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if grooming is due."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the grooming due binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "needs_grooming",
            icon_on="mdi:content-cut",
            icon_off="mdi:check",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if grooming is due."""
        health_data = self._get_health_payload()
        if not health_data:
            return False

        return bool(health_data.get("grooming_due", False))


class PawControlActivityLevelConcernBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if there's concern about activity level."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the activity level concern binary sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "activity_level_concern",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon_on="mdi:alert",
            icon_off="mdi:check-circle",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if there's concern about activity level."""
        health_data = self._get_health_payload()
        if not health_data:
            return False

        activity_level = health_data.get("activity_level", "normal")
        concerning_levels = ["very_low", "very_high"]

        return activity_level in concerning_levels

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return activity level concern details."""
        attrs = super().extra_state_attributes
        health_data = self._get_health_payload()

        if health_data:
            activity_level_value = health_data.get("activity_level")
            activity_level = (
                activity_level_value
                if isinstance(activity_level_value, str)
                else "normal"
            )
            attrs.update(
                {
                    "current_activity_level": activity_level,
                    "concern_reason": self._get_concern_reason(activity_level),
                    "recommended_action": self._get_recommended_action(activity_level),
                }
            )

        return attrs

    def _get_concern_reason(self, activity_level: str) -> str:
        """Get reason for activity level concern."""
        if activity_level == "very_low":
            return "Activity level is unusually low"
        if activity_level == "very_high":
            return "Activity level is unusually high"
        return "No concern"

    def _get_recommended_action(self, activity_level: str) -> str:
        """Get recommended action for activity level concern."""
        if activity_level == "very_low":
            return "Consider vet consultation or encouraging more activity"
        if activity_level == "very_high":
            return "Monitor for signs of distress or illness"
        return "Continue normal monitoring"


class PawControlHealthAwareFeedingBinarySensor(PawControlBinarySensorBase):
    """Binary sensor showing if health-aware feeding mode is active."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the health-aware feeding status sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_aware_feeding",
            icon_on="mdi:heart-cog",
            icon_off="mdi:heart-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    def _get_is_on_state(self) -> bool:
        feeding_data = self._get_feeding_payload()
        if not feeding_data:
            return False
        return bool(feeding_data.get("health_aware_feeding", False))

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return health-aware feeding metadata for the caregiver UI."""
        attrs = super().extra_state_attributes
        feeding_data = self._get_feeding_payload()

        if feeding_data is None:
            attrs["health_conditions"] = []
            return attrs

        portion_adjustment_factor = feeding_data.get("portion_adjustment_factor")
        if isinstance(portion_adjustment_factor, int | float):
            attrs["portion_adjustment_factor"] = float(portion_adjustment_factor)
        elif portion_adjustment_factor is None:
            attrs["portion_adjustment_factor"] = None

        raw_conditions = feeding_data.get("health_conditions")
        if isinstance(raw_conditions, list):
            attrs["health_conditions"] = [
                str(condition) for condition in raw_conditions
            ]
        else:
            attrs["health_conditions"] = []
        return attrs


class PawControlMedicationWithMealsBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if medication should be given with meals."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the medication reminder sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "medication_with_meals",
            icon_on="mdi:pill-multiple",
            icon_off="mdi:pill",
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    def _get_is_on_state(self) -> bool:
        feeding_data = self._get_feeding_payload()
        if not feeding_data:
            return False
        return bool(feeding_data.get("medication_with_meals", False))

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Report which health conditions require medication with meals."""
        attrs = super().extra_state_attributes
        feeding_data = self._get_feeding_payload()
        if feeding_data:
            raw_conditions = feeding_data.get("health_conditions")
            if isinstance(raw_conditions, list):
                attrs["health_conditions"] = [
                    str(condition) for condition in raw_conditions
                ]
                return attrs

        attrs["health_conditions"] = []
        return attrs


class PawControlHealthEmergencyBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating an active health emergency."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the emergency escalation sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_emergency",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon_on="mdi:alert-decagram",
            icon_off="mdi:check-decagram",
        )

    def _get_is_on_state(self) -> bool:
        feeding_data = self._get_feeding_payload()
        if not feeding_data:
            return False

        flag = _coerce_bool_flag(feeding_data.get("health_emergency"))
        if flag is not None:
            return flag

        return False

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Expose emergency context such as type, timing, and status."""
        attrs = super().extra_state_attributes
        feeding_data = self._get_feeding_payload()
        emergency_payload = (
            feeding_data.get("emergency_mode") if feeding_data is not None else None
        )

        if isinstance(emergency_payload, Mapping):
            emergency = cast(FeedingEmergencyState, emergency_payload)

            emergency_type = emergency.get("emergency_type")
            if isinstance(emergency_type, str):
                attrs["emergency_type"] = emergency_type

            portion_adjustment = emergency.get("portion_adjustment")
            if isinstance(portion_adjustment, int | float):
                attrs["portion_adjustment"] = float(portion_adjustment)

            activated_at = emergency.get("activated_at")
            if isinstance(activated_at, str):
                attrs["activated_at"] = activated_at

            expires_at = emergency.get("expires_at")
            if isinstance(expires_at, str) or expires_at is None:
                attrs["expires_at"] = expires_at

            status = emergency.get("status")
            if isinstance(status, str):
                attrs["status"] = status
        return attrs


class PawControlGardenSessionActiveBinarySensor(PawControlGardenBinarySensorBase):
    """Binary sensor indicating an active garden session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the garden session activity sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "garden_session_active",
            icon_on="mdi:flower",
            icon_off="mdi:flower-outline",
        )

    def _get_is_on_state(self) -> bool:
        data = self._get_garden_data()
        status = data.get("status")
        if isinstance(status, str) and status == "active":
            return True

        garden_manager = self._get_garden_manager()
        if garden_manager is not None:
            return garden_manager.is_dog_in_garden(self._dog_id)

        return False


class PawControlInGardenBinarySensor(PawControlGardenBinarySensorBase):
    """Binary sensor indicating whether the dog is currently in the garden."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the in-garden presence sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "in_garden",
            icon_on="mdi:pine-tree",
            icon_off="mdi:pine-tree-variant-outline",
        )

    def _get_is_on_state(self) -> bool:
        garden_manager = self._get_garden_manager()
        if garden_manager is not None:
            return garden_manager.is_dog_in_garden(self._dog_id)

        data = self._get_garden_data()
        status = data.get("status")
        return isinstance(status, str) and status == "active"


class PawControlGardenPoopPendingBinarySensor(PawControlGardenBinarySensorBase):
    """Binary sensor indicating pending garden poop confirmation."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the pending garden poop confirmation sensor."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "garden_poop_pending",
            icon_on="mdi:emoticon-poop",
            icon_off="mdi:check-circle-outline",
        )

    def _get_is_on_state(self) -> bool:
        garden_manager = self._get_garden_manager()
        if garden_manager is not None:
            return garden_manager.has_pending_confirmation(self._dog_id)

        data = self._get_garden_data()
        pending = data.get("pending_confirmations")
        return isinstance(pending, Sequence) and len(pending) > 0

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Expose how many confirmation prompts are outstanding."""
        attrs = super().extra_state_attributes
        pending = self._get_garden_data().get("pending_confirmations")
        if isinstance(pending, list):
            attrs["pending_confirmations"] = cast(JSONValue, pending)
            attrs["pending_confirmation_count"] = len(pending)
        else:
            attrs["pending_confirmation_count"] = 0
        return attrs
