"""Unit tests for PawControl input validation helpers."""

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

validation = _load_module(
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
