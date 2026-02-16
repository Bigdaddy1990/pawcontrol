"""Binary sensor platform for Paw Control integration.

This module provides comprehensive binary sensor entities for dog monitoring
including status indicators, alerts, and automated detection sensors. All
binary sensors are designed to meet Home Assistant's Platinum quality ambitions
with full type annotations, async operations, and robust error handling.

OPTIMIZED: Consistent runtime_data usage, thread-safe caching, reduced code duplication.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from inspect import isawaitable
import logging
import os
from typing import TYPE_CHECKING, Literal, cast

from homeassistant.components.binary_sensor import (
  BinarySensorDeviceClass,
  BinarySensorEntity,
  BinarySensorEntityDescription,
)
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
  DEFAULT_MODEL,
  DEFAULT_SW_VERSION,
  MODULE_FEEDING,
  MODULE_GARDEN,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .entity import PawControlDogEntityBase
from .runtime_data import get_runtime_data
from .types import (
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  VISITOR_MODE_ACTIVE_FIELD,
  WALK_IN_PROGRESS_FIELD,
  CoordinatorTypedModuleName,
  DogConfigData,
  EntityAttributeDateMutableMapping,
  FeedingModulePayload,
  GardenModulePayload,
  GPSModulePayload,
  HealthModulePayload,
  JSONMapping,
  JSONMutableMapping,
  JSONValue,
  PawControlConfigEntry,
  WalkModulePayload,
  ensure_dog_config_data,
  ensure_dog_modules_mapping,
)
from .utils import ensure_utc_datetime, normalise_entity_attributes

if TYPE_CHECKING:
  from .garden_manager import GardenManager  # noqa: E111


_LOGGER = logging.getLogger(__name__)

_RUNNING_DEVICE_CLASS = cast(
  BinarySensorDeviceClass,
  getattr(BinarySensorDeviceClass, "RUNNING", "running"),
)

type AttributeDict = EntityAttributeDateMutableMapping
type SafeZoneName = Literal["home", "park", "vet", "friend_house"]


def _coerce_bool_flag(value: object) -> bool | None:
  """Return a strict boolean for 0/1 sentinel payloads."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return value

  if isinstance(value, int | float) and value in (0, 1):  # noqa: E111
    return bool(value)

  return None  # noqa: E111


def _as_local(dt_value: datetime) -> datetime:
  """Return a timezone-aware datetime in the local timezone."""  # noqa: E111

  if hasattr(dt_util, "as_local"):  # noqa: E111
    return dt_util.as_local(dt_value)

  target = dt_value  # noqa: E111
  if target.tzinfo is None:  # noqa: E111
    target = target.replace(tzinfo=UTC)

  local_tz = getattr(dt_util, "DEFAULT_TIME_ZONE", None)  # noqa: E111
  if local_tz is None:  # noqa: E111
    return target

  try:  # noqa: E111
    return target.astimezone(local_tz)
  except Exception:  # pragma: no cover - defensive fallback  # noqa: E111
    return target


def _normalise_attributes(
  attrs: Mapping[str, object],
) -> JSONMutableMapping:
  """Return JSON-serialisable attributes for entity state."""  # noqa: E111

  return normalise_entity_attributes(attrs)  # noqa: E111


def _coerce_timestamp(value: object | None) -> datetime | None:
  """Return a UTC datetime for supported timestamp values."""  # noqa: E111

  if value is None:  # noqa: E111
    return None

  if isinstance(value, datetime | date | str | int | float):  # noqa: E111
    return ensure_utc_datetime(value)

  return None  # noqa: E111


def _apply_standard_timing_attributes(
  attrs: AttributeDict,
  *,
  started_at: object | None,
  duration_minutes: object | None,
  last_seen: object | None,
) -> None:
  """Populate standardized timing attributes on the attribute mapping."""  # noqa: E111

  attrs["started_at"] = _coerce_timestamp(started_at)  # noqa: E111

  if isinstance(duration_minutes, int | float):  # noqa: E111
    attrs["duration_minutes"] = float(duration_minutes)
  else:  # noqa: E111
    attrs["duration_minutes"] = None

  attrs["last_seen"] = _coerce_timestamp(last_seen)  # noqa: E111


# Home Assistant platform configuration
PARALLEL_UPDATES = 0

FEEDING_MODULE = cast(CoordinatorTypedModuleName, MODULE_FEEDING)
GARDEN_MODULE = cast(CoordinatorTypedModuleName, MODULE_GARDEN)
GPS_MODULE = cast(CoordinatorTypedModuleName, MODULE_GPS)
HEALTH_MODULE = cast(CoordinatorTypedModuleName, MODULE_HEALTH)
WALK_MODULE = cast(CoordinatorTypedModuleName, MODULE_WALK)


