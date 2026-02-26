"""Unit tests for config flow placeholder helper builders."""

from types import MappingProxyType

import pytest

from custom_components.pawcontrol.config_flow_placeholders import (
    _build_add_another_placeholders,
    _build_add_dog_summary_placeholders,
    _build_dog_modules_form_placeholders,
)


def test_build_add_dog_summary_placeholders_sets_expected_values() -> None:
    placeholders = _build_add_dog_summary_placeholders(
        dogs_configured=2,
        max_dogs=5,
        discovery_hint="Found nearby tracker",
    )

    assert placeholders == {
        "dogs_configured": "2",
        "max_dogs": "5",
        "discovery_hint": "Found nearby tracker",
    }
    assert isinstance(placeholders, MappingProxyType)

    with pytest.raises(TypeError):
        placeholders["max_dogs"] = "7"  # type: ignore[index]


def test_build_dog_modules_form_placeholders_sets_expected_values() -> None:
    placeholders = _build_dog_modules_form_placeholders(
        dog_name="Luna",
        dogs_configured=3,
        smart_defaults="Enable geofence and meal reminders",
    )

    assert placeholders == {
        "dog_name": "Luna",
        "dogs_configured": "3",
        "smart_defaults": "Enable geofence and meal reminders",
    }


def test_build_add_another_placeholders_encodes_boolean_as_yes_no() -> None:
    can_add_more = _build_add_another_placeholders(
        dogs_configured=4,
        dogs_list="Luna, Milo, Nala, Koda",
        can_add_more=True,
        max_dogs=5,
        performance_note="One spot remains",
    )
    at_limit = _build_add_another_placeholders(
        dogs_configured=5,
        dogs_list="Luna, Milo, Nala, Koda, Nova",
        can_add_more=False,
        max_dogs=5,
        performance_note="Maximum reached",
    )

    assert can_add_more["can_add_more"] == "yes"
    assert at_limit["can_add_more"] == "no"
    assert can_add_more["max_dogs"] == "5"
    assert at_limit["dogs_configured"] == "5"
