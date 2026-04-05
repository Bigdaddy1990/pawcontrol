"""Additional branch coverage for notification flow helper utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from custom_components.pawcontrol.exceptions import FlowValidationError, ValidationError
import custom_components.pawcontrol.flow_steps.notifications_helpers as helpers
from custom_components.pawcontrol.types import (
    NOTIFICATION_MOBILE_FIELD,
    NOTIFICATION_PRIORITY_FIELD,
    NOTIFICATION_QUIET_END_FIELD,
    NOTIFICATION_QUIET_HOURS_FIELD,
    NOTIFICATION_QUIET_START_FIELD,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
)


@pytest.mark.unit
def test_validate_time_input_accepts_float_zero() -> None:
    """A floating-point zero should be treated like an empty quiet-hour value."""
    helpers._validate_time_input(0.0, NOTIFICATION_QUIET_START_FIELD)


@pytest.mark.unit
def test_validate_time_input_rejects_non_zero_numeric_values() -> None:
    """Numeric values other than zero should be rejected with field-specific errors."""
    with pytest.raises(FlowValidationError) as err:
        helpers._validate_time_input(7.5, NOTIFICATION_QUIET_END_FIELD)

    assert err.value.field_errors == {NOTIFICATION_QUIET_END_FIELD: "quiet_end_invalid"}


@pytest.mark.unit
def test_build_notification_settings_payload_keeps_validation_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation constraints should propagate into flow field errors unchanged."""

    def _raise_with_constraint(*_args: Any, **_kwargs: Any) -> int:
        raise ValidationError(
            field=NOTIFICATION_REMINDER_REPEAT_FIELD,
            value="bad",
            constraint="repeat_too_low",
        )

    monkeypatch.setattr(helpers, "validate_int_range", _raise_with_constraint)

    with pytest.raises(FlowValidationError) as err:
        helpers.build_notification_settings_payload(
            user_input={NOTIFICATION_REMINDER_REPEAT_FIELD: "bad"},
            current={},
            coerce_bool=lambda _value, fallback: fallback,
            coerce_time_string=lambda _value, fallback: fallback,
        )

    assert err.value.field_errors == {
        NOTIFICATION_REMINDER_REPEAT_FIELD: "repeat_too_low"
    }


@pytest.mark.unit
def test_build_notification_settings_payload_uses_default_fallbacks() -> None:
    """Fallback defaults should be applied when current values use wrong types."""
    seen_bool_fallbacks: list[bool] = []
    seen_time_fallbacks: list[str] = []

    def _record_bool(_value: Any, fallback: bool) -> bool:
        seen_bool_fallbacks.append(fallback)
        return fallback

    def _record_time(_value: Any, fallback: str) -> str:
        seen_time_fallbacks.append(fallback)
        return fallback

    payload = helpers.build_notification_settings_payload(
        user_input={NOTIFICATION_REMINDER_REPEAT_FIELD: "20"},
        current={
            NOTIFICATION_QUIET_HOURS_FIELD: "not-a-bool",
            NOTIFICATION_QUIET_START_FIELD: datetime(2026, 1, 1, 22, 30, 0),
            NOTIFICATION_QUIET_END_FIELD: 700,
            NOTIFICATION_PRIORITY_FIELD: "high",
            NOTIFICATION_MOBILE_FIELD: 1,
        },
        coerce_bool=_record_bool,
        coerce_time_string=_record_time,
    )

    assert seen_bool_fallbacks == [True, True, True]
    assert seen_time_fallbacks == ["22:00:00", "07:00:00"]
    assert payload == {
        NOTIFICATION_QUIET_HOURS_FIELD: True,
        NOTIFICATION_QUIET_START_FIELD: "22:00:00",
        NOTIFICATION_QUIET_END_FIELD: "07:00:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: 20,
        NOTIFICATION_PRIORITY_FIELD: True,
        NOTIFICATION_MOBILE_FIELD: True,
    }
