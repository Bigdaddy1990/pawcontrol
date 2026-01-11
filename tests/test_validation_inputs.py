"""Unit tests for PawControl input validation helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import ensure_package, install_homeassistant_stubs, load_module

PROJECT_ROOT = Path(__file__).resolve().parents[1]


install_homeassistant_stubs()
ensure_package("custom_components", PROJECT_ROOT / "custom_components")
ensure_package(
    "custom_components.pawcontrol",
    PROJECT_ROOT / "custom_components" / "pawcontrol",
)

validation = load_module(
    "custom_components.pawcontrol.validation",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "validation.py",
)

InputValidator = validation.InputValidator
ValidationError = validation.ValidationError


def test_validate_gps_coordinates_success() -> None:
    latitude, longitude = InputValidator.validate_gps_coordinates(52.52, 13.405)
    assert latitude == pytest.approx(52.52)
    assert longitude == pytest.approx(13.405)


def test_validate_gps_coordinates_missing_latitude() -> None:
    with pytest.raises(ValidationError) as err:
        InputValidator.validate_gps_coordinates(None, 13.4)

    assert err.value.field == "latitude"


def test_validate_gps_coordinates_invalid_longitude() -> None:
    with pytest.raises(ValidationError) as err:
        InputValidator.validate_gps_coordinates(52.52, 181)

    assert err.value.field == "longitude"


def test_validate_geofence_radius_bounds() -> None:
    assert InputValidator.validate_geofence_radius(50) == pytest.approx(50)

    with pytest.raises(ValidationError) as err:
        InputValidator.validate_geofence_radius(0)

    assert err.value.field == "radius"
