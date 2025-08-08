from pathlib import Path
import importlib.util
from unittest.mock import MagicMock

HELPERS_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "pawcontrol" / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", HELPERS_PATH)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)  # type: ignore[attr-defined]
ImprovedModuleManager = helpers.ImprovedModuleManager


def test_sanitize_name_slugifies_simple():
    hass = MagicMock()
    manager = ImprovedModuleManager(hass, None, None, {"dog_name": "Fido Mc Dog"})
    assert manager.dog_id == "fido_mc_dog"


def test_sanitize_name_special_chars():
    hass = MagicMock()
    manager = ImprovedModuleManager(hass, None, None, {"dog_name": "Ärger & Spaß"})
    assert manager.dog_id == "arger_spass"


def test_sanitize_name_invalid_returns_unknown():
    hass = MagicMock()
    manager = ImprovedModuleManager(hass, None, None, {"dog_name": "!@#$"})
    assert manager.dog_id == "unknown"
