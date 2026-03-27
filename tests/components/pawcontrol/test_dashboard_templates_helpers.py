"""Tests for dashboard template statistics helper formatting."""

from homeassistant.core import State

from custom_components.pawcontrol.dashboard_templates import (
    DashboardTemplates,
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


def test_parse_helpers_cover_scalar_channels_and_notifications() -> None:
    """Parsing helpers should coerce scalar values and notification payloads."""
    assert DashboardTemplates._parse_int(True, default=9) == 1
    assert DashboardTemplates._parse_int("bad-value", default=9) == 9
    assert DashboardTemplates._parse_bool(" yes ") is True
    assert DashboardTemplates._parse_bool(0) is False
    assert DashboardTemplates._parse_channels(" sms, push ,,email ") == [
        "sms",
        "push",
        "email",
    ]
    assert DashboardTemplates._parse_channels((" sms ", 7, "", None)) == [
        "sms",
        "7",
        "None",
    ]

    assert DashboardTemplates._parse_last_notification("invalid") is None
    assert DashboardTemplates._parse_last_notification({
        "type": "alert",
        "sent_at": 12345,
        "title": "Door",
    }) == {"type": "alert", "sent_at": "12345", "title": "Door"}


def test_normalise_notifications_state_handles_non_mapping_and_filters_bad_rows() -> (
    None
):
    """Notification state normalisation should guard malformed metrics and rows."""
    metrics, per_dog = DashboardTemplates._normalise_notifications_state(
        State("sensor.pawcontrol_notifications", "active", {"performance_metrics": 7})
    )
    assert metrics == {"notifications_failed": 0}
    assert per_dog == {}

    metrics, per_dog = DashboardTemplates._normalise_notifications_state(
        State(
            "sensor.pawcontrol_notifications",
            "active",
            {
                "performance_metrics": {"notifications_failed": "4"},
                "per_dog": {
                    "alpha": {
                        "sent_today": "3",
                        "quiet_hours_active": "true",
                        "channels": "sms,push",
                        "last_notification": {
                            "priority": "high",
                            "sent_at": 123,
                        },
                    },
                    123: {"sent_today": 99},
                    "beta": "bad-entry",
                },
            },
        )
    )

    assert metrics == {"notifications_failed": 4}
    assert per_dog == {
        "alpha": {
            "sent_today": 3,
            "quiet_hours_active": True,
            "channels": ["sms", "push"],
            "last_notification": {"priority": "high", "sent_at": "123"},
        }
    }
