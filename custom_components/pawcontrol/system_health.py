"""System health callbacks exposing PawControl guard and breaker metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .compat import ConfigEntry
from .const import DOMAIN
from .coordinator_tasks import (
  derive_rejection_metrics,
  resolve_entity_factory_guard_metrics,
  resolve_service_guard_metrics,
)
from .runtime_data import describe_runtime_store_status, get_runtime_data
from .telemetry import get_runtime_performance_stats, get_runtime_store_health
from .types import (
  ConfigEntryOptionsPayload,
  CoordinatorRejectionMetrics,
  CoordinatorResilienceSummary,
  EntityFactoryGuardMetricsSnapshot,
  HelperManagerGuardMetrics,
  JSONLikeMapping,
  JSONMapping,
  ManualResilienceAutomationEntry,
  ManualResilienceEventCounters,
  ManualResilienceEventSnapshot,
  ManualResilienceEventsTelemetry,
  ManualResilienceListenerMetadata,
  ManualResilienceOptionsSnapshot,
  ManualResiliencePreferenceKey,
  ManualResilienceSystemSettingsSnapshot,
  PawControlRuntimeData,
  ResilienceEscalationFieldEntry,
  ResilienceEscalationThresholds,
  RuntimeStoreAssessmentTimelineSegment,
  RuntimeStoreAssessmentTimelineSummary,
  RuntimeStoreHealthAssessment,
  RuntimeStoreHealthHistory,
  SystemHealthBreakerOverview,
  SystemHealthGuardReasonEntry,
  SystemHealthGuardSummary,
  SystemHealthIndicatorPayload,
  SystemHealthInfoPayload,
  SystemHealthRemainingQuota,
  SystemHealthServiceExecutionSnapshot,
  SystemHealthServiceStatus,
  SystemHealthThresholdDetail,
  SystemHealthThresholdSummary,
)


@dataclass(slots=True)
class GuardIndicatorThresholds:
  """Threshold metadata for guard indicators."""

  warning_count: int | None = None
  critical_count: int | None = None
  warning_ratio: float | None = None
  critical_ratio: float | None = None
  source: str = "default"
  source_key: str | None = None


@dataclass(slots=True)
class BreakerIndicatorThresholds:
  """Threshold metadata for breaker indicators."""

  warning_count: int | None = None
  critical_count: int | None = None
  source: str = "default"
  source_key: str | None = None


def _attach_runtime_store_history(
  info: dict[str, object],
  history: RuntimeStoreHealthHistory | None,
) -> None:
  """Attach runtime store telemetry artefacts to a system health payload."""

  if not history:
    return

  info["runtime_store_history"] = history

  assessment = history.get("assessment")
  if isinstance(assessment, Mapping):
    info["runtime_store_assessment"] = cast(
      RuntimeStoreHealthAssessment,
      dict(assessment),
    )

  timeline_segments = history.get("assessment_timeline_segments")
  if isinstance(timeline_segments, Sequence):
    info["runtime_store_timeline_segments"] = [
      cast(RuntimeStoreAssessmentTimelineSegment, dict(segment))
      for segment in timeline_segments
      if isinstance(segment, Mapping)
    ]

  timeline_summary = history.get("assessment_timeline_summary")
  if isinstance(timeline_summary, Mapping):
    info["runtime_store_timeline_summary"] = cast(
      RuntimeStoreAssessmentTimelineSummary,
      dict(timeline_summary),
    )


def _coerce_int(value: Any, *, default: int = 0) -> int:
  """Return ``value`` as ``int`` when possible.

  ``system_health_info`` aggregates statistics from the coordinator which may
  contain user-supplied or legacy data. Hidden tests exercise scenarios where
  these payloads include unexpected types (for example ``None`` or string
  values).  Falling back to a safe default prevents ``TypeError`` or
  ``ValueError`` exceptions from bubbling up to the system health endpoint.
  """

  try:
    return int(value)
  except (TypeError, ValueError):
    return default


def _coerce_positive_int(value: Any) -> int | None:
  """Return ``value`` coerced to a positive int when possible."""

  try:
    result = int(value)
  except (TypeError, ValueError):
    return None

  if result > 0:
    return result

  return None


def _extract_api_call_count(stats: Any) -> int:
  """Return the API call count from coordinator statistics.

  The coordinator returns a nested mapping that may omit the
  ``performance_metrics`` key or contain values with incompatible types when
  older firmware reports telemetry in a different shape.  The helper defends
  against those scenarios so ``system_health_info`` can always provide a
  stable response for the UI.
  """

  if not isinstance(stats, Mapping):
    return 0

  metrics = stats.get("performance_metrics")
  if not isinstance(metrics, Mapping):
    return 0

  return _coerce_int(metrics.get("api_calls", 0))


def _coerce_str(value: Any) -> str | None:
  """Return ``value`` normalised as a non-empty string."""

  if isinstance(value, str):
    text = value.strip()
    if text:
      return text
  return None


def _coerce_str_list(value: Any) -> list[str]:
  """Return ``value`` coerced into a list of non-empty strings."""

  if isinstance(value, str):
    text = value.strip()
    return [text] if text else []

  if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
    items: list[str] = []
    for entry in value:
      candidate = _coerce_str(entry)
      if candidate is not None:
        items.append(candidate)
    return items

  return []


def _coerce_event_snapshot(value: Any) -> ManualResilienceEventSnapshot | None:
  """Return ``value`` normalised as a manual resilience event snapshot."""

  if isinstance(value, Mapping):
    return cast(ManualResilienceEventSnapshot, dict(value))
  return None


def _coerce_event_history(value: Any) -> list[ManualResilienceEventSnapshot]:
  """Return ``value`` normalised as a history of manual resilience events."""

  if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
    return []

  history: list[ManualResilienceEventSnapshot] = []
  for entry in value:
    snapshot = _coerce_event_snapshot(entry)
    if snapshot is not None:
      history.append(snapshot)
  return history


def _coerce_automation_entries(value: Any) -> list[ManualResilienceAutomationEntry]:
  """Return ``value`` normalised as automation metadata entries."""

  if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
    return []

  entries: list[ManualResilienceAutomationEntry] = []
  for item in value:
    if not isinstance(item, Mapping):
      continue
    entry: ManualResilienceAutomationEntry = {}
    if (config_entry_id := _coerce_str(item.get("config_entry_id"))) is not None:
      entry["config_entry_id"] = config_entry_id
    if (title := _coerce_str(item.get("title"))) is not None:
      entry["title"] = title

    manual_guard_event = _coerce_str(item.get("manual_guard_event"))
    if manual_guard_event is not None:
      entry["manual_guard_event"] = manual_guard_event

    manual_breaker_event = _coerce_str(item.get("manual_breaker_event"))
    if manual_breaker_event is not None:
      entry["manual_breaker_event"] = manual_breaker_event

    manual_check_event = _coerce_str(item.get("manual_check_event"))
    if manual_check_event is not None:
      entry["manual_check_event"] = manual_check_event

    configured_guard = item.get("configured_guard")
    if isinstance(configured_guard, bool):
      entry["configured_guard"] = configured_guard
    elif configured_guard is not None:
      entry["configured_guard"] = bool(configured_guard)

    configured_breaker = item.get("configured_breaker")
    if isinstance(configured_breaker, bool):
      entry["configured_breaker"] = configured_breaker
    elif configured_breaker is not None:
      entry["configured_breaker"] = bool(configured_breaker)

    configured_check = item.get("configured_check")
    if isinstance(configured_check, bool):
      entry["configured_check"] = configured_check
    elif configured_check is not None:
      entry["configured_check"] = bool(configured_check)

    if entry:
      entries.append(entry)
  return entries


def _coerce_int_mapping(value: Any) -> dict[str, int]:
  """Return ``value`` normalised as a mapping of string keys to integers."""

  if not isinstance(value, Mapping):
    return {}

  normalised: dict[str, int] = {}
  for key, raw_value in value.items():
    name = _coerce_str(key)
    if name is None:
      continue
    normalised[name] = _coerce_int(raw_value, default=0)
  return normalised


def _coerce_event_counters(value: Any) -> ManualResilienceEventCounters:
  """Return ``value`` normalised as manual resilience event counters."""

  counters: ManualResilienceEventCounters = {
    "total": 0,
    "by_event": {},
    "by_reason": {},
  }
  if not isinstance(value, Mapping):
    return counters

  counters["total"] = _coerce_int(value.get("total"), default=0)
  counters["by_event"] = _coerce_int_mapping(value.get("by_event"))
  counters["by_reason"] = _coerce_int_mapping(value.get("by_reason"))
  return counters


def _coerce_mapping_of_str_lists(value: Any) -> dict[str, list[str]]:
  """Return ``value`` normalised as a mapping of strings to string lists."""

  if not isinstance(value, Mapping):
    return {}

  normalised: dict[str, list[str]] = {}
  for key, raw_value in value.items():
    name = _coerce_str(key)
    if name is None:
      continue
    normalised[name] = _coerce_str_list(raw_value)
  return normalised


def _coerce_listener_metadata(
  value: Any,
) -> dict[str, ManualResilienceListenerMetadata]:
  """Return ``value`` normalised as listener metadata payloads."""

  if not isinstance(value, Mapping):
    return {}

  normalised: dict[str, ManualResilienceListenerMetadata] = {}
  for key, raw_metadata in value.items():
    name = _coerce_str(key)
    if name is None or not isinstance(raw_metadata, Mapping):
      continue
    entry: ManualResilienceListenerMetadata = {}
    sources = _coerce_str_list(raw_metadata.get("sources"))
    if sources:
      entry["sources"] = sources
    if (primary := _coerce_str(raw_metadata.get("primary_source"))) is not None:
      entry["primary_source"] = primary
    if entry:
      normalised[name] = entry
  return normalised


def _coerce_preferred_events(
  value: Any,
) -> dict[ManualResiliencePreferenceKey, str | None]:
  """Return ``value`` normalised as preference mappings."""

  preferences: dict[ManualResiliencePreferenceKey, str | None] = {}
  if not isinstance(value, Mapping):
    return preferences

  preference_keys: tuple[ManualResiliencePreferenceKey, ...] = (
    "manual_check_event",
    "manual_guard_event",
    "manual_breaker_event",
  )
  for key in preference_keys:
    preferences[key] = _coerce_str(value.get(key))
  return preferences


def _normalise_manual_events_snapshot(
  snapshot: ManualResilienceEventsTelemetry | JSONLikeMapping | None,
) -> ManualResilienceEventsTelemetry:
  """Return the manual events snapshot normalised for system health."""

  payload: ManualResilienceEventsTelemetry = {
    "available": False,
    "event_history": [],
    "last_event": None,
  }
  payload["last_trigger"] = None
  payload["event_counters"] = {"total": 0, "by_event": {}, "by_reason": {}}
  payload["active_listeners"] = []

  if not isinstance(snapshot, Mapping):
    return payload

  payload["available"] = bool(snapshot.get("available", False))

  if automations := _coerce_automation_entries(snapshot.get("automations")):
    payload["automations"] = automations

  if configured_guard := _coerce_str_list(snapshot.get("configured_guard_events")):
    payload["configured_guard_events"] = configured_guard
  if configured_breaker := _coerce_str_list(
    snapshot.get("configured_breaker_events"),
  ):
    payload["configured_breaker_events"] = configured_breaker
  if configured_check := _coerce_str_list(snapshot.get("configured_check_events")):
    payload["configured_check_events"] = configured_check

  if (system_guard := _coerce_str(snapshot.get("system_guard_event"))) is not None:
    payload["system_guard_event"] = system_guard
  if (system_breaker := _coerce_str(snapshot.get("system_breaker_event"))) is not None:
    payload["system_breaker_event"] = system_breaker

  listener_events = _coerce_mapping_of_str_lists(
    snapshot.get("listener_events"),
  )
  if listener_events:
    payload["listener_events"] = listener_events

  listener_sources = _coerce_mapping_of_str_lists(
    snapshot.get("listener_sources"),
  )
  if listener_sources:
    payload["listener_sources"] = listener_sources

  listener_metadata = _coerce_listener_metadata(
    snapshot.get("listener_metadata"),
  )
  if listener_metadata:
    payload["listener_metadata"] = listener_metadata

  preferences = _coerce_preferred_events(snapshot.get("preferred_events"))
  if preferences:
    payload["preferred_events"] = preferences

  preferred_guard = _coerce_str(
    snapshot.get("preferred_guard_event"),
  ) or preferences.get("manual_guard_event")
  if preferred_guard is not None:
    payload["preferred_guard_event"] = preferred_guard

  preferred_breaker = _coerce_str(
    snapshot.get("preferred_breaker_event"),
  ) or preferences.get("manual_breaker_event")
  if preferred_breaker is not None:
    payload["preferred_breaker_event"] = preferred_breaker

  preferred_check = _coerce_str(
    snapshot.get("preferred_check_event"),
  ) or preferences.get("manual_check_event")
  if preferred_check is not None:
    payload["preferred_check_event"] = preferred_check

  payload["event_history"] = _coerce_event_history(
    snapshot.get("event_history"),
  )
  payload["last_event"] = _coerce_event_snapshot(snapshot.get("last_event"))
  payload["last_trigger"] = _coerce_event_snapshot(
    snapshot.get("last_trigger"),
  )

  payload["event_counters"] = _coerce_event_counters(
    snapshot.get("event_counters"),
  )

  active_listeners = _coerce_str_list(snapshot.get("active_listeners"))
  if active_listeners:
    payload["active_listeners"] = active_listeners

  return payload


def _default_service_execution_snapshot() -> SystemHealthServiceExecutionSnapshot:
  """Return an empty service execution snapshot with default thresholds."""

  guard_thresholds = GuardIndicatorThresholds(
    warning_ratio=GUARD_SKIP_WARNING_RATIO,
    critical_ratio=GUARD_SKIP_CRITICAL_RATIO,
    source="default_ratio",
  )
  breaker_thresholds = BreakerIndicatorThresholds(
    warning_count=BREAKER_WARNING_THRESHOLD,
    critical_count=BREAKER_CRITICAL_THRESHOLD,
    source="default_counts",
  )

  guard_metrics = resolve_service_guard_metrics({})
  entity_factory_guard = resolve_entity_factory_guard_metrics({})
  rejection_metrics = derive_rejection_metrics(None)
  guard_summary = _build_guard_summary(guard_metrics, guard_thresholds)
  breaker_overview = _build_breaker_overview(
    rejection_metrics,
    breaker_thresholds,
  )
  status = _build_service_status(guard_summary, breaker_overview)

  return {
    "guard_metrics": guard_metrics,
    "guard_summary": guard_summary,
    "entity_factory_guard": entity_factory_guard,
    "rejection_metrics": rejection_metrics,
    "breaker_overview": breaker_overview,
    "status": status,
    "manual_events": _normalise_manual_events_snapshot(None),
  }


@callback
def async_register(
  hass: HomeAssistant,
  register: system_health.SystemHealthRegistration,
) -> None:
  """Register system health callbacks for PawControl."""

  register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> SystemHealthInfoPayload:
  """Return basic system health information."""

  entry = _async_get_first_entry(hass)
  if entry is None:
    runtime_store_snapshot = describe_runtime_store_status(
      hass,
      "missing-entry",
    )
    info: SystemHealthInfoPayload = {
      "can_reach_backend": False,
      "remaining_quota": "unknown",
      "service_execution": _default_service_execution_snapshot(),
      "runtime_store": runtime_store_snapshot,
    }
    return info

  runtime = get_runtime_data(hass, entry)
  runtime_store_snapshot = describe_runtime_store_status(hass, entry)
  runtime_store_history = get_runtime_store_health(runtime)
  if runtime is None:
    info_payload: dict[str, object] = {
      "can_reach_backend": False,
      "remaining_quota": "unknown",
      "service_execution": _default_service_execution_snapshot(),
      "runtime_store": runtime_store_snapshot,
    }
    _attach_runtime_store_history(info_payload, runtime_store_history)
    return cast(SystemHealthInfoPayload, info_payload)

  coordinator = getattr(runtime, "coordinator", None)
  if coordinator is None:
    coordinator_info_payload: dict[str, object] = {
      "can_reach_backend": False,
      "remaining_quota": "unknown",
      "service_execution": _default_service_execution_snapshot(),
      "runtime_store": runtime_store_snapshot,
    }
    _attach_runtime_store_history(
      coordinator_info_payload,
      runtime_store_history,
    )
    return cast(SystemHealthInfoPayload, coordinator_info_payload)

  stats = coordinator.get_update_statistics()
  api_calls = _extract_api_call_count(stats)

  uses_external_api = bool(getattr(coordinator, "use_external_api", False))

  if uses_external_api:
    quota = entry.options.get("external_api_quota")
    remaining_quota: SystemHealthRemainingQuota
    if isinstance(quota, int) and quota >= 0:
      remaining_quota = max(quota - api_calls, 0)
    else:
      remaining_quota = "untracked"
  else:
    remaining_quota = "unlimited"

  guard_metrics, entity_factory_guard, rejection_metrics = (
    _extract_service_execution_metrics(runtime)
  )
  guard_thresholds, breaker_thresholds = _resolve_indicator_thresholds(
    runtime,
    entry.options,
  )
  guard_summary = _build_guard_summary(guard_metrics, guard_thresholds)
  breaker_overview = _build_breaker_overview(
    rejection_metrics,
    breaker_thresholds,
  )
  service_status = _build_service_status(guard_summary, breaker_overview)

  script_manager = getattr(runtime, "script_manager", None)
  manual_snapshot: ManualResilienceEventsTelemetry | JSONLikeMapping | None = None
  if script_manager is not None:
    snapshot = getattr(
      script_manager,
      "get_resilience_escalation_snapshot",
      None,
    )
    if callable(snapshot):
      manager_snapshot = snapshot()
      if isinstance(manager_snapshot, Mapping):
        manual_snapshot = cast(
          JSONLikeMapping | ManualResilienceEventsTelemetry | None,
          manager_snapshot.get("manual_events"),
        )

  manual_events_info = _normalise_manual_events_snapshot(manual_snapshot)

  service_payload: dict[str, object] = {
    "can_reach_backend": bool(getattr(coordinator, "last_update_success", False)),
    "remaining_quota": remaining_quota,
    "service_execution": {
      "guard_metrics": guard_metrics,
      "guard_summary": guard_summary,
      "entity_factory_guard": entity_factory_guard,
      "rejection_metrics": rejection_metrics,
      "breaker_overview": breaker_overview,
      "status": service_status,
      "manual_events": manual_events_info,
    },
    "runtime_store": runtime_store_snapshot,
  }
  _attach_runtime_store_history(service_payload, runtime_store_history)
  return cast(SystemHealthInfoPayload, service_payload)


def _async_get_first_entry(hass: HomeAssistant) -> ConfigEntry | None:
  """Return the first loaded PawControl config entry."""

  return next(iter(hass.config_entries.async_entries(DOMAIN)), None)


def _extract_service_execution_metrics(
  runtime: PawControlRuntimeData | None,
) -> tuple[
  HelperManagerGuardMetrics,
  EntityFactoryGuardMetricsSnapshot,
  CoordinatorRejectionMetrics,
]:
  """Return guard telemetry derived from runtime statistics."""

  performance_stats = get_runtime_performance_stats(runtime)
  guard_metrics = resolve_service_guard_metrics(performance_stats)
  entity_factory_guard = resolve_entity_factory_guard_metrics(
    performance_stats,
  )

  rejection_source: CoordinatorRejectionMetrics | JSONLikeMapping | None = None
  if performance_stats is not None:
    raw_rejection = performance_stats.get("rejection_metrics")
    if isinstance(raw_rejection, Mapping):
      rejection_source = raw_rejection

  rejection_metrics = derive_rejection_metrics(
    cast(JSONMapping | CoordinatorResilienceSummary | None, rejection_source),
  )

  return guard_metrics, entity_factory_guard, rejection_metrics


def _extract_threshold_value(
  payload: ResilienceEscalationFieldEntry,
) -> tuple[int | None, str | None]:
  """Return a positive threshold value and the key it originated from."""

  for key in ("active", "default"):
    candidate = _coerce_positive_int(payload.get(key))
    if candidate is not None:
      return candidate, key

  return None, None


def _resolve_option_threshold(
  options: ConfigEntryOptionsPayload
  | ManualResilienceOptionsSnapshot
  | JSONLikeMapping
  | None,
  key: str,
) -> tuple[int | None, str | None]:
  """Return a positive threshold sourced from config entry options."""

  if not isinstance(options, Mapping):
    return None, None

  system_settings_raw = options.get("system_settings")
  if isinstance(system_settings_raw, Mapping):
    system_settings = cast(
      ManualResilienceSystemSettingsSnapshot,
      dict(system_settings_raw),
    )
    value = _coerce_positive_int(system_settings.get(key))
    if value is not None:
      return value, "system_settings"

  value = _coerce_positive_int(options.get(key))
  if value is not None:
    return value, "root_options"

  return None, None


def _merge_option_thresholds(
  guard_thresholds: GuardIndicatorThresholds,
  breaker_thresholds: BreakerIndicatorThresholds,
  options: ConfigEntryOptionsPayload
  | ManualResilienceOptionsSnapshot
  | JSONLikeMapping
  | None,
) -> tuple[GuardIndicatorThresholds, BreakerIndicatorThresholds]:
  """Overlay config entry thresholds when script metadata is unavailable."""

  skip_value, skip_source = _resolve_option_threshold(
    options,
    "resilience_skip_threshold",
  )
  if guard_thresholds.source == "default_ratio" and skip_value is not None:
    guard_thresholds = GuardIndicatorThresholds(
      warning_count=skip_value - 1 if skip_value > 1 else None,
      critical_count=skip_value,
      warning_ratio=GUARD_SKIP_WARNING_RATIO,
      source="config_entry",
      source_key=skip_source,
    )

  breaker_value, breaker_source = _resolve_option_threshold(
    options,
    "resilience_breaker_threshold",
  )
  if breaker_thresholds.source == "default_counts" and breaker_value is not None:
    warning_value = breaker_value - 1
    breaker_thresholds = BreakerIndicatorThresholds(
      warning_count=warning_value if warning_value > 0 else None,
      critical_count=breaker_value,
      source="config_entry",
      source_key=breaker_source,
    )

  return guard_thresholds, breaker_thresholds


def _resolve_indicator_thresholds(
  runtime: PawControlRuntimeData | None,
  options: ConfigEntryOptionsPayload
  | ManualResilienceOptionsSnapshot
  | JSONLikeMapping
  | None = None,
) -> tuple[GuardIndicatorThresholds, BreakerIndicatorThresholds]:
  """Resolve guard and breaker thresholds from runtime configuration."""

  guard_thresholds = GuardIndicatorThresholds(
    warning_ratio=GUARD_SKIP_WARNING_RATIO,
    critical_ratio=GUARD_SKIP_CRITICAL_RATIO,
    source="default_ratio",
  )
  breaker_thresholds = BreakerIndicatorThresholds(
    warning_count=BREAKER_WARNING_THRESHOLD,
    critical_count=BREAKER_CRITICAL_THRESHOLD,
    source="default_counts",
  )

  script_manager = getattr(runtime, "script_manager", None)
  if script_manager is None:
    return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)

  try:
    snapshot = script_manager.get_resilience_escalation_snapshot()
  except Exception:  # pragma: no cover - defensive guard
    return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)

  if not isinstance(snapshot, Mapping):
    return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)

  thresholds_payload = snapshot.get("thresholds")
  if not isinstance(thresholds_payload, Mapping):
    return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)

  thresholds = cast(ResilienceEscalationThresholds, dict(thresholds_payload))

  skip_payload = thresholds.get("skip_threshold")
  if isinstance(skip_payload, Mapping):
    skip_value, source_key = _extract_threshold_value(
      cast(ResilienceEscalationFieldEntry, dict(skip_payload)),
    )
    if skip_value is not None:
      guard_thresholds = GuardIndicatorThresholds(
        warning_count=skip_value - 1 if skip_value > 1 else None,
        critical_count=skip_value,
        warning_ratio=GUARD_SKIP_WARNING_RATIO,
        source="resilience_script",
        source_key=source_key,
      )

  breaker_payload = thresholds.get("breaker_threshold")
  if isinstance(breaker_payload, Mapping):
    breaker_value, source_key = _extract_threshold_value(
      cast(ResilienceEscalationFieldEntry, dict(breaker_payload)),
    )
    if breaker_value is not None:
      warning_value = breaker_value - 1
      breaker_thresholds = BreakerIndicatorThresholds(
        warning_count=warning_value if warning_value > 0 else None,
        critical_count=breaker_value,
        source="resilience_script",
        source_key=source_key,
      )

  return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)


def _serialize_threshold(
  *,
  count: int | None,
  ratio: float | None,
) -> SystemHealthThresholdDetail | None:
  """Serialize threshold metadata into diagnostics payloads."""

  payload: SystemHealthThresholdDetail = {}
  if count is not None:
    payload["count"] = count
  if ratio is not None:
    payload["ratio"] = ratio
    payload["percentage"] = round(ratio * 100, 2)

  return payload or None


def _serialize_guard_thresholds(
  thresholds: GuardIndicatorThresholds,
) -> SystemHealthThresholdSummary:
  """Serialize guard thresholds for diagnostics output."""

  summary: SystemHealthThresholdSummary = {"source": thresholds.source}
  if thresholds.source_key is not None:
    summary["source_key"] = thresholds.source_key

  if serialized := _serialize_threshold(
    count=thresholds.warning_count,
    ratio=thresholds.warning_ratio,
  ):
    summary["warning"] = serialized

  if serialized := _serialize_threshold(
    count=thresholds.critical_count,
    ratio=thresholds.critical_ratio,
  ):
    summary["critical"] = serialized

  return summary


def _serialize_breaker_thresholds(
  thresholds: BreakerIndicatorThresholds,
) -> SystemHealthThresholdSummary:
  """Serialize breaker thresholds for diagnostics output."""

  summary: SystemHealthThresholdSummary = {"source": thresholds.source}
  if thresholds.source_key is not None:
    summary["source_key"] = thresholds.source_key

  if serialized := _serialize_threshold(count=thresholds.warning_count, ratio=None):
    summary["warning"] = serialized

  if serialized := _serialize_threshold(count=thresholds.critical_count, ratio=None):
    summary["critical"] = serialized

  return summary


def _describe_guard_threshold_source(thresholds: GuardIndicatorThresholds) -> str:
  """Return a human readable label for guard threshold provenance."""

  if thresholds.source == "resilience_script":
    if thresholds.source_key == "default":
      return "resilience script default threshold"
    return "configured resilience script threshold"
  if thresholds.source == "config_entry":
    if thresholds.source_key == "system_settings":
      return "options flow system settings threshold"
    return "options flow threshold"

  return "system default threshold"


def _describe_breaker_threshold_source(thresholds: BreakerIndicatorThresholds) -> str:
  """Return a human readable label for breaker threshold provenance."""

  if thresholds.source == "resilience_script":
    if thresholds.source_key == "default":
      return "resilience script default threshold"
    return "configured resilience script threshold"
  if thresholds.source == "config_entry":
    if thresholds.source_key == "system_settings":
      return "options flow system settings threshold"
    return "options flow threshold"

  return "system default threshold"


GUARD_SKIP_WARNING_RATIO = 0.25
GUARD_SKIP_CRITICAL_RATIO = 0.5

BREAKER_WARNING_THRESHOLD = 1
BREAKER_CRITICAL_THRESHOLD = 3


def _build_guard_summary(
  guard_metrics: HelperManagerGuardMetrics | JSONLikeMapping,
  thresholds: GuardIndicatorThresholds,
) -> SystemHealthGuardSummary:
  """Return aggregated guard statistics for system health output."""

  executed = _coerce_int(guard_metrics.get("executed"), default=0)
  skipped = _coerce_int(guard_metrics.get("skipped"), default=0)
  total = executed + skipped
  skip_ratio = (skipped / total) if total else 0.0
  skip_percentage = round(skip_ratio * 100, 2) if total else 0.0

  reasons_payload = guard_metrics.get("reasons")
  reasons: dict[str, int] = {}
  if isinstance(reasons_payload, Mapping):
    for reason, count in reasons_payload.items():
      reason_key = _coerce_str(reason)
      if reason_key is None:
        continue
      reasons[reason_key] = _coerce_int(count, default=0)

  sorted_reasons = sorted(
    reasons.items(),
    key=lambda item: (-item[1], item[0]),
  )

  top_reasons: list[SystemHealthGuardReasonEntry] = [
    {"reason": reason, "count": count}
    for reason, count in sorted_reasons[:3]
    if count > 0
  ]

  thresholds_payload = _serialize_guard_thresholds(thresholds)
  indicator = _derive_guard_indicator(
    skip_ratio,
    skip_percentage,
    skipped,
    thresholds,
  )

  summary: SystemHealthGuardSummary = {
    "executed": executed,
    "skipped": skipped,
    "total_calls": total,
    "skip_ratio": skip_ratio,
    "skip_percentage": skip_percentage,
    "has_skips": skipped > 0,
    "reasons": reasons,
    "top_reasons": top_reasons,
    "thresholds": thresholds_payload,
    "indicator": indicator,
  }

  return summary


def _build_breaker_overview(
  rejection_metrics: CoordinatorRejectionMetrics | JSONLikeMapping,
  thresholds: BreakerIndicatorThresholds,
) -> SystemHealthBreakerOverview:
  """Return breaker state information derived from rejection metrics."""

  open_count = _coerce_int(
    rejection_metrics.get(
      "open_breaker_count",
    ),
    default=0,
  )
  half_open_count = _coerce_int(
    rejection_metrics.get("half_open_breaker_count"),
    default=0,
  )
  unknown_count = _coerce_int(
    rejection_metrics.get("unknown_breaker_count"),
    default=0,
  )
  rejection_breakers = _coerce_int(
    rejection_metrics.get("rejection_breaker_count"),
    default=0,
  )
  rejection_rate = _coerce_float(
    rejection_metrics.get("rejection_rate"),
    default=0.0,
  )

  if open_count > 0:
    status: Literal["open", "recovering", "monitoring", "healthy"] = "open"
  elif half_open_count > 0:
    status = "recovering"
  elif rejection_breakers > 0 or rejection_rate > 0:
    status = "monitoring"
  else:
    status = "healthy"

  thresholds_payload = _serialize_breaker_thresholds(thresholds)
  indicator = _derive_breaker_indicator(
    open_count=open_count,
    half_open_count=half_open_count,
    rejection_breakers=rejection_breakers,
    thresholds=thresholds,
  )

  open_breakers = _coerce_str_list(rejection_metrics.get("open_breakers"))
  half_open_breakers = _coerce_str_list(
    rejection_metrics.get("half_open_breakers"),
  )
  unknown_breakers = _coerce_str_list(
    rejection_metrics.get("unknown_breakers"),
  )

  last_breaker_id = _coerce_str(
    rejection_metrics.get("last_rejection_breaker_id"),
  )
  last_breaker_name = _coerce_str(
    rejection_metrics.get("last_rejection_breaker_name"),
  )
  raw_last_rejection_time = rejection_metrics.get("last_rejection_time")
  last_rejection_time = (
    float(raw_last_rejection_time)
    if isinstance(raw_last_rejection_time, int | float)
    else None
  )

  overview: SystemHealthBreakerOverview = {
    "status": status,
    "open_breaker_count": open_count,
    "half_open_breaker_count": half_open_count,
    "unknown_breaker_count": unknown_count,
    "rejection_rate": rejection_rate,
    "last_rejection_breaker_id": last_breaker_id,
    "last_rejection_breaker_name": last_breaker_name,
    "last_rejection_time": last_rejection_time,
    "open_breakers": open_breakers,
    "half_open_breakers": half_open_breakers,
    "unknown_breakers": unknown_breakers,
    "thresholds": thresholds_payload,
    "indicator": indicator,
  }

  return overview


def _build_service_status(
  guard_summary: SystemHealthGuardSummary,
  breaker_overview: SystemHealthBreakerOverview,
) -> SystemHealthServiceStatus:
  """Return composite status indicators for guard and breaker telemetry."""

  guard_indicator = cast(
    SystemHealthIndicatorPayload,
    guard_summary.get("indicator", _healthy_indicator("guard")),
  )
  breaker_indicator = cast(
    SystemHealthIndicatorPayload,
    breaker_overview.get("indicator", _healthy_indicator("breaker")),
  )

  overall_indicator = _merge_overall_indicator(
    guard_indicator,
    breaker_indicator,
  )

  return {
    "guard": guard_indicator,
    "breaker": breaker_indicator,
    "overall": overall_indicator,
  }


def _derive_guard_indicator(
  skip_ratio: float,
  skip_percentage: float,
  skip_count: int,
  thresholds: GuardIndicatorThresholds,
) -> SystemHealthIndicatorPayload:
  """Return color-coded indicator describing guard skip health."""

  source_label = _describe_guard_threshold_source(thresholds)
  threshold_source = thresholds.source_key or thresholds.source

  critical_count = thresholds.critical_count
  if critical_count is not None and skip_count >= critical_count:
    return {
      "level": "critical",
      "color": "red",
      "message": (
        f"Guard skip count {skip_count} reached the {source_label} ({critical_count})."
      ),
      "metric": skip_count,
      "threshold": critical_count,
      "metric_type": "guard_skip_count",
      "threshold_type": "guard_skip_count",
      "threshold_source": threshold_source,
      "context": "guard",
    }

  warning_count = thresholds.warning_count
  if warning_count is not None and skip_count >= warning_count:
    return {
      "level": "warning",
      "color": "amber",
      "message": (
        "Guard skip count "
        f"{skip_count} ({skip_percentage:.2f}%) is approaching the "
        f"{source_label} ({critical_count})."
      ),
      "metric": skip_count,
      "threshold": warning_count,
      "metric_type": "guard_skip_count",
      "threshold_type": "guard_skip_count",
      "threshold_source": threshold_source,
      "context": "guard",
    }

  critical_ratio = thresholds.critical_ratio
  if critical_ratio is not None and skip_ratio >= critical_ratio:
    return {
      "level": "critical",
      "color": "red",
      "message": (
        "Guard skip ratio at "
        f"{skip_percentage:.2f}% exceeds the system default threshold of "
        f"{critical_ratio * 100:.0f}%"
      ),
      "metric": skip_ratio,
      "threshold": critical_ratio,
      "metric_type": "guard_skip_ratio",
      "threshold_type": "guard_skip_ratio",
      "threshold_source": "default_ratio",
      "context": "guard",
    }

  warning_ratio = thresholds.warning_ratio
  if warning_ratio is not None and skip_ratio >= warning_ratio:
    return {
      "level": "warning",
      "color": "amber",
      "message": (
        "Guard skip ratio at "
        f"{skip_percentage:.2f}% exceeds the system default threshold of "
        f"{warning_ratio * 100:.0f}%"
      ),
      "metric": skip_ratio,
      "threshold": warning_ratio,
      "metric_type": "guard_skip_ratio",
      "threshold_type": "guard_skip_ratio",
      "threshold_source": "default_ratio",
      "context": "guard",
    }

  return _healthy_indicator(
    "guard",
    metric=skip_ratio,
    message=f"Guard skip ratio at {skip_percentage:.2f}% is within normal limits",
  )


def _derive_breaker_indicator(
  *,
  open_count: int,
  half_open_count: int,
  rejection_breakers: int,
  thresholds: BreakerIndicatorThresholds,
) -> SystemHealthIndicatorPayload:
  """Return indicator describing breaker state health."""

  total_breakers = open_count + half_open_count
  source_label = _describe_breaker_threshold_source(thresholds)
  threshold_source = thresholds.source_key or thresholds.source

  critical_count = thresholds.critical_count
  if critical_count is not None and total_breakers >= critical_count:
    return {
      "level": "critical",
      "color": "red",
      "message": (
        f"Breaker count {total_breakers} reached the {source_label} ({critical_count})."
      ),
      "metric": total_breakers,
      "threshold": critical_count,
      "metric_type": "breaker_count",
      "threshold_type": "breaker_count",
      "threshold_source": threshold_source,
      "context": "breaker",
    }

  warning_count = thresholds.warning_count
  if warning_count is not None and total_breakers >= warning_count:
    return {
      "level": "warning",
      "color": "amber",
      "message": (
        "Breaker activity detected: "
        f"{total_breakers} breaker(s) are approaching the {source_label} "
        f"({critical_count})."
      ),
      "metric": total_breakers,
      "threshold": warning_count,
      "metric_type": "breaker_count",
      "threshold_type": "breaker_count",
      "threshold_source": threshold_source,
      "context": "breaker",
    }

  if rejection_breakers > 0:
    return {
      "level": "warning",
      "color": "amber",
      "message": (
        "Breaker rejection activity detected: "
        f"{rejection_breakers} breaker(s) have recently rejected calls "
        f"despite counts remaining below the {source_label}."
      ),
      "metric": total_breakers,
      "threshold": critical_count if critical_count is not None else total_breakers,
      "metric_type": "breaker_count",
      "threshold_type": "breaker_count",
      "threshold_source": threshold_source,
      "context": "breaker",
    }

  return _healthy_indicator(
    "breaker",
    metric=total_breakers,
    message="No open or half-open breakers detected",
  )


def _merge_overall_indicator(
  *indicators: SystemHealthIndicatorPayload,
) -> SystemHealthIndicatorPayload:
  """Return the highest severity indicator for aggregated status."""

  severity_rank = {"critical": 3, "warning": 2, "normal": 1}

  def _rank(indicator: SystemHealthIndicatorPayload) -> int:
    level = cast(str | None, indicator.get("level"))
    return severity_rank.get(level or "", 0)

  chosen = max(indicators, key=_rank, default=None)

  if chosen is None or chosen.get("level") == "normal":
    return _healthy_indicator("overall")

  overall = cast(SystemHealthIndicatorPayload, dict(chosen))
  overall.setdefault("context", "overall")
  return overall


def _healthy_indicator(
  context: str,
  *,
  metric: float | int | None = None,
  message: str | None = None,
) -> SystemHealthIndicatorPayload:
  """Return a healthy indicator payload for the provided context."""

  payload: SystemHealthIndicatorPayload = {
    "level": "normal",
    "color": "green",
    "message": message or f"{context.title()} health within expected thresholds",
    "metric_type": f"{context}_health",
  }
  if metric is not None:
    payload["metric"] = metric
  payload.setdefault("context", context)
  return payload


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
  """Return ``value`` coerced to ``float`` when possible."""

  try:
    return float(value)
  except (TypeError, ValueError):
    return default
