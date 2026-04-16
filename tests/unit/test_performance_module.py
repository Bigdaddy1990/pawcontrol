"""Unit tests for performance module helper utilities."""

import asyncio
from itertools import chain, repeat
from types import SimpleNamespace

import pytest

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


def test_capture_cache_diagnostics_collects_all_channels() -> None:  # noqa: D103
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


def test_capture_cache_diagnostics_supports_summary_fallback() -> None:  # noqa: D103
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


def test_capture_cache_diagnostics_skips_failed_summary_collection() -> None:  # noqa: D103
    class _DataManagerSummaryFailure:
        def cache_snapshots(self) -> dict[str, object]:
            return {"primary": {"entries": 3}}

        def cache_repair_summary(
            self,
            snapshots: dict[str, object] | None = None,
        ) -> dict[str, object]:
            if snapshots is not None:
                raise TypeError("legacy signature")
            raise RuntimeError("summary unavailable")

    runtime_data = SimpleNamespace(data_manager=_DataManagerSummaryFailure())

    assert performance.capture_cache_diagnostics(runtime_data) == {
        "snapshots": {"primary": {"entries": 3}}
    }


def test_performance_metric_defaults_and_monitor_summary_paths() -> None:  # noqa: D103
    performance.reset_performance_metrics()
    performance.enable_performance_monitoring()

    metric = performance.PerformanceMetric(name="idle")
    assert metric.avg_time_ms == 0.0
    assert metric.p95_time_ms == 0.0
    assert metric.p99_time_ms == 0.0

    performance._performance_monitor._metrics[metric.name] = metric

    summary = performance._performance_monitor.get_summary()
    all_metrics = performance._performance_monitor.get_all_metrics()

    assert summary["metric_count"] == 1
    assert summary["total_calls"] == 0
    assert summary["avg_call_time_ms"] == 0.0
    assert summary["slowest_operations"][0]["name"] == "idle"
    assert summary["most_called_operations"][0]["name"] == "idle"
    assert all_metrics == {"idle": metric}
    assert all_metrics is not performance._performance_monitor._metrics


def test_performance_tracker_records_runs_and_failures() -> None:  # noqa: D103
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


def test_performance_tracker_recovers_from_invalid_store_shapes() -> None:  # noqa: D103
    runtime_data = SimpleNamespace(
        _performance_stats={
            "performance_buckets": {
                "refresh": {
                    "runs": "1",
                    "failures": None,
                    "durations_ms": "invalid",
                }
            }
        }
    )

    with performance.performance_tracker(runtime_data, "refresh", max_samples=3) as ctx:
        ctx.mark_failure(RuntimeError("bad"))

    bucket = runtime_data._performance_stats["performance_buckets"]["refresh"]
    assert bucket["runs"] == 2
    assert bucket["failures"] == 1
    assert isinstance(bucket["durations_ms"], list)
    assert len(bucket["durations_ms"]) == 1


def test_performance_tracker_initializes_store_from_private_attribute() -> None:  # noqa: D103
    runtime_data = SimpleNamespace(_performance_stats="invalid")

    with performance.performance_tracker(runtime_data, "refresh"):
        pass

    assert isinstance(runtime_data._performance_stats, dict)
    bucket = runtime_data._performance_stats["performance_buckets"]["refresh"]
    assert bucket["runs"] == 1


def test_performance_tracker_handles_non_mapping_bucket_container() -> None:  # noqa: D103
    runtime_data = SimpleNamespace(performance_stats={"performance_buckets": []})

    with performance.performance_tracker(runtime_data, "refresh"):
        pass

    assert isinstance(runtime_data.performance_stats["performance_buckets"], dict)
    bucket = runtime_data.performance_stats["performance_buckets"]["refresh"]
    assert bucket["runs"] == 1


def test_performance_tracker_creates_public_store_when_missing() -> None:  # noqa: D103
    class _RuntimeData:
        def __init__(self) -> None:
            self.performance_stats = None

    runtime_data = _RuntimeData()

    with performance.performance_tracker(runtime_data, "refresh"):
        pass

    assert isinstance(runtime_data.performance_stats, dict)
    bucket = runtime_data.performance_stats["performance_buckets"]["refresh"]
    assert bucket["runs"] == 1


def test_performance_tracker_replaces_non_mapping_bucket() -> None:  # noqa: D103
    runtime_data = SimpleNamespace(
        performance_stats={"performance_buckets": {"refresh": []}}
    )

    with performance.performance_tracker(runtime_data, "refresh"):
        pass

    bucket = runtime_data.performance_stats["performance_buckets"]["refresh"]
    assert bucket == {
        "runs": 1,
        "failures": 0,
        "durations_ms": bucket["durations_ms"],
    }
    assert len(bucket["durations_ms"]) == 1


def test_record_maintenance_result_merges_legacy_history_and_metadata() -> None:  # noqa: D103
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


def test_capture_cache_diagnostics_handles_snapshot_errors_and_empty_runtime() -> None:  # noqa: D103
    class _DataManagerBrokenSnapshots:
        def cache_snapshots(self) -> dict[str, object]:
            raise RuntimeError("broken")

    runtime_data = SimpleNamespace(data_manager=_DataManagerBrokenSnapshots())

    assert performance.capture_cache_diagnostics(runtime_data) is None
    assert performance.capture_cache_diagnostics(None) is None


