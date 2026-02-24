"""Tests for selector shim fallback behavior."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

MODULE_PATH = Path("custom_components/pawcontrol/selector_shim.py")


def _load_selector_shim_with_helpers(helpers_module: ModuleType) -> ModuleType:
    """Load the selector shim using a controlled ``homeassistant.helpers`` module."""
    module_name = "tests_selector_shim_under_test"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    old_homeassistant = sys.modules.get("homeassistant")
    old_helpers = sys.modules.get("homeassistant.helpers")

    try:
        homeassistant_module = ModuleType("homeassistant")
        homeassistant_module.helpers = helpers_module
        sys.modules["homeassistant"] = homeassistant_module
        sys.modules["homeassistant.helpers"] = helpers_module
        spec.loader.exec_module(module)
    finally:
        if old_homeassistant is None:
            sys.modules.pop("homeassistant", None)
        else:
            sys.modules["homeassistant"] = old_homeassistant

        if old_helpers is None:
            sys.modules.pop("homeassistant.helpers", None)
        else:
            sys.modules["homeassistant.helpers"] = old_helpers

    return module


def test_selector_namespace_uses_selector_factory_when_available() -> None:
    """The namespace ``__call__`` should delegate to a callable selector helper."""

    def text_selector(_: object) -> object:
        return lambda value: value

    selector_module = SimpleNamespace(
        TextSelector=text_selector,
        TextSelectorConfig=dict,
        selector=lambda config: {"wrapped": config},
    )
    module = _load_selector_shim_with_helpers(SimpleNamespace(selector=selector_module))

    result = module.selector({"foo": "bar"})

    assert result == {"wrapped": {"foo": "bar"}}


def test_selector_namespace_returns_config_without_selector_factory() -> None:
    """Fallback ``__call__`` should return config unchanged when no factory exists."""
    module = _load_selector_shim_with_helpers(SimpleNamespace())

    config = {"entity": "sensor.pawcontrol"}

    assert module.selector(config) is config


def test_supports_selector_callables_covers_failure_paths() -> None:
    """Validate selector callable detection when implementations are invalid."""
    module = _load_selector_shim_with_helpers(SimpleNamespace())

    assert not module._supports_selector_callables(SimpleNamespace())
    assert not module._supports_selector_callables(
        SimpleNamespace(TextSelector=object(), TextSelectorConfig=dict),
    )

    def raising_selector(_: object) -> object:
        raise ValueError("boom")

    assert not module._supports_selector_callables(
        SimpleNamespace(TextSelector=raising_selector, TextSelectorConfig=dict),
    )
