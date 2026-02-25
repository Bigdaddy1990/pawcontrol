"""Unit tests for health flow helper utilities."""

from typing import Any

from custom_components.pawcontrol.flow_steps.health_helpers import (
    build_health_settings_payload,
    normalise_string_sequence,
    summarise_health_summary,
)


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
