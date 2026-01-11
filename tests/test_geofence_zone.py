"""Unit tests for geofence zone validation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tests.helpers import install_homeassistant_stubs

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_package(name: str, path: Path) -> None:
    if name not in sys.modules:
        module = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(name, loader=None)
        )
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


install_homeassistant_stubs()
_ensure_package("custom_components", PROJECT_ROOT / "custom_components")
_ensure_package(
    "custom_components.pawcontrol",
    PROJECT_ROOT / "custom_components" / "pawcontrol",
)

geofencing = _load_module(
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
