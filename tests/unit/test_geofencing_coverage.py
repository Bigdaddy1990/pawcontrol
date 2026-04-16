"""Targeted coverage tests for geofencing.py — pure helpers (0% → 22%+).

Covers: calculate_distance, validate_coordinates, validate_coordinate_pair, GPSLocation
"""

import pytest

from custom_components.pawcontrol.geofencing import (
    GPSLocation,
    calculate_distance,
    validate_coordinate_pair,
    validate_coordinates,
)

# ─── calculate_distance ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_calculate_distance_same_point() -> None:  # noqa: D103
    dist = calculate_distance(52.52, 13.40, 52.52, 13.40)
    assert dist == pytest.approx(0.0, abs=1e-6)


@pytest.mark.unit
def test_calculate_distance_known_pair() -> None:  # noqa: D103
    # Berlin to Munich ≈ 504 km
    dist = calculate_distance(52.52, 13.40, 48.14, 11.58)
    assert 480_000 < dist < 530_000


@pytest.mark.unit
def test_calculate_distance_is_symmetric() -> None:  # noqa: D103
    d1 = calculate_distance(52.52, 13.40, 48.14, 11.58)
    d2 = calculate_distance(48.14, 11.58, 52.52, 13.40)
    assert d1 == pytest.approx(d2, rel=1e-6)


@pytest.mark.unit
def test_calculate_distance_positive() -> None:  # noqa: D103
    dist = calculate_distance(0.0, 0.0, 1.0, 1.0)
    assert dist > 0


# ─── validate_coordinates ────────────────────────────────────────────────────


@pytest.mark.unit
def test_validate_coordinates_valid() -> None:  # noqa: D103
    assert validate_coordinates(52.52, 13.40) is True


@pytest.mark.unit
def test_validate_coordinates_edge_lat() -> None:  # noqa: D103
    assert validate_coordinates(90.0, 0.0) is True
    assert validate_coordinates(-90.0, 0.0) is True


@pytest.mark.unit
def test_validate_coordinates_invalid_lat() -> None:  # noqa: D103
    assert validate_coordinates(91.0, 0.0) is False


@pytest.mark.unit
def test_validate_coordinates_invalid_lon() -> None:  # noqa: D103
    assert validate_coordinates(0.0, 181.0) is False


@pytest.mark.unit
def test_validate_coordinates_zero() -> None:  # noqa: D103
    assert validate_coordinates(0.0, 0.0) is True


# ─── validate_coordinate_pair ────────────────────────────────────────────────


@pytest.mark.unit
def test_validate_coordinate_pair_valid() -> None:  # noqa: D103
    lat, lon = validate_coordinate_pair(52.52, 13.40)
    assert lat == pytest.approx(52.52)
    assert lon == pytest.approx(13.40)


@pytest.mark.unit
def test_validate_coordinate_pair_invalid_raises() -> None:  # noqa: D103
    with pytest.raises(Exception):  # noqa: B017
        validate_coordinate_pair(999.0, 13.40)


# ─── GPSLocation ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_gps_location_init() -> None:  # noqa: D103
    loc = GPSLocation(latitude=52.52, longitude=13.40)
    assert loc.latitude == pytest.approx(52.52)
    assert loc.longitude == pytest.approx(13.40)


@pytest.mark.unit
def test_gps_location_with_accuracy() -> None:  # noqa: D103
    loc = GPSLocation(latitude=48.14, longitude=11.58, accuracy=5.0)
    assert loc.accuracy == pytest.approx(5.0)


@pytest.mark.unit
def test_gps_location_defaults() -> None:  # noqa: D103
    loc = GPSLocation(latitude=0.0, longitude=0.0)
    assert loc.accuracy is None
    assert loc.altitude is None
