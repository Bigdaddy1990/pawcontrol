"""Binary sensor platform for Paw Control integration.

This module provides comprehensive binary sensor entities for dog monitoring
including status indicators, alerts, and automated detection sensors. All
binary sensors are designed to meet Home Assistant's Platinum quality standards
with full type annotations, async operations, and robust error handling.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from datetime import datetime
from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTR_DOG_ID
from .const import ATTR_DOG_NAME
from .const import CONF_DOG_ID
from .const import CONF_DOG_NAME
from .const import CONF_DOGS
from .const import DOMAIN
from .const import MODULE_FEEDING
from .const import MODULE_GPS
from .const import MODULE_HEALTH
from .const import MODULE_WALK
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Type aliases for better code readability (Python 3.13 compatible)
AttributeDict = dict[str, Any]


async def _async_add_entities_in_batches(
    async_add_entities_func,
    entities: list[PawControlBinarySensorBase],
    batch_size: int = 15,
    delay_between_batches: float = 0.1,
) -> None:
    """Add binary sensor entities in small batches to prevent Entity Registry overload.

    The Entity Registry logs warnings when >200 messages occur rapidly.
    By batching entities and adding delays, we prevent registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of binary sensor entities to add
        batch_size: Number of entities per batch (default: 15)
        delay_between_batches: Seconds to wait between batches (default: 0.1s)
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
        async_add_entities_func(batch, update_before_add=False)

        # Small delay between batches to prevent Registry flooding
        if i + batch_size < total_entities:  # No delay after last batch
            await asyncio.sleep(delay_between_batches)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control binary sensor platform.

    Creates binary sensor entities for all configured dogs based on their
    enabled modules. Binary sensors provide boolean status indicators for
    various aspects of dog monitoring and care.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry containing dog configurations
        async_add_entities: Callback to add binary sensor entities
    """
    runtime_data = getattr(entry, "runtime_data", None)

    if runtime_data:
        coordinator: PawControlCoordinator = runtime_data["coordinator"]
        dogs: list[dict[str, Any]] = runtime_data.get("dogs", [])
    else:
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        dogs = entry.data.get(CONF_DOGS, [])

    entities: list[PawControlBinarySensorBase] = []

    # Create binary sensors for each configured dog
    for dog in dogs:
        dog_id: str = dog[CONF_DOG_ID]
        dog_name: str = dog[CONF_DOG_NAME]
        modules: dict[str, bool] = dog.get("modules", {})

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

    # Add entities in smaller batches to prevent Entity Registry overload
    # With 46+ binary sensor entities (2 dogs), batching prevents Registry flooding
    await _async_add_entities_in_batches(async_add_entities, entities, batch_size=12)

    _LOGGER.info(
        "Created %d binary sensor entities for %d dogs using batched approach",
        len(entities),
        len(dogs),
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
    """Create feeding-related binary sensors for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of feeding binary sensor entities
    """
    return [
        PawControlIsHungryBinarySensor(coordinator, dog_id, dog_name),
        PawControlFeedingDueBinarySensor(coordinator, dog_id, dog_name),
        PawControlFeedingScheduleOnTrackBinarySensor(coordinator, dog_id, dog_name),
        PawControlDailyFeedingGoalMetBinarySensor(coordinator, dog_id, dog_name),
    ]


def _create_walk_binary_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlBinarySensorBase]:
    """Create walk-related binary sensors for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of walk binary sensor entities
    """
    return [
        PawControlWalkInProgressBinarySensor(coordinator, dog_id, dog_name),
        PawControlNeedsWalkBinarySensor(coordinator, dog_id, dog_name),
        PawControlWalkGoalMetBinarySensor(coordinator, dog_id, dog_name),
        PawControlLongWalkOverdueBinarySensor(coordinator, dog_id, dog_name),
    ]


def _create_gps_binary_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlBinarySensorBase]:
    """Create GPS and location-related binary sensors for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of GPS binary sensor entities
    """
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
    """Create health and medical-related binary sensors for a dog.

    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog

    Returns:
        List of health binary sensor entities
    """
    return [
        PawControlHealthAlertBinarySensor(coordinator, dog_id, dog_name),
        PawControlWeightAlertBinarySensor(coordinator, dog_id, dog_name),
        PawControlMedicationDueBinarySensor(coordinator, dog_id, dog_name),
        PawControlVetCheckupDueBinarySensor(coordinator, dog_id, dog_name),
        PawControlGroomingDueBinarySensor(coordinator, dog_id, dog_name),
        PawControlActivityLevelConcernBinarySensor(coordinator, dog_id, dog_name),
    ]


class PawControlBinarySensorBase(
    CoordinatorEntity[PawControlCoordinator], BinarySensorEntity
):
    """Base class for all Paw Control binary sensor entities.

    Provides common functionality and ensures consistent behavior across
    all binary sensor types. Includes proper device grouping, state management,
    and error handling.
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
        """Initialize the binary sensor entity.

        Args:
            coordinator: Data coordinator for updates
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
            sensor_type: Type identifier for the sensor
            device_class: Home Assistant device class
            icon_on: Material Design icon when sensor is on
            icon_off: Material Design icon when sensor is off
            entity_category: Entity category for organization
        """
        super().__init__(coordinator)

        self._dog_id = dog_id
        self._dog_name = dog_name
        self._sensor_type = sensor_type
        self._icon_on = icon_on
        self._icon_off = icon_off

        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{sensor_type}"
        self._attr_name = f"{dog_name} {sensor_type.replace('_', ' ').title()}"
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category

        # Device info for proper grouping - HA 2025.8+ compatible with configuration_url
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog_id)},
            "name": dog_name,
            "manufacturer": "Paw Control",
            "model": "Smart Dog Monitoring",
            "sw_version": "1.0.0",
            "configuration_url": "https://github.com/BigDaddy1990/pawcontrol",
        }

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
        """Return the icon to use in the frontend.

        Dynamically changes icon based on sensor state for better UX.

        Returns:
            Material Design icon string
        """
        if self.is_on and self._icon_on:
            return self._icon_on
        elif not self.is_on and self._icon_off:
            return self._icon_off
        else:
            # Fallback to device class default or generic icon
            return "mdi:information-outline"

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for the binary sensor.

        Provides common attributes that are useful across all binary sensors
        including dog identification and last update information.

        Returns:
            Dictionary of additional state attributes
        """
        attrs: AttributeDict = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "last_update": dt_util.utcnow().isoformat(),
            "sensor_type": self._sensor_type,
        }

        # Add dog-specific information
        dog_data = self._get_dog_data()
        if isinstance(dog_data, dict) and "dog_info" in dog_data:
            dog_info = dog_data["dog_info"]
            attrs.update(
                {
                    "dog_breed": dog_info.get("dog_breed", ""),
                    "dog_age": dog_info.get("dog_age"),
                    "dog_size": dog_info.get("dog_size"),
                    "dog_weight": dog_info.get("dog_weight"),
                }
            )

        return attrs

    def _get_dog_data(self) -> dict[str, Any] | None:
        """Get data for this sensor's dog from the coordinator.

        Returns:
            Dog data dictionary or None if not available
        """
        if not self.coordinator.available:
            return None

        return self.coordinator.get_dog_data(self._dog_id)

    def _get_module_data(self, module: str) -> dict[str, Any] | None:
        """Get specific module data for this dog.

        Args:
            module: Module name to retrieve data for

        Returns:
            Module data dictionary or None if not available
        """
        return self.coordinator.get_module_data(self._dog_id, module)

    @property
    def available(self) -> bool:
        """Return if the binary sensor is available.

        A binary sensor is available when the coordinator is available and
        the dog data can be retrieved.

        Returns:
            True if sensor is available, False otherwise
        """
        return self.coordinator.available and self._get_dog_data() is not None


# Base binary sensors
class PawControlOnlineBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if the dog monitoring system is online.

    This sensor provides overall connectivity and system health status
    for the dog's monitoring components.
    """

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
        dog_data = self._get_dog_data()
        if not dog_data:
            return False

        last_update = dog_data.get("last_update")
        if last_update:
            try:
                last_update_dt = datetime.fromisoformat(last_update)
                time_diff = dt_util.utcnow() - last_update_dt
                return time_diff < timedelta(minutes=10)
            except (ValueError, TypeError):
                return False

        return False

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for the online sensor."""
        attrs = super().extra_state_attributes
        dog_data = self._get_dog_data()

        if dog_data:
            attrs.update(
                {
                    "last_update": dog_data.get("last_update"),
                    "status": dog_data.get("status", STATE_UNKNOWN),
                    "enabled_modules": dog_data.get("enabled_modules", []),
                    "system_health": "healthy" if self.is_on else "disconnected",
                }
            )

        return attrs


class PawControlAttentionNeededBinarySensor(PawControlBinarySensorBase):
    """Binary sensor indicating if the dog needs immediate attention.

    This aggregated sensor considers multiple factors to determine if
    the dog requires immediate care or attention from the owner.
    """

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
        """Return True if the dog needs immediate attention.

        Evaluates multiple conditions across all modules to determine
        if urgent attention is required.

        Returns:
            True if attention is needed
        """
        dog_data = self._get_dog_data()
        if not dog_data:
            return False

        attention_reasons = []

        # Check feeding urgency
        feeding_data = dog_data.get("feeding", {})
        if feeding_data.get("is_hungry", False):
            last_feeding_hours = feeding_data.get("last_feeding_hours")
            if last_feeding_hours and last_feeding_hours > 12:  # Very hungry
                attention_reasons.append("critically_hungry")
            elif feeding_data.get("is_hungry"):
                attention_reasons.append("hungry")

        # Check walk urgency
        walk_data = dog_data.get("walk", {})
        if walk_data.get("needs_walk", False):
            last_walk_hours = walk_data.get("last_walk_hours")
            if last_walk_hours and last_walk_hours > 12:
                attention_reasons.append("urgent_walk_needed")
            else:
                attention_reasons.append("needs_walk")

        # Check health alerts
        health_data = dog_data.get("health", {})
        health_alerts = health_data.get("health_alerts", [])
        if health_alerts:
            attention_reasons.append("health_alert")

        # Check GPS alerts
        gps_data = dog_data.get("gps", {})
        if not gps_data.get("in_safe_zone", True):
            attention_reasons.append("outside_safe_zone")

        # Store reasons in attributes for debugging
        self._attention_reasons = attention_reasons

        return len(attention_reasons) > 0

    @property
    def extra_state_attributes(self) -> AttributeDict:
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
        """Calculate the urgency level based on attention reasons.

        Returns:
            Urgency level string
        """
        if not hasattr(self, "_attention_reasons"):
            return "none"

        urgent_conditions = ["critically_hungry", "health_alert"]

        if any(reason in urgent_conditions for reason in self._attention_reasons):
            return "high"
        elif len(self._attention_reasons) > 2:
            return "medium"
        elif len(self._attention_reasons) > 0:
            return "low"
        else:
            return "none"

    def _get_recommended_actions(self) -> list[str]:
        """Get recommended actions based on attention reasons.

        Returns:
            List of recommended action strings
        """
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
    """Binary sensor indicating if visitor mode is active.

    Visitor mode modifies notification behavior and monitoring sensitivity
    when the dog is being cared for by someone else.
    """

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
        dog_data = self._get_dog_data()
        if not dog_data:
            return False

        return dog_data.get("visitor_mode_active", False)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for visitor mode."""
        attrs = super().extra_state_attributes
        dog_data = self._get_dog_data()

        if dog_data:
            attrs.update(
                {
                    "visitor_mode_started": dog_data.get("visitor_mode_started"),
                    "visitor_name": dog_data.get("visitor_name"),
                    "modified_notifications": dog_data.get(
                        "visitor_mode_settings", {}
                    ).get("modified_notifications", True),
                    "reduced_alerts": dog_data.get("visitor_mode_settings", {}).get(
                        "reduced_alerts", True
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
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return False

        return feeding_data.get("is_hungry", False)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional feeding status attributes."""
        attrs = super().extra_state_attributes
        feeding_data = self._get_module_data("feeding")

        if feeding_data:
            attrs.update(
                {
                    "last_feeding": feeding_data.get("last_feeding"),
                    "last_feeding_hours": feeding_data.get("last_feeding_hours"),
                    "next_feeding_due": feeding_data.get("next_feeding_due"),
                    "hunger_level": self._calculate_hunger_level(feeding_data),
                }
            )

        return attrs

    def _calculate_hunger_level(self, feeding_data: dict[str, Any]) -> str:
        """Calculate hunger level based on time since last feeding.

        Args:
            feeding_data: Feeding module data

        Returns:
            Hunger level description
        """
        last_feeding_hours = feeding_data.get("last_feeding_hours")

        if not last_feeding_hours:
            return STATE_UNKNOWN

        if last_feeding_hours > 12:
            return "very_hungry"
        elif last_feeding_hours >= 8:
            return "hungry"
        elif last_feeding_hours >= 6:
            return "somewhat_hungry"
        else:
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
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return False

        next_feeding_due = feeding_data.get("next_feeding_due")
        if not next_feeding_due:
            return False

        try:
            due_time = datetime.fromisoformat(next_feeding_due)
            return dt_util.utcnow() >= due_time
        except (ValueError, TypeError):
            return False


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
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return True  # Assume on track if no data

        adherence = feeding_data.get("feeding_schedule_adherence", 100.0)
        return adherence >= 80.0  # 80% adherence threshold


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
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return False

        return feeding_data.get("daily_target_met", False)


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
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return False

        return walk_data.get("walk_in_progress", False)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional walk progress attributes."""
        attrs = super().extra_state_attributes
        walk_data = self._get_module_data("walk")

        if walk_data and walk_data.get("walk_in_progress"):
            attrs.update(
                {
                    "walk_start_time": walk_data.get("current_walk_start"),
                    "walk_duration": walk_data.get("current_walk_duration", 0),
                    "walk_distance": walk_data.get("current_walk_distance", 0),
                    "estimated_remaining": self._estimate_remaining_time(walk_data),
                }
            )

        return attrs

    def _estimate_remaining_time(self, walk_data: dict[str, Any]) -> int | None:
        """Estimate remaining walk time based on typical patterns.

        Args:
            walk_data: Walk module data

        Returns:
            Estimated remaining minutes or None
        """
        current_duration = walk_data.get("current_walk_duration", 0)
        average_duration = walk_data.get("average_walk_duration")

        if average_duration and current_duration < average_duration:
            return int(average_duration - current_duration)

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
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return False

        return walk_data.get("needs_walk", False)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional walk need attributes."""
        attrs = super().extra_state_attributes
        walk_data = self._get_module_data("walk")

        if walk_data:
            attrs.update(
                {
                    "last_walk": walk_data.get("last_walk"),
                    "last_walk_hours": walk_data.get("last_walk_hours"),
                    "walks_today": walk_data.get("walks_today", 0),
                    "urgency_level": self._calculate_walk_urgency(walk_data),
                }
            )

        return attrs

    def _calculate_walk_urgency(self, walk_data: dict[str, Any]) -> str:
        """Calculate walk urgency level.

        Args:
            walk_data: Walk module data

        Returns:
            Urgency level description
        """
        last_walk_hours = walk_data.get("last_walk_hours")

        if not last_walk_hours:
            return STATE_UNKNOWN

        if last_walk_hours > 12:
            return "urgent"
        elif last_walk_hours > 8:
            return "high"
        elif last_walk_hours > 6:
            return "medium"
        else:
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
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return False

        return walk_data.get("walk_goal_met", False)


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
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return False

        # Check if last long walk (>30 min) was more than 3 days ago
        last_long_walk = walk_data.get("last_long_walk")
        if not last_long_walk:
            return True  # No long walk recorded

        try:
            last_long_walk_dt = datetime.fromisoformat(last_long_walk)
            days_since = (dt_util.utcnow() - last_long_walk_dt).days
            return days_since > 3
        except (ValueError, TypeError):
            return True


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
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return True  # Assume home if no GPS data

        return gps_data.get("zone") == "home"

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional location attributes."""
        attrs = super().extra_state_attributes
        gps_data = self._get_module_data("gps")

        if gps_data:
            attrs.update(
                {
                    "current_zone": gps_data.get("zone", STATE_UNKNOWN),
                    "distance_from_home": gps_data.get("distance_from_home"),
                    "last_seen": gps_data.get("last_seen"),
                    "accuracy": gps_data.get("accuracy"),
                }
            )

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
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return True  # Assume safe if no GPS data

        # Check if in home zone or other defined safe zones
        current_zone = gps_data.get("zone")
        safe_zones = ["home", "park", "vet", "friend_house"]  # Configurable

        return current_zone in safe_zones


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
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return False

        accuracy = gps_data.get("accuracy")
        last_seen = gps_data.get("last_seen")

        # Check accuracy threshold and data freshness
        accuracy_good = accuracy and accuracy <= 50  # 50 meter threshold

        data_fresh = False
        if last_seen:
            with suppress(ValueError, TypeError):
                last_seen_dt = datetime.fromisoformat(last_seen)
                time_diff = dt_util.utcnow() - last_seen_dt
                data_fresh = time_diff < timedelta(minutes=5)

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
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return False

        speed = gps_data.get("speed", 0)
        return speed is not None and speed > 1.0  # 1 km/h threshold for movement


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
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return False

        return gps_data.get("geofence_alert", False)


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
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return False

        battery_level = gps_data.get("battery_level")
        if battery_level is not None:
            return battery_level <= 20  # 20% threshold

        return False


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
        health_data = self._get_module_data("health")
        if not health_data:
            return False

        health_alerts = health_data.get("health_alerts", [])
        return len(health_alerts) > 0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return health alert details."""
        attrs = super().extra_state_attributes
        health_data = self._get_module_data("health")

        if health_data:
            attrs.update(
                {
                    "health_alerts": health_data.get("health_alerts", []),
                    "health_status": health_data.get("health_status", "good"),
                    "alert_count": len(health_data.get("health_alerts", [])),
                }
            )

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
        health_data = self._get_module_data("health")
        if not health_data:
            return False

        weight_change_percent = health_data.get("weight_change_percent", 0)
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
        health_data = self._get_module_data("health")
        if not health_data:
            return False

        medications_due = health_data.get("medications_due", [])
        return len(medications_due) > 0


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
        health_data = self._get_module_data("health")
        if not health_data:
            return False

        next_checkup = health_data.get("next_checkup_due")
        if not next_checkup:
            return False

        try:
            checkup_date = datetime.fromisoformat(next_checkup)
            return dt_util.utcnow().date() >= checkup_date.date()
        except (ValueError, TypeError):
            return False


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
            "grooming_due",
            icon_on="mdi:content-cut",
            icon_off="mdi:check",
        )

    def _get_is_on_state(self) -> bool:
        """Return True if grooming is due."""
        health_data = self._get_module_data("health")
        if not health_data:
            return False

        return health_data.get("grooming_due", False)


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
        health_data = self._get_module_data("health")
        if not health_data:
            return False

        activity_level = health_data.get("activity_level", "normal")
        concerning_levels = ["very_low", "very_high"]

        return activity_level in concerning_levels

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return activity level concern details."""
        attrs = super().extra_state_attributes
        health_data = self._get_module_data("health")

        if health_data:
            activity_level = health_data.get("activity_level", "normal")
            attrs.update(
                {
                    "current_activity_level": activity_level,
                    "concern_reason": self._get_concern_reason(activity_level),
                    "recommended_action": self._get_recommended_action(activity_level),
                }
            )

        return attrs

    def _get_concern_reason(self, activity_level: str) -> str:
        """Get reason for activity level concern.

        Args:
            activity_level: Current activity level

        Returns:
            Reason for concern
        """
        if activity_level == "very_low":
            return "Activity level is unusually low"
        elif activity_level == "very_high":
            return "Activity level is unusually high"
        else:
            return "No concern"

    def _get_recommended_action(self, activity_level: str) -> str:
        """Get recommended action for activity level concern.

        Args:
            activity_level: Current activity level

        Returns:
            Recommended action
        """
        if activity_level == "very_low":
            return "Consider vet consultation or encouraging more activity"
        elif activity_level == "very_high":
            return "Monitor for signs of distress or illness"
        else:
            return "Continue normal monitoring"
