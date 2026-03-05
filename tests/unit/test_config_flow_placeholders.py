"""Unit tests for config flow placeholder helper builders."""

from types import MappingProxyType

import pytest

from custom_components.pawcontrol.config_flow_placeholders import (
    _build_add_another_placeholders,
    _build_add_dog_summary_placeholders,
    _build_dog_modules_form_placeholders,
)


def test_build_add_dog_summary_placeholders_returns_frozen_mapping() -> None:
    """The add-dog placeholder helper should stringify counts and freeze output."""
    placeholders = _build_add_dog_summary_placeholders(
        dogs_configured=2,
        max_dogs=5,
        discovery_hint="Detected by BLE",
    )

    assert dict(placeholders) == {
        "dogs_configured": "2",
        "max_dogs": "5",
        "discovery_hint": "Detected by BLE",
    }
    assert isinstance(placeholders, MappingProxyType)

    with pytest.raises(TypeError):
        placeholders["dogs_configured"] = "3"  # type: ignore[index]


def test_build_dog_modules_form_placeholders_applies_inputs() -> None:
    """The modules helper should map all provided values."""
    placeholders = _build_dog_modules_form_placeholders(
        dog_name="Luna",
        dogs_configured=1,
        smart_defaults="Use medium dog defaults",
    )

    assert dict(placeholders) == {
        "dog_name": "Luna",
        "dogs_configured": "1",
        "smart_defaults": "Use medium dog defaults",
    }


def test_build_add_another_placeholders_formats_boolean_flag() -> None:
    """The helper should translate booleans to yes/no for translations."""
    placeholders_yes = _build_add_another_placeholders(
        dogs_configured=3,
        dogs_list="Luna, Milo, Koda",
        can_add_more=True,
        max_dogs=4,
        performance_note="Balanced mode",
    )
    placeholders_no = _build_add_another_placeholders(
        dogs_configured=4,
        dogs_list="Luna, Milo, Koda, Nova",
        can_add_more=False,
        max_dogs=4,
        performance_note="Limit reached",
    )

    assert placeholders_yes["can_add_more"] == "yes"
    assert placeholders_no["can_add_more"] == "no"
    assert dict(placeholders_yes) == {
        "dogs_configured": "3",
        "dogs_list": "Luna, Milo, Koda",
        "can_add_more": "yes",
        "max_dogs": "4",
        "performance_note": "Balanced mode",
    }
