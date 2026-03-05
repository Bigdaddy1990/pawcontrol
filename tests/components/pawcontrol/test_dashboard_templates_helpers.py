"""Tests for dashboard template statistics helper formatting."""

from custom_components.pawcontrol.dashboard_templates import (
    _format_breaker_list,
    _format_guard_reasons,
    _format_guard_results,
    _translated_statistics_label,
)
from custom_components.pawcontrol.translation_helpers import component_translation_key


def test_format_breaker_list_uses_translated_empty_fallback() -> None:
    """Empty breaker lists should use localized fallback text."""
    translation_lookup = (
        {component_translation_key("dashboard_statistics_empty_list"): "keine"},
        {},
    )

    assert _format_breaker_list([], translation_lookup) == "keine"
    assert _format_breaker_list(["alpha", "beta"], translation_lookup) == "alpha, beta"


def test_format_guard_reasons_orders_descending_and_fallback() -> None:
    """Reason summaries should sort by count then key and localize empty output."""
    translation_lookup = (
        {
            component_translation_key(
                "dashboard_statistics_fallback_no_guard_reasons"
            ): "keine Gründe"
        },
        {},
    )

    assert _format_guard_reasons({"timeout": 1, "auth": 3, "battery": 3}, ({}, {})) == [
        "auth: 3",
        "battery: 3",
        "timeout: 1",
    ]
    assert _format_guard_reasons({}, translation_lookup) == ["keine Gründe"]


def test_format_guard_results_formats_entries_and_applies_limit() -> None:
    """Guard result output should include translated state, reason and description."""
    translation_lookup = (
        {
            component_translation_key(
                "dashboard_statistics_label_guard_result_executed"
            ): "ausgeführt",
            component_translation_key(
                "dashboard_statistics_label_guard_result_reason"
            ): "Grund",
        },
        {},
    )
    results = [
        {
            "domain": "pawcontrol",
            "service": "refresh",
            "executed": True,
            "reason": "cache",
            "description": "skipped duplicate",
        },
        {
            "domain": "pawcontrol",
            "service": "sync",
            "executed": False,
        },
        "invalid-entry",
    ]

    assert _format_guard_results(results, translation_lookup, limit=1) == [
        "pawcontrol.refresh: ausgeführt (Grund: cache) - skipped duplicate"
    ]


def test_format_guard_results_returns_localized_empty_state() -> None:
    """When no valid results exist a translated fallback should be returned."""
    translation_lookup = (
        {
            component_translation_key("dashboard_statistics_empty_list"): "leer",
            component_translation_key(
                "dashboard_statistics_fallback_no_guard_results"
            ): "keine Ergebnisse",
        },
        {},
    )

    assert _format_guard_results(["bad"], translation_lookup) == ["keine Ergebnisse"]


def test_translated_statistics_label_defaults_to_key_for_unknown_label() -> None:
    """Unknown label keys should pass through unchanged."""
    assert _translated_statistics_label(({}, {}), "custom_label") == "custom_label"
