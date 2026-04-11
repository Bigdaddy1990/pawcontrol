"""Coverage tests for system health normalisation helpers."""

import pytest

from custom_components.pawcontrol.system_health import (
    _attach_runtime_store_history,
    _coerce_automation_entries,
    _coerce_event_counters,
    _coerce_listener_metadata,
    _coerce_mapping_of_str_lists,
    _coerce_positive_int,
    _coerce_preferred_events,
    _extract_api_call_count,
)


def test_attach_runtime_store_history_filters_invalid_timeline_entries() -> None:
    """Only mapping-based assessment and timeline payloads should be copied."""
    info: dict[str, object] = {}
    history = {
        "assessment": {"status": "healthy"},
        "assessment_timeline_segments": [
            {"stage": "latest", "score": 1.0},
            "invalid",
            42,
            {"stage": "baseline", "score": 0.4},
        ],
        "assessment_timeline_summary": {"segments": 2},
    }

    _attach_runtime_store_history(info, history)

    assert info["runtime_store_history"] == history
    assert info["runtime_store_assessment"] == {"status": "healthy"}
    assert info["runtime_store_timeline_segments"] == [
        {"stage": "latest", "score": 1.0},
        {"stage": "baseline", "score": 0.4},
    ]
    assert info["runtime_store_timeline_summary"] == {"segments": 2}


@pytest.mark.parametrize(
    ("stats", "expected"),
    [
        (None, 0),
        ({}, 0),
        ({"performance_metrics": None}, 0),
        ({"performance_metrics": {"api_calls": "9"}}, 9),
        ({"performance_metrics": {"api_calls": object()}}, 0),
    ],
)
def test_extract_api_call_count_handles_legacy_shapes(
    stats: object, expected: int
) -> None:
    """API call extraction should remain stable for missing or invalid payloads."""
    assert _extract_api_call_count(stats) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("5", 5), (0, None), ("-1", None), (None, None), ("nan", None)],
)
def test_coerce_positive_int_returns_only_positive_values(
    value: object,
    expected: int | None,
) -> None:
    """Positive int coercion should reject non-positive and invalid values."""
    assert _coerce_positive_int(value) == expected


def test_coerce_automation_entries_ignores_invalid_rows_and_normalises_bools() -> None:
    """Automation metadata should keep only supported fields and valid mappings."""
    payload = [
        "skip",
        {
            "config_entry_id": "  abc123 ",
            "title": " Front Door ",
            "manual_guard_event": " guard_event ",
            "configured_guard": "yes",
            "configured_breaker": 0,
            "configured_check": True,
        },
        {
            "manual_breaker_event": "",
            "configured_guard": None,
        },
    ]

    assert _coerce_automation_entries(payload) == [
        {
            "config_entry_id": "abc123",
            "title": "Front Door",
            "manual_guard_event": "guard_event",
            "configured_guard": True,
            "configured_breaker": False,
            "configured_check": True,
        }
    ]


def test_coerce_event_counters_defaults_and_normalises_nested_mappings() -> None:
    """Event counter payloads should normalise totals, events, and reasons."""
    counters = _coerce_event_counters({
        "total": "7",
        "by_event": {"  guard ": "3", None: "99", "bad": object()},
        "by_reason": {"manual": 2, "": 1},
    })

    assert counters == {
        "total": 7,
        "by_event": {"guard": 3, "bad": 0},
        "by_reason": {"manual": 2},
    }


def test_mapping_and_listener_coercion_normalises_strings() -> None:
    """List mappings and listener metadata should drop empty/invalid entries."""
    assert _coerce_mapping_of_str_lists({
        "  key  ": [" A ", "", None, "B"],
        "": ["skip"],
        "other": " lone ",
    }) == {"key": ["A", "B"], "other": ["lone"]}

    assert _coerce_listener_metadata({
        " listener ": {
            "sources": ["alpha", " ", "beta"],
            "primary_source": " main ",
        },
        "empty": {},
        "invalid": "not-a-mapping",
    }) == {"listener": {"sources": ["alpha", "beta"], "primary_source": "main"}}


def test_coerce_preferred_events_returns_known_keys_with_optional_values() -> None:
    """Preferred event coercion should always emit all supported keys."""
    preferences = _coerce_preferred_events({
        "manual_check_event": " check_now ",
        "manual_guard_event": "",
        "manual_breaker_event": "breaker",
        "ignored": "value",
    })

    assert preferences == {
        "manual_check_event": "check_now",
        "manual_guard_event": None,
        "manual_breaker_event": "breaker",
    }
