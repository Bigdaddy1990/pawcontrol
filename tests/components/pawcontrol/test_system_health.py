from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from custom_components.pawcontrol import system_health as system_health_module
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.types import (
    CoordinatorHealthIndicators,
    CoordinatorPerformanceMetrics,
    CoordinatorRejectionMetrics,
    CoordinatorRuntimeStoreSummary,
    CoordinatorStatisticsPayload,
    CoordinatorUpdateCounts,
    ManualResilienceOptionsSnapshot,
    PawControlRuntimeData,
    RuntimeStoreAssessmentEvent,
    RuntimeStoreAssessmentTimelineSegment,
    RuntimeStoreAssessmentTimelineSummary,
    RuntimeStoreCompatibilitySnapshot,
    RuntimeStoreHealthAssessment,
    RuntimeStoreHealthHistory,
    RuntimeStoreHealthLevel,
    RuntimeStoreOverallStatus,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _build_statistics_payload(
    *,
    api_calls: int,
    runtime_store: CoordinatorRuntimeStoreSummary | None = None,
) -> CoordinatorStatisticsPayload:
    """Return a fully typed coordinator statistics payload for tests."""

    update_counts: CoordinatorUpdateCounts = {
        "total": api_calls,
        "successful": api_calls,
        "failed": 0,
    }
    performance_metrics: CoordinatorPerformanceMetrics = {
        "success_rate": 1.0,
        "cache_entries": 0,
        "cache_hit_rate": 1.0,
        "consecutive_errors": 0,
        "last_update": datetime.now(UTC).isoformat(),
        "update_interval": 30.0,
        "api_calls": api_calls,
    }
    health_indicators: CoordinatorHealthIndicators = {
        "consecutive_errors": 0,
        "stability_window_ok": True,
    }

    payload: CoordinatorStatisticsPayload = {
        "update_counts": update_counts,
        "performance_metrics": performance_metrics,
        "health_indicators": health_indicators,
    }

    if runtime_store is not None:
        payload["runtime_store"] = runtime_store

    return payload


def _assert_runtime_store(info: Mapping[str, object], expected_status: str) -> None:
    """Assert the runtime store snapshot reported by system health."""

    runtime_store = cast(RuntimeStoreCompatibilitySnapshot, info["runtime_store"])
    assert isinstance(runtime_store, dict)
    assert runtime_store["status"] == expected_status
    history = cast(
        RuntimeStoreHealthHistory | None, info.get("runtime_store_history")
    )
    if history is not None:
        assert history["last_status"] == expected_status
        events = cast(
            Sequence[RuntimeStoreAssessmentEvent] | None,
            history.get("assessment_events"),
        )
        if events is not None:
            assert isinstance(events, list)
            if events:
                assert isinstance(events[-1]["timestamp"], str)
        timeline_segments = cast(
            Sequence[RuntimeStoreAssessmentTimelineSegment] | None,
            history.get("assessment_timeline_segments"),
        )
        if timeline_segments is not None:
            assert isinstance(timeline_segments, list)
            if timeline_segments:
                assert "duration_seconds" in timeline_segments[-1]
        timeline_summary = cast(
            RuntimeStoreAssessmentTimelineSummary | None,
            history.get("assessment_timeline_summary"),
        )
        if timeline_summary is not None:
            assert timeline_summary["total_events"] >= 0
            assert "level_counts" in timeline_summary
            assert "timeline_window_seconds" in timeline_summary
            assert "events_per_day" in timeline_summary
            assert "level_duration_peaks" in timeline_summary
            assert "level_duration_totals" in timeline_summary
            assert "level_duration_samples" in timeline_summary
            assert "level_duration_averages" in timeline_summary
            assert "level_duration_minimums" in timeline_summary
            assert "level_duration_medians" in timeline_summary
            assert "level_duration_standard_deviations" in timeline_summary
            assert "level_duration_percentiles" in timeline_summary
            assert "level_duration_alert_thresholds" in timeline_summary
            assert "level_duration_guard_alerts" in timeline_summary
    assessment = cast(
        RuntimeStoreHealthAssessment | None,
        info.get("runtime_store_assessment"),
    )
    if assessment is not None:
        assert assessment["level"] in {"ok", "watch", "action_required"}
        assert assessment["level_streak"] >= 1
        assert assessment["escalations"] >= 0
        assert assessment["deescalations"] >= 0
        assert assessment["previous_level"] in {None, "ok", "watch", "action_required"}
        assert "level_durations" in assessment
        assert "current_level_duration_seconds" in assessment
        durations = assessment["level_durations"]
        assert isinstance(durations, dict)
        for level_key in cast(
            Sequence[RuntimeStoreHealthLevel], ("ok", "watch", "action_required")
        ):
            assert level_key in durations
            assert durations[level_key] >= 0.0
        current_duration = assessment["current_level_duration_seconds"]
        assert current_duration is None or current_duration >= 0.0
        events = assessment.get("events")
        if events is not None:
            assert isinstance(events, list)
            if events:
                latest_event = events[-1]
                assert latest_event["level"] in {"ok", "watch", "action_required"}
                assert isinstance(latest_event["timestamp"], str)
        timeline_segments = assessment.get("timeline_segments")
        if timeline_segments is not None:
            assert isinstance(timeline_segments, list)
            if timeline_segments:
                assert timeline_segments[-1]["level"] in {"ok", "watch", "action_required"}
                assert "duration_seconds" in timeline_segments[-1]
        timeline_summary = assessment.get("timeline_summary")
        if timeline_summary is not None:
            assert timeline_summary["total_events"] >= 0
            assert "last_level" in timeline_summary
            assert "timeline_window_days" in timeline_summary
            assert "average_divergence_rate" in timeline_summary
            assert "level_duration_latest" in timeline_summary
            assert "level_duration_totals" in timeline_summary
            assert "level_duration_samples" in timeline_summary
            assert "level_duration_averages" in timeline_summary
            assert "level_duration_minimums" in timeline_summary
            assert "level_duration_medians" in timeline_summary
            assert "level_duration_standard_deviations" in timeline_summary
            assert "level_duration_percentiles" in timeline_summary
            assert "level_duration_alert_thresholds" in timeline_summary
            assert "level_duration_guard_alerts" in timeline_summary
    timeline_summary_payload = cast(
        RuntimeStoreAssessmentTimelineSummary | None,
        info.get("runtime_store_timeline_summary"),
    )
    if timeline_summary_payload is not None:
        assert timeline_summary_payload["total_events"] >= 0
        assert "status_counts" in timeline_summary_payload
        assert "most_common_reason" in timeline_summary_payload
        assert "level_duration_samples" in timeline_summary_payload
        assert "level_duration_standard_deviations" in timeline_summary_payload
        assert "level_duration_percentiles" in timeline_summary_payload
        assert "level_duration_alert_thresholds" in timeline_summary_payload
        assert "level_duration_guard_alerts" in timeline_summary_payload
    timeline_segments_payload = cast(
        Sequence[RuntimeStoreAssessmentTimelineSegment] | None,
        info.get("runtime_store_timeline_segments"),
    )
    if timeline_segments_payload is not None:
        assert isinstance(timeline_segments_payload, list)
        if timeline_segments_payload:
            assert "duration_seconds" in timeline_segments_payload[0]


async def test_system_health_no_api(hass: HomeAssistant) -> None:
    """Return defaults when API is unavailable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": [], "entity_profile": "standard"},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pawcontrol.system_health.system_health.async_check_can_reach_url"
    ) as mock_check:
        info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is False
    assert info["remaining_quota"] == "unknown"
    service_execution = info["service_execution"]
    assert service_execution["guard_summary"]["total_calls"] == 0
    assert service_execution["breaker_overview"]["status"] == "healthy"
    assert service_execution["entity_factory_guard"]["last_event"] == "unknown"
    manual_events = service_execution["manual_events"]
    assert manual_events["available"] is False
    assert manual_events["event_history"] == []

    assert manual_events["event_counters"]["total"] == 0
    mock_check.assert_not_called()

    _assert_runtime_store(info, "missing")


async def test_system_health_reports_coordinator_status(
    hass: HomeAssistant,
) -> None:
    """Use coordinator statistics when runtime data is available."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = False
    coordinator.get_update_statistics.return_value = _build_statistics_payload(
        api_calls=3
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        unique_id="coordinator-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
    )

    info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is True
    assert info["remaining_quota"] == "unlimited"
    coordinator.get_update_statistics.assert_called_once()

    service_execution = info["service_execution"]
    assert service_execution["guard_summary"]["total_calls"] == 0
    assert service_execution["guard_summary"]["skip_ratio"] == 0.0
    assert service_execution["breaker_overview"]["status"] == "healthy"
    assert service_execution["entity_factory_guard"]["last_event"] == "unknown"
    assert service_execution["status"]["guard"]["level"] == "normal"
    assert service_execution["status"]["breaker"]["color"] == "green"
    assert service_execution["status"]["overall"]["level"] == "normal"
    manual_events = service_execution["manual_events"]
    assert manual_events["available"] is False
    assert manual_events["event_history"] == []


async def test_system_health_reports_external_quota(
    hass: HomeAssistant,
) -> None:
    """Report remaining quota when external API tracking is enabled."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = True
    coordinator.get_update_statistics.return_value = _build_statistics_payload(
        api_calls=7
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        options={"external_api_quota": 10},
        unique_id="quota-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
    )

    info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is True
    assert info["remaining_quota"] == 3
    assert info["service_execution"]["manual_events"]["available"] is False

    _assert_runtime_store(info, "current")


async def test_system_health_guard_and_breaker_summary(hass: HomeAssistant) -> None:
    """Expose guard skip ratios and breaker details in system health."""

    coordinator = MagicMock()
    coordinator.last_update_success = False
    coordinator.use_external_api = True
    coordinator.get_update_statistics.return_value = _build_statistics_payload(
        api_calls=4
    )

    script_manager = MagicMock()
    script_manager.get_resilience_escalation_snapshot.return_value = {
        "thresholds": {
            "skip_threshold": {"active": 5, "default": 3},
            "breaker_threshold": {"active": 2, "default": 1},
        },
        "manual_events": {
            "available": True,
            "automations": [],
            "configured_guard_events": [],
            "configured_breaker_events": [],
            "configured_check_events": [],
            "preferred_events": {
                "manual_check_event": "pawcontrol_resilience_check",
                "manual_guard_event": "pawcontrol_manual_guard",
                "manual_breaker_event": "pawcontrol_manual_breaker",
            },
            "preferred_guard_event": "pawcontrol_manual_guard",
            "preferred_breaker_event": "pawcontrol_manual_breaker",
            "preferred_check_event": "pawcontrol_resilience_check",
            "active_listeners": [],
            "last_event": {
                "event_type": "pawcontrol_manual_guard",
                "matched_preference": "manual_guard_event",
                "category": "guard",
                "user_id": "support",
                "sources": ["blueprint"],
                "origin": "LOCAL",
            },
            "event_history": [
                {
                    "event_type": "pawcontrol_manual_guard",
                    "matched_preference": "manual_guard_event",
                    "category": "guard",
                    "user_id": "support",
                    "sources": ["blueprint"],
                    "origin": "LOCAL",
                }
            ],
        },
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        options={"external_api_quota": 12},
        unique_id="guard-breaker-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
        performance_stats={
            "service_guard_metrics": {
                "executed": 5,
                "skipped": 3,
                "reasons": {"breaker": 2, "maintenance": 1},
            },
            "entity_factory_guard_metrics": {
                "runtime_floor": 0.0011,
                "baseline_floor": 0.00045,
                "max_floor": 0.0045,
                "runtime_floor_delta": 0.00065,
                "peak_runtime_floor": 0.002,
                "lowest_runtime_floor": 0.00045,
                "last_floor_change": 0.0003,
                "last_floor_change_ratio": 0.35,
                "last_actual_duration": 0.0016,
                "last_duration_ratio": 1.45,
                "last_event": "expand",
                "samples": 8,
                "stable_samples": 4,
                "expansions": 2,
                "contractions": 1,
                "enforce_min_runtime": True,
                "average_duration": 0.0012,
                "max_duration": 0.0016,
                "min_duration": 0.0009,
                "stable_ratio": 0.5,
                "expansion_ratio": 0.25,
                "contraction_ratio": 0.125,
                "volatility_ratio": 0.375,
                "consecutive_stable_samples": 3,
                "longest_stable_run": 5,
                "duration_span": 0.0007,
                "jitter_ratio": 0.0007 / 0.0011,
                "recent_durations": [
                    0.0011,
                    0.0012,
                    0.0014,
                    0.0016,
                    0.0013,
                ],
                "recent_average_duration": 0.00132,
                "recent_max_duration": 0.0016,
                "recent_min_duration": 0.0011,
                "recent_duration_span": 0.0005,
                "recent_jitter_ratio": 0.0005 / 0.0011,
                "recent_samples": 5,
                "recent_events": [
                    "stable",
                    "expand",
                    "stable",
                    "contract",
                    "stable",
                ],
                "recent_stable_samples": 3,
                "recent_stable_ratio": 3 / 5,
                "stability_trend": "steady",
            },
            "rejection_metrics": {
                "schema_version": 3,
                "rejected_call_count": 6,
                "rejection_breaker_count": 2,
                "rejection_rate": 0.42,
                "open_breaker_count": 1,
                "open_breakers": ["Primary API"],
                "half_open_breaker_count": 1,
                "half_open_breakers": ["Telemetry"],
                "unknown_breaker_count": 0,
                "last_rejection_breaker_id": "primary",
                "last_rejection_breaker_name": "Primary API",
                "last_rejection_time": 1_700_000_500.0,
            },
        },
        script_manager=script_manager,
    )

    info = await system_health_module.system_health_info(hass)

    assert info["remaining_quota"] == 8

    service_execution = info["service_execution"]
    guard_summary = service_execution["guard_summary"]
    assert guard_summary["total_calls"] == 8
    assert guard_summary["has_skips"] is True
    assert guard_summary["skip_ratio"] == pytest.approx(3 / 8)
    assert guard_summary["top_reasons"][0] == {"reason": "breaker", "count": 2}
    assert guard_summary["thresholds"]["source"] == "resilience_script"
    entity_guard = service_execution["entity_factory_guard"]
    assert entity_guard["last_event"] == "expand"
    assert entity_guard["runtime_floor_ms"] == pytest.approx(1.1)
    assert entity_guard["runtime_floor_delta_ms"] == pytest.approx(0.65)
    assert entity_guard["peak_runtime_floor_ms"] == pytest.approx(2.0)
    assert entity_guard["lowest_runtime_floor_ms"] == pytest.approx(0.45)
    assert entity_guard["last_floor_change_ms"] == pytest.approx(0.3)
    assert entity_guard["average_duration_ms"] == pytest.approx(1.2)
    assert entity_guard["max_duration_ms"] == pytest.approx(1.6)
    assert entity_guard["min_duration_ms"] == pytest.approx(0.9)
    assert entity_guard["duration_span_ms"] == pytest.approx(0.7)
    assert entity_guard["jitter_ratio"] == pytest.approx(0.0007 / 0.0011)
    assert entity_guard["recent_average_duration_ms"] == pytest.approx(1.32)
    assert entity_guard["recent_max_duration_ms"] == pytest.approx(1.6)
    assert entity_guard["recent_min_duration_ms"] == pytest.approx(1.1)
    assert entity_guard["recent_duration_span_ms"] == pytest.approx(0.5)
    assert entity_guard["recent_jitter_ratio"] == pytest.approx(0.0005 / 0.0011)
    assert entity_guard["stable_ratio"] == pytest.approx(0.5)
    assert entity_guard["expansion_ratio"] == pytest.approx(0.25)
    assert entity_guard["contraction_ratio"] == pytest.approx(0.125)
    assert entity_guard["volatility_ratio"] == pytest.approx(0.375)
    assert entity_guard["consecutive_stable_samples"] == 3
    assert entity_guard["longest_stable_run"] == 5
    assert entity_guard["last_floor_change_ratio"] == pytest.approx(0.35)
    assert entity_guard["recent_samples"] == 5
    assert entity_guard["recent_events"] == [
        "stable",
        "expand",
        "stable",
        "contract",
        "stable",
    ]
    assert entity_guard["recent_stable_samples"] == 3
    assert entity_guard["recent_stable_ratio"] == pytest.approx(3 / 5)
    assert entity_guard["stability_trend"] == "steady"
    manual_events = service_execution["manual_events"]
    assert manual_events["available"] is True
    assert manual_events["last_event"]["event_type"] == "pawcontrol_manual_guard"
    assert manual_events["last_event"]["user_id"] == "support"
    assert manual_events["event_history"][0]["sources"] == ["blueprint"]

    _assert_runtime_store(info, "current")
    assert guard_summary["thresholds"]["source_key"] == "active"
    assert guard_summary["thresholds"]["warning"]["count"] == 4
    assert guard_summary["thresholds"]["critical"]["count"] == 5
    guard_indicator = guard_summary["indicator"]
    assert guard_indicator["level"] == "warning"
    assert guard_indicator["color"] == "amber"
    assert guard_indicator["threshold_source"] == "default_ratio"
    assert "system default threshold" in guard_indicator["message"]

    rejection_metrics = service_execution["rejection_metrics"]
    assert rejection_metrics["open_breaker_count"] == 1
    assert rejection_metrics["half_open_breaker_count"] == 1
    assert rejection_metrics["rejection_rate"] == pytest.approx(0.42)

    breaker_overview = service_execution["breaker_overview"]
    assert breaker_overview["status"] == "open"
    assert breaker_overview["open_breakers"] == ["Primary API"]
    assert breaker_overview["half_open_breakers"] == ["Telemetry"]
    assert breaker_overview["thresholds"]["critical"]["count"] == 2
    breaker_indicator = breaker_overview["indicator"]
    assert breaker_indicator["level"] == "critical"
    assert breaker_indicator["threshold"] == 2
    assert breaker_indicator["threshold_source"] == "active"
    assert "configured resilience script threshold" in breaker_indicator["message"]

    status = service_execution["status"]
    assert status["guard"]["level"] == "warning"
    assert status["breaker"]["level"] == "critical"
    assert status["overall"]["level"] == "critical"


async def test_system_health_indicator_critical_paths(hass: HomeAssistant) -> None:
    """Surface critical status when guard ratios and breakers exceed thresholds."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = False
    coordinator.get_update_statistics.return_value = _build_statistics_payload(
        api_calls=2
    )

    script_manager = MagicMock()
    script_manager.get_resilience_escalation_snapshot.return_value = {
        "thresholds": {
            "skip_threshold": {"active": 5, "default": 3},
            "breaker_threshold": {"active": 2, "default": 1},
        },
        "manual_events": {
            "available": False,
            "automations": [],
            "configured_guard_events": [],
            "configured_breaker_events": [],
            "configured_check_events": [],
            "preferred_events": {
                "manual_check_event": "pawcontrol_resilience_check",
                "manual_guard_event": "pawcontrol_manual_guard",
                "manual_breaker_event": "pawcontrol_manual_breaker",
            },
            "preferred_guard_event": "pawcontrol_manual_guard",
            "preferred_breaker_event": "pawcontrol_manual_breaker",
            "preferred_check_event": "pawcontrol_resilience_check",
            "active_listeners": [],
            "last_event": None,
        },
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        unique_id="critical-indicator-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
        performance_stats={
            "service_guard_metrics": {
                "executed": 2,
                "skipped": 5,
                "reasons": {"breaker": 3, "maintenance": 2},
            },
            "entity_factory_guard_metrics": {
                "runtime_floor": 0.0012,
                "baseline_floor": 0.00045,
                "max_floor": 0.0045,
                "runtime_floor_delta": 0.00075,
                "peak_runtime_floor": 0.0021,
                "lowest_runtime_floor": 0.00045,
                "last_floor_change": -0.0002,
                "last_floor_change_ratio": -0.15,
                "last_actual_duration": 0.0018,
                "last_duration_ratio": 1.5,
                "last_event": "contract",
                "samples": 9,
                "stable_samples": 4,
                "expansions": 2,
                "contractions": 1,
                "enforce_min_runtime": True,
                "average_duration": 0.0014,
                "max_duration": 0.0019,
                "min_duration": 0.001,
                "stable_ratio": 4 / 9,
                "expansion_ratio": 2 / 9,
                "contraction_ratio": 1 / 9,
                "volatility_ratio": 3 / 9,
                "consecutive_stable_samples": 2,
                "longest_stable_run": 4,
                "duration_span": 0.0009,
                "jitter_ratio": 0.0009 / 0.0012,
                "recent_durations": [
                    0.0012,
                    0.0013,
                    0.0018,
                    0.0019,
                    0.0011,
                ],
                "recent_average_duration": 0.00146,
                "recent_max_duration": 0.0019,
                "recent_min_duration": 0.0011,
                "recent_duration_span": 0.0008,
                "recent_jitter_ratio": 0.0008 / 0.0012,
                "recent_samples": 5,
                "recent_events": [
                    "expand",
                    "stable",
                    "contract",
                    "stable",
                    "stable",
                ],
                "recent_stable_samples": 3,
                "recent_stable_ratio": 3 / 5,
                "stability_trend": "steady",
            },
            "rejection_metrics": {
                "schema_version": 3,
                "rejected_call_count": 10,
                "rejection_breaker_count": 1,
                "rejection_rate": 0.78,
                "open_breaker_count": 2,
                "open_breakers": ["Primary API", "Sync"],
                "half_open_breaker_count": 1,
                "half_open_breakers": ["Telemetry"],
                "unknown_breaker_count": 0,
            },
        },
        script_manager=script_manager,
    )

    info = await system_health_module.system_health_info(hass)

    service_execution = info["service_execution"]
    guard_indicator = service_execution["guard_summary"]["indicator"]
    assert guard_indicator["level"] == "critical"
    assert guard_indicator["color"] == "red"
    assert guard_indicator["threshold_source"] == "active"
    assert "configured resilience script threshold" in guard_indicator["message"]
    entity_guard = service_execution["entity_factory_guard"]
    assert entity_guard["last_event"] == "contract"
    assert entity_guard["contractions"] == 1
    assert entity_guard["runtime_floor_delta_ms"] == pytest.approx(0.75)
    assert entity_guard["peak_runtime_floor_ms"] == pytest.approx(2.1)
    assert entity_guard["lowest_runtime_floor_ms"] == pytest.approx(0.45)
    assert entity_guard["last_floor_change_ms"] == pytest.approx(-0.2)
    assert entity_guard["average_duration_ms"] == pytest.approx(1.4)
    assert entity_guard["duration_span_ms"] == pytest.approx(0.9)
    assert entity_guard["jitter_ratio"] == pytest.approx(0.0009 / 0.0012)
    assert entity_guard["recent_average_duration_ms"] == pytest.approx(1.46)
    assert entity_guard["recent_max_duration_ms"] == pytest.approx(1.9)
    assert entity_guard["recent_min_duration_ms"] == pytest.approx(1.1)
    assert entity_guard["recent_duration_span_ms"] == pytest.approx(0.8)
    assert entity_guard["recent_jitter_ratio"] == pytest.approx(0.0008 / 0.0012)
    assert entity_guard["stable_ratio"] == pytest.approx(4 / 9)

    _assert_runtime_store(info, "current")
    assert entity_guard["expansion_ratio"] == pytest.approx(2 / 9)
    assert entity_guard["contraction_ratio"] == pytest.approx(1 / 9)
    assert entity_guard["volatility_ratio"] == pytest.approx(3 / 9)
    assert entity_guard["consecutive_stable_samples"] == 2
    assert entity_guard["longest_stable_run"] == 4
    assert entity_guard["last_floor_change_ratio"] == pytest.approx(-0.15)
    assert entity_guard["recent_samples"] == 5
    assert entity_guard["recent_events"] == [
        "expand",
        "stable",
        "contract",
        "stable",
        "stable",
    ]
    assert entity_guard["recent_stable_samples"] == 3
    assert entity_guard["recent_stable_ratio"] == pytest.approx(3 / 5)
    assert entity_guard["stability_trend"] == "steady"

    breaker_indicator = service_execution["breaker_overview"]["indicator"]
    assert breaker_indicator["level"] == "critical"
    assert breaker_indicator["metric"] == 3
    assert breaker_indicator["threshold_source"] == "active"

    overall_indicator = service_execution["status"]["overall"]
    assert overall_indicator["level"] == "critical"
    assert overall_indicator["color"] == "red"


async def test_system_health_threshold_disabled_fallbacks(
    hass: HomeAssistant,
) -> None:
    """Fallback to ratio and default counts when thresholds are disabled."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = False
    coordinator.get_update_statistics.return_value = _build_statistics_payload(
        api_calls=5
    )

    script_manager = MagicMock()
    script_manager.get_resilience_escalation_snapshot.return_value = {
        "thresholds": {
            "skip_threshold": {"active": 0, "default": 0},
            "breaker_threshold": {"active": 0, "default": 0},
        },
        "manual_events": {
            "available": False,
            "automations": [],
            "configured_guard_events": [],
            "configured_breaker_events": [],
            "configured_check_events": [],
            "preferred_events": {
                "manual_check_event": "pawcontrol_resilience_check",
                "manual_guard_event": "pawcontrol_manual_guard",
                "manual_breaker_event": "pawcontrol_manual_breaker",
            },
            "preferred_guard_event": "pawcontrol_manual_guard",
            "preferred_breaker_event": "pawcontrol_manual_breaker",
            "preferred_check_event": "pawcontrol_resilience_check",
            "active_listeners": [],
            "last_event": None,
        },
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        unique_id="threshold-disabled-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
        performance_stats={
            "service_guard_metrics": {
                "executed": 1,
                "skipped": 1,
                "reasons": {"breaker": 1},
            },
            "entity_factory_guard_metrics": {
                "runtime_floor": 0.0008,
                "baseline_floor": 0.00045,
                "max_floor": 0.0045,
                "runtime_floor_delta": 0.00035,
                "peak_runtime_floor": 0.001,
                "lowest_runtime_floor": 0.00045,
                "last_floor_change": 0.0,
                "last_floor_change_ratio": 0.0,
                "last_actual_duration": 0.0009,
                "last_duration_ratio": 1.1,
                "last_event": "stable",
                "samples": 4,
                "stable_samples": 3,
                "expansions": 0,
                "contractions": 0,
                "enforce_min_runtime": True,
                "average_duration": 0.00085,
                "max_duration": 0.00095,
                "min_duration": 0.0007,
                "stable_ratio": 0.75,
                "expansion_ratio": 0.0,
                "contraction_ratio": 0.0,
                "volatility_ratio": 0.0,
                "consecutive_stable_samples": 3,
                "longest_stable_run": 3,
                "duration_span": 0.00025,
                "jitter_ratio": 0.00025 / 0.0008,
                "recent_durations": [0.0008, 0.00082, 0.0009, 0.00095],
                "recent_average_duration": 0.0008675,
                "recent_max_duration": 0.00095,
                "recent_min_duration": 0.0008,
                "recent_duration_span": 0.00015,
                "recent_jitter_ratio": 0.00015 / 0.0008,
                "recent_samples": 4,
                "recent_events": ["stable", "stable", "stable", "stable"],
                "recent_stable_samples": 4,
                "recent_stable_ratio": 1.0,
                "stability_trend": "steady",
            },
            "rejection_metrics": {
                "schema_version": 3,
                "rejected_call_count": 0,
                "rejection_breaker_count": 0,
                "rejection_rate": 0.0,
                "open_breaker_count": 2,
                "open_breakers": ["Primary", "Backup"],
                "half_open_breaker_count": 1,
                "half_open_breakers": ["Telemetry"],
            },
        },
        script_manager=script_manager,
    )

    info = await system_health_module.system_health_info(hass)

    guard_summary = info["service_execution"]["guard_summary"]
    assert guard_summary["thresholds"]["source"] == "default_ratio"
    assert guard_summary["thresholds"]["critical"]["ratio"] == pytest.approx(0.5)
    guard_indicator = guard_summary["indicator"]
    assert guard_indicator["level"] == "critical"
    assert guard_indicator["threshold_source"] == "default_ratio"
    assert "system default threshold" in guard_indicator["message"]
    entity_guard = info["service_execution"]["entity_factory_guard"]
    assert entity_guard["last_event"] == "stable"
    assert entity_guard["runtime_floor_delta_ms"] == pytest.approx(0.35)
    assert entity_guard["peak_runtime_floor_ms"] == pytest.approx(1.0)
    assert entity_guard["lowest_runtime_floor_ms"] == pytest.approx(0.45)
    assert entity_guard["last_floor_change_ms"] == pytest.approx(0.0)
    assert entity_guard["average_duration_ms"] == pytest.approx(0.85)
    assert entity_guard["duration_span_ms"] == pytest.approx(0.25)
    assert entity_guard["jitter_ratio"] == pytest.approx(0.00025 / 0.0008)
    assert entity_guard["recent_average_duration_ms"] == pytest.approx(0.8675)
    assert entity_guard["recent_max_duration_ms"] == pytest.approx(0.95)
    assert entity_guard["recent_min_duration_ms"] == pytest.approx(0.8)
    assert entity_guard["recent_duration_span_ms"] == pytest.approx(0.15)
    assert entity_guard["recent_jitter_ratio"] == pytest.approx(0.00015 / 0.0008)
    assert entity_guard["stable_ratio"] == pytest.approx(0.75)
    assert entity_guard["expansion_ratio"] == pytest.approx(0.0)
    assert entity_guard["contraction_ratio"] == pytest.approx(0.0)
    assert entity_guard["volatility_ratio"] == pytest.approx(0.0)
    assert entity_guard["consecutive_stable_samples"] == 3
    assert entity_guard["longest_stable_run"] == 3
    assert entity_guard["last_floor_change_ratio"] == pytest.approx(0.0)
    assert entity_guard["recent_samples"] == 4
    assert entity_guard["recent_events"] == [
        "stable",
        "stable",
        "stable",
        "stable",
    ]
    assert entity_guard["recent_stable_samples"] == 4

    _assert_runtime_store(info, "current")
    assert entity_guard["recent_stable_ratio"] == pytest.approx(1.0)
    assert entity_guard["stability_trend"] == "steady"

    breaker_overview = info["service_execution"]["breaker_overview"]
    assert breaker_overview["thresholds"]["source"] == "default_counts"
    breaker_indicator = breaker_overview["indicator"]
    assert breaker_indicator["level"] == "critical"
    assert breaker_indicator["threshold"] == 3
    assert "system default threshold" in breaker_indicator["message"]

    status = info["service_execution"]["status"]
    assert status["overall"]["level"] == "critical"


def test_resolve_indicator_thresholds_prefers_script_snapshot() -> None:
    """Prefer resilience script thresholds over config entry options."""

    script_manager = MagicMock()
    script_manager.get_resilience_escalation_snapshot.return_value = {
        "thresholds": {
            "skip_threshold": {"active": 4, "default": 2},
            "breaker_threshold": {"active": 3, "default": 1},
        }
    }

    runtime = SimpleNamespace(script_manager=script_manager)

    options: ManualResilienceOptionsSnapshot = {
        "resilience_skip_threshold": 6,
        "resilience_breaker_threshold": 5,
        "system_settings": {
            "resilience_skip_threshold": 7,
            "resilience_breaker_threshold": 6,
        },
    }

    guard_thresholds, breaker_thresholds = (
        system_health_module._resolve_indicator_thresholds(runtime, options)
    )

    script_manager.get_resilience_escalation_snapshot.assert_called_once()
    assert guard_thresholds.source == "resilience_script"
    assert guard_thresholds.source_key == "active"
    assert guard_thresholds.critical_count == 4
    assert guard_thresholds.warning_count == 3
    assert guard_thresholds.warning_ratio == pytest.approx(
        system_health_module.GUARD_SKIP_WARNING_RATIO
    )
    assert breaker_thresholds.source == "resilience_script"
    assert breaker_thresholds.source_key == "active"
    assert breaker_thresholds.critical_count == 3
    assert breaker_thresholds.warning_count == 2


def test_resolve_indicator_thresholds_uses_config_entry_fallback() -> None:
    """Fallback to config entry thresholds when script metadata is absent."""

    options: ManualResilienceOptionsSnapshot = {
        "resilience_skip_threshold": 5,
        "system_settings": {"resilience_breaker_threshold": 4},
    }

    guard_thresholds, breaker_thresholds = (
        system_health_module._resolve_indicator_thresholds(None, options)
    )

    assert guard_thresholds.source == "config_entry"
    assert guard_thresholds.source_key == "root_options"
    assert guard_thresholds.critical_count == 5
    assert guard_thresholds.warning_count == 4
    assert guard_thresholds.warning_ratio == pytest.approx(
        system_health_module.GUARD_SKIP_WARNING_RATIO
    )

    assert breaker_thresholds.source == "config_entry"
    assert breaker_thresholds.source_key == "system_settings"
    assert breaker_thresholds.critical_count == 4
    assert breaker_thresholds.warning_count == 3


def test_build_breaker_overview_serialises_metrics_and_thresholds() -> None:
    """Serialise breaker overview using rejection metrics and thresholds."""

    thresholds = system_health_module.BreakerIndicatorThresholds(
        warning_count=1,
        critical_count=2,
        source="resilience_script",
        source_key="active",
    )

    metrics: CoordinatorRejectionMetrics = {
        "schema_version": 3,
        "rejected_call_count": 5,
        "rejection_breaker_count": 2,
        "rejection_rate": 0.5,
        "open_breaker_count": 2,
        "half_open_breaker_count": 1,
        "unknown_breaker_count": 1,
        "open_breakers": ["Primary API", "Telemetry"],
        "half_open_breakers": ["Sync"],
        "unknown_breakers": ["Legacy"],
        "last_rejection_breaker_id": "primary",
        "last_rejection_breaker_name": "Primary API",
        "last_rejection_time": 1_700_000_500.0,
    }

    overview = system_health_module._build_breaker_overview(metrics, thresholds)

    assert overview["status"] == "open"
    assert overview["open_breaker_count"] == 2
    assert overview["half_open_breaker_count"] == 1
    assert overview["unknown_breaker_count"] == 1
    assert overview["rejection_rate"] == pytest.approx(0.5)
    assert overview["last_rejection_breaker_id"] == "primary"
    assert overview["last_rejection_breaker_name"] == "Primary API"
    assert overview["last_rejection_time"] == pytest.approx(1_700_000_500.0)
    assert overview["open_breakers"] == ["Primary API", "Telemetry"]
    assert overview["half_open_breakers"] == ["Sync"]
    assert overview["unknown_breakers"] == ["Legacy"]

    thresholds_summary = overview["thresholds"]
    assert thresholds_summary["source"] == "resilience_script"
    assert thresholds_summary["source_key"] == "active"
    assert thresholds_summary["warning"] == {"count": 1}
    assert thresholds_summary["critical"] == {"count": 2}

    indicator = overview["indicator"]
    assert indicator["level"] == "critical"
    assert indicator["color"] == "red"
    assert indicator["metric"] == 3
    assert indicator["threshold"] == 2
    assert indicator["threshold_source"] == "active"
    assert indicator["context"] == "breaker"


async def test_system_health_uses_option_thresholds(
    hass: HomeAssistant,
) -> None:
    """Use options flow thresholds when script metadata is unavailable."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = False
    coordinator.get_update_statistics.return_value = _build_statistics_payload(
        api_calls=1
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        options={
            "system_settings": {
                "resilience_skip_threshold": 4,
                "resilience_breaker_threshold": 2,
            }
        },
        unique_id="options-threshold-entry",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
        performance_stats={
            "service_guard_metrics": {
                "executed": 2,
                "skipped": 3,
                "reasons": {"breaker": 3},
            },
            "entity_factory_guard_metrics": {
                "runtime_floor": 0.001,
                "baseline_floor": 0.00045,
                "max_floor": 0.0045,
                "runtime_floor_delta": 0.00055,
                "peak_runtime_floor": 0.0014,
                "lowest_runtime_floor": 0.00045,
                "last_floor_change": 0.0001,
                "last_floor_change_ratio": 0.1,
                "last_actual_duration": 0.0012,
                "last_duration_ratio": 1.2,
                "last_event": "expand",
                "samples": 5,
                "stable_samples": 3,
                "expansions": 1,
                "contractions": 0,
                "enforce_min_runtime": True,
                "average_duration": 0.00105,
                "max_duration": 0.0013,
                "min_duration": 0.0009,
                "stable_ratio": 3 / 5,
                "expansion_ratio": 1 / 5,
                "contraction_ratio": 0.0,
                "volatility_ratio": 1 / 5,
                "consecutive_stable_samples": 2,
                "longest_stable_run": 3,
                "duration_span": 0.0004,
                "jitter_ratio": 0.0004 / 0.001,
                "recent_durations": [0.001, 0.0012, 0.0011],
                "recent_average_duration": 0.0011,
                "recent_max_duration": 0.0012,
                "recent_min_duration": 0.001,
                "recent_duration_span": 0.0002,
                "recent_jitter_ratio": 0.0002 / 0.001,
                "recent_samples": 3,
                "recent_events": ["stable", "expand", "stable"],
                "recent_stable_samples": 2,
                "recent_stable_ratio": 2 / 3,
                "stability_trend": "improving",
            },
            "rejection_metrics": {
                "schema_version": 3,
                "rejected_call_count": 0,
                "rejection_breaker_count": 0,
                "rejection_rate": 0.0,
                "open_breaker_count": 2,
                "open_breakers": ["Primary", "Backup"],
                "half_open_breaker_count": 0,
                "half_open_breakers": [],
            },
        },
        script_manager=None,
    )

    info = await system_health_module.system_health_info(hass)

    guard_summary = info["service_execution"]["guard_summary"]
    assert guard_summary["thresholds"]["source"] == "config_entry"
    assert guard_summary["thresholds"]["critical"]["count"] == 4
    guard_indicator = guard_summary["indicator"]
    assert guard_indicator["level"] == "warning"
    assert guard_indicator["threshold_source"] == "system_settings"
    assert "options flow system settings threshold" in guard_indicator["message"]
    entity_guard = info["service_execution"]["entity_factory_guard"]
    assert entity_guard["expansions"] == 1
    assert entity_guard["runtime_floor_ms"] == pytest.approx(1.0)
    assert entity_guard["runtime_floor_delta_ms"] == pytest.approx(0.55)
    assert entity_guard["peak_runtime_floor_ms"] == pytest.approx(1.4)
    assert entity_guard["lowest_runtime_floor_ms"] == pytest.approx(0.45)
    assert entity_guard["last_floor_change_ms"] == pytest.approx(0.1)
    assert entity_guard["last_floor_change_ratio"] == pytest.approx(0.1)
    assert entity_guard["average_duration_ms"] == pytest.approx(1.05)
    assert entity_guard["max_duration_ms"] == pytest.approx(1.3)
    assert entity_guard["min_duration_ms"] == pytest.approx(0.9)
    assert entity_guard["duration_span_ms"] == pytest.approx(0.4)
    assert entity_guard["jitter_ratio"] == pytest.approx(0.0004 / 0.001)
    assert entity_guard["stable_ratio"] == pytest.approx(3 / 5)
    assert entity_guard["expansion_ratio"] == pytest.approx(1 / 5)
    assert entity_guard["contraction_ratio"] == pytest.approx(0.0)
    assert entity_guard["volatility_ratio"] == pytest.approx(1 / 5)
    assert entity_guard["consecutive_stable_samples"] == 2
    assert entity_guard["longest_stable_run"] == 3
    assert entity_guard["recent_average_duration_ms"] == pytest.approx(1.1)
    assert entity_guard["recent_max_duration_ms"] == pytest.approx(1.2)

    _assert_runtime_store(info, "current")
    assert entity_guard["recent_min_duration_ms"] == pytest.approx(1.0)
    assert entity_guard["recent_duration_span_ms"] == pytest.approx(0.2)
    assert entity_guard["recent_jitter_ratio"] == pytest.approx(0.0002 / 0.001)
    assert entity_guard["recent_samples"] == 3
    assert entity_guard["recent_events"] == ["stable", "expand", "stable"]
    assert entity_guard["recent_stable_samples"] == 2
    assert entity_guard["recent_stable_ratio"] == pytest.approx(2 / 3)
    assert entity_guard["stability_trend"] == "improving"

    breaker_overview = info["service_execution"]["breaker_overview"]
    assert breaker_overview["thresholds"]["source"] == "config_entry"
    assert breaker_overview["thresholds"]["critical"]["count"] == 2
    breaker_indicator = breaker_overview["indicator"]
    assert breaker_indicator["level"] == "critical"
    assert breaker_indicator["threshold_source"] == "system_settings"
    assert "options flow system settings threshold" in breaker_indicator["message"]

    status = info["service_execution"]["status"]
    assert status["overall"]["level"] == "critical"
