"""Helpers for tracking performance metrics across PawControl tasks."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal

from homeassistant.util import dt as dt_util

from .coordinator_support import ensure_cache_repair_aggregate
from .types import CacheDiagnosticsMap, CacheDiagnosticsSnapshot

if TYPE_CHECKING:
    from .types import (
        CacheDiagnosticsCapture,
        MaintenanceExecutionDiagnostics,
        MaintenanceExecutionResult,
        PawControlRuntimeData,
    )


_LOGGER = logging.getLogger(__name__)

_EMPTY_DICT: dict[str, Any] = {}


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


def capture_cache_diagnostics(
    runtime_data: Any,
) -> CacheDiagnosticsCapture | None:
    """Return cache diagnostics snapshots when available.

    This helper normalises interactions with the data manager so callers can
    safely surface cache telemetry without duplicating the capture logic.
    """

    if runtime_data is None:
        return None

    data_manager = getattr(runtime_data, "data_manager", None)
    if data_manager is None:
        return None

    snapshots_method = getattr(data_manager, "cache_snapshots", None)
    if not callable(snapshots_method):
        return None

    try:
        snapshots = snapshots_method()
    except Exception as err:  # pragma: no cover - diagnostics guard
        _LOGGER.debug("Failed to capture cache snapshots: %s", err)
        return None

    if not isinstance(snapshots, Mapping):
        return None

    normalised: CacheDiagnosticsMap = {}
    for name, payload in snapshots.items():
        if not isinstance(name, str) or not name:
            continue
        if isinstance(payload, CacheDiagnosticsSnapshot):
            normalised[name] = payload
        elif isinstance(payload, Mapping):
            snapshot_obj = CacheDiagnosticsSnapshot.from_mapping(payload)
            normalised[name] = snapshot_obj
        else:
            snapshot_obj = CacheDiagnosticsSnapshot(error=str(payload))
            normalised[name] = snapshot_obj

    if not normalised:
        return None

    capture: CacheDiagnosticsCapture = {"snapshots": normalised}

    summary_method = getattr(data_manager, "cache_repair_summary", None)
    if callable(summary_method):
        try:
            summary = summary_method(normalised)
        except Exception as err:  # pragma: no cover - diagnostics guard
            _LOGGER.debug("Skipping cache repair summary capture: %s", err)
        else:
            resolved_summary = ensure_cache_repair_aggregate(summary)
            if resolved_summary is not None:
                capture["repair_summary"] = resolved_summary

    return capture


def record_maintenance_result(
    runtime_data: Any,
    *,
    task: str,
    status: Literal["success", "error"],
    message: str | None = None,
    diagnostics: CacheDiagnosticsCapture | None = None,
    metadata: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    """Store structured maintenance telemetry in runtime performance stats."""

    if runtime_data is None or not isinstance(task, str) or not task:
        return

    performance_stats = getattr(runtime_data, "performance_stats", None)
    if not isinstance(performance_stats, dict):
        return

    result: MaintenanceExecutionResult = {
        "task": task,
        "status": status,
        "recorded_at": dt_util.utcnow().isoformat(),
    }

    if message:
        result["message"] = message

    diagnostics_payload: MaintenanceExecutionDiagnostics | None = None
    if diagnostics is not None:
        diagnostics_payload = {"cache": diagnostics}

    if metadata is not None:
        metadata_payload = dict(metadata) if metadata is not _EMPTY_DICT else {}
        if metadata_payload:
            if diagnostics_payload is None:
                diagnostics_payload = {"metadata": metadata_payload}
            else:
                diagnostics_payload["metadata"] = metadata_payload

    if diagnostics_payload:
        result["diagnostics"] = diagnostics_payload

    if details is not None:
        detail_payload = {k: v for k, v in dict(details).items() if v is not None}
        if detail_payload:
            result["details"] = detail_payload

    results = performance_stats.setdefault("maintenance_results", [])
    results.append(result)
    performance_stats["last_maintenance_result"] = result