def test_performance_helpers_and_monitor_lifecycle() -> None:  # noqa: D103
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


def test_track_performance_decorator_records_sync_and_async_calls() -> None:  # noqa: D103
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


def test_track_performance_logs_slow_sync_and_async_calls(monkeypatch) -> None:  # noqa: D103
    async def _exercise() -> None:
        performance.reset_performance_metrics()
        performance.enable_performance_monitoring()
        perf_counter_values = chain([0.0, 0.2, 1.0, 1.2], repeat(1.2))
        warnings: list[tuple[object, ...]] = []

        monkeypatch.setattr(
            performance.time,
            "perf_counter",
            lambda: next(perf_counter_values),
        )
        monkeypatch.setattr(
            performance._LOGGER,
            "warning",
            lambda *args: warnings.append(args),
        )

        @performance.track_performance(slow_threshold_ms=-1.0)
        def sync_call() -> str:
            return "sync"

        @performance.track_performance(slow_threshold_ms=-1.0)
        async def async_call() -> str:
            return "async"

        assert sync_call() == "sync"
        assert await async_call() == "async"
        assert len(warnings) == 2
        assert warnings[0][0] == "Slow operation: %s took %.2fms (threshold: %.2fms)"
        assert warnings[0][1] == "sync_call"
        assert warnings[0][2] >= 0.0
        assert warnings[0][3] == -1.0
        assert warnings[1][0] == "Slow operation: %s took %.2fms (threshold: %.2fms)"
        assert warnings[1][1] == "async_call"
        assert warnings[1][2] >= 0.0
        assert warnings[1][3] == -1.0

    asyncio.run(_exercise())


def test_track_performance_records_failures_for_sync_and_async_calls(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _exercise() -> None:
        performance.reset_performance_metrics()
        performance.enable_performance_monitoring()
        perf_counter_values = chain([2.0, 2.25, 4.0, 4.35], repeat(4.35))
        warnings: list[tuple[object, ...]] = []

        monkeypatch.setattr(
            performance.time,
            "perf_counter",
            lambda: next(perf_counter_values),
        )
        monkeypatch.setattr(
            performance._LOGGER,
            "warning",
            lambda *args: warnings.append(args),
        )

        @performance.track_performance("sync_failure", slow_threshold_ms=-1.0)
        def sync_call() -> None:
            raise RuntimeError("sync boom")

        @performance.track_performance("async_failure", slow_threshold_ms=-1.0)
        async def async_call() -> None:
            raise ValueError("async boom")

        with pytest.raises(RuntimeError, match="sync boom"):
            sync_call()

        with pytest.raises(ValueError, match="async boom"):
            await async_call()

        sync_metric = performance._performance_monitor.get_metric("sync_failure")
        async_metric = performance._performance_monitor.get_metric("async_failure")
        assert sync_metric is not None
        assert async_metric is not None
        assert sync_metric.call_count == 1
        assert async_metric.call_count == 1
        assert len(warnings) == 2
        assert warnings[0][0] == "Slow operation: %s took %.2fms (threshold: %.2fms)"
        assert warnings[0][1] == "sync_failure"
        assert warnings[0][2] >= 0.0
        assert warnings[0][3] == -1.0
        assert warnings[1][0] == "Slow operation: %s took %.2fms (threshold: %.2fms)"
        assert warnings[1][1] == "async_failure"
        assert warnings[1][2] >= 0.0
        assert warnings[1][3] == -1.0

    asyncio.run(_exercise())


def test_debounce_throttle_and_batch_calls() -> None:  # noqa: D103
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


def test_track_performance_records_metrics_when_calls_raise() -> None:  # noqa: D103
    async def _exercise() -> None:
        performance.reset_performance_metrics()
        performance.enable_performance_monitoring()

        @performance.track_performance("sync_failure", log_slow=False)
        def sync_call() -> None:
            raise RuntimeError("sync boom")

        @performance.track_performance("async_failure", log_slow=False)
        async def async_call() -> None:
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError, match="sync boom"):
            sync_call()

        with pytest.raises(RuntimeError, match="async boom"):
            await async_call()

        sync_metric = performance._performance_monitor.get_metric("sync_failure")
        async_metric = performance._performance_monitor.get_metric("async_failure")

        assert sync_metric is not None
        assert async_metric is not None
        assert sync_metric.call_count == 1
        assert async_metric.call_count == 1

    asyncio.run(_exercise())


def test_batch_calls_starts_a_new_task_after_previous_batch_finishes() -> None:  # noqa: D103
    async def _exercise() -> None:
        batched: list[int] = []

        @performance.batch_calls(max_batch_size=2, max_wait_ms=10.0)
        async def batch_target(value: int) -> None:
            batched.append(value)

        await batch_target(1)
        await asyncio.sleep(0.03)
        await batch_target(2)
        await asyncio.sleep(0.03)

        assert batched == [1, 2]

    asyncio.run(_exercise())


