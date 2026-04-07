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
