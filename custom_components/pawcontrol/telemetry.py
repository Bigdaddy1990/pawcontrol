"""Telemetry helpers shared between PawControl services and coordinators."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, cast

from homeassistant.util import dt as dt_util

from .types import (
    BoolCoercionMetrics,
    BoolCoercionSample,
    BoolCoercionSummary,
    CoordinatorResilienceSummary,
    DoorSensorPersistenceFailure,
    PawControlRuntimeData,
    ReconfigureTelemetry,
    ReconfigureTelemetrySummary,
    RuntimePerformanceStats,
)

_BOOL_COERCION_METRICS: BoolCoercionMetrics = {
    "total": 0,
    "defaulted": 0,
    "fallback": 0,
    "reset_count": 0,
    "type_counts": {},
    "reason_counts": {},
    "samples": [],
    "first_seen": None,
    "last_seen": None,
    "active_window_seconds": None,
    "last_reset": None,
    "last_reason": None,
    "last_value_type": None,
    "last_value_repr": None,
    "last_result": None,
    "last_default": None,
}
_BOOL_COERCION_SAMPLE_LIMIT = 10


def _safe_repr(value: Any, *, limit: int = 80) -> str:
    """Return a short, exception-safe representation of ``value``."""

    if value is None:
        return "None"

    try:
        rendered = repr(value)
    except Exception:  # pragma: no cover - defensive fallback
        rendered = object.__repr__(value)

    if len(rendered) > limit:
        return f"{rendered[: limit - 1]}…"
    return rendered


def _calculate_active_window_seconds(
    first_seen: str | None, last_seen: str | None
) -> float | None:
    """Return the duration between the first and last coercions when available."""

    if not first_seen or not last_seen:
        return None

    first_dt = dt_util.parse_datetime(first_seen)
    last_dt = dt_util.parse_datetime(last_seen)
    if first_dt is None or last_dt is None:
        return None

    window = (last_dt - first_dt).total_seconds()
    if window < 0:
        return 0.0
    return window


def get_runtime_performance_stats(
    runtime_data: PawControlRuntimeData | None,
) -> RuntimePerformanceStats | None:
    """Return runtime performance stats when present and mutable."""

    if runtime_data is None:
        return None

    performance_stats = getattr(runtime_data, "performance_stats", None)
    if not isinstance(performance_stats, MutableMapping):
        return None

    return cast(RuntimePerformanceStats, performance_stats)


def ensure_runtime_performance_stats(
    runtime_data: PawControlRuntimeData,
) -> RuntimePerformanceStats:
    """Return a mutable runtime performance stats mapping, initialising if needed."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is not None:
        return performance_stats

    runtime_data.performance_stats = cast(RuntimePerformanceStats, {})
    return runtime_data.performance_stats


def record_bool_coercion_event(
    *, value: Any, default: bool, result: bool, reason: str
) -> None:
    """Record details about a boolean coercion for diagnostics."""

    metrics = _BOOL_COERCION_METRICS
    metrics["total"] = metrics.get("total", 0) + 1

    iso_timestamp = dt_util.utcnow().isoformat()
    if metrics.get("first_seen") is None:
        metrics["first_seen"] = iso_timestamp
    metrics["last_seen"] = iso_timestamp
    if metrics.get("last_reset") is None:
        metrics["last_reset"] = iso_timestamp

    if reason in {"none", "blank_string"}:
        metrics["defaulted"] = metrics.get("defaulted", 0) + 1
    if reason == "fallback":
        metrics["fallback"] = metrics.get("fallback", 0) + 1

    value_type = type(value).__name__ if value is not None else "NoneType"
    value_repr = _safe_repr(value)
    type_counts = metrics.setdefault("type_counts", {})
    type_counts[value_type] = type_counts.get(value_type, 0) + 1

    reason_counts = metrics.setdefault("reason_counts", {})
    reason_counts[reason] = reason_counts.get(reason, 0) + 1

    samples = metrics.setdefault("samples", [])
    if len(samples) < _BOOL_COERCION_SAMPLE_LIMIT:
        samples.append(
            {
                "value_type": value_type,
                "value_repr": value_repr,
                "default": default,
                "result": result,
                "reason": reason,
            }
        )

    metrics["last_reason"] = reason
    metrics["last_value_type"] = value_type
    metrics["last_value_repr"] = value_repr
    metrics["last_result"] = bool(result)
    metrics["last_default"] = bool(default)


