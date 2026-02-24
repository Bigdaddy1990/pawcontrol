"""Regression tests for the Home Assistant selector compatibility shim."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import selector_shim
from custom_components.pawcontrol.selector_shim import selector


def test_number_selector_config_matches_expected_dict() -> None:
    """Ensure the fallback config mirrors Home Assistant's typed dict behaviour."""
    config = selector.NumberSelectorConfig(
        min=0.0,
        max=10.0,
        step=1,
        unit_of_measurement="kg",
        mode=selector.NumberSelectorMode.BOX,
    )

    assert isinstance(config, dict)
    assert config["min"] == 0.0
    assert config["mode"] is selector.NumberSelectorMode.BOX


def test_select_selector_accepts_string_sequence() -> None:
    """Verify the shim preserves string options when validating values."""
    options = ["gps", "manual"]
    config = selector.SelectSelectorConfig(options=options)

    instance = selector.SelectSelector(config)
    assert instance(config["options"][0]) == "gps"


def test_select_selector_accepts_typed_dict_sequence() -> None:
    """Ensure the shim stores typed dict option payloads without mutation."""
    options = [
        selector.SelectOptionDict(value="gps", label="GPS"),
        selector.SelectOptionDict(value="manual", label="Manual"),
    ]
    config = selector.SelectSelectorConfig(options=options)

    instance = selector.SelectSelector(config)
    assert instance(config["options"][1]["value"]) == "manual"


def test_fallback_does_not_expose_legacy_select_option() -> None:
    """Ensure the shim drops the legacy ``SelectOption`` dataclass."""
    if selector_shim.ha_selector is not None:  # pragma: no cover - passthrough env
        pytest.skip("Home Assistant selector module is available")

    assert not hasattr(selector, "SelectOption")
    assert hasattr(selector, "SelectOptionDict")


def test_text_selector_handles_expanded_type_set() -> None:
    """The shim should expose the same selector types as Home Assistant."""
    text_config = selector.TextSelectorConfig(
        type=selector.TextSelectorType.EMAIL,
        multiline=False,
    )

    text_selector = selector.TextSelector(text_config)
    assert text_selector("user@example.com") == "user@example.com"


def test_time_selector_passthrough() -> None:
    """Time selector should return the provided value without mutation."""
    time_selector = selector.TimeSelector(selector.TimeSelectorConfig())
    assert time_selector("12:00:00") == "12:00:00"


def test_boolean_selector_defaults_to_empty_config() -> None:
    """Boolean selector fallback should store an empty configuration dict."""
    selector_instance = selector.BooleanSelector()
    assert selector_instance.config == {}
    assert selector_instance(True) is True


def test_selector_namespace_is_callable() -> None:
    """The selector namespace should also accept schema shorthand calls."""
    config = {"boolean": {}}
    assert selector(config) == config


def test_selector_namespace_returns_config_when_factory_missing() -> None:
    """Namespace should return raw config when no callable factory exists."""
    namespace = selector_shim._SelectorNamespace(selector=None)

    config = {"text": {"type": "email"}}
    assert namespace(config) == config


def test_supports_selector_callables_success() -> None:
    """Detect callable selector helpers when instances are validators."""

    class _DummySelector:
        def __init__(self, _config: object) -> None:
            pass

        def __call__(self, value: object) -> object:
            return value

    module = SimpleNamespace(
        TextSelector=_DummySelector,
        TextSelectorConfig=lambda: {"multiple": False},
    )

    assert selector_shim._supports_selector_callables(module)


def test_supports_selector_callables_rejects_invalid_module() -> None:
    """Reject modules that cannot produce callable selector instances."""
    missing_attrs = SimpleNamespace()
    assert not selector_shim._supports_selector_callables(missing_attrs)

    exploding_module = SimpleNamespace(
        TextSelector=lambda _config: (_ for _ in ()).throw(TypeError("boom")),
        TextSelectorConfig=lambda: {},
    )
    assert not selector_shim._supports_selector_callables(exploding_module)
