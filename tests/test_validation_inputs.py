"""Unit tests for PawControl input validation helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import ensure_package, install_homeassistant_stubs, load_module

PROJECT_ROOT = Path(__file__).resolve().parents[1]


install_homeassistant_stubs()
ensure_package('custom_components', PROJECT_ROOT / 'custom_components')
ensure_package(
    'custom_components.pawcontrol',
    PROJECT_ROOT / 'custom_components' / 'pawcontrol',
)

validation = load_module(
    'custom_components.pawcontrol.validation',
    PROJECT_ROOT / 'custom_components' / 'pawcontrol' / 'validation.py',
)

InputValidator = validation.InputValidator
ValidationError = validation.ValidationError


def test_validate_gps_coordinates_success() -> None:
    latitude, longitude = InputValidator.validate_gps_coordinates(52.52, 13.405)
    assert latitude == pytest.approx(52.52)
    assert longitude == pytest.approx(13.405)


@pytest.mark.parametrize(
    ('latitude', 'longitude', 'field'),
    [
        (None, 13.4, 'latitude'),
        (91, 13.4, 'latitude'),
        (52.52, None, 'longitude'),
        (52.52, 181, 'longitude'),
    ],
)
def test_validate_gps_coordinates_invalid(
    latitude: float | None,
    longitude: float | None,
    field: str,
) -> None:
    with pytest.raises(ValidationError) as err:
        InputValidator.validate_gps_coordinates(latitude, longitude)

    assert err.value.field == field


@pytest.mark.parametrize(
    ('radius', 'field'),
    [
        (0, 'radius'),
        (5001, 'radius'),
    ],
)
def test_validate_geofence_radius_bounds(radius: float, field: str) -> None:
    assert InputValidator.validate_geofence_radius(50) == pytest.approx(50)

    with pytest.raises(ValidationError) as err:
        InputValidator.validate_geofence_radius(radius)

    assert err.value.field == field
