from datetime import UTC, datetime, timezone
import sys
from types import ModuleType

from tests.helpers import install_homeassistant_stubs


def _install_options_flow_dependencies() -> None:
  """Install Home Assistant stubs required to import the options flow."""  # noqa: E111

  install_homeassistant_stubs()  # noqa: E111
  const_module = sys.modules["homeassistant.const"]  # noqa: E111
  const_module.CONF_ALIAS = "alias"  # noqa: E111
  const_module.CONF_DEFAULT = "default"  # noqa: E111
  const_module.CONF_DESCRIPTION = "description"  # noqa: E111
  const_module.CONF_NAME = "name"  # noqa: E111
  const_module.CONF_SEQUENCE = "sequence"  # noqa: E111
  components_module = sys.modules["homeassistant.components"]  # noqa: E111

  script_module = ModuleType("homeassistant.components.script")  # noqa: E111
  script_module.DOMAIN = "script"  # noqa: E111
  script_module.ScriptEntity = object  # noqa: E111
  components_module.script = script_module  # noqa: E111
  sys.modules["homeassistant.components.script"] = script_module  # noqa: E111

  config_module = ModuleType("homeassistant.components.script.config")  # noqa: E111
  config_module.SCRIPT_ENTITY_SCHEMA = {}  # noqa: E111
  sys.modules["homeassistant.components.script.config"] = config_module  # noqa: E111

  const_module = ModuleType("homeassistant.components.script.const")  # noqa: E111
  const_module.CONF_FIELDS = "fields"  # noqa: E111
  const_module.CONF_TRACE = "trace"  # noqa: E111
  sys.modules["homeassistant.components.script.const"] = const_module  # noqa: E111

  entity_component_module = ModuleType(  # noqa: E111
    "homeassistant.helpers.entity_component",
  )
  entity_component_module.EntityComponent = object  # noqa: E111
  sys.modules["homeassistant.helpers.entity_component"] = entity_component_module  # noqa: E111

  typing_module = ModuleType("homeassistant.helpers.typing")  # noqa: E111
  typing_module.ConfigType = dict[str, object]  # noqa: E111
  sys.modules["homeassistant.helpers.typing"] = typing_module  # noqa: E111
  util_module = sys.modules["homeassistant.util"]  # noqa: E111
  util_module.slugify = lambda value: str(value)  # noqa: E111


def test_notification_settings_payload_coercion() -> None:
  """Ensure notification settings normalise quiet hours input."""  # noqa: E111

  _install_options_flow_dependencies()  # noqa: E111
  from custom_components.pawcontrol.options_flow import PawControlOptionsFlow

  current = {  # noqa: E111
    "quiet_hours": True,
    "quiet_start": "22:00:00",
    "quiet_end": "07:00:00",
    "reminder_repeat_min": 20,
    "priority_notifications": True,
    "mobile_notifications": True,
  }
  user_input = {  # noqa: E111
    "quiet_hours": "false",
    "quiet_start": datetime(2024, 7, 1, 8, 30, tzinfo=UTC),
    "quiet_end": 0,  # falls back to current default
    "reminder_repeat_min": "15",
    "priority_notifications": None,
  }

  settings = PawControlOptionsFlow._build_notification_settings_payload(  # noqa: E111
    user_input,
    current,
  )

  assert settings["quiet_hours"] is False  # noqa: E111
  assert settings["quiet_start"].startswith("2024-07-01T08:30:00")  # noqa: E111
  assert settings["quiet_end"] == "07:00:00"  # noqa: E111
  assert settings["reminder_repeat_min"] == 15  # noqa: E111
  assert settings["priority_notifications"] is True  # noqa: E111
  assert settings["mobile_notifications"] is True  # noqa: E111


