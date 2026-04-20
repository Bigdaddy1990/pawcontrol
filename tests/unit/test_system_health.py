"""Unit tests for PawControl system health output."""

from typing import Any
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntry
import pytest

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.system_health import (
    BreakerIndicatorThresholds,
    GuardIndicatorThresholds,
    _attach_runtime_store_history,
    _build_breaker_overview,
    _build_guard_summary,
    _coerce_automation_entries,
    _coerce_event_counters,
    _coerce_event_history,
    _coerce_float,
    _coerce_int,
    _coerce_int_mapping,
    _coerce_listener_metadata,
    _coerce_mapping_of_str_lists,
    _coerce_positive_int,
    _coerce_preferred_events,
    _coerce_str_list,
    _default_service_execution_snapshot,
    _describe_breaker_threshold_source,
    _describe_guard_threshold_source,
    _extract_api_call_count,
    _extract_service_execution_metrics,
    _extract_threshold_value,
    _normalise_manual_events_snapshot,
    _resolve_indicator_thresholds,
    _resolve_option_threshold,
    _serialize_breaker_thresholds,
    _serialize_guard_thresholds,
    _serialize_threshold,
    async_register,
    system_health_info,
)
from custom_components.pawcontrol.types import DomainRuntimeStoreEntry


class _Coordinator:
    """Coordinator stub returning update statistics."""

    def __init__(
        self,
        stats: dict[str, object],
        *,
        last_update_success: bool = True,
        use_external_api: bool = True,
    ) -> None:
        self._stats = stats
        self.last_update_success = last_update_success
        self.use_external_api = use_external_api

    def get_update_statistics(self) -> dict[str, object]:
        """Return the stored statistics payload."""
        return self._stats


_FakeRuntimeData = type(
    "PawControlRuntimeData",
    (),
    {"__module__": "custom_components.pawcontrol.types"},
)


def _make_runtime_data(
    *,
    performance_stats: dict[str, object],
    coordinator: _Coordinator,
    script_manager: object | None = None,
) -> Any:
    """Return a runtime data stub that passes runtime_data validation."""
    runtime_data = _FakeRuntimeData()
    runtime_data.performance_stats = performance_stats
    runtime_data.coordinator = coordinator
    runtime_data.script_manager = script_manager
    return runtime_data


def _install_entry(hass: Any, entry: ConfigEntry) -> None:
    """Install a config entry into the Home Assistant stub."""
    hass.config_entries.async_entries = lambda domain=None: (
        [entry] if domain == DOMAIN else []
    )


