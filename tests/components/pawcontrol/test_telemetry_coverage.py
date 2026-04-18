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


def test_build_runtime_store_assessment_segments_uses_duration_fallback_for_last_event() -> (
    None
):
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


def test_runtime_store_timeline_summary_and_event_recording_fallbacks() -> None:
    """Timeline helpers should reuse stored summaries and support no-op recordings."""
    events = [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "level": "ok",
            "status": "current",
            "reason": "all good",
        }
    ]
    history = {
        "assessment_events": events,
        "assessment_timeline_summary": {"status": "stored"},
    }

    summary_from_history = telemetry._resolve_runtime_store_assessment_timeline_summary(
        history,
        events,
    )
    assert summary_from_history == {"status": "stored"}

    fallback_summary = telemetry._resolve_runtime_store_assessment_timeline_summary(
        {},
        events,
    )
    assert isinstance(fallback_summary, dict)

    assessment = {
        "level": "ok",
        "previous_level": "ok",
        "reason": None,
        "recommended_action": None,
        "checks": 1,
        "divergence_events": 0,
        "current_level_duration_seconds": "invalid",
    }
    recorded_events, timeline_summary = telemetry._record_runtime_store_assessment_event(
        history,
        assessment,
        recorded=False,
        previous_assessment=None,
        status="current",
        entry_status="current",
        store_status="current",
    )
    assert len(recorded_events) == 1
    assert recorded_events[0]["level"] == "ok"
    assert timeline_summary == {"status": "stored"}


