"""Tests for utility helpers."""

import math

from custom_components.pawcontrol.utils import (
    calculate_distance,
    calculate_speed_kmh,
    validate_coordinates,
)

EARTH_RADIUS_M = 6_371_000.0


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


def test_calculate_distance_equator():
    """A one-degree shift at the equator has a known distance."""
    distance = calculate_distance(0.0, 0.0, 0.0, 1.0)
    expected = EARTH_RADIUS_M * math.pi / 180
    assert math.isclose(distance, expected, rel_tol=1e-6)


def test_calculate_speed_kmh():
    """Speed calculation converts m/s to km/h."""
    assert calculate_speed_kmh(1000.0, 3600.0) == 1.0
    assert calculate_speed_kmh(1000.0, 0.0) == 0.0