@pytest.mark.asyncio
async def test_system_health_info_reports_guard_breaker_runtime_store(
    hass: Any,
) -> None:
    """System health should expose guard, breaker, and runtime store telemetry."""
    entry = ConfigEntry(
        domain=DOMAIN,
        data={},
        options={"external_api_quota": 10},
    )
    coordinator = _Coordinator({"performance_metrics": {"api_calls": "5"}})
    performance_stats = {
        "service_guard_metrics": {
            "executed": "4",
            "skipped": "2",
            "reasons": {"missing_instance": "2", "maintenance": 1},
        },
        "entity_factory_guard_metrics": {"runtime_floor": 0.5},
        "rejection_metrics": {
            "open_breaker_count": "1",
            "half_open_breaker_count": 0,
            "unknown_breaker_count": "0",
            "rejection_breaker_count": "2",
            "rejection_rate": "0.2",
            "open_breakers": ["api"],
            "last_rejection_breaker_id": "api",
            "last_rejection_breaker_name": "API Gateway",
            "last_rejection_time": 1700000000,
        },
        "runtime_store_health": {
            "assessment": {
                "level": "watch",
                "reason": "manual test",
            },
            "assessment_timeline_segments": [
                {
                    "status": "current",
                    "level": "ok",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            ],
            "assessment_timeline_summary": {
                "total_events": 1,
                "status_counts": {"current": 1},
                "level_counts": {"ok": 1},
            },
        },
    }
    runtime_data = _make_runtime_data(
        performance_stats=performance_stats,
        coordinator=coordinator,
    )
    entry.runtime_data = runtime_data
    _install_entry(hass, entry)
    hass.data[DOMAIN] = {
        entry.entry_id: DomainRuntimeStoreEntry(runtime_data=runtime_data),
    }

    info = await system_health_info(hass)

    assert info["remaining_quota"] == 5
    guard_summary = info["service_execution"]["guard_summary"]
    assert guard_summary["executed"] == 4
    assert guard_summary["skipped"] == 2
    assert guard_summary["total_calls"] == 6
    assert guard_summary["indicator"]["level"] == "warning"
    assert guard_summary["top_reasons"][0]["reason"] == "missing_instance"
    assert guard_summary["top_reasons"][0]["count"] == 2

    breaker_overview = info["service_execution"]["breaker_overview"]
    assert breaker_overview["status"] == "open"
    assert breaker_overview["open_breaker_count"] == 1
    assert breaker_overview["indicator"]["level"] == "warning"

    runtime_store = info["runtime_store"]
    assert runtime_store["status"] == "current"
    assert info["runtime_store_assessment"]["level"] == "watch"
    assert info["runtime_store_timeline_summary"]["total_events"] == 1


@pytest.mark.asyncio
async def test_system_health_info_coerces_unexpected_types(hass: Any) -> None:
    """System health should coerce malformed telemetry safely."""
    entry = ConfigEntry(domain=DOMAIN, data={}, options={})
    coordinator = _Coordinator({"performance_metrics": {"api_calls": None}})
    coordinator.use_external_api = False
    performance_stats = {
        "service_guard_metrics": {
            "executed": "bad",
            "skipped": None,
            "reasons": {"missing_instance": None, 123: "ignored"},
        },
        "rejection_metrics": {
            "open_breaker_count": "not-a-number",
            "half_open_breaker_count": None,
            "unknown_breaker_count": "0",
            "rejection_breaker_count": "2",
            "rejection_rate": "0.1",
        },
    }
    runtime_data = _make_runtime_data(
        performance_stats=performance_stats,
        coordinator=coordinator,
    )
    entry.runtime_data = runtime_data
    _install_entry(hass, entry)
    hass.data[DOMAIN] = {
        entry.entry_id: DomainRuntimeStoreEntry(runtime_data=runtime_data),
    }

    info = await system_health_info(hass)

    assert info["remaining_quota"] == "unlimited"
    guard_summary = info["service_execution"]["guard_summary"]
    assert guard_summary["executed"] == 0
    assert guard_summary["skipped"] == 0
    assert guard_summary["reasons"]["missing_instance"] == 0

    breaker_overview = info["service_execution"]["breaker_overview"]
    assert breaker_overview["open_breaker_count"] == 0
    assert breaker_overview["half_open_breaker_count"] == 0
    assert breaker_overview["rejection_breaker_count"] == 2
    assert breaker_overview["status"] == "monitoring"


def test_normalise_manual_events_snapshot_coerces_nested_payloads() -> None:
    """Manual event telemetry should be normalized into stable payloads."""
    snapshot = {
        "available": 1,
        "automations": [
            {
                "config_entry_id": " entry-1 ",
                "title": " Dog profile ",
                "manual_guard_event": " guard.event ",
                "configured_guard": "yes",
                "configured_breaker": 0,
                "configured_check": True,
            },
            "skip-me",
        ],
        "configured_guard_events": [" one ", "", 123],
        "listener_events": {" primary ": [" event.one ", "", None]},
        "listener_metadata": {
            "guard": {
                "sources": [" sensor_a ", ""],
                "primary_source": "sensor_a",
            },
        },
        "preferred_events": {
            "manual_guard_event": " preferred.guard ",
            "manual_breaker_event": " preferred.breaker ",
            "manual_check_event": " preferred.check ",
        },
        "event_history": [
            {"event": "manual.guard"},
            "skip",
        ],
        "event_counters": {
            "total": "2",
            "by_event": {"manual.guard": "1"},
            "by_reason": {"manual": "bad"},
        },
        "active_listeners": [" listener.one ", "", None],
    }

    payload = _normalise_manual_events_snapshot(snapshot)

    assert payload["available"] is True
    assert payload["automations"][0]["config_entry_id"] == "entry-1"
    assert payload["automations"][0]["configured_guard"] is True
    assert payload["automations"][0]["configured_breaker"] is False
    assert payload["configured_guard_events"] == ["one"]
    assert payload["listener_events"] == {"primary": ["event.one"]}
    assert payload["listener_metadata"] == {
        "guard": {"sources": ["sensor_a"], "primary_source": "sensor_a"},
    }
    assert payload["preferred_guard_event"] == "preferred.guard"
    assert payload["preferred_breaker_event"] == "preferred.breaker"
    assert payload["preferred_check_event"] == "preferred.check"
    assert payload["event_history"] == [{"event": "manual.guard"}]
    assert payload["event_counters"] == {
        "total": 2,
        "by_event": {"manual.guard": 1},
        "by_reason": {"manual": 0},
    }
    assert payload["active_listeners"] == ["listener.one"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("7", 7),
        (0, None),
        (-3, None),
        ("not-a-number", None),
        (None, None),
    ],
)
def test_coerce_positive_int_accepts_only_positive_numbers(
    value: object,
    expected: int | None,
) -> None:
    """Positive-int coercion should reject invalid, empty, and non-positive values."""
    assert _coerce_positive_int(value) == expected


