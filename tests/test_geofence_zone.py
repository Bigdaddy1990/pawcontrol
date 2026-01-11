"""Unit tests for geofence zone validation."""

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

geofencing = load_module(
    "custom_components.pawcontrol.geofencing",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "geofencing.py",
)

GeofenceZone = geofencing.GeofenceZone
GeofenceType = geofencing.GeofenceType


def test_geofence_zone_accepts_valid_coordinates() -> None:
    zone = GeofenceZone(
        id="home",
        name="Home",
        type=GeofenceType.HOME_ZONE,
        latitude=52.52,
        longitude=13.405,
        radius=50,
    )

    assert zone.name == "Home"


@pytest.mark.parametrize(
    "latitude,longitude",
    [(-91, 10), (91, 10), (10, -181), (10, 181)],
)
def test_geofence_zone_rejects_invalid_coordinates(
    latitude: float, longitude: float
) -> None:
    with pytest.raises(ValueError):
        GeofenceZone(
            id="bad",
            name="Bad",
            type=GeofenceType.SAFE_ZONE,
            latitude=latitude,
            longitude=longitude,
            radius=50,
        )


def test_geofence_zone_rejects_invalid_radius() -> None:
    with pytest.raises(ValueError):
        GeofenceZone(
            id="bad-radius",
            name="Bad radius",
            type=GeofenceType.SAFE_ZONE,
            latitude=52.52,
            longitude=13.405,
            radius=1,
        )
