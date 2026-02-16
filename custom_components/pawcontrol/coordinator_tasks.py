"""Helper routines that keep the coordinator file compact."""

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from datetime import UTC, date, datetime
from math import isfinite
from typing import TYPE_CHECKING, Any, Final, cast

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .coordinator_support import ensure_cache_repair_aggregate
from .performance import (
  capture_cache_diagnostics,
  performance_tracker,
  record_maintenance_result,
)
from .runtime_data import describe_runtime_store_status, get_runtime_data
from .service_guard import normalise_guard_history
from .telemetry import (
  get_runtime_performance_stats,
  get_runtime_reconfigure_summary,
  summarise_reconfigure_options,
  update_runtime_bool_coercion_summary,
  update_runtime_reconfigure_summary,
  update_runtime_resilience_diagnostics,
  update_runtime_store_health,
)
from .types import (
  AdaptivePollingDiagnostics,
  CacheRepairAggregate,
  CircuitBreakerStateSummary,
  CircuitBreakerStatsPayload,
  CoordinatorRejectionMetrics,
  CoordinatorResilienceDiagnostics,
  CoordinatorResilienceSummary,
  CoordinatorRuntimeStatisticsPayload,
  CoordinatorRuntimeStoreSummary,
  CoordinatorServiceExecutionSummary,
  CoordinatorStatisticsPayload,
  EntityBudgetSummary,
  EntityFactoryGuardEvent,
  EntityFactoryGuardMetricsSnapshot,
  EntityFactoryGuardStabilityTrend,
  HelperManagerGuardMetrics,
  JSONMapping,
  JSONMutableMapping,
  MaintenanceMetadataPayload,
  PawControlRuntimeData,
  ReconfigureTelemetrySummary,
  RejectionMetricsSource,
  RejectionMetricsTarget,
  RuntimeStoreHealthAssessment,
)

if TYPE_CHECKING:  # pragma: no cover - import for typing only
  from datetime import timedelta  # noqa: E111

  from .coordinator import PawControlCoordinator  # noqa: E111


def _fetch_cache_repair_summary(
  coordinator: PawControlCoordinator,
) -> CacheRepairAggregate | None:
  """Return the latest cache repair aggregate for coordinator telemetry."""  # noqa: E111

  runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)  # noqa: E111
  if runtime_data is None:  # noqa: E111
    return None

  data_manager = getattr(runtime_data, "data_manager", None)  # noqa: E111
  if data_manager is None:  # noqa: E111
    return None

  summary_method = getattr(data_manager, "cache_repair_summary", None)  # noqa: E111
  if not callable(summary_method):  # noqa: E111
    return None

  try:  # noqa: E111
    summary = summary_method()
  except Exception as err:  # pragma: no cover - diagnostics guard  # noqa: E111
    coordinator.logger.debug(
      "Failed to collect cache repair summary: %s",
      err,
    )
    return None

  resolved_summary = ensure_cache_repair_aggregate(summary)  # noqa: E111
  if resolved_summary is not None:  # noqa: E111
    return resolved_summary
  coordinator.logger.debug(  # noqa: E111
    "Cache repair summary did not return CacheRepairAggregate: %r",
    summary,
  )
  return None  # noqa: E111


def _fetch_reconfigure_summary(
  coordinator: PawControlCoordinator,
) -> ReconfigureTelemetrySummary | None:
  """Return the latest reconfigure summary for coordinator telemetry."""  # noqa: E111

  runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)  # noqa: E111
  if runtime_data is not None:  # noqa: E111
    summary = get_runtime_reconfigure_summary(runtime_data)
    if summary is None:
      summary = update_runtime_reconfigure_summary(runtime_data)  # noqa: E111
    if summary is not None:
      return summary  # noqa: E111

  options = getattr(coordinator.config_entry, "options", None)  # noqa: E111
  return summarise_reconfigure_options(options)  # noqa: E111


def _build_runtime_store_summary(
  coordinator: PawControlCoordinator,
  runtime_data: PawControlRuntimeData | None,
  *,
  record_event: bool,
) -> CoordinatorRuntimeStoreSummary:
  """Return a runtime store summary combining snapshot and history telemetry."""  # noqa: E111

  snapshot = describe_runtime_store_status(  # noqa: E111
    coordinator.hass,
    coordinator.config_entry,
  )
  history = update_runtime_store_health(  # noqa: E111
    runtime_data,
    snapshot,
    record_event=record_event,
  )
  summary: CoordinatorRuntimeStoreSummary = {"snapshot": snapshot}  # noqa: E111
  if history:  # noqa: E111
    summary["history"] = history
    assessment = history.get("assessment")
    if isinstance(assessment, Mapping):
      summary["assessment"] = cast(  # noqa: E111
        RuntimeStoreHealthAssessment,
        dict(assessment),
      )
  return summary  # noqa: E111


