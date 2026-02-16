from datetime import UTC, datetime, time
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, Mock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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
  MAX_GEOFENCE_RADIUS,
  MIN_GEOFENCE_RADIUS,
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_GROOMING,
  MODULE_HEALTH,
  MODULE_WALK,
)
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow
from custom_components.pawcontrol.runtime_data import RuntimeDataUnavailableError
from custom_components.pawcontrol.types import (
  AUTO_TRACK_WALKS_FIELD,
  DOG_ID_FIELD,
  DOG_MODULES_FIELD,
  DOG_NAME_FIELD,
  DOG_WEIGHT_FIELD,
  GEOFENCE_ALERTS_FIELD,
  GEOFENCE_ENABLED_FIELD,
  GEOFENCE_LAT_FIELD,
  GEOFENCE_LON_FIELD,
  GEOFENCE_RADIUS_FIELD,
  GEOFENCE_RESTRICTED_ZONE_FIELD,
  GEOFENCE_SAFE_ZONE_FIELD,
  GEOFENCE_USE_HOME_FIELD,
  GEOFENCE_ZONE_ENTRY_FIELD,
  GEOFENCE_ZONE_EXIT_FIELD,
  GPS_ENABLED_FIELD,
  NOTIFICATION_MOBILE_FIELD,
  NOTIFICATION_PRIORITY_FIELD,
  NOTIFICATION_QUIET_END_FIELD,
  NOTIFICATION_QUIET_HOURS_FIELD,
  NOTIFICATION_QUIET_START_FIELD,
  NOTIFICATION_REMINDER_REPEAT_FIELD,
  ROUTE_HISTORY_DAYS_FIELD,
  ROUTE_RECORDING_FIELD,
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
  assert notifications[NOTIFICATION_QUIET_HOURS_FIELD] is quiet_hours  # noqa: E111
  assert notifications[NOTIFICATION_QUIET_START_FIELD] == quiet_start  # noqa: E111
  assert notifications[NOTIFICATION_QUIET_END_FIELD] == quiet_end  # noqa: E111
  assert notifications[NOTIFICATION_REMINDER_REPEAT_FIELD] == reminder_repeat_min  # noqa: E111
  assert notifications[NOTIFICATION_PRIORITY_FIELD] is priority_notifications  # noqa: E111
  assert notifications[NOTIFICATION_MOBILE_FIELD] is mobile_notifications  # noqa: E111


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
  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])  # noqa: E111
  _assert_notification_values(  # noqa: E111
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
  entry = dog_options[dog_id]  # noqa: E111
  assert entry[DOG_ID_FIELD] == dog_id  # noqa: E111
  modules = entry[DOG_MODULES_FIELD]  # noqa: E111
  for module_key, expected_value in expected_modules.items():  # noqa: E111
    assert modules[module_key] is expected_value


def _set_raw_options(
  mock_config_entry: ConfigEntry,
  *,
  notifications: dict[str, Any] | None = None,
  dog_options: dict[Any, Any] | None = None,
) -> None:
  raw_options = dict(mock_config_entry.options)  # noqa: E111
  if notifications is not None:  # noqa: E111
    raw_options[CONF_NOTIFICATIONS] = notifications
  if dog_options is not None:  # noqa: E111
    raw_options["dog_options"] = dog_options
  mock_config_entry.options = raw_options  # noqa: E111


def _set_raw_options_with_buddy_and_max(
  mock_config_entry: ConfigEntry,
) -> None:
  _set_raw_options(  # noqa: E111
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
      "123": {
        DOG_MODULES_FIELD: {
          MODULE_GPS: "true",
          MODULE_WALK: "",
        }
      },
    },
  )


def _set_raw_options_with_luna(
  mock_config_entry: ConfigEntry,
) -> None:
  _set_raw_options(  # noqa: E111
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


def _assert_notification_snapshot(
  options: PawControlOptionsData,
  *,
  quiet_hours: bool,
  quiet_start: str,
  quiet_end: str,
  reminder_repeat_min: int,
  priority_notifications: bool,
  mobile_notifications: bool,
  dog_modules: dict[str, dict[str, bool]],
) -> None:
  _assert_notifications(  # noqa: E111
    options,
    quiet_hours=quiet_hours,
    quiet_start=quiet_start,
    quiet_end=quiet_end,
    reminder_repeat_min=reminder_repeat_min,
    priority_notifications=priority_notifications,
    mobile_notifications=mobile_notifications,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])  # noqa: E111
  assert set(dog_options) == set(dog_modules)  # noqa: E111

  for dog_id, modules in dog_modules.items():  # noqa: E111
    _assert_dog_modules(dog_options, dog_id, modules)


def test_ensure_notification_options_normalises_values() -> None:
  """Notification options should coerce overrides and preserve defaults."""  # noqa: E111

  defaults = {  # noqa: E111
    CONF_QUIET_HOURS: True,
    CONF_QUIET_START: "21:00",
    CONF_QUIET_END: "06:30",
    CONF_REMINDER_REPEAT_MIN: 30,
    "priority_notifications": False,
    "mobile_notifications": True,
  }
  payload = {  # noqa: E111
    CONF_QUIET_HOURS: "no",
    CONF_QUIET_START: " 20:45 ",
    CONF_QUIET_END: "   ",
    CONF_REMINDER_REPEAT_MIN: "45",
    "priority_notifications": "yes",
    "mobile_notifications": 0,
  }

  options = ensure_notification_options(payload, defaults=defaults)  # noqa: E111

  assert options[NOTIFICATION_QUIET_HOURS_FIELD] is False  # noqa: E111
  assert options[NOTIFICATION_QUIET_START_FIELD] == "20:45"  # noqa: E111
  assert options[NOTIFICATION_QUIET_END_FIELD] == "06:30"  # noqa: E111
  assert options[NOTIFICATION_REMINDER_REPEAT_FIELD] == 45  # noqa: E111
  assert options[NOTIFICATION_PRIORITY_FIELD] is True  # noqa: E111
  assert options[NOTIFICATION_MOBILE_FIELD] is False  # noqa: E111


def test_ensure_notification_options_ignores_invalid_entries() -> None:
  """Invalid overrides should be dropped from the normalised payload."""  # noqa: E111

  payload = {  # noqa: E111
    CONF_QUIET_HOURS: "maybe",
    CONF_QUIET_START: None,
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "fast",
    "priority_notifications": None,
    "mobile_notifications": " ",
  }

  options = ensure_notification_options(payload)  # noqa: E111

  assert NOTIFICATION_QUIET_HOURS_FIELD not in options  # noqa: E111
  assert NOTIFICATION_QUIET_START_FIELD not in options  # noqa: E111
  assert NOTIFICATION_QUIET_END_FIELD not in options  # noqa: E111
  assert NOTIFICATION_REMINDER_REPEAT_FIELD not in options  # noqa: E111
  assert NOTIFICATION_PRIORITY_FIELD not in options  # noqa: E111
  assert NOTIFICATION_MOBILE_FIELD not in options  # noqa: E111


