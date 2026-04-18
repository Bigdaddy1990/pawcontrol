"""Targeted coverage tests for validation.py."""

from datetime import time
from enum import Enum
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.exceptions import InvalidCoordinatesError, ValidationError
from custom_components.pawcontrol.validation import (
    InputCoercionError,
    InputValidator,
    _coerce_int,
    clamp_float_range,
    clamp_int_range,
    coerce_float,
    coerce_int,
    convert_validation_error_to_service_error,
    normalize_dog_id,
    validate_coordinate,
    validate_dog_name,
    validate_expires_in_hours,
    validate_float_range,
    validate_gps_accuracy_value,
    validate_gps_coordinates,
    validate_int_range,
    validate_interval,
    validate_notification_targets,
    validate_sensor_entity_id,
    validate_time_window,
)


class DemoNotification(Enum):  # noqa: D101
    PUSH = "push"
    EMAIL = "email"


@pytest.mark.unit
def test_clamp_float_range_within_bounds() -> None:  # noqa: D103
    result = clamp_float_range(
        5.0, field="weight", minimum=0.0, maximum=100.0, default=50.0
    )
    assert result == pytest.approx(5.0)


@pytest.mark.unit
def test_clamp_float_range_invalid_uses_default() -> None:  # noqa: D103
    result = clamp_float_range(
        "not-a-number", field="weight", minimum=0.0, maximum=100.0, default=50.0
    )
    assert result == pytest.approx(50.0)


@pytest.mark.unit
def test_clamp_int_range_above_max() -> None:  # noqa: D103
    result = clamp_int_range(99, field="meals", minimum=1, maximum=6, default=2)
    assert result == 6


@pytest.mark.unit
def test_coerce_float_bool_rejected() -> None:  # noqa: D103
    with pytest.raises(InputCoercionError, match="Must be numeric"):
        coerce_float("weight", True)


@pytest.mark.unit
def test_coerce_int_fractional_string_rejected() -> None:  # noqa: D103
    with pytest.raises(InputCoercionError, match="Must be a whole number"):
        coerce_int("meals", "2.9")


@pytest.mark.unit
def test_normalize_dog_id_normalizes_spaces() -> None:  # noqa: D103
    assert normalize_dog_id("  My Dog  ") == "my_dog"


@pytest.mark.unit
def test_normalize_dog_id_non_string_rejected() -> None:  # noqa: D103
    with pytest.raises(InputCoercionError, match="Must be a string"):
        normalize_dog_id(123)


@pytest.mark.unit
def test_validate_notification_targets_filters_duplicates_and_invalid() -> None:  # noqa: D103
    result = validate_notification_targets(
        ["push", DemoNotification.EMAIL, "sms", "push"],
        enum_type=DemoNotification,
    )
    assert result.targets == [DemoNotification.PUSH, DemoNotification.EMAIL]
    assert result.invalid == ["sms"]


@pytest.mark.unit
def test_validate_time_window_uses_defaults_for_empty_values() -> None:  # noqa: D103
    start, end = validate_time_window(
        "  ",
        None,
        start_field="start",
        end_field="end",
        default_start="07:00:00",
        default_end=time(21, 0),
    )
    assert start == "07:00:00"
    assert end == "21:00:00"


@pytest.mark.unit
def test_validate_time_window_rejects_invalid_end() -> None:  # noqa: D103
    with pytest.raises(ValidationError):
        validate_time_window(
            "08:00:00",
            "invalid",
            start_field="start",
            end_field="end",
        )


@pytest.mark.unit
def test_validate_time_window_accepts_explicit_start_end() -> None:
    """Explicit values should bypass default substitution branches."""
    start, end = validate_time_window(
        "08:00",
        "09:30",
        start_field="start",
        end_field="end",
        default_start="06:00",
        default_end="22:00",
    )
    assert start == "08:00:00"
    assert end == "09:30:00"


def test_coercion_error_branches_for_float_and_int_wrappers() -> None:
    """Exercise fallback coercion branches for unsupported and empty values."""
    with pytest.raises(InputCoercionError, match="Must be numeric"):
        coerce_float("weight", object())

    with pytest.raises(InputCoercionError, match="Must be a whole number"):
        coerce_int("age", "   ")

    with pytest.raises(ValidationError, match="Must be a whole number"):
        _coerce_int("age", object())


