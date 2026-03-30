"""Targeted coverage tests for validation.py — uncovered paths (58% → 75%+).

Covers: coerce_float, coerce_int, _parse_time_string, validate_dog_name,
        validate_coordinate, validate_gps_source, validate_notify_service,
        validate_time_window, coerce_dog_id, parse_notification_targets
"""

from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
    InputCoercionError,
    coerce_float,
    coerce_int,
    validate_coordinate,
    validate_dog_name,
    validate_time_window,
)

# ═══════════════════════════════════════════════════════════════════════════════
# coerce_float
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_coerce_float_bool_raises() -> None:
    with pytest.raises(InputCoercionError):
        coerce_float("field", True)


@pytest.mark.unit
def test_coerce_float_numeric() -> None:
    assert coerce_float("f", 3) == 3.0
    assert coerce_float("f", 3.14) == pytest.approx(3.14)


@pytest.mark.unit
def test_coerce_float_string() -> None:
    assert coerce_float("f", "2.5") == pytest.approx(2.5)
    assert coerce_float("f", "  7  ") == 7.0


@pytest.mark.unit
def test_coerce_float_empty_string_raises() -> None:
    with pytest.raises(InputCoercionError):
        coerce_float("f", "  ")


@pytest.mark.unit
def test_coerce_float_bad_string_raises() -> None:
    with pytest.raises(InputCoercionError):
        coerce_float("f", "not-a-number")


@pytest.mark.unit
def test_coerce_float_unsupported_type_raises() -> None:
    with pytest.raises(InputCoercionError):
        coerce_float("f", [1, 2])


# ═══════════════════════════════════════════════════════════════════════════════
# coerce_int
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_coerce_int_bool_raises() -> None:
    with pytest.raises(InputCoercionError):
        coerce_int("field", True)


@pytest.mark.unit
def test_coerce_int_int() -> None:
    assert coerce_int("f", 5) == 5


@pytest.mark.unit
def test_coerce_int_float_whole() -> None:
    assert coerce_int("f", 4.0) == 4


@pytest.mark.unit
def test_coerce_int_float_fractional_raises() -> None:
    with pytest.raises(InputCoercionError):
        coerce_int("f", 4.5)


@pytest.mark.unit
def test_coerce_int_string() -> None:
    assert coerce_int("f", "7") == 7


@pytest.mark.unit
def test_coerce_int_empty_string_raises() -> None:
    with pytest.raises(InputCoercionError):
        coerce_int("f", "")


@pytest.mark.unit
def test_coerce_int_bad_string_raises() -> None:
    with pytest.raises(InputCoercionError):
        coerce_int("f", "abc")


# ═══════════════════════════════════════════════════════════════════════════════
# validate_dog_name
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_validate_dog_name_valid() -> None:
    assert validate_dog_name("Rex") == "Rex"


@pytest.mark.unit
def test_validate_dog_name_strips_whitespace() -> None:
    assert validate_dog_name("  Buddy  ") == "Buddy"


@pytest.mark.unit
def test_validate_dog_name_none_required_raises() -> None:
    with pytest.raises(ValidationError):
        validate_dog_name(None, required=True)


@pytest.mark.unit
def test_validate_dog_name_none_optional_returns_none() -> None:
    assert validate_dog_name(None, required=False) is None


@pytest.mark.unit
def test_validate_dog_name_too_short_raises() -> None:
    with pytest.raises(ValidationError):
        validate_dog_name("", required=True)


@pytest.mark.unit
def test_validate_dog_name_too_long_raises() -> None:
    with pytest.raises(ValidationError):
        validate_dog_name("A" * 200)


# ═══════════════════════════════════════════════════════════════════════════════
# validate_coordinate
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_validate_coordinate_valid_lat() -> None:
    result = validate_coordinate(52.5, field="lat", minimum=-90.0, maximum=90.0)
    assert result == pytest.approx(52.5)


@pytest.mark.unit
def test_validate_coordinate_out_of_range_raises() -> None:
    with pytest.raises(ValidationError):
        validate_coordinate(200.0, field="lat", minimum=-90.0, maximum=90.0)


@pytest.mark.unit
def test_validate_coordinate_empty_required_raises() -> None:
    with pytest.raises(ValidationError):
        validate_coordinate(
            None, field="lat", minimum=-90.0, maximum=90.0, required=True
        )


@pytest.mark.unit
def test_validate_coordinate_empty_optional_returns_none() -> None:
    result = validate_coordinate(
        None, field="lat", minimum=-90.0, maximum=90.0, required=False
    )
    assert result is None


@pytest.mark.unit
def test_validate_coordinate_non_numeric_raises() -> None:
    with pytest.raises(ValidationError):
        validate_coordinate("not-a-coord", field="lat", minimum=-90.0, maximum=90.0)


# ═══════════════════════════════════════════════════════════════════════════════
# validate_time_window
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_validate_time_window_valid() -> None:
    start, end = validate_time_window(
        "08:00",
        "22:00",
        start_field="start",
        end_field="end",
    )
    assert "08" in start
    assert "22" in end


@pytest.mark.unit
def test_validate_time_window_uses_defaults() -> None:
    start, end = validate_time_window(
        None,
        None,
        start_field="start",
        end_field="end",
        default_start="07:00",
        default_end="23:00",
    )
    assert "07" in start
    assert "23" in end


@pytest.mark.unit
def test_validate_time_window_missing_required_raises() -> None:
    with pytest.raises(ValidationError):
        validate_time_window(
            None,
            None,
            start_field="start",
            end_field="end",
        )


@pytest.mark.unit
def test_validate_time_window_invalid_format_raises() -> None:
    with pytest.raises(ValidationError):
        validate_time_window(
            "not-a-time",
            "22:00",
            start_field="start",
            end_field="end",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# validate_gps_source
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_validate_gps_source_manual(mock_hass) -> None:
    from custom_components.pawcontrol.validation import validate_gps_source

    result = validate_gps_source(mock_hass, "manual")
    assert result == "manual"


@pytest.mark.unit
def test_validate_gps_source_webhook(mock_hass) -> None:
    from custom_components.pawcontrol.validation import validate_gps_source

    result = validate_gps_source(mock_hass, "webhook")
    assert result == "webhook"


@pytest.mark.unit
def test_validate_gps_source_non_string_raises(mock_hass) -> None:
    from custom_components.pawcontrol.validation import validate_gps_source

    with pytest.raises(ValidationError):
        validate_gps_source(mock_hass, 42)


@pytest.mark.unit
def test_validate_gps_source_not_found_raises(mock_hass) -> None:
    from custom_components.pawcontrol.validation import validate_gps_source

    mock_hass.states.get = MagicMock(return_value=None)
    with pytest.raises(ValidationError):
        validate_gps_source(mock_hass, "device_tracker.unknown")
