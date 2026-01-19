from __future__ import annotations

import json
from datetime import UTC, datetime, time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
  CONF_API_ENDPOINT,
  CONF_API_TOKEN,
  CONF_DASHBOARD_MODE,
  CONF_DOG_AGE,
  CONF_DOG_BREED,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
  CONF_DOGS,
  CONF_DOOR_SENSOR,
  CONF_DOOR_SENSOR_SETTINGS,
  CONF_EXTERNAL_INTEGRATIONS,
  CONF_GPS_ACCURACY_FILTER,
  CONF_GPS_DISTANCE_FILTER,
  CONF_GPS_UPDATE_INTERVAL,
  CONF_MODULES,
  CONF_NOTIFICATIONS,
  CONF_QUIET_END,
  CONF_QUIET_HOURS,
  CONF_QUIET_START,
  CONF_REMINDER_REPEAT_MIN,
  CONF_RESET_TIME,
  CONF_WEATHER_ENTITY,
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_GROOMING,
  MODULE_HEALTH,
  MODULE_WALK,
)
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow
from custom_components.pawcontrol.runtime_data import RuntimeDataUnavailableError
from custom_components.pawcontrol.types import (
  DOG_ID_FIELD,
  DOG_MODULES_FIELD,
  DOG_NAME_FIELD,
  DOG_WEIGHT_FIELD,
  NOTIFICATION_MOBILE_FIELD,
  NOTIFICATION_PRIORITY_FIELD,
  NOTIFICATION_QUIET_END_FIELD,
  NOTIFICATION_QUIET_HOURS_FIELD,
  NOTIFICATION_QUIET_START_FIELD,
  NOTIFICATION_REMINDER_REPEAT_FIELD,
  AdvancedOptions,
  ConfigEntryDataPayload,
  DashboardOptions,
  DogConfigData,
  DogOptionsMap,
  FeedingOptions,
  GeofenceOptions,
  GPSOptions,
  HealthOptions,
  NotificationOptions,
  OptionsExportPayload,
  PawControlOptionsData,
  RuntimeErrorHistoryEntry,
  SystemOptions,
  WeatherOptions,
  ensure_notification_options,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


def _assert_notification_values(
  notifications: NotificationOptions,
  *,
  quiet_hours: bool,
  quiet_start: str,
  quiet_end: str,
  reminder_repeat_min: int,
  priority_notifications: bool,
  mobile_notifications: bool,
) -> None:
  assert notifications[NOTIFICATION_QUIET_HOURS_FIELD] is quiet_hours
  assert notifications[NOTIFICATION_QUIET_START_FIELD] == quiet_start
  assert notifications[NOTIFICATION_QUIET_END_FIELD] == quiet_end
  assert notifications[NOTIFICATION_REMINDER_REPEAT_FIELD] == reminder_repeat_min
  assert notifications[NOTIFICATION_PRIORITY_FIELD] is priority_notifications
  assert notifications[NOTIFICATION_MOBILE_FIELD] is mobile_notifications


def _assert_notifications(
  options: PawControlOptionsData,
  *,
  quiet_hours: bool,
  quiet_start: str,
  quiet_end: str,
  reminder_repeat_min: int,
  priority_notifications: bool,
  mobile_notifications: bool,
) -> None:
  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])
  _assert_notification_values(
    notifications,
    quiet_hours=quiet_hours,
    quiet_start=quiet_start,
    quiet_end=quiet_end,
    reminder_repeat_min=reminder_repeat_min,
    priority_notifications=priority_notifications,
    mobile_notifications=mobile_notifications,
  )


def _assert_dog_modules(
  dog_options: DogOptionsMap,
  dog_id: str,
  expected_modules: dict[str, bool],
) -> None:
  entry = dog_options[dog_id]
  assert entry[DOG_ID_FIELD] == dog_id
  modules = entry[DOG_MODULES_FIELD]
  for module_key, expected_value in expected_modules.items():
    assert modules[module_key] is expected_value


def test_ensure_notification_options_normalises_values() -> None:
  """Notification options should coerce overrides and preserve defaults."""

  defaults = {
    CONF_QUIET_HOURS: True,
    CONF_QUIET_START: "21:00",
    CONF_QUIET_END: "06:30",
    CONF_REMINDER_REPEAT_MIN: 30,
    "priority_notifications": False,
    "mobile_notifications": True,
  }
  payload = {
    CONF_QUIET_HOURS: "no",
    CONF_QUIET_START: " 20:45 ",
    CONF_QUIET_END: "   ",
    CONF_REMINDER_REPEAT_MIN: "45",
    "priority_notifications": "yes",
    "mobile_notifications": 0,
  }

  options = ensure_notification_options(payload, defaults=defaults)

  assert options[NOTIFICATION_QUIET_HOURS_FIELD] is False
  assert options[NOTIFICATION_QUIET_START_FIELD] == "20:45"
  assert options[NOTIFICATION_QUIET_END_FIELD] == "06:30"
  assert options[NOTIFICATION_REMINDER_REPEAT_FIELD] == 45
  assert options[NOTIFICATION_PRIORITY_FIELD] is True
  assert options[NOTIFICATION_MOBILE_FIELD] is False


def test_ensure_notification_options_ignores_invalid_entries() -> None:
  """Invalid overrides should be dropped from the normalised payload."""

  payload = {
    CONF_QUIET_HOURS: "maybe",
    CONF_QUIET_START: None,
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "fast",
    "priority_notifications": None,
    "mobile_notifications": " ",
  }

  options = ensure_notification_options(payload)

  assert NOTIFICATION_QUIET_HOURS_FIELD not in options
  assert NOTIFICATION_QUIET_START_FIELD not in options
  assert NOTIFICATION_QUIET_END_FIELD not in options
  assert NOTIFICATION_REMINDER_REPEAT_FIELD not in options
  assert NOTIFICATION_PRIORITY_FIELD not in options
  assert NOTIFICATION_MOBILE_FIELD not in options


