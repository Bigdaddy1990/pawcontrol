"""Tests for GPS flow helper utilities."""

from types import MappingProxyType

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.flow_steps.gps_helpers import (
    build_dog_gps_placeholders,
    build_gps_source_options,
    validation_error_key,
)


def test_validation_error_key_prefers_constraint() -> None:
    """Constraint identifiers should be used when available."""
    error = ValidationError("latitude", value="bad", constraint="invalid_latitude")

    assert validation_error_key(error, fallback="default_key") == "invalid_latitude"


def test_validation_error_key_uses_fallback_without_constraint() -> None:
    """Fallback keys should be returned when no constraint is attached."""
    error = ValidationError("latitude", value="bad")

    assert validation_error_key(error, fallback="default_key") == "default_key"


def test_build_dog_gps_placeholders_returns_immutable_mapping() -> None:
    """Dog placeholders should include the dog name and remain immutable."""
    placeholders = build_dog_gps_placeholders(dog_name="Luna")

    assert placeholders["dog_name"] == "Luna"
    assert isinstance(placeholders, MappingProxyType)


def test_build_gps_source_options_includes_manual_and_push_defaults() -> None:
    """GPS source options should preserve custom values and append defaults."""
    options = build_gps_source_options({"traccar": "Traccar (Pull)"})

    assert options == {
        "traccar": "Traccar (Pull)",
        "webhook": "Webhook (Push)",
        "mqtt": "MQTT (Push)",
        "manual": "Manual Location Entry",
    }


def test_build_gps_source_options_returns_defaults_without_sources() -> None:
    """When no sources exist only push defaults and manual entry are offered."""
    assert build_gps_source_options({}) == {
        "webhook": "Webhook (Push)",
        "mqtt": "MQTT (Push)",
        "manual": "Manual Location Entry",
    }