@pytest.mark.asyncio
async def test_geofence_settings_coercion(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Geofence options should be normalised into typed payloads."""  # noqa: E111

  hass.config.latitude = 12.34  # noqa: E111
  hass.config.longitude = 56.78  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_geofence_settings({  # noqa: E111
    "geofencing_enabled": True,
    "geofence_radius_m": "120",
    "geofence_lat": "41.8899",
    "geofence_lon": 12.4923,
    "geofence_alerts_enabled": False,
    "safe_zone_alerts": False,
    "restricted_zone_alerts": True,
    "zone_entry_notifications": True,
    "zone_exit_notifications": False,
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  geofence = cast(GeofenceOptions, options["geofence_settings"])  # noqa: E111

  assert geofence["geofence_radius_m"] == 120  # noqa: E111
  assert geofence["geofence_lat"] == pytest.approx(41.8899)  # noqa: E111
  assert geofence["geofence_lon"] == pytest.approx(12.4923)  # noqa: E111
  assert geofence["geofence_alerts_enabled"] is False  # noqa: E111
  assert geofence["safe_zone_alerts"] is False  # noqa: E111
  assert geofence["restricted_zone_alerts"] is True  # noqa: E111
  assert geofence["zone_entry_notifications"] is True  # noqa: E111
  assert geofence["zone_exit_notifications"] is False  # noqa: E111


@pytest.mark.asyncio
async def test_geofence_settings_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Geofence updates should reapply typed notifications and dog payloads."""  # noqa: E111

  _set_raw_options_with_buddy_and_max(mock_config_entry)  # noqa: E111

  hass.config.latitude = 12.34  # noqa: E111
  hass.config.longitude = 56.78  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_geofence_settings({  # noqa: E111
    "geofencing_enabled": True,
    "geofence_radius_m": "95",
    "geofence_lat": "41.8899",
    "geofence_lon": 12.4923,
    "geofence_alerts_enabled": True,
    "safe_zone_alerts": False,
    "restricted_zone_alerts": True,
    "zone_entry_notifications": False,
    "zone_exit_notifications": True,
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  _assert_notification_snapshot(  # noqa: E111
    options,
    quiet_hours=False,
    quiet_start="19:00:00",
    quiet_end="07:00:00",
    reminder_repeat_min=5,
    priority_notifications=False,
    mobile_notifications=True,
    dog_modules={
      "buddy": {
        MODULE_FEEDING: False,
        MODULE_HEALTH: True,
      },
      "123": {
        MODULE_GPS: True,
        MODULE_WALK: False,
      },
    },
  )


@pytest.mark.asyncio
async def test_geofence_settings_rejects_invalid_coordinates(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Geofence settings should reject invalid coordinate inputs."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_geofence_settings({  # noqa: E111
    GEOFENCE_ENABLED_FIELD: True,
    GEOFENCE_USE_HOME_FIELD: False,
    GEOFENCE_RADIUS_FIELD: MIN_GEOFENCE_RADIUS,
    GEOFENCE_LAT_FIELD: "north",
    GEOFENCE_LON_FIELD: 12.4923,
    GEOFENCE_ALERTS_FIELD: True,
    GEOFENCE_SAFE_ZONE_FIELD: True,
    GEOFENCE_RESTRICTED_ZONE_FIELD: True,
    GEOFENCE_ZONE_ENTRY_FIELD: True,
    GEOFENCE_ZONE_EXIT_FIELD: True,
  })

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["errors"][GEOFENCE_LAT_FIELD] == "coordinate_not_numeric"  # noqa: E111


@pytest.mark.asyncio
async def test_geofence_settings_accepts_radius_boundaries(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Geofence settings should accept radius boundary values."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_geofence_settings({  # noqa: E111
    GEOFENCE_ENABLED_FIELD: True,
    GEOFENCE_USE_HOME_FIELD: False,
    GEOFENCE_RADIUS_FIELD: MAX_GEOFENCE_RADIUS,
    GEOFENCE_LAT_FIELD: 0,
    GEOFENCE_LON_FIELD: 0,
    GEOFENCE_ALERTS_FIELD: True,
    GEOFENCE_SAFE_ZONE_FIELD: True,
    GEOFENCE_RESTRICTED_ZONE_FIELD: True,
    GEOFENCE_ZONE_ENTRY_FIELD: True,
    GEOFENCE_ZONE_EXIT_FIELD: True,
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111


@pytest.mark.asyncio
async def test_notification_settings_structured(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Notification settings should store typed quiet-hour metadata."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_notifications({  # noqa: E111
    "quiet_hours": False,
    "quiet_start": "21:30:00",
    "quiet_end": "06:45:00",
    "reminder_repeat_min": "45",
    "priority_notifications": True,
    "mobile_notifications": False,
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  _assert_notifications(  # noqa: E111
    options,
    quiet_hours=False,
    quiet_start="21:30:00",
    quiet_end="06:45:00",
    reminder_repeat_min=45,
    priority_notifications=True,
    mobile_notifications=False,
  )


@pytest.mark.asyncio
async def test_notification_settings_rejects_invalid_repeat_interval(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Notification settings should reject reminder repeat values out of range."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_notifications({  # noqa: E111
    "quiet_hours": True,
    "quiet_start": "22:00:00",
    "quiet_end": "07:00:00",
    "reminder_repeat_min": 1,
    "priority_notifications": True,
    "mobile_notifications": False,
  })

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["errors"]["reminder_repeat_min"] == "invalid_configuration"  # noqa: E111


@pytest.mark.asyncio
async def test_notification_settings_rejects_invalid_quiet_times(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Notification settings should reject invalid quiet-hour times."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_notifications({  # noqa: E111
    "quiet_hours": True,
    "quiet_start": "25:61",
    "quiet_end": "07:00:00",
    "reminder_repeat_min": 30,
    "priority_notifications": True,
    "mobile_notifications": False,
  })

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["errors"]["quiet_start"] == "quiet_start_invalid"  # noqa: E111


def test_notification_settings_normalise_existing_payload(
  mock_config_entry: ConfigEntry,
) -> None:
  """Stored notification mappings should be coerced back onto the typed surface."""  # noqa: E111

  stored_options = dict(mock_config_entry.options)  # noqa: E111
  stored_options[CONF_NOTIFICATIONS] = {  # noqa: E111
    CONF_QUIET_HOURS: "no",
    CONF_QUIET_START: " 20:00:00 ",
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "900",
    "priority_notifications": "false",
    "mobile_notifications": 0,
  }
  mock_config_entry.options = stored_options  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  notifications = flow._current_notification_options()  # noqa: E111

  _assert_notification_values(  # noqa: E111
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
  """Performance settings normalise mixed input types into typed options."""  # noqa: E111

  raw_options = dict(mock_config_entry.options)  # noqa: E111
  raw_options[CONF_NOTIFICATIONS] = {  # noqa: E111
    CONF_QUIET_HOURS: "yes",
    CONF_QUIET_START: " 19:45:00 ",
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "600",
    "priority_notifications": "OFF",
    "mobile_notifications": "true",
  }
  raw_options["dog_options"] = {  # noqa: E111
    "test_dog": {
      DOG_ID_FIELD: "test_dog",
      DOG_MODULES_FIELD: {
        MODULE_HEALTH: "on",
        MODULE_WALK: 0,
      },
    }
  }
  mock_config_entry.options = raw_options  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_performance_settings({  # noqa: E111
    "entity_profile": "advanced",
    "performance_mode": "FAST",
    "batch_size": 25.0,
    "cache_ttl": "900",
    "selective_refresh": "0",
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111

  assert options["entity_profile"] == "advanced"  # noqa: E111
  assert options["performance_mode"] == "balanced"  # noqa: E111
  assert options["batch_size"] == 25  # noqa: E111
  assert options["cache_ttl"] == 900  # noqa: E111
  assert options["selective_refresh"] is False  # noqa: E111

  _assert_notifications(  # noqa: E111
    options,
    quiet_hours=True,
    quiet_start="19:45:00",
    quiet_end="07:00:00",
    reminder_repeat_min=180,
    priority_notifications=False,
    mobile_notifications=True,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])  # noqa: E111
  assert set(dog_options) == {"test_dog"}  # noqa: E111

  _assert_dog_modules(  # noqa: E111
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
  """Entity profile form should surface the latest reconfigure telemetry."""  # noqa: E111

  mock_config_entry.options.update({  # noqa: E111
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
  })

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_entity_profiles()  # noqa: E111

  placeholders = result["description_placeholders"]  # noqa: E111
  assert placeholders["reconfigure_requested_profile"] == "balanced"  # noqa: E111
  assert placeholders["reconfigure_previous_profile"] == "advanced"  # noqa: E111
  assert placeholders["reconfigure_dogs"] == "2"  # noqa: E111
  assert placeholders["reconfigure_entities"] == "12"  # noqa: E111
  assert "Missing GPS source" in placeholders["reconfigure_health"]  # noqa: E111
  assert "GPS disabled" in placeholders["reconfigure_warnings"]  # noqa: E111
  merge_notes = placeholders["reconfigure_merge_notes"].split("\n")  # noqa: E111
  assert "Buddy: your dog options enabled gps." in merge_notes  # noqa: E111


@pytest.mark.asyncio
async def test_entity_profiles_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Entity profile saves should reapply typed notifications and dog data."""  # noqa: E111

  _set_raw_options_with_luna(mock_config_entry)  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_entity_profiles({"entity_profile": "advanced"})  # noqa: E111

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  _assert_notification_snapshot(  # noqa: E111
    options,
    quiet_hours=True,
    quiet_start="22:00:00",
    quiet_end="07:00:00",
    reminder_repeat_min=180,
    priority_notifications=True,
    mobile_notifications=False,
    dog_modules={
      "luna": {
        MODULE_HEALTH: True,
        MODULE_FEEDING: False,
      },
    },
  )

  assert options["entity_profile"] == "advanced"  # noqa: E111


@pytest.mark.asyncio
async def test_profile_preview_apply_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Applying a preview should rehydrate typed options snapshots."""  # noqa: E111

  _set_raw_options(  # noqa: E111
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

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_profile_preview({  # noqa: E111
    "profile": "gps_focus",
    "apply_profile": True,
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  assert options["entity_profile"] == "gps_focus"  # noqa: E111

  _assert_notifications(  # noqa: E111
    options,
    quiet_hours=False,
    quiet_start="20:15:00",
    quiet_end="07:00:00",
    reminder_repeat_min=5,
    priority_notifications=False,
    mobile_notifications=True,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])  # noqa: E111
  assert set(dog_options) == {"scout"}  # noqa: E111

  _assert_dog_modules(  # noqa: E111
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
  """Weather options should clamp intervals and clean override payloads."""  # noqa: E111

  hass.states.async_set(  # noqa: E111
    "weather.home", "sunny", {"friendly_name": "Home", "temperature": 21}
  )

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_weather_settings({  # noqa: E111
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
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  weather = cast(WeatherOptions, options["weather_settings"])  # noqa: E111

  assert options[CONF_WEATHER_ENTITY] == "weather.home"  # noqa: E111
  assert weather[CONF_WEATHER_ENTITY] == "weather.home"  # noqa: E111
  assert weather["weather_update_interval"] == 15  # noqa: E111
  assert weather["weather_health_monitoring"] is False  # noqa: E111
  assert weather["weather_alerts"] is True  # noqa: E111
  assert weather["temperature_alerts"] is True  # noqa: E111
  assert weather["uv_alerts"] is False  # noqa: E111
  assert weather["humidity_alerts"] is True  # noqa: E111
  assert weather["wind_alerts"] is True  # noqa: E111
  assert weather["storm_alerts"] is False  # noqa: E111
  assert weather["breed_specific_recommendations"] is False  # noqa: E111
  assert weather["auto_activity_adjustments"] is True  # noqa: E111
  assert weather["notification_threshold"] == "moderate"  # noqa: E111


@pytest.mark.asyncio
async def test_feeding_settings_coercion(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Feeding options should normalise numeric ranges and booleans."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_feeding_settings({  # noqa: E111
    "meals_per_day": "7",
    "feeding_reminders": "0",
    "portion_tracking": True,
    "calorie_tracking": "False",
    "auto_schedule": "yes",
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  feeding = cast(FeedingOptions, options["feeding_settings"])  # noqa: E111

  assert feeding["default_meals_per_day"] == 6  # noqa: E111
  assert feeding["feeding_reminders"] is False  # noqa: E111
  assert feeding["portion_tracking"] is True  # noqa: E111
  assert feeding["calorie_tracking"] is False  # noqa: E111
  assert feeding["auto_schedule"] is True  # noqa: E111


@pytest.mark.asyncio
async def test_health_settings_coercion(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Health options should coerce truthy strings to booleans."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_health_settings({  # noqa: E111
    "weight_tracking": "no",
    "medication_reminders": "on",
    "vet_reminders": "true",
    "grooming_reminders": "0",
    "health_alerts": "yes",
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  health = cast(HealthOptions, options["health_settings"])  # noqa: E111

  assert health["weight_tracking"] is False  # noqa: E111
  assert health["medication_reminders"] is True  # noqa: E111
  assert health["vet_reminders"] is True  # noqa: E111
  assert health["grooming_reminders"] is False  # noqa: E111
  assert health["health_alerts"] is True  # noqa: E111


@pytest.mark.asyncio
async def test_feeding_settings_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Feeding menu updates should reapply typed notification and dog payloads."""  # noqa: E111

  _set_raw_options_with_buddy_and_max(mock_config_entry)  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_feeding_settings({  # noqa: E111
    "meals_per_day": "3",
    "feeding_reminders": "0",
    "portion_tracking": "True",
    "calorie_tracking": 0,
    "auto_schedule": "yes",
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  _assert_notification_snapshot(  # noqa: E111
    options,
    quiet_hours=False,
    quiet_start="19:00:00",
    quiet_end="07:00:00",
    reminder_repeat_min=5,
    priority_notifications=False,
    mobile_notifications=True,
    dog_modules={
      "buddy": {
        MODULE_FEEDING: False,
        MODULE_HEALTH: True,
      },
      "123": {
        MODULE_GPS: True,
        MODULE_WALK: False,
      },
    },
  )


@pytest.mark.asyncio
async def test_health_settings_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Health menu updates should keep notifications and dogs on typed surfaces."""  # noqa: E111

  _set_raw_options_with_luna(mock_config_entry)  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_health_settings({  # noqa: E111
    "weight_tracking": "1",
    "medication_reminders": "false",
    "vet_reminders": "TRUE",
    "grooming_reminders": 0,
    "health_alerts": "YES",
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  _assert_notification_snapshot(  # noqa: E111
    options,
    quiet_hours=True,
    quiet_start="22:00:00",
    quiet_end="07:00:00",
    reminder_repeat_min=180,
    priority_notifications=True,
    mobile_notifications=False,
    dog_modules={
      "luna": {
        MODULE_HEALTH: True,
        MODULE_FEEDING: False,
      },
    },
  )

  health = cast(HealthOptions, options["health_settings"])  # noqa: E111
  assert health["weight_tracking"] is True  # noqa: E111
  assert health["medication_reminders"] is False  # noqa: E111
  assert health["vet_reminders"] is True  # noqa: E111
  assert health["grooming_reminders"] is False  # noqa: E111
  assert health["health_alerts"] is True  # noqa: E111


@pytest.mark.asyncio
async def test_system_settings_normalisation(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """System options should clamp retention and normalise times."""  # noqa: E111

  raw_options = dict(mock_config_entry.options)  # noqa: E111
  raw_options[CONF_NOTIFICATIONS] = {  # noqa: E111
    CONF_QUIET_HOURS: "yes",
    CONF_QUIET_START: " 05:15:00 ",
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "999",
    "priority_notifications": "off",
    "mobile_notifications": 1,
  }
  raw_options["dog_options"] = {  # noqa: E111
    "buddy": {
      DOG_ID_FIELD: "buddy",
      DOG_MODULES_FIELD: {
        MODULE_WALK: "yes",
        MODULE_FEEDING: 0,
      },
    }
  }
  raw_options["system_settings"] = {  # noqa: E111
    "enable_analytics": False,
    "enable_cloud_backup": True,
  }
  raw_options["enable_analytics"] = False  # noqa: E111
  raw_options["enable_cloud_backup"] = True  # noqa: E111
  mock_config_entry.options = raw_options  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  script_manager = Mock()  # noqa: E111
  script_manager.async_sync_manual_resilience_events = AsyncMock()  # noqa: E111
  runtime = Mock()  # noqa: E111
  runtime.script_manager = script_manager  # noqa: E111

  with patch(  # noqa: E111
    "custom_components.pawcontrol.options_flow_support.get_runtime_data",
    return_value=runtime,
  ):
    result = await flow.async_step_system_settings({
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
    })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  system = cast(SystemOptions, options["system_settings"])  # noqa: E111

  assert options[CONF_RESET_TIME] == "04:30:00"  # noqa: E111
  assert system["data_retention_days"] == 30  # noqa: E111
  assert system["auto_backup"] is True  # noqa: E111
  assert system["performance_mode"] == "full"  # noqa: E111
  assert system["enable_analytics"] is True  # noqa: E111
  assert system["enable_cloud_backup"] is False  # noqa: E111
  assert system["resilience_skip_threshold"] == 7  # noqa: E111
  assert system["resilience_breaker_threshold"] == 2  # noqa: E111
  assert system["manual_check_event"] == "pawcontrol_custom_check"  # noqa: E111
  assert system["manual_guard_event"] == "pawcontrol_manual_guard"  # noqa: E111
  assert system["manual_breaker_event"] is None  # noqa: E111

  assert options["enable_analytics"] is True  # noqa: E111
  assert options["enable_cloud_backup"] is False  # noqa: E111
  assert options["manual_guard_event"] == "pawcontrol_manual_guard"  # noqa: E111
  assert "manual_breaker_event" not in options  # noqa: E111

  _assert_notifications(  # noqa: E111
    options,
    quiet_hours=True,
    quiet_start="05:15:00",
    quiet_end="07:00:00",
    reminder_repeat_min=180,
    priority_notifications=False,
    mobile_notifications=True,
  )

  dog_options = cast(DogOptionsMap, options["dog_options"])  # noqa: E111
  assert set(dog_options) == {"buddy"}  # noqa: E111

  _assert_dog_modules(  # noqa: E111
    dog_options,
    "buddy",
    {
      MODULE_WALK: True,
      MODULE_FEEDING: False,
    },
  )

  script_manager.async_sync_manual_resilience_events.assert_awaited_once_with({  # noqa: E111
    "manual_check_event": "pawcontrol_custom_check",
    "manual_guard_event": "pawcontrol_manual_guard",
    "manual_breaker_event": None,
  })


@pytest.mark.asyncio
async def test_system_settings_manual_event_placeholders(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Manual event placeholders should combine options and blueprint values."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  mock_config_entry.options = {  # noqa: E111
    "system_settings": {
      "manual_guard_event": "pawcontrol_manual_guard",
      "manual_breaker_event": None,
    }
  }
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  script_manager = Mock()  # noqa: E111
  script_manager.get_resilience_escalation_snapshot.return_value = {  # noqa: E111
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
  runtime = Mock()  # noqa: E111
  runtime.script_manager = script_manager  # noqa: E111

  with patch(  # noqa: E111
    "custom_components.pawcontrol.options_flow_support.get_runtime_data",
    return_value=runtime,
  ):
    placeholders = flow._manual_event_description_placeholders()

  assert placeholders["manual_guard_event_options"] == "pawcontrol_manual_guard"  # noqa: E111
  assert placeholders["manual_breaker_event_options"] == "pawcontrol_manual_breaker"  # noqa: E111
  assert placeholders["manual_check_event_options"] == "pawcontrol_resilience_check"  # noqa: E111


@pytest.mark.asyncio
async def test_manual_event_choices_support_disable_and_translations(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Manual event dropdowns should expose disable and localized options."""  # noqa: E111

  hass.config.language = "de"  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  mock_config_entry.options = {  # noqa: E111
    "system_settings": {
      "manual_guard_event": "pawcontrol_manual_guard",
      "manual_breaker_event": "pawcontrol_manual_breaker",
    }
  }
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  script_manager = Mock()  # noqa: E111
  script_manager.get_resilience_escalation_snapshot.return_value = {  # noqa: E111
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
  runtime = Mock()  # noqa: E111
  runtime.script_manager = script_manager  # noqa: E111

  with patch(  # noqa: E111
    "custom_components.pawcontrol.options_flow_support.get_runtime_data",
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
      == "Entfernt den Listener und beendet die Überwachung dieses manuellen Ereignisses."  # noqa: E501
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
  """Dashboard options should normalise modes and booleans."""  # noqa: E111

  raw_options = dict(mock_config_entry.options)  # noqa: E111
  raw_options[CONF_NOTIFICATIONS] = {  # noqa: E111
    CONF_QUIET_HOURS: 0,
    CONF_QUIET_START: "23:00:00",
    CONF_QUIET_END: None,
    CONF_REMINDER_REPEAT_MIN: 12.5,
    "priority_notifications": "on",
    "mobile_notifications": "false",
  }
  raw_options["dog_options"] = {  # noqa: E111
    "fido": {
      DOG_ID_FIELD: "fido",
      DOG_MODULES_FIELD: {
        MODULE_HEALTH: "true",
        MODULE_GPS: "no",
      },
    }
  }
  mock_config_entry.options = raw_options  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_dashboard_settings({  # noqa: E111
    "dashboard_mode": "CARDS",
    "show_statistics": "0",
    "show_alerts": True,
    "compact_mode": "1",
    "show_maps": "off",
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  dashboard = cast(DashboardOptions, options["dashboard_settings"])  # noqa: E111

  assert options[CONF_DASHBOARD_MODE] == "cards"  # noqa: E111
  assert dashboard["show_statistics"] is False  # noqa: E111
  assert dashboard["show_alerts"] is True  # noqa: E111
  assert dashboard["compact_mode"] is True  # noqa: E111
  assert dashboard["show_maps"] is False  # noqa: E111

  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])  # noqa: E111
  assert notifications[CONF_QUIET_HOURS] is False  # noqa: E111
  assert notifications[CONF_QUIET_START] == "23:00:00"  # noqa: E111
  assert notifications[CONF_QUIET_END] == "07:00:00"  # noqa: E111
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 12  # noqa: E111
  assert notifications["priority_notifications"] is True  # noqa: E111
  assert notifications["mobile_notifications"] is False  # noqa: E111

  dog_options = cast(DogOptionsMap, options["dog_options"])  # noqa: E111
  assert set(dog_options) == {"fido"}  # noqa: E111

  fido_entry = dog_options["fido"]  # noqa: E111
  assert fido_entry[DOG_ID_FIELD] == "fido"  # noqa: E111
  fido_modules = fido_entry[DOG_MODULES_FIELD]  # noqa: E111
  assert fido_modules[MODULE_HEALTH] is True  # noqa: E111
  assert fido_modules[MODULE_GPS] is False  # noqa: E111


@pytest.mark.asyncio
async def test_advanced_settings_structured(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Advanced options should normalise ranges and mirror root fields."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_advanced_settings({  # noqa: E111
    "performance_mode": "ULTRA",
    "debug_logging": "true",
    "data_retention_days": "500",
    "auto_backup": "1",
    "experimental_features": "on",
    CONF_EXTERNAL_INTEGRATIONS: "yes",
    CONF_API_ENDPOINT: " https://demo.local ",
    CONF_API_TOKEN: "  secret  ",
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  advanced = cast(AdvancedOptions, options["advanced_settings"])  # noqa: E111

  assert options["performance_mode"] == "balanced"  # noqa: E111
  assert options["debug_logging"] is True  # noqa: E111
  assert options["data_retention_days"] == 365  # noqa: E111
  assert options[CONF_EXTERNAL_INTEGRATIONS] is True  # noqa: E111
  assert options[CONF_API_ENDPOINT] == "https://demo.local"  # noqa: E111
  assert options[CONF_API_TOKEN] == "secret"  # noqa: E111

  assert advanced["performance_mode"] == "balanced"  # noqa: E111
  assert advanced["debug_logging"] is True  # noqa: E111
  assert advanced["data_retention_days"] == 365  # noqa: E111
  assert advanced["auto_backup"] is True  # noqa: E111
  assert advanced["experimental_features"] is True  # noqa: E111
  assert advanced[CONF_EXTERNAL_INTEGRATIONS] is True  # noqa: E111
  assert advanced[CONF_API_ENDPOINT] == "https://demo.local"  # noqa: E111
  assert advanced[CONF_API_TOKEN] == "secret"  # noqa: E111


@pytest.mark.asyncio
async def test_advanced_settings_normalises_existing_payloads(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Advanced settings should coerce legacy notification and dog payloads."""  # noqa: E111

  raw_options = dict(mock_config_entry.options)  # noqa: E111
  raw_options[CONF_NOTIFICATIONS] = {  # noqa: E111
    CONF_QUIET_HOURS: "false",
    CONF_QUIET_START: " 19:00:00 ",
    CONF_QUIET_END: "",
    CONF_REMINDER_REPEAT_MIN: "300",
    "priority_notifications": "no",
    "mobile_notifications": "YES",
  }
  raw_options["dog_options"] = {  # noqa: E111
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
  raw_options["advanced_settings"] = {  # noqa: E111
    "performance_mode": "turbo",
    "debug_logging": "no",
    "data_retention_days": "1000",
    "auto_backup": "maybe",
    "experimental_features": "yes",
    CONF_EXTERNAL_INTEGRATIONS: "enabled",
    CONF_API_ENDPOINT: 123,
    CONF_API_TOKEN: None,
  }
  mock_config_entry.options = raw_options  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_advanced_settings({  # noqa: E111
    "performance_mode": "balanced",
    "debug_logging": True,
    "data_retention_days": 200,
    "auto_backup": False,
    "experimental_features": True,
    CONF_EXTERNAL_INTEGRATIONS: False,
    CONF_API_ENDPOINT: " https://api.demo ",
    CONF_API_TOKEN: " token ",
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])  # noqa: E111
  assert notifications[CONF_QUIET_HOURS] is False  # noqa: E111
  assert notifications[CONF_QUIET_START] == "19:00:00"  # noqa: E111
  assert notifications[CONF_QUIET_END] == "07:00:00"  # noqa: E111
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 180  # noqa: E111
  assert notifications["priority_notifications"] is False  # noqa: E111
  assert notifications["mobile_notifications"] is True  # noqa: E111

  dog_options = cast(DogOptionsMap, options["dog_options"])  # noqa: E111
  assert set(dog_options) == {"buddy", "42"}  # noqa: E111

  buddy_entry = dog_options["buddy"]  # noqa: E111
  assert buddy_entry[DOG_ID_FIELD] == "buddy"  # noqa: E111
  buddy_modules = buddy_entry[DOG_MODULES_FIELD]  # noqa: E111
  assert buddy_modules[MODULE_FEEDING] is True  # noqa: E111
  assert buddy_modules[MODULE_WALK] is False  # noqa: E111

  legacy_entry = dog_options["42"]  # noqa: E111
  assert legacy_entry[DOG_ID_FIELD] == "42"  # noqa: E111
  legacy_modules = legacy_entry[DOG_MODULES_FIELD]  # noqa: E111
  assert legacy_modules[MODULE_HEALTH] is True  # noqa: E111

  assert options[CONF_API_ENDPOINT] == "https://api.demo"  # noqa: E111
  assert options[CONF_API_TOKEN] == "token"  # noqa: E111

  advanced = cast(AdvancedOptions, options["advanced_settings"])  # noqa: E111
  assert advanced["performance_mode"] == "balanced"  # noqa: E111
  assert advanced["debug_logging"] is True  # noqa: E111
  assert advanced["data_retention_days"] == 200  # noqa: E111
  assert advanced["auto_backup"] is False  # noqa: E111
  assert advanced["experimental_features"] is True  # noqa: E111
  assert advanced[CONF_EXTERNAL_INTEGRATIONS] is False  # noqa: E111
  assert advanced[CONF_API_ENDPOINT] == "https://api.demo"  # noqa: E111
  assert advanced[CONF_API_TOKEN] == "token"  # noqa: E111


@pytest.mark.asyncio
async def test_current_gps_options_normalises_legacy_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Legacy GPS options should be normalized through shared validators."""  # noqa: E111

  legacy_options = dict(mock_config_entry.options)  # noqa: E111
  legacy_options[CONF_GPS_UPDATE_INTERVAL] = "9999"  # noqa: E111
  legacy_options[CONF_GPS_ACCURACY_FILTER] = "0"  # noqa: E111
  legacy_options[CONF_GPS_DISTANCE_FILTER] = "bad-value"  # noqa: E111
  mock_config_entry.options = legacy_options  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  gps_options = flow._current_gps_options("test_dog")  # noqa: E111

  assert gps_options[CONF_GPS_UPDATE_INTERVAL] == 600  # noqa: E111
  assert gps_options[CONF_GPS_ACCURACY_FILTER] == 5.0  # noqa: E111
  assert gps_options[CONF_GPS_DISTANCE_FILTER] == 30.0  # noqa: E111
  assert gps_options[GPS_ENABLED_FIELD] is True  # noqa: E111
  assert gps_options[ROUTE_RECORDING_FIELD] is True  # noqa: E111
  assert gps_options[ROUTE_HISTORY_DAYS_FIELD] == 30  # noqa: E111
  assert gps_options[AUTO_TRACK_WALKS_FIELD] is True  # noqa: E111


@pytest.mark.asyncio
async def test_gps_settings_structured(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """GPS settings should be stored as typed payloads with validation."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_gps_settings({  # noqa: E111
    CONF_GPS_UPDATE_INTERVAL: "45",
    CONF_GPS_ACCURACY_FILTER: "12.5",
    CONF_GPS_DISTANCE_FILTER: 30,
    "gps_enabled": False,
    "route_recording": False,
    "route_history_days": "14",
    "auto_track_walks": True,
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  gps_options = cast(GPSOptions, options["gps_settings"])  # noqa: E111

  assert options[CONF_GPS_UPDATE_INTERVAL] == 45  # noqa: E111
  assert options[CONF_GPS_ACCURACY_FILTER] == 12.5  # noqa: E111
  assert options[CONF_GPS_DISTANCE_FILTER] == 30.0  # noqa: E111
  assert gps_options[CONF_GPS_UPDATE_INTERVAL] == 45  # noqa: E111
  assert gps_options[CONF_GPS_ACCURACY_FILTER] == 12.5  # noqa: E111
  assert gps_options[CONF_GPS_DISTANCE_FILTER] == 30.0  # noqa: E111
  assert gps_options["gps_enabled"] is False  # noqa: E111
  assert gps_options["route_recording"] is False  # noqa: E111
  assert gps_options["route_history_days"] == 14  # noqa: E111
  assert gps_options["auto_track_walks"] is True  # noqa: E111


@pytest.mark.asyncio
async def test_gps_settings_rejects_empty_accuracy(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """GPS settings should surface empty accuracy inputs."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_gps_settings({  # noqa: E111
    CONF_GPS_UPDATE_INTERVAL: 45,
    CONF_GPS_ACCURACY_FILTER: "",
    CONF_GPS_DISTANCE_FILTER: 30,
    "gps_enabled": True,
    "route_recording": True,
    "route_history_days": 14,
    "auto_track_walks": True,
  })

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["errors"][CONF_GPS_ACCURACY_FILTER] == "gps_accuracy_required"  # noqa: E111


@pytest.mark.asyncio
async def test_gps_settings_normalises_snapshot(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """GPS settings should reapply typed helpers for legacy payloads."""  # noqa: E111

  raw_options = dict(mock_config_entry.options)  # noqa: E111
  raw_options[CONF_NOTIFICATIONS] = {  # noqa: E111
    CONF_QUIET_HOURS: "1",
    CONF_QUIET_START: " 05:00:00 ",
    CONF_QUIET_END: None,
    CONF_REMINDER_REPEAT_MIN: "30",
    "priority_notifications": "off",
    "mobile_notifications": "TRUE",
  }
  raw_options["dog_options"] = {  # noqa: E111
    "max": {
      DOG_ID_FIELD: "max",
      DOG_MODULES_FIELD: {
        MODULE_GPS: "true",
        MODULE_HEALTH: "no",
      },
    }
  }
  mock_config_entry.options = raw_options  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_gps_settings({  # noqa: E111
    CONF_GPS_UPDATE_INTERVAL: 120,
    CONF_GPS_ACCURACY_FILTER: "8",
    CONF_GPS_DISTANCE_FILTER: "50",
    "gps_enabled": True,
    "route_recording": True,
    "route_history_days": "7",
    "auto_track_walks": "on",
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])  # noqa: E111
  assert notifications[CONF_QUIET_HOURS] is True  # noqa: E111
  assert notifications[CONF_QUIET_START] == "05:00:00"  # noqa: E111
  assert notifications[CONF_QUIET_END] == "07:00:00"  # noqa: E111
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 30  # noqa: E111
  assert notifications["priority_notifications"] is False  # noqa: E111
  assert notifications["mobile_notifications"] is True  # noqa: E111

  dog_options = cast(DogOptionsMap, options["dog_options"])  # noqa: E111
  assert set(dog_options) == {"max"}  # noqa: E111
  modules = dog_options["max"][DOG_MODULES_FIELD]  # noqa: E111
  assert modules[MODULE_GPS] is True  # noqa: E111
  assert modules[MODULE_HEALTH] is False  # noqa: E111

  gps_options = cast(GPSOptions, options["gps_settings"])  # noqa: E111
  assert gps_options[CONF_GPS_UPDATE_INTERVAL] == 120  # noqa: E111
  assert gps_options[CONF_GPS_ACCURACY_FILTER] == 8.0  # noqa: E111
  assert gps_options[CONF_GPS_DISTANCE_FILTER] == 50.0  # noqa: E111
  assert gps_options["gps_enabled"] is True  # noqa: E111
  assert gps_options["route_recording"] is True  # noqa: E111
  assert gps_options["route_history_days"] == 7  # noqa: E111
  assert gps_options["auto_track_walks"] is True  # noqa: E111


@pytest.mark.asyncio
async def test_dog_module_overrides_recorded(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Dog module configuration should persist typed overrides in options."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111
  flow.hass.config_entries.async_update_entry = Mock()  # noqa: E111

  dog_config = cast(DogConfigData, mock_config_entry.data[CONF_DOGS][0])  # noqa: E111
  flow._current_dog = dog_config  # noqa: E111

  result = await flow.async_step_configure_dog_modules({  # noqa: E111
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
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111
  flow.hass.config_entries.async_update_entry.assert_called_once()  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  dog_options = cast(DogOptionsMap, options["dog_options"])  # noqa: E111

  dog_entry = dog_options[dog_config["dog_id"]]  # noqa: E111
  modules = dog_entry["modules"]  # noqa: E111

  assert modules[MODULE_GPS] is True  # noqa: E111
  assert modules[MODULE_WALK] is True  # noqa: E111
  assert modules[MODULE_HEALTH] is True  # noqa: E111
  assert modules.get("notifications") is False  # noqa: E111
  assert modules.get("grooming") is True  # noqa: E111


def test_module_description_placeholders_localize_grooming(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Module summary placeholders should localize grooming descriptions."""  # noqa: E111

  hass.config.language = "de"  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111
  flow._current_dog = flow._dogs[0]  # noqa: E111

  modules = flow._current_dog.setdefault("modules", {})  # noqa: E111
  modules[MODULE_GROOMING] = True  # noqa: E111

  placeholders = flow._get_module_description_placeholders()  # noqa: E111
  enabled_summary = placeholders["enabled_modules"]  # noqa: E111

  assert "Pflegeplan und Tracking" in enabled_summary  # noqa: E111
  assert "• Pflege:" in enabled_summary  # noqa: E111


@pytest.mark.asyncio
async def test_configure_door_sensor_normalises_and_persists(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Door sensor configuration should normalise payloads and persist updates."""  # noqa: E111

  hass.states.async_set(  # noqa: E111
    "binary_sensor.front_door",
    "off",
    {"device_class": "door", "friendly_name": "Front Door"},
  )

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111
  flow.hass.config_entries.async_update_entry = Mock()  # noqa: E111
  flow._current_dog = flow._dogs[0]  # noqa: E111
  dog_id = flow._current_dog[DOG_ID_FIELD]  # noqa: E111

  data_manager = Mock()  # noqa: E111
  data_manager.async_update_dog_data = AsyncMock(return_value=True)  # noqa: E111
  runtime = Mock()  # noqa: E111
  runtime.data_manager = data_manager  # noqa: E111

  user_input = {  # noqa: E111
    CONF_DOOR_SENSOR: "binary_sensor.front_door  ",
    "walk_detection_timeout": " 180 ",
    "minimum_walk_duration": 75,
    "maximum_walk_duration": "7200",
    "door_closed_delay": "45",
    "require_confirmation": False,
    "auto_end_walks": True,
    "confidence_threshold": "0.85",
  }

  with (  # noqa: E111
    patch(
      "custom_components.pawcontrol.options_flow_support.get_runtime_data",
      return_value=runtime,
    ),
    patch(
      "custom_components.pawcontrol.options_flow_support.require_runtime_data",
      return_value=runtime,
    ),
  ):
    result = await flow.async_step_configure_door_sensor(user_input)

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  flow.hass.config_entries.async_update_entry.assert_called_once()  # noqa: E111

  update_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]  # noqa: E111
  updated_dog = update_data[CONF_DOGS][0]  # noqa: E111
  assert updated_dog[CONF_DOOR_SENSOR] == "binary_sensor.front_door"  # noqa: E111

  expected_settings = {  # noqa: E111
    "walk_detection_timeout": 180,
    "minimum_walk_duration": 75,
    "maximum_walk_duration": 7200,
    "door_closed_delay": 45,
    "require_confirmation": False,
    "auto_end_walks": True,
    "confidence_threshold": 0.85,
  }

  assert updated_dog[CONF_DOOR_SENSOR_SETTINGS] == expected_settings  # noqa: E111
  assert flow._current_dog[CONF_DOOR_SENSOR] == "binary_sensor.front_door"  # noqa: E111

  data_manager.async_update_dog_data.assert_awaited_once_with(  # noqa: E111
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
  """Removing a door sensor should clear stored overrides."""  # noqa: E111

  initial_dog = mock_config_entry.data[CONF_DOGS][0]  # noqa: E111
  initial_dog[CONF_DOOR_SENSOR] = "binary_sensor.back_door"  # noqa: E111
  initial_dog[CONF_DOOR_SENSOR_SETTINGS] = {  # noqa: E111
    "walk_detection_timeout": 240,
    "minimum_walk_duration": 90,
    "maximum_walk_duration": 3600,
    "door_closed_delay": 30,
    "require_confirmation": True,
    "auto_end_walks": False,
    "confidence_threshold": 0.7,
  }

  hass.states.async_set(  # noqa: E111
    "binary_sensor.back_door",
    "on",
    {"device_class": "door", "friendly_name": "Back Door"},
  )

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111
  flow.hass.config_entries.async_update_entry = Mock()  # noqa: E111
  flow._current_dog = flow._dogs[0]  # noqa: E111
  dog_id = flow._current_dog[DOG_ID_FIELD]  # noqa: E111

  data_manager = Mock()  # noqa: E111
  data_manager.async_update_dog_data = AsyncMock(return_value=True)  # noqa: E111
  runtime = Mock()  # noqa: E111
  runtime.data_manager = data_manager  # noqa: E111

  with (  # noqa: E111
    patch(
      "custom_components.pawcontrol.options_flow_support.get_runtime_data",
      return_value=runtime,
    ),
    patch(
      "custom_components.pawcontrol.options_flow_support.require_runtime_data",
      return_value=runtime,
    ),
  ):
    result = await flow.async_step_configure_door_sensor({CONF_DOOR_SENSOR: ""})

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  flow.hass.config_entries.async_update_entry.assert_called_once()  # noqa: E111

  update_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]  # noqa: E111
  updated_dog = update_data[CONF_DOGS][0]  # noqa: E111
  assert CONF_DOOR_SENSOR not in updated_dog  # noqa: E111
  assert CONF_DOOR_SENSOR_SETTINGS not in updated_dog  # noqa: E111
  assert CONF_DOOR_SENSOR not in flow._current_dog  # noqa: E111
  assert CONF_DOOR_SENSOR_SETTINGS not in flow._current_dog  # noqa: E111

  data_manager.async_update_dog_data.assert_awaited_once_with(  # noqa: E111
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
  """Persistence failures should raise a repair issue and capture telemetry."""  # noqa: E111

  hass.states.async_set(  # noqa: E111
    "binary_sensor.front_door",
    "off",
    {"device_class": "door", "friendly_name": "Front Door"},
  )

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111
  flow.hass.config_entries.async_update_entry = Mock()  # noqa: E111
  flow._current_dog = flow._dogs[0]  # noqa: E111
  dog_id = flow._current_dog[DOG_ID_FIELD]  # noqa: E111

  data_manager = SimpleNamespace(  # noqa: E111
    async_update_dog_data=AsyncMock(side_effect=RuntimeError("storage offline"))
  )
  runtime = SimpleNamespace(  # noqa: E111
    data_manager=data_manager,
    performance_stats={},
    error_history=cast(list[RuntimeErrorHistoryEntry], []),
  )

  user_input = {  # noqa: E111
    CONF_DOOR_SENSOR: "binary_sensor.front_door",
    "walk_detection_timeout": 60,
    "minimum_walk_duration": 90,
    "maximum_walk_duration": 3600,
    "door_closed_delay": 30,
    "require_confirmation": True,
    "auto_end_walks": False,
    "confidence_threshold": 0.75,
  }

  failure_timestamp = datetime(2024, 1, 1, tzinfo=UTC)  # noqa: E111

  with (  # noqa: E111
    patch(
      "custom_components.pawcontrol.options_flow_support.get_runtime_data",
      return_value=runtime,
    ),
    patch(
      "custom_components.pawcontrol.options_flow_support.require_runtime_data",
      return_value=runtime,
    ),
    patch(
      "custom_components.pawcontrol.options_flow_support.async_create_issue",
      new_callable=AsyncMock,
    ) as create_issue,
    patch(
      "custom_components.pawcontrol.telemetry.dt_util.utcnow",
      return_value=failure_timestamp,
    ),
  ):
    result = await flow.async_step_configure_door_sensor(user_input)

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["errors"]["base"] == "door_sensor_update_failed"  # noqa: E111

  flow.hass.config_entries.async_update_entry.assert_not_called()  # noqa: E111
  data_manager.async_update_dog_data.assert_awaited_once_with(dog_id, ANY)  # noqa: E111

  create_issue.assert_awaited_once()  # noqa: E111
  args, kwargs = create_issue.call_args  # noqa: E111
  assert args[2] == f"{mock_config_entry.entry_id}_door_sensor_{dog_id}"  # noqa: E111
  assert args[3] == "door_sensor_persistence_failure"  # noqa: E111
  payload = args[4]  # noqa: E111
  assert payload["dog_id"] == dog_id  # noqa: E111
  assert payload["door_sensor"] == "binary_sensor.front_door"  # noqa: E111
  assert payload["timestamp"] == failure_timestamp.isoformat()  # noqa: E111
  assert kwargs["severity"] == "error"  # noqa: E111

  performance_stats = runtime.performance_stats  # noqa: E111
  assert performance_stats["door_sensor_failure_count"] == 1  # noqa: E111
  failures = performance_stats["door_sensor_failures"]  # noqa: E111
  assert failures[0]["dog_id"] == dog_id  # noqa: E111
  assert failures[0]["error"] == "storage offline"  # noqa: E111
  assert runtime.error_history[-1]["source"] == "door_sensor_persistence"  # noqa: E111


@pytest.mark.asyncio
async def test_configure_door_sensor_runtime_cache_unavailable(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Door sensor updates should fail when runtime data is missing."""  # noqa: E111

  hass.states.async_set(  # noqa: E111
    "binary_sensor.front_door",
    "off",
    {"device_class": "door", "friendly_name": "Front Door"},
  )

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111
  flow.hass.config_entries.async_update_entry = Mock()  # noqa: E111
  flow._current_dog = flow._dogs[0]  # noqa: E111
  dog_id = flow._current_dog[DOG_ID_FIELD]  # noqa: E111

  user_input = {  # noqa: E111
    CONF_DOOR_SENSOR: "binary_sensor.front_door",
    "walk_detection_timeout": 60,
    "minimum_walk_duration": 90,
    "maximum_walk_duration": 3600,
    "door_closed_delay": 30,
    "require_confirmation": True,
    "auto_end_walks": False,
    "confidence_threshold": 0.75,
  }

  with (  # noqa: E111
    patch(
      "custom_components.pawcontrol.options_flow_support.require_runtime_data",
      side_effect=RuntimeDataUnavailableError("store unavailable"),
    ),
    patch(
      "custom_components.pawcontrol.options_flow_support.async_create_issue",
      new_callable=AsyncMock,
    ) as create_issue,
  ):
    result = await flow.async_step_configure_door_sensor(user_input)

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["errors"]["base"] == "runtime_cache_unavailable"  # noqa: E111
  flow.hass.config_entries.async_update_entry.assert_not_called()  # noqa: E111
  create_issue.assert_not_called()  # noqa: E111
  assert flow._current_dog[DOG_ID_FIELD] == dog_id  # noqa: E111


@pytest.mark.asyncio
async def test_add_new_dog_normalises_config(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Adding a dog should persist typed configuration data."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111
  flow.hass.config_entries.async_update_entry = Mock()  # noqa: E111

  result = await flow.async_step_add_new_dog({  # noqa: E111
    CONF_DOG_ID: "Nova Pup",
    CONF_DOG_NAME: "Nova",
    CONF_DOG_BREED: "Border Collie",
    CONF_DOG_AGE: 5,
    CONF_DOG_WEIGHT: 19.5,
    CONF_DOG_SIZE: "medium",
  })

  assert result["type"] == FlowResultType.MENU  # noqa: E111
  flow.hass.config_entries.async_update_entry.assert_called_once()  # noqa: E111

  _, kwargs = flow.hass.config_entries.async_update_entry.call_args  # noqa: E111
  updated_data = kwargs.get("data")  # noqa: E111
  assert isinstance(updated_data, dict)  # noqa: E111

  dogs = updated_data[CONF_DOGS]  # noqa: E111
  assert isinstance(dogs, list)  # noqa: E111
  new_dog = dogs[-1]  # noqa: E111

  assert new_dog[DOG_ID_FIELD] == "nova_pup"  # noqa: E111
  assert new_dog[DOG_NAME_FIELD] == "Nova"  # noqa: E111
  assert new_dog[DOG_WEIGHT_FIELD] == 19.5  # noqa: E111

  modules = new_dog[DOG_MODULES_FIELD]  # noqa: E111
  assert modules[MODULE_FEEDING] is True  # noqa: E111
  assert modules[MODULE_WALK] is True  # noqa: E111
  assert modules["dashboard"] is True  # noqa: E111

  assert flow._dogs[-1][DOG_NAME_FIELD] == "Nova"  # noqa: E111


@pytest.mark.asyncio
async def test_edit_dog_updates_config(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Editing a dog should write back typed configuration changes."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111
  flow.hass.config_entries.async_update_entry = Mock()  # noqa: E111

  flow._current_dog = flow._dogs[0]  # noqa: E111

  result = await flow.async_step_edit_dog({  # noqa: E111
    CONF_DOG_NAME: "Buddy II",
    CONF_DOG_BREED: "Retriever",
    CONF_DOG_AGE: 4,
    CONF_DOG_WEIGHT: 32.5,
    CONF_DOG_SIZE: "large",
  })

  assert result["type"] == FlowResultType.MENU  # noqa: E111
  flow.hass.config_entries.async_update_entry.assert_called_once()  # noqa: E111

  _, kwargs = flow.hass.config_entries.async_update_entry.call_args  # noqa: E111
  updated_data = kwargs.get("data")  # noqa: E111
  assert isinstance(updated_data, dict)  # noqa: E111

  updated_dog = updated_data[CONF_DOGS][0]  # noqa: E111
  assert updated_dog[DOG_NAME_FIELD] == "Buddy II"  # noqa: E111
  assert updated_dog[DOG_WEIGHT_FIELD] == 32.5  # noqa: E111
  assert updated_dog.get(DOG_ID_FIELD)  # noqa: E111

  assert flow._dogs[0][DOG_NAME_FIELD] == "Buddy II"  # noqa: E111


@pytest.mark.asyncio
async def test_remove_dog_normalises_snapshot(
  hass: HomeAssistant,
  mock_config_entry: ConfigEntry,
  mock_multi_dog_config: list[DogConfigData],
) -> None:
  """Removing a dog should reapply typed options before saving."""  # noqa: E111

  mock_config_entry.data = {CONF_DOGS: mock_multi_dog_config}  # noqa: E111

  raw_options = dict(mock_config_entry.options)  # noqa: E111
  raw_options[CONF_NOTIFICATIONS] = {  # noqa: E111
    CONF_QUIET_HOURS: "true",
    CONF_QUIET_START: " 05:30:00 ",
    CONF_QUIET_END: None,
    CONF_REMINDER_REPEAT_MIN: "120",
    "priority_notifications": "yes",
    "mobile_notifications": 0,
  }
  raw_options["dog_options"] = {  # noqa: E111
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
  mock_config_entry.options = raw_options  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  hass.config_entries.async_update_entry = Mock()  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  result = await flow.async_step_select_dog_to_remove({  # noqa: E111
    "dog_id": "max",
    "confirm_remove": True,
  })

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111
  hass.config_entries.async_update_entry.assert_called_once()  # noqa: E111

  _, update_kwargs = hass.config_entries.async_update_entry.call_args  # noqa: E111
  updated_data = cast(ConfigEntryDataPayload, update_kwargs.get("data"))  # noqa: E111
  assert isinstance(updated_data, dict)  # noqa: E111

  dogs = cast(list[DogConfigData], updated_data[CONF_DOGS])  # noqa: E111
  assert len(dogs) == 1  # noqa: E111
  assert dogs[0][DOG_ID_FIELD] == "buddy"  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111

  notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])  # noqa: E111
  assert notifications[CONF_QUIET_HOURS] is True  # noqa: E111
  assert notifications[CONF_QUIET_START] == "05:30:00"  # noqa: E111
  assert notifications[CONF_QUIET_END] == "07:00:00"  # noqa: E111
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 120  # noqa: E111
  assert notifications["priority_notifications"] is True  # noqa: E111
  assert notifications["mobile_notifications"] is False  # noqa: E111

  dog_options = cast(DogOptionsMap, options["dog_options"])  # noqa: E111
  assert set(dog_options) == {"buddy"}  # noqa: E111

  buddy_entry = dog_options["buddy"]  # noqa: E111
  assert buddy_entry[DOG_ID_FIELD] == "buddy"  # noqa: E111
  buddy_modules = buddy_entry[DOG_MODULES_FIELD]  # noqa: E111
  assert buddy_modules[MODULE_FEEDING] is True  # noqa: E111
  assert buddy_modules[MODULE_HEALTH] is True  # noqa: E111


@pytest.mark.asyncio
async def test_import_export_export_flow(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Export step should surface a JSON payload with current settings."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  menu = await flow.async_step_import_export()  # noqa: E111
  assert menu["type"] == FlowResultType.FORM  # noqa: E111
  assert menu["step_id"] == "import_export"  # noqa: E111

  export_form = await flow.async_step_import_export({"action": "export"})  # noqa: E111
  assert export_form["type"] == FlowResultType.FORM  # noqa: E111
  assert export_form["step_id"] == "import_export_export"  # noqa: E111

  export_blob = export_form["description_placeholders"]["export_blob"]  # noqa: E111
  payload = cast(OptionsExportPayload, json.loads(export_blob))  # noqa: E111

  assert payload["version"] == 1  # noqa: E111
  assert (  # noqa: E111
    payload["options"]["entity_profile"] == mock_config_entry.options["entity_profile"]
  )
  assert payload["dogs"][0]["dog_id"] == mock_config_entry.data[CONF_DOGS][0]["dog_id"]  # noqa: E111

  finished = await flow.async_step_import_export_export({})  # noqa: E111
  assert finished["type"] == FlowResultType.MENU  # noqa: E111
  assert finished["step_id"] == "init"  # noqa: E111


@pytest.mark.asyncio
async def test_import_export_import_flow(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Import step should apply settings and update config entry data."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111
  flow.hass.config_entries.async_update_entry = Mock()  # noqa: E111

  baseline = flow._build_export_payload()  # noqa: E111
  baseline["options"]["entity_profile"] = "advanced"  # noqa: E111
  baseline["options"]["external_integrations"] = True  # noqa: E111
  baseline["dogs"][0]["dog_name"] = "Imported Pup"  # noqa: E111
  baseline["dogs"][0]["modules"] = {  # noqa: E111
    MODULE_GPS: True,
    MODULE_HEALTH: False,
  }

  payload_blob = json.dumps(baseline)  # noqa: E111

  import_form = await flow.async_step_import_export({"action": "import"})  # noqa: E111
  assert import_form["type"] == FlowResultType.FORM  # noqa: E111
  assert import_form["step_id"] == "import_export_import"  # noqa: E111

  result = await flow.async_step_import_export_import({"payload": payload_blob})  # noqa: E111

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111
  flow.hass.config_entries.async_update_entry.assert_called_once()  # noqa: E111

  options = cast(PawControlOptionsData, result["data"])  # noqa: E111
  assert options["entity_profile"] == "advanced"  # noqa: E111
  assert options["external_integrations"] is True  # noqa: E111

  update_call = flow.hass.config_entries.async_update_entry.call_args  # noqa: E111
  assert update_call is not None  # noqa: E111
  update_kwargs = update_call.kwargs  # noqa: E111
  assert update_kwargs["data"][CONF_DOGS][0]["dog_name"] == "Imported Pup"  # noqa: E111


def test_export_payload_normalises_legacy_options(
  mock_config_entry: ConfigEntry,
) -> None:
  """Exported payload should surface typed notifications and dog options."""  # noqa: E111

  raw_options = dict(mock_config_entry.options)  # noqa: E111
  raw_options[CONF_NOTIFICATIONS] = {  # noqa: E111
    CONF_QUIET_HOURS: "no",
    CONF_QUIET_START: " 18:45:00 ",
    CONF_QUIET_END: None,
    CONF_REMINDER_REPEAT_MIN: "15",
    "priority_notifications": "YES",
    "mobile_notifications": 0,
  }
  raw_options["dog_options"] = {  # noqa: E111
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
  mock_config_entry.options = raw_options  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  payload = flow._build_export_payload()  # noqa: E111

  notifications = cast(NotificationOptions, payload["options"][CONF_NOTIFICATIONS])  # noqa: E111
  assert notifications[CONF_QUIET_HOURS] is False  # noqa: E111
  assert notifications[CONF_QUIET_START] == "18:45:00"  # noqa: E111
  assert notifications[CONF_QUIET_END] == "07:00:00"  # noqa: E111
  assert notifications[CONF_REMINDER_REPEAT_MIN] == 15  # noqa: E111
  assert notifications["priority_notifications"] is True  # noqa: E111
  assert notifications["mobile_notifications"] is False  # noqa: E111

  dog_options = cast(DogOptionsMap, payload["options"]["dog_options"])  # noqa: E111
  assert set(dog_options) == {"buddy", "99"}  # noqa: E111

  buddy_modules = dog_options["buddy"][DOG_MODULES_FIELD]  # noqa: E111
  assert buddy_modules[MODULE_WALK] is True  # noqa: E111
  assert buddy_modules[MODULE_FEEDING] is True  # noqa: E111

  legacy_entry = dog_options["99"]  # noqa: E111
  assert legacy_entry[DOG_ID_FIELD] == "99"  # noqa: E111
  assert legacy_entry[DOG_MODULES_FIELD][MODULE_HEALTH] is True  # noqa: E111


@pytest.mark.asyncio
async def test_import_export_import_duplicate_dog(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Duplicate dog IDs should surface a dedicated error code."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  duplicate_payload = flow._build_export_payload()  # noqa: E111
  duplicate_payload["dogs"].append(dict(duplicate_payload["dogs"][0]))  # noqa: E111
  payload_blob = json.dumps(duplicate_payload)  # noqa: E111

  await flow.async_step_import_export({"action": "import"})  # noqa: E111
  result = await flow.async_step_import_export_import({"payload": payload_blob})  # noqa: E111

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["errors"] == {"payload": "dog_duplicate"}  # noqa: E111


@pytest.mark.asyncio
async def test_import_export_import_invalid_modules(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Non-mapping modules payloads should be rejected during import."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  payload = flow._build_export_payload()  # noqa: E111
  payload["dogs"][0][CONF_MODULES] = ["not", "valid"]  # noqa: E111
  payload_blob = json.dumps(payload)  # noqa: E111

  await flow.async_step_import_export({"action": "import"})  # noqa: E111
  result = await flow.async_step_import_export_import({"payload": payload_blob})  # noqa: E111

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["errors"] == {"payload": "dog_invalid_modules"}  # noqa: E111


def test_validate_import_payload_sanitises_modules(
  mock_config_entry: ConfigEntry,
) -> None:
  """Dog module flags should be coerced to booleans when importing."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  payload = flow._build_export_payload()  # noqa: E111
  payload["dogs"][0][CONF_MODULES] = {"gps": "yes", "health": 0}  # noqa: E111

  validated = flow._validate_import_payload(payload)  # noqa: E111

  modules = cast(DogConfigData, validated["dogs"][0])[CONF_MODULES]  # noqa: E111
  assert modules["gps"] is True  # noqa: E111
  assert modules["health"] is False  # noqa: E111


@pytest.mark.asyncio
async def test_import_export_import_unsupported_version(
  hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
  """Unsupported export versions should surface a specific error."""  # noqa: E111

  flow = PawControlOptionsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.initialize_from_config_entry(mock_config_entry)  # noqa: E111

  payload = flow._build_export_payload()  # noqa: E111
  payload["version"] = 99  # type: ignore[assignment]  # noqa: E111
  payload_blob = json.dumps(payload)  # noqa: E111

  await flow.async_step_import_export({"action": "import"})  # noqa: E111
  result = await flow.async_step_import_export_import({"payload": payload_blob})  # noqa: E111

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["errors"] == {"payload": "unsupported_version"}  # noqa: E111