def test_validate_notification_targets_type_error_branch() -> None:
    """Notification target parsing should handle enum conversion TypeError."""

    class _TypeErrorEnum(Enum):
        OK = "ok"

        @classmethod
        def _missing_(cls, value: object) -> _TypeErrorEnum | None:
            if value == "boom":
                raise TypeError("enum conversion failed")
            return None

    parsed = validate_notification_targets(
        ["ok", "boom"],
        enum_type=_TypeErrorEnum,
    )

    assert parsed.targets == [_TypeErrorEnum.OK]
    assert parsed.invalid == ["boom"]


def test_validate_dog_name_required_and_optional_whitespace_paths() -> None:
    """Dog name validation should cover required and optional-empty branches."""
    with pytest.raises(ValidationError, match="dog_name_required"):
        validate_dog_name(None, required=True)

    with pytest.raises(ValidationError, match="dog_name_required"):
        validate_dog_name("   ", required=True)

    assert validate_dog_name("   ", required=False) is None


def test_validate_sensor_entity_id_handles_blank_candidate_after_strip() -> None:
    """Blank string candidates should honor required flag after trimming."""
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))

    class _FlakyStripValue(str):
        """Return non-empty then empty on subsequent strip calls."""

        def __new__(cls) -> _FlakyStripValue:
            instance = str.__new__(cls, "seed")
            instance._calls = 0
            return instance

        def strip(self, chars: str | None = None) -> str:
            self._calls += 1
            return "sensor.demo" if self._calls == 1 else ""

    assert (
        validate_sensor_entity_id(
            hass,
            "   ",
            field="door_sensor",
            required=False,
            required_constraint="door_sensor_required",
        )
        is None
    )

    with pytest.raises(ValidationError, match="door_sensor_required"):
        validate_sensor_entity_id(
            hass,
            "   ",
            field="door_sensor",
            required=True,
            required_constraint="door_sensor_required",
        )

    assert (
        validate_sensor_entity_id(
            hass,
            _FlakyStripValue(),
            field="door_sensor",
            required=False,
            required_constraint="door_sensor_required",
        )
        is None
    )

    with pytest.raises(ValidationError, match="door_sensor_required"):
        validate_sensor_entity_id(
            hass,
            _FlakyStripValue(),
            field="door_sensor",
            required=True,
            required_constraint="door_sensor_required",
        )


@pytest.mark.unit
def test_validate_sensor_entity_id_without_domain_or_device_class_filters() -> None:
    """Domain/device_class checks should be optional when not configured."""
    hass = SimpleNamespace(
        states=SimpleNamespace(
            get=lambda entity_id: (
                SimpleNamespace(state="on", attributes={"device_class": "door"})
                if entity_id == "binary_sensor.front_door"
                else None
            )
        )
    )

    assert (
        validate_sensor_entity_id(
            hass,
            "binary_sensor.front_door",
            field="door_sensor",
            required=True,
            domain=None,
            device_classes=None,
        )
        == "binary_sensor.front_door"
    )


def test_validate_interval_required_and_out_of_range_branches() -> None:
    """Interval validation should cover required, min, and max error branches."""
    with pytest.raises(ValidationError, match="Interval is required"):
        validate_interval(
            None,
            field="interval",
            minimum=5,
            maximum=30,
            required=True,
        )

    with pytest.raises(ValidationError, match="Minimum interval is 5"):
        validate_interval(
            2,
            field="interval",
            minimum=5,
            maximum=30,
            clamp=False,
        )

    with pytest.raises(ValidationError, match="Maximum interval is 30"):
        validate_interval(
            99,
            field="interval",
            minimum=5,
            maximum=30,
            clamp=False,
        )


def test_validate_gps_accuracy_value_none_low_high_and_valid_paths() -> None:
    """GPS accuracy helper should cover optional-none, bounds, and valid return."""
    assert validate_gps_accuracy_value(None, required=False) is None

    with pytest.raises(ValidationError, match="gps_accuracy_out_of_range"):
        validate_gps_accuracy_value(0.1, min_value=1.0, max_value=5.0, clamp=False)

    with pytest.raises(ValidationError, match="gps_accuracy_out_of_range"):
        validate_gps_accuracy_value(7.0, min_value=1.0, max_value=5.0, clamp=False)

    assert validate_gps_accuracy_value(3.0, min_value=1.0, max_value=5.0) == 3.0


