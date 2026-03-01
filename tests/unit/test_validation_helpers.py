"""Unit tests for shared validation helpers."""

from datetime import time as dt_time

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
    InputCoercionError,
    _is_empty,
    _parse_time_string,
    coerce_float,
    coerce_int,
    normalize_dog_id,
    validate_coordinate,
    validate_dog_name,
    validate_float_range,
    validate_interval,
)


def test_validate_dog_name_trims_and_accepts() -> None:
    assert validate_dog_name("  Luna ") == "Luna"


def test_validate_dog_name_rejects_non_string() -> None:
    with pytest.raises(ValidationError) as err:
        validate_dog_name(123)

    assert err.value.field == "dog_name"


def test_validate_coordinate_bounds() -> None:
    assert validate_coordinate(
        52.52, field="latitude", minimum=-90.0, maximum=90.0
    ) == pytest.approx(52.52)

    with pytest.raises(ValidationError) as err:
        validate_coordinate(181, field="longitude", minimum=-180.0, maximum=180.0)

    assert err.value.field == "longitude"


def test_validate_interval_clamps() -> None:
    assert (
        validate_interval(2, field="interval", minimum=5, maximum=10, clamp=True) == 5
    )
    assert (
        validate_interval(12, field="interval", minimum=5, maximum=10, clamp=True) == 10
    )


def test_validate_float_range_defaults_and_rejects() -> None:
    assert validate_float_range(
        None,
        field="accuracy",
        minimum=1.0,
        maximum=10.0,
        default=5.0,
    ) == pytest.approx(5.0)

    with pytest.raises(ValidationError):
        validate_float_range(
            "bad",
            field="accuracy",
            minimum=1.0,
            maximum=10.0,
        )


def test_normalize_dog_id_normalizes_and_handles_none() -> None:
    assert normalize_dog_id(None) == ""
    assert normalize_dog_id("  Luna Bella ") == "luna_bella"


def test_normalize_dog_id_rejects_non_strings() -> None:
    with pytest.raises(InputCoercionError) as err:
        normalize_dog_id(42)

    assert err.value.field == "dog_id"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", True),
        ("   ", True),
        (None, True),
        ("ready", False),
    ],
)
def test_is_empty(value: object, expected: bool) -> None:
    assert _is_empty(value) is expected


def test_parse_time_string_normalizes_multiple_input_types() -> None:
    assert _parse_time_string("start", None, "invalid") is None
    assert _parse_time_string("start", "  ", "invalid") is None
    assert _parse_time_string("start", dt_time(6, 30), "invalid") == "06:30:00"
    assert _parse_time_string("start", "06:30", "invalid") == "06:30:00"


@pytest.mark.parametrize("value", [42, "invalid-time"])
def test_parse_time_string_rejects_invalid_input(value: object) -> None:
    with pytest.raises(ValidationError) as err:
        _parse_time_string("start", value, "invalid_time")

    assert err.value.field == "start"


def test_coerce_float_handles_numeric_and_strips_strings() -> None:
    assert coerce_float("weight", 7) == pytest.approx(7.0)
    assert coerce_float("weight", " 7.5 ") == pytest.approx(7.5)


@pytest.mark.parametrize("value", [True, "", "dog", object()])
def test_coerce_float_rejects_non_numeric_values(value: object) -> None:
    with pytest.raises(InputCoercionError):
        coerce_float("weight", value)


def test_coerce_int_accepts_integer_like_inputs() -> None:
    assert coerce_int("count", 4) == 4
    assert coerce_int("count", 4.0) == 4
    assert coerce_int("count", " 4 ") == 4
    assert coerce_int("count", "4.0") == 4


@pytest.mark.parametrize("value", [True, 4.2, "", "4.2", "dog", object()])
def test_coerce_int_rejects_fractional_or_non_numeric(value: object) -> None:
    with pytest.raises(InputCoercionError):
        coerce_int("count", value)
