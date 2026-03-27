"""Tests for health flow helper utilities."""

from types import MappingProxyType
from typing import Any

from custom_components.pawcontrol.flow_steps.health_helpers import (
    build_dog_health_placeholders,
    build_health_settings_payload,
    normalise_string_sequence,
    summarise_health_summary,
)


def test_build_dog_health_placeholders_returns_immutable_mapping() -> None:
    """Health placeholders should include provided values and remain immutable."""
    placeholders = build_dog_health_placeholders(
        dog_name="Luna",
        dog_age="4",
        dog_weight="20 kg",
        suggested_ideal_weight="18 kg",
        suggested_activity="High",
        medication_enabled="Yes",
        bcs_info="Ideal",
        special_diet_count="1",
        health_diet_info="Low-fat",
    )

    assert isinstance(placeholders, MappingProxyType)
    assert placeholders["dog_name"] == "Luna"
    assert placeholders["health_diet_info"] == "Low-fat"


def test_normalise_string_sequence_normalises_and_filters_values() -> None:
    """Sequences should be trimmed, skip None, and coerce non-string values."""
    assert normalise_string_sequence(["  itchy ", None, 42, "", "   "]) == [
        "itchy",
        "42",
    ]


def test_normalise_string_sequence_returns_empty_for_non_sequence() -> None:
    """Non-sequence values should result in an empty list."""
    assert normalise_string_sequence(123) == []
    assert normalise_string_sequence("already-a-string") == []


def test_summarise_health_summary_for_default_healthy_status() -> None:
    """A healthy summary with no issues should report a healthy status."""
    assert summarise_health_summary({"healthy": True}) == "Healthy"


def test_summarise_health_summary_for_issues_and_warnings() -> None:
    """Unhealthy summaries should include issue and warning segments."""
    summary = {
        "healthy": False,
        "issues": ["  itchiness  ", "vomiting"],
        "warnings": ["weight trending up"],
    }

    assert summarise_health_summary(summary) == (
        "Issues detected | Issues: itchiness, vomiting | Warnings: weight trending up"
    )


def test_summarise_health_summary_for_non_mapping() -> None:
    """Invalid summary payloads should return the default fallback text."""
    assert summarise_health_summary(None) == "No recent health summary"


def test_build_health_settings_payload_uses_defaults_and_coercer() -> None:
    """Health payload should coerce submitted values and reuse current defaults."""

    def _coerce_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)

    payload = build_health_settings_payload(
        user_input={
            "weight_tracking": "on",
            "medication_reminders": None,
            "vet_reminders": "false",
        },
        current={
            "weight_tracking": False,
            "medication_reminders": False,
            "vet_reminders": True,
            "grooming_reminders": False,
            "health_alerts": True,
        },
        coerce_bool=_coerce_bool,
    )

    assert payload == {
        "weight_tracking": True,
        "medication_reminders": False,
        "vet_reminders": False,
        "grooming_reminders": False,
        "health_alerts": True,
    }
