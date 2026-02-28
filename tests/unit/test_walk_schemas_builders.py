"""Tests for walk schema builder helpers."""

import voluptuous as vol

from custom_components.pawcontrol.flows.walk_helpers import WALK_SETTINGS_FIELDS
from custom_components.pawcontrol.flows.walk_schemas import (
    build_auto_end_walks_field,
    build_walk_timing_schema_fields,
)
from custom_components.pawcontrol.types import DoorSensorSettingsConfig

(
    WALK_DETECTION_TIMEOUT_FIELD,
    MINIMUM_WALK_DURATION_FIELD,
    MAXIMUM_WALK_DURATION_FIELD,
    AUTO_END_WALKS_FIELD,
) = WALK_SETTINGS_FIELDS


def _marker_by_name(fields: dict[vol.Optional, object]) -> dict[str, vol.Optional]:
    """Map Optional marker names to marker instances."""
    return {str(marker.schema): marker for marker in fields}


def test_build_walk_timing_schema_fields_uses_defaults() -> None:
    """Walk timing schema should default to normalized settings config values."""
    defaults = DoorSensorSettingsConfig(
        walk_detection_timeout=320,
        minimum_walk_duration=180,
        maximum_walk_duration=720,
    )

    fields = build_walk_timing_schema_fields({}, defaults)
    markers = _marker_by_name(fields)

    assert markers[WALK_DETECTION_TIMEOUT_FIELD].default() == 320
    assert markers[MINIMUM_WALK_DURATION_FIELD].default() == 180
    assert markers[MAXIMUM_WALK_DURATION_FIELD].default() == 720


def test_build_walk_timing_schema_fields_prefers_submitted_values() -> None:
    """Walk timing schema should prefer values supplied by the caller."""
    defaults = DoorSensorSettingsConfig(
        walk_detection_timeout=300,
        minimum_walk_duration=150,
        maximum_walk_duration=800,
    )

    fields = build_walk_timing_schema_fields(
        {
            WALK_DETECTION_TIMEOUT_FIELD: 500,
            MINIMUM_WALK_DURATION_FIELD: 240,
            MAXIMUM_WALK_DURATION_FIELD: 3600,
        },
        defaults,
    )
    markers = _marker_by_name(fields)

    assert markers[WALK_DETECTION_TIMEOUT_FIELD].default() == 500
    assert markers[MINIMUM_WALK_DURATION_FIELD].default() == 240
    assert markers[MAXIMUM_WALK_DURATION_FIELD].default() == 3600


def test_build_auto_end_walks_field_prefers_submitted_value() -> None:
    """Auto-end walks schema field should use explicit flow value over defaults."""
    defaults = DoorSensorSettingsConfig(auto_end_walks=True)

    fields = build_auto_end_walks_field({AUTO_END_WALKS_FIELD: False}, defaults)
    markers = _marker_by_name(fields)

    assert markers[AUTO_END_WALKS_FIELD].default() is False

    fallback_fields = build_auto_end_walks_field({}, defaults)
    fallback_markers = _marker_by_name(fallback_fields)
    assert fallback_markers[AUTO_END_WALKS_FIELD].default() is True
