"""Focused tests for selector shim compatibility helpers."""

from types import SimpleNamespace

from custom_components.pawcontrol import selector_shim


def test_selector_namespace_call_uses_selector_factory_when_callable() -> None:
    """Namespace call should delegate to selector factory when one is provided."""
    namespace = selector_shim._SelectorNamespace(selector=lambda config: {"wrapped": config})

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
