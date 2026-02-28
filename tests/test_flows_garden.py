"""Tests for garden flow helper mixin."""

import voluptuous as vol

from custom_components.pawcontrol.flows.garden import GardenModuleSelectorMixin


def test_build_garden_module_selector_returns_expected_optional_mapping() -> None:
    selector_mapping = GardenModuleSelectorMixin._build_garden_module_selector(
        field="enable_garden_mode",
        default=True,
    )

    assert len(selector_mapping) == 1
    marker, selector_value = next(iter(selector_mapping.items()))

    assert isinstance(marker, vol.Optional)
    assert marker.schema == "enable_garden_mode"
    assert marker.default() is True
    assert selector_value.__class__.__name__ == "BooleanSelector"
