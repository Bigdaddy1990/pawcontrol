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
