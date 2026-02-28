"""Tests for walk schema builder helpers."""

import voluptuous as vol

from custom_components.pawcontrol.flows.walk_schemas import (
    build_auto_end_walks_field,
    build_walk_timing_schema_fields,
)
from custom_components.pawcontrol.types import DoorSensorSettingsConfig


def _markers_by_name(
    schema_fields: dict[vol.Optional, object],
) -> dict[str, vol.Marker]:
    """Map schema field marker names to marker objects."""
    return {str(marker.schema): marker for marker in schema_fields}


def test_build_walk_timing_schema_fields_uses_defaults_without_overrides() -> None:
    """Timing schema should use defaults when values are absent."""
    defaults = DoorSensorSettingsConfig(
        walk_detection_timeout=420,
        minimum_walk_duration=240,
        maximum_walk_duration=3600,
    )

    fields = build_walk_timing_schema_fields({}, defaults)
    markers = _markers_by_name(fields)

    assert markers["walk_detection_timeout"].default() == 420
    assert markers["minimum_walk_duration"].default() == 240
    assert markers["maximum_walk_duration"].default() == 3600

    timeout_selector = fields[markers["walk_detection_timeout"]]
    assert timeout_selector.config["min"] == 30
    assert timeout_selector.config["max"] == 21600
    assert timeout_selector.config["step"] == 30
    assert timeout_selector.config["unit_of_measurement"] == "seconds"


def test_build_walk_timing_schema_fields_prefers_runtime_values() -> None:
    """Timing schema should prioritize runtime values over defaults."""
    defaults = DoorSensorSettingsConfig(
        walk_detection_timeout=420,
        minimum_walk_duration=240,
        maximum_walk_duration=3600,
    )

    fields = build_walk_timing_schema_fields(
        {
            "walk_detection_timeout": 900,
            "minimum_walk_duration": 300,
            "maximum_walk_duration": 5400,
        },
        defaults,
    )
    markers = _markers_by_name(fields)

    assert markers["walk_detection_timeout"].default() == 900
    assert markers["minimum_walk_duration"].default() == 300
    assert markers["maximum_walk_duration"].default() == 5400


def test_build_auto_end_walks_field_prefers_values_and_falls_back_to_defaults() -> None:
    """Auto-end toggle should use explicit values and fallback defaults."""
    defaults = DoorSensorSettingsConfig(auto_end_walks=False)

    explicit_fields = build_auto_end_walks_field({"auto_end_walks": True}, defaults)
    explicit_markers = _markers_by_name(explicit_fields)
    assert explicit_markers["auto_end_walks"].default() is True

    fallback_fields = build_auto_end_walks_field({}, defaults)
    fallback_markers = _markers_by_name(fallback_fields)
    assert fallback_markers["auto_end_walks"].default() is False
