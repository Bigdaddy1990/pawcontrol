"""Regression tests for PawControl validation helpers."""

import pytest

from custom_components.pawcontrol.validation import InputValidator, ValidationError


def test_validate_age_months_rejects_fractional_string() -> None:
    """Age validation should reject fractional month strings."""  # noqa: E111

    with pytest.raises(ValidationError) as err:  # noqa: E111
        InputValidator.validate_age_months("2.5", required=True)

    assert err.value.field == "age_months"  # noqa: E111
    assert err.value.constraint == "Must be a whole number"  # noqa: E111


def test_validate_weight_rejects_boolean() -> None:
    """Weight validation should reject boolean input."""  # noqa: E111

    with pytest.raises(ValidationError) as err:  # noqa: E111
        InputValidator.validate_weight(True)

    assert err.value.field == "weight"  # noqa: E111
    assert err.value.constraint == "Must be numeric"  # noqa: E111