def test_manual_event_helper_coercions_handle_invalid_shapes() -> None:
    """Manual resilience helper coercers should drop unsupported payload structures."""
    assert _coerce_str_list("  ") == []
    assert _coerce_event_history("not-a-sequence") == []
    assert _coerce_int_mapping([("a", 1)]) == {}
    assert _coerce_event_counters("not-a-mapping") == {
        "total": 0,
        "by_event": {},
        "by_reason": {},
    }
    assert _coerce_mapping_of_str_lists({"  ": ["keep"]}) == {}
    assert _coerce_listener_metadata("not-a-mapping") == {}
    assert _coerce_preferred_events("not-a-mapping") == {}


def test_coerce_int_mapping_skips_non_string_keys() -> None:
    """Integer mapping coercion should ignore keys that cannot be normalized."""
    mapping = _coerce_int_mapping({None: 1, "  ": 2, "valid": "3"})
    assert mapping == {"valid": 3}


def test_normalise_manual_events_snapshot_uses_preference_fallbacks() -> None:
    """Preferred event values should fall back to nested preferred_events keys."""
    payload = _normalise_manual_events_snapshot({
        "available": True,
        "preferred_events": {
            "manual_guard_event": " guard.pref ",
            "manual_breaker_event": " breaker.pref ",
            "manual_check_event": " check.pref ",
        },
        "preferred_guard_event": "",
        "preferred_breaker_event": None,
        "preferred_check_event": "   ",
        "listener_sources": {"listener": ["sensor.one", " "]},
    })

    assert payload["preferred_guard_event"] == "guard.pref"
    assert payload["preferred_breaker_event"] == "breaker.pref"
    assert payload["preferred_check_event"] == "check.pref"
    assert payload["listener_sources"] == {"listener": ["sensor.one"]}


def test_coerce_listener_metadata_ignores_empty_listener_entries() -> None:
    """Listener metadata should only retain entries with usable content."""
    metadata = _coerce_listener_metadata({
        "listener.one": {
            "sources": [" source.one ", ""],
            "primary_source": "primary",
        },
        "listener.two": {"sources": ["", None]},
        "listener.three": "invalid",
    })

    assert metadata == {
        "listener.one": {
            "sources": ["source.one"],
            "primary_source": "primary",
        }
    }


def test_coerce_automation_entries_preserves_explicit_boolean_values() -> None:
    """Automation-entry coercion should keep booleans and coerce truthy values."""
    entries = _coerce_automation_entries([
        {
            "manual_breaker_event": " breaker.event ",
            "manual_check_event": " check.event ",
            "configured_guard": True,
            "configured_breaker": False,
            "configured_check": 1,
        }
    ])

    assert entries == [
        {
            "manual_breaker_event": "breaker.event",
            "manual_check_event": "check.event",
            "configured_guard": True,
            "configured_breaker": False,
            "configured_check": True,
        }
    ]


def test_coerce_automation_entries_skips_empty_items_and_none_config_flags() -> None:
    """Entries without usable fields should be skipped while later entries are kept."""
    entries = _coerce_automation_entries([
        {"configured_guard": None, "configured_breaker": None, "configured_check": None},
        {"title": "  Active automation  "},
    ])

    assert entries == [{"title": "Active automation"}]


