"""Tests for config flow placeholder builders."""

from custom_components.pawcontrol.config_flow_placeholders import (
    _build_add_another_placeholders,
    _build_add_dog_summary_placeholders,
    _build_dog_modules_form_placeholders,
)
from custom_components.pawcontrol.types import (
    ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE,
    ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE,
    DOG_MODULES_SMART_DEFAULTS_TEMPLATE,
)


def test_build_add_dog_summary_placeholders_uses_expected_values() -> None:
    """Add-dog summary placeholders should coerce counts and keep discovery text."""
    placeholders = _build_add_dog_summary_placeholders(
        dogs_configured=2,
        max_dogs=5,
        discovery_hint="Use discovery for nearby trackers",
    )

    assert dict(placeholders) == {
        "dogs_configured": "2",
        "max_dogs": "5",
        "discovery_hint": "Use discovery for nearby trackers",
    }
    assert dict(ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE) == {
        "dogs_configured": "",
        "max_dogs": "",
        "discovery_hint": "",
    }


def test_build_dog_modules_form_placeholders_uses_smart_defaults() -> None:
    """Dog-module placeholders should include the current profile details."""
    placeholders = _build_dog_modules_form_placeholders(
        dog_name="Buddy",
        dogs_configured=1,
        smart_defaults="Auto-enable walk + weather",
    )

    assert dict(placeholders) == {
        "dog_name": "Buddy",
        "dogs_configured": "1",
        "smart_defaults": "Auto-enable walk + weather",
    }
    assert dict(DOG_MODULES_SMART_DEFAULTS_TEMPLATE) == {
        "dog_name": "",
        "dogs_configured": "",
        "smart_defaults": "",
    }


def test_build_add_another_placeholders_formats_add_more_toggle() -> None:
    """Add-another placeholders should expose yes/no based on add-more capability."""
    can_add_more = _build_add_another_placeholders(
        dogs_configured=3,
        dogs_list="Buddy, Luna, Max",
        can_add_more=True,
        max_dogs=4,
        performance_note="Balanced mode recommended",
    )
    at_limit = _build_add_another_placeholders(
        dogs_configured=4,
        dogs_list="Buddy, Luna, Max, Coco",
        can_add_more=False,
        max_dogs=4,
        performance_note="Limit reached",
    )

    assert dict(can_add_more) == {
        "dogs_configured": "3",
        "dogs_list": "Buddy, Luna, Max",
        "can_add_more": "yes",
        "max_dogs": "4",
        "performance_note": "Balanced mode recommended",
    }
    assert dict(at_limit) == {
        "dogs_configured": "4",
        "dogs_list": "Buddy, Luna, Max, Coco",
        "can_add_more": "no",
        "max_dogs": "4",
        "performance_note": "Limit reached",
    }
    assert dict(ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE) == {
        "dogs_configured": "",
        "dogs_list": "",
        "can_add_more": "",
        "max_dogs": "",
        "performance_note": "",
    }
