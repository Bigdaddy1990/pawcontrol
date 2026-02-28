"""Unit tests for PawControl system health output."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
import pytest

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.system_health import (
    _attach_runtime_store_history,
    _default_service_execution_snapshot,
    _normalise_manual_events_snapshot,
    _resolve_indicator_thresholds,
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


@pytest.mark.asyncio
async def test_system_health_info_returns_default_payload_when_no_entry(hass: Any) -> None:
    """System health should return a stable fallback payload without an entry."""
    info = await system_health_info(hass)

    assert info["can_reach_backend"] is False
    assert info["remaining_quota"] == "unknown"
    assert info["service_execution"]["status"]["overall"]["level"] == "normal"
    assert info["runtime_store"]["status"] == "missing"
