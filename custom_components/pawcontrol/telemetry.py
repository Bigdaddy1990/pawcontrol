"""Telemetry helpers shared between PawControl services and coordinators.

Simplified to keep only lightweight state tracking.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from homeassistant.util import dt as dt_util

from .types import (
  BoolCoercionMetrics,
  BoolCoercionSample,
  BoolCoercionSummary,
  CoordinatorResilienceDiagnostics,
  CoordinatorResilienceSummary,
  DoorSensorFailureSummary,
  DoorSensorPersistenceFailure,
  EntityFactoryGuardEvent,
  EntityFactoryGuardMetrics,
  EntityFactoryGuardStabilityTrend,
  PawControlRuntimeData,
  ReconfigureTelemetrySummary,
  RuntimeStoreHealthAssessment,
  RuntimeStoreHealthHistory,
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


def _safe_repr(value: Any, *, limit: int = 80) -> str:
  rendered = repr(value)
  return rendered if len(rendered) <= limit else f"{rendered[: limit - 1]}…"


def _calculate_active_window_seconds(
  first_seen: datetime | None,
  last_seen: datetime | None,
) -> float | None:
  if first_seen is None or last_seen is None:
    return None
  return max((last_seen - first_seen).total_seconds(), 0.0)


def get_runtime_performance_stats(
  runtime_data: PawControlRuntimeData | None,
) -> RuntimePerformanceStats | None:
  if runtime_data is None:
    return None
  performance_stats = getattr(runtime_data, "performance_stats", None)
  if not isinstance(performance_stats, dict):
    return None
  return cast(RuntimePerformanceStats, performance_stats)


def ensure_runtime_performance_stats(
  runtime_data: PawControlRuntimeData,
) -> RuntimePerformanceStats:
  if runtime_data.performance_stats is None:
    runtime_data.performance_stats = {}
  return cast(RuntimePerformanceStats, runtime_data.performance_stats)


def get_runtime_entity_factory_guard_metrics(
  runtime_data: PawControlRuntimeData,
) -> EntityFactoryGuardMetrics | None:
  stats = get_runtime_performance_stats(runtime_data)
  if stats is None:
    return None
  payload = stats.get("entity_factory_guard")
  return cast(EntityFactoryGuardMetrics, payload) if isinstance(payload, dict) else None


def get_runtime_store_health(
  runtime_data: PawControlRuntimeData | None,
) -> RuntimeStoreHealthAssessment | None:
  stats = get_runtime_performance_stats(runtime_data)
  if stats is None:
    return None
  payload = stats.get("runtime_store_health")
  if not isinstance(payload, Mapping):
    return None
  assessment = payload.get("assessment")
  return (
    cast(RuntimeStoreHealthAssessment, assessment)
    if isinstance(assessment, dict)
    else cast(RuntimeStoreHealthAssessment, payload)
  )


def update_runtime_store_health(
  runtime_data: PawControlRuntimeData | None,
  snapshot: RuntimeStoreHealthAssessment,
  *,
  record_event: bool = True,
) -> RuntimeStoreHealthHistory | None:
  if runtime_data is None:
    return None

  del record_event
  stats = ensure_runtime_performance_stats(runtime_data)
  previous = stats.get("runtime_store_health")
  checks = 0
  divergence_events = 0
  if isinstance(previous, Mapping):
    checks = _as_int(previous.get("checks"))
    divergence_events = _as_int(previous.get("divergence_events"))

  checks += 1
  divergence_detected = bool(snapshot.get("divergence_detected"))
  if divergence_detected:
    divergence_events += 1

  history: RuntimeStoreHealthHistory = {
    "schema_version": 1,
    "checks": checks,
    "divergence_events": divergence_events,
    "last_checked": str(snapshot.get("last_checked", "")) or None,
    "last_status": cast(Any, snapshot.get("last_status")),
    "last_entry_status": cast(Any, snapshot.get("last_entry_status")),
    "last_store_status": cast(Any, snapshot.get("last_store_status")),
    "divergence_detected": divergence_detected,
    "assessment": snapshot,
  }
  stats["runtime_store_health"] = history
  return history


def update_runtime_entity_factory_guard_metrics(
  runtime_data: PawControlRuntimeData,
  *,
  runtime_floor: float,
  actual_duration: float,
  event: EntityFactoryGuardEvent,
  baseline_floor: float,
  max_floor: float,
  enforce_min_runtime: bool,
) -> EntityFactoryGuardMetrics:
  stats = ensure_runtime_performance_stats(runtime_data)
  payload: EntityFactoryGuardMetrics = {
    "runtime_floor": max(runtime_floor, 0.0),
    "actual_duration": max(actual_duration, 0.0),
    "event": event,
    "baseline_floor": max(baseline_floor, 0.0),
    "max_floor": max(max_floor, 0.0),
    "enforce_min_runtime": enforce_min_runtime,
    "stability_trend": cast(EntityFactoryGuardStabilityTrend, "stable"),
  }
  stats["entity_factory_guard"] = payload
  return payload


def record_bool_coercion_event(
  *,
  value: Any,
  default: bool,
  result: bool,
  reason: str,
) -> None:
  now = dt_util.utcnow()
  _BOOL_COERCION_METRICS["total"] += 1
  if result == default:
    _BOOL_COERCION_METRICS["defaulted"] += 1
  if reason != "bool":
    _BOOL_COERCION_METRICS["fallback"] += 1

  _BOOL_COERCION_METRICS["last_seen"] = now
  if _BOOL_COERCION_METRICS["first_seen"] is None:
    _BOOL_COERCION_METRICS["first_seen"] = now

  _BOOL_COERCION_METRICS["active_window_seconds"] = _calculate_active_window_seconds(
    _BOOL_COERCION_METRICS["first_seen"],
    _BOOL_COERCION_METRICS["last_seen"],
  )
  _BOOL_COERCION_METRICS["last_reason"] = reason
  _BOOL_COERCION_METRICS["last_value_type"] = type(value).__name__
  _BOOL_COERCION_METRICS["last_value_repr"] = _safe_repr(value)
  _BOOL_COERCION_METRICS["last_result"] = result
  _BOOL_COERCION_METRICS["last_default"] = default

  reason_counts = _BOOL_COERCION_METRICS["reason_counts"]
  reason_counts[reason] = reason_counts.get(reason, 0) + 1

  type_key = type(value).__name__
  type_counts = _BOOL_COERCION_METRICS["type_counts"]
  type_counts[type_key] = type_counts.get(type_key, 0) + 1

  samples = cast(list[BoolCoercionSample], _BOOL_COERCION_METRICS["samples"])
  samples.append(
    {
      "timestamp": now.isoformat(),
      "reason": reason,
      "value_type": type_key,
      "result": result,
      "default": default,
      "value": _safe_repr(value),
    },
  )
  if len(samples) > 5:
    del samples[:-5]


def get_bool_coercion_metrics() -> BoolCoercionMetrics:
  return {
    **_BOOL_COERCION_METRICS,
    "type_counts": dict(_BOOL_COERCION_METRICS["type_counts"]),
    "reason_counts": dict(_BOOL_COERCION_METRICS["reason_counts"]),
    "samples": list(_BOOL_COERCION_METRICS["samples"]),
  }


def reset_bool_coercion_metrics() -> None:
  _BOOL_COERCION_METRICS.update(
    {
      "total": 0,
      "defaulted": 0,
      "fallback": 0,
      "type_counts": {},
      "reason_counts": {},
      "samples": [],
      "first_seen": None,
      "last_seen": None,
      "active_window_seconds": None,
      "last_reason": None,
      "last_value_type": None,
      "last_value_repr": None,
      "last_result": None,
      "last_default": None,
      "last_reset": dt_util.utcnow(),
      "reset_count": _BOOL_COERCION_METRICS["reset_count"] + 1,
    },
  )


def summarise_bool_coercion_metrics(*, sample_limit: int = 5) -> BoolCoercionSummary:
  metrics = get_bool_coercion_metrics()
  samples = cast(list[BoolCoercionSample], metrics["samples"])
  if sample_limit >= 0:
    samples = samples[-sample_limit:]
  return {
    "recorded": bool(metrics["total"]),
    "total": metrics["total"],
    "defaulted": metrics["defaulted"],
    "fallback": metrics["fallback"],
    "reset_count": metrics["reset_count"],
    "first_seen": metrics["first_seen"].isoformat() if metrics["first_seen"] else None,
    "last_seen": metrics["last_seen"].isoformat() if metrics["last_seen"] else None,
    "last_reset": metrics["last_reset"].isoformat() if metrics["last_reset"] else None,
    "active_window_seconds": metrics["active_window_seconds"],
    "last_reason": metrics["last_reason"],
    "last_value_type": metrics["last_value_type"],
    "last_value_repr": metrics["last_value_repr"],
    "last_result": metrics["last_result"],
    "last_default": metrics["last_default"],
    "reason_counts": cast(dict[str, int], metrics["reason_counts"]),
    "type_counts": cast(dict[str, int], metrics["type_counts"]),
    "samples": samples,
  }


def get_runtime_bool_coercion_summary(
  runtime_data: PawControlRuntimeData | None,
) -> BoolCoercionSummary | None:
  stats = get_runtime_performance_stats(runtime_data)
  if stats is None:
    return None
  payload = stats.get("bool_coercion")
  return cast(BoolCoercionSummary, payload) if isinstance(payload, dict) else None


def update_runtime_bool_coercion_summary(
  runtime_data: PawControlRuntimeData | None,
  *,
  sample_limit: int = 5,
) -> BoolCoercionSummary:
  summary = summarise_bool_coercion_metrics(sample_limit=sample_limit)
  if runtime_data is not None:
    ensure_runtime_performance_stats(runtime_data)["bool_coercion"] = summary
  return summary


def _as_int(value: Any) -> int:
  try:
    return int(float(value))
  except (TypeError, ValueError):
    return 0


def _as_list(value: Any) -> list[str]:
  if value is None:
    return []
  if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
    return [str(item) for item in value if item is not None]
  return [str(value)]


def summarise_reconfigure_options(
  options: Mapping[str, Any],
) -> ReconfigureTelemetrySummary | None:
  telemetry = options.get("reconfigure_telemetry")
  if not isinstance(telemetry, Mapping):
    return None
  warnings = _as_list(telemetry.get("compatibility_warnings"))
  merge_notes = _as_list(telemetry.get("merge_notes"))
  health_summary = telemetry.get("health_summary")
  health_issues = []
  health_warnings = []
  healthy = False
  if isinstance(health_summary, Mapping):
    health_issues = _as_list(health_summary.get("issues"))
    health_warnings = _as_list(health_summary.get("warnings"))
    healthy = bool(health_summary.get("healthy"))
  return {
    "timestamp": str(telemetry.get("timestamp", "")) or None,
    "requested_profile": str(telemetry.get("requested_profile", "")) or None,
    "previous_profile": str(telemetry.get("previous_profile", "")) or None,
    "dogs_count": _as_int(telemetry.get("dogs_count")),
    "estimated_entities": _as_int(telemetry.get("estimated_entities")),
    "version": _as_int(telemetry.get("version")),
    "warnings": warnings,
    "warning_count": len(warnings),
    "healthy": healthy,
    "health_issues": health_issues,
    "health_issue_count": len(health_issues),
    "health_warnings": health_warnings,
    "health_warning_count": len(health_warnings),
    "merge_notes": merge_notes,
    "merge_note_count": len(merge_notes),
  }


def get_runtime_reconfigure_summary(
  runtime_data: PawControlRuntimeData,
) -> ReconfigureTelemetrySummary | None:
  stats = get_runtime_performance_stats(runtime_data)
  if stats is None:
    return None
  payload = stats.get("reconfigure_summary")
  return (
    cast(ReconfigureTelemetrySummary, payload) if isinstance(payload, dict) else None
  )


def update_runtime_reconfigure_summary(
  runtime_data: PawControlRuntimeData,
) -> ReconfigureTelemetrySummary | None:
  options = runtime_data.config_entry.options
  summary = summarise_reconfigure_options(options)
  if summary is None:
    return None
  ensure_runtime_performance_stats(runtime_data)["reconfigure_summary"] = summary
  return summary


def get_runtime_resilience_summary(
  runtime_data: PawControlRuntimeData,
) -> CoordinatorResilienceSummary | None:
  stats = get_runtime_performance_stats(runtime_data)
  if stats is None:
    return None
  payload = stats.get("resilience_summary")
  return (
    cast(CoordinatorResilienceSummary, payload) if isinstance(payload, dict) else None
  )


def get_runtime_resilience_diagnostics(
  runtime_data: PawControlRuntimeData,
) -> CoordinatorResilienceDiagnostics | None:
  stats = get_runtime_performance_stats(runtime_data)
  if stats is None:
    return None
  payload = stats.get("resilience_diagnostics")
  return (
    cast(CoordinatorResilienceDiagnostics, payload)
    if isinstance(payload, dict)
    else None
  )


def update_runtime_resilience_summary(
  runtime_data: PawControlRuntimeData,
  summary: CoordinatorResilienceSummary | None,
) -> CoordinatorResilienceSummary | None:
  stats = ensure_runtime_performance_stats(runtime_data)
  if summary is None:
    stats.pop("resilience_summary", None)
    return None
  stats["resilience_summary"] = summary
  return summary


def update_runtime_resilience_diagnostics(
  runtime_data: PawControlRuntimeData,
  diagnostics: CoordinatorResilienceDiagnostics | None,
) -> CoordinatorResilienceDiagnostics | None:
  stats = ensure_runtime_performance_stats(runtime_data)
  if diagnostics is None:
    stats.pop("resilience_diagnostics", None)
    return None
  stats["resilience_diagnostics"] = diagnostics
  return diagnostics


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
  if runtime_data is None:
    return None

  stats = ensure_runtime_performance_stats(runtime_data)
  failures_raw = stats.setdefault("door_sensor_failures", [])
  failures = cast(list[DoorSensorPersistenceFailure], failures_raw)
  event: DoorSensorPersistenceFailure = {
    "recorded_at": dt_util.utcnow().isoformat(),
    "dog_id": dog_id,
  }
  if dog_name is not None:
    event["dog_name"] = dog_name
  if door_sensor is not None:
    event["door_sensor"] = door_sensor
  if settings is not None:
    event["settings"] = cast(Any, dict(settings))
  if error is not None:
    event["error"] = (
      f"{error.__class__.__name__}: {error}"
      if isinstance(error, Exception)
      else str(error)
    )

  failures.append(event)
  if len(failures) > limit:
    del failures[:-limit]

  summary: DoorSensorFailureSummary = {
    "dog_id": dog_id,
    "failure_count": len(failures),
    "last_failure": failures[-1] if failures else None,
  }
  if dog_name is not None:
    summary["dog_name"] = dog_name
  stats["door_sensor_failure_summary"] = summary
  stats["last_door_sensor_failure"] = event
  return event
