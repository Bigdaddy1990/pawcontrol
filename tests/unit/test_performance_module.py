"""Unit tests for performance module helper utilities."""

from types import SimpleNamespace

from custom_components.pawcontrol import performance


class _DataManagerWithSnapshots:
    def cache_snapshots(self) -> dict[str, object]:
        return {"primary": {"entries": 2}}

    def cache_repair_summary(self, snapshots: dict[str, object]) -> dict[str, object]:
        return {"sources": list(snapshots)}


class _DataManagerFallbackSummary:
    def cache_snapshots(self) -> dict[str, object]:
        return {"primary": {"entries": 1}}

    def cache_repair_summary(self) -> dict[str, object]:
        return {"status": "fallback"}


class _MonitorRaises:
    def get_summary(self) -> dict[str, object]:
        raise RuntimeError("nope")


def test_capture_cache_diagnostics_collects_all_channels() -> None:
    runtime_data = SimpleNamespace(
        data_manager=_DataManagerWithSnapshots(),
        cache={"a": 1},
        _cache={"b": 2},
        performance_monitor=SimpleNamespace(get_summary=lambda: {"enabled": True}),
    )

    diagnostics = performance.capture_cache_diagnostics(runtime_data)

    assert diagnostics == {
        "snapshots": {"primary": {"entries": 2}},
        "repair_summary": {"sources": ["primary"]},
        "legacy": {
            "cache": {"entries": 1},
            "_cache": {"entries": 1},
        },
        "performance": {"enabled": True},
    }


def test_capture_cache_diagnostics_supports_summary_fallback() -> None:
    runtime_data = SimpleNamespace(
        data_manager=_DataManagerFallbackSummary(),
        performance_monitor=_MonitorRaises(),
    )

    diagnostics = performance.capture_cache_diagnostics(runtime_data)

    assert diagnostics == {
        "snapshots": {"primary": {"entries": 1}},
        "repair_summary": {"status": "fallback"},
        "performance": {"status": "unavailable"},
    }


def test_performance_tracker_records_runs_and_failures() -> None:
    runtime_data = SimpleNamespace(performance_stats={})

    with performance.performance_tracker(runtime_data, "refresh", max_samples=2) as ctx:
        ctx.mark_failure(ValueError("bad"))

    with performance.performance_tracker(runtime_data, "refresh", max_samples=2):
        pass

    with performance.performance_tracker(runtime_data, "refresh", max_samples=2):
        pass

    bucket = runtime_data.performance_stats["performance_buckets"]["refresh"]
    assert bucket["runs"] == 3
    assert bucket["failures"] == 1
    assert len(bucket["durations_ms"]) == 2


def test_record_maintenance_result_merges_legacy_history_and_metadata() -> None:
    existing_event = {"task": "old", "status": "ok"}
    runtime_data = SimpleNamespace(
        performance_stats={
            "maintenance_history": [existing_event],
            "maintenance_results": "invalid",
        }
    )

    performance.record_maintenance_result(
        runtime_data,
        task="daily_cleanup",
        status="ok",
        message="done",
        diagnostics={"source": "scheduler"},
        metadata={"window": "night"},
        details={"removed": 2},
        max_entries=2,
    )
    performance.record_maintenance_result(
        runtime_data,
        task="second",
        status="ok",
        max_entries=2,
    )

    store = runtime_data.performance_stats
    assert store["maintenance_results"] is store["maintenance_history"]
    history = store["maintenance_results"]
    assert len(history) == 2
    assert history[0]["task"] == "daily_cleanup"
    assert history[0]["diagnostics"]["metadata"] == {"window": "night"}
    assert history[0]["details"] == {"removed": 2}
    assert history[1]["task"] == "second"
    assert store["last_maintenance_result"]["task"] == "second"
