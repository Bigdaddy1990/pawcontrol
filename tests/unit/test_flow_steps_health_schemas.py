"""Tests for health flow schema builders."""

import voluptuous as vol

from custom_components.pawcontrol.const import MODULE_MEDICATION
from custom_components.pawcontrol.flow_steps.health_schemas import (
    build_dog_health_schema,
    build_health_settings_schema,
)


def _find_marker(schema: vol.Schema, key_name: str) -> vol.Marker:
    for marker in schema.schema:
        if isinstance(marker, vol.Marker) and marker.schema == key_name:
            return marker
    raise AssertionError(f"Schema marker {key_name!r} not found")


def test_build_dog_health_schema_includes_dynamic_defaults_and_medication() -> None:
    """Dog health schema includes dynamic diet defaults and medication controls."""
    schema = build_dog_health_schema(
        dog_age=9,
        dog_size="large",
        suggested_ideal_weight=28.5,
        suggested_activity="moderate",
        modules={MODULE_MEDICATION: True},
    )

    assert _find_marker(schema, "senior_formula").default() is True
    assert _find_marker(schema, "joint_support").default() is True
    assert _find_marker(schema, "puppy_formula").default() is False
    assert _find_marker(schema, "medication_1_name")
    assert _find_marker(schema, "medication_2_frequency")


def test_build_dog_health_schema_without_medication_omits_medication_fields() -> None:
    """Medication fields are absent when module is disabled."""
    schema = build_dog_health_schema(
        dog_age=1,
        dog_size="small",
        suggested_ideal_weight=4.2,
        suggested_activity="high",
        modules={MODULE_MEDICATION: False},
    )

    assert _find_marker(schema, "puppy_formula").default() is True
    assert _find_marker(schema, "joint_support").default() is False
    assert "medication_1_name" not in {marker.schema for marker in schema.schema}


def test_build_health_settings_schema_prefers_user_input_defaults() -> None:
    """Settings schema defaults should prefer user input over stored values."""
    schema = build_health_settings_schema(
        {
            "weight_tracking": True,
            "medication_reminders": False,
            "vet_reminders": True,
            "grooming_reminders": True,
            "health_alerts": False,
        },
        {
            "weight_tracking": False,
            "health_alerts": True,
        },
    )

    assert _find_marker(schema, "weight_tracking").default() is False
    assert _find_marker(schema, "medication_reminders").default() is False
    assert _find_marker(schema, "health_alerts").default() is True
