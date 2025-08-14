"""Tests for utility helpers."""

import math

from custom_components.pawcontrol.utils import validate_coordinates


def test_validate_coordinates_valid():
    """Valid latitude and longitude return True."""
    assert validate_coordinates(10.0, 20.0)


def test_validate_coordinates_invalid_bool():
    """Boolean values should be rejected."""
    assert not validate_coordinates(True, 0)  # type: ignore[arg-type]
    assert not validate_coordinates(0, False)  # type: ignore[arg-type]


def test_validate_coordinates_out_of_range():
    """Coordinates outside valid range are rejected."""
    assert not validate_coordinates(91.0, 0)
    assert not validate_coordinates(0, 181.0)


def test_validate_coordinates_non_finite():
    """NaN or infinite values are rejected."""
    assert not validate_coordinates(math.nan, 0)
    assert not validate_coordinates(0, math.inf)
