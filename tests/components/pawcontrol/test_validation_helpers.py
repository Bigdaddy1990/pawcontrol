"""Tests for shared validation helper utilities."""

import pytest

from custom_components.pawcontrol.const import CONF_DOG_NAME
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


def test_normalise_existing_names_skips_invalid_values() -> None:
    """Name normalisation should lowercase, trim, and drop empty/non-string values."""
    assert normalise_existing_names({" Buddy ", "", "LUNA", "  "}) == {
        "buddy",
        "luna",
    }
    assert normalise_existing_names(None) == set()


def test_validate_unique_dog_name_handles_optional_and_duplicate_names() -> None:
    """Unique-name validation should pass optional values and reject duplicates."""
    assert validate_unique_dog_name("", required=False) is None

    assert (
        validate_unique_dog_name(" Buddy ", existing_names={"luna", "max"}) == "Buddy"
    )

    with pytest.raises(ValidationError, match="dog_name_already_exists"):
        validate_unique_dog_name(
            " Buddy ",
            existing_names={"buddy"},
            field=CONF_DOG_NAME,
        )


@pytest.mark.parametrize(
    ("constraint", "min_value", "max_value", "expected_message"),
    [
        ("coordinate_required", None, None, "latitude is required"),
        ("coordinate_not_numeric", None, None, "latitude must be a number"),
        (
            "coordinate_out_of_range",
            -90.0,
            90.0,
            "latitude must be between -90.0 and 90.0",
        ),
        ("coordinate_out_of_range", None, None, "latitude is out of range"),
        ("something_else", None, None, "latitude is invalid"),
    ],
)
def test_format_coordinate_validation_error_messages(
    constraint: str,
    min_value: float | None,
    max_value: float | None,
    expected_message: str,
) -> None:
    """Coordinate formatting should map each constraint to user-facing text."""
    error = ValidationError(
        "latitude",
        value="bad",
        constraint=constraint,
        min_value=min_value,
        max_value=max_value,
    )

    assert format_coordinate_validation_error(error) == expected_message


def test_validate_coordinate_pair_and_service_wrapper() -> None:
    """Coordinate pair helper should return floats and wrap service errors."""
    assert validate_coordinate_pair("48.8566", "2.3522") == (48.8566, 2.3522)

    with pytest.raises(ServiceValidationError, match="latitude must be a number"):
        validate_service_coordinates("abc", 2.3522)


def test_safe_validate_interval_returns_default_on_validation_errors() -> None:
    """safe_validate_interval should return validated value or default fallback."""
    assert (
        safe_validate_interval(
            "10",
            default=15,
            minimum=5,
            maximum=20,
            field="interval",
            clamp=False,
            required=False,
        )
        == 10
    )

    assert (
        safe_validate_interval(
            "not-a-number",
            default=15,
            minimum=5,
            maximum=20,
            field="interval",
            clamp=False,
            required=False,
        )
        == 15
    )