def test_gps_settings_payload_clamps_ranges() -> None:
  """Ensure GPS options normalization clamps and defaults values."""  # noqa: E111

  _install_options_flow_dependencies()  # noqa: E111
  from custom_components.pawcontrol.const import DEFAULT_GPS_UPDATE_INTERVAL
  from custom_components.pawcontrol.flow_helpers import coerce_bool  # noqa: E111
  from custom_components.pawcontrol.flow_steps.gps import GPSOptionsNormalizerMixin
  from custom_components.pawcontrol.types import (  # noqa: E111
    AUTO_TRACK_WALKS_FIELD,
    GPS_ACCURACY_FILTER_FIELD,
    GPS_DISTANCE_FILTER_FIELD,
    GPS_ENABLED_FIELD,
    GPS_UPDATE_INTERVAL_FIELD,
    ROUTE_HISTORY_DAYS_FIELD,
    ROUTE_RECORDING_FIELD,
  )

  class _GPSNormalizer(GPSOptionsNormalizerMixin):  # noqa: E111
    @staticmethod
    def _coerce_bool(value: object, default: bool) -> bool:
      return coerce_bool(value, default=default)  # noqa: E111

  normalizer = _GPSNormalizer()  # noqa: E111
  payload = normalizer._normalise_gps_settings(  # noqa: E111
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

  assert payload[GPS_ENABLED_FIELD] is False  # noqa: E111
  assert payload[GPS_UPDATE_INTERVAL_FIELD] == DEFAULT_GPS_UPDATE_INTERVAL  # noqa: E111
  assert payload[GPS_ACCURACY_FILTER_FIELD] == 500.0  # noqa: E111
  assert payload[GPS_DISTANCE_FILTER_FIELD] == 1.0  # noqa: E111
  assert payload[ROUTE_RECORDING_FIELD] is True  # noqa: E111
  assert payload[ROUTE_HISTORY_DAYS_FIELD] == 365  # noqa: E111
  assert payload[AUTO_TRACK_WALKS_FIELD] is True  # noqa: E111


def test_build_notifications_schema_defaults() -> None:
  """Ensure notification schema defaults match current settings."""  # noqa: E111

  _install_options_flow_dependencies()  # noqa: E111
  from custom_components.pawcontrol.flow_steps.notifications_schemas import (  # noqa: E111
    build_notifications_schema,
  )
  from custom_components.pawcontrol.types import (  # noqa: E111
    NOTIFICATION_MOBILE_FIELD,
    NOTIFICATION_PRIORITY_FIELD,
    NOTIFICATION_QUIET_END_FIELD,
    NOTIFICATION_QUIET_HOURS_FIELD,
    NOTIFICATION_QUIET_START_FIELD,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
  )

  current = {  # noqa: E111
    NOTIFICATION_QUIET_HOURS_FIELD: False,
    NOTIFICATION_QUIET_START_FIELD: "21:30:00",
    NOTIFICATION_QUIET_END_FIELD: "06:15:00",
    NOTIFICATION_REMINDER_REPEAT_FIELD: 25,
    NOTIFICATION_PRIORITY_FIELD: True,
    NOTIFICATION_MOBILE_FIELD: False,
  }

  schema = build_notifications_schema(current)  # noqa: E111
  validated = schema({})  # noqa: E111

  assert validated[NOTIFICATION_QUIET_HOURS_FIELD] is False  # noqa: E111
  assert validated[NOTIFICATION_QUIET_START_FIELD] == "21:30:00"  # noqa: E111
  assert validated[NOTIFICATION_QUIET_END_FIELD] == "06:15:00"  # noqa: E111
  assert validated[NOTIFICATION_REMINDER_REPEAT_FIELD] == 25  # noqa: E111
  assert validated[NOTIFICATION_PRIORITY_FIELD] is True  # noqa: E111
  assert validated[NOTIFICATION_MOBILE_FIELD] is False  # noqa: E111


def test_ensure_notification_options_coerces_payload() -> None:
  """Ensure notification options parsing normalizes mixed payload values."""  # noqa: E111

  from custom_components.pawcontrol.types import (  # noqa: E111
    DEFAULT_NOTIFICATION_OPTIONS,
    NOTIFICATION_MOBILE_FIELD,
    NOTIFICATION_PRIORITY_FIELD,
    NOTIFICATION_QUIET_END_FIELD,
    NOTIFICATION_QUIET_HOURS_FIELD,
    NOTIFICATION_QUIET_START_FIELD,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
    ensure_notification_options,
  )

  payload = {  # noqa: E111
    "quiet_hours": "true",
    "quiet_start": "  ",
    "quiet_end": "08:00:00",
    "reminder_repeat_min": "45",
    "priority_notifications": 0,
  }

  options = ensure_notification_options(  # noqa: E111
    payload,
    defaults=DEFAULT_NOTIFICATION_OPTIONS,
  )

  assert options[NOTIFICATION_QUIET_HOURS_FIELD] is True  # noqa: E111
  assert options[NOTIFICATION_QUIET_START_FIELD] == "22:00:00"  # noqa: E111
  assert options[NOTIFICATION_QUIET_END_FIELD] == "08:00:00"  # noqa: E111
  assert options[NOTIFICATION_REMINDER_REPEAT_FIELD] == 45  # noqa: E111
  assert options[NOTIFICATION_PRIORITY_FIELD] is False  # noqa: E111
  assert options[NOTIFICATION_MOBILE_FIELD] is True  # noqa: E111