@pytest.mark.unit
def test_validate_gps_accuracy_value_default_required_and_clamp_edges() -> None:
    """Cover default/required handling and both clamped bounds."""
    assert (
        validate_gps_accuracy_value(
            None,
            required=False,
            default=2.5,
            min_value=1.0,
            max_value=5.0,
        )
        == pytest.approx(2.5)
    )

    with pytest.raises(ValidationError, match="gps_accuracy_required"):
        validate_gps_accuracy_value(
            None,
            required=True,
            default=None,
            min_value=1.0,
            max_value=5.0,
        )

    assert (
        validate_gps_accuracy_value(0.5, min_value=1.0, max_value=5.0, clamp=True)
        == pytest.approx(1.0)
    )
    assert (
        validate_gps_accuracy_value(8.0, min_value=1.0, max_value=5.0, clamp=True)
        == pytest.approx(5.0)
    )


@pytest.mark.unit
def test_validate_expires_in_hours_required_numeric_and_bounds_paths() -> None:
    """Expiry helper should cover empty, coercion, bounds and valid paths."""
    assert validate_expires_in_hours(None, required=False) is None

    with pytest.raises(ValidationError, match="expires_in_hours_required"):
        validate_expires_in_hours(None, required=True)

    with pytest.raises(ValidationError, match="expires_in_hours_not_numeric"):
        validate_expires_in_hours("invalid", required=False)

    with pytest.raises(ValidationError, match="expires_in_hours_out_of_range"):
        validate_expires_in_hours(0.0, minimum=0.0, maximum=8.0)

    with pytest.raises(ValidationError, match="expires_in_hours_out_of_range"):
        validate_expires_in_hours(9.0, minimum=0.0, maximum=8.0)

    assert validate_expires_in_hours("4.5", minimum=0.0, maximum=8.0) == pytest.approx(
        4.5
    )


def test_validate_float_and_int_range_remaining_error_paths() -> None:
    """Range helpers should cover optional-none and non-clamped bound failures."""
    assert (
        validate_float_range(
            None,
            minimum=1.0,
            maximum=5.0,
            field="ratio",
            required=False,
            clamp=False,
        )
        == 0.0
    )

    assert (
        validate_float_range(
            6.0,
            minimum=1.0,
            maximum=5.0,
            field="ratio",
            clamp=True,
        )
        == 5.0
    )

    with pytest.raises(ValidationError, match="Minimum value is 1.0"):
        validate_float_range(
            0.5,
            minimum=1.0,
            maximum=5.0,
            field="ratio",
            clamp=False,
        )

    with pytest.raises(ValidationError, match="Maximum value is 5.0"):
        validate_float_range(
            6.0,
            minimum=1.0,
            maximum=5.0,
            field="ratio",
            clamp=False,
        )

    with pytest.raises(ValidationError, match="Value is required"):
        validate_float_range(
            None,
            minimum=1.0,
            maximum=5.0,
            field="ratio",
            required=True,
        )

    assert (
        validate_float_range(
            0.5,
            minimum=1.0,
            maximum=5.0,
            field="ratio",
            clamp=True,
        )
        == pytest.approx(1.0)
    )

    assert (
        validate_int_range(
            None,
            field="count",
            minimum=1,
            maximum=10,
            required=False,
        )
        is None
    )
    assert (
        validate_int_range(
            0,
            field="count",
            minimum=1,
            maximum=10,
            clamp=True,
        )
        == 1
    )
    with pytest.raises(ValidationError, match="value_out_of_range"):
        validate_int_range(
            0,
            field="count",
            minimum=1,
            maximum=10,
            clamp=False,
        )

    assert (
        validate_int_range(
            None,
            field="count",
            minimum=1,
            maximum=10,
            default=4,
            required=False,
        )
        == 4
    )

    with pytest.raises(ValidationError, match="value_not_numeric"):
        validate_int_range(
            "invalid",
            field="count",
            minimum=1,
            maximum=10,
            required=False,
        )

    with pytest.raises(ValidationError, match="value_out_of_range"):
        validate_int_range(
            11,
            field="count",
            minimum=1,
            maximum=10,
            clamp=False,
        )


@pytest.mark.unit
def test_validate_coordinate_required_and_clamp_int_error_path() -> None:
    """Cover required-coordinate errors and clamp-int fallback exceptions."""
    with pytest.raises(ValidationError, match="coordinate_required"):
        validate_coordinate(
            None,
            field="latitude",
            minimum=-90.0,
            maximum=90.0,
            required=True,
        )

    assert (
        clamp_int_range(
            "not-numeric",
            field="count",
            minimum=1,
            maximum=10,
            default=5,
        )
        == 5
    )