def test_update_runtime_reconfigure_summary_persists_valid_payload() -> None:
    """Valid config-entry telemetry should be cached in runtime performance stats."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            config_entry=SimpleNamespace(
                options={
                    "last_reconfigure": "2026-01-01T00:00:00+00:00",
                    "reconfigure_telemetry": {
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "requested_profile": "balanced",
                        "previous_profile": "minimal",
                        "dogs_count": 2,
                        "estimated_entities": 8,
                        "version": 1,
                    },
                }
            )
        ),
        performance_stats={},
    )

    summary = telemetry.update_runtime_reconfigure_summary(runtime_data)
    assert summary is not None
    assert runtime_data.performance_stats["reconfigure_summary"] == summary
    assert telemetry.get_runtime_reconfigure_summary(runtime_data) == summary


def test_runtime_resilience_getters_and_update_helpers() -> None:
    """Resilience helper APIs should round-trip summary and diagnostics payloads."""
    runtime_data = SimpleNamespace(performance_stats={})

    summary = {"state": "watch", "failures": 1}
    stored_summary = telemetry.update_runtime_resilience_summary(runtime_data, summary)
    assert stored_summary == summary
    assert telemetry.get_runtime_resilience_summary(runtime_data) == summary

    diagnostics = {
        "breakers": {
            "api": {"state": "open", "opens": 2},
            "ignored": "not-a-mapping",
        },
        "summary": {"state": "watch", "failures": 1},
    }
    stored_diagnostics = telemetry.update_runtime_resilience_diagnostics(
        runtime_data,
        diagnostics,
    )
    assert stored_diagnostics is not None
    assert "api" in stored_diagnostics.get("breakers", {})
    assert telemetry.get_runtime_resilience_diagnostics(runtime_data) is not None

    telemetry.update_runtime_resilience_summary(runtime_data, None)
    remaining_diagnostics = runtime_data.performance_stats.get("resilience_diagnostics")
    assert isinstance(remaining_diagnostics, dict)
    assert "summary" not in remaining_diagnostics

    telemetry.update_runtime_resilience_diagnostics(runtime_data, None)
    assert telemetry.get_runtime_resilience_summary(runtime_data) is None
    assert telemetry.get_runtime_resilience_diagnostics(runtime_data) is None


def test_entity_factory_guard_metrics_init_none_runtime_and_defaults() -> None:
    """Guard metrics helper should initialize defaults and handle None runtime data."""
    assert (
        telemetry.update_runtime_entity_factory_guard_metrics(
            None,
            runtime_floor=5.0,
            actual_duration=1.0,
            event="stable",
            baseline_floor=4.0,
            max_floor=10.0,
            enforce_min_runtime=False,
        )
        is None
    )

    runtime_data = SimpleNamespace(
        performance_stats={"entity_factory_guard_metrics": "invalid"},
    )
    metrics = telemetry.update_runtime_entity_factory_guard_metrics(
        runtime_data,
        runtime_floor=0.0,
        actual_duration=-5.0,
        event="unknown",
        baseline_floor=2.0,
        max_floor=20.0,
        enforce_min_runtime=False,
    )

    assert metrics is not None
    assert metrics["samples"] == 1
    assert metrics["runtime_floor"] == 0.0
    assert metrics["stable_ratio"] >= 0.0
    assert metrics["recent_events"][-1] == "unknown"


def test_record_door_sensor_persistence_failure_without_optional_error_history() -> None:
    """Door-sensor telemetry should skip optional fields when not provided."""
    runtime_data = SimpleNamespace(
        performance_stats={},
        error_history="not-a-list",
    )

    failure = telemetry.record_door_sensor_persistence_failure(
        runtime_data,
        dog_id="solo",
        limit=1,
    )

    assert failure is not None
    assert failure["dog_id"] == "solo"
    assert "error" not in failure
    assert runtime_data.performance_stats["door_sensor_failure_count"] == 1


def test_runtime_resilience_and_reconfigure_getters_none_paths() -> None:
    """Getter helpers should return ``None`` when stats are missing or malformed."""
    runtime_reconfigure = SimpleNamespace(performance_stats={"reconfigure_summary": "bad"})
    assert telemetry.get_runtime_reconfigure_summary(runtime_reconfigure) is None

    runtime_resilience = SimpleNamespace(
        performance_stats={
            "resilience_summary": "bad",
            "resilience_diagnostics": {"breakers": "bad", "summary": "bad"},
        }
    )
    assert telemetry.get_runtime_resilience_summary(runtime_resilience) is None
    assert telemetry.get_runtime_resilience_diagnostics(runtime_resilience) is None


def test_runtime_resilience_update_branch_matrix() -> None:
    """Resilience update helpers should cover mapping/non-mapping transitions."""
    runtime_data = SimpleNamespace(
        performance_stats={
            "resilience_diagnostics": "bad",
            "resilience_summary": {"state": "ok"},
        }
    )

    telemetry.update_runtime_resilience_summary(runtime_data, None)
    assert "resilience_diagnostics" not in runtime_data.performance_stats
    assert "resilience_summary" not in runtime_data.performance_stats

    runtime_data.performance_stats["resilience_diagnostics"] = {"breakers": {"api": {"state": "open"}}}
    stored = telemetry.update_runtime_resilience_summary(runtime_data, {"state": "watch"})
    assert stored is not None
    diagnostics = runtime_data.performance_stats["resilience_diagnostics"]
    assert diagnostics["summary"]["state"] == "watch"

    telemetry.update_runtime_resilience_diagnostics(runtime_data, {"breakers": "bad", "summary": "bad"})
    assert runtime_data.performance_stats["resilience_diagnostics"] == {}
    assert "resilience_summary" not in runtime_data.performance_stats


def test_entity_factory_guard_metrics_cover_contract_stable_and_trim_branches() -> None:
    """Guard metrics should handle contract/stable events and trimming windows."""
    runtime_data_trim = SimpleNamespace(
        performance_stats={
            "entity_factory_guard_metrics": {
                "schema_version": 1,
                "samples": -1,
                "stable_samples": 0,
                "expansions": 0,
                "contractions": 0,
                "stable_ratio": 0.1,
                "lowest_runtime_floor": 5.0,
                "recent_durations": [1.0, 2.0, 3.0, 4.0, 5.0],
                "recent_events": ["expand", "expand", "expand", "expand", "expand"],
            }
        },
    )
    metrics_trim = telemetry.update_runtime_entity_factory_guard_metrics(
        runtime_data_trim,
        runtime_floor=3.0,
        actual_duration=6.0,
        event="stable",
        baseline_floor=2.0,
        max_floor=20.0,
        enforce_min_runtime=False,
    )
    assert metrics_trim is not None
    assert metrics_trim["samples"] == 0
    assert metrics_trim["stable_ratio"] == 0.0
    assert len(metrics_trim["recent_durations"]) == 5
    assert len(metrics_trim["recent_events"]) == 5
    assert metrics_trim["stability_trend"] == "improving"

    runtime_data_contract = SimpleNamespace(
        performance_stats={
            "entity_factory_guard_metrics": {
                "schema_version": 1,
                "samples": 2,
                "stable_samples": 1,
                "expansions": 1,
                "contractions": 0,
                "average_duration": 2.0,
                "max_duration": 4.0,
                "min_duration": 1.0,
                "runtime_floor": 10.0,
                "stable_ratio": 0.5,
            }
        },
    )
    metrics_contract = telemetry.update_runtime_entity_factory_guard_metrics(
        runtime_data_contract,
        runtime_floor=8.0,
        actual_duration=3.0,
        event="contract",
        baseline_floor=2.0,
        max_floor=20.0,
        enforce_min_runtime=True,
    )
    assert metrics_contract is not None
    assert metrics_contract["samples"] == 3
    assert metrics_contract["contractions"] == 1
    assert metrics_contract["average_duration"] > 0.0
    assert metrics_contract["max_duration"] >= 4.0
    assert metrics_contract["min_duration"] <= 3.0


def test_record_door_sensor_persistence_failure_error_history_without_error_field() -> None:
    """Error-history entries should omit the error key when no error is supplied."""
    runtime_data = SimpleNamespace(performance_stats={}, error_history=[])
    telemetry.record_door_sensor_persistence_failure(
        runtime_data,
        dog_id="solo",
        door_sensor="binary_sensor.solo_door",
        error=None,
    )
    assert runtime_data.error_history
    latest = runtime_data.error_history[-1]
    assert latest["source"] == "door_sensor_persistence"
    assert "error" not in latest


def test_update_runtime_entity_factory_guard_metrics_handles_missing_previous_floor(
    monkeypatch,
) -> None:
    """Guard metrics should default floor-change deltas when previous floor resolves missing."""
    import builtins

    runtime_data = SimpleNamespace(performance_stats={})
    baseline_floor = 7.123
    coerced_once = {"done": False}

    def _patched_max(*args, **kwargs):  # type: ignore[no-untyped-def]
        if (
            not coerced_once["done"]
            and len(args) == 2
            and args[0] == baseline_floor
            and args[1] == 0.0
        ):
            coerced_once["done"] = True
            return None
        return builtins.max(*args, **kwargs)

    monkeypatch.setattr(telemetry, "max", _patched_max, raising=False)

    metrics = telemetry.update_runtime_entity_factory_guard_metrics(
        runtime_data,
        runtime_floor=3.0,
        actual_duration=1.0,
        event="expand",
        baseline_floor=baseline_floor,
        max_floor=15.0,
        enforce_min_runtime=False,
    )

    assert metrics is not None
    assert metrics["last_floor_change"] == 0.0
    assert metrics["last_floor_change_ratio"] == 0.0


def test_update_runtime_entity_factory_guard_metrics_stable_run_not_extended() -> None:
    """Stable samples below the longest run should keep the historical max run."""
    runtime_data = SimpleNamespace(
        performance_stats={
            "entity_factory_guard_metrics": {
                "schema_version": 1,
                "samples": 5,
                "stable_samples": 2,
                "expansions": 1,
                "contractions": 1,
                "runtime_floor": 5.0,
                "consecutive_stable_samples": 3,
                "longest_stable_run": 10,
            }
        },
    )

    metrics = telemetry.update_runtime_entity_factory_guard_metrics(
        runtime_data,
        runtime_floor=5.0,
        actual_duration=2.0,
        event="stable",
        baseline_floor=4.0,
        max_floor=20.0,
        enforce_min_runtime=True,
    )

    assert metrics is not None
    assert metrics["consecutive_stable_samples"] == 4
    assert metrics["longest_stable_run"] == 10


def test_record_bool_coercion_event_honours_sample_limit() -> None:
    """Bool coercion sample storage should stop appending after the configured cap."""
    telemetry.reset_bool_coercion_metrics()
    limit = telemetry._BOOL_COERCION_SAMPLE_LIMIT

    for index in range(limit + 1):
        telemetry.record_bool_coercion_event(
            value=index,
            default=False,
            result=bool(index % 2),
            reason="fallback",
        )

    metrics = telemetry.get_bool_coercion_metrics()
    assert metrics["total"] == limit + 1
    assert len(metrics["samples"]) == limit

    telemetry.reset_bool_coercion_metrics()


def test_runtime_reconfigure_and_resilience_getters_return_none_without_stats() -> None:
    """Getter helpers should return None when runtime performance stats are unavailable."""
    runtime_data = SimpleNamespace()

    assert telemetry.get_runtime_reconfigure_summary(runtime_data) is None
    assert telemetry.get_runtime_resilience_summary(runtime_data) is None
    assert telemetry.get_runtime_resilience_diagnostics(runtime_data) is None


def test_update_runtime_resilience_summary_removes_empty_diagnostics_mapping() -> None:
    """Removing resilience summary should drop diagnostics when only summary data remains."""
    runtime_data = SimpleNamespace(
        performance_stats={
            "resilience_summary": {"state": "watch"},
            "resilience_diagnostics": {"summary": {"state": "watch"}},
        },
    )

    result = telemetry.update_runtime_resilience_summary(runtime_data, None)

    assert result is None
    assert "resilience_summary" not in runtime_data.performance_stats
    assert "resilience_diagnostics" not in runtime_data.performance_stats
