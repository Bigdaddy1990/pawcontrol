"""Tests for garden flow selector helpers."""

import voluptuous as vol

from custom_components.pawcontrol.flows.garden import GardenModuleSelectorMixin


def test_build_garden_module_selector_uses_optional_boolean_selector() -> None:
    """The helper should create an optional field with the provided default."""
    selector_map = GardenModuleSelectorMixin._build_garden_module_selector(
        field="enable_garden_module",
        default=True,
    )

    assert len(selector_map) == 1

    marker = next(iter(selector_map))
    assert isinstance(marker, vol.Optional)
    assert str(marker.schema) == "enable_garden_module"
    assert marker.default() is True

    selector_value = selector_map[marker]
    assert selector_value.__class__.__name__ == "BooleanSelector"
    assert callable(selector_value)