def get_bool_coercion_metrics() -> BoolCoercionMetrics:
    """Return a defensive copy of the collected bool coercion metrics."""

    first_seen = _BOOL_COERCION_METRICS.get("first_seen")
    last_seen = _BOOL_COERCION_METRICS.get("last_seen")
    snapshot: BoolCoercionMetrics = {
        "total": int(_BOOL_COERCION_METRICS.get("total", 0)),
        "defaulted": int(_BOOL_COERCION_METRICS.get("defaulted", 0)),
        "fallback": int(_BOOL_COERCION_METRICS.get("fallback", 0)),
        "reset_count": int(_BOOL_COERCION_METRICS.get("reset_count", 0)),
        "type_counts": dict(_BOOL_COERCION_METRICS.get("type_counts", {})),
        "reason_counts": dict(_BOOL_COERCION_METRICS.get("reason_counts", {})),
        "samples": [
            {
                "value_type": sample["value_type"],
                "value_repr": sample["value_repr"],
                "default": bool(sample["default"]),
                "result": bool(sample["result"]),
                "reason": sample["reason"],
            }
            for sample in _BOOL_COERCION_METRICS.get("samples", [])
        ],
        "first_seen": first_seen,
        "last_seen": last_seen,
        "active_window_seconds": _calculate_active_window_seconds(
            first_seen, last_seen
        ),
        "last_reset": _BOOL_COERCION_METRICS.get("last_reset"),
        "last_reason": _BOOL_COERCION_METRICS.get("last_reason"),
        "last_value_type": _BOOL_COERCION_METRICS.get("last_value_type"),
        "last_value_repr": _BOOL_COERCION_METRICS.get("last_value_repr"),
        "last_result": _BOOL_COERCION_METRICS.get("last_result"),
        "last_default": _BOOL_COERCION_METRICS.get("last_default"),
    }
    return snapshot


def reset_bool_coercion_metrics() -> None:
    """Reset collected bool coercion metrics (primarily for testing)."""

    reset_count = int(_BOOL_COERCION_METRICS.get("reset_count", 0)) + 1
    iso_timestamp = dt_util.utcnow().isoformat()

    _BOOL_COERCION_METRICS["total"] = 0
    _BOOL_COERCION_METRICS["defaulted"] = 0
    _BOOL_COERCION_METRICS["fallback"] = 0
    _BOOL_COERCION_METRICS["reset_count"] = reset_count
    _BOOL_COERCION_METRICS["type_counts"] = {}
    _BOOL_COERCION_METRICS["reason_counts"] = {}
    _BOOL_COERCION_METRICS["samples"] = []
    _BOOL_COERCION_METRICS["first_seen"] = None
    _BOOL_COERCION_METRICS["last_seen"] = None
    _BOOL_COERCION_METRICS["active_window_seconds"] = None
    _BOOL_COERCION_METRICS["last_reset"] = iso_timestamp
    _BOOL_COERCION_METRICS["last_reason"] = None
    _BOOL_COERCION_METRICS["last_value_type"] = None
    _BOOL_COERCION_METRICS["last_value_repr"] = None
    _BOOL_COERCION_METRICS["last_result"] = None
    _BOOL_COERCION_METRICS["last_default"] = None


