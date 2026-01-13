"""Performance monitoring helpers for the PawControl config flow."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .types import ConfigFlowOperationMetricsMap, ConfigFlowPerformanceStats

_LOGGER = logging.getLogger(__name__)


class ConfigFlowPerformanceMonitor:
    """Monitor performance of config flow operations."""

    def __init__(self) -> None:
        """Initialise empty metric buckets for tracking config flow performance."""
        self.operation_times: dict[str, list[float]] = {}
        self.validation_counts: dict[str, int] = {}

    def record_operation(self, operation: str, duration: float) -> None:
        """Record timing information for an operation."""

        times = self.operation_times.setdefault(operation, [])
        times.append(duration)

        # Keep cache size bounded to avoid memory bloat
        if len(times) > 100:
            self.operation_times[operation] = times[-50:]

    def record_validation(self, validation_type: str) -> None:
        """Record a validation invocation."""

        self.validation_counts[validation_type] = (
            self.validation_counts.get(validation_type, 0) + 1
        )

    def get_stats(self) -> ConfigFlowPerformanceStats:
        """Return aggregated statistics for diagnostics."""

        operations: ConfigFlowOperationMetricsMap = {}
        for operation, times in self.operation_times.items():
            if not times:
                continue
            operations[operation] = {
                'avg_time': sum(times) / len(times),
                'max_time': max(times),
                'count': len(times),
            }

        return ConfigFlowPerformanceStats(
            operations=operations,
            validations=self.validation_counts.copy(),
        )


config_flow_monitor = ConfigFlowPerformanceMonitor()


@asynccontextmanager
async def timed_operation(operation_name: str) -> AsyncIterator[None]:
    """Async context manager that records operation duration."""

    start_time = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start_time
        config_flow_monitor.record_operation(operation_name, duration)
        if duration > 2.0:
            _LOGGER.warning(
                'Slow config flow operation: %s took %.2fs',
                operation_name,
                duration,
            )
