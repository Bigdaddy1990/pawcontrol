"""Coverage tests for helpers performance monitor utilities."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timezone

import pytest

from custom_components.pawcontrol.helpers import PerformanceMonitor, _data_encoder


@dataclass(slots=True)
class _DataWithIsoformat:
    value: str

    def isoformat(self) -> str:
        return self.value


class _StringOnly:
    __slots__ = ()

    def __str__(self) -> str:
        return "string-only"


def test_data_encoder_handles_supported_types() -> None:
    """The data encoder should normalize datetimes, objects, and fallbacks."""
    dt_value = datetime(2026, 3, 27, 12, 30, tzinfo=UTC)

    class _HasDict:
        def __init__(self) -> None:
            self.name = "Buddy"

    assert _data_encoder(dt_value) == "2026-03-27T12:30:00+00:00"
    assert _data_encoder(_HasDict()) == {"name": "Buddy"}
    assert _data_encoder(_DataWithIsoformat("iso-token")) == "iso-token"
    assert _data_encoder(_StringOnly()) == "string-only"


def test_performance_monitor_records_metrics_and_resets() -> None:
    """The monitor should track operations, cache stats, and reset state."""
    monitor = PerformanceMonitor()
    monitor.record_operation(0.2, success=True)
    monitor.record_operation(0.4, success=False)
    monitor.record_cache_hit()
    monitor.record_cache_hit()
    monitor.record_cache_miss()

    metrics = monitor.get_metrics()
    assert metrics["operations"] == 2
    assert metrics["errors"] == 1
    assert metrics["cache_hits"] == 2
    assert metrics["cache_misses"] == 1
    assert metrics["avg_operation_time"] == pytest.approx(0.3)
    assert metrics["cache_hit_rate"] == 66.7
    assert metrics["error_rate"] == 50.0
    assert metrics["last_cleanup"] is None
    assert metrics["recent_operations"] == 2

    monitor.reset_metrics()
    reset_metrics = monitor.get_metrics()
    assert reset_metrics["operations"] == 0
    assert reset_metrics["errors"] == 0
    assert reset_metrics["recent_operations"] == 0
    assert isinstance(reset_metrics["last_cleanup"], str)


@pytest.mark.asyncio
async def test_performance_monitor_decorator_handles_sync_and_async_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decorator should account for success, timeout, cancellation, and errors."""
    monitor = PerformanceMonitor()
    warnings: list[tuple[object, ...]] = []
    debug_logs: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        "custom_components.pawcontrol.helpers._LOGGER.warning",
        lambda *args: warnings.append(args),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.helpers._LOGGER.debug",
        lambda *args: debug_logs.append(args),
    )

    @monitor(timeout=1.0)
    def sync_ok(value: int) -> int:
        return value + 1

    @monitor(timeout=1.0)
    def sync_raises() -> None:
        raise RuntimeError("sync boom")

    @monitor(timeout=0.0, label="timed-async")
    async def async_timeout() -> None:
        await asyncio.sleep(0.01)

    @monitor(label="cancelled-async")
    async def async_cancelled() -> None:
        await asyncio.sleep(10)

    @monitor(label="error-async")
    async def async_raises() -> None:
        raise ValueError("async boom")

    @monitor(label="ok-async")
    async def async_ok() -> str:
        await asyncio.sleep(0)
        return "ok"

    assert sync_ok(4) == 5
    with pytest.raises(RuntimeError, match="sync boom"):
        sync_raises()

    with pytest.raises(TimeoutError):
        await async_timeout()

    cancelled_task = asyncio.create_task(async_cancelled())
    await asyncio.sleep(0)
    cancelled_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_task

    with pytest.raises(ValueError, match="async boom"):
        await async_raises()

    assert await async_ok() == "ok"

    metrics = monitor.get_metrics()
    assert metrics["operations"] == 6
    assert metrics["errors"] == 4

    assert any(
        entry[0] == "Operation %s timed out after %.2fs" and entry[1] == "timed-async"
        for entry in warnings
    )
    assert any(
        entry[0] == "Timeout %.2fs for synchronous operation %s is ignored"
        and entry[1] == 1.0
        for entry in debug_logs
    )