def summarise_bool_coercion_metrics(*, sample_limit: int = 5) -> BoolCoercionSummary:
    """Return a condensed bool coercion snapshot for observability exports."""

    metrics = get_bool_coercion_metrics()
    reason_counts_raw = metrics.get("reason_counts", {})
    type_counts_raw = metrics.get("type_counts", {})

    reason_counts = (
        {key: int(reason_counts_raw[key]) for key in sorted(reason_counts_raw)}
        if isinstance(reason_counts_raw, Mapping)
        else {}
    )
    type_counts = (
        {key: int(type_counts_raw[key]) for key in sorted(type_counts_raw)}
        if isinstance(type_counts_raw, Mapping)
        else {}
    )

    samples = metrics.get("samples", [])
    if not isinstance(samples, Sequence):
        samples_list: list[BoolCoercionSample] = []
    else:
        limited_samples = tuple(samples)[: max(0, sample_limit)]
        samples_list = [
            {
                "value_type": sample.get("value_type", ""),
                "value_repr": sample.get("value_repr", ""),
                "default": bool(sample.get("default", False)),
                "result": bool(sample.get("result", False)),
                "reason": sample.get("reason", ""),
            }
            for sample in limited_samples
            if isinstance(sample, Mapping)
        ]

    summary: BoolCoercionSummary = {
        "recorded": bool(metrics.get("total", 0) or metrics.get("reset_count", 0)),
        "total": int(metrics.get("total", 0)),
        "defaulted": int(metrics.get("defaulted", 0)),
        "fallback": int(metrics.get("fallback", 0)),
        "reset_count": int(metrics.get("reset_count", 0)),
        "first_seen": metrics.get("first_seen"),
        "last_seen": metrics.get("last_seen"),
        "last_reset": metrics.get("last_reset"),
        "active_window_seconds": metrics.get("active_window_seconds"),
        "last_reason": metrics.get("last_reason"),
        "last_value_type": metrics.get("last_value_type"),
        "last_value_repr": metrics.get("last_value_repr"),
        "last_result": metrics.get("last_result"),
        "last_default": metrics.get("last_default"),
        "reason_counts": reason_counts,
        "type_counts": type_counts,
        "samples": samples_list,
    }

    return summary


def get_runtime_bool_coercion_summary(
    runtime_data: PawControlRuntimeData | None,
) -> BoolCoercionSummary | None:
    """Return the cached bool coercion summary when stored in runtime stats."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is None:
        return None

    summary = performance_stats.get("bool_coercion_summary")
    if not isinstance(summary, Mapping):
        return None

    return cast(BoolCoercionSummary, dict(summary))


def update_runtime_bool_coercion_summary(
    runtime_data: PawControlRuntimeData | None,
    *,
    sample_limit: int = 5,
) -> BoolCoercionSummary:
    """Persist the latest bool coercion summary to runtime performance stats."""

    summary = summarise_bool_coercion_metrics(sample_limit=sample_limit)

    if runtime_data is not None:
        performance_stats = ensure_runtime_performance_stats(runtime_data)
        performance_stats["bool_coercion_summary"] = cast(
            BoolCoercionSummary, dict(summary)
        )
    return summary


def _as_int(value: Any) -> int:
    """Return ``value`` coerced to an integer when possible."""

    try:
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _as_list(value: Any) -> list[str]:
    """Return ``value`` normalised as a list of strings."""

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [str(item) for item in value if item is not None]
    if value is None:
        return []
    return [str(value)]


def summarise_reconfigure_options(
    options: Mapping[str, Any] | MutableMapping[str, Any] | None,
) -> ReconfigureTelemetrySummary | None:
    """Build a condensed telemetry payload from config-entry options."""

    if not isinstance(options, Mapping):
        return None

    telemetry_raw = options.get("reconfigure_telemetry")
    if not isinstance(telemetry_raw, Mapping):
        return None

    telemetry = cast(ReconfigureTelemetry, telemetry_raw)

    warnings = _as_list(telemetry.get("compatibility_warnings"))
    merge_notes = _as_list(telemetry.get("merge_notes"))
    health_summary = telemetry.get("health_summary")
    healthy = True
    health_issues: list[str] = []
    health_warnings: list[str] = []
    if isinstance(health_summary, Mapping):
        healthy = bool(health_summary.get("healthy", True))
        health_issues = _as_list(health_summary.get("issues"))
        health_warnings = _as_list(health_summary.get("warnings"))

    timestamp = str(telemetry.get("timestamp") or options.get("last_reconfigure") or "")
    requested_profile = str(telemetry.get("requested_profile", ""))
    previous_profile = str(
        telemetry.get("previous_profile") or options.get("previous_profile") or ""
    )

    summary: ReconfigureTelemetrySummary = {
        "timestamp": timestamp,
        "requested_profile": requested_profile,
        "previous_profile": previous_profile,
        "dogs_count": _as_int(telemetry.get("dogs_count")),
        "estimated_entities": _as_int(telemetry.get("estimated_entities")),
        "version": _as_int(telemetry.get("version")),
        "warnings": warnings,
        "warning_count": len(warnings),
        "merge_notes": merge_notes,
        "merge_note_count": len(merge_notes),
        "healthy": healthy,
        "health_issues": health_issues,
        "health_issue_count": len(health_issues),
        "health_warnings": health_warnings,
        "health_warning_count": len(health_warnings),
    }

    return summary


def get_runtime_reconfigure_summary(
    runtime_data: PawControlRuntimeData,
) -> ReconfigureTelemetrySummary | None:
    """Return the cached reconfigure summary stored in performance stats."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is None:
        return None

    summary = performance_stats.get("reconfigure_summary")
    if not isinstance(summary, Mapping):
        return None

    return cast(ReconfigureTelemetrySummary, dict(summary))


