"""Tests for notification schema builders."""

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


def test_build_notifications_schema_uses_fallback_defaults() -> None:
    """Schema should provide expected defaults when no values exist."""
    schema = build_notifications_schema({})

    assert schema({}) == {
        NOTIFICATION_QUIET_HOURS_FIELD: True,
        NOTIFICATION_QUIET_START_FIELD: "22:00:00",
        NOTIFICATION_QUIET_END_FIELD: "07:00:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: DEFAULT_REMINDER_REPEAT_MIN,
        NOTIFICATION_PRIORITY_FIELD: True,
        NOTIFICATION_MOBILE_FIELD: True,
    }


def test_build_notifications_schema_prefers_user_input_over_current() -> None:
    """User-provided values should override current notification settings."""
    current = {
        NOTIFICATION_QUIET_HOURS_FIELD: False,
        NOTIFICATION_QUIET_START_FIELD: "21:30:00",
        NOTIFICATION_QUIET_END_FIELD: "06:30:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: 45,
        NOTIFICATION_PRIORITY_FIELD: False,
        NOTIFICATION_MOBILE_FIELD: False,
    }
    user_input = {
        NOTIFICATION_QUIET_HOURS_FIELD: True,
        NOTIFICATION_REMINDER_REPEAT_FIELD: 60,
    }

    schema = build_notifications_schema(current, user_input)

    assert schema({}) == {
        NOTIFICATION_QUIET_HOURS_FIELD: True,
        NOTIFICATION_QUIET_START_FIELD: "21:30:00",
        NOTIFICATION_QUIET_END_FIELD: "06:30:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: 60,
        NOTIFICATION_PRIORITY_FIELD: False,
        NOTIFICATION_MOBILE_FIELD: False,
    }