def test_resolve_indicator_thresholds_uses_script_snapshot_before_options() -> None:
    """Script-provided thresholds should win over config entry options."""

    class _ScriptManager:
        def get_resilience_escalation_snapshot(self) -> dict[str, object]:
            return {
                "thresholds": {
                    "skip_threshold": {"active": "4", "default": 9},
                    "breaker_threshold": {"default": "5"},
                },
            }

    runtime = _make_runtime_data(
        performance_stats={},
        coordinator=_Coordinator({}),
        script_manager=_ScriptManager(),
    )

    guard_thresholds, breaker_thresholds = _resolve_indicator_thresholds(
        runtime,
        {
            "system_settings": {
                "resilience_skip_threshold": 2,
                "resilience_breaker_threshold": 2,
            },
        },
    )

    assert guard_thresholds.warning_count == 3
    assert guard_thresholds.critical_count == 4
    assert guard_thresholds.source == "resilience_script"
    assert guard_thresholds.source_key == "active"

    assert breaker_thresholds.warning_count == 4
    assert breaker_thresholds.critical_count == 5
    assert breaker_thresholds.source == "resilience_script"
    assert breaker_thresholds.source_key == "default"


def test_resolve_indicator_thresholds_falls_back_to_options_for_invalid_snapshot() -> (
    None
):
    """Invalid script snapshots should gracefully defer to config-entry options."""

    class _BrokenScriptManager:
        def __init__(self, payload: object) -> None:
            self._payload = payload

        def get_resilience_escalation_snapshot(self) -> object:
            return self._payload

    option_payload = {
        "system_settings": {
            "resilience_skip_threshold": 4,
            "resilience_breaker_threshold": 3,
        }
    }

    runtime_with_non_mapping = _make_runtime_data(
        performance_stats={},
        coordinator=_Coordinator({}),
        script_manager=_BrokenScriptManager(["bad-shape"]),
    )
    guard_thresholds, breaker_thresholds = _resolve_indicator_thresholds(
        runtime_with_non_mapping,
        option_payload,
    )
    assert guard_thresholds.warning_count == 3
    assert guard_thresholds.critical_count == 4
    assert guard_thresholds.source == "config_entry"
    assert guard_thresholds.source_key == "system_settings"
    assert breaker_thresholds.warning_count == 2
    assert breaker_thresholds.critical_count == 3
    assert breaker_thresholds.source == "config_entry"
    assert breaker_thresholds.source_key == "system_settings"

    runtime_with_missing_thresholds = _make_runtime_data(
        performance_stats={},
        coordinator=_Coordinator({}),
        script_manager=_BrokenScriptManager({"thresholds": "invalid"}),
    )
    guard_thresholds, breaker_thresholds = _resolve_indicator_thresholds(
        runtime_with_missing_thresholds,
        option_payload,
    )
    assert guard_thresholds.warning_count == 3
    assert guard_thresholds.critical_count == 4
    assert breaker_thresholds.warning_count == 2
    assert breaker_thresholds.critical_count == 3


def test_system_health_threshold_helpers_cover_serialization_and_sources() -> None:
    """Threshold helpers should serialize sparse payloads and describe sources."""
    assert _serialize_threshold(count=None, ratio=None) is None
    assert _serialize_threshold(count=2, ratio=0.25) == {
        "count": 2,
        "ratio": 0.25,
        "percentage": 25.0,
    }

    guard_thresholds = GuardIndicatorThresholds(
        warning_count=1,
        critical_count=2,
        warning_ratio=0.25,
        critical_ratio=0.5,
        source="config_entry",
        source_key="manual_override",
    )
    assert _serialize_guard_thresholds(guard_thresholds) == {
        "source": "config_entry",
        "source_key": "manual_override",
        "warning": {"count": 1, "ratio": 0.25, "percentage": 25.0},
        "critical": {"count": 2, "ratio": 0.5, "percentage": 50.0},
    }

    breaker_thresholds = BreakerIndicatorThresholds(
        warning_count=None,
        critical_count=2,
        source="resilience_script",
        source_key="active",
    )
    assert _serialize_breaker_thresholds(breaker_thresholds) == {
        "source": "resilience_script",
        "source_key": "active",
        "critical": {"count": 2},
    }

    assert (
        _describe_guard_threshold_source(
            GuardIndicatorThresholds(source="resilience_script", source_key="default"),
        )
        == "resilience script default threshold"
    )
    assert (
        _describe_guard_threshold_source(
            GuardIndicatorThresholds(
                source="config_entry",
                source_key="system_settings",
            ),
        )
        == "options flow system settings threshold"
    )
    assert (
        _describe_guard_threshold_source(
            GuardIndicatorThresholds(source="default_ratio")
        )
        == "system default threshold"
    )
    assert (
        _describe_breaker_threshold_source(
            BreakerIndicatorThresholds(source="resilience_script", source_key="custom"),
        )
        == "configured resilience script threshold"
    )
    assert (
        _describe_breaker_threshold_source(
            BreakerIndicatorThresholds(source="config_entry", source_key="other"),
        )
        == "options flow threshold"
    )
    assert (
        _describe_breaker_threshold_source(BreakerIndicatorThresholds())
        == "system default threshold"
    )


