"""Unit coverage for the PawControl data manager instrumentation."""

from __future__ import annotations

from collections import deque
from typing import Any

import pytest
from custom_components.pawcontrol.coordinator_support import CoordinatorMetrics
from custom_components.pawcontrol.data_manager import PawControlDataManager


class StubDataManager(PawControlDataManager):
    """Minimal data manager that exercises visitor profiling without HA deps."""

    def __init__(self) -> None:
        self._metrics = {
            "operations": 0,
            "saves": 0,
            "errors": 0,
            "last_cleanup": None,
            "performance_score": 100.0,
        }
        self._visitor_timings: deque[float] = deque(maxlen=50)
        self._metrics_sink: CoordinatorMetrics | None = None
        self.saved_payload: dict[str, Any] | None = None

    async def _get_namespace_data(self, namespace: str) -> dict[str, Any]:
        """Return empty namespace data for tests."""

        assert namespace == "visitor_mode"
        return {}

    async def _save_namespace(self, namespace: str, data: dict[str, Any]) -> None:
        """Capture writes instead of hitting Home Assistant storage."""

        assert namespace == "visitor_mode"
        self.saved_payload = data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_set_visitor_mode_records_metrics() -> None:
    """Visitor workflows should record runtime samples and update metrics."""

    manager = StubDataManager()
    metrics_sink = CoordinatorMetrics()
    manager.set_metrics_sink(metrics_sink)

    await manager.async_set_visitor_mode("buddy", {"enabled": True})

    assert manager.saved_payload == {"buddy": {"enabled": True}}
    assert manager._visitor_timings  # at least one sample captured
    assert manager._metrics["visitor_mode_last_runtime_ms"] < 3.0
    assert manager._metrics["visitor_mode_avg_runtime_ms"] < 3.0
    assert metrics_sink.visitor_mode_timings
    assert metrics_sink.average_visitor_runtime_ms < 3.0
