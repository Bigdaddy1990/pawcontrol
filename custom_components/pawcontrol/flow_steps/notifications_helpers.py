"""Notification helper utilities for Paw Control flows."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
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
  NotificationOptionsField,
  NotificationSettingsInput,
)
from ..validation import validate_int_range


def _bool_default(
  current: NotificationOptions,
  field: NotificationOptionsField,
  fallback: bool,
) -> bool:
  """Return a boolean default extracted from a notification payload."""  # noqa: E111

  value = current.get(field, fallback)  # noqa: E111
  return value if isinstance(value, bool) else fallback  # noqa: E111


def _string_default(
  current: NotificationOptions,
  field: NotificationOptionsField,
  fallback: str,
) -> str:
  """Return a string default extracted from a notification payload."""  # noqa: E111

  value = current.get(field, fallback)  # noqa: E111
  return value if isinstance(value, str) else fallback  # noqa: E111


def _validate_time_input(value: Any, field: NotificationOptionsField) -> None:
  """Validate optional quiet-hour time input."""  # noqa: E111

  if value is None:  # noqa: E111
    return

  if isinstance(value, datetime):  # noqa: E111
    return

  if isinstance(value, int | float) and value == 0:  # noqa: E111
    return

  candidate = str(value).strip()  # noqa: E111
  if not candidate:  # noqa: E111
    return

  formats = ("%H:%M:%S", "%H:%M")  # noqa: E111
  for fmt in formats:  # noqa: E111
    try:
      datetime.strptime(candidate, fmt)  # noqa: E111
      return  # noqa: E111
    except ValueError:
      continue  # noqa: E111

  raise FlowValidationError(field_errors={field: f"{field}_invalid"})  # noqa: E111


def build_notification_settings_payload(
  user_input: NotificationSettingsInput,
  current: NotificationOptions,
  *,
  coerce_bool: Callable[[Any, bool], bool],
  coerce_time_string: Callable[[Any, str], str],
) -> NotificationOptions:
  """Create a typed notification payload from submitted form data."""  # noqa: E111

  _validate_time_input(  # noqa: E111
    user_input.get(NOTIFICATION_QUIET_START_FIELD),
    NOTIFICATION_QUIET_START_FIELD,
  )
  _validate_time_input(  # noqa: E111
    user_input.get(NOTIFICATION_QUIET_END_FIELD),
    NOTIFICATION_QUIET_END_FIELD,
  )

  try:  # noqa: E111
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
  except ValidationError as err:  # noqa: E111
    raise FlowValidationError(
      field_errors={
        NOTIFICATION_REMINDER_REPEAT_FIELD: err.constraint or "invalid_configuration"
      }
    ) from err

  return cast(  # noqa: E111
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
