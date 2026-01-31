"""Tests for flow helper modules."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.flows.health_helpers import summarise_health_summary
from custom_components.pawcontrol.flows.notifications_helpers import (
  build_notification_settings_payload,
)
from custom_components.pawcontrol.flows.walk_schemas import (
  build_auto_end_walks_field,
  build_walk_timing_schema_fields,
)
from custom_components.pawcontrol.types import (
  DEFAULT_DOOR_SENSOR_SETTINGS,
  NOTIFICATION_REMINDER_REPEAT_FIELD,
)


def test_summarise_health_summary_flags_issues() -> None:
  """Health summaries should surface issues and warnings."""

  summary = {
    "healthy": False,
    "issues": ["Weight loss"],
    "warnings": ["Check hydration"],
  }

  result = summarise_health_summary(summary)

  assert result == "Issues detected | Issues: Weight loss | Warnings: Check hydration"


def test_build_notification_settings_payload_rejects_invalid_repeat() -> None:
  """Invalid reminder repeat values should raise a validation error."""

  user_input = {NOTIFICATION_REMINDER_REPEAT_FIELD: "invalid"}

  with pytest.raises(FlowValidationError):
    build_notification_settings_payload(
      user_input,
      {},
      coerce_bool=lambda value, default: default if value is None else bool(value),
      coerce_int=lambda value, default: default if value is None else int(value),
      coerce_time_string=lambda value, default: default
      if value is None
      else str(value),
    )


def test_walk_schema_helpers_cover_expected_fields() -> None:
  """Walk helpers should define the expected schema fields."""

  defaults = DEFAULT_DOOR_SENSOR_SETTINGS
  timing_fields = build_walk_timing_schema_fields({}, defaults)
  auto_end_field = build_auto_end_walks_field({}, defaults)

  assert {key.schema for key in timing_fields} == {
    "walk_detection_timeout",
    "minimum_walk_duration",
    "maximum_walk_duration",
  }
  assert {key.schema for key in auto_end_field} == {"auto_end_walks"}