def _summarise_resilience(
  breakers: dict[str, CircuitBreakerStatsPayload],
) -> CoordinatorResilienceSummary:
  """Aggregate circuit breaker diagnostics into a concise summary."""  # noqa: E111

  state_counts: dict[str, int] = {  # noqa: E111
    "closed": 0,
    "open": 0,
    "half_open": 0,
    "unknown": 0,
    "other": 0,
  }
  failure_count = 0  # noqa: E111
  success_count = 0  # noqa: E111
  total_calls = 0  # noqa: E111
  total_failures = 0  # noqa: E111
  total_successes = 0  # noqa: E111
  rejected_call_count = 0  # noqa: E111
  latest_failure: float | None = None  # noqa: E111
  latest_state_change: float | None = None  # noqa: E111
  latest_success: float | None = None  # noqa: E111
  latest_rejection: float | None = None  # noqa: E111
  latest_recovered_pair: tuple[str, str, float, float] | None = None  # noqa: E111
  latest_rejection_pair: tuple[str, str, float] | None = None  # noqa: E111
  recovery_latency: float | None = None  # noqa: E111
  recovery_breaker_id: str | None = None  # noqa: E111
  recovery_breaker_name: str | None = None  # noqa: E111
  rejection_breaker_id: str | None = None  # noqa: E111
  rejection_breaker_name: str | None = None  # noqa: E111
  open_breakers: list[str] = []  # noqa: E111
  half_open_breakers: list[str] = []  # noqa: E111
  unknown_breakers: list[str] = []  # noqa: E111
  open_breaker_ids: list[str] = []  # noqa: E111
  half_open_breaker_ids: list[str] = []  # noqa: E111
  unknown_breaker_ids: list[str] = []  # noqa: E111
  rejection_breakers: list[str] = []  # noqa: E111
  rejection_breaker_ids: list[str] = []  # noqa: E111

  for name, stats in breakers.items():  # noqa: E111
    breaker_name = _stringify_breaker_name(name)
    breaker_id = _normalise_breaker_id(breaker_name, stats)
    state = _normalise_breaker_state(stats.get("state"))
    if state in ("closed", "open", "half_open"):
      state_counts[state] += 1  # noqa: E111
    elif state == "unknown":
      state_counts["unknown"] += 1  # noqa: E111
      unknown_breakers.append(breaker_name)  # noqa: E111
      unknown_breaker_ids.append(breaker_id)  # noqa: E111
    else:
      state_counts["other"] += 1  # noqa: E111

    if state == "open":
      open_breakers.append(breaker_name)  # noqa: E111
      open_breaker_ids.append(breaker_id)  # noqa: E111
    elif state == "half_open":
      half_open_breakers.append(breaker_name)  # noqa: E111
      half_open_breaker_ids.append(breaker_id)  # noqa: E111

    failure_count += _coerce_int(stats.get("failure_count"))
    success_count += _coerce_int(stats.get("success_count"))
    total_calls += _coerce_int(stats.get("total_calls"))
    total_failures += _coerce_int(stats.get("total_failures"))
    total_successes += _coerce_int(stats.get("total_successes"))
    rejected_calls = _coerce_int(stats.get("rejected_calls"))
    rejected_call_count += rejected_calls
    if rejected_calls > 0:
      rejection_breakers.append(breaker_name)  # noqa: E111
      rejection_breaker_ids.append(breaker_id)  # noqa: E111

    failure_value = _coerce_float(stats.get("last_failure_time"))
    if failure_value is not None:
      latest_failure = (  # noqa: E111
        failure_value if latest_failure is None else max(latest_failure, failure_value)
      )

    state_change_value = _coerce_float(stats.get("last_state_change"))
    if state_change_value is not None:
      latest_state_change = (  # noqa: E111
        state_change_value
        if latest_state_change is None
        else max(latest_state_change, state_change_value)
      )

    success_value = _coerce_float(stats.get("last_success_time"))
    if success_value is not None:
      latest_success = (  # noqa: E111
        success_value if latest_success is None else max(latest_success, success_value)
      )

      if (  # noqa: E111
        failure_value is not None
        and success_value >= failure_value
        and (latest_recovered_pair is None or success_value > latest_recovered_pair[2])
      ):
        latest_recovered_pair = (
          breaker_id,
          breaker_name,
          success_value,
          failure_value,
        )

    rejection_value = _coerce_float(stats.get("last_rejection_time"))
    if rejection_value is not None:
      latest_rejection = (  # noqa: E111
        rejection_value
        if latest_rejection is None
        else max(latest_rejection, rejection_value)
      )
      if latest_rejection_pair is None or rejection_value > latest_rejection_pair[2]:  # noqa: E111
        latest_rejection_pair = (
          breaker_id,
          breaker_name,
          rejection_value,
        )

  open_breaker_count = len(open_breakers)  # noqa: E111
  half_open_breaker_count = len(half_open_breakers)  # noqa: E111
  unknown_breaker_count = len(unknown_breakers)  # noqa: E111

  if latest_recovered_pair is not None:  # noqa: E111
    (
      recovered_breaker_id,
      recovered_breaker_name,
      success_value,
      failure_value,
    ) = latest_recovered_pair
    if latest_failure is None or success_value >= latest_failure:
      recovery_latency = max(success_value - failure_value, 0.0)  # noqa: E111
      recovery_breaker_id = recovered_breaker_id  # noqa: E111
      recovery_breaker_name = recovered_breaker_name  # noqa: E111

  if latest_rejection_pair is not None:  # noqa: E111
    rejection_breaker_id, rejection_breaker_name, latest_rejection = (
      latest_rejection_pair
    )

  rejection_rate: float | None  # noqa: E111
  total_attempts = total_calls + rejected_call_count  # noqa: E111
  rejection_rate = rejected_call_count / total_attempts if total_attempts > 0 else None  # noqa: E111

  summary: CoordinatorResilienceSummary = {  # noqa: E111
    "total_breakers": len(breakers),
    "states": cast(CircuitBreakerStateSummary, state_counts),
    "failure_count": failure_count,
    "success_count": success_count,
    "total_calls": total_calls,
    "total_failures": total_failures,
    "total_successes": total_successes,
    "rejected_call_count": rejected_call_count,
    "last_failure_time": latest_failure,
    "last_state_change": latest_state_change,
    "last_success_time": latest_success,
    "last_rejection_time": latest_rejection,
    "recovery_latency": recovery_latency,
    "recovery_breaker_id": recovery_breaker_id,
    "open_breaker_count": open_breaker_count,
    "half_open_breaker_count": half_open_breaker_count,
    "unknown_breaker_count": unknown_breaker_count,
    "open_breakers": list(open_breakers),
    "open_breaker_ids": list(open_breaker_ids),
    "half_open_breakers": list(half_open_breakers),
    "half_open_breaker_ids": list(half_open_breaker_ids),
    "unknown_breakers": list(unknown_breakers),
    "unknown_breaker_ids": list(unknown_breaker_ids),
    "rejection_breaker_count": len(rejection_breakers),
    "rejection_breakers": list(rejection_breakers),
    "rejection_breaker_ids": list(rejection_breaker_ids),
    "rejection_rate": rejection_rate,
  }

  if recovery_breaker_name is not None:  # noqa: E111
    summary["recovery_breaker_name"] = recovery_breaker_name

  if rejection_breaker_name is not None:  # noqa: E111
    summary["last_rejection_breaker_name"] = rejection_breaker_name

  if rejection_breaker_id is not None:  # noqa: E111
    summary["last_rejection_breaker_id"] = rejection_breaker_id

  return summary  # noqa: E111


def _extract_stat_value(stats: Any, key: str, default: Any = None) -> Any:
  """Return ``key`` from ``stats`` supporting both mapping and attribute access."""  # noqa: E111

  if isinstance(stats, Mapping):  # noqa: E111
    return stats.get(key, default)
  return getattr(stats, key, default)  # noqa: E111


def _normalise_breaker_id(name: Any, stats: Any) -> str:
  """Return a stable breaker identifier derived from diagnostics metadata."""  # noqa: E111

  candidate = _extract_stat_value(stats, "breaker_id")  # noqa: E111
  if candidate in (None, ""):  # noqa: E111
    candidate = _extract_stat_value(stats, "name")
  if candidate in (None, ""):  # noqa: E111
    candidate = _extract_stat_value(stats, "identifier")
  if candidate in (None, ""):  # noqa: E111
    candidate = _extract_stat_value(stats, "id")

  if candidate in (None, ""):  # noqa: E111
    candidate = name

  try:  # noqa: E111
    breaker_id = str(candidate)
  except Exception:  # pragma: no cover - defensive fallback  # noqa: E111
    breaker_id = str(name)

  if not breaker_id:  # noqa: E111
    breaker_id = str(name)

  return breaker_id  # noqa: E111


def _normalise_entity_budget_summary(data: Any) -> EntityBudgetSummary:
  """Return an entity budget summary with guaranteed diagnostics keys."""  # noqa: E111

  summary: EntityBudgetSummary = {  # noqa: E111
    "active_dogs": 0,
    "total_capacity": 0,
    "total_allocated": 0,
    "total_remaining": 0,
    "average_utilization": 0.0,
    "peak_utilization": 0.0,
    "denied_requests": 0,
  }

  if isinstance(data, Mapping):  # noqa: E111
    summary["active_dogs"] = _coerce_int(data.get("active_dogs"))
    summary["total_capacity"] = _coerce_int(data.get("total_capacity"))
    summary["total_allocated"] = _coerce_int(data.get("total_allocated"))
    summary["total_remaining"] = _coerce_int(data.get("total_remaining"))

    average = _coerce_float(data.get("average_utilization"))
    if average is not None:
      summary["average_utilization"] = average  # noqa: E111

    peak = _coerce_float(data.get("peak_utilization"))
    if peak is not None:
      summary["peak_utilization"] = peak  # noqa: E111

    summary["denied_requests"] = _coerce_int(data.get("denied_requests"))

  return summary  # noqa: E111


