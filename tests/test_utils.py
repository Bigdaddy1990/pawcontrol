import importlib.util
import sys
import types
from pathlib import Path

import pytest

# Set up package structure for relative imports
BASE_PATH = Path(__file__).resolve().parent.parent / "custom_components" / "pawcontrol"

custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(BASE_PATH.parent)]
sys.modules["custom_components"] = custom_components

pawcontrol_pkg = types.ModuleType("custom_components.pawcontrol")
pawcontrol_pkg.__path__ = [str(BASE_PATH)]
sys.modules["custom_components.pawcontrol"] = pawcontrol_pkg

const_spec = importlib.util.spec_from_file_location(
    "custom_components.pawcontrol.const", BASE_PATH / "const.py"
)
const_mod = importlib.util.module_from_spec(const_spec)
const_spec.loader.exec_module(const_mod)
sys.modules["custom_components.pawcontrol.const"] = const_mod

utils_spec = importlib.util.spec_from_file_location(
    "custom_components.pawcontrol.utils", BASE_PATH / "utils.py"
)
utils = importlib.util.module_from_spec(utils_spec)
utils_spec.loader.exec_module(utils)


def test_calculate_distance_valid():
    dist = utils.calculate_distance(0, 0, 0, 1)
    assert dist == pytest.approx(111195, rel=1e-5)


def test_calculate_distance_invalid():
    assert utils.calculate_distance(91, 0, 0, 1) == 0.0
