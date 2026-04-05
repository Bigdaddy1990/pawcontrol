"""Tests for garden flow helper mixin coverage."""

import voluptuous as vol

from custom_components.pawcontrol.flows.garden import GardenModuleSelectorMixin
from custom_components.pawcontrol.selector_shim import selector


def test_build_garden_module_selector_returns_optional_boolean_selector() -> None:
    """Garden selector helper should wire optional boolean toggles."""
    mapping = GardenModuleSelectorMixin._build_garden_module_selector(
        field="enable_garden",
        default=True,
    )

    marker = next(iter(mapping))
    assert isinstance(marker, vol.Optional)
    assert marker.schema == "enable_garden"
    assert marker.default() is True
    assert isinstance(mapping[marker], selector.BooleanSelector)