def _normalise_adaptive_diagnostics(data: Any) -> AdaptivePollingDiagnostics:
  """Return adaptive polling diagnostics with consistent numeric types."""  # noqa: E111

  diagnostics: AdaptivePollingDiagnostics = {  # noqa: E111
    "target_cycle_ms": 0.0,
    "current_interval_ms": 0.0,
    "average_cycle_ms": 0.0,
    "history_samples": 0,
    "error_streak": 0,
    "entity_saturation": 0.0,
    "idle_interval_ms": 0.0,
    "idle_grace_ms": 0.0,
  }

  if isinstance(data, Mapping):  # noqa: E111
    target = _coerce_float(data.get("target_cycle_ms"))
    if target is not None:
      diagnostics["target_cycle_ms"] = target  # noqa: E111

    current = _coerce_float(data.get("current_interval_ms"))
    if current is not None:
      diagnostics["current_interval_ms"] = current  # noqa: E111

    average = _coerce_float(data.get("average_cycle_ms"))
    if average is not None:
      diagnostics["average_cycle_ms"] = average  # noqa: E111

    diagnostics["history_samples"] = _coerce_int(
      data.get("history_samples"),
    )
    diagnostics["error_streak"] = _coerce_int(data.get("error_streak"))

    saturation = _coerce_float(data.get("entity_saturation"))
    if saturation is not None:
      diagnostics["entity_saturation"] = saturation  # noqa: E111

    idle_interval = _coerce_float(data.get("idle_interval_ms"))
    if idle_interval is not None:
      diagnostics["idle_interval_ms"] = idle_interval  # noqa: E111

    idle_grace = _coerce_float(data.get("idle_grace_ms"))
    if idle_grace is not None:
      diagnostics["idle_grace_ms"] = idle_grace  # noqa: E111

  return diagnostics  # noqa: E111


_REJECTION_SCALAR_KEYS: Final[tuple[str, ...]] = (
  "rejected_call_count",
  "rejection_breaker_count",
  "rejection_rate",
  "last_rejection_time",
  "last_rejection_breaker_id",
  "last_rejection_breaker_name",
  "last_failure_reason",
  "open_breaker_count",
  "half_open_breaker_count",
  "unknown_breaker_count",
)

_REJECTION_SEQUENCE_KEYS: Final[tuple[str, ...]] = (
  "open_breakers",
  "open_breaker_ids",
  "half_open_breakers",
  "half_open_breaker_ids",
  "unknown_breakers",
  "unknown_breaker_ids",
  "rejection_breaker_ids",
  "rejection_breakers",
)

_REJECTION_MAPPING_KEYS: Final[tuple[str, ...]] = ("failure_reasons",)


def default_rejection_metrics() -> CoordinatorRejectionMetrics:
  """Return a baseline rejection metric payload for diagnostics consumers."""  # noqa: E111

  return {  # noqa: E111
    "schema_version": 4,
    "rejected_call_count": 0,
    "rejection_breaker_count": 0,
    "rejection_rate": 0.0,
    "last_rejection_time": None,
    "last_rejection_breaker_id": None,
    "last_rejection_breaker_name": None,
    "last_failure_reason": None,
    "failure_reasons": {},
    "open_breaker_count": 0,
    "half_open_breaker_count": 0,
    "unknown_breaker_count": 0,
    "open_breakers": [],
    "open_breaker_ids": [],
    "half_open_breakers": [],
    "half_open_breaker_ids": [],
    "unknown_breakers": [],
    "unknown_breaker_ids": [],
    "rejection_breaker_ids": [],
    "rejection_breakers": [],
  }


def merge_rejection_metric_values(
  target: RejectionMetricsTarget,
  *sources: RejectionMetricsSource,
) -> None:
  """Populate ``target`` with rejection metrics extracted from ``sources``."""  # noqa: E111

  if not sources:  # noqa: E111
    return

  mutable_target = cast(JSONMutableMapping, target)  # noqa: E111
  source_mappings = [cast(JSONMapping, source) for source in sources]  # noqa: E111

  for key in _REJECTION_SCALAR_KEYS:  # noqa: E111
    for source in source_mappings:
      if key in source:  # noqa: E111
        mutable_target[key] = source[key]
        break

  for key in _REJECTION_SEQUENCE_KEYS:  # noqa: E111
    for source in source_mappings:
      if key in source:  # noqa: E111
        value = source[key]
        if isinstance(value, Sequence) and not isinstance(
          value,
          str | bytes | bytearray,
        ):
          mutable_target[key] = list(value)  # noqa: E111
        else:
          mutable_target[key] = []  # noqa: E111
        break
    else:
      mutable_target[key] = []  # noqa: E111

  for key in _REJECTION_MAPPING_KEYS:  # noqa: E111
    for source in source_mappings:
      if key in source:  # noqa: E111
        value = source[key]
        if isinstance(value, Mapping):
          mapping: dict[str, int] = {}  # noqa: E111
          for reason, count in value.items():  # noqa: E111
            reason_text = str(reason).strip()
            if not reason_text:
              continue  # noqa: E111
            mapping[reason_text] = max(_coerce_int(count), 0)
          mutable_target[key] = mapping  # noqa: E111
        else:
          mutable_target[key] = {}  # noqa: E111
        break
    else:
      mutable_target[key] = {}  # noqa: E111


