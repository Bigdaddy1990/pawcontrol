"""Unit tests for GPS flow helper utilities."""

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.flow_steps.gps_helpers import (
    build_dog_gps_placeholders,
    build_gps_source_options,
    validation_error_key,
)
from custom_components.pawcontrol.types import DOG_GPS_PLACEHOLDERS_TEMPLATE


def test_validation_error_key_prefers_constraint() -> None:
    """A set constraint should be used as translation key."""
    error = ValidationError("gps", value="invalid", constraint="gps_invalid")

    assert validation_error_key(error, "fallback_key") == "gps_invalid"


def test_validation_error_key_uses_fallback_when_constraint_is_missing() -> None:
    """The provided fallback should be returned when constraint is empty."""
    error = ValidationError("gps", value="invalid")

    assert validation_error_key(error, "fallback_key") == "fallback_key"


def test_build_gps_source_options_uses_defaults_when_no_sources() -> None:
    """Without discovered sources, only push defaults and manual should exist."""
    assert build_gps_source_options({}) == {
        "webhook": "Webhook (Push)",
        "mqtt": "MQTT (Push)",
        "manual": "Manual Location Entry",
    }


def test_build_gps_source_options_extends_custom_sources() -> None:
    """Discovered sources should be preserved and augmented with defaults."""
    options = build_gps_source_options({"ha_tracker": "Home Assistant Tracker"})

    assert options == {
        "ha_tracker": "Home Assistant Tracker",
        "webhook": "Webhook (Push)",
        "mqtt": "MQTT (Push)",
        "manual": "Manual Location Entry",
    }


def test_build_dog_gps_placeholders_returns_immutable_copy() -> None:
    """Dog GPS placeholders should be frozen and avoid mutating the template."""
    placeholders = build_dog_gps_placeholders(dog_name="Luna")

    assert placeholders["dog_name"] == "Luna"
    assert DOG_GPS_PLACEHOLDERS_TEMPLATE["dog_name"] == ""

    mutable_copy = dict(placeholders)
    mutable_copy["dog_name"] = "Nova"

    assert placeholders["dog_name"] == "Luna"
