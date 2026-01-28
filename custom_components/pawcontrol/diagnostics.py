"""Diagnostics helpers for the PawControl integration.

The Platinum development plan requires richly structured diagnostics surfaces
that expose typed coordinator statistics, cache telemetry, and rejection
metrics. This module normalises runtime payloads into JSON-safe snapshots while
redacting sensitive fields so support tooling and the bundled dashboard can
ingest the data without custom adapters.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypedDict, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry, ConfigEntryState
from .const import (
  CONF_API_ENDPOINT,
  CONF_API_TOKEN,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOGS,
  DOMAIN,
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_NOTIFICATIONS,
  MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .coordinator_support import ensure_cache_repair_aggregate
from .coordinator_tasks import (
  default_rejection_metrics,
  derive_rejection_metrics,
  merge_rejection_metric_values,
  resolve_entity_factory_guard_metrics,
)
from .diagnostics_redaction import compile_redaction_patterns, redact_sensitive_data
from .error_classification import classify_error_reason
from .runtime_data import describe_runtime_store_status, get_runtime_data
from .service_guard import (
  ServiceGuardMetricsSnapshot,
  ServiceGuardResultHistory,
  normalise_guard_history,
)
from .telemetry import (
  get_bool_coercion_metrics,
  get_runtime_performance_stats,
  get_runtime_resilience_diagnostics,
  get_runtime_store_health,
  update_runtime_bool_coercion_summary,
)
from .types import (
  BoolCoercionDiagnosticsPayload,
  CacheDiagnosticsMap,
  CacheDiagnosticsMetadata,
  CacheDiagnosticsSnapshot,
  CacheRepairAggregate,
  CoordinatorHealthIndicators,
  CoordinatorPerformanceMetrics,
  CoordinatorRejectionMetrics,
  CoordinatorResilienceDiagnostics,
  CoordinatorStatisticsPayload,
  CoordinatorUpdateCounts,
  DataStatisticsPayload,
  DebugInformationPayload,
  DogConfigData,
  EntityFactoryGuardMetricsSnapshot,
  JSONLikeMapping,
  JSONMapping,
  JSONMutableMapping,
  JSONValue,
  ModuleUsageBreakdown,
  PawControlConfigEntry,
  PawControlRuntimeData,
  RecentErrorEntry,
  ResilienceEscalationSnapshot,
  RuntimeStoreAssessmentTimelineSegment,
  RuntimeStoreAssessmentTimelineSummary,
  RuntimeStoreHealthAssessment,
  SetupFlagPanelEntry,
  SetupFlagSourceBreakdown,
  SetupFlagSourceLabels,
  SetupFlagsPanelPayload,
)
from .utils import normalise_json_value

if TYPE_CHECKING:
  from .data_manager import PawControlDataManager
  from .notifications import PawControlNotificationManager


def _resolve_data_manager(
  runtime_data: PawControlRuntimeData | None,
) -> PawControlDataManager | None:
  """Return the data manager from the runtime container when available."""

  if runtime_data is None:
    return None

  return runtime_data.runtime_managers.data_manager


def _resolve_notification_manager(
  runtime_data: PawControlRuntimeData | None,
) -> PawControlNotificationManager | None:
  """Return the notification manager stored in runtime managers."""

  if runtime_data is None:
    return None

  return runtime_data.runtime_managers.notification_manager


class SetupFlagSnapshot(TypedDict):
  """Snapshot describing a persisted setup flag state."""

  value: bool
  source: str


SETUP_FLAG_LABELS = {
  "enable_analytics": "Analytics telemetry",
  "enable_cloud_backup": "Cloud backup",
  "debug_logging": "Debug logging",
}


SETUP_FLAG_LABEL_TRANSLATION_KEYS = {
  "enable_analytics": "component.pawcontrol.common.setup_flags_panel_flag_enable_analytics",
  "enable_cloud_backup": "component.pawcontrol.common.setup_flags_panel_flag_enable_cloud_backup",
  "debug_logging": "component.pawcontrol.common.setup_flags_panel_flag_debug_logging",
}


SETUP_FLAG_SOURCE_LABELS = {
  "options": "Options flow",
  "system_settings": "System settings",
  "advanced_settings": "Advanced settings",
  "blueprint": "Blueprint suggestion",
  "config_entry": "Config entry defaults",
  "disabled": "Disable",
  "default": "Integration default",
}


SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS = {
  "options": "component.pawcontrol.common.setup_flags_panel_source_options",
  "system_settings": "component.pawcontrol.common.setup_flags_panel_source_system_settings",
  "advanced_settings": "component.pawcontrol.common.setup_flags_panel_source_advanced_settings",
  "blueprint": "component.pawcontrol.common.setup_flags_panel_source_blueprint",
  "config_entry": "component.pawcontrol.common.setup_flags_panel_source_config_entry",
  "disabled": "component.pawcontrol.common.setup_flags_panel_source_disabled",
  "default": "component.pawcontrol.common.setup_flags_panel_source_default",
}


SETUP_FLAGS_PANEL_TITLE = "Setup flags"


SETUP_FLAGS_PANEL_TITLE_TRANSLATION_KEY = (
  "component.pawcontrol.common.setup_flags_panel_title"
)

SETUP_FLAGS_PANEL_DESCRIPTION = (
  "Analytics, backup, and debug logging toggles captured during onboarding "
  "and options flows."
)


SETUP_FLAGS_PANEL_DESCRIPTION_TRANSLATION_KEY = (
  "component.pawcontrol.common.setup_flags_panel_description"
)


_TRANSLATIONS_IMPORT_PATH = "homeassistant.helpers.translation"
_ASYNC_GET_TRANSLATIONS: Callable[..., Awaitable[dict[str, str]]] | None
try:
  _translations_module = importlib.import_module(_TRANSLATIONS_IMPORT_PATH)
  _ASYNC_GET_TRANSLATIONS = getattr(
    _translations_module,
    "async_get_translations",
    None,
  )
except (ModuleNotFoundError, AttributeError):
  _ASYNC_GET_TRANSLATIONS = None


async def _async_get_translations_wrapper(
  hass: HomeAssistant,
  language: str,
  category: str,
  integrations: set[str],
) -> dict[str, str]:
  """Call Home Assistant translations when available."""

  if _ASYNC_GET_TRANSLATIONS is None:
    return {}

  return await _ASYNC_GET_TRANSLATIONS(hass, language, category, integrations)


async_get_translations = _async_get_translations_wrapper


async def _async_resolve_setup_flag_translations(
  hass: HomeAssistant,
  *,
  language: str | None = None,
) -> tuple[
  str,
  dict[str, str],
  dict[str, str],
  str,
  str,
]:
  """Return localised labels for setup flag diagnostics."""

  config_language = cast(str | None, getattr(hass.config, "language", None))
  target_language = (language or config_language or "en").lower()

  async def _async_fetch(lang: str) -> dict[str, str]:
    if _ASYNC_GET_TRANSLATIONS is None:
      return {}
    try:
      return await _ASYNC_GET_TRANSLATIONS(hass, lang, "component", {DOMAIN})
    except Exception:  # pragma: no cover - defensive guard for HA API
      _LOGGER.debug(
        "Failed to load %s translations for setup flags",
        lang,
      )
      return {}

  translations = await _async_fetch(target_language)
  fallback_language = "en"
  if target_language == fallback_language:
    fallback_translations = translations
  else:
    fallback_translations = await _async_fetch(fallback_language)

  def _lookup(key: str, default: str) -> str:
    return translations.get(key) or fallback_translations.get(key) or default

  flag_labels = {
    key: _lookup(SETUP_FLAG_LABEL_TRANSLATION_KEYS[key], label)
    for key, label in SETUP_FLAG_LABELS.items()
  }

  source_labels = {
    key: _lookup(SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS[key], label)
    for key, label in SETUP_FLAG_SOURCE_LABELS.items()
  }

  title = _lookup(
    SETUP_FLAGS_PANEL_TITLE_TRANSLATION_KEY,
    SETUP_FLAGS_PANEL_TITLE,
  )
  description = _lookup(
    SETUP_FLAGS_PANEL_DESCRIPTION_TRANSLATION_KEY,
    SETUP_FLAGS_PANEL_DESCRIPTION,
  )

  return target_language, flag_labels, source_labels, title, description


def _collect_setup_flag_snapshots(entry: ConfigEntry) -> dict[str, SetupFlagSnapshot]:
  """Return analytics, backup, and debug logging flag states and sources."""

  raw_options = entry.options
  options = (
    cast(JSONMapping, raw_options)
    if isinstance(
      raw_options,
      Mapping,
    )
    else {}
  )
  system_raw = options.get("system_settings")
  system = (
    cast(JSONMapping, system_raw)
    if isinstance(
      system_raw,
      Mapping,
    )
    else {}
  )
  advanced_raw = options.get("advanced_settings")
  advanced = (
    cast(JSONMapping, advanced_raw)
    if isinstance(
      advanced_raw,
      Mapping,
    )
    else {}
  )
  entry_data = cast(JSONMapping, entry.data)

  def _resolve_flag(
    key: str,
    *,
    allow_advanced: bool = False,
  ) -> SetupFlagSnapshot:
    candidate = options.get(key)
    if isinstance(candidate, bool):
      return SetupFlagSnapshot(value=candidate, source="options")

    candidate = system.get(key)
    if isinstance(candidate, bool):
      return SetupFlagSnapshot(value=candidate, source="system_settings")

    if allow_advanced:
      candidate = advanced.get(key)
      if isinstance(candidate, bool):
        return SetupFlagSnapshot(value=candidate, source="advanced_settings")

    candidate = entry_data.get(key)
    if isinstance(candidate, bool):
      return SetupFlagSnapshot(value=candidate, source="config_entry")

    return SetupFlagSnapshot(value=False, source="default")

  return {
    "enable_analytics": _resolve_flag("enable_analytics"),
    "enable_cloud_backup": _resolve_flag("enable_cloud_backup"),
    "debug_logging": _resolve_flag("debug_logging", allow_advanced=True),
  }


def _summarise_setup_flags(entry: ConfigEntry) -> dict[str, bool]:
  """Return analytics, backup, and debug logging flags for diagnostics."""

  snapshots = _collect_setup_flag_snapshots(entry)
  return {key: snapshot["value"] for key, snapshot in snapshots.items()}


async def _async_build_setup_flags_panel(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> SetupFlagsPanelPayload:
  """Expose setup flag metadata in a dashboard-friendly structure."""

  (
    language,
    flag_labels,
    resolved_source_labels,
    title,
    description,
  ) = await _async_resolve_setup_flag_translations(hass)

  snapshots = _collect_setup_flag_snapshots(entry)
  flags: list[SetupFlagPanelEntry] = []
  source_labels: SetupFlagSourceLabels = dict(resolved_source_labels)
  source_labels_default: SetupFlagSourceLabels = dict(
    SETUP_FLAG_SOURCE_LABELS,
  )
  source_label_translation_keys: SetupFlagSourceLabels = dict(
    SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS,
  )

  def _resolve_source_labels(source: str) -> tuple[str, str, str]:
    default_label = SETUP_FLAG_SOURCE_LABELS.get(source, source)
    translation_key = SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS.get(
      source,
      SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS["default"],
    )
    label = source_labels.get(source, default_label)
    return label, default_label, translation_key

  for key, snapshot in snapshots.items():
    source = snapshot["source"]
    source_label, source_label_default, source_label_translation_key = (
      _resolve_source_labels(source)
    )
    flags.append(
      {
        "key": key,
        "label": flag_labels.get(key, SETUP_FLAG_LABELS[key]),
        "label_default": SETUP_FLAG_LABELS[key],
        "label_translation_key": SETUP_FLAG_LABEL_TRANSLATION_KEYS[key],
        "enabled": snapshot["value"],
        "source": source,
        "source_label": source_label,
        "source_label_default": source_label_default,
        "source_label_translation_key": source_label_translation_key,
      },
    )

  enabled_count = sum(1 for flag in flags if flag["enabled"])
  disabled_count = len(flags) - enabled_count

  source_breakdown: SetupFlagSourceBreakdown = {}
  for flag in flags:
    source = cast(str, flag["source"])
    source_breakdown[source] = source_breakdown.get(source, 0) + 1

  return {
    "title": title,
    "title_translation_key": SETUP_FLAGS_PANEL_TITLE_TRANSLATION_KEY,
    "title_default": SETUP_FLAGS_PANEL_TITLE,
    "description": description,
    "description_translation_key": SETUP_FLAGS_PANEL_DESCRIPTION_TRANSLATION_KEY,
    "description_default": SETUP_FLAGS_PANEL_DESCRIPTION,
    "flags": flags,
    "enabled_count": enabled_count,
    "disabled_count": disabled_count,
    "source_breakdown": source_breakdown,
    "source_labels": source_labels,
    "source_labels_default": source_labels_default,
    "source_label_translation_keys": source_label_translation_keys,
    "language": language,
  }


_LOGGER = logging.getLogger(__name__)

# Sensitive keys that should be redacted in diagnostics
REDACTED_KEYS = {
  "access_token",
  "auth",
  "authorization",
  "bearer",
  "client_id",
  "client_secret",
  "cookie",
  "credentials",
  "configuration_url",
  "id_token",
  "jwt",
  "passphrase",
  "private_key",
  "refresh_token",
  "secret_key",
  "session",
  "session_id",
  "signature",
  "ssh_key",
  "token_secret",
  "api_key",
  "api_token",
  "hardware_id",
  "mac",
  "macaddress",
  "password",
  "serial",
  "serial_number",
  "token",
  "secret",
  "unique_id",
  "webhook_url",
  "email",
  "phone",
  "address",
  "latitude",
  "longitude",
  "lat",
  "lon",
  "coordinates",
  "gps_latitude",
  "gps_longitude",
  "gps_position",
  "geofence_lat",
  "geofence_lon",
  "location",
  "personal_info",
  CONF_API_ENDPOINT,
  CONF_API_TOKEN,
}

_REDACTED_KEY_PATTERNS = compile_redaction_patterns(REDACTED_KEYS)


def _fallback_coordinator_statistics() -> CoordinatorStatisticsPayload:
  """Return default coordinator statistics when telemetry is unavailable."""

  update_counts: CoordinatorUpdateCounts = {
    "total": 0,
    "successful": 0,
    "failed": 0,
  }
  performance_metrics: CoordinatorPerformanceMetrics = {
    "success_rate": 0.0,
    "cache_entries": 0,
    "cache_hit_rate": 0.0,
    "consecutive_errors": 0,
    "last_update": None,
    "update_interval": 0.0,
    "api_calls": 0,
  }
  health_indicators: CoordinatorHealthIndicators = {
    "consecutive_errors": 0,
    "stability_window_ok": True,
  }
  return {
    "update_counts": update_counts,
    "performance_metrics": performance_metrics,
    "health_indicators": health_indicators,
  }


def _apply_rejection_metrics_to_performance(
  performance_metrics: CoordinatorPerformanceMetrics,
  rejection_metrics: CoordinatorRejectionMetrics,
) -> None:
  """Copy rejection metrics into the coordinator performance snapshot."""

  merge_rejection_metric_values(performance_metrics, rejection_metrics)


def _build_statistics_payload(
  payload: JSONLikeMapping,
) -> CoordinatorStatisticsPayload:
  """Normalise coordinator statistics into the active typed structure."""

  stats = _fallback_coordinator_statistics()
  update_counts = stats["update_counts"]
  performance_metrics = stats["performance_metrics"]
  health_indicators = stats["health_indicators"]

  counts_payload = payload.get("update_counts")
  if isinstance(counts_payload, Mapping):
    total_value = _coerce_int(counts_payload.get("total"))
    if total_value is not None:
      update_counts["total"] = total_value
    failed_value = _coerce_int(counts_payload.get("failed"))
    if failed_value is not None:
      update_counts["failed"] = failed_value
    successful_value = _coerce_int(counts_payload.get("successful"))
    if successful_value is not None:
      update_counts["successful"] = successful_value
  else:
    total_value = _coerce_int(payload.get("total_updates"))
    failed_value = _coerce_int(payload.get("failed"))
    if total_value is not None:
      update_counts["total"] = total_value
    if failed_value is not None:
      update_counts["failed"] = failed_value
    if total_value is not None and failed_value is not None:
      update_counts["successful"] = max(total_value - failed_value, 0)

  metrics_payload = payload.get("performance_metrics")
  if isinstance(metrics_payload, Mapping):
    success_rate = metrics_payload.get("success_rate")
    if isinstance(success_rate, int | float):
      performance_metrics["success_rate"] = float(success_rate)
    cache_entries = _coerce_int(metrics_payload.get("cache_entries"))
    if cache_entries is not None:
      performance_metrics["cache_entries"] = cache_entries
    cache_hit_rate = metrics_payload.get("cache_hit_rate")
    if isinstance(cache_hit_rate, int | float):
      performance_metrics["cache_hit_rate"] = float(cache_hit_rate)
    consecutive_errors = _coerce_int(
      metrics_payload.get("consecutive_errors"),
    )
    if consecutive_errors is not None:
      performance_metrics["consecutive_errors"] = consecutive_errors
      health_indicators["consecutive_errors"] = consecutive_errors
      health_indicators["stability_window_ok"] = consecutive_errors < 5
    last_update = metrics_payload.get("last_update")
    if last_update is not None:
      performance_metrics["last_update"] = last_update
    update_interval = metrics_payload.get("update_interval")
    if isinstance(update_interval, int | float):
      performance_metrics["update_interval"] = float(update_interval)
    api_calls = _coerce_int(metrics_payload.get("api_calls"))
    if api_calls is not None:
      performance_metrics["api_calls"] = api_calls
  else:
    update_interval = payload.get("update_interval")
    if isinstance(update_interval, int | float):
      performance_metrics["update_interval"] = float(update_interval)

  health_payload = payload.get("health_indicators")
  if isinstance(health_payload, Mapping):
    consecutive_errors = _coerce_int(
      health_payload.get("consecutive_errors"),
    )
    if consecutive_errors is not None:
      health_indicators["consecutive_errors"] = consecutive_errors
      health_indicators["stability_window_ok"] = consecutive_errors < 5
    stability_ok = health_payload.get("stability_window_ok")
    if isinstance(stability_ok, bool):
      health_indicators["stability_window_ok"] = stability_ok

  total_updates = update_counts["total"]
  successful_updates = update_counts["successful"]
  if total_updates and successful_updates and not payload.get("success_rate"):
    performance_metrics["success_rate"] = round(
      (successful_updates / total_updates) * 100,
      2,
    )

  repairs = payload.get("repairs")
  if repairs is not None:
    stats["repairs"] = cast(Any, repairs)

  reconfigure = payload.get("reconfigure")
  if reconfigure is not None:
    stats["reconfigure"] = cast(Any, reconfigure)

  entity_budget = payload.get("entity_budget")
  if entity_budget is not None:
    stats["entity_budget"] = cast(Any, entity_budget)

  adaptive_polling = payload.get("adaptive_polling")
  if adaptive_polling is not None:
    stats["adaptive_polling"] = cast(Any, adaptive_polling)

  resilience = payload.get("resilience")
  if resilience is not None:
    stats["resilience"] = cast(Any, resilience)

  rejection_metrics = payload.get("rejection_metrics")
  if isinstance(rejection_metrics, Mapping):
    stats["rejection_metrics"] = derive_rejection_metrics(
      cast(JSONMapping, rejection_metrics),
    )

  return stats


def _entity_registry_entries_for_config_entry(
  entity_registry: er.EntityRegistry,
  entry_id: str,
) -> list[er.RegistryEntry]:
  """Return registry entries associated with a config entry."""

  module_helper = getattr(er, "async_entries_for_config_entry", None)
  if callable(module_helper):
    return list(module_helper(entity_registry, entry_id))

  entities = getattr(entity_registry, "entities", {})
  return [
    entry
    for entry in entities.values()
    if getattr(entry, "config_entry_id", None) == entry_id
  ]


def _device_registry_entries_for_config_entry(
  device_registry: dr.DeviceRegistry,
  entry_id: str,
) -> list[dr.DeviceEntry]:
  """Return device registry entries associated with a config entry."""

  module_helper = getattr(dr, "async_entries_for_config_entry", None)
  if callable(module_helper):
    return list(module_helper(device_registry, entry_id))

  devices = getattr(device_registry, "devices", {})
  return [
    entry
    for entry in devices.values()
    if getattr(entry, "config_entry_id", None) == entry_id
    or (
      isinstance(getattr(entry, "config_entries", None), set)
      and entry_id in entry.config_entries
    )
  ]


async def async_get_config_entry_diagnostics(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
) -> JSONMutableMapping:
  """Return diagnostics for a config entry.

  This function collects comprehensive diagnostic information including
  configuration details, system status, entity information, and operational
  metrics while ensuring sensitive data is properly redacted.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry to diagnose

  Returns:
      Dictionary containing diagnostic information
  """
  _LOGGER.debug(
    "Generating diagnostics for Paw Control entry: %s",
    entry.entry_id,
  )

  # Get runtime data using the shared helper (runtime adoption still being proven)
  runtime_data = get_runtime_data(hass, entry)
  coordinator = runtime_data.coordinator if runtime_data else None

  # Base diagnostics structure
  cache_snapshots = _collect_cache_diagnostics(runtime_data)

  diagnostics_payload: dict[str, object] = {
    "config_entry": await _get_config_entry_diagnostics(entry),
    "system_info": await _get_system_diagnostics(hass),
    "integration_status": await _get_integration_status(hass, entry, runtime_data),
    "coordinator_info": await _get_coordinator_diagnostics(coordinator),
    "entities": await _get_entities_diagnostics(hass, entry),
    "devices": await _get_devices_diagnostics(hass, entry),
    "dogs_summary": await _get_dogs_summary(entry, coordinator),
    "performance_metrics": await _get_performance_metrics(coordinator),
    "data_statistics": await _get_data_statistics(runtime_data, cache_snapshots),
    "error_logs": await _get_recent_errors(entry.entry_id),
    "debug_info": await _get_debug_information(hass, entry),
    "door_sensor": await _get_door_sensor_diagnostics(runtime_data),
    "service_execution": await _get_service_execution_diagnostics(runtime_data),
    "bool_coercion": _get_bool_coercion_diagnostics(runtime_data),
    "setup_flags": _summarise_setup_flags(entry),
    "setup_flags_panel": await _async_build_setup_flags_panel(hass, entry),
    "resilience": _get_resilience_diagnostics(runtime_data, coordinator),
    "resilience_escalation": _get_resilience_escalation_snapshot(runtime_data),
    "guard_notification_error_metrics": _get_guard_notification_error_metrics(
      runtime_data,
    ),
    "runtime_store": describe_runtime_store_status(hass, entry),
    "notifications": await _get_notification_diagnostics(runtime_data),
  }

  runtime_store_history = get_runtime_store_health(runtime_data)
  if runtime_store_history:
    diagnostics_payload["runtime_store_history"] = runtime_store_history
    assessment = runtime_store_history.get("assessment")
    if isinstance(assessment, Mapping):
      diagnostics_payload["runtime_store_assessment"] = cast(
        RuntimeStoreHealthAssessment,
        dict(assessment),
      )
    timeline_segments = runtime_store_history.get(
      "assessment_timeline_segments",
    )
    if isinstance(timeline_segments, Sequence):
      diagnostics_payload["runtime_store_timeline_segments"] = [
        cast(RuntimeStoreAssessmentTimelineSegment, dict(segment))
        for segment in timeline_segments
        if isinstance(segment, Mapping)
      ]
    timeline_summary = runtime_store_history.get(
      "assessment_timeline_summary",
    )
    if isinstance(timeline_summary, Mapping):
      diagnostics_payload["runtime_store_timeline_summary"] = cast(
        RuntimeStoreAssessmentTimelineSummary,
        dict(timeline_summary),
      )

  if cache_snapshots is not None:
    diagnostics_payload["cache_diagnostics"] = _serialise_cache_diagnostics_payload(
      cache_snapshots,
    )

  normalised_payload = cast(
    JSONMutableMapping,
    _normalise_json(diagnostics_payload),
  )

  # Redact sensitive information
  redacted_diagnostics = cast(
    JSONMutableMapping,
    _redact_sensitive_data(cast(JSONValue, normalised_payload)),
  )

  _LOGGER.debug(
    "Diagnostics generated successfully for entry %s",
    entry.entry_id,
  )
  return redacted_diagnostics


def _get_resilience_escalation_snapshot(
  runtime_data: PawControlRuntimeData | None,
) -> ResilienceEscalationSnapshot:
  """Build diagnostics metadata for the resilience escalation helper."""

  if runtime_data is None:
    return {"available": False}

  script_manager = getattr(runtime_data, "script_manager", None)
  if script_manager is None:
    return {"available": False}

  snapshot = script_manager.get_resilience_escalation_snapshot()
  if snapshot is None:
    return {"available": False}

  return cast(
    ResilienceEscalationSnapshot,
    _normalise_json(cast(JSONLikeMapping, snapshot)),
  )


def _get_resilience_diagnostics(
  runtime_data: PawControlRuntimeData | None,
  coordinator: PawControlCoordinator | None,
) -> JSONMutableMapping:
  """Build a resilience diagnostics payload using stored runtime telemetry."""

  diagnostics: CoordinatorResilienceDiagnostics | None = None

  if runtime_data is not None:
    diagnostics = get_runtime_resilience_diagnostics(runtime_data)

  if diagnostics is None and coordinator is not None:
    fetch_stats = getattr(coordinator, "get_update_statistics", None)
    if callable(fetch_stats):
      try:
        raw_stats = fetch_stats()
      except Exception:  # pragma: no cover - diagnostics guard
        raw_stats = None
      if isinstance(raw_stats, Mapping):
        resilience_payload = raw_stats.get("resilience")
        if isinstance(resilience_payload, Mapping):
          diagnostics = cast(
            CoordinatorResilienceDiagnostics,
            dict(resilience_payload),
          )

  if diagnostics is None:
    return cast(JSONMutableMapping, {"available": False})

  payload: JSONMutableMapping = {"available": True, "schema_version": 1}

  summary = diagnostics.get("summary")
  if isinstance(summary, Mapping):
    payload["summary"] = cast(JSONMutableMapping, dict(summary))
  else:
    payload["summary"] = None

  breakers = diagnostics.get("breakers")
  if isinstance(breakers, Mapping):
    payload["breakers"] = {
      str(name): cast(JSONMutableMapping, dict(values))
      for name, values in breakers.items()
      if isinstance(values, Mapping)
    }

  return cast(JSONMutableMapping, _normalise_json(payload))


async def _get_config_entry_diagnostics(entry: ConfigEntry) -> JSONMutableMapping:
  """Get configuration entry diagnostic information.

  Args:
      entry: Configuration entry

  Returns:
      Configuration diagnostics
  """
  version = getattr(entry, "version", None)
  state = getattr(entry, "state", None)
  if isinstance(state, ConfigEntryState):
    state_value: str | None = state.value
  elif state is None:
    state_value = None
  else:
    state_value = str(state)

  created_at = getattr(entry, "created_at", None)
  modified_at = getattr(entry, "modified_at", None)

  supports_options = getattr(entry, "supports_options", False)
  supports_reconfigure = getattr(entry, "supports_reconfigure", False)
  supports_remove_device = getattr(entry, "supports_remove_device", False)
  supports_unload = getattr(entry, "supports_unload", False)
  dogs_value = entry.data.get(CONF_DOGS)
  dogs_configured = (
    len(dogs_value)
    if isinstance(dogs_value, Sequence)
    and not isinstance(dogs_value, str | bytes | bytearray)
    else 0
  )

  return cast(
    JSONMutableMapping,
    {
      "entry_id": entry.entry_id,
      "title": getattr(entry, "title", entry.entry_id),
      "version": version,
      "domain": entry.domain,
      "state": state_value,
      "source": getattr(entry, "source", None),
      "unique_id": getattr(entry, "unique_id", None),
      "created_at": created_at.isoformat() if created_at else None,
      "modified_at": modified_at.isoformat() if modified_at else None,
      "data_keys": list(entry.data.keys()),
      "options_keys": list(getattr(entry, "options", {})),
      "supports_options": supports_options,
      "supports_reconfigure": supports_reconfigure,
      "supports_remove_device": supports_remove_device,
      "supports_unload": supports_unload,
      "dogs_configured": dogs_configured,
    },
  )


async def _get_system_diagnostics(hass: HomeAssistant) -> JSONMutableMapping:
  """Get Home Assistant system diagnostic information.

  Args:
      hass: Home Assistant instance

  Returns:
      System diagnostics
  """
  config = hass.config
  time_zone = getattr(config, "time_zone", None)
  safe_mode = getattr(config, "safe_mode", False)
  recovery_mode = getattr(config, "recovery_mode", False)
  start_time = getattr(config, "start_time", None)
  uptime_seconds: float | None = None
  if start_time:
    uptime_seconds = (dt_util.utcnow() - start_time).total_seconds()

  return cast(
    JSONMutableMapping,
    {
      "ha_version": getattr(config, "version", None),
      "python_version": getattr(config, "python_version", None),
      "timezone": str(time_zone) if time_zone else None,
      "config_dir": getattr(config, "config_dir", None),
      "is_running": getattr(hass, "is_running", False),
      "safe_mode": safe_mode,
      "recovery_mode": recovery_mode,
      "current_time": dt_util.utcnow().isoformat(),
      "uptime_seconds": uptime_seconds,
    },
  )


def _collect_cache_diagnostics(
  runtime_data: PawControlRuntimeData | None,
) -> CacheDiagnosticsMap | None:
  """Return cache diagnostics captured by the data manager when available."""

  if runtime_data is None:
    return None

  data_manager = _resolve_data_manager(runtime_data)
  if data_manager is None:
    return None

  snapshot_method = getattr(data_manager, "cache_snapshots", None)
  if not callable(snapshot_method):
    return None

  try:
    raw_snapshots = snapshot_method()
  except Exception as err:  # pragma: no cover - defensive guard
    _LOGGER.debug("Unable to collect cache diagnostics: %s", err)
    return None

  if isinstance(raw_snapshots, Mapping):
    snapshots = dict(raw_snapshots)
  elif isinstance(raw_snapshots, dict):
    snapshots = raw_snapshots
  else:
    _LOGGER.debug(
      "Unexpected cache diagnostics payload type: %s",
      type(raw_snapshots).__name__,
    )
    return None

  normalised: CacheDiagnosticsMap = {}
  for name, payload in snapshots.items():
    if not isinstance(name, str) or not name:
      _LOGGER.debug(
        "Skipping cache diagnostics entry with invalid name: %s",
        name,
      )
      continue

    normalised[name] = _normalise_cache_snapshot(payload)

  return normalised or None


def _normalise_cache_snapshot(payload: Any) -> CacheDiagnosticsSnapshot:
  """Coerce arbitrary cache payloads into diagnostics-friendly snapshots."""

  if isinstance(payload, CacheDiagnosticsSnapshot):
    snapshot = payload
  elif isinstance(payload, Mapping):
    snapshot = CacheDiagnosticsSnapshot.from_mapping(
      cast(JSONMapping, payload),
    )
  else:
    return CacheDiagnosticsSnapshot(
      error=f"Unsupported diagnostics payload: {type(payload).__name__}",
      snapshot={"value": _normalise_json(payload)},
    )

  repair_summary = snapshot.repair_summary
  resolved_summary = ensure_cache_repair_aggregate(repair_summary)
  if resolved_summary is not None:
    snapshot.repair_summary = resolved_summary
  elif isinstance(repair_summary, Mapping):
    try:
      snapshot.repair_summary = CacheRepairAggregate.from_mapping(
        repair_summary,
      )
    except Exception:  # pragma: no cover - defensive fallback
      snapshot.repair_summary = None
  else:
    snapshot.repair_summary = None

  if snapshot.stats is not None:
    snapshot.stats = cast(
      JSONMutableMapping,
      _normalise_json(snapshot.stats),
    )

  if snapshot.diagnostics is not None:
    diagnostics_payload = _normalise_json(snapshot.diagnostics)
    if isinstance(diagnostics_payload, Mapping):
      snapshot.diagnostics = cast(
        CacheDiagnosticsMetadata,
        {str(key): value for key, value in diagnostics_payload.items()},
      )
    else:
      snapshot.diagnostics = None

  if snapshot.snapshot is not None:
    snapshot.snapshot = cast(
      JSONMutableMapping,
      _normalise_json(snapshot.snapshot),
    )

  if not snapshot.to_mapping():
    snapshot.snapshot = {"value": _normalise_json(payload)}

  return snapshot


def _serialise_cache_diagnostics_payload(
  payload: JSONLikeMapping | CacheDiagnosticsMap,
) -> JSONMutableMapping:
  """Convert cache diagnostics snapshots into JSON-safe payloads."""

  serialised: JSONMutableMapping = {}
  for name, snapshot in payload.items():
    serialised[str(name)] = _serialise_cache_snapshot(snapshot)
  return serialised


def _serialise_cache_snapshot(snapshot: object) -> JSONMutableMapping:
  """Return a JSON-serialisable payload for a cache diagnostics snapshot."""

  snapshot_input: object
  if isinstance(snapshot, CacheDiagnosticsSnapshot):
    snapshot_input = CacheDiagnosticsSnapshot.from_mapping(
      snapshot.to_mapping(),
    )
  else:
    snapshot_input = snapshot

  normalised_snapshot = _normalise_cache_snapshot(snapshot_input)
  summary = (
    normalised_snapshot.repair_summary
    if isinstance(normalised_snapshot.repair_summary, CacheRepairAggregate)
    else None
  )
  snapshot_payload = normalised_snapshot.to_mapping()

  if summary is not None:
    snapshot_payload["repair_summary"] = summary.to_mapping()
  else:
    snapshot_payload.pop("repair_summary", None)

  return cast(JSONMutableMapping, _normalise_json(snapshot_payload))


def normalize_value(value: object, _seen: set[int] | None = None) -> JSONValue:
  """Backwards-compatible wrapper for JSON normalisation."""

  return normalise_json_value(value, _seen)


def _normalise_json(value: Any, _seen: set[int] | None = None) -> JSONValue:
  """Normalise diagnostics payloads into JSON-serialisable data."""

  return normalise_json_value(value, _seen)


async def _get_integration_status(
  hass: HomeAssistant,
  entry: ConfigEntry,
  runtime_data: PawControlRuntimeData | None,
) -> JSONMutableMapping:
  """Get integration status diagnostics.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry
      runtime_data: Runtime data from entry

  Returns:
      Integration status diagnostics
  """
  if runtime_data:
    coordinator = runtime_data.coordinator
    data_manager = _resolve_data_manager(runtime_data)
    notification_manager = _resolve_notification_manager(runtime_data)
  else:
    coordinator = None
    data_manager = None
    notification_manager = None

  entry_loaded = entry.state is ConfigEntryState.LOADED

  return cast(
    JSONMutableMapping,
    {
      "entry_loaded": entry_loaded,
      "coordinator_available": coordinator is not None,
      "coordinator_success": coordinator.last_update_success if coordinator else False,
      "coordinator_last_update": coordinator.last_update_time.isoformat()
      if coordinator and coordinator.last_update_time
      else None,
      "data_manager_available": data_manager is not None,
      "notification_manager_available": notification_manager is not None,
      "platforms_loaded": await _get_loaded_platforms(hass, entry),
      "services_registered": await _get_registered_services(hass),
      "setup_completed": True,
    },
  )


async def _get_notification_diagnostics(
  runtime_data: PawControlRuntimeData | None,
) -> JSONMutableMapping:
  """Return notification-specific diagnostics."""

  if runtime_data is None:
    return cast(JSONMutableMapping, {"available": False})

  notification_manager = _resolve_notification_manager(runtime_data)
  if notification_manager is None:
    return cast(JSONMutableMapping, {"available": False})

  stats = await notification_manager.async_get_performance_statistics()
  delivery = notification_manager.get_delivery_status_snapshot()

  return cast(
    JSONMutableMapping,
    {
      "available": True,
      "manager_stats": stats,
      "delivery_status": delivery,
      "rejection_metrics": _build_notification_rejection_metrics(delivery),
    },
  )


def _build_notification_rejection_metrics(
  delivery: Mapping[str, object] | None,
) -> JSONMutableMapping:
  """Return a per-service rejection/failure snapshot for notifications."""

  payload: JSONMutableMapping = {
    "schema_version": 1,
    "total_services": 0,
    "total_failures": 0,
    "services_with_failures": [],
    "service_failures": {},
    "service_consecutive_failures": {},
    "service_last_error_reasons": {},
    "service_last_errors": {},
  }

  if not isinstance(delivery, Mapping):
    return payload

  services = delivery.get("services")
  if not isinstance(services, Mapping):
    return payload

  service_failures: dict[str, int] = {}
  consecutive_failures: dict[str, int] = {}
  last_error_reasons: dict[str, str] = {}
  last_errors: dict[str, str] = {}
  services_with_failures: list[str] = []
  total_failures = 0

  for service_name, service_payload in services.items():
    if not isinstance(service_name, str) or not isinstance(service_payload, Mapping):
      continue

    failures = _coerce_int(service_payload.get("total_failures")) or 0
    consecutive = _coerce_int(service_payload.get("consecutive_failures")) or 0
    service_failures[service_name] = failures
    consecutive_failures[service_name] = consecutive
    total_failures += failures
    if failures:
      services_with_failures.append(service_name)

    last_error_reason = service_payload.get("last_error_reason")
    if isinstance(last_error_reason, str) and last_error_reason:
      last_error_reasons[service_name] = last_error_reason

    last_error = service_payload.get("last_error")
    if isinstance(last_error, str) and last_error:
      last_errors[service_name] = last_error

  payload["total_services"] = len(service_failures)
  payload["total_failures"] = total_failures
  payload["services_with_failures"] = sorted(services_with_failures)
  payload["service_failures"] = service_failures
  payload["service_consecutive_failures"] = consecutive_failures
  payload["service_last_error_reasons"] = last_error_reasons
  payload["service_last_errors"] = last_errors

  return payload


# -----------------------------------------------------------------------------
# Guard and Notification Error Aggregation
# -----------------------------------------------------------------------------


def _build_guard_notification_error_metrics(
  guard_metrics: Mapping[str, object] | None,
  delivery: Mapping[str, object] | None,
) -> JSONMutableMapping:
  """Aggregate service guard and notification error counters into a payload.

  The result includes counts of skipped service executions and failed
  notifications, plus a classification summary mapping categories (e.g.
  ``auth_error`` or ``device_unreachable``) to the total number of failures.
  """

  payload: JSONMutableMapping = {
    "schema_version": 1,
    "available": False,
    "total_errors": 0,
    "guard": {
      "skipped": 0,
      "reasons": {},
    },
    "notifications": {
      "total_failures": 0,
      "services_with_failures": [],
      "reasons": {},
    },
    "classified_errors": {},
  }

  classified_errors: dict[str, int] = {}
  guard_reasons: dict[str, int] = {}
  guard_skipped = 0

  # Process guard metrics (skip counts and reasons)
  if isinstance(guard_metrics, Mapping):
    guard_skipped = _coerce_int(guard_metrics.get("skipped")) or 0
    reasons_raw = guard_metrics.get("reasons")
    if isinstance(reasons_raw, Mapping):
      for reason_key, count in reasons_raw.items():
        coerced = _coerce_int(count) or 0
        if not coerced:
          continue
        reason_text = str(reason_key)
        guard_reasons[reason_text] = guard_reasons.get(reason_text, 0) + coerced
        classification = classify_error_reason(reason_text, error=None)
        classified_errors[classification] = (
          classified_errors.get(classification, 0) + coerced
        )

  notification_failures = 0
  notification_reasons: dict[str, int] = {}
  services_with_failures: list[str] = []
  # Process notification delivery failures
  if isinstance(delivery, Mapping):
    services = delivery.get("services")
    if isinstance(services, Mapping):
      for service_name, service_payload in services.items():
        if not isinstance(service_name, str) or not isinstance(
          service_payload, Mapping
        ):
          continue
        failures = _coerce_int(service_payload.get("total_failures")) or 0
        if not failures:
          continue
        notification_failures += failures
        services_with_failures.append(service_name)
        last_error_reason = service_payload.get("last_error_reason")
        reason_text = (
          last_error_reason
          if isinstance(last_error_reason, str) and last_error_reason
          else None
        )
        last_error = service_payload.get("last_error")
        error_text = last_error if isinstance(last_error, str) else None
        if reason_text is not None:
          notification_reasons[reason_text] = (
            notification_reasons.get(reason_text, 0) + failures
          )
        classification = classify_error_reason(reason_text, error=error_text)
        classified_errors[classification] = (
          classified_errors.get(classification, 0) + failures
        )

  total_errors = guard_skipped + notification_failures

  payload["available"] = bool(
    guard_skipped
    or guard_reasons
    or notification_failures
    or notification_reasons
    or services_with_failures
  )
  payload["total_errors"] = total_errors
  payload["guard"] = {
    "skipped": guard_skipped,
    "reasons": guard_reasons,
  }
  payload["notifications"] = {
    "total_failures": notification_failures,
    "services_with_failures": sorted(services_with_failures),
    "reasons": notification_reasons,
  }
  payload["classified_errors"] = classified_errors

  return payload


def _get_guard_notification_error_metrics(
  runtime_data: PawControlRuntimeData | None,
) -> JSONMutableMapping:
  """Collect aggregated guard and notification error metrics from runtime.

  This helper extracts guard and delivery snapshots from runtime data (if
  available) and delegates to ``_build_guard_notification_error_metrics``.
  """
  if runtime_data is None:
    return _build_guard_notification_error_metrics(None, None)

  performance_stats = get_runtime_performance_stats(runtime_data)
  guard_metrics: Mapping[str, object] | None = None
  if isinstance(performance_stats, Mapping):
    guard_metrics_raw = performance_stats.get("service_guard_metrics")
    if isinstance(guard_metrics_raw, Mapping):
      guard_metrics = guard_metrics_raw

  notification_manager = _resolve_notification_manager(runtime_data)
  delivery_status: Mapping[str, object] | None = None
  if notification_manager is not None:
    delivery = notification_manager.get_delivery_status_snapshot()
    if isinstance(delivery, Mapping):
      delivery_status = delivery

  return _build_guard_notification_error_metrics(guard_metrics, delivery_status)


async def _get_coordinator_diagnostics(
  coordinator: PawControlCoordinator | None,
) -> JSONMutableMapping:
  """Get coordinator diagnostic information.

  Args:
      coordinator: Data coordinator instance

  Returns:
      Coordinator diagnostics
  """
  if not coordinator:
    return cast(
      JSONMutableMapping,
      {"available": False, "reason": "Coordinator not initialized"},
    )

  try:
    stats: CoordinatorStatisticsPayload = coordinator.get_update_statistics()
  except Exception as err:
    _LOGGER.debug("Could not get coordinator statistics: %s", err)
    stats = _fallback_coordinator_statistics()

  update_interval_seconds = (
    coordinator.update_interval.total_seconds() if coordinator.update_interval else None
  )

  return cast(
    JSONMutableMapping,
    {
      "available": coordinator.available,
      "last_update_success": coordinator.last_update_success,
      "last_update_time": coordinator.last_update_time.isoformat()
      if coordinator.last_update_time
      else None,
      "update_interval_seconds": update_interval_seconds,
      "update_method": str(coordinator.update_method)
      if hasattr(coordinator, "update_method")
      else "unknown",
      "logger_name": coordinator.logger.name,
      "name": coordinator.name,
      "statistics": stats,
      "config_entry_id": coordinator.config_entry.entry_id,
      "dogs_managed": len(getattr(coordinator, "dogs", [])),
    },
  )


async def _get_entities_diagnostics(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> JSONMutableMapping:
  """Get entities diagnostic information.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry

  Returns:
      Entities diagnostics
  """
  entity_registry = er.async_get(hass)

  # Get all entities for this integration
  entities = _entity_registry_entries_for_config_entry(
    entity_registry,
    entry.entry_id,
  )

  # Group entities by platform
  entities_by_platform: dict[str, list[JSONMutableMapping]] = {}

  for entity in entities:
    platform = entity.platform
    if platform not in entities_by_platform:
      entities_by_platform[platform] = []

    entity_info: JSONMutableMapping = {
      "entity_id": entity.entity_id,
      "unique_id": entity.unique_id,
      "platform": entity.platform,
      "device_id": entity.device_id,
      "disabled": entity.disabled,
      "disabled_by": entity.disabled_by.value if entity.disabled_by else None,
      "hidden": entity.hidden,
      "entity_category": entity.entity_category.value
      if entity.entity_category
      else None,
      "has_entity_name": entity.has_entity_name,
      "original_name": entity.original_name,
      "capabilities": entity.capabilities,
    }

    # Get current state
    state = hass.states.get(entity.entity_id)
    if state:
      entity_info.update(
        {
          "state": state.state,
          "available": state.state != "unavailable",
          "last_changed": state.last_changed.isoformat(),
          "last_updated": state.last_updated.isoformat(),
          "attributes_count": len(state.attributes),
        },
      )

    entities_by_platform[platform].append(
      cast(JSONMutableMapping, _normalise_json(entity_info)),
    )

  return cast(
    JSONMutableMapping,
    {
      "total_entities": len(entities),
      "entities_by_platform": entities_by_platform,
      "platform_counts": {
        platform: len(platform_entities)
        for platform, platform_entities in entities_by_platform.items()
      },
      "disabled_entities": len([e for e in entities if e.disabled]),
      "hidden_entities": len([e for e in entities if e.hidden]),
    },
  )


async def _get_devices_diagnostics(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> JSONMutableMapping:
  """Get devices diagnostic information.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry

  Returns:
      Devices diagnostics
  """
  device_registry = dr.async_get(hass)

  # Get all devices for this integration
  devices = _device_registry_entries_for_config_entry(
    device_registry,
    entry.entry_id,
  )

  devices_info: list[JSONMutableMapping] = []
  for device in devices:
    device_info: JSONMutableMapping = {
      "id": device.id,
      "name": device.name,
      "manufacturer": device.manufacturer,
      "model": device.model,
      "sw_version": device.sw_version,
      "hw_version": device.hw_version,
      "via_device_id": device.via_device_id,
      "disabled": device.disabled,
      "disabled_by": device.disabled_by.value if device.disabled_by else None,
      "entry_type": device.entry_type.value if device.entry_type else None,
      "identifiers": list(device.identifiers),
      "connections": list(device.connections),
      "configuration_url": device.configuration_url,
    }
    devices_info.append(device_info)

  return cast(
    JSONMutableMapping,
    {
      "total_devices": len(devices),
      "devices": devices_info,
      "disabled_devices": len([d for d in devices if d.disabled]),
    },
  )


async def _get_dogs_summary(
  entry: ConfigEntry,
  coordinator: PawControlCoordinator | None,
) -> JSONMutableMapping:
  """Get summary of configured dogs.

  Args:
      entry: Configuration entry
      coordinator: Data coordinator

  Returns:
      Dogs summary diagnostics
  """
  dogs_payload = entry.data.get(CONF_DOGS)
  dogs_source: Sequence[Any] | None = (
    dogs_payload
    if isinstance(dogs_payload, Sequence)
    and not isinstance(dogs_payload, str | bytes | bytearray)
    else None
  )
  dogs: list[DogConfigData] = (
    [cast(DogConfigData, dog) for dog in dogs_source if isinstance(dog, Mapping)]
    if dogs_source
    else []
  )

  dogs_summary: list[JSONMutableMapping] = []
  for dog in dogs:
    dog_id = dog.get(CONF_DOG_ID)
    if not isinstance(dog_id, str):
      continue
    modules_payload = dog.get("modules", {})
    modules = (
      modules_payload
      if isinstance(
        modules_payload,
        Mapping,
      )
      else {}
    )
    enabled_modules = {
      str(name): bool(enabled)
      for name, enabled in modules.items()
      if isinstance(enabled, bool)
    }
    dog_summary: JSONMutableMapping = cast(
      JSONMutableMapping,
      {
        "dog_id": dog_id,
        "dog_name": cast(JSONValue, dog.get(CONF_DOG_NAME)),
        "dog_breed": cast(JSONValue, dog.get("dog_breed", "")),
        "dog_age": cast(JSONValue, dog.get("dog_age")),
        "dog_weight": cast(JSONValue, dog.get("dog_weight")),
        "dog_size": cast(JSONValue, dog.get("dog_size")),
        "enabled_modules": cast(JSONValue, enabled_modules),
        "module_count": sum(enabled_modules.values()),
      },
    )
    dog_summary = cast(JSONMutableMapping, _normalise_json(dog_summary))

    # Add coordinator data if available
    if coordinator:
      try:
        get_dog_data_method = getattr(
          coordinator,
          "get_dog_data",
          None,
        )
        dog_data = (
          get_dog_data_method(dog_id) if callable(get_dog_data_method) else None
        )
        if isinstance(dog_data, Mapping):
          dog_summary.update(
            {
              "coordinator_data_available": True,
              "last_activity": dog_data.get("last_update"),
              "status": dog_data.get("status"),
            },
          )
        else:
          dog_summary["coordinator_data_available"] = False
      except Exception as err:
        _LOGGER.debug(
          "Could not get coordinator data for dog %s: %s",
          dog_id,
          err,
        )
        dog_summary["coordinator_data_available"] = False

    dogs_summary.append(dog_summary)

  return cast(
    JSONMutableMapping,
    {
      "total_dogs": len(dogs),
      "dogs": dogs_summary,
      "module_usage": _calculate_module_usage(dogs),
    },
  )


async def _get_performance_metrics(
  coordinator: PawControlCoordinator | None,
) -> JSONMutableMapping:
  """Get performance metrics.

  Args:
      coordinator: Data coordinator

  Returns:
      Performance metrics
  """
  if not coordinator:
    return cast(JSONMutableMapping, {"available": False})

  try:
    raw_stats = coordinator.get_update_statistics()
  except Exception as err:
    _LOGGER.debug("Could not get performance metrics: %s", err)
    return cast(JSONMutableMapping, {"available": False, "error": str(err)})

  stats_mapping: JSONLikeMapping = (
    cast(JSONLikeMapping, raw_stats)
    if isinstance(
      raw_stats,
      Mapping,
    )
    else {}
  )
  statistics = _build_statistics_payload(stats_mapping)
  stats_payload: JSONMutableMapping = (
    cast(JSONMutableMapping, dict(stats_mapping))
    if isinstance(stats_mapping, Mapping)
    else cast(JSONMutableMapping, {})
  )
  stats_payload["update_counts"] = cast(
    JSONMapping,
    dict(statistics["update_counts"]),
  )
  stats_payload["health_indicators"] = cast(
    JSONMapping,
    dict(statistics["health_indicators"]),
  )

  update_counts = statistics["update_counts"]
  total_updates = update_counts["total"]
  failed_updates = update_counts["failed"]
  error_rate = failed_updates / total_updates if total_updates else 0.0

  rejection_payload = (
    stats_mapping.get("rejection_metrics")
    if isinstance(stats_mapping, Mapping)
    else None
  ) or statistics.get("rejection_metrics")
  if isinstance(rejection_payload, Mapping):
    rejection_metrics = derive_rejection_metrics(
      cast(JSONMapping, _normalise_json(rejection_payload)),
    )
  else:
    rejection_metrics = default_rejection_metrics()

  statistics["rejection_metrics"] = rejection_metrics
  rejection_metrics_payload = cast(
    JSONMapping,
    _normalise_json(dict(rejection_metrics)),
  )
  stats_payload["rejection_metrics"] = rejection_metrics_payload

  performance_metrics = statistics["performance_metrics"]
  _apply_rejection_metrics_to_performance(
    performance_metrics,
    rejection_metrics,
  )
  stats_payload["performance_metrics"] = cast(
    JSONMapping,
    dict(performance_metrics),
  )

  repairs = statistics.get("repairs")
  if repairs is not None:
    stats_payload["repairs"] = cast(JSONValue, _normalise_json(repairs))

  reconfigure = statistics.get("reconfigure")
  if reconfigure is not None:
    stats_payload["reconfigure"] = cast(
      JSONValue,
      _normalise_json(reconfigure),
    )

  entity_budget = statistics.get("entity_budget")
  if entity_budget is not None:
    stats_payload["entity_budget"] = cast(
      JSONValue,
      _normalise_json(entity_budget),
    )

  adaptive_polling = statistics.get("adaptive_polling")
  if adaptive_polling is not None:
    stats_payload["adaptive_polling"] = cast(
      JSONValue,
      _normalise_json(adaptive_polling),
    )

  resilience = statistics.get("resilience")
  if resilience is not None:
    stats_payload["resilience"] = cast(
      JSONValue,
      _normalise_json(resilience),
    )

  stats_payload = cast(JSONMutableMapping, _normalise_json(stats_payload))
  performance_payload = (
    cast(JSONMutableMapping, _normalise_json(performance_metrics))
    if isinstance(performance_metrics, Mapping)
    else cast(JSONMutableMapping, {})
  )

  metrics_output: JSONMutableMapping = {
    "update_frequency": performance_metrics["update_interval"],
    "data_freshness": "fresh" if coordinator.last_update_success else "stale",
    "memory_efficient": True,
    "cpu_efficient": True,
    "network_efficient": True,
    "error_rate": error_rate,
    "response_time": "fast",
    "rejection_metrics": rejection_metrics_payload,
    "statistics": stats_payload,
  }

  if performance_payload:
    merge_rejection_metric_values(
      metrics_output,
      performance_payload,
      rejection_metrics_payload,
    )
  else:
    merge_rejection_metric_values(
      metrics_output,
      rejection_metrics_payload,
    )

  return cast(JSONMutableMapping, _normalise_json(metrics_output))


async def _get_door_sensor_diagnostics(
  runtime_data: PawControlRuntimeData | None,
) -> JSONMutableMapping:
  """Summarise door sensor manager status and failure telemetry."""

  if runtime_data is None:
    return cast(JSONMutableMapping, {"available": False})

  manager = getattr(runtime_data, "door_sensor_manager", None)
  diagnostics: JSONMutableMapping = {
    "available": manager is not None,
    "manager_type": type(manager).__name__ if manager is not None else None,
  }

  telemetry: JSONMutableMapping = {}
  performance_stats = get_runtime_performance_stats(runtime_data)
  if isinstance(performance_stats, Mapping):
    failure_count = performance_stats.get("door_sensor_failure_count")
    if isinstance(failure_count, int | float):
      telemetry["failure_count"] = int(failure_count)

    last_failure = performance_stats.get("last_door_sensor_failure")
    if isinstance(last_failure, Mapping):
      telemetry["last_failure"] = cast(
        JSONMutableMapping,
        dict(last_failure),
      )

    failures = performance_stats.get("door_sensor_failures")
    if isinstance(failures, Sequence) and not isinstance(
      failures,
      str | bytes | bytearray,
    ):
      serialised_failures: list[JSONMutableMapping] = [
        cast(JSONMutableMapping, dict(entry))
        for entry in failures
        if isinstance(entry, Mapping)
      ]
      if serialised_failures:
        telemetry["failures"] = serialised_failures

    failure_summary = performance_stats.get("door_sensor_failure_summary")
    if isinstance(failure_summary, Mapping):
      serialised_summary = {
        str(key): cast(JSONMutableMapping, dict(value))
        for key, value in failure_summary.items()
        if isinstance(key, str) and isinstance(value, Mapping)
      }
      if serialised_summary:
        telemetry["failure_summary"] = serialised_summary

  if telemetry:
    diagnostics["telemetry"] = telemetry

  if manager is None:
    return diagnostics

  status_method = getattr(manager, "async_get_detection_status", None)
  if callable(status_method):
    try:
      diagnostics["status"] = await status_method()
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.debug("Could not gather door sensor status: %s", err)

  diag_method = getattr(manager, "get_diagnostics", None)
  if callable(diag_method):
    try:
      diagnostics["manager_diagnostics"] = diag_method()
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.debug("Could not capture door sensor diagnostics: %s", err)

  return diagnostics


async def _get_service_execution_diagnostics(
  runtime_data: PawControlRuntimeData | None,
) -> JSONMutableMapping:
  """Summarise guarded Home Assistant service execution telemetry."""

  if runtime_data is None:
    return cast(JSONMutableMapping, {"available": False})

  performance_stats = get_runtime_performance_stats(runtime_data)
  if not isinstance(performance_stats, Mapping):
    return cast(JSONMutableMapping, {"available": False})

  diagnostics: JSONMutableMapping = {"available": True}

  guard_metrics = performance_stats.get("service_guard_metrics")
  guard_payload = _normalise_service_guard_metrics(guard_metrics)
  if guard_payload is not None:
    diagnostics["guard_metrics"] = cast(JSONValue, guard_payload)

  entity_guard_payload: EntityFactoryGuardMetricsSnapshot | None = (
    resolve_entity_factory_guard_metrics(performance_stats)
    if isinstance(performance_stats, Mapping)
    else None
  )
  if entity_guard_payload:
    diagnostics["entity_factory_guard"] = cast(
      JSONMutableMapping,
      _normalise_json(dict(entity_guard_payload)),
    )

  metrics_payload = default_rejection_metrics()
  rejection_metrics = performance_stats.get("rejection_metrics")
  if isinstance(rejection_metrics, Mapping):
    merge_rejection_metric_values(
      metrics_payload,
      cast(JSONMapping, rejection_metrics),
    )
  diagnostics["rejection_metrics"] = cast(
    JSONMutableMapping,
    _normalise_json(metrics_payload),
  )

  service_results = performance_stats.get("service_results")
  if isinstance(service_results, Sequence) and not isinstance(
    service_results,
    str | bytes | bytearray,
  ):
    normalised_results: list[JSONMutableMapping] = [
      cast(JSONMutableMapping, _normalise_json(dict(result)))
      for result in service_results
      if isinstance(result, Mapping)
    ]
    if normalised_results:
      diagnostics["service_results"] = normalised_results

  last_result = performance_stats.get("last_service_result")
  if isinstance(last_result, Mapping):
    diagnostics["last_service_result"] = cast(
      JSONMutableMapping,
      _normalise_json(dict(last_result)),
    )

  service_call_telemetry = performance_stats.get("service_call_telemetry")
  telemetry_payload = _normalise_service_call_telemetry(
    service_call_telemetry,
  )
  if telemetry_payload is not None:
    diagnostics["service_call_telemetry"] = telemetry_payload

  return cast(JSONMutableMapping, _normalise_json(diagnostics))


def _get_bool_coercion_diagnostics(
  runtime_data: PawControlRuntimeData | None,
) -> BoolCoercionDiagnosticsPayload:
  """Expose recent bool coercion telemetry captured during normalisation."""

  metrics = get_bool_coercion_metrics()
  summary = update_runtime_bool_coercion_summary(runtime_data)
  recorded = bool(summary["recorded"])
  payload: BoolCoercionDiagnosticsPayload = {
    "recorded": recorded,
    "summary": summary,
  }

  if recorded and metrics:
    payload["metrics"] = metrics

  return payload


def _normalise_service_guard_metrics(
  payload: Any,
) -> ServiceGuardMetricsSnapshot | None:
  """Return a JSON-safe snapshot of aggregated guard metrics when available."""

  if not isinstance(payload, Mapping):
    return None

  executed = _coerce_int(payload.get("executed"))
  skipped = _coerce_int(payload.get("skipped"))

  reasons_payload: dict[str, int] | None = None
  reasons = payload.get("reasons")
  if isinstance(reasons, Mapping):
    serialised_reasons: dict[str, int] = {}
    for reason, count in reasons.items():
      coerced = _coerce_int(count)
      if coerced:
        serialised_reasons[str(reason)] = coerced
    if serialised_reasons:
      reasons_payload = serialised_reasons

  last_results_payload: ServiceGuardResultHistory | None = None
  history_payload = normalise_guard_history(payload.get("last_results"))
  if history_payload:
    last_results_payload = history_payload

  if (
    executed is None
    and skipped is None
    and reasons_payload is None
    and last_results_payload is None
  ):
    return None

  guard_metrics: ServiceGuardMetricsSnapshot = {}
  if executed is not None:
    guard_metrics["executed"] = executed
  if skipped is not None:
    guard_metrics["skipped"] = skipped
  if reasons_payload is not None:
    guard_metrics["reasons"] = reasons_payload
  if last_results_payload is not None:
    guard_metrics["last_results"] = last_results_payload

  return guard_metrics


def _normalise_service_call_telemetry(payload: Any) -> JSONMutableMapping | None:
  """Return a JSON-safe snapshot of service call telemetry metrics."""

  if not isinstance(payload, Mapping):
    return None

  telemetry_payload = cast(
    JSONMutableMapping,
    _normalise_json(dict(payload)),
  )

  per_service = payload.get("per_service")
  if isinstance(per_service, Mapping):
    telemetry_payload["per_service"] = {
      str(service): cast(JSONMutableMapping, _normalise_json(dict(entry)))
      for service, entry in per_service.items()
      if isinstance(entry, Mapping)
    }

  return telemetry_payload


def _coerce_int(value: Any) -> int | None:
  """Convert ``value`` into an integer when possible."""

  if isinstance(value, bool):
    return int(value)

  if isinstance(value, int):
    return value

  if isinstance(value, float):
    return int(value)

  if isinstance(value, str):
    try:
      return int(value.strip())
    except ValueError:
      return None

  return None


async def _get_data_statistics(
  runtime_data: PawControlRuntimeData | None,
  cache_snapshots: CacheDiagnosticsMap | None,
) -> DataStatisticsPayload:
  """Get data storage statistics.

  Args:
      runtime_data: Runtime data

  Returns:
      Data statistics
  """
  if runtime_data is None:
    return {"data_manager_available": False, "metrics": {}}

  data_manager = _resolve_data_manager(runtime_data)
  if data_manager is None:
    return {"data_manager_available": False, "metrics": {}}

  metrics_payload: JSONLikeMapping | None = None
  metrics_method = getattr(data_manager, "get_metrics", None)
  if callable(metrics_method):
    try:
      metrics_payload = metrics_method()
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.debug("Failed to gather data manager metrics: %s", err)

  if isinstance(metrics_payload, Mapping):
    metrics: JSONMutableMapping = {}
    for key, value in metrics_payload.items():
      metrics[str(key)] = cast(JSONValue, _normalise_json(value))
  else:
    metrics = cast(JSONMutableMapping, {})

  if cache_snapshots is None:
    cache_payload = _collect_cache_diagnostics(runtime_data)
  else:
    cache_payload = cache_snapshots

  if cache_payload is not None:
    metrics["cache_diagnostics"] = _serialise_cache_diagnostics_payload(
      cache_payload,
    )

  dogs_payload = getattr(runtime_data, "dogs", None)
  if isinstance(dogs_payload, Sequence) and not isinstance(
    dogs_payload,
    str | bytes | bytearray,
  ):
    metrics.setdefault("dogs", len(dogs_payload))

  return {
    "data_manager_available": True,
    "metrics": metrics,
  }


async def _get_recent_errors(entry_id: str) -> list[RecentErrorEntry]:
  """Get recent error logs for this integration.

  Args:
      entry_id: Configuration entry ID

  Returns:
      List of recent error information
  """
  # In a real implementation, this would collect actual error logs
  # from the Home Assistant logging system
  return [
    {
      "note": "Error collection not implemented in this version",
      "suggestion": "Check Home Assistant logs for detailed error information",
      "entry_id": entry_id,
    },
  ]


async def _get_debug_information(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> DebugInformationPayload:
  """Get debug information.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry

  Returns:
      Debug information
  """

  return {
    "debug_logging_enabled": _LOGGER.isEnabledFor(logging.DEBUG),
    "integration_version": "1.0.0",
    "quality_scale": "bronze",
    "supported_features": [
      "config_flow",
      "options_flow",
      "diagnostics",
      "repairs",
      "device_registry",
      "entity_registry",
      "services",
      "events",
      "multi_dog_support",
      "gps_tracking",
      "health_monitoring",
      "feeding_tracking",
      "notifications",
    ],
    "documentation_url": "https://github.com/BigDaddy1990/pawcontrol",
    "issue_tracker": "https://github.com/BigDaddy1990/pawcontrol/issues",
    "entry_id": entry.entry_id,
    "ha_version": hass.config.version,
  }


async def _get_loaded_platforms(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
  """Get list of loaded platforms for this entry.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry

  Returns:
      List of loaded platform names
  """
  # Check which platforms have been loaded by checking entity registry
  entity_registry = er.async_get(hass)
  entities = _entity_registry_entries_for_config_entry(
    entity_registry,
    entry.entry_id,
  )

  # Get unique platforms
  return list({entity.platform for entity in entities})


async def _get_registered_services(hass: HomeAssistant) -> list[str]:
  """Get list of registered services for this domain.

  Args:
      hass: Home Assistant instance

  Returns:
      List of registered service names
  """
  domain_services = hass.services.async_services().get(DOMAIN, {})

  return list(domain_services.keys())


def _calculate_module_usage(dogs: Sequence[DogConfigData]) -> ModuleUsageBreakdown:
  """Calculate module usage statistics across all dogs.

  Args:
      dogs: List of dog configurations

  Returns:
      Module usage statistics
  """
  module_counts: dict[str, int] = {
    MODULE_FEEDING: 0,
    MODULE_WALK: 0,
    MODULE_GPS: 0,
    MODULE_HEALTH: 0,
    MODULE_NOTIFICATIONS: 0,
  }

  dogs_sequence: Sequence[DogConfigData] = (
    dogs
    if isinstance(dogs, Sequence) and not isinstance(dogs, str | bytes | bytearray)
    else ()
  )

  valid_dogs: list[DogConfigData] = [
    cast(DogConfigData, dog) for dog in dogs_sequence if isinstance(dog, Mapping)
  ]

  total_dogs = len(valid_dogs)

  for dog in valid_dogs:
    modules_payload = dog.get("modules")
    modules = (
      modules_payload
      if isinstance(
        modules_payload,
        Mapping,
      )
      else {}
    )
    for module in module_counts:
      if modules.get(module, False):
        module_counts[module] += 1

  # Calculate percentages
  module_percentages: dict[str, float] = {}
  for module, count in module_counts.items():
    percentage = (count / total_dogs * 100) if total_dogs > 0 else 0
    module_percentages[f"{module}_percentage"] = round(percentage, 1)

  def _module_score(key: str) -> int:
    return module_counts[key]

  return {
    "counts": module_counts,
    "percentages": module_percentages,
    "most_used_module": max(module_counts, key=lambda module: module_counts[module])
    if module_counts
    else None,
    "least_used_module": min(
      module_counts,
      key=lambda module: module_counts[module],
    )
    if module_counts
    else None,
  }


def _redact_sensitive_data(data: JSONValue) -> JSONValue:
  """Recursively redact sensitive data from diagnostic information."""

  return redact_sensitive_data(data, patterns=_REDACTED_KEY_PATTERNS)
