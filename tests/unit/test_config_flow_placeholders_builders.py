"""Tests for config-flow placeholder builder helpers."""

from types import MappingProxyType

import pytest

from custom_components.pawcontrol import config_flow_placeholders as placeholders


def test_build_add_dog_summary_placeholders_sets_expected_values() -> None:  # noqa: D103
    result = placeholders._build_add_dog_summary_placeholders(
        dogs_configured=2,
        max_dogs=6,
        discovery_hint="Found via DHCP",
    )

    assert isinstance(result, MappingProxyType)
    assert result == {
        "dogs_configured": "2",
        "max_dogs": "6",
        "discovery_hint": "Found via DHCP",
    }


def test_build_dog_modules_form_placeholders_sets_expected_values() -> None:  # noqa: D103
    result = placeholders._build_dog_modules_form_placeholders(
        dog_name="Milo",
        dogs_configured=1,
        smart_defaults="Indoor profile",
    )

    assert isinstance(result, MappingProxyType)
    assert result == {
        "dog_name": "Milo",
        "dogs_configured": "1",
        "smart_defaults": "Indoor profile",
    }


def test_build_add_another_placeholders_formats_boolean_and_freezes() -> None:  # noqa: D103
    result = placeholders._build_add_another_placeholders(
        dogs_configured=3,
        dogs_list="Milo, Luna, Bella",
        can_add_more=False,
        max_dogs=4,
        performance_note="Adding more may slow updates",
    )

    assert isinstance(result, MappingProxyType)
    assert result["dogs_configured"] == "3"
    assert result["dogs_list"] == "Milo, Luna, Bella"
    assert result["can_add_more"] == "no"
    assert result["max_dogs"] == "4"
    assert result["performance_note"] == "Adding more may slow updates"


def test_build_add_another_placeholders_marks_can_add_more_yes() -> None:  # noqa: D103
    result = placeholders._build_add_another_placeholders(
        dogs_configured=1,
        dogs_list="Milo",
        can_add_more=True,
        max_dogs=4,
        performance_note="Fast path",
    )

    assert result["can_add_more"] == "yes"


def test_build_add_dog_summary_placeholders_returns_immutable_mapping() -> None:  # noqa: D103
    result = placeholders._build_add_dog_summary_placeholders(
        dogs_configured=1,
        max_dogs=3,
        discovery_hint="Manual setup",
    )

    with pytest.raises(TypeError):
        result["dogs_configured"] = "2"  # type: ignore[misc]
