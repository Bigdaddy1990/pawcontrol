from __future__ import annotations

import sys
from datetime import UTC, datetime, timezone
from types import ModuleType

from tests.helpers import install_homeassistant_stubs


def _install_options_flow_dependencies() -> None:
  """Install Home Assistant stubs required to import the options flow."""

  install_homeassistant_stubs()
  const_module = sys.modules["homeassistant.const"]
  const_module.CONF_ALIAS = "alias"
  const_module.CONF_DEFAULT = "default"
  const_module.CONF_DESCRIPTION = "description"
  const_module.CONF_NAME = "name"
  const_module.CONF_SEQUENCE = "sequence"
  components_module = sys.modules["homeassistant.components"]

  script_module = ModuleType("homeassistant.components.script")
  script_module.DOMAIN = "script"
  script_module.ScriptEntity = object
  components_module.script = script_module
  sys.modules["homeassistant.components.script"] = script_module

  config_module = ModuleType("homeassistant.components.script.config")
  config_module.SCRIPT_ENTITY_SCHEMA = {}
  sys.modules["homeassistant.components.script.config"] = config_module

  const_module = ModuleType("homeassistant.components.script.const")
  const_module.CONF_FIELDS = "fields"
  const_module.CONF_TRACE = "trace"
  sys.modules["homeassistant.components.script.const"] = const_module

  entity_component_module = ModuleType(
    "homeassistant.helpers.entity_component",
  )
  entity_component_module.EntityComponent = object
  sys.modules["homeassistant.helpers.entity_component"] = entity_component_module

  typing_module = ModuleType("homeassistant.helpers.typing")
  typing_module.ConfigType = dict[str, object]
  sys.modules["homeassistant.helpers.typing"] = typing_module
  util_module = sys.modules["homeassistant.util"]
  util_module.slugify = lambda value: str(value)


def test_notification_settings_payload_coercion() -> None:
  """Ensure notification settings normalise quiet hours input."""

  _install_options_flow_dependencies()
  from custom_components.pawcontrol.options_flow import PawControlOptionsFlow

  current = {
    "quiet_hours": True,
    "quiet_start": "22:00:00",
    "quiet_end": "07:00:00",
    "reminder_repeat_min": 20,
    "priority_notifications": True,
    "mobile_notifications": True,
  }
  user_input = {
    "quiet_hours": "false",
    "quiet_start": datetime(2024, 7, 1, 8, 30, tzinfo=UTC),
    "quiet_end": 0,  # falls back to current default
    "reminder_repeat_min": "15",
    "priority_notifications": None,
  }

  settings = PawControlOptionsFlow._build_notification_settings_payload(
    user_input,
    current,
  )

  assert settings["quiet_hours"] is False
  assert settings["quiet_start"].startswith("2024-07-01T08:30:00")
  assert settings["quiet_end"] == "07:00:00"
  assert settings["reminder_repeat_min"] == 15
  assert settings["priority_notifications"] is True
  assert settings["mobile_notifications"] is True