def test_default_service_execution_snapshot_uses_expected_defaults() -> None:
    """The default snapshot should expose safe baseline guard and breaker state."""
    snapshot = _default_service_execution_snapshot()

    assert snapshot["status"]["overall"]["level"] == "normal"
    assert snapshot["guard_summary"]["total_calls"] == 0
    assert snapshot["guard_summary"]["indicator"]["level"] == "normal"
    assert snapshot["breaker_overview"]["status"] == "healthy"
    assert snapshot["breaker_overview"]["indicator"]["level"] == "normal"
    assert snapshot["manual_events"] == {
        "available": False,
        "event_history": [],
        "last_event": None,
        "last_trigger": None,
        "event_counters": {"total": 0, "by_event": {}, "by_reason": {}},
        "active_listeners": [],
    }


def test_attach_runtime_store_history_adds_only_mapping_and_sequence_payloads() -> None:
    """History attachment should ignore malformed payload sections."""
    info: dict[str, object] = {"existing": True}

    _attach_runtime_store_history(
        info,
        {
            "assessment": {"level": "watch"},
            "assessment_timeline_segments": [
                {"status": "current", "level": "ok"},
                "skip",
            ],
            "assessment_timeline_summary": {"total_events": 1},
        },
    )

    assert info["runtime_store_history"] == {
        "assessment": {"level": "watch"},
        "assessment_timeline_segments": [
            {"status": "current", "level": "ok"},
            "skip",
        ],
        "assessment_timeline_summary": {"total_events": 1},
    }
    assert info["runtime_store_assessment"] == {"level": "watch"}
    assert info["runtime_store_timeline_segments"] == [
        {"status": "current", "level": "ok"},
    ]
    assert info["runtime_store_timeline_summary"] == {"total_events": 1}


def test_attach_runtime_store_history_skips_empty_payload() -> None:
    """History attachment should leave the payload untouched when history is missing."""
    info: dict[str, object] = {"existing": True}

    _attach_runtime_store_history(info, None)

    assert info == {"existing": True}


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ("9", 0, 9),
        ("bad", 7, 7),
        (None, 5, 5),
    ],
)
def test_coerce_int_handles_value_and_type_errors(
    value: object,
    default: int,
    expected: int,
) -> None:
    """Integer coercion should return the fallback for invalid or missing values."""
    assert _coerce_int(value, default=default) == expected


@pytest.mark.parametrize(
    ("stats", "expected"),
    [
        (None, 0),
        ({"performance_metrics": None}, 0),
        ({"performance_metrics": {"api_calls": "11"}}, 11),
        ({"performance_metrics": {"api_calls": "invalid"}}, 0),
    ],
)
def test_extract_api_call_count_handles_missing_or_invalid_shapes(
    stats: object,
    expected: int,
) -> None:
    """API call extraction should tolerate malformed coordinator statistics."""
    assert _extract_api_call_count(stats) == expected


@pytest.mark.asyncio
async def test_system_health_info_returns_default_payload_when_no_entry(
    hass: Any,
) -> None:
    """System health should return a stable fallback payload without an entry."""
    info = await system_health_info(hass)

    assert info["can_reach_backend"] is False
    assert info["remaining_quota"] == "unknown"
    assert info["service_execution"]["status"]["overall"]["level"] == "normal"
    assert info["runtime_store"]["status"] == "missing"


def test_async_register_registers_system_health_callback() -> None:
    """Integration registration should wire the system health callback."""
    register = type("Register", (), {"async_register_info": MagicMock()})()

    async_register(MagicMock(), register)

    register.async_register_info.assert_called_once_with(system_health_info)


@pytest.mark.asyncio
async def test_system_health_info_handles_missing_runtime_and_coordinator(
    hass: Any,
) -> None:
    """System health should gracefully fallback when runtime data is incomplete."""
    missing_runtime_entry = ConfigEntry(domain=DOMAIN, data={}, options={})
    _install_entry(hass, missing_runtime_entry)

    info_missing_runtime = await system_health_info(hass)
    assert info_missing_runtime["can_reach_backend"] is False
    assert info_missing_runtime["remaining_quota"] == "unknown"

    entry_with_runtime = ConfigEntry(domain=DOMAIN, data={}, options={})
    runtime_data = _FakeRuntimeData()
    runtime_data.performance_stats = {}
    runtime_data.coordinator = None
    runtime_data.script_manager = None
    entry_with_runtime.runtime_data = runtime_data
    _install_entry(hass, entry_with_runtime)

    info_missing_coordinator = await system_health_info(hass)
    assert info_missing_coordinator["can_reach_backend"] is False
    assert info_missing_coordinator["remaining_quota"] == "unknown"


