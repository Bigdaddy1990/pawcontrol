"""Unit tests for config flow performance monitoring helpers."""

import logging

import pytest

from custom_components.pawcontrol.config_flow_monitor import (
    ConfigFlowPerformanceMonitor,
    timed_operation,
)


def test_record_operation_trims_history_after_threshold() -> None:
    """Operation history should be trimmed once it grows beyond 100 entries."""
    monitor = ConfigFlowPerformanceMonitor()

    for idx in range(101):
        monitor.record_operation("validation", float(idx))

    times = monitor.operation_times["validation"]
    assert len(times) == 50
    assert times[0] == 51.0
    assert times[-1] == 100.0


def test_get_stats_ignores_empty_operation_buckets() -> None:
    """Stats should not include operation keys with empty sample lists."""
    monitor = ConfigFlowPerformanceMonitor()
    monitor.operation_times["empty"] = []
    monitor.record_operation("active", 1.5)
    monitor.record_operation("active", 2.5)
    monitor.record_validation("host")

    stats = monitor.get_stats()

    assert "empty" not in stats["operations"]
    assert stats["operations"]["active"] == {
        "avg_time": 2.0,
        "max_time": 2.5,
        "count": 2,
    }
    assert stats["validations"] == {"host": 1}


@pytest.mark.asyncio
async def test_timed_operation_records_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timed operations should persist the measured duration in the shared monitor."""
    from custom_components.pawcontrol import config_flow_monitor as monitor_module

    monitor_module.config_flow_monitor = ConfigFlowPerformanceMonitor()

    timeline = [10.0, 10.4]

    def fake_monotonic() -> float:
        if timeline:
            return timeline.pop(0)
        return 10.4

    monkeypatch.setattr(monitor_module.time, "monotonic", fake_monotonic)

    async with timed_operation("import"):
        pass

    stats = monitor_module.config_flow_monitor.get_stats()
    assert stats["operations"]["import"]["count"] == 1
    assert stats["operations"]["import"]["avg_time"] == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_timed_operation_warns_for_slow_operations(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slow operations should emit a warning log entry."""
    from custom_components.pawcontrol import config_flow_monitor as monitor_module

    monitor_module.config_flow_monitor = ConfigFlowPerformanceMonitor()

    timeline = [5.0, 8.5]

    def fake_monotonic() -> float:
        if timeline:
            return timeline.pop(0)
        return 8.5

    monkeypatch.setattr(monitor_module.time, "monotonic", fake_monotonic)

    with caplog.at_level(logging.WARNING):
        async with timed_operation("discovery"):
            pass

    assert "Slow config flow operation: discovery took 3.50s" in caplog.text
