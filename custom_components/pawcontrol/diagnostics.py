"""Diagnostics helpers for the PawControl integration.

The Platinum development plan requires richly structured diagnostics surfaces
that expose typed coordinator statistics, cache telemetry, and rejection
metrics. This module normalises runtime payloads into JSON-safe snapshots while
redacting sensitive fields so support tooling and the bundled dashboard can
ingest the data without custom adapters.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
import importlib
import logging
from typing import TYPE_CHECKING, Any, TypedDict, cast

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

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
from .push_router import get_entry_push_telemetry_snapshot
from .runtime_data import describe_runtime_store_status, get_runtime_data
from .service_guard import (
  ServiceGuardMetricsSnapshot,
  ServiceGuardResultHistory,
  ServiceGuardSnapshot,
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
from .utils import normalize_value

if TYPE_CHECKING:
  from .data_manager import PawControlDataManager  # noqa: E111
  from .notifications import PawControlNotificationManager  # noqa: E111


def _resolve_data_manager(
  runtime_data: PawControlRuntimeData | None,
) -> PawControlDataManager | None:
  """Return the data manager from the runtime container when available."""  # noqa: E111

  if runtime_data is None:  # noqa: E111
    return None

  return runtime_data.runtime_managers.data_manager  # noqa: E111


def _resolve_notification_manager(
  runtime_data: PawControlRuntimeData | None,
) -> PawControlNotificationManager | None:
  """Return the notification manager stored in runtime managers."""  # noqa: E111

  if runtime_data is None:  # noqa: E111
    return None

  return runtime_data.runtime_managers.notification_manager  # noqa: E111


class SetupFlagSnapshot(TypedDict):
  """Snapshot describing a persisted setup flag state."""  # noqa: E111

  value: bool  # noqa: E111
  source: str  # noqa: E111


SETUP_FLAG_LABELS = {
  "enable_analytics": "Analytics telemetry",
  "enable_cloud_backup": "Cloud backup",
  "debug_logging": "Debug logging",
}


SETUP_FLAG_LABEL_TRANSLATION_KEYS = {
  "enable_analytics": "component.pawcontrol.common.setup_flags_panel_flag_enable_analytics",  # noqa: E501
  "enable_cloud_backup": "component.pawcontrol.common.setup_flags_panel_flag_enable_cloud_backup",  # noqa: E501
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
  "system_settings": "component.pawcontrol.common.setup_flags_panel_source_system_settings",  # noqa: E501
  "advanced_settings": "component.pawcontrol.common.setup_flags_panel_source_advanced_settings",  # noqa: E501
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
  _translations_module = importlib.import_module(_TRANSLATIONS_IMPORT_PATH)  # noqa: E111
  _ASYNC_GET_TRANSLATIONS = getattr(  # noqa: E111
    _translations_module,
    "async_get_translations",
    None,
  )
except ModuleNotFoundError, AttributeError:
  _ASYNC_GET_TRANSLATIONS = None  # noqa: E111


async def _async_get_translations_wrapper(
  hass: HomeAssistant,
  language: str,
  category: str,
  integrations: set[str],
) -> dict[str, str]:
  """Call Home Assistant translations when available."""  # noqa: E111

  if _ASYNC_GET_TRANSLATIONS is None:  # noqa: E111
    return {}

  return await _ASYNC_GET_TRANSLATIONS(hass, language, category, integrations)  # noqa: E111


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
  """Return localised labels for setup flag diagnostics."""  # noqa: E111

  config_language = cast(str | None, getattr(hass.config, "language", None))  # noqa: E111
  target_language = (language or config_language or "en").lower()  # noqa: E111

  async def _async_fetch(lang: str) -> dict[str, str]:  # noqa: E111
    if _ASYNC_GET_TRANSLATIONS is None:
      return {}  # noqa: E111
    try:
      return await _ASYNC_GET_TRANSLATIONS(hass, lang, "component", {DOMAIN})  # noqa: E111
    except Exception:  # pragma: no cover - defensive guard for HA API
      _LOGGER.debug(  # noqa: E111
        "Failed to load %s translations for setup flags",
        lang,
      )
      return {}  # noqa: E111

  translations = await _async_fetch(target_language)  # noqa: E111
  fallback_language = "en"  # noqa: E111
  if target_language == fallback_language:  # noqa: E111
    fallback_translations = translations
  else:  # noqa: E111
    fallback_translations = await _async_fetch(fallback_language)

  def _lookup(key: str, default: str) -> str:  # noqa: E111
    return translations.get(key) or fallback_translations.get(key) or default

  flag_labels = {  # noqa: E111
    key: _lookup(SETUP_FLAG_LABEL_TRANSLATION_KEYS[key], label)
    for key, label in SETUP_FLAG_LABELS.items()
  }

  source_labels = {  # noqa: E111
    key: _lookup(SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS[key], label)
    for key, label in SETUP_FLAG_SOURCE_LABELS.items()
  }

  title = _lookup(  # noqa: E111
    SETUP_FLAGS_PANEL_TITLE_TRANSLATION_KEY,
    SETUP_FLAGS_PANEL_TITLE,
  )
  description = _lookup(  # noqa: E111
    SETUP_FLAGS_PANEL_DESCRIPTION_TRANSLATION_KEY,
    SETUP_FLAGS_PANEL_DESCRIPTION,
  )

  return target_language, flag_labels, source_labels, title, description  # noqa: E111


def _collect_setup_flag_snapshots(entry: ConfigEntry) -> dict[str, SetupFlagSnapshot]:
  """Return analytics, backup, and debug logging flag states and sources."""  # noqa: E111

  raw_options = entry.options  # noqa: E111
  options = (  # noqa: E111
    cast(JSONMapping, raw_options)
    if isinstance(
      raw_options,
      Mapping,
    )
    else {}
  )
  system_raw = options.get("system_settings")  # noqa: E111
  system = (  # noqa: E111
    cast(JSONMapping, system_raw)
    if isinstance(
      system_raw,
      Mapping,
    )
    else {}
  )
  advanced_raw = options.get("advanced_settings")  # noqa: E111
  advanced = (  # noqa: E111
    cast(JSONMapping, advanced_raw)
    if isinstance(
      advanced_raw,
      Mapping,
    )
    else {}
  )
  entry_data = cast(JSONMapping, entry.data)  # noqa: E111

  def _resolve_flag(  # noqa: E111
    key: str,
    *,
    allow_advanced: bool = False,
  ) -> SetupFlagSnapshot:
    candidate = options.get(key)
    if isinstance(candidate, bool):
      return SetupFlagSnapshot(value=candidate, source="options")  # noqa: E111

    candidate = system.get(key)
    if isinstance(candidate, bool):
      return SetupFlagSnapshot(value=candidate, source="system_settings")  # noqa: E111

    if allow_advanced:
      candidate = advanced.get(key)  # noqa: E111
      if isinstance(candidate, bool):  # noqa: E111
        return SetupFlagSnapshot(value=candidate, source="advanced_settings")

    candidate = entry_data.get(key)
    if isinstance(candidate, bool):
      return SetupFlagSnapshot(value=candidate, source="config_entry")  # noqa: E111

    return SetupFlagSnapshot(value=False, source="default")

  return {  # noqa: E111
    "enable_analytics": _resolve_flag("enable_analytics"),
    "enable_cloud_backup": _resolve_flag("enable_cloud_backup"),
    "debug_logging": _resolve_flag("debug_logging", allow_advanced=True),
  }


def _summarise_setup_flags(entry: ConfigEntry) -> dict[str, bool]:
  """Return analytics, backup, and debug logging flags for diagnostics."""  # noqa: E111

  snapshots = _collect_setup_flag_snapshots(entry)  # noqa: E111
  return {key: snapshot["value"] for key, snapshot in snapshots.items()}  # noqa: E111


async def _async_build_setup_flags_panel(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> SetupFlagsPanelPayload:
  """Expose setup flag metadata in a dashboard-friendly structure."""  # noqa: E111

  (  # noqa: E111
    language,
    flag_labels,
    resolved_source_labels,
    title,
    description,
  ) = await _async_resolve_setup_flag_translations(hass)

  snapshots = _collect_setup_flag_snapshots(entry)  # noqa: E111
  flags: list[SetupFlagPanelEntry] = []  # noqa: E111
  source_labels: SetupFlagSourceLabels = dict(resolved_source_labels)  # noqa: E111
  source_labels_default: SetupFlagSourceLabels = dict(  # noqa: E111
    SETUP_FLAG_SOURCE_LABELS,
  )
  source_label_translation_keys: SetupFlagSourceLabels = dict(  # noqa: E111
    SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS,
  )

  def _resolve_source_labels(source: str) -> tuple[str, str, str]:  # noqa: E111
    default_label = SETUP_FLAG_SOURCE_LABELS.get(source, source)
    translation_key = SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS.get(
      source,
      SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS["default"],
    )
    label = source_labels.get(source, default_label)
    return label, default_label, translation_key

  for key, snapshot in snapshots.items():  # noqa: E111
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

  enabled_count = sum(1 for flag in flags if flag["enabled"])  # noqa: E111
  disabled_count = len(flags) - enabled_count  # noqa: E111

  source_breakdown: SetupFlagSourceBreakdown = {}  # noqa: E111
  for flag in flags:  # noqa: E111
    source = cast(str, flag["source"])
    source_breakdown[source] = source_breakdown.get(source, 0) + 1

  return {  # noqa: E111
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
  """Return default coordinator statistics when telemetry is unavailable."""  # noqa: E111

  update_counts: CoordinatorUpdateCounts = {  # noqa: E111
    "total": 0,
    "successful": 0,
    "failed": 0,
  }
  performance_metrics: CoordinatorPerformanceMetrics = {  # noqa: E111
    "success_rate": 0.0,
    "cache_entries": 0,
    "cache_hit_rate": 0.0,
    "consecutive_errors": 0,
    "last_update": None,
    "update_interval": 0.0,
    "api_calls": 0,
  }
  health_indicators: CoordinatorHealthIndicators = {  # noqa: E111
    "consecutive_errors": 0,
    "stability_window_ok": True,
  }
  return {  # noqa: E111
    "update_counts": update_counts,
    "performance_metrics": performance_metrics,
    "health_indicators": health_indicators,
    "rejection_metrics": default_rejection_metrics(),
  }


def _apply_rejection_metrics_to_performance(
  performance_metrics: CoordinatorPerformanceMetrics,
  rejection_metrics: CoordinatorRejectionMetrics,
) -> None:
  """Copy rejection metrics into the coordinator performance snapshot."""  # noqa: E111

  merge_rejection_metric_values(performance_metrics, rejection_metrics)  # noqa: E111


def _build_default_rejection_metrics_payload() -> JSONMutableMapping:
  """Return a JSON-safe default rejection metrics payload."""  # noqa: E111

  return cast(  # noqa: E111
    JSONMutableMapping,
    normalize_value(dict(default_rejection_metrics())),
  )


def _build_statistics_payload(
  payload: JSONLikeMapping,
) -> CoordinatorStatisticsPayload:
  """Normalise coordinator statistics into the active typed structure."""  # noqa: E111

  stats = _fallback_coordinator_statistics()  # noqa: E111
  update_counts = stats["update_counts"]  # noqa: E111
  performance_metrics = stats["performance_metrics"]  # noqa: E111
  health_indicators = stats["health_indicators"]  # noqa: E111

  counts_payload = payload.get("update_counts")  # noqa: E111
  if isinstance(counts_payload, Mapping):  # noqa: E111
    total_value = _coerce_int(counts_payload.get("total"))
    if total_value is not None:
      update_counts["total"] = total_value  # noqa: E111
    failed_value = _coerce_int(counts_payload.get("failed"))
    if failed_value is not None:
      update_counts["failed"] = failed_value  # noqa: E111
    successful_value = _coerce_int(counts_payload.get("successful"))
    if successful_value is not None:
      update_counts["successful"] = successful_value  # noqa: E111
  else:  # noqa: E111
    total_value = _coerce_int(payload.get("total_updates"))
    failed_value = _coerce_int(payload.get("failed"))
    if total_value is not None:
      update_counts["total"] = total_value  # noqa: E111
    if failed_value is not None:
      update_counts["failed"] = failed_value  # noqa: E111
    if total_value is not None and failed_value is not None:
      update_counts["successful"] = max(total_value - failed_value, 0)  # noqa: E111

  metrics_payload = payload.get("performance_metrics")  # noqa: E111
  if isinstance(metrics_payload, Mapping):  # noqa: E111
    success_rate = metrics_payload.get("success_rate")
    if isinstance(success_rate, int | float):
      performance_metrics["success_rate"] = float(success_rate)  # noqa: E111
    cache_entries = _coerce_int(metrics_payload.get("cache_entries"))
    if cache_entries is not None:
      performance_metrics["cache_entries"] = cache_entries  # noqa: E111
    cache_hit_rate = metrics_payload.get("cache_hit_rate")
    if isinstance(cache_hit_rate, int | float):
      performance_metrics["cache_hit_rate"] = float(cache_hit_rate)  # noqa: E111
    consecutive_errors = _coerce_int(
      metrics_payload.get("consecutive_errors"),
    )
    if consecutive_errors is not None:
      performance_metrics["consecutive_errors"] = consecutive_errors  # noqa: E111
      health_indicators["consecutive_errors"] = consecutive_errors  # noqa: E111
      health_indicators["stability_window_ok"] = consecutive_errors < 5  # noqa: E111
    last_update = metrics_payload.get("last_update")
    if last_update is not None:
      performance_metrics["last_update"] = last_update  # noqa: E111
    update_interval = metrics_payload.get("update_interval")
    if isinstance(update_interval, int | float):
      performance_metrics["update_interval"] = float(update_interval)  # noqa: E111
    api_calls = _coerce_int(metrics_payload.get("api_calls"))
    if api_calls is not None:
      performance_metrics["api_calls"] = api_calls  # noqa: E111
  else:  # noqa: E111
    update_interval = payload.get("update_interval")
    if isinstance(update_interval, int | float):
      performance_metrics["update_interval"] = float(update_interval)  # noqa: E111

  health_payload = payload.get("health_indicators")  # noqa: E111
  if isinstance(health_payload, Mapping):  # noqa: E111
    consecutive_errors = _coerce_int(
      health_payload.get("consecutive_errors"),
    )
    if consecutive_errors is not None:
      health_indicators["consecutive_errors"] = consecutive_errors  # noqa: E111
      health_indicators["stability_window_ok"] = consecutive_errors < 5  # noqa: E111
    stability_ok = health_payload.get("stability_window_ok")
    if isinstance(stability_ok, bool):
      health_indicators["stability_window_ok"] = stability_ok  # noqa: E111

  total_updates = update_counts["total"]  # noqa: E111
  successful_updates = update_counts["successful"]  # noqa: E111
  if total_updates and successful_updates and not payload.get("success_rate"):  # noqa: E111
    performance_metrics["success_rate"] = round(
      (successful_updates / total_updates) * 100,
      2,
    )

  repairs = payload.get("repairs")  # noqa: E111
  if repairs is not None:  # noqa: E111
    stats["repairs"] = cast(Any, repairs)

  reconfigure = payload.get("reconfigure")  # noqa: E111
  if reconfigure is not None:  # noqa: E111
    stats["reconfigure"] = cast(Any, reconfigure)

  entity_budget = payload.get("entity_budget")  # noqa: E111
  if entity_budget is not None:  # noqa: E111
    stats["entity_budget"] = cast(Any, entity_budget)

  adaptive_polling = payload.get("adaptive_polling")  # noqa: E111
  if adaptive_polling is not None:  # noqa: E111
    stats["adaptive_polling"] = cast(Any, adaptive_polling)

  resilience = payload.get("resilience")  # noqa: E111
  if resilience is not None:  # noqa: E111
    stats["resilience"] = cast(Any, resilience)

  rejection_metrics = payload.get("rejection_metrics")  # noqa: E111
  if isinstance(rejection_metrics, Mapping):  # noqa: E111
    stats["rejection_metrics"] = derive_rejection_metrics(
      cast(JSONMapping, rejection_metrics),
    )

  return stats  # noqa: E111


def _entity_registry_entries_for_config_entry(
  entity_registry: er.EntityRegistry,
  entry_id: str,
) -> list[er.RegistryEntry]:
  """Return registry entries associated with a config entry."""  # noqa: E111

  module_helper = getattr(er, "async_entries_for_config_entry", None)  # noqa: E111
  if callable(module_helper):  # noqa: E111
    return list(module_helper(entity_registry, entry_id))

  entities = getattr(entity_registry, "entities", {})  # noqa: E111
  return [  # noqa: E111
    entry
    for entry in entities.values()
    if getattr(entry, "config_entry_id", None) == entry_id
  ]


def _device_registry_entries_for_config_entry(
  device_registry: dr.DeviceRegistry,
  entry_id: str,
) -> list[dr.DeviceEntry]:
  """Return device registry entries associated with a config entry."""  # noqa: E111

  module_helper = getattr(dr, "async_entries_for_config_entry", None)  # noqa: E111
  if callable(module_helper):  # noqa: E111
    return list(module_helper(device_registry, entry_id))

  devices = getattr(device_registry, "devices", {})  # noqa: E111
  return [  # noqa: E111
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
  """  # noqa: E111
  _LOGGER.debug(  # noqa: E111
    "Generating diagnostics for Paw Control entry: %s",
    entry.entry_id,
  )

  # Get runtime data using the shared helper (runtime adoption still being proven)  # noqa: E114
  runtime_data = get_runtime_data(hass, entry)  # noqa: E111
  coordinator = runtime_data.coordinator if runtime_data else None  # noqa: E111

  # Base diagnostics structure  # noqa: E114
  cache_snapshots = _collect_cache_diagnostics(runtime_data)  # noqa: E111

  diagnostics_payload: dict[str, object] = {  # noqa: E111
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
    "push_telemetry": get_entry_push_telemetry_snapshot(hass, entry.entry_id),
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

  runtime_store_history = get_runtime_store_health(runtime_data)  # noqa: E111
  if runtime_store_history:  # noqa: E111
    diagnostics_payload["runtime_store_history"] = runtime_store_history
    assessment = runtime_store_history.get("assessment")
    if isinstance(assessment, Mapping):
      diagnostics_payload["runtime_store_assessment"] = cast(  # noqa: E111
        RuntimeStoreHealthAssessment,
        dict(assessment),
      )
    timeline_segments = runtime_store_history.get(
      "assessment_timeline_segments",
    )
    if isinstance(timeline_segments, Sequence):
      diagnostics_payload["runtime_store_timeline_segments"] = [  # noqa: E111
        cast(RuntimeStoreAssessmentTimelineSegment, dict(segment))
        for segment in timeline_segments
        if isinstance(segment, Mapping)
      ]
    timeline_summary = runtime_store_history.get(
      "assessment_timeline_summary",
    )
    if isinstance(timeline_summary, Mapping):
      diagnostics_payload["runtime_store_timeline_summary"] = cast(  # noqa: E111
        RuntimeStoreAssessmentTimelineSummary,
        dict(timeline_summary),
      )

  if cache_snapshots is not None:  # noqa: E111
    diagnostics_payload["cache_diagnostics"] = _serialise_cache_diagnostics_payload(
      cache_snapshots,
    )

  normalised_payload = cast(  # noqa: E111
    JSONMutableMapping,
    normalize_value(diagnostics_payload),
  )

  # Redact sensitive information  # noqa: E114
  redacted_diagnostics = cast(  # noqa: E111
    JSONMutableMapping,
    _redact_sensitive_data(cast(JSONValue, normalised_payload)),
  )

  _LOGGER.debug(  # noqa: E111
    "Diagnostics generated successfully for entry %s",
    entry.entry_id,
  )
  return redacted_diagnostics  # noqa: E111


def _get_resilience_escalation_snapshot(
  runtime_data: PawControlRuntimeData | None,
) -> ResilienceEscalationSnapshot:
  """Build diagnostics metadata for the resilience escalation helper."""  # noqa: E111

  if runtime_data is None:  # noqa: E111
    return {"available": False}

  script_manager = getattr(runtime_data, "script_manager", None)  # noqa: E111
  if script_manager is None:  # noqa: E111
    return {"available": False}

  snapshot = script_manager.get_resilience_escalation_snapshot()  # noqa: E111
  if snapshot is None:  # noqa: E111
    return {"available": False}

  return cast(  # noqa: E111
    ResilienceEscalationSnapshot,
    normalize_value(cast(JSONLikeMapping, snapshot)),
  )


def _get_resilience_diagnostics(
  runtime_data: PawControlRuntimeData | None,
  coordinator: PawControlCoordinator | None,
) -> JSONMutableMapping:
  """Build a resilience diagnostics payload using stored runtime telemetry."""  # noqa: E111

  diagnostics: CoordinatorResilienceDiagnostics | None = None  # noqa: E111

  if runtime_data is not None:  # noqa: E111
    diagnostics = get_runtime_resilience_diagnostics(runtime_data)

  if diagnostics is None and coordinator is not None:  # noqa: E111
    fetch_stats = getattr(coordinator, "get_update_statistics", None)
    if callable(fetch_stats):
      try:  # noqa: E111
        raw_stats = fetch_stats()
      except Exception:  # pragma: no cover - diagnostics guard  # noqa: E111
        raw_stats = None
      if isinstance(raw_stats, Mapping):  # noqa: E111
        resilience_payload = raw_stats.get("resilience")
        if isinstance(resilience_payload, Mapping):
          diagnostics = cast(  # noqa: E111
            CoordinatorResilienceDiagnostics,
            dict(resilience_payload),
          )

  if diagnostics is None:  # noqa: E111
    return cast(JSONMutableMapping, {"available": False})

  payload: JSONMutableMapping = {"available": True, "schema_version": 1}  # noqa: E111

  summary = diagnostics.get("summary")  # noqa: E111
  if isinstance(summary, Mapping):  # noqa: E111
    payload["summary"] = cast(JSONMutableMapping, dict(summary))
  else:  # noqa: E111
    payload["summary"] = None

  breakers = diagnostics.get("breakers")  # noqa: E111
  if isinstance(breakers, Mapping):  # noqa: E111
    payload["breakers"] = {
      str(name): cast(JSONMutableMapping, dict(values))
      for name, values in breakers.items()
      if isinstance(values, Mapping)
    }

  return cast(JSONMutableMapping, normalize_value(payload))  # noqa: E111


async def _get_config_entry_diagnostics(entry: ConfigEntry) -> JSONMutableMapping:
  """Get configuration entry diagnostic information.

  Args:
      entry: Configuration entry

  Returns:
      Configuration diagnostics
  """  # noqa: E111
  version = getattr(entry, "version", None)  # noqa: E111
  state = getattr(entry, "state", None)  # noqa: E111
  if isinstance(state, ConfigEntryState):  # noqa: E111
    state_value: str | None = state.value
  elif state is None:  # noqa: E111
    state_value = None
  else:  # noqa: E111
    state_value = str(state)

  created_at = getattr(entry, "created_at", None)  # noqa: E111
  modified_at = getattr(entry, "modified_at", None)  # noqa: E111

  supports_options = getattr(entry, "supports_options", False)  # noqa: E111
  supports_reconfigure = getattr(entry, "supports_reconfigure", False)  # noqa: E111
  supports_remove_device = getattr(entry, "supports_remove_device", False)  # noqa: E111
  supports_unload = getattr(entry, "supports_unload", False)  # noqa: E111
  dogs_value = entry.data.get(CONF_DOGS)  # noqa: E111
  dogs_configured = (  # noqa: E111
    len(dogs_value)
    if isinstance(dogs_value, Sequence)
    and not isinstance(dogs_value, str | bytes | bytearray)
    else 0
  )

  return cast(  # noqa: E111
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
  """  # noqa: E111
  config = hass.config  # noqa: E111
  time_zone = getattr(config, "time_zone", None)  # noqa: E111
  safe_mode = getattr(config, "safe_mode", False)  # noqa: E111
  recovery_mode = getattr(config, "recovery_mode", False)  # noqa: E111
  start_time = getattr(config, "start_time", None)  # noqa: E111
  uptime_seconds: float | None = None  # noqa: E111
  if start_time:  # noqa: E111
    uptime_seconds = (dt_util.utcnow() - start_time).total_seconds()

  return cast(  # noqa: E111
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
  """Return cache diagnostics captured by the data manager when available."""  # noqa: E111

  if runtime_data is None:  # noqa: E111
    return None

  data_manager = _resolve_data_manager(runtime_data)  # noqa: E111
  if data_manager is None:  # noqa: E111
    return None

  snapshot_method = getattr(data_manager, "cache_snapshots", None)  # noqa: E111
  if not callable(snapshot_method):  # noqa: E111
    return None

  try:  # noqa: E111
    raw_snapshots = snapshot_method()
  except Exception as err:  # pragma: no cover - defensive guard  # noqa: E111
    _LOGGER.debug("Unable to collect cache diagnostics: %s", err)
    return None

  if isinstance(raw_snapshots, Mapping):  # noqa: E111
    snapshots = dict(raw_snapshots)
  elif isinstance(raw_snapshots, dict):  # noqa: E111
    snapshots = raw_snapshots
  else:  # noqa: E111
    _LOGGER.debug(
      "Unexpected cache diagnostics payload type: %s",
      type(raw_snapshots).__name__,
    )
    return None

  normalised: CacheDiagnosticsMap = {}  # noqa: E111
  for name, payload in snapshots.items():  # noqa: E111
    if not isinstance(name, str) or not name:
      _LOGGER.debug(  # noqa: E111
        "Skipping cache diagnostics entry with invalid name: %s",
        name,
      )
      continue  # noqa: E111

    normalised[name] = _normalise_cache_snapshot(payload)

  return normalised or None  # noqa: E111


def _normalise_cache_snapshot(payload: Any) -> CacheDiagnosticsSnapshot:
  """Coerce arbitrary cache payloads into diagnostics-friendly snapshots."""  # noqa: E111

  if isinstance(payload, CacheDiagnosticsSnapshot):  # noqa: E111
    snapshot = payload
  elif isinstance(payload, Mapping):  # noqa: E111
    snapshot = CacheDiagnosticsSnapshot.from_mapping(
      cast(JSONMapping, payload),
    )
  else:  # noqa: E111
    return CacheDiagnosticsSnapshot(
      error=f"Unsupported diagnostics payload: {type(payload).__name__}",
      snapshot={"value": normalize_value(payload)},
    )

  repair_summary = snapshot.repair_summary  # noqa: E111
  resolved_summary = ensure_cache_repair_aggregate(repair_summary)  # noqa: E111
  if resolved_summary is not None:  # noqa: E111
    snapshot.repair_summary = resolved_summary
  elif isinstance(repair_summary, Mapping):  # noqa: E111
    try:
      snapshot.repair_summary = CacheRepairAggregate.from_mapping(  # noqa: E111
        repair_summary,
      )
    except Exception:  # pragma: no cover - defensive fallback
      snapshot.repair_summary = None  # noqa: E111
  else:  # noqa: E111
    snapshot.repair_summary = None

  if snapshot.stats is not None:  # noqa: E111
    snapshot.stats = cast(
      JSONMutableMapping,
      normalize_value(snapshot.stats),
    )

  if snapshot.diagnostics is not None:  # noqa: E111
    diagnostics_payload = normalize_value(snapshot.diagnostics)
    if isinstance(diagnostics_payload, Mapping):
      snapshot.diagnostics = cast(  # noqa: E111
        CacheDiagnosticsMetadata,
        {str(key): value for key, value in diagnostics_payload.items()},
      )
    else:
      snapshot.diagnostics = None  # noqa: E111

  if snapshot.snapshot is not None:  # noqa: E111
    snapshot.snapshot = cast(
      JSONMutableMapping,
      normalize_value(snapshot.snapshot),
    )

  if not snapshot.to_mapping():  # noqa: E111
    snapshot.snapshot = {"value": normalize_value(payload)}

  return snapshot  # noqa: E111


def _serialise_cache_diagnostics_payload(
  payload: JSONLikeMapping | CacheDiagnosticsMap,
) -> JSONMutableMapping:
  """Convert cache diagnostics snapshots into JSON-safe payloads."""  # noqa: E111

  serialised: JSONMutableMapping = {}  # noqa: E111
  for name, snapshot in payload.items():  # noqa: E111
    serialised[str(name)] = _serialise_cache_snapshot(snapshot)
  return serialised  # noqa: E111


def _serialise_cache_snapshot(snapshot: object) -> JSONMutableMapping:
  """Return a JSON-serialisable payload for a cache diagnostics snapshot."""  # noqa: E111

  snapshot_input: object  # noqa: E111
  if isinstance(snapshot, CacheDiagnosticsSnapshot):  # noqa: E111
    snapshot_input = CacheDiagnosticsSnapshot.from_mapping(
      snapshot.to_mapping(),
    )
  else:  # noqa: E111
    snapshot_input = snapshot

  normalised_snapshot = _normalise_cache_snapshot(snapshot_input)  # noqa: E111
  summary = (  # noqa: E111
    normalised_snapshot.repair_summary
    if isinstance(normalised_snapshot.repair_summary, CacheRepairAggregate)
    else None
  )
  snapshot_payload = normalised_snapshot.to_mapping()  # noqa: E111

  if summary is not None:  # noqa: E111
    snapshot_payload["repair_summary"] = summary.to_mapping()
  else:  # noqa: E111
    snapshot_payload.pop("repair_summary", None)

  return cast(JSONMutableMapping, normalize_value(snapshot_payload))  # noqa: E111


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
  """  # noqa: E111
  if runtime_data:  # noqa: E111
    coordinator = runtime_data.coordinator
    data_manager = _resolve_data_manager(runtime_data)
    notification_manager = _resolve_notification_manager(runtime_data)
  else:  # noqa: E111
    coordinator = None
    data_manager = None
    notification_manager = None

  entry_loaded = entry.state is ConfigEntryState.LOADED  # noqa: E111

  return cast(  # noqa: E111
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
  """Return notification-specific diagnostics."""  # noqa: E111

  if runtime_data is None:  # noqa: E111
    return cast(
      JSONMutableMapping,
      {
        "available": False,
        "rejection_metrics": _build_notification_rejection_metrics(None),
      },
    )

  notification_manager = _resolve_notification_manager(runtime_data)  # noqa: E111
  if notification_manager is None:  # noqa: E111
    return cast(
      JSONMutableMapping,
      {
        "available": False,
        "rejection_metrics": _build_notification_rejection_metrics(None),
      },
    )

  stats = await notification_manager.async_get_performance_statistics()  # noqa: E111
  delivery = notification_manager.get_delivery_status_snapshot()  # noqa: E111
  stats_payload = cast(JSONValue, normalize_value(stats))  # noqa: E111
  delivery_payload = cast(JSONValue, normalize_value(delivery))  # noqa: E111

  return cast(  # noqa: E111
    JSONMutableMapping,
    {
      "available": True,
      "manager_stats": stats_payload,
      "delivery_status": delivery_payload,
      "rejection_metrics": _build_notification_rejection_metrics(delivery),
    },
  )


def _build_notification_rejection_metrics(
  delivery: Mapping[str, object] | None,
) -> JSONMutableMapping:
  """Return a per-service rejection/failure snapshot for notifications."""  # noqa: E111

  payload: JSONMutableMapping = {  # noqa: E111
    "schema_version": 1,
    "total_services": 0,
    "total_failures": 0,
    "services_with_failures": [],
    "service_failures": {},
    "service_consecutive_failures": {},
    "service_last_error_reasons": {},
    "service_last_errors": {},
  }

  if not isinstance(delivery, Mapping):  # noqa: E111
    return payload

  services = delivery.get("services")  # noqa: E111
  if not isinstance(services, Mapping):  # noqa: E111
    return payload

  service_failures: dict[str, int] = {}  # noqa: E111
  consecutive_failures: dict[str, int] = {}  # noqa: E111
  last_error_reasons: dict[str, str] = {}  # noqa: E111
  last_errors: dict[str, str] = {}  # noqa: E111
  services_with_failures: list[str] = []  # noqa: E111
  total_failures = 0  # noqa: E111

  for service_name, service_payload in services.items():  # noqa: E111
    if not isinstance(service_name, str) or not isinstance(service_payload, Mapping):
      continue  # noqa: E111

    failures = _coerce_int(service_payload.get("total_failures")) or 0
    consecutive = _coerce_int(service_payload.get("consecutive_failures")) or 0
    service_failures[service_name] = failures
    consecutive_failures[service_name] = consecutive
    total_failures += failures
    if failures:
      services_with_failures.append(service_name)  # noqa: E111

    last_error_reason = service_payload.get("last_error_reason")
    if isinstance(last_error_reason, str) and last_error_reason:
      last_error_reasons[service_name] = last_error_reason  # noqa: E111

    last_error = service_payload.get("last_error")
    if isinstance(last_error, str) and last_error:
      last_errors[service_name] = last_error  # noqa: E111

  payload["total_services"] = len(service_failures)  # noqa: E111
  payload["total_failures"] = total_failures  # noqa: E111
  payload["services_with_failures"] = sorted(services_with_failures)  # noqa: E111
  payload["service_failures"] = service_failures  # noqa: E111
  payload["service_consecutive_failures"] = consecutive_failures  # noqa: E111
  payload["service_last_error_reasons"] = last_error_reasons  # noqa: E111
  payload["service_last_errors"] = last_errors  # noqa: E111

  return payload  # noqa: E111


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
  """  # noqa: E111

  payload: JSONMutableMapping = {  # noqa: E111
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

  classified_errors: dict[str, int] = {}  # noqa: E111
  guard_reasons: dict[str, int] = {}  # noqa: E111
  guard_skipped = 0  # noqa: E111

  # Process guard metrics (skip counts and reasons)  # noqa: E114
  if isinstance(guard_metrics, Mapping):  # noqa: E111
    guard_skipped = _coerce_int(guard_metrics.get("skipped")) or 0
    reasons_raw = guard_metrics.get("reasons")
    if isinstance(reasons_raw, Mapping):
      for reason_key, count in reasons_raw.items():  # noqa: E111
        coerced = _coerce_int(count) or 0
        if not coerced:
          continue  # noqa: E111
        reason_text = str(reason_key)
        guard_reasons[reason_text] = guard_reasons.get(reason_text, 0) + coerced
        classification = classify_error_reason(reason_text, error=None)
        classified_errors[classification] = (
          classified_errors.get(classification, 0) + coerced
        )

  notification_failures = 0  # noqa: E111
  notification_reasons: dict[str, int] = {}  # noqa: E111
  services_with_failures: list[str] = []  # noqa: E111
  # Process notification delivery failures  # noqa: E114
  if isinstance(delivery, Mapping):  # noqa: E111
    services = delivery.get("services")
    if isinstance(services, Mapping):
      for service_name, service_payload in services.items():  # noqa: E111
        if not isinstance(service_name, str) or not isinstance(
          service_payload, Mapping
        ):
          continue  # noqa: E111
        failures = _coerce_int(service_payload.get("total_failures")) or 0
        if not failures:
          continue  # noqa: E111
        notification_failures += failures
        services_with_failures.append(service_name)
        last_error_reason = service_payload.get("last_error_reason")
        service_reason: str | None = (
          last_error_reason
          if isinstance(last_error_reason, str) and last_error_reason
          else None
        )
        last_error = service_payload.get("last_error")
        error_text = last_error if isinstance(last_error, str) else None
        if service_reason is not None:
          notification_reasons[service_reason] = (  # noqa: E111
            notification_reasons.get(service_reason, 0) + failures
          )
        classification = classify_error_reason(service_reason, error=error_text)
        classified_errors[classification] = (
          classified_errors.get(classification, 0) + failures
        )

  total_errors = guard_skipped + notification_failures  # noqa: E111

  payload["available"] = bool(  # noqa: E111
    guard_skipped
    or guard_reasons
    or notification_failures
    or notification_reasons
    or services_with_failures
  )
  payload["total_errors"] = total_errors  # noqa: E111
  payload["guard"] = {  # noqa: E111
    "skipped": guard_skipped,
    "reasons": guard_reasons,
  }
  payload["notifications"] = {  # noqa: E111
    "total_failures": notification_failures,
    "services_with_failures": sorted(services_with_failures),
    "reasons": notification_reasons,
  }
  payload["classified_errors"] = classified_errors  # noqa: E111

  return payload  # noqa: E111


def _get_guard_notification_error_metrics(
  runtime_data: PawControlRuntimeData | None,
) -> JSONMutableMapping:
  """Collect aggregated guard and notification error metrics from runtime.

  This helper extracts guard and delivery snapshots from runtime data (if
  available) and delegates to ``_build_guard_notification_error_metrics``.
  """  # noqa: E111
  if runtime_data is None:  # noqa: E111
    return _build_guard_notification_error_metrics(None, None)

  performance_stats = get_runtime_performance_stats(runtime_data)  # noqa: E111
  guard_metrics: Mapping[str, object] | None = None  # noqa: E111
  if isinstance(performance_stats, Mapping):  # noqa: E111
    guard_metrics_raw = performance_stats.get("service_guard_metrics")
    if isinstance(guard_metrics_raw, Mapping):
      guard_metrics = guard_metrics_raw  # noqa: E111

  notification_manager = _resolve_notification_manager(runtime_data)  # noqa: E111
  delivery_status: Mapping[str, object] | None = None  # noqa: E111
  if notification_manager is not None:  # noqa: E111
    delivery = notification_manager.get_delivery_status_snapshot()
    if isinstance(delivery, Mapping):
      delivery_status = delivery  # noqa: E111

  return _build_guard_notification_error_metrics(guard_metrics, delivery_status)  # noqa: E111


async def _get_coordinator_diagnostics(
  coordinator: PawControlCoordinator | None,
) -> JSONMutableMapping:
  """Get coordinator diagnostic information.

  Args:
      coordinator: Data coordinator instance

  Returns:
      Coordinator diagnostics
  """  # noqa: E111
  if not coordinator:  # noqa: E111
    return cast(
      JSONMutableMapping,
      {"available": False, "reason": "Coordinator not initialized"},
    )

  try:  # noqa: E111
    stats: CoordinatorStatisticsPayload = coordinator.get_update_statistics()
  except Exception as err:  # noqa: E111
    _LOGGER.debug("Could not get coordinator statistics: %s", err)
    stats = _fallback_coordinator_statistics()

  update_interval_seconds = (  # noqa: E111
    coordinator.update_interval.total_seconds() if coordinator.update_interval else None
  )

  return cast(  # noqa: E111
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
  """  # noqa: E111
  entity_registry = er.async_get(hass)  # noqa: E111

  # Get all entities for this integration  # noqa: E114
  entities = _entity_registry_entries_for_config_entry(  # noqa: E111
    entity_registry,
    entry.entry_id,
  )

  # Group entities by platform  # noqa: E114
  entities_by_platform: dict[str, list[JSONMutableMapping]] = {}  # noqa: E111

  for entity in entities:  # noqa: E111
    platform = entity.platform
    if platform not in entities_by_platform:
      entities_by_platform[platform] = []  # noqa: E111

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
      entity_info.update(  # noqa: E111
        {
          "state": state.state,
          "available": state.state != "unavailable",
          "last_changed": state.last_changed.isoformat(),
          "last_updated": state.last_updated.isoformat(),
          "attributes_count": len(state.attributes),
        },
      )

    entities_by_platform[platform].append(
      cast(JSONMutableMapping, normalize_value(entity_info)),
    )

  return cast(  # noqa: E111
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
  """  # noqa: E111
  device_registry = dr.async_get(hass)  # noqa: E111

  # Get all devices for this integration  # noqa: E114
  devices = _device_registry_entries_for_config_entry(  # noqa: E111
    device_registry,
    entry.entry_id,
  )

  devices_info: list[JSONMutableMapping] = []  # noqa: E111
  for device in devices:  # noqa: E111
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

  return cast(  # noqa: E111
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
  """  # noqa: E111
  dogs_payload = entry.data.get(CONF_DOGS)  # noqa: E111
  dogs_source: Sequence[Any] | None = (  # noqa: E111
    dogs_payload
    if isinstance(dogs_payload, Sequence)
    and not isinstance(dogs_payload, str | bytes | bytearray)
    else None
  )
  dogs: list[DogConfigData] = (  # noqa: E111
    [cast(DogConfigData, dog) for dog in dogs_source if isinstance(dog, Mapping)]
    if dogs_source
    else []
  )

  dogs_summary: list[JSONMutableMapping] = []  # noqa: E111
  for dog in dogs:  # noqa: E111
    dog_id = dog.get(CONF_DOG_ID)
    if not isinstance(dog_id, str):
      continue  # noqa: E111
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
    dog_summary = cast(JSONMutableMapping, normalize_value(dog_summary))

    # Add coordinator data if available
    if coordinator:
      try:  # noqa: E111
        get_dog_data_method = getattr(
          coordinator,
          "get_dog_data",
          None,
        )
        dog_data = (
          get_dog_data_method(dog_id) if callable(get_dog_data_method) else None
        )
        if isinstance(dog_data, Mapping):
          dog_summary.update(  # noqa: E111
            {
              "coordinator_data_available": True,
              "last_activity": dog_data.get("last_update"),
              "status": dog_data.get("status"),
            },
          )
        else:
          dog_summary["coordinator_data_available"] = False  # noqa: E111
      except Exception as err:  # noqa: E111
        _LOGGER.debug(
          "Could not get coordinator data for dog %s: %s",
          dog_id,
          err,
        )
        dog_summary["coordinator_data_available"] = False

    dogs_summary.append(dog_summary)

  return cast(  # noqa: E111
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
  """  # noqa: E111
  if not coordinator:  # noqa: E111
    return cast(
      JSONMutableMapping,
      {
        "available": False,
        "rejection_metrics": _build_default_rejection_metrics_payload(),
      },
    )

  try:  # noqa: E111
    raw_stats = coordinator.get_update_statistics()
  except Exception as err:  # noqa: E111
    _LOGGER.debug("Could not get performance metrics: %s", err)
    return cast(
      JSONMutableMapping,
      {
        "available": False,
        "error": str(err),
        "rejection_metrics": _build_default_rejection_metrics_payload(),
      },
    )

  stats_mapping: JSONLikeMapping = (  # noqa: E111
    cast(JSONLikeMapping, raw_stats)
    if isinstance(
      raw_stats,
      Mapping,
    )
    else {}
  )
  statistics = _build_statistics_payload(stats_mapping)  # noqa: E111
  stats_payload: JSONMutableMapping = (  # noqa: E111
    cast(JSONMutableMapping, dict(stats_mapping))
    if isinstance(stats_mapping, Mapping)
    else cast(JSONMutableMapping, {})
  )
  stats_payload["update_counts"] = cast(  # noqa: E111
    JSONMapping,
    dict(statistics["update_counts"]),
  )
  stats_payload["health_indicators"] = cast(  # noqa: E111
    JSONMapping,
    dict(statistics["health_indicators"]),
  )

  update_counts = statistics["update_counts"]  # noqa: E111
  total_updates = update_counts["total"]  # noqa: E111
  failed_updates = update_counts["failed"]  # noqa: E111
  error_rate = failed_updates / total_updates if total_updates else 0.0  # noqa: E111

  rejection_payload = (  # noqa: E111
    stats_mapping.get("rejection_metrics")
    if isinstance(stats_mapping, Mapping)
    else None
  ) or statistics.get("rejection_metrics")
  if isinstance(rejection_payload, Mapping):  # noqa: E111
    rejection_metrics = derive_rejection_metrics(
      cast(JSONMapping, normalize_value(rejection_payload)),
    )
  else:  # noqa: E111
    rejection_metrics = default_rejection_metrics()

  statistics["rejection_metrics"] = rejection_metrics  # noqa: E111
  rejection_metrics_payload = cast(  # noqa: E111
    JSONMapping,
    normalize_value(dict(rejection_metrics)),
  )
  stats_payload["rejection_metrics"] = rejection_metrics_payload  # noqa: E111

  performance_metrics = statistics["performance_metrics"]  # noqa: E111
  _apply_rejection_metrics_to_performance(  # noqa: E111
    performance_metrics,
    rejection_metrics,
  )
  stats_payload["performance_metrics"] = cast(  # noqa: E111
    JSONMapping,
    dict(performance_metrics),
  )

  repairs = statistics.get("repairs")  # noqa: E111
  if repairs is not None:  # noqa: E111
    stats_payload["repairs"] = cast(JSONValue, normalize_value(repairs))

  reconfigure = statistics.get("reconfigure")  # noqa: E111
  if reconfigure is not None:  # noqa: E111
    stats_payload["reconfigure"] = cast(
      JSONValue,
      normalize_value(reconfigure),
    )

  entity_budget = statistics.get("entity_budget")  # noqa: E111
  if entity_budget is not None:  # noqa: E111
    stats_payload["entity_budget"] = cast(
      JSONValue,
      normalize_value(entity_budget),
    )

  adaptive_polling = statistics.get("adaptive_polling")  # noqa: E111
  if adaptive_polling is not None:  # noqa: E111
    stats_payload["adaptive_polling"] = cast(
      JSONValue,
      normalize_value(adaptive_polling),
    )

  resilience = statistics.get("resilience")  # noqa: E111
  if resilience is not None:  # noqa: E111
    stats_payload["resilience"] = cast(
      JSONValue,
      normalize_value(resilience),
    )

  stats_payload = cast(JSONMutableMapping, normalize_value(stats_payload))  # noqa: E111
  performance_payload = (  # noqa: E111
    cast(JSONMutableMapping, normalize_value(performance_metrics))
    if isinstance(performance_metrics, Mapping)
    else cast(JSONMutableMapping, {})
  )

  metrics_output: JSONMutableMapping = {  # noqa: E111
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

  if performance_payload:  # noqa: E111
    merge_rejection_metric_values(
      metrics_output,
      performance_payload,
      rejection_metrics_payload,
    )
  else:  # noqa: E111
    merge_rejection_metric_values(
      metrics_output,
      rejection_metrics_payload,
    )

  return cast(JSONMutableMapping, normalize_value(metrics_output))  # noqa: E111


async def _get_door_sensor_diagnostics(
  runtime_data: PawControlRuntimeData | None,
) -> JSONMutableMapping:
  """Summarise door sensor manager status and failure telemetry."""  # noqa: E111

  if runtime_data is None:  # noqa: E111
    return cast(JSONMutableMapping, {"available": False})

  manager = getattr(runtime_data, "door_sensor_manager", None)  # noqa: E111
  diagnostics: JSONMutableMapping = {  # noqa: E111
    "available": manager is not None,
    "manager_type": type(manager).__name__ if manager is not None else None,
  }

  telemetry: JSONMutableMapping = {}  # noqa: E111
  performance_stats = get_runtime_performance_stats(runtime_data)  # noqa: E111
  if isinstance(performance_stats, Mapping):  # noqa: E111
    failure_count = performance_stats.get("door_sensor_failure_count")
    if isinstance(failure_count, int | float):
      telemetry["failure_count"] = int(failure_count)  # noqa: E111

    last_failure = performance_stats.get("last_door_sensor_failure")
    if isinstance(last_failure, Mapping):
      telemetry["last_failure"] = cast(  # noqa: E111
        JSONMutableMapping,
        dict(last_failure),
      )

    failures = performance_stats.get("door_sensor_failures")
    if isinstance(failures, Sequence) and not isinstance(
      failures,
      str | bytes | bytearray,
    ):
      serialised_failures: list[JSONMutableMapping] = [  # noqa: E111
        cast(JSONMutableMapping, dict(entry))
        for entry in failures
        if isinstance(entry, Mapping)
      ]
      if serialised_failures:  # noqa: E111
        telemetry["failures"] = serialised_failures

    failure_summary = performance_stats.get("door_sensor_failure_summary")
    if isinstance(failure_summary, Mapping):
      serialised_summary = {  # noqa: E111
        str(key): cast(JSONMutableMapping, dict(value))
        for key, value in failure_summary.items()
        if isinstance(key, str) and isinstance(value, Mapping)
      }
      if serialised_summary:  # noqa: E111
        telemetry["failure_summary"] = serialised_summary

  if telemetry:  # noqa: E111
    diagnostics["telemetry"] = telemetry

  if manager is None:  # noqa: E111
    return diagnostics

  status_method = getattr(manager, "async_get_detection_status", None)  # noqa: E111
  if callable(status_method):  # noqa: E111
    try:
      diagnostics["status"] = await status_method()  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.debug("Could not gather door sensor status: %s", err)  # noqa: E111

  diag_method = getattr(manager, "get_diagnostics", None)  # noqa: E111
  if callable(diag_method):  # noqa: E111
    try:
      diagnostics["manager_diagnostics"] = diag_method()  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.debug("Could not capture door sensor diagnostics: %s", err)  # noqa: E111

  return diagnostics  # noqa: E111


async def _get_service_execution_diagnostics(
  runtime_data: PawControlRuntimeData | None,
) -> JSONMutableMapping:
  """Summarise guarded Home Assistant service execution telemetry."""  # noqa: E111

  if runtime_data is None:  # noqa: E111
    return cast(
      JSONMutableMapping,
      {
        "available": False,
        "guard_metrics": _build_service_guard_metrics_export(None),
        "rejection_metrics": _build_default_rejection_metrics_payload(),
      },
    )

  performance_stats = get_runtime_performance_stats(runtime_data)  # noqa: E111
  if not isinstance(performance_stats, Mapping):  # noqa: E111
    return cast(
      JSONMutableMapping,
      {
        "available": False,
        "guard_metrics": _build_service_guard_metrics_export(None),
        "rejection_metrics": _build_default_rejection_metrics_payload(),
      },
    )

  diagnostics: JSONMutableMapping = {"available": True}  # noqa: E111

  guard_metrics = performance_stats.get("service_guard_metrics")  # noqa: E111
  guard_payload = _build_service_guard_metrics_export(guard_metrics)  # noqa: E111
  diagnostics["guard_metrics"] = cast(JSONValue, guard_payload)  # noqa: E111

  entity_guard_payload: EntityFactoryGuardMetricsSnapshot | None = (  # noqa: E111
    resolve_entity_factory_guard_metrics(performance_stats)
    if isinstance(performance_stats, Mapping)
    else None
  )
  if entity_guard_payload:  # noqa: E111
    diagnostics["entity_factory_guard"] = cast(
      JSONMutableMapping,
      normalize_value(dict(entity_guard_payload)),
    )

  metrics_payload = default_rejection_metrics()  # noqa: E111
  rejection_metrics = performance_stats.get("rejection_metrics")  # noqa: E111
  if isinstance(rejection_metrics, Mapping):  # noqa: E111
    merge_rejection_metric_values(
      metrics_payload,
      cast(JSONMapping, rejection_metrics),
    )
  diagnostics["rejection_metrics"] = cast(  # noqa: E111
    JSONMutableMapping,
    normalize_value(metrics_payload),
  )

  service_results = performance_stats.get("service_results")  # noqa: E111
  if isinstance(service_results, Sequence) and not isinstance(  # noqa: E111
    service_results,
    str | bytes | bytearray,
  ):
    normalised_results: list[JSONMutableMapping] = [
      cast(JSONMutableMapping, normalize_value(dict(result)))
      for result in service_results
      if isinstance(result, Mapping)
    ]
    if normalised_results:
      diagnostics["service_results"] = normalised_results  # noqa: E111

  last_result = performance_stats.get("last_service_result")  # noqa: E111
  if isinstance(last_result, Mapping):  # noqa: E111
    diagnostics["last_service_result"] = cast(
      JSONMutableMapping,
      normalize_value(dict(last_result)),
    )

  service_call_telemetry = performance_stats.get("service_call_telemetry")  # noqa: E111
  telemetry_payload = _normalise_service_call_telemetry(  # noqa: E111
    service_call_telemetry,
  )
  if telemetry_payload is not None:  # noqa: E111
    diagnostics["service_call_telemetry"] = telemetry_payload

  return cast(JSONMutableMapping, normalize_value(diagnostics))  # noqa: E111


def _get_bool_coercion_diagnostics(
  runtime_data: PawControlRuntimeData | None,
) -> BoolCoercionDiagnosticsPayload:
  """Expose recent bool coercion telemetry captured during normalisation."""  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  summary = update_runtime_bool_coercion_summary(runtime_data)  # noqa: E111
  recorded = bool(summary["recorded"])  # noqa: E111
  payload: BoolCoercionDiagnosticsPayload = {  # noqa: E111
    "recorded": recorded,
    "summary": summary,
  }

  if recorded and metrics:  # noqa: E111
    payload["metrics"] = metrics

  return payload  # noqa: E111


def _normalise_service_guard_metrics(
  payload: Any,
) -> ServiceGuardMetricsSnapshot | None:
  """Return a JSON-safe snapshot of aggregated guard metrics when available."""  # noqa: E111

  if not isinstance(payload, Mapping):  # noqa: E111
    return None

  executed = _coerce_int(payload.get("executed"))  # noqa: E111
  skipped = _coerce_int(payload.get("skipped"))  # noqa: E111

  reasons_payload: dict[str, int] | None = None  # noqa: E111
  reasons = payload.get("reasons")  # noqa: E111
  if isinstance(reasons, Mapping):  # noqa: E111
    serialised_reasons: dict[str, int] = {}
    for reason, count in reasons.items():
      coerced = _coerce_int(count)  # noqa: E111
      if coerced:  # noqa: E111
        serialised_reasons[str(reason)] = coerced
    if serialised_reasons:
      reasons_payload = serialised_reasons  # noqa: E111

  last_results_payload: ServiceGuardResultHistory | None = None  # noqa: E111
  history_payload = normalise_guard_history(payload.get("last_results"))  # noqa: E111
  if history_payload:  # noqa: E111
    last_results_payload = history_payload

  if (  # noqa: E111
    executed is None
    and skipped is None
    and reasons_payload is None
    and last_results_payload is None
  ):
    return None

  guard_metrics: ServiceGuardMetricsSnapshot = {}  # noqa: E111
  if executed is not None:  # noqa: E111
    guard_metrics["executed"] = executed
  if skipped is not None:  # noqa: E111
    guard_metrics["skipped"] = skipped
  if reasons_payload is not None:  # noqa: E111
    guard_metrics["reasons"] = reasons_payload
  if last_results_payload is not None:  # noqa: E111
    guard_metrics["last_results"] = last_results_payload

  return guard_metrics  # noqa: E111


def _build_service_guard_metrics_export(
  payload: Any,
) -> ServiceGuardMetricsSnapshot:
  """Return a complete service guard metrics export payload.

  The export schema must always include the guard metrics keys so downstream
  dashboards can rely on a consistent payload (mirroring the rejection metrics
  defaults).
  """  # noqa: E111

  default_payload = ServiceGuardSnapshot.zero_metrics()  # noqa: E111
  normalised = _normalise_service_guard_metrics(payload)  # noqa: E111
  if normalised is None:  # noqa: E111
    return default_payload

  merged = ServiceGuardSnapshot.zero_metrics()  # noqa: E111
  merged.update(normalised)  # noqa: E111
  return merged  # noqa: E111


def _normalise_service_call_telemetry(payload: Any) -> JSONMutableMapping | None:
  """Return a JSON-safe snapshot of service call telemetry metrics."""  # noqa: E111

  if not isinstance(payload, Mapping):  # noqa: E111
    return None

  telemetry_payload = cast(  # noqa: E111
    JSONMutableMapping,
    normalize_value(dict(payload)),
  )

  per_service = payload.get("per_service")  # noqa: E111
  if isinstance(per_service, Mapping):  # noqa: E111
    telemetry_payload["per_service"] = {
      str(service): cast(JSONMutableMapping, normalize_value(dict(entry)))
      for service, entry in per_service.items()
      if isinstance(entry, Mapping)
    }

  return telemetry_payload  # noqa: E111


def _coerce_int(value: Any) -> int | None:
  """Convert ``value`` into an integer when possible."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return int(value)

  if isinstance(value, int):  # noqa: E111
    return value

  if isinstance(value, float):  # noqa: E111
    return int(value)

  if isinstance(value, str):  # noqa: E111
    try:
      return int(value.strip())  # noqa: E111
    except ValueError:
      return None  # noqa: E111

  return None  # noqa: E111


async def _get_data_statistics(
  runtime_data: PawControlRuntimeData | None,
  cache_snapshots: CacheDiagnosticsMap | None,
) -> DataStatisticsPayload:
  """Get data storage statistics.

  Args:
      runtime_data: Runtime data

  Returns:
      Data statistics
  """  # noqa: E111
  if runtime_data is None:  # noqa: E111
    return {"data_manager_available": False, "metrics": {}}

  data_manager = _resolve_data_manager(runtime_data)  # noqa: E111
  if data_manager is None:  # noqa: E111
    return {"data_manager_available": False, "metrics": {}}

  metrics_payload: JSONLikeMapping | None = None  # noqa: E111
  metrics_method = getattr(data_manager, "get_metrics", None)  # noqa: E111
  if callable(metrics_method):  # noqa: E111
    try:
      metrics_payload = metrics_method()  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.debug("Failed to gather data manager metrics: %s", err)  # noqa: E111

  if isinstance(metrics_payload, Mapping):  # noqa: E111
    metrics: JSONMutableMapping = {}
    for key, value in metrics_payload.items():
      metrics[str(key)] = cast(JSONValue, normalize_value(value))  # noqa: E111
  else:  # noqa: E111
    metrics = cast(JSONMutableMapping, {})

  if cache_snapshots is None:  # noqa: E111
    cache_payload = _collect_cache_diagnostics(runtime_data)
  else:  # noqa: E111
    cache_payload = cache_snapshots

  if cache_payload is not None:  # noqa: E111
    metrics["cache_diagnostics"] = _serialise_cache_diagnostics_payload(
      cache_payload,
    )

  dogs_payload = getattr(runtime_data, "dogs", None)  # noqa: E111
  if isinstance(dogs_payload, Sequence) and not isinstance(  # noqa: E111
    dogs_payload,
    str | bytes | bytearray,
  ):
    metrics.setdefault("dogs", len(dogs_payload))

  return {  # noqa: E111
    "data_manager_available": True,
    "metrics": metrics,
  }


async def _get_recent_errors(entry_id: str) -> list[RecentErrorEntry]:
  """Get recent error logs for this integration.

  Args:
      entry_id: Configuration entry ID

  Returns:
      List of recent error information
  """  # noqa: E111
  # In a real implementation, this would collect actual error logs  # noqa: E114
  # from the Home Assistant logging system  # noqa: E114
  return [  # noqa: E111
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
  """  # noqa: E111

  return {  # noqa: E111
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
  """  # noqa: E111
  # Check which platforms have been loaded by checking entity registry  # noqa: E114
  entity_registry = er.async_get(hass)  # noqa: E111
  entities = _entity_registry_entries_for_config_entry(  # noqa: E111
    entity_registry,
    entry.entry_id,
  )

  # Get unique platforms  # noqa: E114
  return list({entity.platform for entity in entities})  # noqa: E111


async def _get_registered_services(hass: HomeAssistant) -> list[str]:
  """Get list of registered services for this domain.

  Args:
      hass: Home Assistant instance

  Returns:
      List of registered service names
  """  # noqa: E111
  domain_services = hass.services.async_services().get(DOMAIN, {})  # noqa: E111

  return list(domain_services.keys())  # noqa: E111


def _calculate_module_usage(dogs: Sequence[DogConfigData]) -> ModuleUsageBreakdown:
  """Calculate module usage statistics across all dogs.

  Args:
      dogs: List of dog configurations

  Returns:
      Module usage statistics
  """  # noqa: E111
  module_counts: dict[str, int] = {  # noqa: E111
    MODULE_FEEDING: 0,
    MODULE_WALK: 0,
    MODULE_GPS: 0,
    MODULE_HEALTH: 0,
    MODULE_NOTIFICATIONS: 0,
  }

  dogs_sequence: Sequence[DogConfigData] = (  # noqa: E111
    dogs
    if isinstance(dogs, Sequence) and not isinstance(dogs, str | bytes | bytearray)
    else ()
  )

  valid_dogs: list[DogConfigData] = [  # noqa: E111
    cast(DogConfigData, dog) for dog in dogs_sequence if isinstance(dog, Mapping)
  ]

  total_dogs = len(valid_dogs)  # noqa: E111

  for dog in valid_dogs:  # noqa: E111
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
      if modules.get(module, False):  # noqa: E111
        module_counts[module] += 1

  # Calculate percentages  # noqa: E114
  module_percentages: dict[str, float] = {}  # noqa: E111
  for module, count in module_counts.items():  # noqa: E111
    percentage = (count / total_dogs * 100) if total_dogs > 0 else 0
    module_percentages[f"{module}_percentage"] = round(percentage, 1)

  def _module_score(key: str) -> int:  # noqa: E111
    return module_counts[key]

  return {  # noqa: E111
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
  """Recursively redact sensitive data from diagnostic information."""  # noqa: E111

  return redact_sensitive_data(data, patterns=_REDACTED_KEY_PATTERNS)  # noqa: E111
