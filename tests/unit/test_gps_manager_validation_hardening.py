"""Hardening coverage for gps_manager.py and validation.py."""

from datetime import time as dt_time
from enum import Enum
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.gps_manager import (
    _build_tracking_config,
    _coerce_tracking_bool,
    _coerce_tracking_float,
    _coerce_tracking_int,
)
from custom_components.pawcontrol.validation import (
    InputCoercionError,
    NotificationTargets,
    _parse_time_string,
    validate_expires_in_hours,
    validate_notification_targets,
    validate_time_window,
)


class _Target(Enum):
    """Local enum for notification parsing tests."""

    PUSH = "push"
    EMAIL = "email"


@pytest.mark.unit
def test_tracking_bool_uses_default_for_non_bool_values() -> None:
    """Invalid bool-like config values should use default safely."""
    assert _coerce_tracking_bool("true", True) is True
    assert _coerce_tracking_bool(1, False) is False
    assert _coerce_tracking_bool(None, True) is True


@pytest.mark.unit
def test_tracking_float_coercion_and_fallback_defaults() -> None:
    """Float conversion should accept numerics and reject bools/objects."""
    assert _coerce_tracking_float(12, 2.5) == pytest.approx(12.0)
    assert _coerce_tracking_float(12.8, 2.5) == pytest.approx(12.8)
    assert _coerce_tracking_float(True, 2.5) == pytest.approx(2.5)
    assert _coerce_tracking_float(object(), 2.5) == pytest.approx(2.5)


@pytest.mark.unit
def test_tracking_int_coercion_truncates_float_and_falls_back() -> None:
    """Integer conversion should truncate floats and ignore unsupported types."""
    assert _coerce_tracking_int(20, 9) == 20
    assert _coerce_tracking_int(20.9, 9) == 20
    assert _coerce_tracking_int(False, 9) == 9
    assert _coerce_tracking_int("20", 9) == 9


@pytest.mark.unit
def test_build_tracking_config_applies_defaults_without_crash() -> None:
    """Schema/type mismatches should safely fallback to runtime defaults."""
    config = _build_tracking_config({
        "enabled": "yes",
        "auto_start_walk": 1,
        "track_route": None,
        "safety_alerts": "no",
        "geofence_notifications": [],
        "auto_detect_home": {},
        "gps_accuracy_threshold": "50",
        "update_interval_seconds": "30",
        "min_distance_for_point": False,
        "route_smoothing": "on",
    })

    assert config.enabled is True
    assert config.auto_start_walk is True
    assert config.track_route is True
    assert config.safety_alerts is True
    assert config.geofence_notifications is True
    assert config.auto_detect_home is True
    assert config.accuracy_threshold == pytest.approx(50.0)
    assert config.update_interval == 60
    assert config.min_distance_for_point == pytest.approx(10.0)
    assert config.route_smoothing is True


@pytest.mark.unit
def test_build_tracking_config_accepts_explicit_bool_and_numeric_values() -> None:
    """Valid inputs should be preserved exactly where appropriate."""
    config = _build_tracking_config({
        "enabled": False,
        "auto_start_walk": False,
        "track_route": False,
        "safety_alerts": False,
        "geofence_notifications": False,
        "auto_detect_home": False,
        "gps_accuracy_threshold": 18,
        "update_interval_seconds": 15.9,
        "min_distance_for_point": 2,
        "route_smoothing": False,
    })

    assert config.enabled is False
    assert config.auto_start_walk is False
    assert config.track_route is False
    assert config.safety_alerts is False
    assert config.geofence_notifications is False
    assert config.auto_detect_home is False
    assert config.accuracy_threshold == pytest.approx(18.0)
    assert config.update_interval == 15
    assert config.min_distance_for_point == pytest.approx(2.0)
    assert config.route_smoothing is False


@pytest.mark.unit
def test_parse_time_string_covers_missing_type_and_value_error_paths() -> None:
    """Time parser should separate missing, type, and parse failures."""
    assert _parse_time_string("start", None, "invalid") is None
    assert _parse_time_string("start", "   ", "invalid") is None
    assert _parse_time_string("start", dt_time(7, 45), "invalid") == "07:45:00"

    with pytest.raises(ValidationError, match="invalid"):
        _parse_time_string("start", 123, "invalid")

    with pytest.raises(ValidationError, match="invalid"):
        _parse_time_string("start", "not-a-time", "invalid")


@pytest.mark.unit
def test_validate_time_window_uses_defaults_and_required_constraints() -> None:
    """Missing fields should use defaults; absent defaults should fail clearly."""
    assert validate_time_window(
        None,
        "",
        start_field="quiet_start",
        end_field="quiet_end",
        default_start="22:00",
        default_end="07:00",
    ) == ("22:00:00", "07:00:00")

    with pytest.raises(ValidationError, match="start_required"):
        validate_time_window(
            None,
            "07:00",
            start_field="quiet_start",
            end_field="quiet_end",
            required_start_constraint="start_required",
        )


@pytest.mark.unit
def test_validate_notification_targets_separates_value_and_type_errors() -> None:
    """Enum coercion should classify both ValueError and TypeError inputs."""
    parsed = validate_notification_targets(
        ["push", "invalid", ["nested"], {"bad"}, "push", _Target.EMAIL],
        enum_type=_Target,
    )

    assert isinstance(parsed, NotificationTargets)
    assert parsed.targets == [_Target.PUSH, _Target.EMAIL]
    assert "invalid" in parsed.invalid
    assert "['nested']" in parsed.invalid
    assert "{'bad'}" in parsed.invalid


@pytest.mark.unit
def test_validate_notification_targets_handles_scalar_non_iterable() -> None:
    """A scalar non-iterable candidate should be validated without crashing."""
    parsed = validate_notification_targets(
        SimpleNamespace(value="x"), enum_type=_Target
    )
    assert parsed.targets == []
    assert parsed.invalid == ["namespace(value='x')"]


@pytest.mark.unit
def test_validate_expires_in_hours_missing_numeric_and_bounds() -> None:
    """Expiry validation should cover required, type, and range branches."""
    assert validate_expires_in_hours(None, required=False) is None

    with pytest.raises(ValidationError, match="expires_in_hours_required"):
        validate_expires_in_hours(None, required=True)

    with pytest.raises(ValidationError, match="expires_in_hours_not_numeric"):
        validate_expires_in_hours(object())

    with pytest.raises(ValidationError, match="expires_in_hours_out_of_range"):
        validate_expires_in_hours(0)

    with pytest.raises(ValidationError, match="expires_in_hours_out_of_range"):
        validate_expires_in_hours(12, maximum=10)

    assert validate_expires_in_hours("2.5", maximum=10) == pytest.approx(2.5)


@pytest.mark.unit
def test_input_coercion_error_exposes_context_fields() -> None:
    """InputCoercionError should preserve field and raw value metadata."""
    err = InputCoercionError("gps_accuracy", "abc", "Must be numeric")
    assert err.field == "gps_accuracy"
    assert err.value == "abc"
    assert err.message == "Must be numeric"