# OPTIMIZED: Shared logic patterns to reduce code duplication
class BinarySensorLogicMixin:
  """Mixin providing shared logic patterns for binary sensors."""  # noqa: E111

  @staticmethod  # noqa: E111
  def _calculate_time_based_status(  # noqa: E111
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
      return default_if_none  # noqa: E111

    timestamp = ensure_utc_datetime(timestamp_value)
    if timestamp is None:
      return default_if_none  # noqa: E111

    time_diff = dt_util.utcnow() - timestamp
    return time_diff < timedelta(hours=threshold_hours)

  @staticmethod  # noqa: E111
  def _evaluate_threshold(  # noqa: E111
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
      return default_if_none  # noqa: E111

    try:
      num_value = float(value)  # noqa: E111
      if comparison == "greater":  # noqa: E111
        return num_value > threshold
      if comparison == "less":  # noqa: E111
        return num_value < threshold
      if comparison == "greater_equal":  # noqa: E111
        return num_value >= threshold
      if comparison == "less_equal":  # noqa: E111
        return num_value <= threshold
      raise ValueError(f"Unknown comparison: {comparison}")  # noqa: E111

    except ValueError:
      _LOGGER.debug(  # noqa: E111
        "Failed to compare non-numeric value '%s' against threshold %s",
        value,
        threshold,
      )
      return default_if_none  # noqa: E111
    except TypeError:
      _LOGGER.debug(  # noqa: E111
        "Failed to compare value of unsupported type %s against threshold %s",
        type(value).__name__,
        threshold,
      )
      return default_if_none  # noqa: E111


async def async_setup_entry(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
  async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up Paw Control binary sensor platform."""  # noqa: E111

  # OPTIMIZED: Consistent runtime_data usage for Platinum readiness  # noqa: E114
  runtime_data = get_runtime_data(hass, entry)  # noqa: E111
  if runtime_data is None:  # noqa: E111
    _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
    return
  coordinator = runtime_data.coordinator  # noqa: E111
  raw_dogs = getattr(runtime_data, "dogs", [])  # noqa: E111
  dog_configs: list[DogConfigData] = []  # noqa: E111
  for raw_dog in raw_dogs:  # noqa: E111
    if not isinstance(raw_dog, Mapping):
      continue  # noqa: E111

    normalised = ensure_dog_config_data(cast(JSONMapping, raw_dog))
    if normalised is None:
      continue  # noqa: E111

    dog_configs.append(normalised)

  if not dog_configs:  # noqa: E111
    return

  entities: list[PawControlBinarySensorBase] = []  # noqa: E111

  # Create binary sensors for each configured dog  # noqa: E114
  for dog in dog_configs:  # noqa: E111
    dog_id: str = dog[DOG_ID_FIELD]
    dog_name: str = dog[DOG_NAME_FIELD]
    modules = ensure_dog_modules_mapping(dog)

    # Base binary sensors - always created for every dog
    entities.extend(
      _create_base_binary_sensors(
        coordinator,
        dog_id,
        dog_name,
      ),
    )

    # Module-specific binary sensors
    if modules.get(MODULE_FEEDING, False):
      entities.extend(  # noqa: E111
        _create_feeding_binary_sensors(coordinator, dog_id, dog_name),
      )

    if modules.get(MODULE_WALK, False):
      entities.extend(  # noqa: E111
        _create_walk_binary_sensors(
          coordinator,
          dog_id,
          dog_name,
        ),
      )

    if modules.get(MODULE_GPS, False):
      entities.extend(  # noqa: E111
        _create_gps_binary_sensors(
          coordinator,
          dog_id,
          dog_name,
        ),
      )

    if modules.get(MODULE_HEALTH, False):
      entities.extend(  # noqa: E111
        _create_health_binary_sensors(coordinator, dog_id, dog_name),
      )

    if modules.get(MODULE_GARDEN, False):
      entities.extend(  # noqa: E111
        _create_garden_binary_sensors(coordinator, dog_id, dog_name),
      )

  if entities:  # noqa: E111
    add_result = async_add_entities(entities)
    if isawaitable(add_result):
      await add_result  # noqa: E111


def _create_base_binary_sensors(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlBinarySensorBase]:
  """Create base binary sensors that are always present for every dog.

  Args:
      coordinator: Data coordinator instance
      dog_id: Unique identifier for the dog
      dog_name: Display name for the dog

  Returns:
      List of base binary sensor entities
  """  # noqa: E111
  return [  # noqa: E111
    PawControlOnlineBinarySensor(coordinator, dog_id, dog_name),
    PawControlAttentionNeededBinarySensor(coordinator, dog_id, dog_name),
    PawControlVisitorModeBinarySensor(coordinator, dog_id, dog_name),
  ]


def _create_feeding_binary_sensors(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlBinarySensorBase]:
  """Create feeding-related binary sensors for a dog."""  # noqa: E111
  return [  # noqa: E111
    PawControlIsHungryBinarySensor(coordinator, dog_id, dog_name),
    PawControlFeedingDueBinarySensor(coordinator, dog_id, dog_name),
    PawControlFeedingScheduleOnTrackBinarySensor(
      coordinator,
      dog_id,
      dog_name,
    ),
    PawControlDailyFeedingGoalMetBinarySensor(
      coordinator,
      dog_id,
      dog_name,
    ),
  ]


def _create_walk_binary_sensors(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlBinarySensorBase]:
  """Create walk-related binary sensors for a dog."""  # noqa: E111
  return [  # noqa: E111
    PawControlWalkInProgressBinarySensor(coordinator, dog_id, dog_name),
    PawControlNeedsWalkBinarySensor(coordinator, dog_id, dog_name),
    PawControlWalkGoalMetBinarySensor(coordinator, dog_id, dog_name),
    PawControlLongWalkOverdueBinarySensor(coordinator, dog_id, dog_name),
  ]


def _create_gps_binary_sensors(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlBinarySensorBase]:
  """Create GPS and location-related binary sensors for a dog."""  # noqa: E111
  return [  # noqa: E111
    PawControlIsHomeBinarySensor(coordinator, dog_id, dog_name),
    PawControlInSafeZoneBinarySensor(coordinator, dog_id, dog_name),
    PawControlGPSAccuratelyTrackedBinarySensor(
      coordinator,
      dog_id,
      dog_name,
    ),
    PawControlMovingBinarySensor(coordinator, dog_id, dog_name),
    PawControlGeofenceAlertBinarySensor(coordinator, dog_id, dog_name),
    PawControlGPSBatteryLowBinarySensor(coordinator, dog_id, dog_name),
  ]


def _create_health_binary_sensors(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlBinarySensorBase]:
  """Create health and medical-related binary sensors for a dog."""  # noqa: E111
  return [  # noqa: E111
    PawControlHealthAlertBinarySensor(coordinator, dog_id, dog_name),
    PawControlWeightAlertBinarySensor(coordinator, dog_id, dog_name),
    PawControlMedicationDueBinarySensor(coordinator, dog_id, dog_name),
    PawControlVetCheckupDueBinarySensor(coordinator, dog_id, dog_name),
    PawControlGroomingDueBinarySensor(coordinator, dog_id, dog_name),
    PawControlActivityLevelConcernBinarySensor(
      coordinator,
      dog_id,
      dog_name,
    ),
    PawControlHealthAwareFeedingBinarySensor(
      coordinator,
      dog_id,
      dog_name,
    ),
    PawControlMedicationWithMealsBinarySensor(
      coordinator,
      dog_id,
      dog_name,
    ),
    PawControlHealthEmergencyBinarySensor(coordinator, dog_id, dog_name),
  ]


def _create_garden_binary_sensors(
  coordinator: PawControlCoordinator,
  dog_id: str,
  dog_name: str,
) -> list[PawControlBinarySensorBase]:
  """Create garden-related binary sensors for a dog."""  # noqa: E111

  return [  # noqa: E111
    PawControlGardenSessionActiveBinarySensor(
      coordinator,
      dog_id,
      dog_name,
    ),
    PawControlInGardenBinarySensor(coordinator, dog_id, dog_name),
    PawControlGardenPoopPendingBinarySensor(coordinator, dog_id, dog_name),
  ]


class PawControlBinarySensorBase(
  PawControlDogEntityBase,
  BinarySensorEntity,
  BinarySensorLogicMixin,
):
  """Base class for all Paw Control binary sensor entities.

  OPTIMIZED: Thread-safe caching, shared logic patterns, improved performance.
  """  # noqa: E111

  def __init__(  # noqa: E111
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
    self.entity_description = BinarySensorEntityDescription(
      key=sensor_type,
      translation_key=sensor_type,
      device_class=device_class,
      entity_category=entity_category,
    )

    # Link entity to PawControl device entry for the dog
    self.update_device_metadata(
      model=DEFAULT_MODEL,
      sw_version=DEFAULT_SW_VERSION,
    )

    self._set_cache_ttl(30.0)

  @property  # noqa: E111
  def is_on(self) -> bool:  # noqa: E111
    """Return the sensor's state, allowing for test overrides."""
    if hasattr(self, "_test_is_on"):
      return self._test_is_on  # noqa: E111
    return self._get_is_on_state()

  @is_on.setter  # noqa: E111
  def is_on(self, value: bool) -> None:  # noqa: E111
    """Set the sensor's state for testing."""
    if "PYTEST_CURRENT_TEST" not in os.environ:
      raise AttributeError("is_on is read-only")  # noqa: E111
    self._test_is_on = value

  @is_on.deleter  # noqa: E111
  def is_on(self) -> None:  # noqa: E111
    """Delete the test override for the sensor's state."""
    if hasattr(self, "_test_is_on"):
      del self._test_is_on  # noqa: E111

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return the actual state of the sensor. Subclasses should override."""
    return False

  def _inherit_extra_attributes(self) -> AttributeDict:  # noqa: E111
    """Return a mutable copy of inherited attributes."""

    return cast(
      AttributeDict, normalise_entity_attributes(super().extra_state_attributes)
    )

  @property  # noqa: E111
  def icon(self) -> str | None:  # noqa: E111
    """Return the icon to use in the frontend."""
    if self.is_on and self._icon_on:
      return self._icon_on  # noqa: E111
    if not self.is_on and self._icon_off:
      return self._icon_off  # noqa: E111
    return "mdi:information-outline"

  @property  # noqa: E111
  def device_class(self) -> BinarySensorDeviceClass | None:  # noqa: E111
    """Expose the configured device class for test doubles."""

    return getattr(self, "_attr_device_class", None)

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional state attributes for the binary sensor."""
    attrs = self._build_entity_attributes(self._extra_state_attributes())
    return self._finalize_entity_attributes(attrs)

  def _extra_state_attributes(self) -> Mapping[str, object] | None:  # noqa: E111
    """Return additional attributes shared by binary sensors."""

    return {
      "last_update": _as_local(dt_util.utcnow()).isoformat(),
      "sensor_type": self._sensor_type,
    }

  def _get_feeding_payload(self) -> FeedingModulePayload | None:  # noqa: E111
    """Return the structured feeding payload when available."""

    module_state = self._get_module_data(FEEDING_MODULE)
    return cast(FeedingModulePayload, module_state) if module_state else None

  def _get_walk_payload(self) -> WalkModulePayload | None:  # noqa: E111
    """Return the structured walk payload when available."""

    module_state = self._get_module_data(WALK_MODULE)
    return cast(WalkModulePayload, module_state) if module_state else None

  def _get_gps_payload(self) -> GPSModulePayload | None:  # noqa: E111
    """Return the structured GPS payload when available."""

    module_state = self._get_module_data(GPS_MODULE)
    return cast(GPSModulePayload, module_state) if module_state else None

  def _get_health_payload(self) -> HealthModulePayload | None:  # noqa: E111
    """Return the structured health payload when available."""

    module_state = self._get_module_data(HEALTH_MODULE)
    return cast(HealthModulePayload, module_state) if module_state else None

  def _get_garden_payload(self) -> GardenModulePayload | None:  # noqa: E111
    """Return the structured garden payload when available."""

    module_state = self._get_module_data(GARDEN_MODULE)
    return cast(GardenModulePayload, module_state) if module_state else None

  @property  # noqa: E111
  def available(self) -> bool:  # noqa: E111
    """Return if the binary sensor is available."""
    return self.coordinator.available and self._get_dog_data_cached() is not None


# Garden-specific binary sensor base


class PawControlGardenBinarySensorBase(PawControlBinarySensorBase):
  """Base class for garden binary sensors."""  # noqa: E111

  def _apply_garden_common_attributes(self, attrs: AttributeDict) -> None:  # noqa: E111
    """Populate common garden telemetry attributes for garden sensors."""

    data = self._get_garden_data()
    garden_status = data.get("status")
    if garden_status is not None:
      attrs["garden_status"] = garden_status  # noqa: E111

    sessions_today = data.get("sessions_today")
    if sessions_today is not None:
      attrs["sessions_today"] = sessions_today  # noqa: E111

    pending_confirmations = data.get("pending_confirmations")
    if pending_confirmations is not None:
      attrs["pending_confirmations"] = cast(JSONValue, pending_confirmations)  # noqa: E111

    active_session = data.get("active_session")
    last_session = data.get("last_session")
    started_at = None
    duration_minutes = None
    last_seen = None
    if isinstance(active_session, Mapping):
      started_at = active_session.get("start_time")  # noqa: E111
      duration_minutes = active_session.get("duration_minutes")  # noqa: E111
    if started_at is None and isinstance(last_session, Mapping):
      started_at = last_session.get("start_time")  # noqa: E111
    if duration_minutes is None and isinstance(last_session, Mapping):
      duration_minutes = last_session.get("duration_minutes")  # noqa: E111
    if isinstance(last_session, Mapping):
      last_seen = last_session.get("end_time")  # noqa: E111

    _apply_standard_timing_attributes(
      attrs,
      started_at=started_at,
      duration_minutes=duration_minutes,
      last_seen=last_seen,
    )

  def _get_garden_manager(self) -> GardenManager | None:  # noqa: E111
    """Return the configured garden manager when available."""

    return self._get_runtime_managers().garden_manager

  def _get_garden_data(self) -> GardenModulePayload:  # noqa: E111
    """Return garden snapshot data for the dog."""

    payload = self._get_garden_payload()
    if payload:
      return payload  # noqa: E111

    garden_manager = self._get_garden_manager()
    if garden_manager is not None:
      try:  # noqa: E111
        return garden_manager.build_garden_snapshot(self._dog_id)
      except Exception as err:  # pragma: no cover - defensive logging  # noqa: E111
        _LOGGER.debug(
          "Garden snapshot fallback failed for %s: %s",
          self._dog_id,
          err,
        )

    return cast(GardenModulePayload, {})

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Expose the latest garden telemetry for diagnostics dashboards."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    self._apply_garden_common_attributes(attrs)
    return _normalise_attributes(attrs)


# Base binary sensors
class PawControlOnlineBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if the dog monitoring system is online."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if the dog monitoring system is online."""
    dog_data = self._get_dog_data_cached()
    if not dog_data:
      return False  # noqa: E111

    last_update = dog_data.get("last_update")
    return self._calculate_time_based_status(
      last_update,
      10.0 / 60,
      False,
    )  # 10 minutes

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional attributes for the online sensor."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    dog_data = self._get_dog_data_cached()

    if dog_data:
      last_update = dog_data.get("last_update")  # noqa: E111
      if isinstance(last_update, datetime):  # noqa: E111
        attrs["last_update"] = _as_local(last_update).isoformat()
      elif isinstance(last_update, str):  # noqa: E111
        attrs["last_update"] = last_update

      attrs["status"] = dog_data.get("status", STATE_UNKNOWN)  # noqa: E111
      enabled_modules = sorted(  # noqa: E111
        self.coordinator.get_enabled_modules(self._dog_id),
      )
      if enabled_modules:  # noqa: E111
        attrs["enabled_modules"] = list(enabled_modules)
      attrs["system_health"] = "healthy" if self.is_on else "disconnected"  # noqa: E111

    return _normalise_attributes(attrs)


class PawControlAttentionNeededBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if the dog needs immediate attention."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if the dog needs immediate attention."""
    attention_reasons: list[str] = []

    feeding_data = self._get_feeding_payload()
    if feeding_data and bool(feeding_data.get("is_hungry", False)):
      last_feeding_hours = feeding_data.get("last_feeding_hours")  # noqa: E111
      if isinstance(last_feeding_hours, int | float) and float(last_feeding_hours) > 12:  # noqa: E111
        attention_reasons.append("critically_hungry")
      else:  # noqa: E111
        attention_reasons.append("hungry")

    walk_data = self._get_walk_payload()
    if walk_data and bool(walk_data.get("needs_walk", False)):
      last_walk_hours = walk_data.get("last_walk_hours")  # noqa: E111
      if isinstance(last_walk_hours, int | float) and float(last_walk_hours) > 12:  # noqa: E111
        attention_reasons.append("urgent_walk_needed")
      else:  # noqa: E111
        attention_reasons.append("needs_walk")

    health_data = self._get_health_payload()
    if health_data:
      health_alerts = health_data.get("health_alerts", [])  # noqa: E111
      if isinstance(health_alerts, Sequence) and health_alerts:  # noqa: E111
        attention_reasons.append("health_alert")

    status_snapshot = self._get_status_snapshot()
    if status_snapshot is not None:
      if not bool(status_snapshot.get("in_safe_zone", True)):  # noqa: E111
        attention_reasons.append("outside_safe_zone")
    else:
      gps_data = self._get_gps_payload()  # noqa: E111
      if gps_data is not None:  # noqa: E111
        geofence_status = gps_data.get("geofence_status")
        in_safe_zone = True
        if isinstance(geofence_status, Mapping):
          in_safe_zone = bool(  # noqa: E111
            geofence_status.get("in_safe_zone", True),
          )
        if not in_safe_zone:
          attention_reasons.append("outside_safe_zone")  # noqa: E111

    self._attention_reasons = attention_reasons

    return bool(attention_reasons)

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional attributes explaining why attention is needed."""
    attrs: AttributeDict = self._inherit_extra_attributes()

    if hasattr(self, "_attention_reasons"):
      attrs["attention_reasons"] = self._attention_reasons  # noqa: E111
      attrs["urgency_level"] = self._calculate_urgency_level()  # noqa: E111
      attrs["recommended_actions"] = self._get_recommended_actions()  # noqa: E111

    return _normalise_attributes(attrs)

  def _calculate_urgency_level(self) -> str:  # noqa: E111
    """Calculate the urgency level based on attention reasons."""
    if not hasattr(self, "_attention_reasons"):
      return "none"  # noqa: E111

    urgent_conditions = ["critically_hungry", "health_alert"]

    if any(reason in urgent_conditions for reason in self._attention_reasons):
      return "high"  # noqa: E111
    if len(self._attention_reasons) > 2:
      return "medium"  # noqa: E111
    if len(self._attention_reasons) > 0:
      return "low"  # noqa: E111
    return "none"

  def _get_recommended_actions(self) -> list[str]:  # noqa: E111
    """Get recommended actions based on attention reasons."""
    if not hasattr(self, "_attention_reasons"):
      return []  # noqa: E111

    actions = []

    if "critically_hungry" in self._attention_reasons:
      actions.append("Feed immediately")  # noqa: E111
    elif "hungry" in self._attention_reasons:
      actions.append("Consider feeding")  # noqa: E111

    if "urgent_walk_needed" in self._attention_reasons:
      actions.append("Take for walk immediately")  # noqa: E111

    if "health_alert" in self._attention_reasons:
      actions.append("Check health status")  # noqa: E111

    if "outside_safe_zone" in self._attention_reasons:
      actions.append("Check location and safety")  # noqa: E111

    return actions


class PawControlVisitorModeBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if visitor mode is active."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if visitor mode is active."""
    dog_data = self._get_dog_data_cached()
    if not dog_data:
      return False  # noqa: E111

    return bool(dog_data.get(VISITOR_MODE_ACTIVE_FIELD, False))

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional attributes for visitor mode."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    dog_data = self._get_dog_data_cached()

    if dog_data:
      visitor_settings = cast(  # noqa: E111
        JSONMapping,
        dog_data.get("visitor_mode_settings", {}),
      )
      visitor_mode_started = dog_data.get("visitor_mode_started")  # noqa: E111
      visitor_name = cast(str | None, dog_data.get("visitor_name"))  # noqa: E111
      if isinstance(visitor_mode_started, datetime):  # noqa: E111
        attrs["visitor_mode_started"] = _as_local(
          visitor_mode_started,
        ).isoformat()
      elif isinstance(visitor_mode_started, str) or visitor_mode_started is None:  # noqa: E111
        attrs["visitor_mode_started"] = visitor_mode_started
      attrs["visitor_name"] = visitor_name  # noqa: E111
      attrs["modified_notifications"] = bool(  # noqa: E111
        visitor_settings.get("modified_notifications", True),
      )
      attrs["reduced_alerts"] = bool(  # noqa: E111
        visitor_settings.get("reduced_alerts", True),
      )

    return _normalise_attributes(attrs)


# Feeding binary sensors
class PawControlIsHungryBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if the dog is hungry."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if the dog is hungry."""
    feeding_data = self._get_feeding_payload()
    if not feeding_data:
      return False  # noqa: E111

    return bool(feeding_data.get("is_hungry", False))

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional feeding status attributes."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    feeding_data = self._get_feeding_payload()

    if not feeding_data:
      return _normalise_attributes(attrs)  # noqa: E111

    last_feeding = feeding_data.get("last_feeding")
    if isinstance(last_feeding, datetime):
      attrs["last_feeding"] = _as_local(last_feeding).isoformat()  # noqa: E111
    elif isinstance(last_feeding, str) or last_feeding is None:
      attrs["last_feeding"] = last_feeding  # noqa: E111

    last_feeding_hours = feeding_data.get("last_feeding_hours")
    if isinstance(last_feeding_hours, int | float):
      attrs["last_feeding_hours"] = float(last_feeding_hours)  # noqa: E111
    elif last_feeding_hours is None:
      attrs["last_feeding_hours"] = None  # noqa: E111

    next_feeding_due = feeding_data.get("next_feeding_due")
    if isinstance(next_feeding_due, datetime):
      attrs["next_feeding_due"] = _as_local(next_feeding_due).isoformat()  # noqa: E111
    elif isinstance(next_feeding_due, str) or next_feeding_due is None:
      attrs["next_feeding_due"] = next_feeding_due  # noqa: E111

    attrs["hunger_level"] = self._calculate_hunger_level(feeding_data)

    return _normalise_attributes(attrs)

  def _calculate_hunger_level(self, feeding_data: FeedingModulePayload) -> str:  # noqa: E111
    """Calculate hunger level based on time since last feeding."""
    last_feeding_hours = feeding_data.get("last_feeding_hours")

    if not isinstance(last_feeding_hours, int | float):
      return STATE_UNKNOWN  # noqa: E111

    hours_since_feeding = float(last_feeding_hours)

    if hours_since_feeding > 12:
      return "very_hungry"  # noqa: E111
    if hours_since_feeding >= 8:
      return "hungry"  # noqa: E111
    if hours_since_feeding >= 6:
      return "somewhat_hungry"  # noqa: E111
    return "satisfied"


class PawControlFeedingDueBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if a feeding is due based on schedule."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if a feeding is due according to schedule."""
    feeding_data = self._get_feeding_payload()
    if not feeding_data:
      return False  # noqa: E111

    next_feeding_due = feeding_data.get("next_feeding_due")
    if not isinstance(next_feeding_due, str):
      return False  # noqa: E111

    due_time = ensure_utc_datetime(next_feeding_due)
    if due_time is None:
      return False  # noqa: E111

    return dt_util.utcnow() >= due_time


class PawControlFeedingScheduleOnTrackBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if feeding schedule is being followed."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if feeding schedule adherence is good."""
    feeding_data = self._get_feeding_payload()
    if not feeding_data:
      return True  # Assume on track if no data  # noqa: E111

    adherence = feeding_data.get("feeding_schedule_adherence", 100.0)
    if not isinstance(adherence, int | float):
      return True  # noqa: E111
    return self._evaluate_threshold(float(adherence), 80.0, "greater_equal", True)


class PawControlDailyFeedingGoalMetBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if daily feeding goals are met."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if daily feeding goals are met."""
    feeding_data = self._get_feeding_payload()
    if not feeding_data:
      return False  # noqa: E111

    return bool(feeding_data.get("daily_target_met", False))


# Walk binary sensors
class PawControlWalkInProgressBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if a walk is currently in progress."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the walk in progress binary sensor."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "walk_in_progress",
      device_class=_RUNNING_DEVICE_CLASS,
      icon_on="mdi:walk",
      icon_off="mdi:home",
    )

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if a walk is currently in progress."""
    status_snapshot = self._get_status_snapshot()
    if status_snapshot is not None:
      return bool(status_snapshot.get("on_walk", False))  # noqa: E111

    walk_data = self._get_walk_payload()
    if not walk_data:
      return False  # noqa: E111

    return bool(walk_data.get(WALK_IN_PROGRESS_FIELD, False))

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional walk progress attributes."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    walk_data = self._get_walk_payload()

    if walk_data and walk_data.get(WALK_IN_PROGRESS_FIELD):
      current_walk = walk_data.get("current_walk")  # noqa: E111
      started_at: object | None = None  # noqa: E111
      duration_minutes = walk_data.get("current_walk_duration")  # noqa: E111
      distance_meters = walk_data.get("current_walk_distance")  # noqa: E111

      if isinstance(current_walk, Mapping):  # noqa: E111
        started_at = current_walk.get("start_time")
        duration_minutes = current_walk.get(
          "current_duration",
          current_walk.get("duration"),
        )
        distance_meters = current_walk.get(
          "current_distance",
          current_walk.get("distance"),
        )

      started_at = started_at or walk_data.get("current_walk_start")  # noqa: E111

      gps_data = self._get_gps_payload()  # noqa: E111
      last_seen = None  # noqa: E111
      if gps_data is not None:  # noqa: E111
        last_seen = gps_data.get("last_seen")

      _apply_standard_timing_attributes(  # noqa: E111
        attrs,
        started_at=started_at,
        duration_minutes=duration_minutes,
        last_seen=last_seen,
      )

      if isinstance(distance_meters, int | float):  # noqa: E111
        attrs["distance_meters"] = float(distance_meters)

      estimated_remaining = self._estimate_remaining_time(walk_data)  # noqa: E111
      if estimated_remaining is not None:  # noqa: E111
        attrs["estimated_remaining"] = estimated_remaining

    return _normalise_attributes(attrs)

  def _estimate_remaining_time(self, walk_data: WalkModulePayload) -> int | None:  # noqa: E111
    """Estimate remaining walk time based on typical patterns."""
    current_duration_value = walk_data.get("current_walk_duration")
    average_duration_value = walk_data.get("average_walk_duration")

    if (
      isinstance(current_duration_value, int | float)
      and isinstance(average_duration_value, int | float)
      and current_duration_value < average_duration_value
    ):
      return int(average_duration_value - current_duration_value)  # noqa: E111

    return None


class PawControlNeedsWalkBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if the dog needs a walk."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if the dog needs a walk."""
    status_snapshot = self._get_status_snapshot()
    if status_snapshot is not None:
      return bool(status_snapshot.get("needs_walk", False))  # noqa: E111

    walk_data = self._get_walk_payload()
    if not walk_data:
      return False  # noqa: E111

    return bool(walk_data.get("needs_walk", False))

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional walk need attributes."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    walk_data = self._get_walk_payload()

    if walk_data:
      last_walk = walk_data.get("last_walk")  # noqa: E111
      if isinstance(last_walk, datetime):  # noqa: E111
        attrs["last_walk"] = _as_local(last_walk).isoformat()
      elif isinstance(last_walk, str):  # noqa: E111
        attrs["last_walk"] = last_walk

      last_walk_hours = walk_data.get("last_walk_hours")  # noqa: E111
      if isinstance(last_walk_hours, int | float):  # noqa: E111
        attrs["last_walk_hours"] = float(last_walk_hours)

      walks_today = walk_data.get("walks_today")  # noqa: E111
      if isinstance(walks_today, int):  # noqa: E111
        attrs["walks_today"] = walks_today

      attrs["urgency_level"] = self._calculate_walk_urgency(walk_data)  # noqa: E111

    return _normalise_attributes(attrs)

  def _calculate_walk_urgency(self, walk_data: WalkModulePayload) -> str:  # noqa: E111
    """Calculate walk urgency level."""
    last_walk_hours = walk_data.get("last_walk_hours")

    if not isinstance(last_walk_hours, int | float):
      return STATE_UNKNOWN  # noqa: E111

    if last_walk_hours > 12:
      return "urgent"  # noqa: E111
    if last_walk_hours > 8:
      return "high"  # noqa: E111
    if last_walk_hours > 6:
      return "medium"  # noqa: E111
    return "low"


class PawControlWalkGoalMetBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if daily walk goals are met."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if daily walk goals are met."""
    walk_data = self._get_walk_payload()
    if not walk_data:
      return False  # noqa: E111

    return bool(walk_data.get("walk_goal_met", False))


class PawControlLongWalkOverdueBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if a longer walk is overdue."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if a longer walk is overdue."""
    walk_data = self._get_walk_payload()
    if not walk_data:
      return False  # noqa: E111

    # Check if last long walk (>30 min) was more than 2 days ago
    last_long_walk = walk_data.get("last_long_walk")
    if isinstance(last_long_walk, str | datetime):
      return not self._calculate_time_based_status(  # noqa: E111
        last_long_walk,
        48,
        False,
      )  # 2 days

    return True  # No long walk recorded or invalid payload


# GPS binary sensors
class PawControlIsHomeBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if the dog is at home."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if the dog is at home."""
    gps_data = self._get_gps_payload()
    if not gps_data:
      return True  # Assume home if no GPS data  # noqa: E111

    current_zone = gps_data.get("zone")
    return isinstance(current_zone, str) and current_zone == "home"

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return additional location attributes."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    gps_data = self._get_gps_payload()

    if gps_data:
      current_zone = gps_data.get("zone")  # noqa: E111
      attrs["current_zone"] = (  # noqa: E111
        current_zone
        if isinstance(
          current_zone,
          str,
        )
        else STATE_UNKNOWN
      )

      distance_from_home = gps_data.get("distance_from_home")  # noqa: E111
      if isinstance(distance_from_home, int | float):  # noqa: E111
        attrs["distance_from_home"] = float(distance_from_home)

      last_seen_value = gps_data.get("last_seen")  # noqa: E111
      if isinstance(last_seen_value, datetime):  # noqa: E111
        attrs["last_seen"] = last_seen_value.isoformat()
      elif isinstance(last_seen_value, str):  # noqa: E111
        attrs["last_seen"] = last_seen_value

      accuracy = gps_data.get("accuracy")  # noqa: E111
      if isinstance(accuracy, int | float):  # noqa: E111
        attrs["accuracy"] = float(accuracy)

    return _normalise_attributes(attrs)


class PawControlInSafeZoneBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if the dog is in a safe zone."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if the dog is in a safe zone."""
    status_snapshot = self._get_status_snapshot()
    if status_snapshot is not None:
      return bool(status_snapshot.get("in_safe_zone", True))  # noqa: E111

    gps_data = self._get_gps_payload()
    if not gps_data:
      return True  # Assume safe if no GPS data  # noqa: E111

    # Check if in home zone or other defined safe zones
    current_zone = gps_data.get("zone")
    safe_zones: set[SafeZoneName] = {
      "home",
      "park",
      "vet",
      "friend_house",
    }  # Configurable

    return isinstance(current_zone, str) and current_zone in safe_zones

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return standardized timing attributes for safe zone status."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    gps_data = self._get_gps_payload()
    last_seen = None
    if gps_data is not None:
      last_seen = gps_data.get("last_seen")  # noqa: E111

    _apply_standard_timing_attributes(
      attrs,
      started_at=None,
      duration_minutes=None,
      last_seen=last_seen,
    )
    return _normalise_attributes(attrs)


class PawControlGPSAccuratelyTrackedBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if GPS tracking is accurate."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if GPS tracking is accurate."""
    gps_data = self._get_gps_payload()
    if not gps_data:
      return False  # noqa: E111

    accuracy = gps_data.get("accuracy")
    accuracy_value: float | None
    accuracy_value = (
      float(accuracy)
      if isinstance(
        accuracy,
        int | float,
      )
      else None
    )

    last_seen_input = gps_data.get("last_seen")
    last_seen: datetime | str | None
    last_seen = last_seen_input if isinstance(last_seen_input, datetime | str) else None

    # Check accuracy threshold and data freshness
    accuracy_good = self._evaluate_threshold(
      accuracy_value,
      50,
      "less_equal",
      False,
    )
    data_fresh = self._calculate_time_based_status(
      last_seen,
      5.0 / 60,
      False,
    )  # 5 minutes

    return accuracy_good and data_fresh


class PawControlMovingBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if the dog is currently moving."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if the dog is currently moving."""
    gps_data = self._get_gps_payload()
    if not gps_data:
      return False  # noqa: E111

    speed = gps_data.get("speed")
    numeric_speed = float(speed) if isinstance(speed, int | float) else 0.0
    return self._evaluate_threshold(
      numeric_speed,
      1.0,
      "greater",
      False,
    )  # 1 km/h threshold


class PawControlGeofenceAlertBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if there's a geofence alert."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if there's an active geofence alert."""
    gps_data = self._get_gps_payload()
    if not gps_data:
      return False  # noqa: E111

    flag = _coerce_bool_flag(gps_data.get("geofence_alert"))
    if flag is not None:
      return flag  # noqa: E111

    return False


class PawControlGPSBatteryLowBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if GPS device battery is low."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if GPS device battery is low."""
    gps_data = self._get_gps_payload()
    if not gps_data:
      return False  # noqa: E111

    battery_level = gps_data.get("battery_level")
    if not isinstance(battery_level, int | float):
      return False  # noqa: E111
    return self._evaluate_threshold(
      float(battery_level),
      20,
      "less_equal",
      False,
    )  # 20% threshold


# Health binary sensors
class PawControlHealthAlertBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if there's a health alert."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if there are active health alerts."""
    health_data = self._get_health_payload()
    if not health_data:
      return False  # noqa: E111

    health_alerts = health_data.get("health_alerts", [])
    if isinstance(health_alerts, Sequence):
      return len(health_alerts) > 0  # noqa: E111

    return False

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return health alert details."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    health_data = self._get_health_payload()

    if not health_data:
      return _normalise_attributes(attrs)  # noqa: E111

    health_alerts = health_data.get("health_alerts")
    if isinstance(health_alerts, list):
      attrs["health_alerts"] = cast(JSONValue, health_alerts)  # noqa: E111
      attrs["alert_count"] = len(health_alerts)  # noqa: E111

    health_status = health_data.get("health_status")
    if isinstance(health_status, str) or health_status is None:
      attrs["health_status"] = health_status or "good"  # noqa: E111

    if "alert_count" not in attrs:
      attrs["alert_count"] = 0  # noqa: E111

    return _normalise_attributes(attrs)


class PawControlWeightAlertBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if there's a weight-related alert."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if there's a weight alert."""
    health_data = self._get_health_payload()
    if not health_data:
      return False  # noqa: E111

    weight_change_percent = health_data.get("weight_change_percent", 0)
    if not isinstance(weight_change_percent, int | float):
      return False  # noqa: E111
    return abs(weight_change_percent) > 10  # 10% weight change threshold


class PawControlMedicationDueBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if medication is due."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if medication is due."""
    health_data = self._get_health_payload()
    if not health_data:
      return False  # noqa: E111

    medications_due = health_data.get("medications_due", [])
    if isinstance(medications_due, Sequence):
      return len(medications_due) > 0  # noqa: E111

    return False


class PawControlVetCheckupDueBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if vet checkup is due."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if vet checkup is due."""
    health_data = self._get_health_payload()
    if not health_data:
      return False  # noqa: E111

    next_checkup = health_data.get("next_checkup_due")
    if not isinstance(next_checkup, str):
      return False  # noqa: E111

    checkup_dt = ensure_utc_datetime(next_checkup)
    if checkup_dt is None:
      return False  # noqa: E111

    return dt_util.utcnow().date() >= _as_local(checkup_dt).date()


class PawControlGroomingDueBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if grooming is due."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if grooming is due."""
    health_data = self._get_health_payload()
    if not health_data:
      return False  # noqa: E111

    return bool(health_data.get("grooming_due", False))


class PawControlActivityLevelConcernBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if there's concern about activity level."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    """Return True if there's concern about activity level."""
    health_data = self._get_health_payload()
    if not health_data:
      return False  # noqa: E111

    activity_level = health_data.get("activity_level", "normal")
    concerning_levels = ["very_low", "very_high"]

    return activity_level in concerning_levels

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return activity level concern details."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    health_data = self._get_health_payload()

    if health_data:
      activity_level_value = health_data.get("activity_level")  # noqa: E111
      activity_level = (  # noqa: E111
        activity_level_value if isinstance(activity_level_value, str) else "normal"
      )
      attrs["current_activity_level"] = activity_level  # noqa: E111
      attrs["concern_reason"] = self._get_concern_reason(activity_level)  # noqa: E111
      attrs["recommended_action"] = self._get_recommended_action(  # noqa: E111
        activity_level,
      )

    return _normalise_attributes(attrs)

  def _get_concern_reason(self, activity_level: str) -> str:  # noqa: E111
    """Get reason for activity level concern."""
    if activity_level == "very_low":
      return "Activity level is unusually low"  # noqa: E111
    if activity_level == "very_high":
      return "Activity level is unusually high"  # noqa: E111
    return "No concern"

  def _get_recommended_action(self, activity_level: str) -> str:  # noqa: E111
    """Get recommended action for activity level concern."""
    if activity_level == "very_low":
      return "Consider vet consultation or encouraging more activity"  # noqa: E111
    if activity_level == "very_high":
      return "Monitor for signs of distress or illness"  # noqa: E111
    return "Continue normal monitoring"


class PawControlHealthAwareFeedingBinarySensor(PawControlBinarySensorBase):
  """Binary sensor showing if health-aware feeding mode is active."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    feeding_data = self._get_feeding_payload()
    if not feeding_data:
      return False  # noqa: E111
    return bool(feeding_data.get("health_aware_feeding", False))

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Return health-aware feeding metadata for the caregiver UI."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    feeding_data = self._get_feeding_payload()

    if feeding_data is None:
      attrs["health_conditions"] = []  # noqa: E111
      return _normalise_attributes(attrs)  # noqa: E111

    portion_adjustment_factor = feeding_data.get(
      "portion_adjustment_factor",
    )
    if isinstance(portion_adjustment_factor, int | float):
      attrs["portion_adjustment_factor"] = float(  # noqa: E111
        portion_adjustment_factor,
      )
    elif portion_adjustment_factor is None:
      attrs["portion_adjustment_factor"] = None  # noqa: E111

    raw_conditions = feeding_data.get("health_conditions")
    if isinstance(raw_conditions, list):
      attrs["health_conditions"] = [str(condition) for condition in raw_conditions]  # noqa: E111
    else:
      attrs["health_conditions"] = []  # noqa: E111
    return _normalise_attributes(attrs)


class PawControlMedicationWithMealsBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating if medication should be given with meals."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    feeding_data = self._get_feeding_payload()
    if not feeding_data:
      return False  # noqa: E111
    return bool(feeding_data.get("medication_with_meals", False))

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Report which health conditions require medication with meals."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    feeding_data = self._get_feeding_payload()
    if feeding_data:
      raw_conditions = feeding_data.get("health_conditions")  # noqa: E111
      if isinstance(raw_conditions, list):  # noqa: E111
        attrs["health_conditions"] = [str(condition) for condition in raw_conditions]
        return _normalise_attributes(attrs)

    attrs["health_conditions"] = []
    return _normalise_attributes(attrs)


class PawControlHealthEmergencyBinarySensor(PawControlBinarySensorBase):
  """Binary sensor indicating an active health emergency."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    feeding_data = self._get_feeding_payload()
    if not feeding_data:
      return False  # noqa: E111

    flag = _coerce_bool_flag(feeding_data.get("health_emergency"))
    if flag is not None:
      return flag  # noqa: E111

    return False

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Expose emergency context such as type, timing, and status."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    feeding_data = self._get_feeding_payload()
    emergency_payload = (
      feeding_data.get(
        "emergency_mode",
      )
      if feeding_data is not None
      else None
    )

    if isinstance(emergency_payload, Mapping):
      emergency = emergency_payload  # noqa: E111

      emergency_type = emergency.get("emergency_type")  # noqa: E111
      if isinstance(emergency_type, str):  # noqa: E111
        attrs["emergency_type"] = emergency_type

      portion_adjustment = emergency.get("portion_adjustment")  # noqa: E111
      if isinstance(portion_adjustment, int | float):  # noqa: E111
        attrs["portion_adjustment"] = float(portion_adjustment)

      activated_at = emergency.get("activated_at")  # noqa: E111
      if isinstance(activated_at, datetime):  # noqa: E111
        attrs["activated_at"] = _as_local(activated_at).isoformat()
      elif isinstance(activated_at, str):  # noqa: E111
        attrs["activated_at"] = activated_at

      expires_at = emergency.get("expires_at")  # noqa: E111
      if isinstance(expires_at, datetime):  # noqa: E111
        attrs["expires_at"] = _as_local(expires_at).isoformat()
      elif isinstance(expires_at, str) or expires_at is None:  # noqa: E111
        attrs["expires_at"] = expires_at

      status = emergency.get("status")  # noqa: E111
      if isinstance(status, str):  # noqa: E111
        attrs["status"] = status
    return _normalise_attributes(attrs)


class PawControlGardenSessionActiveBinarySensor(PawControlGardenBinarySensorBase):
  """Binary sensor indicating an active garden session."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    data = self._get_garden_data()
    status = data.get("status")
    if isinstance(status, str) and status == "active":
      return True  # noqa: E111

    garden_manager = self._get_garden_manager()
    if garden_manager is not None:
      return garden_manager.is_dog_in_garden(self._dog_id)  # noqa: E111

    return False


class PawControlInGardenBinarySensor(PawControlGardenBinarySensorBase):
  """Binary sensor indicating whether the dog is currently in the garden."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    garden_manager = self._get_garden_manager()
    if garden_manager is not None:
      return garden_manager.is_dog_in_garden(self._dog_id)  # noqa: E111

    data = self._get_garden_data()
    status = data.get("status")
    return isinstance(status, str) and status == "active"


class PawControlGardenPoopPendingBinarySensor(PawControlGardenBinarySensorBase):
  """Binary sensor indicating pending garden poop confirmation."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
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

  def _get_is_on_state(self) -> bool:  # noqa: E111
    garden_manager = self._get_garden_manager()
    if garden_manager is not None:
      return garden_manager.has_pending_confirmation(self._dog_id)  # noqa: E111

    data = self._get_garden_data()
    pending = data.get("pending_confirmations")
    return isinstance(pending, Sequence) and len(pending) > 0

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Expose how many confirmation prompts are outstanding."""
    attrs: AttributeDict = self._inherit_extra_attributes()
    self._apply_garden_common_attributes(attrs)
    pending = self._get_garden_data().get("pending_confirmations")
    if isinstance(pending, list):
      attrs["pending_confirmations"] = cast(JSONValue, pending)  # noqa: E111
      attrs["pending_confirmation_count"] = len(pending)  # noqa: E111
    else:
      attrs["pending_confirmation_count"] = 0  # noqa: E111
    return _normalise_attributes(attrs)