@pytest.mark.asyncio
async def test_system_health_info_untracked_quota_and_threshold_descriptions(
    hass: Any,
) -> None:
    """Quota and indicator source labels should cover script/default branches."""
    entry = ConfigEntry(domain=DOMAIN, data={}, options={"external_api_quota": "x"})

    class _ScriptManager:
        def get_resilience_escalation_snapshot(self) -> dict[str, object]:
            return {
                "manual_events": {
                    "configured_breaker_events": ["breaker.event"],
                    "configured_check_events": ["check.event"],
                    "system_guard_event": "system.guard",
                    "system_breaker_event": "system.breaker",
                },
                "thresholds": {
                    "skip_threshold": {"default": 2},
                    "breaker_threshold": {"default": 1},
                },
            }

    runtime_data = _make_runtime_data(
        performance_stats={
            "service_guard_metrics": {"executed": 0, "skipped": 2, "reasons": {}},
            "rejection_metrics": {
                "open_breaker_count": 0,
                "half_open_breaker_count": 1,
                "unknown_breaker_count": 0,
                "rejection_breaker_count": 0,
                "rejection_rate": 0.0,
            },
        },
        coordinator=_Coordinator({"performance_metrics": {"api_calls": 1}}),
        script_manager=_ScriptManager(),
    )
    entry.runtime_data = runtime_data
    _install_entry(hass, entry)

    info = await system_health_info(hass)

    assert info["remaining_quota"] == "untracked"
    assert info["service_execution"]["manual_events"]["configured_breaker_events"] == [
        "breaker.event"
    ]
    assert info["service_execution"]["manual_events"]["configured_check_events"] == [
        "check.event"
    ]
    assert (
        info["service_execution"]["manual_events"]["system_guard_event"]
        == "system.guard"
    )
    assert (
        info["service_execution"]["guard_summary"]["indicator"]["threshold_source"]
        == "default"
    )
    assert (
        info["service_execution"]["breaker_overview"]["indicator"]["threshold_source"]
        == "default"
    )

    guard_thresholds, breaker_thresholds = _resolve_indicator_thresholds(
        None,
        {
            "system_settings": {
                "resilience_skip_threshold": 3,
                "resilience_breaker_threshold": 2,
            }
        },
    )
    guard_indicator = _build_guard_summary(
        {"executed": 1, "skipped": 2, "reasons": {}},
        guard_thresholds,
    )["indicator"]
    breaker_indicator = _build_breaker_overview(
        {
            "open_breaker_count": 2,
            "half_open_breaker_count": 0,
            "unknown_breaker_count": 0,
            "rejection_breaker_count": 0,
            "rejection_rate": 0,
        },
        breaker_thresholds,
    )["indicator"]
    assert guard_indicator["threshold_source"] == "system_settings"
    assert breaker_indicator["threshold_source"] == "system_settings"