def test_gps_settings_payload_clamps_ranges() -> None:
  """Ensure GPS options normalization clamps and defaults values."""

  _install_options_flow_dependencies()
  from custom_components.pawcontrol.flow_helpers import coerce_bool
  from custom_components.pawcontrol.flows.gps import GPSOptionsNormalizerMixin
  from custom_components.pawcontrol.types import (
    AUTO_TRACK_WALKS_FIELD,
    GPS_ACCURACY_FILTER_FIELD,
    GPS_DISTANCE_FILTER_FIELD,
    GPS_ENABLED_FIELD,
    GPS_UPDATE_INTERVAL_FIELD,
    ROUTE_HISTORY_DAYS_FIELD,
    ROUTE_RECORDING_FIELD,
  )
  from custom_components.pawcontrol.const import DEFAULT_GPS_UPDATE_INTERVAL

  class _GPSNormalizer(GPSOptionsNormalizerMixin):
    @staticmethod
    def _coerce_bool(value: object, default: bool) -> bool:
      return coerce_bool(value, default=default)

  normalizer = _GPSNormalizer()
  payload = normalizer._normalise_gps_settings(
    {
      GPS_ENABLED_FIELD: "false",
      GPS_UPDATE_INTERVAL_FIELD: "bad",
      GPS_ACCURACY_FILTER_FIELD: "800",
      GPS_DISTANCE_FILTER_FIELD: "-5",
      ROUTE_RECORDING_FIELD: None,
      ROUTE_HISTORY_DAYS_FIELD: "400",
      AUTO_TRACK_WALKS_FIELD: "true",
    },
  )

  assert payload[GPS_ENABLED_FIELD] is False
  assert payload[GPS_UPDATE_INTERVAL_FIELD] == DEFAULT_GPS_UPDATE_INTERVAL
  assert payload[GPS_ACCURACY_FILTER_FIELD] == 500.0
  assert payload[GPS_DISTANCE_FILTER_FIELD] == 1.0
  assert payload[ROUTE_RECORDING_FIELD] is True
  assert payload[ROUTE_HISTORY_DAYS_FIELD] == 365
  assert payload[AUTO_TRACK_WALKS_FIELD] is True


def test_build_notifications_schema_defaults() -> None:
  """Ensure notification schema defaults match current settings."""

  _install_options_flow_dependencies()
  from custom_components.pawcontrol.flows.notifications_schemas import (
    build_notifications_schema,
  )
  from custom_components.pawcontrol.types import (
    NOTIFICATION_MOBILE_FIELD,
    NOTIFICATION_PRIORITY_FIELD,
    NOTIFICATION_QUIET_END_FIELD,
    NOTIFICATION_QUIET_HOURS_FIELD,
    NOTIFICATION_QUIET_START_FIELD,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
  )

  current = {
    NOTIFICATION_QUIET_HOURS_FIELD: False,
    NOTIFICATION_QUIET_START_FIELD: "21:30:00",
    NOTIFICATION_QUIET_END_FIELD: "06:15:00",
    NOTIFICATION_REMINDER_REPEAT_FIELD: 25,
    NOTIFICATION_PRIORITY_FIELD: True,
    NOTIFICATION_MOBILE_FIELD: False,
  }

  schema = build_notifications_schema(current)
  validated = schema({})

  assert validated[NOTIFICATION_QUIET_HOURS_FIELD] is False
  assert validated[NOTIFICATION_QUIET_START_FIELD] == "21:30:00"
  assert validated[NOTIFICATION_QUIET_END_FIELD] == "06:15:00"
  assert validated[NOTIFICATION_REMINDER_REPEAT_FIELD] == 25
  assert validated[NOTIFICATION_PRIORITY_FIELD] is True
  assert validated[NOTIFICATION_MOBILE_FIELD] is False


def test_ensure_notification_options_coerces_payload() -> None:
  """Ensure notification options parsing normalizes mixed payload values."""

  from custom_components.pawcontrol.types import (
    DEFAULT_NOTIFICATION_OPTIONS,
    NOTIFICATION_MOBILE_FIELD,
    NOTIFICATION_PRIORITY_FIELD,
    NOTIFICATION_QUIET_END_FIELD,
    NOTIFICATION_QUIET_HOURS_FIELD,
    NOTIFICATION_QUIET_START_FIELD,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
    ensure_notification_options,
  )

  payload = {
    "quiet_hours": "true",
    "quiet_start": "  ",
    "quiet_end": "08:00:00",
    "reminder_repeat_min": "45",
    "priority_notifications": 0,
  }

  options = ensure_notification_options(
    payload,
    defaults=DEFAULT_NOTIFICATION_OPTIONS,
  )

  assert options[NOTIFICATION_QUIET_HOURS_FIELD] is True
  assert options[NOTIFICATION_QUIET_START_FIELD] == "22:00:00"
  assert options[NOTIFICATION_QUIET_END_FIELD] == "08:00:00"
  assert options[NOTIFICATION_REMINDER_REPEAT_FIELD] == 45
  assert options[NOTIFICATION_PRIORITY_FIELD] is False
  assert options[NOTIFICATION_MOBILE_FIELD] is True
