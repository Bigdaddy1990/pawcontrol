"""Focused tests for selector shim compatibility helpers."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from custom_components.pawcontrol import selector_shim

MODULE_PATH = Path("custom_components/pawcontrol/selector_shim.py")


def _load_selector_shim_with_helpers(helpers_module: ModuleType) -> ModuleType:
    """Load selector shim with controlled ``homeassistant.helpers`` modules."""
    module_name = "tests_unit_selector_shim_fallback"
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


def test_selector_namespace_call_uses_selector_factory_when_callable() -> None:
    """Namespace call should delegate to selector factory when one is provided."""
    namespace = selector_shim._SelectorNamespace(
        selector=lambda config: {"wrapped": config}
    )

    assert namespace({"foo": "bar"}) == {"wrapped": {"foo": "bar"}}


def test_selector_namespace_call_returns_config_without_factory() -> None:
    """Namespace call should return original config when no factory is configured."""
    namespace = selector_shim._SelectorNamespace()

    payload = {"foo": "bar"}
    assert namespace(payload) is payload


def test_supports_selector_callables_returns_false_for_missing_symbols() -> None:
    """Support probe should reject namespaces without TextSelector APIs."""
    assert selector_shim._supports_selector_callables(SimpleNamespace()) is False


def test_supports_selector_callables_returns_false_for_non_callable_instance() -> None:
    """Support probe should reject selectors that do not return callable instances."""

    class TextSelector:
        def __init__(self, _config: object) -> None:
            pass

    module = SimpleNamespace(TextSelector=TextSelector, TextSelectorConfig=dict)

    assert selector_shim._supports_selector_callables(module) is False


def test_supports_selector_callables_returns_true_for_callable_instance() -> None:
    """Support probe should accept selectors that build callable validator objects."""

    class TextSelector:
        def __init__(self, _config: object) -> None:
            pass

        def __call__(self, value: object) -> object:
            return value

    module = SimpleNamespace(TextSelector=TextSelector, TextSelectorConfig=dict)

    assert selector_shim._supports_selector_callables(module) is True


def test_fallback_selector_exports_preserve_passthrough_semantics() -> None:
    """Fallback export should expose all selector shims and keep values unchanged."""
    module = _load_selector_shim_with_helpers(SimpleNamespace())

    selector = module.selector
    number_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.0,
            max=4.0,
            step="any",
            unit_of_measurement="kg",
            mode=selector.NumberSelectorMode.SLIDER,
            translation_key="weight",
        )
    )
    select_selector = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value="gps", label="GPS"), "manual"],
            multiple=True,
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="source",
            sort=True,
        )
    )
    text_selector = selector.TextSelector(
        selector.TextSelectorConfig(
            multiline=False,
            prefix="pre",
            suffix="suf",
            type=selector.TextSelectorType.EMAIL,
            autocomplete="email",
            multiple=False,
        )
    )

    assert selector({"foo": "bar"}) == {"foo": "bar"}
    assert number_selector(3) == 3
    assert select_selector("gps") == "gps"
    assert text_selector("dog@example.com") == "dog@example.com"
    assert (
        selector.TimeSelector(selector.TimeSelectorConfig())("12:34:56") == "12:34:56"
    )
    assert (
        selector.DateSelector(selector.DateSelectorConfig())("2026-04-01")
        == "2026-04-01"
    )
    assert selector.BooleanSelector(selector.BooleanSelectorConfig())(True) is True
    assert selector.Selector({"read_only": False})("raw") == "raw"
