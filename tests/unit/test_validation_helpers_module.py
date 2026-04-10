"""Tests for :mod:`custom_components.pawcontrol.validation_helpers`."""

import pytest

from custom_components.pawcontrol.exceptions import (
    ServiceValidationError,
    ValidationError,
)
from custom_components.pawcontrol.validation_helpers import (
    format_coordinate_validation_error,
    normalise_existing_names,
    safe_validate_interval,
    validate_coordinate_pair,
    validate_service_coordinates,
    validate_unique_dog_name,
)


def test_normalise_existing_names_filters_and_normalises() -> None:
    assert normalise_existing_names({" Luna ", "MILO", "", "   "}) == {
        "luna",
        "milo",
    }
    assert normalise_existing_names(None) == set()


def test_validate_unique_dog_name_duplicate_and_optional_none() -> None:
    assert (
        validate_unique_dog_name(
            "  Bella ",
            existing_names={"luna", "MILO"},
        )
        == "Bella"
    )

    with pytest.raises(ValidationError) as err:
        validate_unique_dog_name("milo", existing_names={"Milo"})

    assert err.value.constraint == "dog_name_already_exists"
    assert validate_unique_dog_name(None, required=False) is None


def test_validate_coordinate_pair_and_service_wrapper() -> None:
    assert validate_coordinate_pair(47.6, -122.3) == pytest.approx((47.6, -122.3))

    with pytest.raises(ServiceValidationError, match="latitude must be between"):
        validate_service_coordinates(120, -122.3)


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        ("coordinate_required", "latitude is required"),
        ("coordinate_not_numeric", "latitude must be a number"),
        (
            "coordinate_out_of_range",
            "latitude must be between -90.0 and 90.0",
        ),
        ("unknown", "latitude is invalid"),
    ],
)
def test_format_coordinate_validation_error_messages(
    constraint: str,
    expected: str,
) -> None:
    error = ValidationError(
        "latitude",
        "bad",
        constraint,
        min_value=-90.0,
        max_value=90.0,
    )

    assert format_coordinate_validation_error(error) == expected


def test_safe_validate_interval_returns_default_on_validation_errors() -> None:
    assert (
        safe_validate_interval(
            30,
            field="interval",
            minimum=10,
            maximum=60,
            default=15,
        )
        == 30
    )

    assert (
        safe_validate_interval(
            "not-an-int",
            field="interval",
            minimum=10,
            maximum=60,
            default=15,
        )
        == 15
    )


def test_format_coordinate_validation_error_out_of_range_without_bounds() -> None:
    error = ValidationError("gps_latitude", "bad", "coordinate_out_of_range")

    assert format_coordinate_validation_error(error) == "gps latitude is out of range"


def test_validate_service_coordinates_raises_for_non_numeric_longitude() -> None:
    with pytest.raises(ServiceValidationError, match="longitude must be a number"):
        validate_service_coordinates(45.0, "west")
