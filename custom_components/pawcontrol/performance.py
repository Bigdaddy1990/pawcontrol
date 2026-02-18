"""Performance monitoring and optimization utilities for PawControl.

This module provides decorators and utilities for tracking performance,
identifying bottlenecks, and optimizing critical code paths.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
import functools
import inspect
import logging
import time
from typing import Any, ParamSpec, TypeVar, cast

_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class PerformanceMetric:
    """Performance metric for a function.

    Attributes:
        name: Function name
        call_count: Number of calls
        total_time_ms: Total execution time in milliseconds
        min_time_ms: Minimum execution time
        max_time_ms: Maximum execution time
        recent_times: Recent execution times (last 100)
    """

    name: str
    call_count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float("inf")
    max_time_ms: float = 0.0
    recent_times: deque[float] = field(default_factory=lambda: deque(maxlen=100))

    @property
    def avg_time_ms(self) -> float:
        """Return average execution time."""
        return self.total_time_ms / self.call_count if self.call_count > 0 else 0.0

    @property
    def p95_time_ms(self) -> float:
        """Return 95th percentile execution time."""
        if not self.recent_times:
            return 0.0
        sorted_times = sorted(self.recent_times)
        index = int(len(sorted_times) * 0.95)
        return sorted_times[index] if index < len(sorted_times) else 0.0

    @property
    def p99_time_ms(self) -> float:
        """Return 99th percentile execution time."""
        if not self.recent_times:
            return 0.0
        sorted_times = sorted(self.recent_times)
        index = int(len(sorted_times) * 0.99)
        return sorted_times[index] if index < len(sorted_times) else 0.0

    def record(self, duration_ms: float) -> None:
        """Record an execution time.

        Args:
            duration_ms: Duration in milliseconds
        """
        self.call_count += 1
        self.total_time_ms += duration_ms
        self.min_time_ms = min(self.min_time_ms, duration_ms)
        self.max_time_ms = max(self.max_time_ms, duration_ms)
        self.recent_times.append(duration_ms)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "call_count": self.call_count,
            "total_time_ms": round(self.total_time_ms, 2),
            "avg_time_ms": round(self.avg_time_ms, 2),
            "min_time_ms": round(self.min_time_ms, 2),
            "max_time_ms": round(self.max_time_ms, 2),
            "p95_time_ms": round(self.p95_time_ms, 2),
            "p99_time_ms": round(self.p99_time_ms, 2),
        }


class PerformanceMonitor:
    """Global performance monitoring singleton."""

    _instance: PerformanceMonitor | None = None
    _metrics: dict[str, PerformanceMetric]
    _enabled: bool

    def __new__(cls) -> PerformanceMonitor:
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._metrics = {}
            cls._instance._enabled = True
        return cls._instance

    @classmethod
    def get_instance(cls) -> PerformanceMonitor:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def enable(self) -> None:
        """Enable performance monitoring."""
        self._enabled = True
        _LOGGER.info("Performance monitoring enabled")

    def disable(self) -> None:
        """Disable performance monitoring."""
        self._enabled = False
        _LOGGER.info("Performance monitoring disabled")

    def record(self, name: str, duration_ms: float) -> None:
        """Record a performance metric.

        Args:
            name: Metric name
            duration_ms: Duration in milliseconds
        """
        if not self._enabled:
            return
        if name not in self._metrics:
            self._metrics[name] = PerformanceMetric(name=name)
        self._metrics[name].record(duration_ms)

    def get_metric(self, name: str) -> PerformanceMetric | None:
        """Get metric by name.

        Args:
            name: Metric name

        Returns:
            PerformanceMetric or None
        """
        return self._metrics.get(name)

    def get_all_metrics(self) -> dict[str, PerformanceMetric]:
        """Return all metrics."""
        return dict(self._metrics)

    def get_slow_operations(
        self, threshold_ms: float = 100.0
    ) -> list[PerformanceMetric]:
        """Get operations slower than threshold.

        Args:
            threshold_ms: Threshold in milliseconds

        Returns:
            List of slow operations
        """
        return [
            metric
            for metric in self._metrics.values()
            if metric.avg_time_ms > threshold_ms
        ]

    def reset(self) -> None:
        """Reset all metrics."""
        self._metrics.clear()
        _LOGGER.info("Performance metrics reset")

    def get_summary(self) -> dict[str, Any]:
        """Get performance summary.

        Returns:
            Summary dictionary
        """
        if not self._metrics:
            return {
                "enabled": self._enabled,
                "metric_count": 0,
                "total_calls": 0,
            }

        total_calls = sum(m.call_count for m in self._metrics.values())
        total_time_ms = sum(m.total_time_ms for m in self._metrics.values())

        # Find slowest operations
        slowest = sorted(
            self._metrics.values(),
            key=lambda m: m.avg_time_ms,
            reverse=True,
        )[:5]

        # Find most called operations
        most_called = sorted(
            self._metrics.values(),
            key=lambda m: m.call_count,
            reverse=True,
        )[:5]

        return {
            "enabled": self._enabled,
            "metric_count": len(self._metrics),
            "total_calls": total_calls,
            "total_time_ms": round(total_time_ms, 2),
            "avg_call_time_ms": round(total_time_ms / total_calls, 2)
            if total_calls > 0
            else 0.0,
            "slowest_operations": [m.to_dict() for m in slowest],
            "most_called_operations": [m.to_dict() for m in most_called],
        }


# Global performance monitor instance
_performance_monitor = PerformanceMonitor.get_instance()


def track_performance(
    name: str | None = None,
    *,
    log_slow: bool = True,
    slow_threshold_ms: float = 100.0,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to track function performance.

    Args:
        name: Metric name (defaults to function name)
        log_slow: Whether to log slow operations
        slow_threshold_ms: Threshold for slow operation logging

    Returns:
        Decorated function

    Examples:
        >>> @track_performance()
        ... async def fetch_data():
        ...     await api.get_data()

        >>> @track_performance("custom_name", slow_threshold_ms=50.0)
        ... def calculate():
        ...     return sum(range(1000))
    """

    def decorator(
        func: Callable[P, T] | Callable[P, Awaitable[T]],
    ) -> Callable[P, T] | Callable[P, Awaitable[T]]:
        metric_name = name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start = time.perf_counter()
            try:
                async_func = cast(Callable[P, Awaitable[T]], func)
                result = await async_func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                _performance_monitor.record(metric_name, duration_ms)

                if log_slow and duration_ms > slow_threshold_ms:
                    _LOGGER.warning(
                        "Slow operation: %s took %.2fms (threshold: %.2fms)",
                        metric_name,
                        duration_ms,
                        slow_threshold_ms,
                    )

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start = time.perf_counter()
            try:
                sync_func = cast(Callable[P, T], func)
                return sync_func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                _performance_monitor.record(metric_name, duration_ms)

                if log_slow and duration_ms > slow_threshold_ms:
                    _LOGGER.warning(
                        "Slow operation: %s took %.2fms (threshold: %.2fms)",
                        metric_name,
                        duration_ms,
                        slow_threshold_ms,
                    )

        if inspect.iscoroutinefunction(func):
            return cast(Callable[P, Awaitable[T]], async_wrapper)
        return sync_wrapper

    return cast(Callable[[Callable[P, T]], Callable[P, T]], decorator)