def derive_rejection_metrics(
  summary: JSONMapping | CoordinatorResilienceSummary | None,
) -> CoordinatorRejectionMetrics:
  """Return rejection counters extracted from a resilience summary."""  # noqa: E111

  metrics = default_rejection_metrics()  # noqa: E111

  if not summary:  # noqa: E111
    return metrics

  rejected_calls = summary.get("rejected_call_count")  # noqa: E111
  if rejected_calls is not None:  # noqa: E111
    metrics["rejected_call_count"] = _coerce_int(rejected_calls)

  rejection_breakers = summary.get("rejection_breaker_count")  # noqa: E111
  if rejection_breakers is not None:  # noqa: E111
    metrics["rejection_breaker_count"] = _coerce_int(rejection_breakers)

  rejection_rate = _coerce_float(summary.get("rejection_rate"))  # noqa: E111
  if rejection_rate is not None:  # noqa: E111
    metrics["rejection_rate"] = rejection_rate

  last_rejection_time = _coerce_float(summary.get("last_rejection_time"))  # noqa: E111
  if last_rejection_time is not None:  # noqa: E111
    metrics["last_rejection_time"] = last_rejection_time

  breaker_id_raw = summary.get("last_rejection_breaker_id")  # noqa: E111
  if isinstance(breaker_id_raw, str):  # noqa: E111
    metrics["last_rejection_breaker_id"] = breaker_id_raw

  breaker_name_raw = summary.get("last_rejection_breaker_name")  # noqa: E111
  if isinstance(breaker_name_raw, str):  # noqa: E111
    metrics["last_rejection_breaker_name"] = breaker_name_raw

  last_failure_reason = summary.get("last_failure_reason")  # noqa: E111
  if isinstance(last_failure_reason, str) and last_failure_reason:  # noqa: E111
    metrics["last_failure_reason"] = last_failure_reason

  failure_reasons = summary.get("failure_reasons")  # noqa: E111
  if isinstance(failure_reasons, Mapping):  # noqa: E111
    normalised: dict[str, int] = {}
    for reason, count in failure_reasons.items():
      reason_text = str(reason).strip()  # noqa: E111
      if not reason_text:  # noqa: E111
        continue
      normalised[reason_text] = max(_coerce_int(count), 0)  # noqa: E111
    metrics["failure_reasons"] = normalised

  open_breakers = summary.get("open_breaker_count")  # noqa: E111
  if open_breakers is not None:  # noqa: E111
    metrics["open_breaker_count"] = _coerce_int(open_breakers)

  half_open_breakers = summary.get("half_open_breaker_count")  # noqa: E111
  if half_open_breakers is not None:  # noqa: E111
    metrics["half_open_breaker_count"] = _coerce_int(half_open_breakers)

  unknown_breakers = summary.get("unknown_breaker_count")  # noqa: E111
  if unknown_breakers is not None:  # noqa: E111
    metrics["unknown_breaker_count"] = _coerce_int(unknown_breakers)

  metrics["open_breakers"] = _normalise_string_list(  # noqa: E111
    summary.get("open_breakers"),
  )
  metrics["open_breaker_ids"] = _normalise_string_list(  # noqa: E111
    summary.get("open_breaker_ids"),
  )
  metrics["half_open_breakers"] = _normalise_string_list(  # noqa: E111
    summary.get("half_open_breakers"),
  )
  metrics["half_open_breaker_ids"] = _normalise_string_list(  # noqa: E111
    summary.get("half_open_breaker_ids"),
  )
  metrics["unknown_breakers"] = _normalise_string_list(  # noqa: E111
    summary.get("unknown_breakers"),
  )
  metrics["unknown_breaker_ids"] = _normalise_string_list(  # noqa: E111
    summary.get("unknown_breaker_ids"),
  )
  metrics["rejection_breaker_ids"] = _normalise_string_list(  # noqa: E111
    summary.get("rejection_breaker_ids"),
  )
  metrics["rejection_breakers"] = _normalise_string_list(  # noqa: E111
    summary.get("rejection_breakers"),
  )

  return metrics  # noqa: E111


def _derive_rejection_metrics(
  summary: JSONMapping | CoordinatorResilienceSummary,
) -> CoordinatorRejectionMetrics:
  """Backwards-compatible wrapper for legacy imports."""  # noqa: E111

  return derive_rejection_metrics(summary)  # noqa: E111


def _default_guard_metrics() -> HelperManagerGuardMetrics:
  """Return zeroed guard metrics for runtime statistics snapshots."""  # noqa: E111

  return {  # noqa: E111
    "executed": 0,
    "skipped": 0,
    "reasons": {},
    "last_results": [],
  }


def _normalise_guard_metrics(payload: Any) -> HelperManagerGuardMetrics:
  """Coerce ``payload`` into guard metrics with canonical structures."""  # noqa: E111

  guard_metrics = _default_guard_metrics()  # noqa: E111
  if not isinstance(payload, Mapping):  # noqa: E111
    return guard_metrics

  executed_raw = payload.get("executed")  # noqa: E111
  if executed_raw is not None:  # noqa: E111
    guard_metrics["executed"] = max(_coerce_int(executed_raw), 0)

  skipped_raw = payload.get("skipped")  # noqa: E111
  if skipped_raw is not None:  # noqa: E111
    guard_metrics["skipped"] = max(_coerce_int(skipped_raw), 0)

  reasons_payload = payload.get("reasons")  # noqa: E111
  reasons: dict[str, int] = {}  # noqa: E111
  if isinstance(reasons_payload, Mapping):  # noqa: E111
    for reason, count in reasons_payload.items():
      text = str(reason).strip()  # noqa: E111
      if not text:  # noqa: E111
        continue
      coerced = max(_coerce_int(count), 0)  # noqa: E111
      if coerced:  # noqa: E111
        reasons[text] = coerced
  guard_metrics["reasons"] = reasons  # noqa: E111

  last_results_payload = payload.get("last_results")  # noqa: E111
  guard_metrics["last_results"] = normalise_guard_history(  # noqa: E111
    last_results_payload,
  )

  return guard_metrics  # noqa: E111


def resolve_service_guard_metrics(payload: Any) -> HelperManagerGuardMetrics:
  """Return aggregated guard metrics stored on runtime performance stats."""  # noqa: E111

  guard_metrics = _default_guard_metrics()  # noqa: E111
  if not isinstance(payload, Mapping):  # noqa: E111
    return guard_metrics

  guard_metrics = _normalise_guard_metrics(  # noqa: E111
    payload.get("service_guard_metrics"),
  )

  if isinstance(payload, MutableMapping):  # noqa: E111
    payload["service_guard_metrics"] = {
      "executed": guard_metrics["executed"],
      "skipped": guard_metrics["skipped"],
      "reasons": dict(guard_metrics["reasons"]),
      "last_results": list(guard_metrics["last_results"]),
    }

  return guard_metrics  # noqa: E111


