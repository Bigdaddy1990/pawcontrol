"""Unit tests for health flow helper utilities."""

from typing import Any

from custom_components.pawcontrol.flow_steps.health_helpers import (
    build_dog_health_placeholders,
    build_health_settings_payload,
    normalise_string_sequence,
    summarise_health_summary,
)
from custom_components.pawcontrol.types import DOG_HEALTH_PLACEHOLDERS_TEMPLATE


def test_build_dog_health_placeholders_returns_immutable_copy() -> None:
    """Health placeholders should be frozen and not mutate the template."""
    placeholders = build_dog_health_placeholders(
        dog_name="Luna",
        dog_age="4",
        dog_weight="22.4",
        suggested_ideal_weight="20.0",
        suggested_activity="moderate",
        medication_enabled="yes",
        bcs_info="BCS info",
        special_diet_count="3",
        health_diet_info="Diet guidance",
    )

    assert placeholders["dog_name"] == "Luna"
    assert placeholders["medication_enabled"] == "yes"
    assert DOG_HEALTH_PLACEHOLDERS_TEMPLATE["dog_name"] == ""

    mutable_copy = dict(placeholders)
    mutable_copy["dog_name"] = "Nova"

    assert placeholders["dog_name"] == "Luna"


def test_normalise_string_sequence_handles_mixed_values() -> None:
    """Sequence values should be trimmed, filtered, and stringified."""
    values: list[Any] = ["  limping  ", "", None, 42, "  ", True]

    assert normalise_string_sequence(values) == ["limping", "42", "True"]


def test_normalise_string_sequence_ignores_non_sequences_and_strings() -> None:
    """Non-sequences and raw strings should return an empty list."""
    assert normalise_string_sequence("single-value") == []
    assert normalise_string_sequence(None) == []


def test_summarise_health_summary_renders_issues_and_warnings() -> None:
    """Non-healthy summaries should include issue and warning sections."""
    summary = {
        "healthy": False,
        "issues": [" limping "],
        "warnings": ["  meds overdue"],
    }

    assert (
        summarise_health_summary(summary)
        == "Issues detected | Issues: limping | Warnings: meds overdue"
    )


def test_summarise_health_summary_defaults_for_non_mapping_and_healthy() -> None:
    """Summary helper should handle invalid payloads and healthy snapshots."""
    assert summarise_health_summary(None) == "No recent health summary"
    assert summarise_health_summary({"healthy": True}) == "Healthy"


def test_build_health_settings_payload_uses_coercion_defaults() -> None:
    """Boolean settings should be resolved via coerce_bool with current fallback."""
    calls: list[tuple[Any, bool]] = []

    def _coerce_bool(value: Any, default: bool) -> bool:
        calls.append((value, default))
        if value is None:
            return default
        return bool(value)

    current = {
        "weight_tracking": True,
        "medication_reminders": False,
        "vet_reminders": True,
        "grooming_reminders": False,
        "health_alerts": True,
    }
    user_input = {
        "weight_tracking": None,
        "medication_reminders": 1,
        "vet_reminders": 0,
    }

    payload = build_health_settings_payload(
        user_input,
        current,
        coerce_bool=_coerce_bool,
    )

    assert payload == {
        "weight_tracking": True,
        "medication_reminders": True,
        "vet_reminders": False,
        "grooming_reminders": False,
        "health_alerts": True,
    }
    assert calls == [
        (None, True),
        (1, False),
        (0, True),
        (None, False),
        (None, True),
    ]