def debounce(
    wait_seconds: float,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T | None]]]:
    """Decorator to debounce function calls.

    Only executes function after wait_seconds have passed since last call.

    Args:
        wait_seconds: Wait time in seconds

    Returns:
        Decorated function

    Examples:
        >>> @debounce(1.0)
        ... async def update_state():
        ...     await coordinator.async_request_refresh()
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T | None]]:
        last_call_time: float = 0.0
        pending_task: asyncio.Task[Any] | None = None

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:
            nonlocal last_call_time, pending_task
            current_time = time.time()
            # Cancel pending task if exists
            if pending_task and not pending_task.done():
                pending_task.cancel()

            # If enough time has passed, execute immediately
            if current_time - last_call_time >= wait_seconds:
                last_call_time = current_time
                return await func(*args, **kwargs)

            # Otherwise, schedule for later
            async def delayed_call() -> T:
                nonlocal last_call_time
                await asyncio.sleep(wait_seconds)
                last_call_time = time.time()
                return await func(*args, **kwargs)

            pending_task = asyncio.create_task(delayed_call())
            return None

        return async_wrapper

    return decorator


def throttle(
    calls_per_second: float,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to throttle function calls.

    Limits function to maximum calls_per_second rate.

    Args:
        calls_per_second: Maximum calls per second

    Returns:
        Decorated function

    Examples:
        >>> @throttle(2.0)  # Max 2 calls per second
        ... async def api_call():
        ...     return await api.fetch()
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        min_interval = 1.0 / calls_per_second
        last_call_time: float = 0.0
        lock = asyncio.Lock()

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            nonlocal last_call_time
            async with lock:
                current_time = time.time()
                time_since_last = current_time - last_call_time

                if time_since_last < min_interval:
                    await asyncio.sleep(min_interval - time_since_last)
                last_call_time = time.time()

            return await func(*args, **kwargs)

        return async_wrapper

    return decorator


def batch_calls(
    max_batch_size: int = 10,
    max_wait_ms: float = 100.0,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to batch function calls.

    Collects multiple calls and executes them in batches.

    Args:
        max_batch_size: Maximum batch size
        max_wait_ms: Maximum wait time in milliseconds

    Returns:
        Decorated function

    Examples:
        >>> @batch_calls(max_batch_size=10, max_wait_ms=100.0)
        ... async def update_entities(entity_ids: list[str]):
        ...     await coordinator.async_update_entities(entity_ids)
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        pending_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        batch_task: asyncio.Task[Any] | None = None
        lock = asyncio.Lock()

        async def process_batch() -> None:
            nonlocal pending_calls
            await asyncio.sleep(max_wait_ms / 1000)
            async with lock:
                if not pending_calls:
                    return
                # Combine all calls
                batch = pending_calls[:max_batch_size]
                pending_calls = pending_calls[max_batch_size:]

                # Execute batch
                for args, kwargs in batch:
                    try:
                        await func(*args, **kwargs)
                    except Exception as e:
                        _LOGGER.error("Batch call failed: %s", e)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> None:
            nonlocal batch_task
            async with lock:
                pending_calls.append((args, kwargs))

                # Start batch task if not running
                if batch_task is None or batch_task.done():
                    batch_task = asyncio.create_task(process_batch())

        return async_wrapper

    return decorator


# Performance helpers


def get_performance_summary() -> dict[str, Any]:
    """Get global performance summary.

    Returns:
        Performance summary dictionary
    """
    return _performance_monitor.get_summary()


def get_slow_operations(threshold_ms: float = 100.0) -> list[dict[str, Any]]:
    """Get slow operations.

    Args:
        threshold_ms: Threshold in milliseconds

    Returns:
        List of slow operations
    """
    slow_ops = _performance_monitor.get_slow_operations(threshold_ms)
    return [op.to_dict() for op in slow_ops]


def reset_performance_metrics() -> None:
    """Reset all performance metrics."""
    _performance_monitor.reset()


def enable_performance_monitoring() -> None:
    """Enable performance monitoring."""
    _performance_monitor.enable()


def disable_performance_monitoring() -> None:
    """Disable performance monitoring."""
    _performance_monitor.disable()


def capture_cache_diagnostics(runtime_data: object | None) -> dict[str, Any] | None:
    """Capture cache snapshots and repair telemetry when available."""
    if runtime_data is None:
        return None

    diagnostics: dict[str, Any] = {}
    data_manager = getattr(runtime_data, "data_manager", None)
    snapshot_method = getattr(data_manager, "cache_snapshots", None)
    if callable(snapshot_method):
        try:
            snapshots = snapshot_method()
        except Exception:  # pragma: no cover - diagnostics guard
            snapshots = None
        if isinstance(snapshots, Mapping):
            diagnostics["snapshots"] = dict(snapshots)
            summary_method = getattr(data_manager, "cache_repair_summary", None)
            if callable(summary_method):
                try:
                    summary = summary_method(
                        cast(dict[str, object], diagnostics["snapshots"])
                    )
                except TypeError:
                    try:
                        summary = summary_method()
                    except Exception:  # pragma: no cover - diagnostics guard
                        summary = None
                except Exception:  # pragma: no cover - diagnostics guard
                    summary = None
                if summary is not None:
                    diagnostics["repair_summary"] = summary
    for attr_name in ("cache", "_cache", "caches", "_caches"):
        cache = getattr(runtime_data, attr_name, None)
        if isinstance(cache, dict):
            diagnostics.setdefault("legacy", {})[attr_name] = {"entries": len(cache)}
    monitor = getattr(runtime_data, "performance_monitor", None)
    if monitor is not None and hasattr(monitor, "get_summary"):
        try:
            diagnostics["performance"] = monitor.get_summary()
        except Exception:  # pragma: no cover - defensive telemetry collection
            diagnostics["performance"] = {"status": "unavailable"}
    return diagnostics or None


@dataclass(slots=True)
class _TrackedPerformanceContext:
    """Mutable context object exposed by ``performance_tracker``."""

    metric_name: str
    started_at: float = field(default_factory=time.perf_counter)
    failure: str | None = None

    def mark_failure(self, error: Exception) -> None:
        """Record a failure for the current tracked operation."""
        self.failure = f"{error.__class__.__name__}: {error}"


def _ensure_runtime_performance_store(runtime_data: object) -> dict[str, Any]:
    """Return a mutable diagnostics bucket from runtime data."""
    store = getattr(runtime_data, "performance_stats", None)
    if isinstance(store, dict):
        return store

    store = getattr(runtime_data, "_performance_stats", None)
    if isinstance(store, dict):
        return store

    store = {}
    if hasattr(runtime_data, "performance_stats"):
        runtime_data.performance_stats = store
    elif hasattr(runtime_data, "_performance_stats"):
        runtime_data._performance_stats = store
    return store


@contextmanager
def performance_tracker(
    runtime_data: object,
    metric_name: str,
    *,
    max_samples: int = 50,
) -> Any:
    """Track maintenance execution metadata for diagnostics payloads."""
    context = _TrackedPerformanceContext(metric_name=metric_name)
    try:
        yield context
    finally:
        duration_ms = (time.perf_counter() - context.started_at) * 1000.0
        store = _ensure_runtime_performance_store(runtime_data)
        buckets = store.setdefault("performance_buckets", {})
        if not isinstance(buckets, dict):
            buckets = {}
            store["performance_buckets"] = buckets
        bucket = buckets.setdefault(
            metric_name, {"runs": 0, "failures": 0, "durations_ms": []}
        )
        if not isinstance(bucket, dict):
            bucket = {"runs": 0, "failures": 0, "durations_ms": []}
            buckets[metric_name] = bucket
        bucket["runs"] = int(bucket.get("runs", 0) or 0) + 1
        if context.failure:
            bucket["failures"] = int(bucket.get("failures", 0) or 0) + 1
        durations = bucket.get("durations_ms")
        if not isinstance(durations, list):
            durations = []
            bucket["durations_ms"] = durations
        durations.append(round(duration_ms, 2))
        if len(durations) > max_samples:
            del durations[:-max_samples]


def record_maintenance_result(
    runtime_data: object,
    *,
    task: str,
    status: str,
    message: str | None = None,
    diagnostics: dict[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
    max_entries: int = 50,
) -> None:
    """Store maintenance task outcomes on runtime diagnostics state."""
    store = _ensure_runtime_performance_store(runtime_data)
    history = store.setdefault("maintenance_results", [])
    if not isinstance(history, list):
        history = []
        store["maintenance_results"] = history

    legacy_history = store.get("maintenance_history")
    if isinstance(legacy_history, list):
        history = legacy_history
        store["maintenance_results"] = history
    else:
        store["maintenance_history"] = history

    entry: dict[str, Any] = {
        "task": task,
        "status": status,
        "recorded_at": datetime.now(UTC).isoformat(),
        "timestamp": time.time(),
    }
    if message is not None:
        entry["message"] = message

    if diagnostics is not None:
        entry["diagnostics"] = (
            dict(diagnostics) if isinstance(diagnostics, Mapping) else diagnostics
        )
    if metadata is not None:
        serialised_metadata = dict(metadata)
        entry["metadata"] = serialised_metadata
        if (
            task != "coordinator_maintenance"
            and isinstance(entry.get("diagnostics"), dict)
            and "metadata" not in entry["diagnostics"]
        ):
            entry["diagnostics"]["metadata"] = serialised_metadata

    if metadata is not None:
        entry["metadata"] = dict(metadata)

    if details is not None:
        entry["details"] = dict(details)

    history.append(entry)
    if len(history) > max_entries:
        del history[:-max_entries]

    store["last_maintenance_result"] = entry
