"""Tests for walk schema builders."""

from typing import Any

import voluptuous as vol

from custom_components.pawcontrol.flows.walk_schemas import (
    build_auto_end_walks_field,
    build_walk_timing_schema_fields,
)
from custom_components.pawcontrol.types import DoorSensorSettingsConfig


def _optional_by_name(fields: dict[vol.Optional, object]) -> dict[str, vol.Optional]:
    """Index voluptuous optional keys by their schema name."""
    return {str(optional.schema): optional for optional in fields}


def test_build_walk_timing_schema_fields_uses_defaults_and_overrides() -> None:
    """Timing fields should use defaults when missing and submitted values otherwise."""
    defaults = DoorSensorSettingsConfig(
        walk_detection_timeout=300,
        minimum_walk_duration=180,
        maximum_walk_duration=7200,
    )

    fields = build_walk_timing_schema_fields(
        {
            "walk_detection_timeout": 900,
            "maximum_walk_duration": 8100,
        },
        defaults,
    )

    keyed_optionals = _optional_by_name(fields)
    assert set(keyed_optionals) == {
        "walk_detection_timeout",
        "minimum_walk_duration",
        "maximum_walk_duration",
    }

    assert keyed_optionals["walk_detection_timeout"].default() == 900
    assert keyed_optionals["minimum_walk_duration"].default() == 180
    assert keyed_optionals["maximum_walk_duration"].default() == 8100

    timeout_selector = fields[keyed_optionals["walk_detection_timeout"]]
    minimum_selector = fields[keyed_optionals["minimum_walk_duration"]]
    maximum_selector = fields[keyed_optionals["maximum_walk_duration"]]

    for selector_obj in (timeout_selector, minimum_selector, maximum_selector):
        config: dict[str, Any] = selector_obj.config
        assert config["mode"] == "box"
        assert config["unit_of_measurement"] == "seconds"

    assert timeout_selector.config["min"] == 30
    assert timeout_selector.config["max"] == 21600
    assert timeout_selector.config["step"] == 30

    assert minimum_selector.config["min"] == 60
    assert minimum_selector.config["max"] == 21600
    assert minimum_selector.config["step"] == 30

    assert maximum_selector.config["min"] == 120
    assert maximum_selector.config["max"] == 43200
    assert maximum_selector.config["step"] == 60


def test_build_auto_end_walks_field_uses_value_and_default() -> None:
    """Auto-end selector should prefer provided value and fall back to defaults."""
    defaults = DoorSensorSettingsConfig(auto_end_walks=False)

    field_from_defaults = build_auto_end_walks_field({}, defaults)
    default_optional = next(iter(field_from_defaults))
    assert str(default_optional.schema) == "auto_end_walks"
    assert default_optional.default() is False
    assert field_from_defaults[default_optional].config == {}

    field_from_values = build_auto_end_walks_field(
        {"auto_end_walks": True},
        defaults,
    )
    value_optional = next(iter(field_from_values))
    assert value_optional.default() is True
