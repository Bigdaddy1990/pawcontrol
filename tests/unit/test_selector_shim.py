"""Regression tests for the Home Assistant selector compatibility shim."""

from __future__ import annotations

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