def resolve_entity_factory_guard_metrics(
  payload: Any,
) -> EntityFactoryGuardMetricsSnapshot:
  """Return normalised entity factory guard metrics for diagnostics consumers."""  # noqa: E111

  metrics: Mapping[str, object] | None = None  # noqa: E111
  if isinstance(payload, Mapping):  # noqa: E111
    candidate = payload.get("entity_factory_guard_metrics")
    if isinstance(candidate, Mapping):
      metrics = candidate  # noqa: E111
    elif "runtime_floor" in payload:
      metrics = payload  # noqa: E111

  snapshot: EntityFactoryGuardMetricsSnapshot = {}  # noqa: E111
  if metrics is None:  # noqa: E111
    snapshot["last_event"] = "unknown"
    return snapshot

  runtime_floor = _coerce_float(metrics.get("runtime_floor"))  # noqa: E111
  if runtime_floor is not None:  # noqa: E111
    snapshot["runtime_floor_ms"] = runtime_floor * 1000

  baseline_floor = _coerce_float(metrics.get("baseline_floor"))  # noqa: E111
  if baseline_floor is not None:  # noqa: E111
    snapshot["baseline_floor_ms"] = baseline_floor * 1000

  max_floor = _coerce_float(metrics.get("max_floor"))  # noqa: E111
  if max_floor is not None:  # noqa: E111
    snapshot["max_floor_ms"] = max_floor * 1000

  actual_duration = _coerce_float(metrics.get("last_actual_duration"))  # noqa: E111
  if actual_duration is not None:  # noqa: E111
    snapshot["last_actual_duration_ms"] = actual_duration * 1000

  peak_runtime_floor = _coerce_float(metrics.get("peak_runtime_floor"))  # noqa: E111
  if peak_runtime_floor is not None:  # noqa: E111
    snapshot["peak_runtime_floor_ms"] = peak_runtime_floor * 1000

  lowest_runtime_floor = _coerce_float(metrics.get("lowest_runtime_floor"))  # noqa: E111
  if lowest_runtime_floor is not None:  # noqa: E111
    snapshot["lowest_runtime_floor_ms"] = lowest_runtime_floor * 1000

  last_floor_change = _coerce_float(metrics.get("last_floor_change"))  # noqa: E111
  if last_floor_change is not None:  # noqa: E111
    snapshot["last_floor_change_ms"] = last_floor_change * 1000

  floor_delta = _coerce_float(metrics.get("runtime_floor_delta"))  # noqa: E111
  if floor_delta is not None:  # noqa: E111
    snapshot["runtime_floor_delta_ms"] = floor_delta * 1000
  elif runtime_floor is not None and baseline_floor is not None:  # noqa: E111
    snapshot["runtime_floor_delta_ms"] = max(runtime_floor - baseline_floor, 0.0) * 1000

  ratio = _coerce_float(metrics.get("last_duration_ratio"))  # noqa: E111
  if ratio is not None and isfinite(ratio):  # noqa: E111
    snapshot["last_duration_ratio"] = ratio

  last_floor_change_ratio = _coerce_float(  # noqa: E111
    metrics.get("last_floor_change_ratio"),
  )
  if last_floor_change_ratio is not None and isfinite(last_floor_change_ratio):  # noqa: E111
    snapshot["last_floor_change_ratio"] = last_floor_change_ratio

  last_event = metrics.get("last_event")  # noqa: E111
  if isinstance(last_event, str) and last_event:  # noqa: E111
    snapshot["last_event"] = cast("EntityFactoryGuardEvent", last_event)
  else:  # noqa: E111
    snapshot["last_event"] = "unknown"

  last_updated = metrics.get("last_updated")  # noqa: E111
  if isinstance(last_updated, str) and last_updated:  # noqa: E111
    snapshot["last_updated"] = last_updated

  samples = metrics.get("samples")  # noqa: E111
  if isinstance(samples, int | float):  # noqa: E111
    snapshot["samples"] = int(samples)

  stable_samples = metrics.get("stable_samples")  # noqa: E111
  if isinstance(stable_samples, int | float):  # noqa: E111
    snapshot["stable_samples"] = int(stable_samples)

  expansions = metrics.get("expansions")  # noqa: E111
  if isinstance(expansions, int | float):  # noqa: E111
    snapshot["expansions"] = int(expansions)

  contractions = metrics.get("contractions")  # noqa: E111
  if isinstance(contractions, int | float):  # noqa: E111
    snapshot["contractions"] = int(contractions)

  last_expansion = _coerce_float(metrics.get("last_expansion_duration"))  # noqa: E111
  if last_expansion is not None:  # noqa: E111
    snapshot["last_expansion_duration_ms"] = last_expansion * 1000

  last_contraction = _coerce_float(metrics.get("last_contraction_duration"))  # noqa: E111
  if last_contraction is not None:  # noqa: E111
    snapshot["last_contraction_duration_ms"] = last_contraction * 1000

  average_duration = _coerce_float(metrics.get("average_duration"))  # noqa: E111
  if average_duration is not None:  # noqa: E111
    snapshot["average_duration_ms"] = average_duration * 1000

  max_duration = _coerce_float(metrics.get("max_duration"))  # noqa: E111
  if max_duration is not None:  # noqa: E111
    snapshot["max_duration_ms"] = max_duration * 1000

  min_duration = _coerce_float(metrics.get("min_duration"))  # noqa: E111
  if min_duration is not None:  # noqa: E111
    snapshot["min_duration_ms"] = min_duration * 1000

  duration_span = _coerce_float(metrics.get("duration_span"))  # noqa: E111
  if duration_span is not None:  # noqa: E111
    snapshot["duration_span_ms"] = duration_span * 1000

  jitter_ratio = _coerce_float(metrics.get("jitter_ratio"))  # noqa: E111
  if jitter_ratio is not None and isfinite(jitter_ratio):  # noqa: E111
    snapshot["jitter_ratio"] = jitter_ratio

  recent_average = _coerce_float(metrics.get("recent_average_duration"))  # noqa: E111
  if recent_average is not None:  # noqa: E111
    snapshot["recent_average_duration_ms"] = recent_average * 1000

  recent_max = _coerce_float(metrics.get("recent_max_duration"))  # noqa: E111
  if recent_max is not None:  # noqa: E111
    snapshot["recent_max_duration_ms"] = recent_max * 1000

  recent_min = _coerce_float(metrics.get("recent_min_duration"))  # noqa: E111
  if recent_min is not None:  # noqa: E111
    snapshot["recent_min_duration_ms"] = recent_min * 1000

  recent_span = _coerce_float(metrics.get("recent_duration_span"))  # noqa: E111
  if recent_span is not None:  # noqa: E111
    snapshot["recent_duration_span_ms"] = recent_span * 1000

  recent_jitter_ratio = _coerce_float(metrics.get("recent_jitter_ratio"))  # noqa: E111
  if recent_jitter_ratio is not None and isfinite(recent_jitter_ratio):  # noqa: E111
    snapshot["recent_jitter_ratio"] = recent_jitter_ratio

  stable_ratio = _coerce_float(metrics.get("stable_ratio"))  # noqa: E111
  if stable_ratio is not None and isfinite(stable_ratio):  # noqa: E111
    snapshot["stable_ratio"] = stable_ratio

  expansion_ratio = _coerce_float(metrics.get("expansion_ratio"))  # noqa: E111
  if expansion_ratio is not None and isfinite(expansion_ratio):  # noqa: E111
    snapshot["expansion_ratio"] = expansion_ratio

  contraction_ratio = _coerce_float(metrics.get("contraction_ratio"))  # noqa: E111
  if contraction_ratio is not None and isfinite(contraction_ratio):  # noqa: E111
    snapshot["contraction_ratio"] = contraction_ratio

  consecutive_stable = metrics.get("consecutive_stable_samples")  # noqa: E111
  if isinstance(consecutive_stable, int | float):  # noqa: E111
    snapshot["consecutive_stable_samples"] = int(consecutive_stable)

  longest_stable = metrics.get("longest_stable_run")  # noqa: E111
  if isinstance(longest_stable, int | float):  # noqa: E111
    snapshot["longest_stable_run"] = int(longest_stable)

  volatility_ratio = _coerce_float(metrics.get("volatility_ratio"))  # noqa: E111
  if volatility_ratio is not None and isfinite(volatility_ratio):  # noqa: E111
    snapshot["volatility_ratio"] = volatility_ratio

  recent_samples = metrics.get("recent_samples")  # noqa: E111
  if isinstance(recent_samples, int | float):  # noqa: E111
    snapshot["recent_samples"] = int(recent_samples)

  recent_events_raw = metrics.get("recent_events")  # noqa: E111
  if isinstance(recent_events_raw, Sequence) and not isinstance(  # noqa: E111
    recent_events_raw,
    str | bytes | bytearray,
  ):
    recent_events: list[EntityFactoryGuardEvent] = [
      cast(EntityFactoryGuardEvent, item)
      for item in recent_events_raw
      if isinstance(item, str) and item
    ]
    if recent_events:
      snapshot["recent_events"] = recent_events  # noqa: E111

  recent_stable_samples = metrics.get("recent_stable_samples")  # noqa: E111
  if isinstance(recent_stable_samples, int | float):  # noqa: E111
    snapshot["recent_stable_samples"] = int(recent_stable_samples)

  recent_stable_ratio = _coerce_float(metrics.get("recent_stable_ratio"))  # noqa: E111
  if recent_stable_ratio is not None and isfinite(recent_stable_ratio):  # noqa: E111
    snapshot["recent_stable_ratio"] = recent_stable_ratio

  stability_trend = metrics.get("stability_trend")  # noqa: E111
  if isinstance(stability_trend, str) and stability_trend:  # noqa: E111
    snapshot["stability_trend"] = cast(
      "EntityFactoryGuardStabilityTrend",
      stability_trend,
    )

  enforce_min_runtime = metrics.get("enforce_min_runtime")  # noqa: E111
  if isinstance(enforce_min_runtime, bool) and not enforce_min_runtime:  # noqa: E111
    snapshot.setdefault("last_event", "disabled")

  if isinstance(payload, MutableMapping):  # noqa: E111
    payload["entity_factory_guard_metrics"] = dict(snapshot)

  return snapshot  # noqa: E111


