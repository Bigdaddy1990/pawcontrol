"""Unit tests for shared validation helper utilities."""

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


def test_normalise_existing_names_filters_and_normalises_values() -> None:
    names = {"  Luna  ", "", "MILO", "   ", 123}

    assert normalise_existing_names(names) == {"luna", "milo"}


def test_validate_unique_dog_name_detects_duplicates_case_insensitive() -> None:
    with pytest.raises(ValidationError) as err:
        validate_unique_dog_name("Luna", existing_names={" luna "})

    assert err.value.constraint == "dog_name_already_exists"


def test_validate_unique_dog_name_allows_optional_empty_name() -> None:
    assert (
        validate_unique_dog_name(None, required=False, existing_names={"luna"}) is None
    )


def test_validate_coordinate_pair_returns_validated_float_values() -> None:
    latitude, longitude = validate_coordinate_pair("52.52", "13.405")

    assert latitude == pytest.approx(52.52)
    assert longitude == pytest.approx(13.405)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            ValidationError("latitude", None, "coordinate_required"),
            "latitude is required",
        ),
        (
            ValidationError("longitude", "x", "coordinate_not_numeric"),
            "longitude must be a number",
        ),
        (
            ValidationError(
                "latitude",
                200,
                "coordinate_out_of_range",
                min_value=-90,
                max_value=90,
            ),
            "latitude must be between -90 and 90",
        ),
        (
            ValidationError("latitude", 200, "coordinate_out_of_range"),
            "latitude is out of range",
        ),
        (
            ValidationError("gps_latitude", object(), "unexpected"),
            "gps latitude is invalid",
        ),
    ],
)
def test_format_coordinate_validation_error_messages(
    error: ValidationError,
    expected: str,
) -> None:
    assert format_coordinate_validation_error(error) == expected


def test_validate_service_coordinates_wraps_validation_error() -> None:
    with pytest.raises(ServiceValidationError, match="latitude must be a number"):
        validate_service_coordinates("bad", 10)


def test_safe_validate_interval_returns_default_on_validation_error() -> None:
    assert (
        safe_validate_interval(
            "bad",
            default=30,
            minimum=5,
            maximum=120,
            field="gps_interval",
            required=True,
        )
        == 30
    )


def test_safe_validate_interval_returns_validated_interval() -> None:
    assert (
        safe_validate_interval(
            45,
            default=30,
            minimum=5,
            maximum=120,
            field="gps_interval",
        )
        == 45
    )