@pytest.mark.unit
def test_validate_gps_coordinates_out_of_range_and_static_wrapper_path() -> None:
    """Out-of-range numerics should leave fast-path and wrapper should return tuple."""
    with pytest.raises(InvalidCoordinatesError):
        validate_gps_coordinates(95.0, 13.0)

    assert InputValidator.validate_gps_coordinates("52.52", "13.405") == pytest.approx(
        (52.52, 13.405)
    )


def test_input_validator_dog_id_and_wrapper_paths() -> None:
    """InputValidator dog-id and dog-name wrappers should cover edge branches."""
    with pytest.raises(ValidationError, match="Dog ID is required"):
        InputValidator.validate_dog_id(None, required=True)

    assert InputValidator.validate_dog_id("", required=False) is None

    with pytest.raises(ValidationError, match="Must be a string"):
        InputValidator.validate_dog_id(42, required=True)

    with pytest.raises(ValidationError, match="Cannot be empty or whitespace only"):
        InputValidator.validate_dog_id("   ", required=True)

    assert InputValidator.validate_dog_id("   ", required=False) is None

    with pytest.raises(ValidationError, match="Maximum 50 characters"):
        InputValidator.validate_dog_id("a" * 51, required=True)

    with pytest.raises(
        ValidationError,
        match="Only alphanumeric characters, underscore, and hyphen allowed",
    ):
        InputValidator.validate_dog_id("bad id!", required=True)

    assert InputValidator.validate_dog_id(" dog_1 ", required=True) == "dog_1"

    assert InputValidator.validate_dog_name("  Buddy  ", required=True) == "Buddy"


def test_input_validator_weight_and_age_branches() -> None:
    """Weight and age validators should cover required and range failures."""
    with pytest.raises(ValidationError, match="Weight is required"):
        InputValidator.validate_weight(None, required=True)
    assert InputValidator.validate_weight(None, required=False) is None

    with pytest.raises(ValidationError, match="Must be positive"):
        InputValidator.validate_weight(0, required=True)

    with pytest.raises(ValidationError, match="Minimum weight is 1.0 kg"):
        InputValidator.validate_weight(0.5, required=True, min_kg=1.0, max_kg=20.0)

    with pytest.raises(ValidationError, match="Maximum weight is 5.0 kg"):
        InputValidator.validate_weight(6.0, required=True, min_kg=1.0, max_kg=5.0)

    assert (
        InputValidator.validate_weight(3.5, required=True, min_kg=1.0, max_kg=20.0)
        == 3.5
    )

    with pytest.raises(ValidationError, match="Age is required"):
        InputValidator.validate_age_months(None, required=True)
    assert InputValidator.validate_age_months(None, required=False) is None

    with pytest.raises(ValidationError, match="Minimum age is 2 months"):
        InputValidator.validate_age_months(
            1, required=True, min_months=2, max_months=24
        )

    with pytest.raises(ValidationError, match="Maximum age is 12 months"):
        InputValidator.validate_age_months(
            13,
            required=True,
            min_months=1,
            max_months=12,
        )

    assert (
        InputValidator.validate_age_months(
            6, required=True, min_months=1, max_months=12
        )
        == 6
    )

    assert (
        InputValidator.validate_gps_accuracy(
            3.0,
            required=True,
            field="accuracy",
            min_value=1.0,
            max_value=5.0,
        )
        == 3.0
    )


