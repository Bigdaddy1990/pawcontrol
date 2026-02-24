"""Tests for notification flow schema builders."""

import voluptuous as vol

from custom_components.pawcontrol.const import DEFAULT_REMINDER_REPEAT_MIN
from custom_components.pawcontrol.flow_steps.notifications_schemas import (
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


def test_build_notifications_schema_uses_current_settings_defaults() -> None:
    """Defaults should come from current notification settings."""
    current = {
        NOTIFICATION_QUIET_HOURS_FIELD: False,
        NOTIFICATION_QUIET_START_FIELD: "21:15:00",
        NOTIFICATION_QUIET_END_FIELD: "06:45:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: 30,
        NOTIFICATION_PRIORITY_FIELD: False,
        NOTIFICATION_MOBILE_FIELD: True,
    }

    schema = build_notifications_schema(current)

    assert schema({}) == current


def test_build_notifications_schema_user_input_overrides_current_defaults() -> None:
    """In-flight user input should take precedence over stored settings."""
    current = {
        NOTIFICATION_QUIET_HOURS_FIELD: True,
        NOTIFICATION_QUIET_START_FIELD: "22:00:00",
        NOTIFICATION_QUIET_END_FIELD: "07:00:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: DEFAULT_REMINDER_REPEAT_MIN,
        NOTIFICATION_PRIORITY_FIELD: True,
        NOTIFICATION_MOBILE_FIELD: True,
    }
    user_input = {
        NOTIFICATION_QUIET_HOURS_FIELD: False,
        NOTIFICATION_QUIET_START_FIELD: "20:00:00",
        NOTIFICATION_QUIET_END_FIELD: "05:30:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: 45,
        NOTIFICATION_PRIORITY_FIELD: False,
        NOTIFICATION_MOBILE_FIELD: False,
    }

    schema = build_notifications_schema(current, user_input)

    assert schema({}) == user_input


def test_build_notifications_schema_falls_back_to_integration_defaults() -> None:
    """Missing current values should use integration-level defaults."""
    schema = build_notifications_schema({})

    assert schema({}) == {
        NOTIFICATION_QUIET_HOURS_FIELD: True,
        NOTIFICATION_QUIET_START_FIELD: "22:00:00",
        NOTIFICATION_QUIET_END_FIELD: "07:00:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: DEFAULT_REMINDER_REPEAT_MIN,
        NOTIFICATION_PRIORITY_FIELD: True,
        NOTIFICATION_MOBILE_FIELD: True,
    }


def test_build_notifications_schema_allows_explicit_overrides() -> None:
    """Explicit values should pass through schema validation unchanged."""
    schema = build_notifications_schema({})

    parsed = schema({NOTIFICATION_REMINDER_REPEAT_FIELD: 1})

    assert parsed[NOTIFICATION_REMINDER_REPEAT_FIELD] == 1