@pytest.mark.asyncio
async def test_geofence_settings_coercion(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Geofence options should be normalised into typed payloads."""

  hass.config.latitude = 12.34
  hass.config.longitude = 56.78

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_geofence_settings(
    {
      "geofencing_enabled": True,
      "geofence_radius_m": "120",
      "geofence_lat": "41.8899",
      "geofence_lon": 12.4923,
      "geofence_alerts_enabled": False,
      "safe_zone_alerts": False,
      "restricted_zone_alerts": True,
      "zone_entry_notifications": True,
      "zone_exit_notifications": False,
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  geofence = cast(GeofenceOptions, options["geofence_settings"])

  assert geofence["geofence_radius_m"] == 120
  assert geofence["geofence_lat"] == pytest.approx(41.8899)
  assert geofence["geofence_lon"] == pytest.approx(12.4923)
  assert geofence["geofence_alerts_enabled"] is False
  assert geofence["safe_zone_alerts"] is False
  assert geofence["restricted_zone_alerts"] is True
  assert geofence["zone_entry_notifications"] is True
  assert geofence["zone_exit_notifications"] is False


@pytest.mark.asyncio
async def test_geofence_settings_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Geofence updates should reapply typed notifications and dog payloads."""

  _set_raw_options(
    mock_config_entry,
    notifications={
      CONF_QUIET_HOURS: "False",
      CONF_QUIET_START: " 19:00:00 ",
      CONF_QUIET_END: "",
      CONF_REMINDER_REPEAT_MIN: "3",
      "priority_notifications": "no",
      "mobile_notifications": "1",
    },
    dog_options={
      "buddy": {
        DOG_ID_FIELD: "buddy",
        DOG_MODULES_FIELD: {
          MODULE_FEEDING: "no",
          MODULE_HEALTH: "1",
        },
      },
      123: {
        DOG_MODULES_FIELD: {
          MODULE_GPS: "true",
          MODULE_WALK: "",
        }
      },
    },
  )

  hass.config.latitude = 12.34
  hass.config.longitude = 56.78

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_geofence_settings(
    {
      "geofencing_enabled": True,
      "geofence_radius_m": "95",
      "geofence_lat": "41.8899",
      "geofence_lon": 12.4923,
      "geofence_alerts_enabled": True,
      "safe_zone_alerts": False,
      "restricted_zone_alerts": True,
      "zone_entry_notifications": False,
      "zone_exit_notifications": True,
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  _assert_notifications(
    options,
    quiet_hours=False,
    quiet_start="19:00:00",
    quiet_end="07:00:00",
    reminder_repeat_min=5,
    priority_notifications=False,
    mobile_notifications=True,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"buddy", "123"}

  _assert_dog_modules(
    dog_options,
    "buddy",
    {
      MODULE_FEEDING: False,
      MODULE_HEALTH: True,
    },
  )
  _assert_dog_modules(
    dog_options,
    "123",
    {
      MODULE_GPS: True,
      MODULE_WALK: False,
    },
  )


@pytest.mark.asyncio
async def test_notification_settings_structured(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Notification settings should store typed quiet-hour metadata."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_notifications(
    {
      "quiet_hours": False,
      "quiet_start": "21:30:00",
      "quiet_end": "06:45:00",
      "reminder_repeat_min": "45",
      "priority_notifications": True,
      "mobile_notifications": False,
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  _assert_notifications(
    options,
    quiet_hours=False,
    quiet_start="21:30:00",
    quiet_end="06:45:00",
    reminder_repeat_min=45,
    priority_notifications=True,
    mobile_notifications=False,
  )


def test_notification_settings_normalise_existing_payload(
  mock_config_entry: ConfigEntry,
) -> None:
  """Stored notification mappings should be coerced back onto the typed surface."""

  stored_options = dict(mock_config_entry.options)
  stored_options[CONF_NOTIFICATIONS] = {
    CONF_QUIET_HOURS: "no",
    CONF_QUIET_START: " 20:00:00 ",
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "900",
    "priority_notifications": "false",
    "mobile_notifications": 0,
  }
  mock_config_entry.options = stored_options

  flow = PawControlOptionsFlow()
  flow.initialize_from_config_entry(mock_config_entry)

  notifications = flow._current_notification_options()

  _assert_notification_values(
    notifications,
    quiet_hours=False,
    quiet_start="20:00:00",
    quiet_end="07:00:00",
    reminder_repeat_min=180,
    priority_notifications=False,
    mobile_notifications=False,
  )


@pytest.mark.asyncio
async def test_performance_settings_normalisation(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Performance settings normalise mixed input types into typed options."""

  raw_options = dict(mock_config_entry.options)
  raw_options[CONF_NOTIFICATIONS] = {
    CONF_QUIET_HOURS: "yes",
    CONF_QUIET_START: " 19:45:00 ",
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "600",
    "priority_notifications": "OFF",
    "mobile_notifications": "true",
  }
  raw_options["dog_options"] = {
    "test_dog": {
      DOG_ID_FIELD: "test_dog",
      DOG_MODULES_FIELD: {
        MODULE_HEALTH: "on",
        MODULE_WALK: 0,
      },
    }
  }
  mock_config_entry.options = raw_options

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_performance_settings(
    {
      "entity_profile": "advanced",
      "performance_mode": "FAST",
      "batch_size": 25.0,
      "cache_ttl": "900",
      "selective_refresh": "0",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])

  assert options["entity_profile"] == "advanced"
  assert options["performance_mode"] == "balanced"
  assert options["batch_size"] == 25
  assert options["cache_ttl"] == 900
  assert options["selective_refresh"] is False

  _assert_notifications(
    options,
    quiet_hours=True,
    quiet_start="19:45:00",
    quiet_end="07:00:00",
    reminder_repeat_min=180,
    priority_notifications=False,
    mobile_notifications=True,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"test_dog"}

  _assert_dog_modules(
    dog_options,
    "test_dog",
    {
      MODULE_HEALTH: True,
      MODULE_WALK: False,
    },
  )


@pytest.mark.asyncio
async def test_entity_profile_placeholders_expose_reconfigure_telemetry(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Entity profile form should surface the latest reconfigure telemetry."""

  mock_config_entry.options.update(
    {
      "entity_profile": "standard",
      "last_reconfigure": "2024-01-02T03:04:05+00:00",
      "reconfigure_telemetry": {
        "timestamp": "2024-01-02T03:04:05+00:00",
        "requested_profile": "balanced",
        "previous_profile": "advanced",
        "dogs_count": 2,
        "estimated_entities": 12,
        "compatibility_warnings": ["GPS disabled for dog"],
        "health_summary": {
          "healthy": False,
          "issues": ["Missing GPS source"],
          "warnings": ["Reauth recommended"],
        },
        "merge_notes": [
          "Buddy: your dog options enabled gps.",
          "Max: your config entry options added a dog configuration.",
        ],
      },
    }
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_entity_profiles()

  placeholders = result["description_placeholders"]
  assert placeholders["reconfigure_requested_profile"] == "balanced"
  assert placeholders["reconfigure_previous_profile"] == "advanced"
  assert placeholders["reconfigure_dogs"] == "2"
  assert placeholders["reconfigure_entities"] == "12"
  assert "Missing GPS source" in placeholders["reconfigure_health"]
  assert "GPS disabled" in placeholders["reconfigure_warnings"]
  merge_notes = placeholders["reconfigure_merge_notes"].split("\n")
  assert "Buddy: your dog options enabled gps." in merge_notes


@pytest.mark.asyncio
async def test_entity_profiles_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Entity profile saves should reapply typed notifications and dog data."""

  _set_raw_options(
    mock_config_entry,
    notifications={
      CONF_QUIET_HOURS: 1,
      CONF_QUIET_START: None,
      CONF_QUIET_END: "  ",
      CONF_REMINDER_REPEAT_MIN: 500,
      "priority_notifications": "ON",
      "mobile_notifications": "off",
    },
    dog_options={
      "luna": {
        DOG_ID_FIELD: "luna",
        DOG_MODULES_FIELD: {
          MODULE_HEALTH: True,
          MODULE_FEEDING: "false",
        },
      }
    },
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_entity_profiles({"entity_profile": "advanced"})

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  _assert_notifications(
    options,
    quiet_hours=True,
    quiet_start="22:00:00",
    quiet_end="07:00:00",
    reminder_repeat_min=180,
    priority_notifications=True,
    mobile_notifications=False,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"luna"}

  _assert_dog_modules(
    dog_options,
    "luna",
    {
      MODULE_HEALTH: True,
      MODULE_FEEDING: False,
    },
  )

  assert options["entity_profile"] == "advanced"


@pytest.mark.asyncio
async def test_profile_preview_apply_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Applying a preview should rehydrate typed options snapshots."""

  _set_raw_options(
    mock_config_entry,
    notifications={
      CONF_QUIET_HOURS: "false",
      CONF_QUIET_START: " 20:15:00 ",
      CONF_QUIET_END: "",
      CONF_REMINDER_REPEAT_MIN: "2",
      "priority_notifications": "off",
      "mobile_notifications": "yes",
    },
    dog_options={
      "scout": {
        DOG_ID_FIELD: "scout",
        DOG_MODULES_FIELD: {
          MODULE_GPS: "on",
          MODULE_HEALTH: "0",
        },
      }
    },
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_profile_preview(
    {"profile": "gps_focus", "apply_profile": True}
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  assert options["entity_profile"] == "gps_focus"

  _assert_notifications(
    options,
    quiet_hours=False,
    quiet_start="20:15:00",
    quiet_end="07:00:00",
    reminder_repeat_min=5,
    priority_notifications=False,
    mobile_notifications=True,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"scout"}

  _assert_dog_modules(
    dog_options,
    "scout",
    {
      MODULE_GPS: True,
      MODULE_HEALTH: False,
    },
  )


@pytest.mark.asyncio
async def test_weather_settings_normalisation(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Weather options should clamp intervals and clean override payloads."""

  hass.states.async_set(
    "weather.home", "sunny", {"friendly_name": "Home", "temperature": 21}
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_weather_settings(
    {
      "weather_entity": "weather.home",
      "weather_health_monitoring": False,
      "weather_alerts": True,
      "weather_update_interval": "5",
      "temperature_alerts": "1",
      "uv_alerts": 0,
      "humidity_alerts": "yes",
      "wind_alerts": "on",
      "storm_alerts": "false",
      "breed_specific_recommendations": "",
      "health_condition_adjustments": True,
      "auto_activity_adjustments": "1",
      "notification_threshold": "EXTREME",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  weather = cast(WeatherOptions, options["weather_settings"])

  assert options[CONF_WEATHER_ENTITY] == "weather.home"
  assert weather[CONF_WEATHER_ENTITY] == "weather.home"
  assert weather["weather_update_interval"] == 15
  assert weather["weather_health_monitoring"] is False
  assert weather["weather_alerts"] is True
  assert weather["temperature_alerts"] is True
  assert weather["uv_alerts"] is False
  assert weather["humidity_alerts"] is True
  assert weather["wind_alerts"] is True
  assert weather["storm_alerts"] is False
  assert weather["breed_specific_recommendations"] is False
  assert weather["auto_activity_adjustments"] is True
  assert weather["notification_threshold"] == "moderate"


@pytest.mark.asyncio
async def test_feeding_settings_coercion(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Feeding options should normalise numeric ranges and booleans."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_feeding_settings(
    {
      "meals_per_day": "7",
      "feeding_reminders": "0",
      "portion_tracking": True,
      "calorie_tracking": "False",
      "auto_schedule": "yes",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  feeding = cast(FeedingOptions, options["feeding_settings"])

  assert feeding["default_meals_per_day"] == 6
  assert feeding["feeding_reminders"] is False
  assert feeding["portion_tracking"] is True
  assert feeding["calorie_tracking"] is False
  assert feeding["auto_schedule"] is True


@pytest.mark.asyncio
async def test_health_settings_coercion(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Health options should coerce truthy strings to booleans."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_health_settings(
    {
      "weight_tracking": "no",
      "medication_reminders": "on",
      "vet_reminders": "true",
      "grooming_reminders": "0",
      "health_alerts": "yes",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  health = cast(HealthOptions, options["health_settings"])

  assert health["weight_tracking"] is False
  assert health["medication_reminders"] is True
  assert health["vet_reminders"] is True
  assert health["grooming_reminders"] is False
  assert health["health_alerts"] is True


@pytest.mark.asyncio
async def test_feeding_settings_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Feeding menu updates should reapply typed notification and dog payloads."""

  _set_raw_options(
    mock_config_entry,
    notifications={
      CONF_QUIET_HOURS: "False",
      CONF_QUIET_START: " 19:00:00 ",
      CONF_QUIET_END: "",
      CONF_REMINDER_REPEAT_MIN: "3",
      "priority_notifications": "no",
      "mobile_notifications": "1",
    },
    dog_options={
      "buddy": {
        DOG_ID_FIELD: "buddy",
        DOG_MODULES_FIELD: {
          MODULE_FEEDING: "no",
          MODULE_HEALTH: "1",
        },
      },
      123: {
        DOG_MODULES_FIELD: {
          MODULE_GPS: "true",
          MODULE_WALK: "",
        }
      },
    },
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_feeding_settings(
    {
      "meals_per_day": "3",
      "feeding_reminders": "0",
      "portion_tracking": "True",
      "calorie_tracking": 0,
      "auto_schedule": "yes",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  _assert_notifications(
    options,
    quiet_hours=False,
    quiet_start="19:00:00",
    quiet_end="07:00:00",
    reminder_repeat_min=5,
    priority_notifications=False,
    mobile_notifications=True,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"buddy", "123"}

  _assert_dog_modules(
    dog_options,
    "buddy",
    {
      MODULE_FEEDING: False,
      MODULE_HEALTH: True,
    },
  )
  _assert_dog_modules(
    dog_options,
    "123",
    {
      MODULE_GPS: True,
      MODULE_WALK: False,
    },
  )


@pytest.mark.asyncio
async def test_health_settings_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Health menu updates should keep notifications and dogs on typed surfaces."""

  _set_raw_options(
    mock_config_entry,
    notifications={
      CONF_QUIET_HOURS: 1,
      CONF_QUIET_START: None,
      CONF_QUIET_END: "  ",
      CONF_REMINDER_REPEAT_MIN: 500,
      "priority_notifications": "ON",
      "mobile_notifications": "off",
    },
    dog_options={
      "luna": {
        DOG_ID_FIELD: "luna",
        DOG_MODULES_FIELD: {
          MODULE_HEALTH: True,
          MODULE_FEEDING: "false",
        },
      }
    },
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_health_settings(
    {
      "weight_tracking": "1",
      "medication_reminders": "false",
      "vet_reminders": "TRUE",
      "grooming_reminders": 0,
      "health_alerts": "YES",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  _assert_notifications(
    options,
    quiet_hours=True,
    quiet_start="22:00:00",
    quiet_end="07:00:00",
    reminder_repeat_min=180,
    priority_notifications=True,
    mobile_notifications=False,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"luna"}

  _assert_dog_modules(
    dog_options,
    "luna",
    {
      MODULE_HEALTH: True,
      MODULE_FEEDING: False,
    },
  )

  health = cast(HealthOptions, options["health_settings"])
  assert health["weight_tracking"] is True
  assert health["medication_reminders"] is False
  assert health["vet_reminders"] is True
  assert health["grooming_reminders"] is False
  assert health["health_alerts"] is True


@pytest.mark.asyncio
async def test_system_settings_normalisation(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """System options should clamp retention and normalise times."""

  raw_options = dict(mock_config_entry.options)
  raw_options[CONF_NOTIFICATIONS] = {
    CONF_QUIET_HOURS: "yes",
    CONF_QUIET_START: " 05:15:00 ",
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "999",
    "priority_notifications": "off",
    "mobile_notifications": 1,
  }
  raw_options["dog_options"] = {
    "buddy": {
      DOG_ID_FIELD: "buddy",
      DOG_MODULES_FIELD: {
        MODULE_WALK: "yes",
        MODULE_FEEDING: 0,
      },
    }
  }
  raw_options["system_settings"] = {
    "enable_analytics": False,
    "enable_cloud_backup": True,
  }
  raw_options["enable_analytics"] = False
  raw_options["enable_cloud_backup"] = True
  mock_config_entry.options = raw_options

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  script_manager = Mock()
  script_manager.async_sync_manual_resilience_events = AsyncMock()
  runtime = Mock()
  runtime.script_manager = script_manager

  with patch(
    "custom_components.pawcontrol.options_flow.get_runtime_data",
    return_value=runtime,
  ):
    result = await flow.async_step_system_settings(
      {
        "reset_time": time(4, 30),
        "data_retention_days": "10",
        "auto_backup": "true",
        "enable_analytics": "1",
        "enable_cloud_backup": 0,
        "performance_mode": "FULL",
        "resilience_skip_threshold": "7",
        "resilience_breaker_threshold": 2,
        "manual_check_event": "  pawcontrol_custom_check  ",
        "manual_guard_event": "  pawcontrol_manual_guard  ",
        "manual_breaker_event": "  ",
      }
    )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  system = cast(SystemOptions, options["system_settings"])

  assert options[CONF_RESET_TIME] == "04:30:00"
  assert system["data_retention_days"] == 30
  assert system["auto_backup"] is True
  assert system["performance_mode"] == "full"
  assert system["enable_analytics"] is True
  assert system["enable_cloud_backup"] is False
  assert system["resilience_skip_threshold"] == 7
  assert system["resilience_breaker_threshold"] == 2
  assert system["manual_check_event"] == "pawcontrol_custom_check"
  assert system["manual_guard_event"] == "pawcontrol_manual_guard"
  assert system["manual_breaker_event"] is None

  assert options["enable_analytics"] is True
  assert options["enable_cloud_backup"] is False
  assert options["manual_guard_event"] == "pawcontrol_manual_guard"
  assert "manual_breaker_event" not in options

  _assert_notifications(
    options,
    quiet_hours=True,
    quiet_start="05:15:00",
    quiet_end="07:00:00",
    reminder_repeat_min=180,
    priority_notifications=False,
    mobile_notifications=True,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"buddy"}

  _assert_dog_modules(
    dog_options,
    "buddy",
    {
      MODULE_WALK: True,
      MODULE_FEEDING: False,
    },
  )

  script_manager.async_sync_manual_resilience_events.assert_awaited_once_with(
    {
      "manual_check_event": "pawcontrol_custom_check",
      "manual_guard_event": "pawcontrol_manual_guard",
      "manual_breaker_event": None,
    }
  )


@pytest.mark.asyncio
async def test_system_settings_manual_event_placeholders(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Manual event placeholders should combine options and blueprint values."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  mock_config_entry.options = {
    "system_settings": {
      "manual_guard_event": "pawcontrol_manual_guard",
      "manual_breaker_event": None,
    }
  }
  flow.initialize_from_config_entry(mock_config_entry)

  script_manager = Mock()
  script_manager.get_resilience_escalation_snapshot.return_value = {
    "manual_events": {
      "configured_guard_events": ["pawcontrol_manual_guard"],
      "configured_breaker_events": ["pawcontrol_manual_breaker"],
      "configured_check_events": ["pawcontrol_resilience_check"],
      "preferred_events": {
        "manual_check_event": "pawcontrol_resilience_check",
        "manual_guard_event": "pawcontrol_manual_guard",
        "manual_breaker_event": "pawcontrol_manual_breaker",
      },
    }
  }
  runtime = Mock()
  runtime.script_manager = script_manager

  with patch(
    "custom_components.pawcontrol.options_flow.get_runtime_data",
    return_value=runtime,
  ):
    placeholders = flow._manual_event_description_placeholders()

  assert placeholders["manual_guard_event_options"] == "pawcontrol_manual_guard"
  assert placeholders["manual_breaker_event_options"] == "pawcontrol_manual_breaker"
  assert placeholders["manual_check_event_options"] == "pawcontrol_resilience_check"


@pytest.mark.asyncio
async def test_manual_event_choices_support_disable_and_translations(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Manual event dropdowns should expose disable and localized options."""

  hass.config.language = "de"

  flow = PawControlOptionsFlow()
  flow.hass = hass
  mock_config_entry.options = {
    "system_settings": {
      "manual_guard_event": "pawcontrol_manual_guard",
      "manual_breaker_event": "pawcontrol_manual_breaker",
    }
  }
  flow.initialize_from_config_entry(mock_config_entry)

  script_manager = Mock()
  script_manager.get_resilience_escalation_snapshot.return_value = {
    "manual_events": {
      "configured_guard_events": ["pawcontrol_manual_guard_blueprint"],
      "configured_breaker_events": ["pawcontrol_manual_breaker"],
      "configured_check_events": ["pawcontrol_resilience_check"],
      "listener_sources": {
        "pawcontrol_manual_guard": ["system_options"],
        "pawcontrol_manual_guard_blueprint": ["blueprint"],
        "pawcontrol_manual_breaker": ["blueprint"],
        "pawcontrol_resilience_check": ["blueprint"],
      },
      "preferred_events": {
        "manual_check_event": "pawcontrol_resilience_check",
      },
    }
  }
  runtime = Mock()
  runtime.script_manager = script_manager

  with patch(
    "custom_components.pawcontrol.options_flow.get_runtime_data",
    return_value=runtime,
  ):
    current_system = flow._current_system_options()
    guard_options = flow._manual_event_choices("manual_guard_event", current_system)
    check_options = flow._manual_event_choices("manual_check_event", current_system)

    disable_option = guard_options[0]
    assert disable_option["value"] == ""
    assert disable_option["label"] == "Deaktivieren"
    assert disable_option["description"] == "Integrationsstandard"
    assert disable_option["badge"] == "Deaktiviert"
    assert (
      disable_option["help_text"]
      == "Entfernt den Listener und beendet die Überwachung dieses manuellen Ereignisses."
    )
    assert disable_option["metadata_sources"] == ["disabled"]
    assert disable_option["metadata_primary_source"] == "disabled"

    guard_by_value = {
      option["value"]: option
      for option in guard_options
      if isinstance(option, dict) and option.get("value")
    }
    assert guard_by_value["pawcontrol_manual_guard"]["description"] == (
      "Integrationsstandard, Systemeinstellungen"
    )
    assert guard_by_value["pawcontrol_manual_guard"]["badge"] == "System"
    assert guard_by_value["pawcontrol_manual_guard"]["metadata_sources"] == [
      "default",
      "system_settings",
    ]
    assert (
      guard_by_value["pawcontrol_manual_guard"]["metadata_primary_source"]
      == "system_settings"
    )
    assert guard_by_value["pawcontrol_manual_guard"]["help_text"] == (
      "Integration verwendet diesen Wert, solange keine Überschreibungen aktiv sind. "
      'Über das Formular "Systemeinstellungen" gespeichert.'
    )
    assert (
      guard_by_value["pawcontrol_manual_guard_blueprint"]["description"]
      == "Blueprint-Vorschlag"
    )
    assert guard_by_value["pawcontrol_manual_guard_blueprint"]["badge"] == "Blueprint"
    assert guard_by_value["pawcontrol_manual_guard_blueprint"]["help_text"] == (
      "Vom Resilience-Blueprint vorgeschlagen."
    )
    assert guard_by_value["pawcontrol_manual_guard_blueprint"]["metadata_sources"] == [
      "blueprint"
    ]
    assert (
      guard_by_value["pawcontrol_manual_guard_blueprint"]["metadata_primary_source"]
      == "blueprint"
    )

    check_by_value = {
      option["value"]: option
      for option in check_options
      if isinstance(option, dict) and option.get("value")
    }
    assert (
      check_by_value["pawcontrol_resilience_check"]["description"]
      == "Blueprint-Vorschlag"
    )
    assert check_by_value["pawcontrol_resilience_check"]["badge"] == "Blueprint"
    assert check_by_value["pawcontrol_resilience_check"]["metadata_sources"] == [
      "blueprint",
      "default",
    ]
    assert (
      check_by_value["pawcontrol_resilience_check"]["metadata_primary_source"]
      == "blueprint"
    )
    assert check_by_value["pawcontrol_resilience_check"]["help_text"] == (
      "Vom Resilience-Blueprint vorgeschlagen. "
      "Integration verwendet diesen Wert, solange keine Überschreibungen aktiv sind."
    )

    hass.config.language = "en"
    english_options = flow._manual_event_choices("manual_guard_event", current_system)
    assert english_options[0]["label"] == "Disable"
    assert english_options[0]["description"] == "Integration default"
    assert english_options[0]["badge"] == "Disabled"
    assert (
      english_options[0]["help_text"]
      == "Removes the listener and stops monitoring this manual event."
    )


@pytest.mark.asyncio
async def test_dashboard_settings_normalisation(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Dashboard options should normalise modes and booleans."""

  raw_options = dict(mock_config_entry.options)
  raw_options[CONF_NOTIFICATIONS] = {
    CONF_QUIET_HOURS: 0,
    CONF_QUIET_START: "23:00:00",
    CONF_QUIET_END: None,
    CONF_REMINDER_REPEAT_MIN: 12.5,
    "priority_notifications": "on",
    "mobile_notifications": "false",
  }
  raw_options["dog_options"] = {
    "fido": {
      DOG_ID_FIELD: "fido",
      DOG_MODULES_FIELD: {
        MODULE_HEALTH: "true",
        MODULE_GPS: "no",
      },
    }
  }
  mock_config_entry.options = raw_options

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_dashboard_settings(
    {
      "dashboard_mode": "CARDS",
      "show_statistics": "0",
      "show_alerts": True,
      "compact_mode": "1",
      "show_maps": "off",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  dashboard = cast(DashboardOptions, options["dashboard_settings"])

  assert options[CONF_DASHBOARD_MODE] == "cards"
  assert dashboard["show_statistics"] is False
  assert dashboard["show_alerts"] is True
  assert dashboard["compact_mode"] is True
  assert dashboard["show_maps"] is False

  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])
  assert notifications[CONF_QUIET_HOURS] is False
  assert notifications[CONF_QUIET_START] == "23:00:00"
  assert notifications[CONF_QUIET_END] == "07:00:00"
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 12
  assert notifications["priority_notifications"] is True
  assert notifications["mobile_notifications"] is False

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"fido"}

  fido_entry = dog_options["fido"]
  assert fido_entry[DOG_ID_FIELD] == "fido"
  fido_modules = fido_entry[DOG_MODULES_FIELD]
  assert fido_modules[MODULE_HEALTH] is True
  assert fido_modules[MODULE_GPS] is False


@pytest.mark.asyncio
async def test_advanced_settings_structured(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Advanced options should normalise ranges and mirror root fields."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_advanced_settings(
    {
      "performance_mode": "ULTRA",
      "debug_logging": "true",
      "data_retention_days": "500",
      "auto_backup": "1",
      "experimental_features": "on",
      CONF_EXTERNAL_INTEGRATIONS: "yes",
      CONF_API_ENDPOINT: " https://demo.local ",
      CONF_API_TOKEN: "  secret  ",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  advanced = cast(AdvancedOptions, options["advanced_settings"])

  assert options["performance_mode"] == "balanced"
  assert options["debug_logging"] is True
  assert options["data_retention_days"] == 365
  assert options[CONF_EXTERNAL_INTEGRATIONS] is True
  assert options[CONF_API_ENDPOINT] == "https://demo.local"
  assert options[CONF_API_TOKEN] == "secret"

  assert advanced["performance_mode"] == "balanced"
  assert advanced["debug_logging"] is True
  assert advanced["data_retention_days"] == 365
  assert advanced["auto_backup"] is True
  assert advanced["experimental_features"] is True
  assert advanced[CONF_EXTERNAL_INTEGRATIONS] is True
  assert advanced[CONF_API_ENDPOINT] == "https://demo.local"
  assert advanced[CONF_API_TOKEN] == "secret"


@pytest.mark.asyncio
async def test_advanced_settings_normalises_existing_payloads(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Advanced settings should coerce legacy notification and dog payloads."""

  raw_options = dict(mock_config_entry.options)
  raw_options[CONF_NOTIFICATIONS] = {
    CONF_QUIET_HOURS: "false",
    CONF_QUIET_START: " 19:00:00 ",
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "300",
    "priority_notifications": "no",
    "mobile_notifications": "YES",
  }
  raw_options["dog_options"] = {
    "buddy": {
      DOG_ID_FIELD: "buddy",
      DOG_MODULES_FIELD: {
        MODULE_FEEDING: True,
        MODULE_WALK: "no",
      },
    },
    42: {
      DOG_MODULES_FIELD: {
        MODULE_HEALTH: 1,
      }
    },
  }
  raw_options["advanced_settings"] = {
    "performance_mode": "turbo",
    "debug_logging": "no",
    "data_retention_days": "1000",
    "auto_backup": "maybe",
    "experimental_features": "yes",
    CONF_EXTERNAL_INTEGRATIONS: "enabled",
    CONF_API_ENDPOINT: 123,
    CONF_API_TOKEN: None,
  }
  mock_config_entry.options = raw_options

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_advanced_settings(
    {
      "performance_mode": "balanced",
      "debug_logging": True,
      "data_retention_days": 200,
      "auto_backup": False,
      "experimental_features": True,
      CONF_EXTERNAL_INTEGRATIONS: False,
      CONF_API_ENDPOINT: " https://api.demo ",
      CONF_API_TOKEN: " token ",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])
  assert notifications[CONF_QUIET_HOURS] is False
  assert notifications[CONF_QUIET_START] == "19:00:00"
  assert notifications[CONF_QUIET_END] == "07:00:00"
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 180
  assert notifications["priority_notifications"] is False
  assert notifications["mobile_notifications"] is True

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"buddy", "42"}

  buddy_entry = dog_options["buddy"]
  assert buddy_entry[DOG_ID_FIELD] == "buddy"
  buddy_modules = buddy_entry[DOG_MODULES_FIELD]
  assert buddy_modules[MODULE_FEEDING] is True
  assert buddy_modules[MODULE_WALK] is False

  legacy_entry = dog_options["42"]
  assert legacy_entry[DOG_ID_FIELD] == "42"
  legacy_modules = legacy_entry[DOG_MODULES_FIELD]
  assert legacy_modules[MODULE_HEALTH] is True

  assert options[CONF_API_ENDPOINT] == "https://api.demo"
  assert options[CONF_API_TOKEN] == "token"

  advanced = cast(AdvancedOptions, options["advanced_settings"])
  assert advanced["performance_mode"] == "balanced"
  assert advanced["debug_logging"] is True
  assert advanced["data_retention_days"] == 200
  assert advanced["auto_backup"] is False
  assert advanced["experimental_features"] is True
  assert advanced[CONF_EXTERNAL_INTEGRATIONS] is False
  assert advanced[CONF_API_ENDPOINT] == "https://api.demo"
  assert advanced[CONF_API_TOKEN] == "token"


@pytest.mark.asyncio
async def test_gps_settings_structured(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """GPS settings should be stored as typed payloads with validation."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_gps_settings(
    {
      CONF_GPS_UPDATE_INTERVAL: "45",
      CONF_GPS_ACCURACY_FILTER: "12.5",
      CONF_GPS_DISTANCE_FILTER: 30,
      "gps_enabled": False,
      "route_recording": False,
      "route_history_days": "14",
      "auto_track_walks": True,
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  gps_options = cast(GPSOptions, options["gps_settings"])

  assert options[CONF_GPS_UPDATE_INTERVAL] == 45
  assert options[CONF_GPS_ACCURACY_FILTER] == 12.5
  assert options[CONF_GPS_DISTANCE_FILTER] == 30.0
  assert gps_options[CONF_GPS_UPDATE_INTERVAL] == 45
  assert gps_options[CONF_GPS_ACCURACY_FILTER] == 12.5
  assert gps_options[CONF_GPS_DISTANCE_FILTER] == 30.0
  assert gps_options["gps_enabled"] is False
  assert gps_options["route_recording"] is False
  assert gps_options["route_history_days"] == 14
  assert gps_options["auto_track_walks"] is True


@pytest.mark.asyncio
async def test_gps_settings_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """GPS settings should reapply typed helpers for legacy payloads."""

  raw_options = dict(mock_config_entry.options)
  raw_options[CONF_NOTIFICATIONS] = {
    CONF_QUIET_HOURS: "1",
    CONF_QUIET_START: " 05:00:00 ",
    CONF_QUIET_END: None,
    CONF_REMINDER_REPEAT_MIN: "30",
    "priority_notifications": "off",
    "mobile_notifications": "TRUE",
  }
  raw_options["dog_options"] = {
    "max": {
      DOG_ID_FIELD: "max",
      DOG_MODULES_FIELD: {
        MODULE_GPS: "true",
        MODULE_HEALTH: "no",
      },
    }
  }
  mock_config_entry.options = raw_options

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_gps_settings(
    {
      CONF_GPS_UPDATE_INTERVAL: 120,
      CONF_GPS_ACCURACY_FILTER: "8",
      CONF_GPS_DISTANCE_FILTER: "50",
      "gps_enabled": True,
      "route_recording": True,
      "route_history_days": "7",
      "auto_track_walks": "on",
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY

  options = cast(PawControlOptionsData, result["data"])
  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])
  assert notifications[CONF_QUIET_HOURS] is True
  assert notifications[CONF_QUIET_START] == "05:00:00"
  assert notifications[CONF_QUIET_END] == "07:00:00"
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 30
  assert notifications["priority_notifications"] is False
  assert notifications["mobile_notifications"] is True

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"max"}
  modules = dog_options["max"][DOG_MODULES_FIELD]
  assert modules[MODULE_GPS] is True
  assert modules[MODULE_HEALTH] is False

  gps_options = cast(GPSOptions, options["gps_settings"])
  assert gps_options[CONF_GPS_UPDATE_INTERVAL] == 120
  assert gps_options[CONF_GPS_ACCURACY_FILTER] == 8.0
  assert gps_options[CONF_GPS_DISTANCE_FILTER] == 50.0
  assert gps_options["gps_enabled"] is True
  assert gps_options["route_recording"] is True
  assert gps_options["route_history_days"] == 7
  assert gps_options["auto_track_walks"] is True


@pytest.mark.asyncio
async def test_dog_module_overrides_recorded(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Dog module configuration should persist typed overrides in options."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)
  flow.hass.config_entries.async_update_entry = Mock()

  dog_config = cast(DogConfigData, mock_config_entry.data[CONF_DOGS][0])
  flow._current_dog = dog_config

  result = await flow.async_step_configure_dog_modules(
    {
      "module_feeding": False,
      "module_walk": True,
      "module_gps": True,
      "module_garden": False,
      "module_health": True,
      "module_notifications": False,
      "module_dashboard": True,
      "module_visitor": True,
      "module_grooming": True,
      "module_medication": False,
      "module_training": True,
    }
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY
  flow.hass.config_entries.async_update_entry.assert_called_once()

  options = cast(PawControlOptionsData, result["data"])
  dog_options = cast(DogOptionsMap, options["dog_options"])

  dog_entry = dog_options[dog_config["dog_id"]]
  modules = dog_entry["modules"]

  assert modules[MODULE_GPS] is True
  assert modules[MODULE_WALK] is True
  assert modules[MODULE_HEALTH] is True
  assert modules.get("notifications") is False
  assert modules.get("grooming") is True


def test_module_description_placeholders_localize_grooming(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Module summary placeholders should localize grooming descriptions."""

  hass.config.language = "de"

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)
  flow._current_dog = flow._dogs[0]

  modules = flow._current_dog.setdefault("modules", {})
  modules[MODULE_GROOMING] = True

  placeholders = flow._get_module_description_placeholders()
  enabled_summary = placeholders["enabled_modules"]

  assert "Pflegeplan und Tracking" in enabled_summary
  assert "• Pflege:" in enabled_summary


@pytest.mark.asyncio
async def test_configure_door_sensor_normalises_and_persists(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Door sensor configuration should normalise payloads and persist updates."""

  hass.states.async_set(
    "binary_sensor.front_door",
    "off",
    {"device_class": "door", "friendly_name": "Front Door"},
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)
  flow.hass.config_entries.async_update_entry = Mock()
  flow._current_dog = flow._dogs[0]
  dog_id = flow._current_dog[DOG_ID_FIELD]

  data_manager = Mock()
  data_manager.async_update_dog_data = AsyncMock(return_value=True)
  runtime = Mock()
  runtime.data_manager = data_manager

  user_input = {
    CONF_DOOR_SENSOR: "binary_sensor.front_door  ",
    "walk_detection_timeout": " 180 ",
    "minimum_walk_duration": 75,
    "maximum_walk_duration": "7200",
    "door_closed_delay": "45",
    "require_confirmation": False,
    "auto_end_walks": True,
    "confidence_threshold": "0.85",
  }

  with (
    patch(
      "custom_components.pawcontrol.options_flow.get_runtime_data",
      return_value=runtime,
    ),
    patch(
      "custom_components.pawcontrol.options_flow.require_runtime_data",
      return_value=runtime,
    ),
  ):
    result = await flow.async_step_configure_door_sensor(user_input)

  assert result["type"] == FlowResultType.FORM
  flow.hass.config_entries.async_update_entry.assert_called_once()

  update_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
  updated_dog = update_data[CONF_DOGS][0]
  assert updated_dog[CONF_DOOR_SENSOR] == "binary_sensor.front_door"

  expected_settings = {
    "walk_detection_timeout": 180,
    "minimum_walk_duration": 75,
    "maximum_walk_duration": 7200,
    "door_closed_delay": 45,
    "require_confirmation": False,
    "auto_end_walks": True,
    "confidence_threshold": 0.85,
  }

  assert updated_dog[CONF_DOOR_SENSOR_SETTINGS] == expected_settings
  assert flow._current_dog[CONF_DOOR_SENSOR] == "binary_sensor.front_door"

  data_manager.async_update_dog_data.assert_awaited_once_with(
    dog_id,
    {
      CONF_DOOR_SENSOR: "binary_sensor.front_door",
      CONF_DOOR_SENSOR_SETTINGS: expected_settings,
    },
  )


@pytest.mark.asyncio
async def test_configure_door_sensor_removal_clears_persistence(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Removing a door sensor should clear stored overrides."""

  initial_dog = mock_config_entry.data[CONF_DOGS][0]
  initial_dog[CONF_DOOR_SENSOR] = "binary_sensor.back_door"
  initial_dog[CONF_DOOR_SENSOR_SETTINGS] = {
    "walk_detection_timeout": 240,
    "minimum_walk_duration": 90,
    "maximum_walk_duration": 3600,
    "door_closed_delay": 30,
    "require_confirmation": True,
    "auto_end_walks": False,
    "confidence_threshold": 0.7,
  }

  hass.states.async_set(
    "binary_sensor.back_door",
    "on",
    {"device_class": "door", "friendly_name": "Back Door"},
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)
  flow.hass.config_entries.async_update_entry = Mock()
  flow._current_dog = flow._dogs[0]
  dog_id = flow._current_dog[DOG_ID_FIELD]

  data_manager = Mock()
  data_manager.async_update_dog_data = AsyncMock(return_value=True)
  runtime = Mock()
  runtime.data_manager = data_manager

  with (
    patch(
      "custom_components.pawcontrol.options_flow.get_runtime_data",
      return_value=runtime,
    ),
    patch(
      "custom_components.pawcontrol.options_flow.require_runtime_data",
      return_value=runtime,
    ),
  ):
    result = await flow.async_step_configure_door_sensor({CONF_DOOR_SENSOR: ""})

  assert result["type"] == FlowResultType.FORM
  flow.hass.config_entries.async_update_entry.assert_called_once()

  update_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
  updated_dog = update_data[CONF_DOGS][0]
  assert CONF_DOOR_SENSOR not in updated_dog
  assert CONF_DOOR_SENSOR_SETTINGS not in updated_dog
  assert CONF_DOOR_SENSOR not in flow._current_dog
  assert CONF_DOOR_SENSOR_SETTINGS not in flow._current_dog

  data_manager.async_update_dog_data.assert_awaited_once_with(
    dog_id,
    {
      CONF_DOOR_SENSOR: None,
      CONF_DOOR_SENSOR_SETTINGS: None,
    },
  )


@pytest.mark.asyncio
async def test_configure_door_sensor_persistence_failure_records_telemetry(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Persistence failures should raise a repair issue and capture telemetry."""

  hass.states.async_set(
    "binary_sensor.front_door",
    "off",
    {"device_class": "door", "friendly_name": "Front Door"},
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)
  flow.hass.config_entries.async_update_entry = Mock()
  flow._current_dog = flow._dogs[0]
  dog_id = flow._current_dog[DOG_ID_FIELD]

  data_manager = SimpleNamespace(
    async_update_dog_data=AsyncMock(side_effect=RuntimeError("storage offline"))
  )
  runtime = SimpleNamespace(
    data_manager=data_manager,
    performance_stats={},
    error_history=cast(list[RuntimeErrorHistoryEntry], []),
  )

  user_input = {
    CONF_DOOR_SENSOR: "binary_sensor.front_door",
    "walk_detection_timeout": 60,
    "minimum_walk_duration": 90,
    "maximum_walk_duration": 3600,
    "door_closed_delay": 30,
    "require_confirmation": True,
    "auto_end_walks": False,
    "confidence_threshold": 0.75,
  }

  failure_timestamp = datetime(2024, 1, 1, tzinfo=UTC)

  with (
    patch(
      "custom_components.pawcontrol.options_flow.get_runtime_data",
      return_value=runtime,
    ),
    patch(
      "custom_components.pawcontrol.options_flow.require_runtime_data",
      return_value=runtime,
    ),
    patch(
      "custom_components.pawcontrol.options_flow.async_create_issue",
      new_callable=AsyncMock,
    ) as create_issue,
    patch(
      "custom_components.pawcontrol.telemetry.dt_util.utcnow",
      return_value=failure_timestamp,
    ),
  ):
    result = await flow.async_step_configure_door_sensor(user_input)

  assert result["type"] == FlowResultType.FORM
  assert result["errors"]["base"] == "door_sensor_update_failed"

  flow.hass.config_entries.async_update_entry.assert_not_called()
  data_manager.async_update_dog_data.assert_awaited_once_with(dog_id, ANY)

  create_issue.assert_awaited_once()
  args, kwargs = create_issue.call_args
  assert args[2] == f"{mock_config_entry.entry_id}_door_sensor_{dog_id}"
  assert args[3] == "door_sensor_persistence_failure"
  payload = args[4]
  assert payload["dog_id"] == dog_id
  assert payload["door_sensor"] == "binary_sensor.front_door"
  assert payload["timestamp"] == failure_timestamp.isoformat()
  assert kwargs["severity"] == "error"

  performance_stats = runtime.performance_stats
  assert performance_stats["door_sensor_failure_count"] == 1
  failures = performance_stats["door_sensor_failures"]
  assert failures[0]["dog_id"] == dog_id
  assert failures[0]["error"] == "storage offline"
  assert runtime.error_history[-1]["source"] == "door_sensor_persistence"


@pytest.mark.asyncio
async def test_configure_door_sensor_runtime_cache_unavailable(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Door sensor updates should fail when runtime data is missing."""

  hass.states.async_set(
    "binary_sensor.front_door",
    "off",
    {"device_class": "door", "friendly_name": "Front Door"},
  )

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)
  flow.hass.config_entries.async_update_entry = Mock()
  flow._current_dog = flow._dogs[0]
  dog_id = flow._current_dog[DOG_ID_FIELD]

  user_input = {
    CONF_DOOR_SENSOR: "binary_sensor.front_door",
    "walk_detection_timeout": 60,
    "minimum_walk_duration": 90,
    "maximum_walk_duration": 3600,
    "door_closed_delay": 30,
    "require_confirmation": True,
    "auto_end_walks": False,
    "confidence_threshold": 0.75,
  }

  with (
    patch(
      "custom_components.pawcontrol.options_flow.require_runtime_data",
      side_effect=RuntimeDataUnavailableError("store unavailable"),
    ),
    patch(
      "custom_components.pawcontrol.options_flow.async_create_issue",
      new_callable=AsyncMock,
    ) as create_issue,
  ):
    result = await flow.async_step_configure_door_sensor(user_input)

  assert result["type"] == FlowResultType.FORM
  assert result["errors"]["base"] == "runtime_cache_unavailable"
  flow.hass.config_entries.async_update_entry.assert_not_called()
  create_issue.assert_not_called()
  assert flow._current_dog[DOG_ID_FIELD] == dog_id


@pytest.mark.asyncio
async def test_add_new_dog_normalises_config(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Adding a dog should persist typed configuration data."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)
  flow.hass.config_entries.async_update_entry = Mock()

  result = await flow.async_step_add_new_dog(
    {
      CONF_DOG_ID: "Nova Pup",
      CONF_DOG_NAME: "Nova",
      CONF_DOG_BREED: "Border Collie",
      CONF_DOG_AGE: 5,
      CONF_DOG_WEIGHT: 19.5,
      CONF_DOG_SIZE: "medium",
    }
  )

  assert result["type"] == FlowResultType.MENU
  flow.hass.config_entries.async_update_entry.assert_called_once()

  _, kwargs = flow.hass.config_entries.async_update_entry.call_args
  updated_data = kwargs.get("data")
  assert isinstance(updated_data, dict)

  dogs = updated_data[CONF_DOGS]
  assert isinstance(dogs, list)
  new_dog = dogs[-1]

  assert new_dog[DOG_ID_FIELD] == "nova_pup"
  assert new_dog[DOG_NAME_FIELD] == "Nova"
  assert new_dog[DOG_WEIGHT_FIELD] == 19.5

  modules = new_dog[DOG_MODULES_FIELD]
  assert modules[MODULE_FEEDING] is True
  assert modules[MODULE_WALK] is True
  assert modules["dashboard"] is True

  assert flow._dogs[-1][DOG_NAME_FIELD] == "Nova"


@pytest.mark.asyncio
async def test_edit_dog_updates_config(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Editing a dog should write back typed configuration changes."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)
  flow.hass.config_entries.async_update_entry = Mock()

  flow._current_dog = flow._dogs[0]

  result = await flow.async_step_edit_dog(
    {
      CONF_DOG_NAME: "Buddy II",
      CONF_DOG_BREED: "Retriever",
      CONF_DOG_AGE: 4,
      CONF_DOG_WEIGHT: 32.5,
      CONF_DOG_SIZE: "large",
    }
  )

  assert result["type"] == FlowResultType.MENU
  flow.hass.config_entries.async_update_entry.assert_called_once()

  _, kwargs = flow.hass.config_entries.async_update_entry.call_args
  updated_data = kwargs.get("data")
  assert isinstance(updated_data, dict)

  updated_dog = updated_data[CONF_DOGS][0]
  assert updated_dog[DOG_NAME_FIELD] == "Buddy II"
  assert updated_dog[DOG_WEIGHT_FIELD] == 32.5
  assert updated_dog.get(DOG_ID_FIELD)

  assert flow._dogs[0][DOG_NAME_FIELD] == "Buddy II"


@pytest.mark.asyncio
async def test_remove_dog_normalises_snapshot(
  hass: HomeAssistant,
  mock_config_entry: ConfigEntry,
  mock_multi_dog_config: list[DogConfigData],
) -> None:
  """Removing a dog should reapply typed options before saving."""

  mock_config_entry.data = {CONF_DOGS: mock_multi_dog_config}

  raw_options = dict(mock_config_entry.options)
  raw_options[CONF_NOTIFICATIONS] = {
    CONF_QUIET_HOURS: "true",
    CONF_QUIET_START: " 05:30:00 ",
    CONF_QUIET_END: None,
    CONF_REMINDER_REPEAT_MIN: "120",
    "priority_notifications": "yes",
    "mobile_notifications": 0,
  }
  raw_options["dog_options"] = {
    "buddy": {
      DOG_ID_FIELD: "buddy",
      DOG_MODULES_FIELD: {
        MODULE_FEEDING: "1",
        MODULE_HEALTH: True,
      },
    },
    "max": {
      DOG_ID_FIELD: "max",
      DOG_MODULES_FIELD: {
        MODULE_FEEDING: "false",
        MODULE_HEALTH: "off",
      },
    },
  }
  mock_config_entry.options = raw_options

  flow = PawControlOptionsFlow()
  flow.hass = hass
  hass.config_entries.async_update_entry = Mock()
  flow.initialize_from_config_entry(mock_config_entry)

  result = await flow.async_step_select_dog_to_remove(
    {"dog_id": "max", "confirm_remove": True}
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY
  hass.config_entries.async_update_entry.assert_called_once()

  _, update_kwargs = hass.config_entries.async_update_entry.call_args
  updated_data = cast(ConfigEntryDataPayload, update_kwargs.get("data"))
  assert isinstance(updated_data, dict)

  dogs = cast(list[DogConfigData], updated_data[CONF_DOGS])
  assert len(dogs) == 1
  assert dogs[0][DOG_ID_FIELD] == "buddy"

  options = cast(PawControlOptionsData, result["data"])

  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])
  assert notifications[CONF_QUIET_HOURS] is True
  assert notifications[CONF_QUIET_START] == "05:30:00"
  assert notifications[CONF_QUIET_END] == "07:00:00"
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 120
  assert notifications["priority_notifications"] is True
  assert notifications["mobile_notifications"] is False

  dog_options = cast(DogOptionsMap, options["dog_options"])
  assert set(dog_options) == {"buddy"}

  buddy_entry = dog_options["buddy"]
  assert buddy_entry[DOG_ID_FIELD] == "buddy"
  buddy_modules = buddy_entry[DOG_MODULES_FIELD]
  assert buddy_modules[MODULE_FEEDING] is True
  assert buddy_modules[MODULE_HEALTH] is True


@pytest.mark.asyncio
async def test_import_export_export_flow(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Export step should surface a JSON payload with current settings."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  menu = await flow.async_step_import_export()
  assert menu["type"] == FlowResultType.FORM
  assert menu["step_id"] == "import_export"

  export_form = await flow.async_step_import_export({"action": "export"})
  assert export_form["type"] == FlowResultType.FORM
  assert export_form["step_id"] == "import_export_export"

  export_blob = export_form["description_placeholders"]["export_blob"]
  payload = cast(OptionsExportPayload, json.loads(export_blob))

  assert payload["version"] == 1
  assert (
    payload["options"]["entity_profile"] == mock_config_entry.options["entity_profile"]
  )
  assert payload["dogs"][0]["dog_id"] == mock_config_entry.data[CONF_DOGS][0]["dog_id"]

  finished = await flow.async_step_import_export_export({})
  assert finished["type"] == FlowResultType.MENU
  assert finished["step_id"] == "init"


@pytest.mark.asyncio
async def test_import_export_import_flow(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Import step should apply settings and update config entry data."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)
  flow.hass.config_entries.async_update_entry = Mock()

  baseline = flow._build_export_payload()
  baseline["options"]["entity_profile"] = "advanced"
  baseline["options"]["external_integrations"] = True
  baseline["dogs"][0]["dog_name"] = "Imported Pup"
  baseline["dogs"][0]["modules"] = {
    MODULE_GPS: True,
    MODULE_HEALTH: False,
  }

  payload_blob = json.dumps(baseline)

  import_form = await flow.async_step_import_export({"action": "import"})
  assert import_form["type"] == FlowResultType.FORM
  assert import_form["step_id"] == "import_export_import"

  result = await flow.async_step_import_export_import({"payload": payload_blob})

  assert result["type"] == FlowResultType.CREATE_ENTRY
  flow.hass.config_entries.async_update_entry.assert_called_once()

  options = cast(PawControlOptionsData, result["data"])
  assert options["entity_profile"] == "advanced"
  assert options["external_integrations"] is True

  update_call = flow.hass.config_entries.async_update_entry.call_args
  assert update_call is not None
  update_kwargs = update_call.kwargs
  assert update_kwargs["data"][CONF_DOGS][0]["dog_name"] == "Imported Pup"


def test_export_payload_normalises_legacy_options(
  mock_config_entry: ConfigEntry,
) -> None:
  """Exported payload should surface typed notifications and dog options."""

  raw_options = dict(mock_config_entry.options)
  raw_options[CONF_NOTIFICATIONS] = {
    CONF_QUIET_HOURS: "no",
    CONF_QUIET_START: " 18:45:00 ",
    CONF_QUIET_END: None,
    CONF_REMINDER_REPEAT_MIN: "15",
    "priority_notifications": "YES",
    "mobile_notifications": 0,
  }
  raw_options["dog_options"] = {
    "buddy": {
      DOG_ID_FIELD: "buddy",
      DOG_MODULES_FIELD: {
        MODULE_WALK: True,
        MODULE_FEEDING: "1",
      },
    },
    99: {
      DOG_MODULES_FIELD: {
        MODULE_HEALTH: "yes",
      }
    },
  }
  mock_config_entry.options = raw_options

  flow = PawControlOptionsFlow()
  flow.initialize_from_config_entry(mock_config_entry)

  payload = flow._build_export_payload()

  notifications = cast(NotificationOptions, payload["options"][CONF_NOTIFICATIONS])
  assert notifications[CONF_QUIET_HOURS] is False
  assert notifications[CONF_QUIET_START] == "18:45:00"
  assert notifications[CONF_QUIET_END] == "07:00:00"
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 15
  assert notifications["priority_notifications"] is True
  assert notifications["mobile_notifications"] is False

  dog_options = cast(DogOptionsMap, payload["options"]["dog_options"])
  assert set(dog_options) == {"buddy", "99"}

  buddy_modules = dog_options["buddy"][DOG_MODULES_FIELD]
  assert buddy_modules[MODULE_WALK] is True
  assert buddy_modules[MODULE_FEEDING] is True

  legacy_entry = dog_options["99"]
  assert legacy_entry[DOG_ID_FIELD] == "99"
  assert legacy_entry[DOG_MODULES_FIELD][MODULE_HEALTH] is True


@pytest.mark.asyncio
async def test_import_export_import_duplicate_dog(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Duplicate dog IDs should surface a dedicated error code."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  duplicate_payload = flow._build_export_payload()
  duplicate_payload["dogs"].append(dict(duplicate_payload["dogs"][0]))
  payload_blob = json.dumps(duplicate_payload)

  await flow.async_step_import_export({"action": "import"})
  result = await flow.async_step_import_export_import({"payload": payload_blob})

  assert result["type"] == FlowResultType.FORM
  assert result["errors"] == {"payload": "dog_duplicate"}


@pytest.mark.asyncio
async def test_import_export_import_invalid_modules(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Non-mapping modules payloads should be rejected during import."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  payload = flow._build_export_payload()
  payload["dogs"][0][CONF_MODULES] = ["not", "valid"]
  payload_blob = json.dumps(payload)

  await flow.async_step_import_export({"action": "import"})
  result = await flow.async_step_import_export_import({"payload": payload_blob})

  assert result["type"] == FlowResultType.FORM
  assert result["errors"] == {"payload": "dog_invalid_modules"}


def test_validate_import_payload_sanitises_modules(
  mock_config_entry: ConfigEntry,
) -> None:
  """Dog module flags should be coerced to booleans when importing."""

  flow = PawControlOptionsFlow()
  flow.initialize_from_config_entry(mock_config_entry)

  payload = flow._build_export_payload()
  payload["dogs"][0][CONF_MODULES] = {"gps": "yes", "health": 0}

  validated = flow._validate_import_payload(payload)

  modules = cast(DogConfigData, validated["dogs"][0])[CONF_MODULES]
  assert modules["gps"] is True
  assert modules["health"] is False


@pytest.mark.asyncio
async def test_import_export_import_unsupported_version(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Unsupported export versions should surface a specific error."""

  flow = PawControlOptionsFlow()
  flow.hass = hass
  flow.initialize_from_config_entry(mock_config_entry)

  payload = flow._build_export_payload()
  payload["version"] = 99  # type: ignore[assignment]
  payload_blob = json.dumps(payload)

  await flow.async_step_import_export({"action": "import"})
  result = await flow.async_step_import_export_import({"payload": payload_blob})

  assert result["type"] == FlowResultType.FORM
  assert result["errors"] == {"payload": "unsupported_version"}