def update_runtime_reconfigure_summary(
    runtime_data: PawControlRuntimeData,
) -> ReconfigureTelemetrySummary | None:
    """Synchronise runtime reconfigure telemetry with the active config entry."""

    coordinator = getattr(runtime_data, "coordinator", None)
    entry = getattr(coordinator, "config_entry", None)
    options = getattr(entry, "options", None)

    summary = summarise_reconfigure_options(options)

    performance_stats = ensure_runtime_performance_stats(runtime_data)

    if summary is None:
        performance_stats.pop("reconfigure_summary", None)
        return None

    performance_stats["reconfigure_summary"] = summary
    return summary


def get_runtime_resilience_summary(
    runtime_data: PawControlRuntimeData,
) -> CoordinatorResilienceSummary | None:
    """Return the cached resilience summary from performance statistics."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is None:
        return None

    summary = performance_stats.get("resilience_summary")
    if not isinstance(summary, Mapping):
        return None

    return cast(CoordinatorResilienceSummary, dict(summary))


def update_runtime_resilience_summary(
    runtime_data: PawControlRuntimeData,
    summary: CoordinatorResilienceSummary | None,
) -> CoordinatorResilienceSummary | None:
    """Persist the latest resilience summary in runtime performance stats."""

    performance_stats = ensure_runtime_performance_stats(runtime_data)

    if summary is None:
        performance_stats.pop("resilience_summary", None)
        return None

    performance_stats["resilience_summary"] = cast(
        CoordinatorResilienceSummary, dict(summary)
    )
    return summary


def record_door_sensor_persistence_failure(
    runtime_data: PawControlRuntimeData | None,
    *,
    dog_id: str,
    dog_name: str | None = None,
    door_sensor: str | None = None,
    settings: Mapping[str, Any] | None = None,
    error: Exception | str | None = None,
    limit: int = 10,
) -> DoorSensorPersistenceFailure | None:
    """Append door sensor persistence failure telemetry to runtime stats."""

    if runtime_data is None:
        return None

    performance_stats = ensure_runtime_performance_stats(runtime_data)

    failures_raw = performance_stats.get("door_sensor_failures")
    if isinstance(failures_raw, list):
        failures = failures_raw
    elif isinstance(failures_raw, Sequence):
        failures = [dict(entry) for entry in failures_raw if isinstance(entry, Mapping)]
    else:
        failures = []

    failure: DoorSensorPersistenceFailure = {
        "dog_id": dog_id,
        "recorded_at": dt_util.utcnow().isoformat(),
    }

    if dog_name is not None:
        failure["dog_name"] = dog_name

    if door_sensor is not None:
        failure["door_sensor"] = door_sensor

    if settings is not None:
        failure["settings"] = dict(settings)

    if error is not None:
        failure["error"] = str(error)

    failures.append(failure)

    if limit > 0 and len(failures) > limit:
        del failures[:-limit]

    performance_stats["door_sensor_failures"] = failures
    performance_stats["door_sensor_failure_count"] = len(failures)
    performance_stats["last_door_sensor_failure"] = failure

    error_history = getattr(runtime_data, "error_history", None)
    if isinstance(error_history, list):
        error_entry: dict[str, Any] = {
            "timestamp": failure["recorded_at"],
            "source": "door_sensor_persistence",
            "dog_id": dog_id,
        }
        if door_sensor is not None:
            error_entry["door_sensor"] = door_sensor
        if error is not None:
            error_entry["error"] = str(error)
        error_history.append(error_entry)
        if len(error_history) > 50:
            del error_history[:-50]

    return failure
