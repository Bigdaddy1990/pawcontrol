"""Additional coverage tests for shared validation helpers."""

from typing import cast

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


def test_normalise_existing_names_filters_blank_and_non_strings() -> None:
    """Existing names should be trimmed, lowercased, and de-duplicated."""
    raw_names: set[object] = {"  Luna ", "LUNA", "", "  ", 123}
    # ``normalise_existing_names`` is typed for persisted string sets, but this
    # regression test intentionally mixes in a non-string value to confirm the
    # helper safely filters malformed data before normalising names.
    result = normalise_existing_names(cast("set[str]", raw_names))

    assert result == {"luna"}
    assert 123 not in result
    assert normalise_existing_names(None) == set()


def test_validate_unique_dog_name_accepts_optional_missing_name() -> None:
    """Optional dog names should return ``None`` when omitted."""
    assert validate_unique_dog_name("   ", required=False) is None


def test_validate_unique_dog_name_rejects_case_insensitive_duplicates() -> None:
    """Duplicate names should raise the integration validation error."""
    with pytest.raises(ValidationError) as err:
        validate_unique_dog_name("Luna", existing_names={" luna ", "Milo"})

    assert err.value.field == "dog_name"
    assert err.value.constraint == "dog_name_already_exists"


def test_validate_coordinate_pair_supports_custom_field_names() -> None:
    """Coordinate validation should pass custom field labels through errors."""
    assert validate_coordinate_pair("52.52", "13.405") == pytest.approx((52.52, 13.405))

    with pytest.raises(ValidationError) as err:
        validate_coordinate_pair(95, 13.405, latitude_field="home_lat")

    assert err.value.field == "home_lat"
    assert err.value.constraint == "coordinate_out_of_range"


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (
            ValidationError("latitude", None, "coordinate_required"),
            "latitude is required",
        ),
        (
            ValidationError("longitude", "bad", "coordinate_not_numeric"),
            "longitude must be a number",
        ),
        (
            ValidationError(
                "gps_latitude",
                95,
                "coordinate_out_of_range",
                min_value=-90.0,
                max_value=90.0,
            ),
            "gps latitude must be between -90.0 and 90.0",
        ),
        (
            ValidationError("longitude", 181, "coordinate_out_of_range"),
            "longitude is out of range",
        ),
        (
            ValidationError("gps_latitude", "bad", "unexpected"),
            "gps latitude is invalid",
        ),
    ],
)
def test_format_coordinate_validation_error_branches(
    error: ValidationError,
    expected_message: str,
) -> None:
    """Formatting should produce user-friendly messages for each branch."""
    assert format_coordinate_validation_error(error) == expected_message


def test_validate_service_coordinates_wraps_validation_errors() -> None:
    """Service validation should translate coordinate errors to HA service errors."""
    # The wrapped message should stay aligned with the user-facing formatter
    # branch for non-numeric latitude values.
    with pytest.raises(ServiceValidationError, match="latitude must be a number"):
        validate_service_coordinates("bad", 13.405)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("15", 15),
        (None, 30),
        ("bad", 30),
    ],
)
def test_safe_validate_interval_returns_default_on_validation_errors(
    value: object,
    expected: int,
) -> None:
    """Interval validation should fall back to the provided default on errors."""
    assert (
        safe_validate_interval(
            value,
            default=30,
            minimum=5,
            maximum=60,
            field="refresh_interval",
        )
        == expected
    )
