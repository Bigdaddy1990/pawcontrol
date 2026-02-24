"""Tests for config flow performance monitoring helpers."""

from __future__ import annotations

from collections.abc import Iterator
import logging
from unittest.mock import patch

import pytest

from custom_components.pawcontrol.config_flow_monitor import (
    ConfigFlowPerformanceMonitor,
    timed_operation,
)


@pytest.fixture
def monitor() -> Iterator[ConfigFlowPerformanceMonitor]:
    """Provide an isolated monitor instance for each test."""
    isolated_monitor = ConfigFlowPerformanceMonitor()
    with patch(
        "custom_components.pawcontrol.config_flow_monitor.config_flow_monitor",
        isolated_monitor,
    ):
        yield isolated_monitor


def test_record_operation_trims_large_samples(
    monitor: ConfigFlowPerformanceMonitor,
) -> None:
    """Keep only the latest 50 entries when the operation history grows too large."""
    for index in range(101):
        monitor.record_operation("validate", float(index))

    assert len(monitor.operation_times["validate"]) == 50
    assert monitor.operation_times["validate"] == [float(i) for i in range(51, 101)]


def test_get_stats_skips_empty_operation_buckets() -> None:
    """Ignore operation buckets that have no timing values."""
    monitor = ConfigFlowPerformanceMonitor()
    monitor.operation_times["empty"] = []
    monitor.record_validation("schema")

    stats = monitor.get_stats()

    assert stats["operations"] == {}
    assert stats["validations"] == {"schema": 1}


def test_get_stats_calculates_operation_metrics() -> None:
    """Aggregate average, max and count for populated operation timings."""
    monitor = ConfigFlowPerformanceMonitor()
    monitor.record_operation("step", 1.0)
    monitor.record_operation("step", 2.0)

    stats = monitor.get_stats()

    assert stats["operations"]["step"] == {"avg_time": 1.5, "max_time": 2.0, "count": 2}


@pytest.mark.asyncio
async def test_timed_operation_records_duration_without_warning(
    monitor: ConfigFlowPerformanceMonitor,
) -> None:
    """Record normal durations and do not emit a warning under the slow threshold."""
    with (
        patch(
            "custom_components.pawcontrol.config_flow_monitor.time.monotonic",
            side_effect=[10.0, 11.5],
        ),
        patch(
            "custom_components.pawcontrol.config_flow_monitor._LOGGER.warning"
        ) as warning_mock,
    ):
        async with timed_operation("fast-op"):
            pass

    assert monitor.operation_times["fast-op"] == [1.5]
    warning_mock.assert_not_called()


@pytest.mark.asyncio
async def test_timed_operation_logs_warning_for_slow_calls(
    monitor: ConfigFlowPerformanceMonitor,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Emit a warning when an operation takes longer than the accepted threshold."""
    caplog.set_level(logging.WARNING)

    with patch(
        "custom_components.pawcontrol.config_flow_monitor.time.monotonic",
        side_effect=[100.0, 102.5],
    ):
        async with timed_operation("slow-op"):
            pass

    assert monitor.operation_times["slow-op"] == [2.5]
    assert "Slow config flow operation: slow-op took 2.50s" in caplog.text