def _normalise_breaker_state(value: Any) -> str:
  """Return a canonical breaker state used for resilience aggregation."""  # noqa: E111

  candidate = getattr(value, "value", value)  # noqa: E111

  if isinstance(candidate, str):  # noqa: E111
    text = candidate.strip()
  elif candidate is None:  # noqa: E111
    return "unknown"
  else:  # noqa: E111
    try:
      text = str(candidate).strip()  # noqa: E111
    except Exception:  # pragma: no cover - defensive fallback
      return "unknown"  # noqa: E111

  if not text:  # noqa: E111
    return "unknown"

  normalised = text.replace("-", " ")  # noqa: E111
  normalised = "_".join(normalised.split())  # noqa: E111
  normalised = normalised.lower()  # noqa: E111

  return normalised or "unknown"  # noqa: E111


def _stringify_breaker_name(name: Any) -> str:
  """Return the original breaker mapping key coerced to a string."""  # noqa: E111

  if isinstance(name, str) and name:  # noqa: E111
    return name

  for candidate in (name, repr(name)):  # noqa: E111
    try:
      text = str(candidate)  # noqa: E111
    except Exception:  # pragma: no cover - defensive fallback
      continue  # noqa: E111
    if text and not text.isspace():
      return text  # noqa: E111

  return f"breaker_{id(name)}"  # noqa: E111


