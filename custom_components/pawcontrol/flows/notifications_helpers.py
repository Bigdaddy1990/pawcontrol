"""Notification helper utilities for Paw Control flows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from ..exceptions import FlowValidationError, ValidationError
from ..types import (
  NOTIFICATION_MOBILE_FIELD,
  NOTIFICATION_PRIORITY_FIELD,
  NOTIFICATION_QUIET_END_FIELD,
  NOTIFICATION_QUIET_HOURS_FIELD,
  NOTIFICATION_QUIET_START_FIELD,
  NOTIFICATION_REMINDER_REPEAT_FIELD,
  NotificationOptions,
  NotificationSettingsInput,
)
from ..validation import validate_int_range, validate_time_window


def build_notification_settings_payload(
  user_input: NotificationSettingsInput,
  current: NotificationOptions,
  *,
  coerce_bool: Callable[[Any, bool], bool],
) -> NotificationOptions:
  """Create a typed notification payload from submitted form data."""

  try:
    reminder_repeat = validate_int_range(
      user_input.get(NOTIFICATION_REMINDER_REPEAT_FIELD),
      field=NOTIFICATION_REMINDER_REPEAT_FIELD,
      minimum=5,
      maximum=240,
      required=True,
      required_constraint="invalid_configuration",
      not_numeric_constraint="invalid_configuration",
      out_of_range_constraint="invalid_configuration",
    )
  except ValidationError as err:
    raise FlowValidationError(
      field_errors={
        NOTIFICATION_REMINDER_REPEAT_FIELD: err.constraint or "invalid_configuration"
      }
    ) from err

  try:
    quiet_start, quiet_end = validate_time_window(
      user_input.get(NOTIFICATION_QUIET_START_FIELD),
      user_input.get(NOTIFICATION_QUIET_END_FIELD),
      start_field=NOTIFICATION_QUIET_START_FIELD,
      end_field=NOTIFICATION_QUIET_END_FIELD,
      default_start=current.get(NOTIFICATION_QUIET_START_FIELD, "22:00:00"),
      default_end=current.get(NOTIFICATION_QUIET_END_FIELD, "07:00:00"),
      invalid_start_constraint="quiet_start_invalid",
      invalid_end_constraint="quiet_end_invalid",
    )
  except ValidationError as err:
    raise FlowValidationError(field_errors={err.field: err.constraint}) from err

  return cast(
    NotificationOptions,
    {
      NOTIFICATION_QUIET_HOURS_FIELD: coerce_bool(
        user_input.get(NOTIFICATION_QUIET_HOURS_FIELD),
        current.get(NOTIFICATION_QUIET_HOURS_FIELD, True),
      ),
      NOTIFICATION_QUIET_START_FIELD: quiet_start,
      NOTIFICATION_QUIET_END_FIELD: quiet_end,
      NOTIFICATION_REMINDER_REPEAT_FIELD: reminder_repeat,
      NOTIFICATION_PRIORITY_FIELD: coerce_bool(
        user_input.get(NOTIFICATION_PRIORITY_FIELD),
        current.get(NOTIFICATION_PRIORITY_FIELD, True),
      ),
      NOTIFICATION_MOBILE_FIELD: coerce_bool(
        user_input.get(NOTIFICATION_MOBILE_FIELD),
        current.get(NOTIFICATION_MOBILE_FIELD, True),
      ),
    },
  )
