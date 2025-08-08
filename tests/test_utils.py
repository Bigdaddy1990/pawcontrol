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


def test_validate_dog_name_valid_characters():
    assert utils.validate_dog_name("Fido_Ä")


def test_validate_dog_name_invalid_characters():
    assert not utils.validate_dog_name("Bad*Name!")


def test_filter_invalid_modules_removes_unknown():
    modules = {"feeding": {"enabled": True}, "unknown": {"enabled": True}}
    filtered = utils.filter_invalid_modules(modules)
    assert "feeding" in filtered
    assert "unknown" not in filtered

def test_filter_invalid_modules_handles_non_dict():
    assert utils.filter_invalid_modules([]) == {}
    
def test_validate_dog_name_strips_whitespace():
    assert utils.validate_dog_name("  Fido  ")

def test_validate_dog_name_whitespace_only():
    assert not utils.validate_dog_name("   ")

def test_validate_dog_name_rejects_non_string():
    assert not utils.validate_dog_name(None)


def test_sanitize_entity_id_provides_fallback_for_empty_names():
    """Sanitized entity IDs should never be empty."""
    assert utils.sanitize_entity_id("!!!") == "unnamed"