def test_capture_cache_diagnostics_counts_all_legacy_cache_slots() -> None:  # noqa: D103
    runtime_data = SimpleNamespace(
        caches={"alpha": object(), "beta": object()},
        _caches={"gamma": object()},
    )

    diagnostics = performance.capture_cache_diagnostics(runtime_data)

    assert diagnostics == {
        "legacy": {
            "caches": {"entries": 2},
            "_caches": {"entries": 1},
        }
    }


def test_debounce_cancels_pending_task_before_latest_call_runs() -> None:  # noqa: D103
    async def _exercise() -> None:
        calls: list[str] = []

        @performance.debounce(0.03)
        async def debounced(marker: str) -> str:
            calls.append(marker)
            return marker

        assert await debounced("first") == "first"
        assert await debounced("second") is None
        assert await debounced("third") is None
        await asyncio.sleep(0.05)

        assert calls == ["first", "third"]

    asyncio.run(_exercise())


def test_performance_monitor_singleton_reuse_and_get_instance_paths() -> None:
    """Singleton helpers should reuse the existing monitor instance."""
    first = performance.PerformanceMonitor()
    second = performance.PerformanceMonitor()
    from_get_instance = performance.PerformanceMonitor.get_instance()

    assert first is second
    assert second is from_get_instance


def test_performance_monitor_record_reuses_existing_metric_instance() -> None:
    """Recording the same metric twice should not allocate a second metric object."""
    monitor = performance.PerformanceMonitor.get_instance()
    monitor._metrics = {}
    monitor.enable()

    monitor.record("repeat_metric", 10.0)
    monitor.record("repeat_metric", 25.0)

    metric = monitor.get_metric("repeat_metric")
    assert metric is not None
    assert len(monitor._metrics) == 1
    assert metric.call_count == 2


def test_capture_cache_diagnostics_skips_non_callable_summary_method() -> None:
    """Snapshot diagnostics should skip repair summary when hook is not callable."""

    class _DataManagerNoSummaryCallable:
        cache_repair_summary = "not-callable"

        def cache_snapshots(self) -> dict[str, object]:
            return {"primary": {"entries": 4}}

    runtime_data = SimpleNamespace(data_manager=_DataManagerNoSummaryCallable())

    assert performance.capture_cache_diagnostics(runtime_data) == {
        "snapshots": {"primary": {"entries": 4}}
    }


def test_ensure_runtime_performance_store_without_known_attributes() -> None:
    """Store helper should return an ephemeral dict when runtime has no store attrs."""
    runtime_data = object()

    store = performance._ensure_runtime_performance_store(runtime_data)

    assert store == {}


def test_record_maintenance_result_handles_non_list_legacy_history() -> None:
    """Legacy history should be ignored when it is not list-shaped."""
    runtime_data = SimpleNamespace(
        performance_stats={
            "maintenance_history": {"legacy": "invalid"},
            "maintenance_results": [],
        }
    )

    performance.record_maintenance_result(
        runtime_data,
        task="cleanup",
        status="ok",
        max_entries=5,
    )

    history = runtime_data.performance_stats["maintenance_results"]
    assert runtime_data.performance_stats["maintenance_history"] is history
    assert isinstance(history, list)
    assert len(history) == 1
    assert history[0]["task"] == "cleanup"


def test_record_maintenance_result_skips_metadata_injection_for_coordinator_task() -> (
    None
):
    """Coordinator maintenance events should not inject metadata into diagnostics."""
    runtime_data = SimpleNamespace(performance_stats={})

    performance.record_maintenance_result(
        runtime_data,
        task="coordinator_maintenance",
        status="ok",
        diagnostics={"source": "scheduler"},
        metadata={"window": "night"},
    )

    entry = runtime_data.performance_stats["last_maintenance_result"]
    assert entry["metadata"] == {"window": "night"}
    assert entry["diagnostics"] == {"source": "scheduler"}


def test_batch_calls_process_batch_returns_when_pending_is_drained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Queued batch task should no-op when pending calls are cleared."""

    async def _exercise() -> None:
        executed: list[int] = []
        queued_batches: list[asyncio.coroutines] = []

        class _TaskStub:
            def done(self) -> bool:
                return False

        def _capture_batch(coro):
            queued_batches.append(coro)
            return _TaskStub()

        async def _fast_sleep(_delay: float) -> None:
            return None

        monkeypatch.setattr(performance.asyncio, "create_task", _capture_batch)
        monkeypatch.setattr(performance.asyncio, "sleep", _fast_sleep)

        @performance.batch_calls(max_batch_size=2, max_wait_ms=1.0)
        async def batch_target(value: int) -> None:
            executed.append(value)

        await batch_target(1)
        assert len(queued_batches) == 1

        pending_calls = next(
            cell.cell_contents
            for cell in batch_target.__closure__ or ()
            if isinstance(cell.cell_contents, list)
            and (not cell.cell_contents or isinstance(cell.cell_contents[0], tuple))
        )
        pending_calls.clear()

        await queued_batches[0]
        assert executed == []

    asyncio.run(_exercise())
