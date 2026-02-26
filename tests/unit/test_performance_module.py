"""Unit tests for performance module helper utilities."""

import asyncio
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


def test_capture_cache_diagnostics_handles_snapshot_errors_and_empty_runtime() -> None:
    class _DataManagerBrokenSnapshots:
        def cache_snapshots(self) -> dict[str, object]:
            raise RuntimeError("broken")

    runtime_data = SimpleNamespace(data_manager=_DataManagerBrokenSnapshots())

    assert performance.capture_cache_diagnostics(runtime_data) is None
    assert performance.capture_cache_diagnostics(None) is None


def test_performance_helpers_and_monitor_lifecycle() -> None:
    performance.reset_performance_metrics()
    performance.enable_performance_monitoring()

    performance._performance_monitor.record("fast_op", 12.0)
    performance._performance_monitor.record("slow_op", 200.0)

    summary = performance.get_performance_summary()
    assert summary["enabled"] is True
    assert summary["metric_count"] == 2
    assert summary["total_calls"] == 2

    slow = performance.get_slow_operations(100.0)
    assert [metric["name"] for metric in slow] == ["slow_op"]

    performance.disable_performance_monitoring()
    performance._performance_monitor.record("ignored", 1000.0)
    assert performance._performance_monitor.get_metric("ignored") is None

    performance.enable_performance_monitoring()
    performance.reset_performance_metrics()
    assert performance.get_performance_summary()["metric_count"] == 0


def test_track_performance_decorator_records_sync_and_async_calls() -> None:
    async def _exercise() -> None:
        performance.reset_performance_metrics()
        performance.enable_performance_monitoring()

        @performance.track_performance("sync_metric", log_slow=False)
        def sync_call(value: int) -> int:
            return value + 1

        @performance.track_performance("async_metric", log_slow=False)
        async def async_call(value: int) -> int:
            await asyncio.sleep(0)
            return value + 2

        assert sync_call(3) == 4
        assert await async_call(3) == 5

        assert performance._performance_monitor.get_metric("sync_metric") is not None
        assert performance._performance_monitor.get_metric("async_metric") is not None

    asyncio.run(_exercise())


def test_debounce_throttle_and_batch_calls() -> None:
    async def _exercise() -> None:
        calls: list[str] = []

        @performance.debounce(0.05)
        async def debounced(marker: str) -> str:
            calls.append(f"debounced:{marker}")
            return marker

        first = await debounced("first")
        second = await debounced("second")
        await asyncio.sleep(0.07)

        assert first == "first"
        assert second is None
        assert calls == ["debounced:first", "debounced:second"]

        throttle_calls: list[float] = []

        @performance.throttle(50.0)
        async def throttled() -> None:
            throttle_calls.append(asyncio.get_running_loop().time())

        await throttled()
        await throttled()
        assert len(throttle_calls) == 2
        assert throttle_calls[1] >= throttle_calls[0]

        batched: list[int] = []

        @performance.batch_calls(max_batch_size=2, max_wait_ms=20.0)
        async def batch_target(value: int) -> None:
            if value == 2:
                raise RuntimeError("boom")
            batched.append(value)

        await batch_target(1)
        await batch_target(2)
        await asyncio.sleep(0.05)

        assert batched == [1]

    asyncio.run(_exercise())
