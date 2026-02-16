"""Regression tests for the Home Assistant selector compatibility shim."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol import selector_shim
from custom_components.pawcontrol.selector_shim import selector


def test_number_selector_config_matches_expected_dict() -> None:
  """Ensure the fallback config mirrors Home Assistant's typed dict behaviour."""  # noqa: E111

  config = selector.NumberSelectorConfig(  # noqa: E111
    min=0.0,
    max=10.0,
    step=1,
    unit_of_measurement="kg",
    mode=selector.NumberSelectorMode.BOX,
  )

  assert isinstance(config, dict)  # noqa: E111
  assert config["min"] == 0.0  # noqa: E111
  assert config["mode"] is selector.NumberSelectorMode.BOX  # noqa: E111


def test_select_selector_accepts_string_sequence() -> None:
  """Verify the shim preserves string options when validating values."""  # noqa: E111

  options = ["gps", "manual"]  # noqa: E111
  config = selector.SelectSelectorConfig(options=options)  # noqa: E111

  instance = selector.SelectSelector(config)  # noqa: E111
  assert instance(config["options"][0]) == "gps"  # noqa: E111


def test_select_selector_accepts_typed_dict_sequence() -> None:
  """Ensure the shim stores typed dict option payloads without mutation."""  # noqa: E111

  options = [  # noqa: E111
    selector.SelectOptionDict(value="gps", label="GPS"),
    selector.SelectOptionDict(value="manual", label="Manual"),
  ]
  config = selector.SelectSelectorConfig(options=options)  # noqa: E111

  instance = selector.SelectSelector(config)  # noqa: E111
  assert instance(config["options"][1]["value"]) == "manual"  # noqa: E111


def test_fallback_does_not_expose_legacy_select_option() -> None:
  """Ensure the shim drops the legacy ``SelectOption`` dataclass."""  # noqa: E111

  if (
    selector_shim.ha_selector is not None
  ):  # pragma: no cover - passthrough env  # noqa: E111
    pytest.skip("Home Assistant selector module is available")

  assert not hasattr(selector, "SelectOption")  # noqa: E111
  assert hasattr(selector, "SelectOptionDict")  # noqa: E111


def test_text_selector_handles_expanded_type_set() -> None:
  """The shim should expose the same selector types as Home Assistant."""  # noqa: E111

  text_config = selector.TextSelectorConfig(  # noqa: E111
    type=selector.TextSelectorType.EMAIL,
    multiline=False,
  )

  text_selector = selector.TextSelector(text_config)  # noqa: E111
  assert text_selector("user@example.com") == "user@example.com"  # noqa: E111


def test_time_selector_passthrough() -> None:
  """Time selector should return the provided value without mutation."""  # noqa: E111

  time_selector = selector.TimeSelector(selector.TimeSelectorConfig())  # noqa: E111
  assert time_selector("12:00:00") == "12:00:00"  # noqa: E111


def test_boolean_selector_defaults_to_empty_config() -> None:
  """Boolean selector fallback should store an empty configuration dict."""  # noqa: E111

  selector_instance = selector.BooleanSelector()  # noqa: E111
  assert selector_instance.config == {}  # noqa: E111
  assert selector_instance(True) is True  # noqa: E111


def test_selector_namespace_is_callable() -> None:
  """The selector namespace should also accept schema shorthand calls."""  # noqa: E111

  config = {"boolean": {}}  # noqa: E111
  assert selector(config) == config  # noqa: E111
