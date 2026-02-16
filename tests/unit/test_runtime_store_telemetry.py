"""Unit tests for runtime store telemetry helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from pytest import MonkeyPatch

from custom_components.pawcontrol import telemetry as telemetry_module
from custom_components.pawcontrol.telemetry import (
  get_runtime_store_health,
  update_runtime_store_health,
)
from custom_components.pawcontrol.types import (
  RuntimeStoreAssessmentEvent,
  RuntimeStoreCompatibilitySnapshot,
  RuntimeStoreHealthAssessment,
  RuntimeStoreHealthHistory,
)


def _runtime_data() -> SimpleNamespace:
  """Return a minimal runtime data container for telemetry tests."""  # noqa: E111

  return SimpleNamespace(performance_stats={})  # noqa: E111


def _snapshot(
  *,
  status: str = "current",
  entry_status: str = "current",
  store_status: str = "current",
  divergence: bool = False,
) -> RuntimeStoreCompatibilitySnapshot:
  """Build a runtime store compatibility snapshot for testing."""  # noqa: E111

  return {  # noqa: E111
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


def test_update_runtime_store_health_records_counts(monkeypatch: MonkeyPatch) -> None:
  """Recording telemetry should update counts and metadata."""  # noqa: E111

  runtime_data = _runtime_data()  # noqa: E111
  snapshot = _snapshot()  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: datetime(2024, 1, 1, tzinfo=UTC),
  )

  history = update_runtime_store_health(runtime_data, snapshot)  # noqa: E111

  assert history is not None  # noqa: E111
  history = cast(RuntimeStoreHealthHistory, history)  # noqa: E111
  assert history["schema_version"] == 1  # noqa: E111
  assert history["checks"] == 1  # noqa: E111
  assert history["status_counts"] == {"current": 1}  # noqa: E111
  assert history["divergence_events"] == 0  # noqa: E111
  assert history["last_status"] == "current"  # noqa: E111
  assert history["last_entry_status"] == "current"  # noqa: E111
  assert history["last_store_status"] == "current"  # noqa: E111
  assert history["last_checked"] == "2024-01-01T00:00:00+00:00"  # noqa: E111
  timeline_summary = history.get("assessment_timeline_summary")  # noqa: E111
  assert timeline_summary is not None  # noqa: E111
  assert timeline_summary["total_events"] == 1  # noqa: E111
  assert timeline_summary["level_changes"] == 1  # noqa: E111
  assert timeline_summary["level_counts"]["ok"] == 1  # noqa: E111
  assert timeline_summary["status_counts"]["current"] == 1  # noqa: E111
  assert timeline_summary["distinct_reasons"] == 1  # noqa: E111
  assert timeline_summary["first_event_timestamp"] == "2024-01-01T00:00:00+00:00"  # noqa: E111
  assert timeline_summary["last_event_timestamp"] == "2024-01-01T00:00:00+00:00"  # noqa: E111
  assert timeline_summary["last_level"] == "ok"  # noqa: E111
  assert timeline_summary["last_status"] == "current"  # noqa: E111
  assert timeline_summary["level_change_rate"] == pytest.approx(1.0)  # noqa: E111
  assert timeline_summary["timeline_window_seconds"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["timeline_window_days"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["events_per_day"] == pytest.approx(1.0)  # noqa: E111
  assert (  # noqa: E111
    timeline_summary["most_common_reason"]
    == "Runtime store metadata matches the active schema."
  )
  assert timeline_summary["most_common_level"] == "ok"  # noqa: E111
  assert timeline_summary["most_common_status"] == "current"  # noqa: E111
  assert timeline_summary["average_divergence_rate"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["max_divergence_rate"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["last_level_duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_peaks"]["ok"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_peaks"]["watch"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_peaks"]["action_required"] == pytest.approx(  # noqa: E111
    0.0
  )
  assert timeline_summary["level_duration_latest"]["ok"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_latest"]["watch"] is None  # noqa: E111
  assert timeline_summary["level_duration_latest"]["action_required"] is None  # noqa: E111
  assert timeline_summary["level_duration_totals"]["ok"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_totals"]["watch"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_totals"]["action_required"] == pytest.approx(  # noqa: E111
    0.0
  )
  assert timeline_summary["level_duration_minimums"]["ok"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_minimums"]["watch"] is None  # noqa: E111
  assert timeline_summary["level_duration_minimums"]["action_required"] is None  # noqa: E111
  assert timeline_summary["level_duration_samples"]["ok"] == 1  # noqa: E111
  assert timeline_summary["level_duration_samples"]["watch"] == 0  # noqa: E111
  assert timeline_summary["level_duration_samples"]["action_required"] == 0  # noqa: E111
  assert timeline_summary["level_duration_averages"]["ok"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_averages"]["watch"] is None  # noqa: E111
  assert timeline_summary["level_duration_averages"]["action_required"] is None  # noqa: E111
  assert timeline_summary["level_duration_medians"]["ok"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_medians"]["watch"] is None  # noqa: E111
  assert timeline_summary["level_duration_medians"]["action_required"] is None  # noqa: E111
  assert timeline_summary["level_duration_standard_deviations"]["ok"] == pytest.approx(  # noqa: E111
    0.0
  )
  assert timeline_summary["level_duration_standard_deviations"]["watch"] is None  # noqa: E111
  assert (  # noqa: E111
    timeline_summary["level_duration_standard_deviations"]["action_required"] is None
  )
  ok_percentiles = timeline_summary["level_duration_percentiles"]["ok"]  # noqa: E111
  assert ok_percentiles["p75"] == pytest.approx(0.0)  # noqa: E111
  assert ok_percentiles["p90"] == pytest.approx(0.0)  # noqa: E111
  assert ok_percentiles["p95"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_percentiles"]["watch"] == {}  # noqa: E111
  assert timeline_summary["level_duration_percentiles"]["action_required"] == {}  # noqa: E111
  assert timeline_summary["level_duration_alert_thresholds"]["ok"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_alert_thresholds"]["watch"] is None  # noqa: E111
  assert timeline_summary["level_duration_alert_thresholds"]["action_required"] is None  # noqa: E111
  assert timeline_summary["level_duration_guard_alerts"] == []  # noqa: E111
  assessment = history.get("assessment")  # noqa: E111
  assert isinstance(assessment, dict)  # noqa: E111
  assessment = cast(RuntimeStoreHealthAssessment, assessment)  # noqa: E111
  assert assessment["level"] == "ok"  # noqa: E111
  assert assessment["previous_level"] is None  # noqa: E111
  assert assessment["divergence_events"] == 0  # noqa: E111
  assert assessment["recommended_action"] is None  # noqa: E111
  assert assessment["level_streak"] == 1  # noqa: E111
  assert assessment["last_level_change"] == "2024-01-01T00:00:00+00:00"  # noqa: E111
  assert assessment["escalations"] == 0  # noqa: E111
  assert assessment["deescalations"] == 0  # noqa: E111
  assert assessment["current_level_duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  durations = assessment["level_durations"]  # noqa: E111
  assert durations["ok"] == pytest.approx(0.0)  # noqa: E111
  assert durations["watch"] == pytest.approx(0.0)  # noqa: E111
  assert durations["action_required"] == pytest.approx(0.0)  # noqa: E111
  segments = history.get("assessment_timeline_segments")  # noqa: E111
  assert isinstance(segments, list)  # noqa: E111
  assert len(segments) == 1  # noqa: E111
  first_segment = segments[0]  # noqa: E111
  assert first_segment["start"] == "2024-01-01T00:00:00+00:00"  # noqa: E111
  assert first_segment.get("end") is None  # noqa: E111
  assert first_segment["level"] == "ok"  # noqa: E111
  assert first_segment["status"] == "current"  # noqa: E111
  assert first_segment["duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  assert assessment["timeline_segments"] == segments  # noqa: E111
  events = assessment["events"]  # noqa: E111
  assert isinstance(events, list)  # noqa: E111
  assert len(events) == 1  # noqa: E111
  first_event = events[0]  # noqa: E111
  assert first_event["timestamp"] == "2024-01-01T00:00:00+00:00"  # noqa: E111
  assert first_event["level"] == "ok"  # noqa: E111
  assert first_event["status"] == "current"  # noqa: E111
  assert first_event["entry_status"] == "current"  # noqa: E111
  assert first_event["store_status"] == "current"  # noqa: E111
  assert first_event["level_changed"] is True  # noqa: E111
  assert first_event["divergence_detected"] is False  # noqa: E111
  assert first_event["checks"] == 1  # noqa: E111
  assert history["assessment_events"] == events  # noqa: E111
  assert assessment["timeline_summary"]["total_events"] == 1  # noqa: E111
  assert (  # noqa: E111
    assessment["timeline_summary"]["last_event_timestamp"]
    == "2024-01-01T00:00:00+00:00"
  )


def test_update_runtime_store_health_does_not_increment_when_suppressed(
  monkeypatch: MonkeyPatch,
) -> None:
  """Suppressing recording should still refresh last status without new counts."""  # noqa: E111

  runtime_data = _runtime_data()  # noqa: E111
  first_snapshot = _snapshot(status="current")  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: datetime(2024, 1, 1, tzinfo=UTC),
  )
  update_runtime_store_health(runtime_data, first_snapshot)  # noqa: E111

  second_snapshot = _snapshot(status="diverged", divergence=True)  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: datetime(2024, 1, 2, tzinfo=UTC),
  )
  history = update_runtime_store_health(  # noqa: E111
    runtime_data, second_snapshot, record_event=False
  )

  assert history is not None  # noqa: E111
  history = cast(RuntimeStoreHealthHistory, history)  # noqa: E111
  assert history["checks"] == 1  # noqa: E111
  # Status counts should not increment when recording is suppressed.  # noqa: E114
  assert history["status_counts"] == {"current": 1}  # noqa: E111
  assert history["last_status"] == "diverged"  # noqa: E111
  assert history["divergence_detected"] is True  # noqa: E111
  assert history["last_checked"] == "2024-01-02T00:00:00+00:00"  # noqa: E111
  timeline_summary = history.get("assessment_timeline_summary")  # noqa: E111
  assert timeline_summary is not None  # noqa: E111
  assert timeline_summary["total_events"] == 2  # noqa: E111
  assert timeline_summary["level_changes"] == 2  # noqa: E111
  assert timeline_summary["level_counts"]["ok"] == 1  # noqa: E111
  assert timeline_summary["level_counts"]["watch"] == 1  # noqa: E111
  assert timeline_summary["status_counts"]["diverged"] == 1  # noqa: E111
  assert timeline_summary["last_event_timestamp"] == "2024-01-02T00:00:00+00:00"  # noqa: E111
  assert timeline_summary["last_level"] == "watch"  # noqa: E111
  assert timeline_summary["last_status"] == "diverged"  # noqa: E111
  assert timeline_summary["timeline_window_seconds"] == pytest.approx(86400.0)  # noqa: E111
  assert timeline_summary["timeline_window_days"] == pytest.approx(1.0)  # noqa: E111
  assert timeline_summary["events_per_day"] == pytest.approx(2.0)  # noqa: E111
  assert timeline_summary["most_common_reason"] is not None  # noqa: E111
  assert timeline_summary["most_common_level"] == "ok"  # noqa: E111
  assert timeline_summary["most_common_status"] == "current"  # noqa: E111
  assert timeline_summary["average_divergence_rate"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["max_divergence_rate"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_peaks"]["ok"] >= 0.0  # noqa: E111
  assert timeline_summary["level_duration_peaks"]["watch"] >= 0.0  # noqa: E111
  assert timeline_summary["last_level_duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_latest"]["watch"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_totals"]["ok"] >= 0.0  # noqa: E111
  assert timeline_summary["level_duration_totals"]["watch"] >= 0.0  # noqa: E111
  assert (  # noqa: E111
    timeline_summary["level_duration_minimums"]["ok"] is None
    or timeline_summary["level_duration_minimums"]["ok"] >= 0.0
  )
  assert (  # noqa: E111
    timeline_summary["level_duration_minimums"]["watch"] is None
    or timeline_summary["level_duration_minimums"]["watch"] >= 0.0
  )
  assert timeline_summary["level_duration_samples"]["ok"] == 1  # noqa: E111
  assert timeline_summary["level_duration_samples"]["watch"] == 1  # noqa: E111
  assert timeline_summary["level_duration_samples"]["action_required"] == 0  # noqa: E111
  assert (  # noqa: E111
    timeline_summary["level_duration_averages"]["ok"] is None
    or timeline_summary["level_duration_averages"]["ok"] >= 0.0
  )
  assert (  # noqa: E111
    timeline_summary["level_duration_averages"]["watch"] is None
    or timeline_summary["level_duration_averages"]["watch"] >= 0.0
  )
  assert (  # noqa: E111
    timeline_summary["level_duration_medians"]["ok"] is None
    or timeline_summary["level_duration_medians"]["ok"] >= 0.0
  )
  assert (  # noqa: E111
    timeline_summary["level_duration_medians"]["watch"] is None
    or timeline_summary["level_duration_medians"]["watch"] >= 0.0
  )
  assert (  # noqa: E111
    timeline_summary["level_duration_standard_deviations"]["ok"] is None
    or timeline_summary["level_duration_standard_deviations"]["ok"] >= 0.0
  )
  assert (  # noqa: E111
    timeline_summary["level_duration_standard_deviations"]["watch"] is None
    or timeline_summary["level_duration_standard_deviations"]["watch"] >= 0.0
  )
  assessment = history.get("assessment")  # noqa: E111
  assert isinstance(assessment, dict)  # noqa: E111
  assessment = cast(RuntimeStoreHealthAssessment, assessment)  # noqa: E111
  assert assessment["level"] == "watch"  # noqa: E111
  assert assessment["divergence_detected"] is True  # noqa: E111
  assert assessment["previous_level"] == "ok"  # noqa: E111
  assert assessment["level_streak"] == 1  # noqa: E111
  assert assessment["last_level_change"] == "2024-01-02T00:00:00+00:00"  # noqa: E111
  assert assessment["escalations"] == 1  # noqa: E111
  assert assessment["deescalations"] == 0  # noqa: E111
  durations = assessment["level_durations"]  # noqa: E111
  assert durations["ok"] == pytest.approx(86400.0)  # noqa: E111
  assert durations["watch"] == pytest.approx(0.0)  # noqa: E111
  assert durations["action_required"] == pytest.approx(0.0)  # noqa: E111
  assert assessment["current_level_duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  segments = history.get("assessment_timeline_segments")  # noqa: E111
  assert isinstance(segments, list)  # noqa: E111
  assert len(segments) == 2  # noqa: E111
  first_segment = segments[0]  # noqa: E111
  assert first_segment["start"] == "2024-01-01T00:00:00+00:00"  # noqa: E111
  assert first_segment["end"] == "2024-01-02T00:00:00+00:00"  # noqa: E111
  assert first_segment["duration_seconds"] == pytest.approx(86400.0)  # noqa: E111
  second_segment = segments[1]  # noqa: E111
  assert second_segment["start"] == "2024-01-02T00:00:00+00:00"  # noqa: E111
  assert second_segment.get("end") is None  # noqa: E111
  assert second_segment["duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  assert assessment["timeline_segments"] == segments  # noqa: E111
  events = assessment["events"]  # noqa: E111
  assert isinstance(events, list)  # noqa: E111
  assert len(events) == 2  # noqa: E111
  last_event = events[-1]  # noqa: E111
  assert last_event["timestamp"] == "2024-01-02T00:00:00+00:00"  # noqa: E111
  assert last_event["level"] == "watch"  # noqa: E111
  assert last_event["previous_level"] == "ok"  # noqa: E111
  assert last_event["status"] == "diverged"  # noqa: E111
  assert last_event["divergence_detected"] is True  # noqa: E111
  assert last_event["checks"] == 1  # noqa: E111
  assert last_event["level_changed"] is True  # noqa: E111
  assert history["assessment_events"] == events  # noqa: E111
  assert assessment["timeline_summary"]["total_events"] == 2  # noqa: E111
  assert assessment["timeline_summary"]["last_level"] == assessment["level"]  # noqa: E111


def test_update_runtime_store_health_records_first_event_when_suppressed(
  monkeypatch: MonkeyPatch,
) -> None:
  """The first invocation should record even when suppression is requested."""  # noqa: E111

  runtime_data = _runtime_data()  # noqa: E111
  snapshot = _snapshot(status="needs_migration", entry_status="unstamped")  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: datetime(2024, 2, 1, tzinfo=UTC),
  )

  history = update_runtime_store_health(runtime_data, snapshot, record_event=False)  # noqa: E111

  assert history is not None  # noqa: E111
  history = cast(RuntimeStoreHealthHistory, history)  # noqa: E111
  assert history["checks"] == 1  # noqa: E111
  assert history["status_counts"] == {"needs_migration": 1}  # noqa: E111
  assert history["last_status"] == "needs_migration"  # noqa: E111
  assert history["last_entry_status"] == "unstamped"  # noqa: E111
  assert get_runtime_store_health(runtime_data) is history  # noqa: E111
  timeline_summary = history.get("assessment_timeline_summary")  # noqa: E111
  assert timeline_summary is not None  # noqa: E111
  assert timeline_summary["total_events"] == 1  # noqa: E111
  assert timeline_summary["level_counts"]["action_required"] == 1  # noqa: E111
  assert timeline_summary["last_level"] == "action_required"  # noqa: E111
  assert timeline_summary["level_duration_totals"]["action_required"] == pytest.approx(  # noqa: E111
    0.0
  )
  assert timeline_summary["level_duration_minimums"][  # noqa: E111
    "action_required"
  ] == pytest.approx(0.0)
  assert timeline_summary["level_duration_minimums"]["ok"] is None  # noqa: E111
  assert timeline_summary["level_duration_minimums"]["watch"] is None  # noqa: E111
  assert timeline_summary["level_duration_samples"]["action_required"] == 1  # noqa: E111
  assert timeline_summary["level_duration_samples"]["ok"] == 0  # noqa: E111
  assert timeline_summary["level_duration_samples"]["watch"] == 0  # noqa: E111
  assert timeline_summary["level_duration_averages"][  # noqa: E111
    "action_required"
  ] == pytest.approx(0.0)
  assert timeline_summary["level_duration_medians"]["action_required"] == pytest.approx(  # noqa: E111
    0.0
  )
  assert timeline_summary["level_duration_medians"]["ok"] is None  # noqa: E111
  assert timeline_summary["level_duration_medians"]["watch"] is None  # noqa: E111
  assert timeline_summary["level_duration_standard_deviations"][  # noqa: E111
    "action_required"
  ] == pytest.approx(0.0)
  assert timeline_summary["level_duration_standard_deviations"]["ok"] is None  # noqa: E111
  assert timeline_summary["level_duration_standard_deviations"]["watch"] is None  # noqa: E111
  percentiles = timeline_summary["level_duration_percentiles"]["action_required"]  # noqa: E111
  assert percentiles["p75"] == pytest.approx(0.0)  # noqa: E111
  assert percentiles["p90"] == pytest.approx(0.0)  # noqa: E111
  assert percentiles["p95"] == pytest.approx(0.0)  # noqa: E111
  assert timeline_summary["level_duration_percentiles"]["ok"] == {}  # noqa: E111
  assert timeline_summary["level_duration_percentiles"]["watch"] == {}  # noqa: E111
  assert timeline_summary["level_duration_alert_thresholds"][  # noqa: E111
    "action_required"
  ] == pytest.approx(0.0)
  assert timeline_summary["level_duration_alert_thresholds"]["ok"] is None  # noqa: E111
  assert timeline_summary["level_duration_alert_thresholds"]["watch"] is None  # noqa: E111
  assessment = history.get("assessment")  # noqa: E111
  assert isinstance(assessment, dict)  # noqa: E111
  assessment = cast(RuntimeStoreHealthAssessment, assessment)  # noqa: E111
  assert assessment["level"] == "action_required"  # noqa: E111
  assert assessment["recommended_action"]  # noqa: E111
  assert assessment["level_streak"] == 1  # noqa: E111
  assert assessment["escalations"] == 0  # noqa: E111
  assert assessment["deescalations"] == 0  # noqa: E111
  durations = assessment["level_durations"]  # noqa: E111
  assert durations["action_required"] == pytest.approx(0.0)  # noqa: E111
  assert assessment["current_level_duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  segments = history.get("assessment_timeline_segments")  # noqa: E111
  assert isinstance(segments, list)  # noqa: E111
  assert len(segments) == 1  # noqa: E111
  segment = segments[0]  # noqa: E111
  assert segment["level"] == "action_required"  # noqa: E111
  assert segment["status"] == "needs_migration"  # noqa: E111
  assert segment.get("end") is None  # noqa: E111
  assert segment["duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  assert assessment["timeline_segments"] == segments  # noqa: E111
  events = assessment["events"]  # noqa: E111
  assert isinstance(events, list)  # noqa: E111
  assert len(events) == 1  # noqa: E111
  event = events[0]  # noqa: E111
  assert event["timestamp"] == "2024-02-01T00:00:00+00:00"  # noqa: E111
  assert event["level"] == "action_required"  # noqa: E111
  assert event["status"] == "needs_migration"  # noqa: E111
  assert event["entry_status"] == "unstamped"  # noqa: E111
  assert event["level_changed"] is True  # noqa: E111
  assert history["assessment_events"] == events  # noqa: E111
  assert assessment["timeline_summary"]["last_status"] == "needs_migration"  # noqa: E111


def test_update_runtime_store_health_escalates_on_persistent_divergence(
  monkeypatch: MonkeyPatch,
) -> None:
  """Repeated divergence should escalate the assessment severity."""  # noqa: E111

  runtime_data = _runtime_data()  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: datetime(2024, 3, 1, tzinfo=UTC),
  )
  first_snapshot = _snapshot(status="diverged", divergence=True)  # noqa: E111
  update_runtime_store_health(runtime_data, first_snapshot)  # noqa: E111

  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: datetime(2024, 3, 2, tzinfo=UTC),
  )
  second_snapshot = _snapshot(status="diverged", divergence=True)  # noqa: E111
  history = update_runtime_store_health(runtime_data, second_snapshot)  # noqa: E111

  assert history is not None  # noqa: E111
  history = cast(RuntimeStoreHealthHistory, history)  # noqa: E111
  timeline_summary = history.get("assessment_timeline_summary")  # noqa: E111
  assert timeline_summary is not None  # noqa: E111
  assert timeline_summary["total_events"] == 2  # noqa: E111
  assert timeline_summary["level_counts"]["action_required"] >= 1  # noqa: E111
  assert timeline_summary["last_level"] == "action_required"  # noqa: E111
  assert timeline_summary["average_divergence_rate"] == pytest.approx(1.0)  # noqa: E111
  assert timeline_summary["max_divergence_rate"] == pytest.approx(1.0)  # noqa: E111
  assert timeline_summary["level_duration_peaks"]["action_required"] >= 0.0  # noqa: E111
  assert timeline_summary["last_level_duration_seconds"] >= 0.0  # noqa: E111
  assert timeline_summary["level_duration_latest"]["action_required"] >= 0.0  # noqa: E111
  assert timeline_summary["level_duration_totals"]["action_required"] >= 0.0  # noqa: E111
  assert (  # noqa: E111
    timeline_summary["level_duration_minimums"]["action_required"] is None
    or timeline_summary["level_duration_minimums"]["action_required"] >= 0.0
  )
  assert timeline_summary["level_duration_samples"]["action_required"] >= 1  # noqa: E111
  assert (  # noqa: E111
    timeline_summary["level_duration_averages"]["action_required"] is None
    or timeline_summary["level_duration_averages"]["action_required"] >= 0.0
  )
  assert (  # noqa: E111
    timeline_summary["level_duration_medians"]["action_required"] is None
    or timeline_summary["level_duration_medians"]["action_required"] >= 0.0
  )
  assert (  # noqa: E111
    timeline_summary["level_duration_standard_deviations"]["action_required"] is None
    or timeline_summary["level_duration_standard_deviations"]["action_required"] >= 0.0
  )
  assessment = history.get("assessment")  # noqa: E111
  assert isinstance(assessment, dict)  # noqa: E111
  assessment = cast(RuntimeStoreHealthAssessment, assessment)  # noqa: E111
  assert assessment["level"] == "action_required"  # noqa: E111
  assert assessment["divergence_events"] == 2  # noqa: E111
  assert assessment["last_level_change"]  # noqa: E111
  previous_level = assessment.get("previous_level")  # noqa: E111
  assert previous_level in {"watch", "action_required", None}  # noqa: E111
  if previous_level == "watch":  # noqa: E111
    assert assessment["level_streak"] == 1
    assert assessment["escalations"] >= 1
  else:  # noqa: E111
    assert assessment["level_streak"] >= 2
    assert assessment["escalations"] >= 0
  durations = assessment["level_durations"]  # noqa: E111
  assert durations["action_required"] == pytest.approx(86400.0)  # noqa: E111
  assert assessment["current_level_duration_seconds"] == pytest.approx(86400.0)  # noqa: E111
  events = assessment["events"]  # noqa: E111
  assert isinstance(events, list)  # noqa: E111
  assert len(events) >= 2  # noqa: E111
  latest_event = events[-1]  # noqa: E111
  assert latest_event["level"] == "action_required"  # noqa: E111
  assert latest_event["status"] == "diverged"  # noqa: E111
  assert latest_event["divergence_events"] == 2  # noqa: E111
  assert latest_event["divergence_detected"] is True  # noqa: E111
  assert latest_event["level_changed"] in {True, False}  # noqa: E111
  history_events = history.get("assessment_events")  # noqa: E111
  assert isinstance(history_events, list)  # noqa: E111
  assert history_events[-1] == latest_event  # noqa: E111
  segments = history.get("assessment_timeline_segments")  # noqa: E111
  assert isinstance(segments, list)  # noqa: E111
  assert segments[-1]["level"] == "action_required"  # noqa: E111
  assert assessment["timeline_segments"] == segments  # noqa: E111


def test_runtime_store_assessment_tracks_trends(monkeypatch: MonkeyPatch) -> None:
  """Trend counters should track level changes and streaks."""  # noqa: E111

  runtime_data = _runtime_data()  # noqa: E111
  moments = iter((  # noqa: E111
    datetime(2024, 4, 1, tzinfo=UTC),
    datetime(2024, 4, 2, tzinfo=UTC),
    datetime(2024, 4, 3, tzinfo=UTC),
    datetime(2024, 4, 4, tzinfo=UTC),
  ))
  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: next(moments),
  )

  first = update_runtime_store_health(runtime_data, _snapshot())  # noqa: E111
  assert first is not None  # noqa: E111
  first_history = cast(RuntimeStoreHealthHistory, first)  # noqa: E111
  first_assessment = cast(RuntimeStoreHealthAssessment, first_history["assessment"])  # noqa: E111
  assert first_assessment["level"] == "ok"  # noqa: E111
  assert first_assessment["level_streak"] == 1  # noqa: E111
  assert first_assessment["escalations"] == 0  # noqa: E111
  assert first_assessment["deescalations"] == 0  # noqa: E111
  assert first_assessment["last_level_change"] == "2024-04-01T00:00:00+00:00"  # noqa: E111
  assert first_assessment["current_level_duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  first_durations = first_assessment["level_durations"]  # noqa: E111
  assert first_durations["ok"] == pytest.approx(0.0)  # noqa: E111
  assert first_durations["watch"] == pytest.approx(0.0)  # noqa: E111
  assert first_durations["action_required"] == pytest.approx(0.0)  # noqa: E111
  assert first_assessment["events"][0]["level"] == "ok"  # noqa: E111

  second = update_runtime_store_health(  # noqa: E111
    runtime_data,
    _snapshot(status="diverged", divergence=False),
    record_event=False,
  )
  assert second is not None  # noqa: E111
  second_history = cast(RuntimeStoreHealthHistory, second)  # noqa: E111
  second_assessment = cast(RuntimeStoreHealthAssessment, second_history["assessment"])  # noqa: E111
  assert second_assessment["level"] == "watch"  # noqa: E111
  assert second_assessment["previous_level"] == "ok"  # noqa: E111
  assert second_assessment["level_streak"] == 1  # noqa: E111
  assert second_assessment["escalations"] == 1  # noqa: E111
  assert second_assessment["deescalations"] == 0  # noqa: E111
  assert second_assessment["last_level_change"] == "2024-04-02T00:00:00+00:00"  # noqa: E111
  assert second_assessment["current_level_duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  second_durations = second_assessment["level_durations"]  # noqa: E111
  assert second_durations["ok"] == pytest.approx(86400.0)  # noqa: E111
  assert second_durations["watch"] == pytest.approx(0.0)  # noqa: E111
  assert second_durations["action_required"] == pytest.approx(0.0)  # noqa: E111
  assert second_assessment["events"][-1]["level"] == "watch"  # noqa: E111

  third = update_runtime_store_health(  # noqa: E111
    runtime_data, _snapshot(status="diverged", divergence=True)
  )
  assert third is not None  # noqa: E111
  third_history = cast(RuntimeStoreHealthHistory, third)  # noqa: E111
  third_assessment = cast(RuntimeStoreHealthAssessment, third_history["assessment"])  # noqa: E111
  assert third_assessment["level"] == "action_required"  # noqa: E111
  assert third_assessment["previous_level"] == "watch"  # noqa: E111
  assert third_assessment["level_streak"] == 1  # noqa: E111
  assert third_assessment["escalations"] == 2  # noqa: E111
  assert third_assessment["deescalations"] == 0  # noqa: E111
  assert third_assessment["last_level_change"] == "2024-04-03T00:00:00+00:00"  # noqa: E111
  assert third_assessment["current_level_duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  third_durations = third_assessment["level_durations"]  # noqa: E111
  assert third_durations["ok"] == pytest.approx(86400.0)  # noqa: E111
  assert third_durations["watch"] == pytest.approx(86400.0)  # noqa: E111
  assert third_durations["action_required"] == pytest.approx(0.0)  # noqa: E111
  assert third_assessment["events"][-1]["level"] == "action_required"  # noqa: E111

  fourth = update_runtime_store_health(runtime_data, _snapshot())  # noqa: E111
  assert fourth is not None  # noqa: E111
  fourth_history = cast(RuntimeStoreHealthHistory, fourth)  # noqa: E111
  fourth_assessment = cast(RuntimeStoreHealthAssessment, fourth_history["assessment"])  # noqa: E111
  assert fourth_assessment["level"] in {"ok", "watch"}  # noqa: E111
  assert fourth_assessment["previous_level"] == "action_required"  # noqa: E111
  assert fourth_assessment["level_streak"] == 1  # noqa: E111
  assert fourth_assessment["escalations"] == 2  # noqa: E111
  assert fourth_assessment["deescalations"] == 1  # noqa: E111
  assert fourth_assessment["last_level_change"] == "2024-04-04T00:00:00+00:00"  # noqa: E111
  fourth_durations = fourth_assessment["level_durations"]  # noqa: E111
  assert fourth_durations["ok"] == pytest.approx(86400.0)  # noqa: E111
  assert fourth_durations["watch"] == pytest.approx(86400.0)  # noqa: E111
  assert fourth_durations["action_required"] == pytest.approx(86400.0)  # noqa: E111
  assert fourth_assessment["current_level_duration_seconds"] == pytest.approx(0.0)  # noqa: E111
  events = fourth_assessment.get("events")  # noqa: E111
  assert isinstance(events, list)  # noqa: E111
  assert len(events) >= 4  # noqa: E111
  assert events[-1]["status"] == "current"  # noqa: E111
  segments = fourth_history.get("assessment_timeline_segments")  # noqa: E111
  assert isinstance(segments, list)  # noqa: E111
  assert len(segments) >= 4  # noqa: E111
  assert fourth_assessment["timeline_segments"] == segments  # noqa: E111


def test_runtime_store_assessment_event_log_capped(monkeypatch: MonkeyPatch) -> None:
  """The assessment event timeline should retain only the configured window."""  # noqa: E111

  runtime_data = _runtime_data()  # noqa: E111
  limit = telemetry_module._RUNTIME_STORE_ASSESSMENT_EVENT_LIMIT  # noqa: E111
  base = datetime(2024, 5, 1, tzinfo=UTC)  # noqa: E111
  moments = (base + timedelta(days=index) for index in range(limit + 5))  # noqa: E111

  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: next(moments),
  )

  history: RuntimeStoreHealthHistory | None = None  # noqa: E111
  for step in range(limit + 5):  # noqa: E111
    status = "diverged" if step % 2 else "current"
    history = update_runtime_store_health(
      runtime_data,
      _snapshot(status=status, divergence=status == "diverged"),
    )

  assert history is not None  # noqa: E111
  history = cast(RuntimeStoreHealthHistory, history)  # noqa: E111
  events = history.get("assessment_events")  # noqa: E111
  assert isinstance(events, list)  # noqa: E111
  assert len(events) == limit  # noqa: E111
  assert events[0]["timestamp"] == (base + timedelta(days=5)).isoformat()  # noqa: E111
  assert events[-1]["timestamp"] == (base + timedelta(days=limit + 4)).isoformat()  # noqa: E111
  segments = history.get("assessment_timeline_segments")  # noqa: E111
  assert isinstance(segments, list)  # noqa: E111
  assert len(segments) == limit  # noqa: E111


def test_summarise_runtime_store_events_backfills_legacy_durations() -> None:
  """Legacy events without duration metadata should derive it from timestamps."""  # noqa: E111

  events = [  # noqa: E111
    {
      "timestamp": "2024-01-01T00:00:00+00:00",
      "level": "ok",
      "status": "current",
      "level_changed": True,
    },
    {
      "timestamp": "2024-01-01T06:00:00+00:00",
      "level": "watch",
      "status": "diverged",
      "level_changed": True,
    },
  ]

  summary = telemetry_module._summarise_runtime_store_assessment_events(events)  # noqa: E111

  assert summary["level_duration_peaks"]["ok"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_latest"]["ok"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["last_level_duration_seconds"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_peaks"]["watch"] == pytest.approx(0.0)  # noqa: E111
  assert summary["level_duration_latest"]["watch"] is None  # noqa: E111
  assert summary["level_duration_totals"]["ok"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_averages"]["ok"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_totals"]["watch"] == pytest.approx(0.0)  # noqa: E111
  assert summary["level_duration_averages"]["watch"] is None  # noqa: E111
  assert summary["level_duration_minimums"]["ok"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_minimums"]["watch"] is None  # noqa: E111
  assert summary["level_duration_medians"]["ok"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_medians"]["watch"] is None  # noqa: E111
  assert summary["level_duration_standard_deviations"]["ok"] == pytest.approx(0.0)  # noqa: E111
  assert summary["level_duration_standard_deviations"]["watch"] is None  # noqa: E111
  assert summary["level_duration_samples"]["ok"] == 1  # noqa: E111
  assert summary["level_duration_samples"]["watch"] == 0  # noqa: E111
  assert summary["level_duration_percentiles"]["ok"]["p75"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_percentiles"]["ok"]["p90"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_percentiles"]["ok"]["p95"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_percentiles"]["watch"] == {}  # noqa: E111
  assert summary["level_duration_alert_thresholds"]["ok"] == pytest.approx(21600.0)  # noqa: E111
  assert summary["level_duration_alert_thresholds"]["watch"] is None  # noqa: E111
  assert summary["level_duration_guard_alerts"] == []  # noqa: E111


def test_summarise_runtime_store_events_includes_percentiles() -> None:
  """Percentiles and alert thresholds should cover multi-sample durations."""  # noqa: E111

  events: list[RuntimeStoreAssessmentEvent] = [  # noqa: E111
    {
      "timestamp": "2024-01-01T00:00:00+00:00",
      "level": "ok",
      "status": "current",
      "level_changed": True,
      "current_level_duration_seconds": 10.0,
    },
    {
      "timestamp": "2024-01-01T01:00:00+00:00",
      "level": "watch",
      "status": "diverged",
      "level_changed": True,
      "current_level_duration_seconds": 20.0,
    },
    {
      "timestamp": "2024-01-01T02:00:00+00:00",
      "level": "ok",
      "status": "current",
      "level_changed": True,
      "current_level_duration_seconds": 30.0,
    },
    {
      "timestamp": "2024-01-01T03:00:00+00:00",
      "level": "ok",
      "status": "current",
      "level_changed": True,
      "current_level_duration_seconds": 40.0,
    },
  ]

  summary = telemetry_module._summarise_runtime_store_assessment_events(events)  # noqa: E111

  ok_percentiles = summary["level_duration_percentiles"]["ok"]  # noqa: E111
  assert ok_percentiles["p75"] == pytest.approx(35.0)  # noqa: E111
  assert ok_percentiles["p90"] == pytest.approx(38.0)  # noqa: E111
  assert ok_percentiles["p95"] == pytest.approx(39.0)  # noqa: E111
  watch_percentiles = summary["level_duration_percentiles"]["watch"]  # noqa: E111
  assert watch_percentiles["p75"] == pytest.approx(20.0)  # noqa: E111
  assert watch_percentiles["p90"] == pytest.approx(20.0)  # noqa: E111
  assert watch_percentiles["p95"] == pytest.approx(20.0)  # noqa: E111
  assert summary["level_duration_alert_thresholds"]["ok"] == pytest.approx(39.0)  # noqa: E111
  assert summary["level_duration_alert_thresholds"]["watch"] == pytest.approx(20.0)  # noqa: E111
  assert summary["level_duration_percentiles"]["action_required"] == {}  # noqa: E111
  assert summary["level_duration_alert_thresholds"]["action_required"] is None  # noqa: E111
  assert summary["level_duration_guard_alerts"] == []  # noqa: E111


def test_summarise_runtime_store_events_sets_guard_alerts() -> None:
  """Guard alerts should surface when percentiles exceed limits."""  # noqa: E111

  events: list[RuntimeStoreAssessmentEvent] = [  # noqa: E111
    {
      "timestamp": "2024-01-01T00:00:00+00:00",
      "level": "watch",
      "status": "diverged",
      "level_changed": True,
      "current_level_duration_seconds": 28800.0,
    },
    {
      "timestamp": "2024-01-01T08:00:00+00:00",
      "level": "ok",
      "status": "current",
      "level_changed": True,
      "current_level_duration_seconds": 1800.0,
    },
  ]

  summary = telemetry_module._summarise_runtime_store_assessment_events(events)  # noqa: E111

  alerts = summary["level_duration_guard_alerts"]  # noqa: E111
  assert len(alerts) == 1  # noqa: E111
  alert = alerts[0]  # noqa: E111
  assert alert["level"] == "watch"  # noqa: E111
  assert alert["percentile_label"] == "p95"  # noqa: E111
  assert alert["percentile_seconds"] == pytest.approx(28800.0)  # noqa: E111
  assert alert["guard_limit_seconds"] == pytest.approx(21600.0)  # noqa: E111
  assert alert["severity"] == "warning"  # noqa: E111
  assert alert["recommended_action"] is not None  # noqa: E111