def test_build_guard_and_breaker_helpers_cover_healthy_and_critical_paths() -> None:
    """Guard and breaker summaries should expose healthy and critical states."""
    healthy_guard = _build_guard_summary(
        {"executed": 5, "skipped": 0, "reasons": {"ignored": 2}},
        GuardIndicatorThresholds(
            warning_count=None,
            critical_count=None,
            warning_ratio=0.25,
            critical_ratio=0.5,
        ),
    )
    assert healthy_guard["indicator"]["level"] == "normal"
    assert healthy_guard["indicator"]["metric_type"] == "guard_health"
    assert healthy_guard["top_reasons"] == [{"reason": "ignored", "count": 2}]

    critical_guard = _build_guard_summary(
        {"executed": 1, "skipped": 3, "reasons": {}},
        GuardIndicatorThresholds(
            warning_count=2,
            critical_count=3,
            warning_ratio=0.25,
            critical_ratio=0.5,
            source="config_entry",
            source_key="system_settings",
        ),
    )
    assert critical_guard["indicator"]["level"] == "critical"
    assert critical_guard["indicator"]["threshold_source"] == "system_settings"

    healthy_breaker = _build_breaker_overview(
        {
            "open_breaker_count": 0,
            "half_open_breaker_count": 0,
            "unknown_breaker_count": 1,
            "rejection_breaker_count": 0,
            "rejection_rate": 0,
        },
        BreakerIndicatorThresholds(
            warning_count=1,
            critical_count=3,
        ),
    )
    assert healthy_breaker["status"] == "healthy"
    assert healthy_breaker["indicator"]["level"] == "normal"
    assert healthy_breaker["unknown_breaker_count"] == 1

    critical_breaker = _build_breaker_overview(
        {
            "open_breaker_count": 2,
            "half_open_breaker_count": 1,
            "unknown_breaker_count": 0,
            "rejection_breaker_count": 1,
            "rejection_rate": 0.2,
            "open_breakers": ["api", "sync"],
            "half_open_breakers": ["fallback"],
            "unknown_breakers": ["legacy"],
            "last_rejection_time": 123.4,
        },
        BreakerIndicatorThresholds(
            warning_count=2,
            critical_count=3,
            source="resilience_script",
            source_key="active",
        ),
    )
    assert critical_breaker["status"] == "open"
    assert critical_breaker["indicator"]["level"] == "critical"
    assert critical_breaker["indicator"]["threshold_source"] == "active"
    assert critical_breaker["open_breakers"] == ["api", "sync"]
    assert critical_breaker["half_open_breakers"] == ["fallback"]
    assert critical_breaker["unknown_breakers"] == ["legacy"]
    assert critical_breaker["last_rejection_time"] == 123.4


def test_attach_runtime_store_history_ignores_non_mapping_sections() -> None:
    """Malformed assessment/timeline sections should be ignored."""
    info: dict[str, object] = {}

    _attach_runtime_store_history(
        info,
        {
            "assessment": "invalid",
            "assessment_timeline_segments": 42,
            "assessment_timeline_summary": ["invalid"],
        },
    )

    assert "runtime_store_assessment" not in info
    assert "runtime_store_timeline_segments" not in info
    assert "runtime_store_timeline_summary" not in info


def test_extract_service_execution_metrics_handles_missing_and_invalid_rejection_metrics() -> (
    None
):
    """Guard extraction should tolerate missing stats and invalid rejection payloads."""
    _, _, rejection_none = _extract_service_execution_metrics(None)
    assert rejection_none["open_breaker_count"] == 0

    runtime = _make_runtime_data(
        performance_stats={"rejection_metrics": "invalid"},
        coordinator=_Coordinator({}),
        script_manager=None,
    )
    _, _, rejection_invalid = _extract_service_execution_metrics(runtime)
    assert rejection_invalid["open_breaker_count"] == 0


def test_threshold_extractors_cover_none_and_root_option_paths() -> None:
    """Threshold extraction should cover missing and root-option fallbacks."""
    assert _extract_threshold_value({"active": 0, "default": "bad"}) == (None, None)
    assert _resolve_option_threshold(None, "resilience_skip_threshold") == (None, None)
    assert _resolve_option_threshold(
        {"resilience_skip_threshold": "6"},
        "resilience_skip_threshold",
    ) == (6, "root_options")


def test_resolve_option_threshold_falls_back_to_root_when_system_settings_missing_key() -> (
    None
):
    """Root options should be used when system_settings exists but lacks a value."""
    options = {
        "system_settings": {"resilience_skip_threshold": "invalid"},
        "resilience_skip_threshold": 4,
    }

    assert _resolve_option_threshold(options, "resilience_skip_threshold") == (
        4,
        "root_options",
    )


def test_resolve_indicator_thresholds_skips_invalid_script_threshold_values() -> None:
    """Invalid script threshold entries should not override defaults."""

    class _ScriptManager:
        def get_resilience_escalation_snapshot(self) -> dict[str, object]:
            return {
                "thresholds": {
                    "skip_threshold": {"active": "bad"},
                    "breaker_threshold": {"default": "bad"},
                }
            }

    runtime = _make_runtime_data(
        performance_stats={},
        coordinator=_Coordinator({}),
        script_manager=_ScriptManager(),
    )

    guard_thresholds, breaker_thresholds = _resolve_indicator_thresholds(runtime, {})

    assert guard_thresholds.source == "default_ratio"
    assert breaker_thresholds.source == "default_counts"


