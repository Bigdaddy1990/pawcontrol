"""Unit tests for runtime store telemetry helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from custom_components.pawcontrol import telemetry as telemetry_module
from custom_components.pawcontrol.telemetry import (
    get_runtime_store_health,
    update_runtime_store_health,
)
from custom_components.pawcontrol.types import RuntimeStoreCompatibilitySnapshot


def _runtime_data() -> SimpleNamespace:
    """Return a minimal runtime data container for telemetry tests."""

    return SimpleNamespace(performance_stats={})


def _snapshot(
    *,
    status: str = "current",
    entry_status: str = "current",
    store_status: str = "current",
    divergence: bool = False,
) -> RuntimeStoreCompatibilitySnapshot:
    """Build a runtime store compatibility snapshot for testing."""

    return {
        "entry_id": "entry",
        "status": status,  # type: ignore[assignment]
        "current_version": 2,
        "minimum_compatible_version": 1,
        "entry": {
            "available": True,
            "status": entry_status,  # type: ignore[assignment]
            "version": 2,
            "created_version": 2,
        },
        "store": {
            "available": True,
            "status": store_status,  # type: ignore[assignment]
            "version": 2,
            "created_version": 2,
        },
        "divergence_detected": divergence,
    }


def test_update_runtime_store_health_records_counts(monkeypatch) -> None:
    """Recording telemetry should update counts and metadata."""

    runtime_data = _runtime_data()
    snapshot = _snapshot()
    monkeypatch.setattr(
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: datetime(2024, 1, 1, tzinfo=UTC),
    )

    history = update_runtime_store_health(runtime_data, snapshot)

    assert history is not None
    assert history["schema_version"] == 1
    assert history["checks"] == 1
    assert history["status_counts"] == {"current": 1}
    assert history["divergence_events"] == 0
    assert history["last_status"] == "current"
    assert history["last_entry_status"] == "current"
    assert history["last_store_status"] == "current"
    assert history["last_checked"] == "2024-01-01T00:00:00+00:00"
    timeline_summary = history.get("assessment_timeline_summary")
    assert timeline_summary is not None
    assert timeline_summary["total_events"] == 1
    assert timeline_summary["level_changes"] == 1
    assert timeline_summary["level_counts"]["ok"] == 1
    assert timeline_summary["status_counts"]["current"] == 1
    assert timeline_summary["distinct_reasons"] == 1
    assert timeline_summary["first_event_timestamp"] == "2024-01-01T00:00:00+00:00"
    assert timeline_summary["last_event_timestamp"] == "2024-01-01T00:00:00+00:00"
    assert timeline_summary["last_level"] == "ok"
    assert timeline_summary["last_status"] == "current"
    assert timeline_summary["level_change_rate"] == pytest.approx(1.0)
    assert timeline_summary["timeline_window_seconds"] == pytest.approx(0.0)
    assert timeline_summary["timeline_window_days"] == pytest.approx(0.0)
    assert timeline_summary["events_per_day"] == pytest.approx(1.0)
    assert (
        timeline_summary["most_common_reason"]
        == "Runtime store metadata matches the active schema."
    )
    assert timeline_summary["most_common_level"] == "ok"
    assert timeline_summary["most_common_status"] == "current"
    assert timeline_summary["average_divergence_rate"] == pytest.approx(0.0)
    assert timeline_summary["max_divergence_rate"] == pytest.approx(0.0)
    assert timeline_summary["last_level_duration_seconds"] == pytest.approx(0.0)
    assert timeline_summary["level_duration_peaks"]["ok"] == pytest.approx(0.0)
    assert timeline_summary["level_duration_peaks"]["watch"] == pytest.approx(0.0)
    assert timeline_summary["level_duration_peaks"]["action_required"] == pytest.approx(
        0.0
    )
    assert timeline_summary["level_duration_latest"]["ok"] == pytest.approx(0.0)
    assert timeline_summary["level_duration_latest"]["watch"] is None
    assert timeline_summary["level_duration_latest"]["action_required"] is None
    assessment = history.get("assessment")
    assert assessment is not None
    assert assessment["level"] == "ok"
    assert assessment["previous_level"] is None
    assert assessment["divergence_events"] == 0
    assert assessment["recommended_action"] is None
    assert assessment["level_streak"] == 1
    assert assessment["last_level_change"] == "2024-01-01T00:00:00+00:00"
    assert assessment["escalations"] == 0
    assert assessment["deescalations"] == 0
    assert assessment["current_level_duration_seconds"] == pytest.approx(0.0)
    durations = assessment["level_durations"]
    assert durations["ok"] == pytest.approx(0.0)
    assert durations["watch"] == pytest.approx(0.0)
    assert durations["action_required"] == pytest.approx(0.0)
    events = assessment["events"]
    assert isinstance(events, list)
    assert len(events) == 1
    first_event = events[0]
    assert first_event["timestamp"] == "2024-01-01T00:00:00+00:00"
    assert first_event["level"] == "ok"
    assert first_event["status"] == "current"
    assert first_event["entry_status"] == "current"
    assert first_event["store_status"] == "current"
    assert first_event["level_changed"] is True
    assert first_event["divergence_detected"] is False
    assert first_event["checks"] == 1
    assert history["assessment_events"] == events
    assert assessment["timeline_summary"]["total_events"] == 1
    assert (
        assessment["timeline_summary"]["last_event_timestamp"]
        == "2024-01-01T00:00:00+00:00"
    )


def test_update_runtime_store_health_does_not_increment_when_suppressed(
    monkeypatch,
) -> None:
    """Suppressing recording should still refresh last status without new counts."""

    runtime_data = _runtime_data()
    first_snapshot = _snapshot(status="current")
    monkeypatch.setattr(
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: datetime(2024, 1, 1, tzinfo=UTC),
    )
    update_runtime_store_health(runtime_data, first_snapshot)

    second_snapshot = _snapshot(status="diverged", divergence=True)
    monkeypatch.setattr(
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: datetime(2024, 1, 2, tzinfo=UTC),
    )
    history = update_runtime_store_health(
        runtime_data, second_snapshot, record_event=False
    )

    assert history is not None
    assert history["checks"] == 1
    # Status counts should not increment when recording is suppressed.
    assert history["status_counts"] == {"current": 1}
    assert history["last_status"] == "diverged"
    assert history["divergence_detected"] is True
    assert history["last_checked"] == "2024-01-02T00:00:00+00:00"
    timeline_summary = history.get("assessment_timeline_summary")
    assert timeline_summary is not None
    assert timeline_summary["total_events"] == 2
    assert timeline_summary["level_changes"] == 2
    assert timeline_summary["level_counts"]["ok"] == 1
    assert timeline_summary["level_counts"]["watch"] == 1
    assert timeline_summary["status_counts"]["diverged"] == 1
    assert timeline_summary["last_event_timestamp"] == "2024-01-02T00:00:00+00:00"
    assert timeline_summary["last_level"] == "watch"
    assert timeline_summary["last_status"] == "diverged"
    assert timeline_summary["timeline_window_seconds"] == pytest.approx(86400.0)
    assert timeline_summary["timeline_window_days"] == pytest.approx(1.0)
    assert timeline_summary["events_per_day"] == pytest.approx(2.0)
    assert timeline_summary["most_common_reason"] is not None
    assert timeline_summary["most_common_level"] == "ok"
    assert timeline_summary["most_common_status"] == "current"
    assert timeline_summary["average_divergence_rate"] == pytest.approx(0.0)
    assert timeline_summary["max_divergence_rate"] == pytest.approx(0.0)
    assert timeline_summary["level_duration_peaks"]["ok"] >= 0.0
    assert timeline_summary["level_duration_peaks"]["watch"] >= 0.0
    assert timeline_summary["last_level_duration_seconds"] == pytest.approx(0.0)
    assert timeline_summary["level_duration_latest"]["watch"] == pytest.approx(0.0)
    assessment = history.get("assessment")
    assert assessment is not None
    assert assessment["level"] == "watch"
    assert assessment["divergence_detected"] is True
    assert assessment["previous_level"] == "ok"
    assert assessment["level_streak"] == 1
    assert assessment["last_level_change"] == "2024-01-02T00:00:00+00:00"
    assert assessment["escalations"] == 1
    assert assessment["deescalations"] == 0
    durations = assessment["level_durations"]
    assert durations["ok"] == pytest.approx(86400.0)
    assert durations["watch"] == pytest.approx(0.0)
    assert durations["action_required"] == pytest.approx(0.0)
    assert assessment["current_level_duration_seconds"] == pytest.approx(0.0)
    events = assessment["events"]
    assert isinstance(events, list)
    assert len(events) == 2
    last_event = events[-1]
    assert last_event["timestamp"] == "2024-01-02T00:00:00+00:00"
    assert last_event["level"] == "watch"
    assert last_event["previous_level"] == "ok"
    assert last_event["status"] == "diverged"
    assert last_event["divergence_detected"] is True
    assert last_event["checks"] == 1
    assert last_event["level_changed"] is True
    assert history["assessment_events"] == events
    assert assessment["timeline_summary"]["total_events"] == 2
    assert assessment["timeline_summary"]["last_level"] == assessment["level"]


def test_update_runtime_store_health_records_first_event_when_suppressed(
    monkeypatch,
) -> None:
    """The first invocation should record even when suppression is requested."""

    runtime_data = _runtime_data()
    snapshot = _snapshot(status="needs_migration", entry_status="unstamped")
    monkeypatch.setattr(
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: datetime(2024, 2, 1, tzinfo=UTC),
    )

    history = update_runtime_store_health(runtime_data, snapshot, record_event=False)

    assert history is not None
    assert history["checks"] == 1
    assert history["status_counts"] == {"needs_migration": 1}
    assert history["last_status"] == "needs_migration"
    assert history["last_entry_status"] == "unstamped"
    assert get_runtime_store_health(runtime_data) is history
    timeline_summary = history.get("assessment_timeline_summary")
    assert timeline_summary is not None
    assert timeline_summary["total_events"] == 1
    assert timeline_summary["level_counts"]["action_required"] == 1
    assert timeline_summary["last_level"] == "action_required"
    assessment = history.get("assessment")
    assert assessment is not None
    assert assessment["level"] == "action_required"
    assert assessment["recommended_action"]
    assert assessment["level_streak"] == 1
    assert assessment["escalations"] == 0
    assert assessment["deescalations"] == 0
    durations = assessment["level_durations"]
    assert durations["action_required"] == pytest.approx(0.0)
    assert assessment["current_level_duration_seconds"] == pytest.approx(0.0)
    events = assessment["events"]
    assert isinstance(events, list)
    assert len(events) == 1
    event = events[0]
    assert event["timestamp"] == "2024-02-01T00:00:00+00:00"
    assert event["level"] == "action_required"
    assert event["status"] == "needs_migration"
    assert event["entry_status"] == "unstamped"
    assert event["level_changed"] is True
    assert history["assessment_events"] == events
    assert assessment["timeline_summary"]["last_status"] == "needs_migration"


def test_update_runtime_store_health_escalates_on_persistent_divergence(
    monkeypatch,
) -> None:
    """Repeated divergence should escalate the assessment severity."""

    runtime_data = _runtime_data()
    monkeypatch.setattr(
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: datetime(2024, 3, 1, tzinfo=UTC),
    )
    first_snapshot = _snapshot(status="diverged", divergence=True)
    update_runtime_store_health(runtime_data, first_snapshot)

    monkeypatch.setattr(
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: datetime(2024, 3, 2, tzinfo=UTC),
    )
    second_snapshot = _snapshot(status="diverged", divergence=True)
    history = update_runtime_store_health(runtime_data, second_snapshot)

    assert history is not None
    timeline_summary = history.get("assessment_timeline_summary")
    assert timeline_summary is not None
    assert timeline_summary["total_events"] == 2
    assert timeline_summary["level_counts"]["action_required"] >= 1
    assert timeline_summary["last_level"] == "action_required"
    assert timeline_summary["average_divergence_rate"] == pytest.approx(1.0)
    assert timeline_summary["max_divergence_rate"] == pytest.approx(1.0)
    assert timeline_summary["level_duration_peaks"]["action_required"] >= 0.0
    assert timeline_summary["last_level_duration_seconds"] >= 0.0
    assert timeline_summary["level_duration_latest"]["action_required"] >= 0.0
    assessment = history.get("assessment")
    assert assessment is not None
    assert assessment["level"] == "action_required"
    assert assessment["divergence_events"] == 2
    assert assessment["last_level_change"]
    previous_level = assessment.get("previous_level")
    assert previous_level in {"watch", "action_required", None}
    if previous_level == "watch":
        assert assessment["level_streak"] == 1
        assert assessment["escalations"] >= 1
    else:
        assert assessment["level_streak"] >= 2
        assert assessment["escalations"] >= 0
    durations = assessment["level_durations"]
    assert durations["action_required"] == pytest.approx(86400.0)
    assert assessment["current_level_duration_seconds"] == pytest.approx(86400.0)
    events = assessment["events"]
    assert isinstance(events, list)
    assert len(events) >= 2
    latest_event = events[-1]
    assert latest_event["level"] == "action_required"
    assert latest_event["status"] == "diverged"
    assert latest_event["divergence_events"] == 2
    assert latest_event["divergence_detected"] is True
    assert latest_event["level_changed"] in {True, False}
    history_events = history.get("assessment_events")
    assert isinstance(history_events, list)
    assert history_events[-1] == latest_event


def test_runtime_store_assessment_tracks_trends(monkeypatch) -> None:
    """Trend counters should track level changes and streaks."""

    runtime_data = _runtime_data()
    moments = iter(
        (
            datetime(2024, 4, 1, tzinfo=UTC),
            datetime(2024, 4, 2, tzinfo=UTC),
            datetime(2024, 4, 3, tzinfo=UTC),
            datetime(2024, 4, 4, tzinfo=UTC),
        )
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: next(moments),
    )

    first = update_runtime_store_health(runtime_data, _snapshot())
    first_assessment = first["assessment"]
    assert first_assessment["level"] == "ok"
    assert first_assessment["level_streak"] == 1
    assert first_assessment["escalations"] == 0
    assert first_assessment["deescalations"] == 0
    assert first_assessment["last_level_change"] == "2024-04-01T00:00:00+00:00"
    assert first_assessment["current_level_duration_seconds"] == pytest.approx(0.0)
    first_durations = first_assessment["level_durations"]
    assert first_durations["ok"] == pytest.approx(0.0)
    assert first_durations["watch"] == pytest.approx(0.0)
    assert first_durations["action_required"] == pytest.approx(0.0)
    assert first_assessment["events"][0]["level"] == "ok"

    second = update_runtime_store_health(
        runtime_data,
        _snapshot(status="diverged", divergence=False),
        record_event=False,
    )
    second_assessment = second["assessment"]
    assert second_assessment["level"] == "watch"
    assert second_assessment["previous_level"] == "ok"
    assert second_assessment["level_streak"] == 1
    assert second_assessment["escalations"] == 1
    assert second_assessment["deescalations"] == 0
    assert second_assessment["last_level_change"] == "2024-04-02T00:00:00+00:00"
    assert second_assessment["current_level_duration_seconds"] == pytest.approx(0.0)
    second_durations = second_assessment["level_durations"]
    assert second_durations["ok"] == pytest.approx(86400.0)
    assert second_durations["watch"] == pytest.approx(0.0)
    assert second_durations["action_required"] == pytest.approx(0.0)
    assert second_assessment["events"][-1]["level"] == "watch"

    third = update_runtime_store_health(
        runtime_data, _snapshot(status="diverged", divergence=True)
    )
    third_assessment = third["assessment"]
    assert third_assessment["level"] == "action_required"
    assert third_assessment["previous_level"] == "watch"
    assert third_assessment["level_streak"] == 1
    assert third_assessment["escalations"] == 2
    assert third_assessment["deescalations"] == 0
    assert third_assessment["last_level_change"] == "2024-04-03T00:00:00+00:00"
    assert third_assessment["current_level_duration_seconds"] == pytest.approx(0.0)
    third_durations = third_assessment["level_durations"]
    assert third_durations["ok"] == pytest.approx(86400.0)
    assert third_durations["watch"] == pytest.approx(86400.0)
    assert third_durations["action_required"] == pytest.approx(0.0)
    assert third_assessment["events"][-1]["level"] == "action_required"

    fourth = update_runtime_store_health(runtime_data, _snapshot())
    fourth_assessment = fourth["assessment"]
    assert fourth_assessment["level"] in {"ok", "watch"}
    assert fourth_assessment["previous_level"] == "action_required"
    assert fourth_assessment["level_streak"] == 1
    assert fourth_assessment["escalations"] == 2
    assert fourth_assessment["deescalations"] == 1
    assert fourth_assessment["last_level_change"] == "2024-04-04T00:00:00+00:00"
    fourth_durations = fourth_assessment["level_durations"]
    assert fourth_durations["ok"] == pytest.approx(86400.0)
    assert fourth_durations["watch"] == pytest.approx(86400.0)
    assert fourth_durations["action_required"] == pytest.approx(86400.0)
    assert fourth_assessment["current_level_duration_seconds"] == pytest.approx(0.0)
    events = fourth_assessment["events"]
    assert len(events) >= 4
    assert events[-1]["status"] == "current"


def test_runtime_store_assessment_event_log_capped(monkeypatch) -> None:
    """The assessment event timeline should retain only the configured window."""

    runtime_data = _runtime_data()
    limit = telemetry_module._RUNTIME_STORE_ASSESSMENT_EVENT_LIMIT
    base = datetime(2024, 5, 1, tzinfo=UTC)
    moments = (base + timedelta(days=index) for index in range(limit + 5))

    monkeypatch.setattr(
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: next(moments),
    )

    history = None
    for step in range(limit + 5):
        status = "diverged" if step % 2 else "current"
        history = update_runtime_store_health(
            runtime_data,
            _snapshot(status=status, divergence=status == "diverged"),
        )

    assert history is not None
    events = history.get("assessment_events")
    assert isinstance(events, list)
    assert len(events) == limit
    assert events[0]["timestamp"] == (base + timedelta(days=5)).isoformat()
    assert events[-1]["timestamp"] == (base + timedelta(days=limit + 4)).isoformat()
