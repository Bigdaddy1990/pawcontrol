import asyncio
import importlib.util
import logging
import pathlib
import types
import sys

import pytest

# Stub Home Assistant module dependencies
homeassistant = types.ModuleType("homeassistant")
ha_const = types.ModuleType("homeassistant.const")


# Minimal homeassistant.util.logging stub for pytest plugin
ha_util = types.ModuleType("homeassistant.util")
ha_logging = types.ModuleType("homeassistant.util.logging")


def _log_exception(format_err, *args):
    """Dummy log_exception function for tests."""
    return None


ha_logging.log_exception = _log_exception
ha_util.logging = ha_logging


class Platform:
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    DATETIME = "datetime"
    DEVICE_TRACKER = "device_tracker"
    NUMBER = "number"
    SENSOR = "sensor"
    SELECT = "select"
    SWITCH = "switch"
    TEXT = "text"


ha_const.Platform = Platform
homeassistant.const = ha_const
homeassistant.util = ha_util
sys.modules["homeassistant"] = homeassistant
sys.modules["homeassistant.const"] = ha_const
sys.modules["homeassistant.util"] = ha_util
sys.modules["homeassistant.util.logging"] = ha_logging

# Set up package stubs for custom_components.pawcontrol
ROOT = pathlib.Path(__file__).resolve().parents[1]
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules["custom_components"] = custom_components

pawcontrol = types.ModuleType("custom_components.pawcontrol")
pawcontrol.__path__ = [str(ROOT / "custom_components" / "pawcontrol")]
sys.modules["custom_components.pawcontrol"] = pawcontrol

# Load const and utils modules explicitly to avoid executing package __init__
const_path = ROOT / "custom_components" / "pawcontrol" / "const.py"
const_spec = importlib.util.spec_from_file_location(
    "custom_components.pawcontrol.const",
    const_path,
)
const_mod = importlib.util.module_from_spec(const_spec)
const_spec.loader.exec_module(const_mod)
sys.modules["custom_components.pawcontrol.const"] = const_mod

utils_path = ROOT / "custom_components" / "pawcontrol" / "utils.py"
utils_spec = importlib.util.spec_from_file_location(
    "custom_components.pawcontrol.utils",
    utils_path,
)
utils_mod = importlib.util.module_from_spec(utils_spec)
utils_spec.loader.exec_module(utils_mod)
calculate_speed_kmh = utils_mod.calculate_speed_kmh
calculate_distance = utils_mod.calculate_distance
validate_coordinates = utils_mod.validate_coordinates
format_coordinates = utils_mod.format_coordinates
safe_service_call = utils_mod.safe_service_call


def test_calculate_speed_kmh_negative_distance():
    assert calculate_speed_kmh(-100.0, 10.0) == 0.0


def test_calculate_speed_kmh_positive():
    assert calculate_speed_kmh(100.0, 50.0) == pytest.approx(7.2)


def test_calculate_speed_kmh_zero_duration():
    assert calculate_speed_kmh(100.0, 0.0) == 0.0


def test_calculate_distance_variants():
    assert calculate_distance(0.0, 0.0, 0.0, 0.0) == 0.0
    assert calculate_distance(50.0, 10.0, 50.0, 10.1) > 0.0


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (10.0, 20.0, True),
        ("bad", 20.0, False),
        (True, 20.0, False),
        (100.0, 20.0, False),
    ],
)
def test_validate_coordinates(lat, lon, expected):
    assert validate_coordinates(lat, lon) is expected


def test_format_coordinates():
    assert format_coordinates(1.23456789, 9.87654321) == "1.234568,9.876543"


def test_safe_service_call(caplog):
    class DummyServices:
        def __init__(self):
            self.called = False

        async def async_call(self, domain, service, data, blocking=False):
            self.called = True
            if domain == "fail":
                raise ValueError

    class DummyHass:
        def __init__(self):
            self.services = DummyServices()

    hass = DummyHass()
    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(safe_service_call(hass, "test", "service"))
        assert hass.services.called
        assert not asyncio.run(safe_service_call(hass, "fail", "service"))
    assert "Service call failed for fail.service" in caplog.text
