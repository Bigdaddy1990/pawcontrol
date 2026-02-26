"""Tests for garden flow selector helpers."""

import voluptuous as vol

from custom_components.pawcontrol.flows.garden import GardenModuleSelectorMixin
from custom_components.pawcontrol.selector_shim import selector


def test_build_garden_module_selector_creates_boolean_optional_field() -> None:
    """Garden selector helper should expose an optional boolean selector."""
    selector_mapping = GardenModuleSelectorMixin._build_garden_module_selector(
        field="enable_garden",
        default=True,
    )

    assert len(selector_mapping) == 1
    optional_key, selector_value = next(iter(selector_mapping.items()))

    assert isinstance(optional_key, vol.Optional)
    assert optional_key.schema == "enable_garden"
    assert isinstance(selector_value, selector.BooleanSelector)

    schema = vol.Schema(selector_mapping)
    assert schema({}) == {"enable_garden": True}
    assert schema({"enable_garden": False}) == {"enable_garden": False}
