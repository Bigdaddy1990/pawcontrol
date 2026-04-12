"""Coverage-focused tests for telemetry fallbacks and aggregations."""

from types import SimpleNamespace

from custom_components.pawcontrol import telemetry


def test_summarise_reconfigure_options_handles_positive_and_fallback_paths() -> None:
    """Summary helper should aggregate valid payloads and default malformed values."""
    options = {
        "last_reconfigure": "2026-01-01T00:00:00+00:00",
        "reconfigure_telemetry": {
            "timestamp": None,
            "requested_profile": "balanced",
            "previous_profile": None,
            "dogs_count": "3",
            "estimated_entities": "12.9",
            "version": "invalid",
            "compatibility_warnings": ["warn-a", None],
            "merge_notes": "single-note",
            "health_summary": {
                "healthy": False,
                "issues": "db mismatch",
                "warnings": ["slow refresh", None],
            },
        },
    }

    summary = telemetry.summarise_reconfigure_options(options)

    assert summary is not None
    assert summary["timestamp"] == "2026-01-01T00:00:00+00:00"
    assert summary["dogs_count"] == 3
    assert summary["estimated_entities"] == 12
    assert summary["version"] == 0
    assert summary["warning_count"] == 1
    assert summary["merge_notes"] == ["single-note"]
    assert summary["healthy"] is False
    assert summary["health_issues"] == ["db mismatch"]

    assert telemetry.summarise_reconfigure_options(None) is None
    assert (
        telemetry.summarise_reconfigure_options({"reconfigure_telemetry": "bad"})
        is None
    )


def test_update_runtime_reconfigure_summary_stable_cleanup_on_missing_schema() -> None:
    """Missing telemetry payload should consistently remove stale summary data."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(config_entry=SimpleNamespace(options={})),
        performance_stats={"reconfigure_summary": {"stale": True}},
    )

    summary = telemetry.update_runtime_reconfigure_summary(runtime_data)

    assert summary is None
    assert "reconfigure_summary" not in runtime_data.performance_stats


def test_record_door_sensor_persistence_failure_aggregates_and_clamps_defaults() -> (
    None
):
    """Door sensor telemetry should aggregate counters from malformed baselines."""
    runtime_data = SimpleNamespace(
        performance_stats={
            "door_sensor_failures": (
                {"dog_id": "old", "recorded_at": "x"},
                "bad",
            ),
            "door_sensor_failure_summary": {"fido": "invalid"},
        },
        error_history=[],
    )

    first = telemetry.record_door_sensor_persistence_failure(
        runtime_data,
        dog_id="fido",
        dog_name="Fido",
        door_sensor="binary_sensor.fido_door",
        settings={"enabled": True},
        error=RuntimeError("cannot persist"),
        limit=2,
    )
    second = telemetry.record_door_sensor_persistence_failure(
        runtime_data,
        dog_id="fido",
        error="retry failed",
        limit=2,
    )
    third = telemetry.record_door_sensor_persistence_failure(
        runtime_data,
        dog_id="fido",
        error="third",
        limit=2,
    )

    assert first is not None
    assert second is not None
    assert third is not None

    stats = runtime_data.performance_stats
    assert stats["door_sensor_failure_count"] == 2
    assert len(stats["door_sensor_failures"]) == 2
    summary = stats["door_sensor_failure_summary"]["fido"]
    assert summary["failure_count"] == 3
    assert summary["dog_name"] == "Fido"
    assert stats["last_door_sensor_failure"]["error"] == "third"

    assert len(runtime_data.error_history) == 3
    assert runtime_data.error_history[-1]["source"] == "door_sensor_persistence"


def test_record_door_sensor_persistence_failure_returns_none_without_runtime_data() -> (
    None
):
    """None runtime data should no-op instead of creating inconsistent telemetry."""
    assert (
        telemetry.record_door_sensor_persistence_failure(
            None,
            dog_id="fido",
            error="ignored",
        )
        is None
    )


def test_build_runtime_store_assessment_escalates_on_future_incompatible_status() -> (
    None
):
    """Future-incompatible snapshots should produce action-required assessments."""
    snapshot = {
        "status": "future_incompatible",
        "entry": {"status": "future_incompatible"},
        "store": {"status": "future_incompatible"},
        "divergence_detected": False,
    }
    history = {
        "checks": 4,
        "divergence_events": 0,
        "last_status": "future_incompatible",
        "last_entry_status": "future_incompatible",
        "last_store_status": "future_incompatible",
        "last_checked": "2026-01-01T00:00:00+00:00",
        "divergence_detected": False,
    }

    assessment = telemetry._build_runtime_store_assessment(
        snapshot,
        history,
        recorded=True,
        previous_assessment=None,
    )

    assert assessment["level"] == "action_required"
    assert assessment["reason"] == (
        "Runtime store caches were produced by a newer schema and must be reset."
    )
    assert assessment["recommended_action"] is not None


def test_build_runtime_store_assessment_segments_uses_duration_fallback_for_last_event(
) -> None:
    """Segment builder should use current-level fallback duration for final events."""
    events = [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "level": "ok",
            "status": "current",
            "reason": "ok",
        },
        {
            "timestamp": "2026-01-01T00:10:00+00:00",
            "level": "watch",
            "status": "diverged",
            "reason": "drift",
            "current_level_duration_seconds": 120.0,
        },
    ]

    segments = telemetry._build_runtime_store_assessment_segments(events)

    assert len(segments) == 2
    assert segments[0]["duration_seconds"] == 600.0
    assert segments[1]["duration_seconds"] == 120.0
    assert segments[1]["status"] == "diverged"


def test_update_runtime_entity_factory_guard_metrics_calculates_regressing_trend() -> (
    None
):
    """Guard metrics should report regressing trend when stable ratio drops sharply."""
    runtime_data = SimpleNamespace(
        performance_stats={
            "entity_factory_guard_metrics": {
                "schema_version": 1,
                "samples": 10,
                "stable_samples": 8,
                "stable_ratio": 0.8,
                "runtime_floor": 10.0,
                "recent_events": ["expand", "contract", "expand", "contract"],
                "recent_durations": [2.0, 2.0, 2.0, 2.0],
                "expansions": 1,
                "contractions": 1,
            }
        },
    )

    metrics = telemetry.update_runtime_entity_factory_guard_metrics(
        runtime_data,
        runtime_floor=8.0,
        actual_duration=3.0,
        event="expand",
        baseline_floor=5.0,
        max_floor=20.0,
        enforce_min_runtime=True,
    )

    assert metrics is not None
    assert metrics["samples"] == 11
    assert metrics["expansions"] == 2
    assert metrics["stability_trend"] == "regressing"
