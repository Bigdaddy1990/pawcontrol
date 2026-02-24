"""Unit tests for notification flow helper utilities."""

from datetime import datetime

import pytest

from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.flow_steps.notifications_helpers import (
    _bool_default,
    _string_default,
    _validate_time_input,
    build_notification_settings_payload,
)
from custom_components.pawcontrol.types import (
    NOTIFICATION_MOBILE_FIELD,
    NOTIFICATION_PRIORITY_FIELD,
    NOTIFICATION_QUIET_END_FIELD,
    NOTIFICATION_QUIET_HOURS_FIELD,
    NOTIFICATION_QUIET_START_FIELD,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
)


@pytest.mark.unit
def test_bool_default_uses_fallback_for_non_booleans() -> None:
    """Boolean defaults should ignore non-boolean payload values."""
    current = {NOTIFICATION_QUIET_HOURS_FIELD: "true"}

    assert _bool_default(current, NOTIFICATION_QUIET_HOURS_FIELD, False) is False
    assert _bool_default({}, NOTIFICATION_PRIORITY_FIELD, True) is True


@pytest.mark.unit
def test_string_default_uses_fallback_for_non_strings() -> None:
    """String defaults should ignore numeric payload values."""
    current = {NOTIFICATION_QUIET_START_FIELD: 2300}

    assert _string_default(current, NOTIFICATION_QUIET_START_FIELD, "22:00:00") == "22:00:00"
    assert _string_default({}, NOTIFICATION_QUIET_END_FIELD, "07:00:00") == "07:00:00"


@pytest.mark.unit
def test_validate_time_input_accepts_supported_representations() -> None:
    """Time validation should accept datetime and common HH:MM formats."""
    _validate_time_input(None, NOTIFICATION_QUIET_START_FIELD)
    _validate_time_input(datetime(2025, 1, 1, 22, 0, 0), NOTIFICATION_QUIET_START_FIELD)
    _validate_time_input(0, NOTIFICATION_QUIET_START_FIELD)
    _validate_time_input("22:00", NOTIFICATION_QUIET_START_FIELD)
    _validate_time_input("22:00:00", NOTIFICATION_QUIET_START_FIELD)


@pytest.mark.unit
def test_validate_time_input_rejects_invalid_values() -> None:
    """Invalid quiet-hour values should raise field-specific validation errors."""
    with pytest.raises(FlowValidationError) as err:
        _validate_time_input("25:00", NOTIFICATION_QUIET_START_FIELD)

    assert err.value.field_errors == {NOTIFICATION_QUIET_START_FIELD: "quiet_start_invalid"}


@pytest.mark.unit
def test_build_notification_settings_payload_uses_current_defaults() -> None:
    """Payload builder should use current values when user input is omitted."""
    current = {
        NOTIFICATION_QUIET_HOURS_FIELD: False,
        NOTIFICATION_QUIET_START_FIELD: "23:15:00",
        NOTIFICATION_QUIET_END_FIELD: "06:45:00",
        NOTIFICATION_PRIORITY_FIELD: False,
        NOTIFICATION_MOBILE_FIELD: False,
    }
    user_input = {NOTIFICATION_REMINDER_REPEAT_FIELD: "15"}

    result = build_notification_settings_payload(
        user_input,
        current,
        coerce_bool=lambda value, fallback: fallback if value is None else bool(value),
        coerce_time_string=lambda value, fallback: fallback if value is None else str(value),
    )

    assert result[NOTIFICATION_QUIET_HOURS_FIELD] is False
    assert result[NOTIFICATION_QUIET_START_FIELD] == "23:15:00"
    assert result[NOTIFICATION_QUIET_END_FIELD] == "06:45:00"
    assert result[NOTIFICATION_REMINDER_REPEAT_FIELD] == 15
    assert result[NOTIFICATION_PRIORITY_FIELD] is False
    assert result[NOTIFICATION_MOBILE_FIELD] is False


@pytest.mark.unit
def test_build_notification_settings_payload_maps_validation_errors() -> None:
    """Reminder-repeat validation errors should map to flow field errors."""
    with pytest.raises(FlowValidationError) as err:
        build_notification_settings_payload(
            {NOTIFICATION_REMINDER_REPEAT_FIELD: "invalid"},
            {},
            coerce_bool=lambda value, fallback: fallback,
            coerce_time_string=lambda value, fallback: fallback,
        )

    assert err.value.field_errors == {
        NOTIFICATION_REMINDER_REPEAT_FIELD: "invalid_configuration"
    }