def _coerce_int(value: Any) -> int:
  """Return ``value`` normalised as an integer for diagnostics payloads."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return int(value)

  try:  # noqa: E111
    return int(value)
  except ValueError:  # noqa: E111
    try:
      return int(float(value))  # noqa: E111
    except ValueError:
      return 0  # noqa: E111
    except TypeError:
      return 0  # noqa: E111
  except TypeError:  # noqa: E111
    try:
      return int(float(value))  # noqa: E111
    except ValueError:
      return 0  # noqa: E111
    except TypeError:
      return 0  # noqa: E111


def _normalise_string_list(value: Any) -> list[str]:
  """Return ``value`` coerced into a list of non-empty strings."""  # noqa: E111

  if value is None:  # noqa: E111
    return []

  if isinstance(value, str):  # noqa: E111
    text = value.strip()
    return [text] if text else []

  if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):  # noqa: E111
    items: list[str] = []
    for entry in value:
      if isinstance(entry, str):  # noqa: E111
        candidate = entry.strip()
      else:  # noqa: E111
        try:
          candidate = str(entry).strip()  # noqa: E111
        except Exception:  # pragma: no cover - defensive fallback
          continue  # noqa: E111
      if candidate:  # noqa: E111
        items.append(candidate)
    return items

  try:  # noqa: E111
    text = str(value).strip()
  except Exception:  # pragma: no cover - defensive fallback  # noqa: E111
    return []

  return [text] if text else []  # noqa: E111


def _timestamp_from_datetime(value: datetime) -> float | None:
  """Return a POSIX timestamp for ``value`` with robust fallbacks."""  # noqa: E111

  convert = getattr(dt_util, "as_timestamp", None)  # noqa: E111
  if callable(convert):  # noqa: E111
    try:
      return float(convert(value))  # noqa: E111
    except TypeError, ValueError, OverflowError:
      return None  # noqa: E111

  as_utc = getattr(dt_util, "as_utc", None)  # noqa: E111
  try:  # noqa: E111
    aware = as_utc(value) if callable(as_utc) else value
  except (  # noqa: E111
    TypeError,
    ValueError,
    AttributeError,
  ):  # pragma: no cover - compat guard
    aware = value

  if aware.tzinfo is None:  # noqa: E111
    aware = aware.replace(tzinfo=UTC)

  try:  # noqa: E111
    return float(aware.timestamp())
  except OverflowError, OSError, ValueError:  # noqa: E111
    return None


def _coerce_float(value: Any) -> float | None:
  """Return ``value`` as a finite float when possible."""  # noqa: E111

  if value is None:  # noqa: E111
    return None

  if isinstance(value, bool):  # noqa: E111
    value = int(value)

  if isinstance(value, datetime):  # noqa: E111
    return _timestamp_from_datetime(value)

  if isinstance(value, date) and not isinstance(value, datetime):  # noqa: E111
    try:
      start_of_day = dt_util.start_of_local_day(value)  # noqa: E111
    except TypeError, ValueError, AttributeError:
      # ``start_of_local_day`` may be unavailable in some compat paths.  # noqa: E114
      start_of_day = datetime(  # noqa: E111
        value.year,
        value.month,
        value.day,
        tzinfo=UTC,
      )
    return _timestamp_from_datetime(start_of_day)

  if isinstance(value, str):  # noqa: E111
    try:
      parsed = dt_util.parse_datetime(value)  # noqa: E111
    except ValueError:
      parsed = None  # noqa: E111
    except TypeError:
      parsed = None  # noqa: E111
    if parsed is not None:
      return _timestamp_from_datetime(parsed)  # noqa: E111

  try:  # noqa: E111
    number = float(value)
  except ValueError:  # noqa: E111
    return None
  except TypeError:  # noqa: E111
    return None

  if not isfinite(number):  # noqa: E111
    return None

  return number  # noqa: E111


def _store_resilience_diagnostics(
  coordinator: PawControlCoordinator,
  payload: CoordinatorResilienceDiagnostics,
) -> None:
  """Persist the latest resilience diagnostics for reuse by runtime telemetry."""  # noqa: E111

  runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)  # noqa: E111
  if runtime_data is None:  # noqa: E111
    return

  update_runtime_resilience_diagnostics(runtime_data, payload)  # noqa: E111


def _clear_resilience_diagnostics(coordinator: PawControlCoordinator) -> None:
  """Remove stored resilience telemetry when no breakers are available."""  # noqa: E111

  runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)  # noqa: E111
  if runtime_data is None:  # noqa: E111
    return

  update_runtime_resilience_diagnostics(runtime_data, None)  # noqa: E111


def collect_resilience_diagnostics(
  coordinator: PawControlCoordinator,
) -> CoordinatorResilienceDiagnostics:
  """Return a structured resilience diagnostics payload for the coordinator."""  # noqa: E111

  payload: CoordinatorResilienceDiagnostics = {}  # noqa: E111

  manager = getattr(coordinator, "resilience_manager", None)  # noqa: E111
  if manager is None:  # noqa: E111
    _clear_resilience_diagnostics(coordinator)
    return payload

  fetch = getattr(manager, "get_all_circuit_breakers", None)  # noqa: E111
  if not callable(fetch):  # noqa: E111
    _clear_resilience_diagnostics(coordinator)
    return payload

  try:  # noqa: E111
    raw = fetch()
  except Exception as err:  # pragma: no cover - diagnostics guard  # noqa: E111
    coordinator.logger.debug(
      "Failed to collect circuit breaker stats: %s",
      err,
    )
    _clear_resilience_diagnostics(coordinator)
    return payload

  if isinstance(raw, Mapping):  # noqa: E111
    item_source: Iterable[tuple[Any, Any]] = raw.items()
  elif isinstance(raw, Iterable) and not isinstance(raw, str | bytes | bytearray):  # noqa: E111

    def _iter_items() -> Iterable[tuple[Any, Any]]:
      for item in raw:  # noqa: E111
        if isinstance(item, tuple) and len(item) == 2:
          yield item  # noqa: E111
        else:
          yield str(item), item  # noqa: E111

    item_source = _iter_items()
  else:  # noqa: E111
    coordinator.logger.debug(
      "Unexpected circuit breaker diagnostics payload: %s",
      type(raw).__name__,
    )
    _clear_resilience_diagnostics(coordinator)
    return payload

  breakers: dict[str, CircuitBreakerStatsPayload] = {}  # noqa: E111

  for name, stats in item_source:  # noqa: E111
    state = _extract_stat_value(stats, "state")
    candidate = getattr(state, "value", state)
    if isinstance(candidate, str):
      state_value = candidate.strip() or "unknown"  # noqa: E111
    elif candidate is None:
      state_value = "unknown"  # noqa: E111
    else:
      text = str(candidate)  # noqa: E111
      state_value = "unknown" if not text or text.isspace() else text  # noqa: E111

    breaker_id = _normalise_breaker_id(name, stats)
    mapping_key = _stringify_breaker_name(name)

    entry: CircuitBreakerStatsPayload = {
      "breaker_id": breaker_id,
      "state": str(state_value),
      "failure_count": _coerce_int(
        _extract_stat_value(stats, "failure_count", 0),
      ),
      "success_count": _coerce_int(
        _extract_stat_value(stats, "success_count", 0),
      ),
      "last_failure_time": _coerce_float(
        _extract_stat_value(stats, "last_failure_time"),
      ),
      "last_state_change": _coerce_float(
        _extract_stat_value(stats, "last_state_change"),
      ),
      "total_calls": _coerce_int(_extract_stat_value(stats, "total_calls", 0)),
      "total_failures": _coerce_int(
        _extract_stat_value(stats, "total_failures", 0),
      ),
      "total_successes": _coerce_int(
        _extract_stat_value(stats, "total_successes", 0),
      ),
      "rejected_calls": _coerce_int(
        _extract_stat_value(stats, "rejected_calls", 0),
      ),
    }

    last_success_time = _coerce_float(
      _extract_stat_value(stats, "last_success_time"),
    )
    if last_success_time is not None:
      entry["last_success_time"] = last_success_time  # noqa: E111

    last_rejection_time = _coerce_float(
      _extract_stat_value(stats, "last_rejection_time"),
    )
    if last_rejection_time is not None:
      entry["last_rejection_time"] = last_rejection_time  # noqa: E111

    breakers[mapping_key] = entry

  if not breakers:  # noqa: E111
    _clear_resilience_diagnostics(coordinator)
    return payload

  payload["breakers"] = breakers  # noqa: E111
  summary = _summarise_resilience(breakers)  # noqa: E111
  payload["summary"] = summary  # noqa: E111
  _store_resilience_diagnostics(coordinator, payload)  # noqa: E111
  return payload  # noqa: E111


def build_update_statistics(
  coordinator: PawControlCoordinator,
) -> CoordinatorStatisticsPayload:
  """Return lightweight update statistics for diagnostics endpoints."""  # noqa: E111

  cache_metrics = coordinator._modules.cache_metrics()  # noqa: E111
  repair_summary = _fetch_cache_repair_summary(coordinator)  # noqa: E111
  reconfigure_summary = _fetch_reconfigure_summary(coordinator)  # noqa: E111
  stats = coordinator._metrics.update_statistics(  # noqa: E111
    cache_entries=cache_metrics.entries,
    cache_hit_rate=cache_metrics.hit_rate,
    last_update=coordinator.last_update_time,
    interval=coordinator.update_interval,
    repair_summary=repair_summary,
  )
  runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)  # noqa: E111
  stats["runtime_store"] = _build_runtime_store_summary(  # noqa: E111
    coordinator,
    runtime_data,
    record_event=False,
  )
  stats["entity_budget"] = _normalise_entity_budget_summary(  # noqa: E111
    coordinator._entity_budget.summary(),
  )
  stats["adaptive_polling"] = _normalise_adaptive_diagnostics(  # noqa: E111
    coordinator._adaptive_polling.as_diagnostics(),
  )
  rejection_metrics = default_rejection_metrics()  # noqa: E111

  resilience = collect_resilience_diagnostics(coordinator)  # noqa: E111
  if resilience:  # noqa: E111
    stats["resilience"] = resilience
    summary_payload = resilience.get("summary")
    if isinstance(summary_payload, Mapping):
      rejection_metrics = derive_rejection_metrics(summary_payload)  # noqa: E111

  stats["rejection_metrics"] = rejection_metrics  # noqa: E111

  performance_metrics = stats["performance_metrics"]  # noqa: E111
  merge_rejection_metric_values(performance_metrics, rejection_metrics)  # noqa: E111
  if reconfigure_summary is not None:  # noqa: E111
    stats["reconfigure"] = reconfigure_summary
  return stats  # noqa: E111


def build_runtime_statistics(
  coordinator: PawControlCoordinator,
) -> CoordinatorRuntimeStatisticsPayload:
  """Return expanded statistics for diagnostics pages."""  # noqa: E111

  cache_metrics = coordinator._modules.cache_metrics()  # noqa: E111
  repair_summary = _fetch_cache_repair_summary(coordinator)  # noqa: E111
  reconfigure_summary = _fetch_reconfigure_summary(coordinator)  # noqa: E111
  stats = coordinator._metrics.runtime_statistics(  # noqa: E111
    cache_metrics=cache_metrics,
    total_dogs=len(coordinator.registry),
    last_update=coordinator.last_update_time,
    interval=coordinator.update_interval,
    repair_summary=repair_summary,
  )
  runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)  # noqa: E111
  stats["runtime_store"] = _build_runtime_store_summary(  # noqa: E111
    coordinator,
    runtime_data,
    record_event=True,
  )
  stats["bool_coercion"] = update_runtime_bool_coercion_summary(runtime_data)  # noqa: E111
  stats["entity_budget"] = _normalise_entity_budget_summary(  # noqa: E111
    coordinator._entity_budget.summary(),
  )
  stats["adaptive_polling"] = _normalise_adaptive_diagnostics(  # noqa: E111
    coordinator._adaptive_polling.as_diagnostics(),
  )
  performance_stats_payload = get_runtime_performance_stats(  # noqa: E111
    cast(PawControlRuntimeData | None, runtime_data),
  )
  guard_metrics = resolve_service_guard_metrics(performance_stats_payload)  # noqa: E111
  entity_factory_guard = resolve_entity_factory_guard_metrics(  # noqa: E111
    performance_stats_payload,
  )
  rejection_metrics = default_rejection_metrics()  # noqa: E111

  resilience = collect_resilience_diagnostics(coordinator)  # noqa: E111
  if resilience:  # noqa: E111
    stats["resilience"] = resilience
    summary_payload = resilience.get("summary")
    if isinstance(summary_payload, Mapping):
      rejection_metrics = derive_rejection_metrics(summary_payload)  # noqa: E111

  stats["rejection_metrics"] = rejection_metrics  # noqa: E111

  service_execution: CoordinatorServiceExecutionSummary = {  # noqa: E111
    "guard_metrics": guard_metrics,
    "entity_factory_guard": entity_factory_guard,
    "rejection_metrics": rejection_metrics,
  }
  stats["service_execution"] = service_execution  # noqa: E111

  performance_metrics = stats.get("performance_metrics")  # noqa: E111
  if isinstance(performance_metrics, dict):  # noqa: E111
    merge_rejection_metric_values(performance_metrics, rejection_metrics)

  error_summary = stats.get("error_summary")  # noqa: E111
  if isinstance(error_summary, dict):  # noqa: E111
    error_summary["rejection_rate"] = rejection_metrics["rejection_rate"]
    error_summary["rejected_call_count"] = rejection_metrics["rejected_call_count"]
    error_summary["rejection_breaker_count"] = rejection_metrics[
      "rejection_breaker_count"
    ]
    error_summary["open_breaker_count"] = rejection_metrics["open_breaker_count"]
    error_summary["half_open_breaker_count"] = rejection_metrics[
      "half_open_breaker_count"
    ]
    error_summary["unknown_breaker_count"] = rejection_metrics["unknown_breaker_count"]
    error_summary["open_breakers"] = list(
      rejection_metrics["open_breakers"],
    )
    error_summary["open_breaker_ids"] = list(
      rejection_metrics["open_breaker_ids"],
    )
    error_summary["half_open_breakers"] = list(
      rejection_metrics["half_open_breakers"],
    )
    error_summary["half_open_breaker_ids"] = list(
      rejection_metrics["half_open_breaker_ids"],
    )
    error_summary["unknown_breakers"] = list(
      rejection_metrics["unknown_breakers"],
    )
    error_summary["unknown_breaker_ids"] = list(
      rejection_metrics["unknown_breaker_ids"],
    )
    error_summary["rejection_breaker_ids"] = list(
      rejection_metrics["rejection_breaker_ids"],
    )
    error_summary["rejection_breakers"] = list(
      rejection_metrics["rejection_breakers"],
    )
  if reconfigure_summary is not None:  # noqa: E111
    stats["reconfigure"] = reconfigure_summary
  return stats  # noqa: E111


@callback
def ensure_background_task(
  coordinator: PawControlCoordinator,
  interval: timedelta,
) -> None:
  """Start the maintenance task if not already running."""  # noqa: E111

  if coordinator._maintenance_unsub is None:  # noqa: E111
    coordinator._maintenance_unsub = async_track_time_interval(
      coordinator.hass,
      coordinator._async_maintenance,
      interval,
    )


async def run_maintenance(coordinator: PawControlCoordinator) -> None:
  """Perform periodic maintenance work for caches and metrics."""  # noqa: E111

  runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)  # noqa: E111
  now = dt_util.utcnow()  # noqa: E111

  diagnostics = None  # noqa: E111
  metadata: MaintenanceMetadataPayload = {  # noqa: E111
    "schedule": "hourly",
    "runtime_available": runtime_data is not None,
  }
  details: MaintenanceMetadataPayload = {}  # noqa: E111

  with performance_tracker(  # noqa: E111
    runtime_data,
    "analytics_collector_metrics",
    max_samples=50,
  ) as perf:
    try:
      expired = coordinator._modules.cleanup_expired(now)  # noqa: E111
      if expired:  # noqa: E111
        coordinator.logger.debug(
          "Cleaned %d expired cache entries",
          expired,
        )
        details["expired_entries"] = expired

      if (  # noqa: E111
        coordinator._metrics.consecutive_errors > 0 and coordinator.last_update_success
      ):
        hours_since_last_update = (
          now - (coordinator.last_update_time or now)
        ).total_seconds() / 3600
        if hours_since_last_update > 1:
          previous = coordinator._metrics.consecutive_errors  # noqa: E111
          coordinator._metrics.reset_consecutive()  # noqa: E111
          coordinator.logger.info(  # noqa: E111
            "Reset consecutive error count (%d) after %d hours of stability",
            previous,
            int(hours_since_last_update),
          )
          details["consecutive_errors_reset"] = previous  # noqa: E111
          details["hours_since_last_update"] = round(  # noqa: E111
            hours_since_last_update,
            2,
          )

      diagnostics = capture_cache_diagnostics(runtime_data)  # noqa: E111
      if diagnostics is not None:  # noqa: E111
        details["cache_snapshot"] = True

      record_maintenance_result(  # noqa: E111
        runtime_data,
        task="coordinator_maintenance",
        status="success",
        diagnostics=diagnostics,
        metadata=metadata,
        details=details,
      )
    except Exception as err:
      perf.mark_failure(err)  # noqa: E111
      if diagnostics is None:  # noqa: E111
        diagnostics = capture_cache_diagnostics(runtime_data)
      record_maintenance_result(  # noqa: E111
        runtime_data,
        task="coordinator_maintenance",
        status="error",
        message=str(err),
        diagnostics=diagnostics,
        metadata=metadata,
        details=details,
      )
      raise  # noqa: E111


async def shutdown(coordinator: PawControlCoordinator) -> None:
  """Shutdown hook for coordinator teardown."""  # noqa: E111

  if coordinator._maintenance_unsub:  # noqa: E111
    coordinator._maintenance_unsub()
    coordinator._maintenance_unsub = None

  coordinator._data.clear()  # noqa: E111
  coordinator._modules.clear_caches()  # noqa: E111
  coordinator.logger.info("Coordinator shutdown completed successfully")  # noqa: E111
