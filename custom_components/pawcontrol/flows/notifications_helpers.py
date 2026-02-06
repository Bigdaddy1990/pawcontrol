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
  NotificationOptionsField,
  NotificationOptions,
  NotificationSettingsInput,
)
from ..validation import validate_int_range


def _bool_default(
  current: NotificationOptions,
  field: NotificationOptionsField,
  fallback: bool,
) -> bool:
  """Return a boolean default extracted from a notification payload."""

  value = current.get(field, fallback)
  return value if isinstance(value, bool) else fallback


def _string_default(
  current: NotificationOptions,
  field: NotificationOptionsField,
  fallback: str,
) -> str:
  """Return a string default extracted from a notification payload."""

  value = current.get(field, fallback)
  return value if isinstance(value, str) else fallback


def build_notification_settings_payload(
  user_input: NotificationSettingsInput,
  current: NotificationOptions,
  *,
  coerce_bool: Callable[[Any, bool], bool],
  coerce_time_string: Callable[[Any, str], str],
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

  return cast(
    NotificationOptions,
    {
      NOTIFICATION_QUIET_HOURS_FIELD: coerce_bool(
        user_input.get(NOTIFICATION_QUIET_HOURS_FIELD),
        _bool_default(current, NOTIFICATION_QUIET_HOURS_FIELD, True),
      ),
      NOTIFICATION_QUIET_START_FIELD: coerce_time_string(
        user_input.get(NOTIFICATION_QUIET_START_FIELD),
        _string_default(current, NOTIFICATION_QUIET_START_FIELD, "22:00:00"),
      ),
      NOTIFICATION_QUIET_END_FIELD: coerce_time_string(
        user_input.get(NOTIFICATION_QUIET_END_FIELD),
        _string_default(current, NOTIFICATION_QUIET_END_FIELD, "07:00:00"),
      ),
      NOTIFICATION_REMINDER_REPEAT_FIELD: reminder_repeat,
      NOTIFICATION_PRIORITY_FIELD: coerce_bool(
        user_input.get(NOTIFICATION_PRIORITY_FIELD),
        _bool_default(current, NOTIFICATION_PRIORITY_FIELD, True),
      ),
      NOTIFICATION_MOBILE_FIELD: coerce_bool(
        user_input.get(NOTIFICATION_MOBILE_FIELD),
        _bool_default(current, NOTIFICATION_MOBILE_FIELD, True),
      ),
    },
  )