def test_resolve_indicator_thresholds_ignores_non_mapping_threshold_entries() -> None:
    """Non-mapping threshold entries should leave defaults unchanged."""

    class _ScriptManager:
        def get_resilience_escalation_snapshot(self) -> dict[str, object]:
            return {
                "thresholds": {
                    "skip_threshold": 2,
                    "breaker_threshold": 3,
                }
            }

    runtime = _make_runtime_data(
        performance_stats={},
        coordinator=_Coordinator({}),
        script_manager=_ScriptManager(),
    )

    guard_thresholds, breaker_thresholds = _resolve_indicator_thresholds(runtime, {})

    assert guard_thresholds.source == "default_ratio"
    assert breaker_thresholds.source == "default_counts"


def test_threshold_serializers_skip_empty_payload_sections() -> None:
    """Serializer helpers should omit warning/critical blocks when empty."""
    guard = _serialize_guard_thresholds(
        GuardIndicatorThresholds(
            warning_count=None,
            critical_count=None,
            warning_ratio=None,
            critical_ratio=None,
        ),
    )
    breaker = _serialize_breaker_thresholds(
        BreakerIndicatorThresholds(warning_count=1, critical_count=None),
    )

    assert "warning" not in guard
    assert "critical" not in guard
    assert "warning" in breaker
    assert "critical" not in breaker


def test_describe_guard_threshold_source_additional_branches() -> None:
    """Guard source labels should cover non-default script/config keys."""
    assert (
        _describe_guard_threshold_source(
            GuardIndicatorThresholds(source="resilience_script", source_key="active"),
        )
        == "configured resilience script threshold"
    )
    assert (
        _describe_guard_threshold_source(
            GuardIndicatorThresholds(source="config_entry", source_key="custom"),
        )
        == "options flow threshold"
    )


def test_build_guard_summary_handles_non_mapping_and_non_string_reason_keys() -> None:
    """Reason aggregation should handle malformed payloads defensively."""
    summary_non_mapping = _build_guard_summary(
        {"executed": 1, "skipped": 0, "reasons": ["bad"]},
        GuardIndicatorThresholds(),
    )
    assert summary_non_mapping["reasons"]["missing_instance"] == 0

    summary_non_string_key = _build_guard_summary(
        {"executed": 1, "skipped": 1, "reasons": {1: 4, "valid": 2}},
        GuardIndicatorThresholds(),
    )
    assert all(
        reason["reason"] != "1" for reason in summary_non_string_key["top_reasons"]
    )


def test_build_guard_summary_critical_ratio_path() -> None:
    """Critical ratio thresholds should produce a red ratio-based indicator."""
    summary = _build_guard_summary(
        {"executed": 1, "skipped": 1, "reasons": {}},
        GuardIndicatorThresholds(
            warning_count=None,
            critical_count=None,
            warning_ratio=None,
            critical_ratio=0.5,
        ),
    )

    assert summary["indicator"]["level"] == "critical"
    assert summary["indicator"]["threshold_type"] == "guard_skip_ratio"


def test_coerce_float_handles_value_and_type_errors() -> None:
    """Float coercion should fall back on both value and type conversion errors."""
    assert _coerce_float("invalid", default=1.25) == 1.25
    assert _coerce_float(object(), default=2.5) == 2.5


@pytest.mark.asyncio
async def test_system_health_info_manual_snapshot_non_callable_and_non_mapping_paths(
    hass: Any,
) -> None:
    """Manual snapshot extraction should tolerate non-callable and invalid snapshots."""
    entry = ConfigEntry(domain=DOMAIN, data={}, options={"external_api_quota": 5})
    runtime = _make_runtime_data(
        performance_stats={},
        coordinator=_Coordinator({"performance_metrics": {"api_calls": 0}}),
        script_manager=type(
            "ScriptManagerNonCallable",
            (),
            {"get_resilience_escalation_snapshot": "not-callable"},
        )(),
    )
    entry.runtime_data = runtime
    _install_entry(hass, entry)

    info = await system_health_info(hass)
    assert info["service_execution"]["manual_events"]["available"] is False

    class _ScriptManagerInvalidSnapshot:
        def get_resilience_escalation_snapshot(self) -> list[str]:
            return ["invalid"]

    runtime.script_manager = _ScriptManagerInvalidSnapshot()
    info_invalid = await system_health_info(hass)
    assert info_invalid["service_execution"]["manual_events"]["available"] is False
