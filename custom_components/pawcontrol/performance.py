"""Helpers for tracking performance metrics across PawControl tasks."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .types import PawControlRuntimeData


@dataclass(slots=True)
class PerformanceResult:
    """State container passed to tracked blocks for manual overrides."""

    success: bool = True
    error: Exception | None = None

    def mark_failure(self, error: Exception | None = None) -> None:
        """Mark the tracked block as failed without raising an exception."""

        self.success = False
        self.error = error


@contextmanager
def performance_tracker(
    runtime_data: PawControlRuntimeData | None,
    bucket_name: str,
    *,
    max_samples: int = 50,
) -> Iterator[PerformanceResult]:
    """Context manager that records execution metrics for integration tasks."""

    result = PerformanceResult()

    if runtime_data is None:
        yield result
        return

    bucket = runtime_data.performance_stats.setdefault(
        bucket_name,
        {
            "runs": 0,
            "failures": 0,
            "durations_ms": [],
            "average_ms": 0.0,
            "last_run": None,
            "last_error": None,
        },
    )

    start = perf_counter()

    try:
        yield result
    except Exception as err:
        result.mark_failure(err)
        raise
    finally:
        duration_ms = max((perf_counter() - start) * 1000.0, 0.0)
        durations = bucket.setdefault("durations_ms", [])
        durations.append(round(duration_ms, 3))
        if len(durations) > max_samples:
            del durations[:-max_samples]

        bucket["runs"] = bucket.get("runs", 0) + 1

        if result.success:
            bucket["last_run"] = dt_util.utcnow().isoformat()
        else:
            bucket["failures"] = bucket.get("failures", 0) + 1
            bucket["last_error"] = (
                f"{result.error.__class__.__name__}: {result.error}"
                if result.error
                else "unknown"
            )

        if durations:
            bucket["average_ms"] = round(sum(durations) / len(durations), 3)