def test_input_validator_portion_temperature_text_and_duration_paths() -> None:
    """Cover remaining branch paths for portion/temperature/text/duration."""
    with pytest.raises(ValidationError, match="Portion amount is required"):
        InputValidator.validate_portion_size(None, required=True)
    assert InputValidator.validate_portion_size(None, required=False) is None

    with pytest.raises(ValidationError, match="Must be positive"):
        InputValidator.validate_portion_size(0, required=True)

    with pytest.raises(ValidationError, match="Minimum portion is"):
        InputValidator.validate_portion_size(0.5, required=True)

    with pytest.raises(ValidationError, match="Maximum portion is"):
        InputValidator.validate_portion_size(10000, required=True)

    assert InputValidator.validate_portion_size(250, required=True) == 250

    with pytest.raises(ValidationError, match="Temperature is required"):
        InputValidator.validate_temperature(None, required=True)
    assert InputValidator.validate_temperature(None, required=False) is None

    with pytest.raises(ValidationError, match="Normal range"):
        InputValidator.validate_temperature(100, required=True)
    assert InputValidator.validate_temperature(38.5, required=True) == 38.5

    with pytest.raises(ValidationError, match="comment is required"):
        InputValidator.validate_text_input(None, "comment", required=True)
    assert InputValidator.validate_text_input(None, "comment", required=False) is None

    with pytest.raises(ValidationError, match="Must be text"):
        InputValidator.validate_text_input(123, "comment", required=True)

    with pytest.raises(ValidationError, match="Cannot be empty or whitespace"):
        InputValidator.validate_text_input("   ", "comment", required=True)

    with pytest.raises(ValidationError, match="Minimum length: 3 characters"):
        InputValidator.validate_text_input("ab", "comment", required=True, min_length=3)

    with pytest.raises(ValidationError, match="Maximum length: 4 characters"):
        InputValidator.validate_text_input(
            "abcde",
            "comment",
            required=True,
            max_length=4,
        )

    assert (
        InputValidator.validate_text_input(
            "A\x01B\n",
            "comment",
            required=True,
        )
        == "AB"
    )

    with pytest.raises(ValidationError, match="Duration is required"):
        InputValidator.validate_duration(None, required=True)
    assert InputValidator.validate_duration(None, required=False) is None
    assert (
        InputValidator.validate_duration(
            15, required=True, min_minutes=5, max_minutes=60
        )
        == 15
    )


def test_input_validator_geofence_email_enum_and_error_conversion_paths() -> None:
    """Cover geofence/email/enum helpers and service-error conversion fallback."""
    with pytest.raises(ValidationError, match="geofence_radius_required"):
        InputValidator.validate_geofence_radius(None, required=True)
    assert InputValidator.validate_geofence_radius(None, required=False) is None

    with pytest.raises(ValidationError, match="geofence_radius_out_of_range"):
        InputValidator.validate_geofence_radius(
            0.1, required=True, min_value=1.0, max_value=100.0
        )

    with pytest.raises(ValidationError, match="geofence_radius_out_of_range"):
        InputValidator.validate_geofence_radius(
            200.0, required=True, min_value=1.0, max_value=100.0
        )

    assert (
        InputValidator.validate_geofence_radius(
            25.0,
            required=True,
            min_value=1.0,
            max_value=100.0,
        )
        == 25.0
    )

    with pytest.raises(ValidationError, match="Email address is required"):
        InputValidator.validate_email(None, required=True)
    assert InputValidator.validate_email(None, required=False) is None

    with pytest.raises(ValidationError, match="Must be text"):
        InputValidator.validate_email(123, required=True)

    with pytest.raises(ValidationError, match="Invalid email format"):
        InputValidator.validate_email("not-an-email", required=True)

    with pytest.raises(ValidationError, match="Email too long"):
        InputValidator.validate_email(f"{'a' * 250}@x.com", required=True)

    assert (
        InputValidator.validate_email(" User@Example.com ", required=True)
        == "user@example.com"
    )

    with pytest.raises(ValidationError, match="mode is required"):
        InputValidator.validate_enum_value(
            None, "mode", {"Home", "Away"}, required=True
        )
    assert (
        InputValidator.validate_enum_value(
            None, "mode", {"Home", "Away"}, required=False
        )
        is None
    )

    assert (
        InputValidator.validate_enum_value(1, "mode", {"1", "2"}, required=True) == "1"
    )

    with pytest.raises(ValidationError, match="Invalid value"):
        InputValidator.validate_enum_value(
            "invalid", "mode", {"Home", "Away"}, required=True
        )

    assert (
        InputValidator.validate_enum_value(
            "home", "mode", {"Home", "Away"}, required=True
        )
        == "Home"
    )

    class _FlakyLower:
        def __init__(self) -> None:
            self.calls = 0

        def lower(self) -> str:
            self.calls += 1
            return "match" if self.calls == 1 else "mismatch"

    flaky = _FlakyLower()
    assert (
        InputValidator.validate_enum_value("match", "mode", [flaky], required=True)
        == "match"
    )

    service_error = convert_validation_error_to_service_error(
        ValidationError("field", "value", "constraint"),
    )
    assert "field" in str(service_error)
