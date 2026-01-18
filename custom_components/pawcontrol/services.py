"""Home Assistant services for PawControl integration.

Comprehensive service definitions for all PawControl functionality including
feeding management, walk tracking, health monitoring, GPS tracking, medication
logging, visitor mode, and notifications.

Quality Scale: Platinum target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import (
  Awaitable,
  Callable,
  Iterable,
  Mapping,
  MutableMapping,
  Sequence,
)
from contextlib import suppress
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Literal, TypeVar, cast

import voluptuous as vol
from homeassistant import config_entries as ha_config_entries
from homeassistant.core import Context, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from . import compat
from .compat import (
  ConfigEntry,
  ConfigEntryChange,
  ConfigEntryState,
  bind_exception_alias,
)
from .const import (
  CONF_RESET_TIME,
  DEFAULT_RESET_TIME,
  DOMAIN,
  EVENT_FEEDING_COMPLIANCE_CHECKED,
  MAX_GEOFENCE_RADIUS,
  MIN_GEOFENCE_RADIUS,
  SERVICE_ACTIVATE_DIABETIC_FEEDING_MODE,
  SERVICE_ACTIVATE_EMERGENCY_FEEDING_MODE,
  SERVICE_ADD_HEALTH_SNACK,
  SERVICE_ADJUST_CALORIES_FOR_ACTIVITY,
  SERVICE_ADJUST_DAILY_PORTIONS,
  SERVICE_CHECK_FEEDING_COMPLIANCE,
  SERVICE_DAILY_RESET,
  SERVICE_FEED_DOG,
  SERVICE_FEED_WITH_MEDICATION,
  SERVICE_GENERATE_WEEKLY_HEALTH_REPORT,
  SERVICE_GET_WEATHER_ALERTS,
  SERVICE_GET_WEATHER_RECOMMENDATIONS,
  SERVICE_GPS_END_WALK,
  SERVICE_GPS_EXPORT_ROUTE,
  SERVICE_GPS_POST_LOCATION,
  SERVICE_GPS_START_WALK,
  SERVICE_LOG_HEALTH,
  SERVICE_LOG_MEDICATION,
  SERVICE_LOG_POOP,
  SERVICE_RECALCULATE_HEALTH_PORTIONS,
  SERVICE_START_DIET_TRANSITION,
  SERVICE_START_GROOMING,
  SERVICE_TOGGLE_VISITOR_MODE,
  SERVICE_UPDATE_WEATHER,
)

SIGNAL_CONFIG_ENTRY_CHANGED = getattr(
  ha_config_entries,
  "SIGNAL_CONFIG_ENTRY_CHANGED",
  "config_entry_changed",
)
from .coordinator import PawControlCoordinator
from .coordinator_support import ensure_cache_repair_aggregate
from .coordinator_tasks import default_rejection_metrics, merge_rejection_metric_values
from .feeding_manager import FeedingComplianceCompleted
from .feeding_translations import build_feeding_compliance_summary
from .grooming_translations import (
  translated_grooming_template,
)
from .notifications import NotificationChannel, NotificationPriority, NotificationType
from .performance import (
  capture_cache_diagnostics,
  performance_tracker,
  record_maintenance_result,
)
from .repairs import async_publish_feeding_compliance_issue
from .runtime_data import get_runtime_data
from .service_guard import (
  ServiceGuardMetricsSnapshot,
  ServiceGuardResult,
  ServiceGuardSnapshot,
  ServiceGuardSummary,
)
from .telemetry import (
  ensure_runtime_performance_stats,
  get_runtime_performance_stats,
  get_runtime_resilience_summary,
  update_runtime_reconfigure_summary,
)
from .types import (
  CacheDiagnosticsCapture,
  CacheDiagnosticsMap,
  CacheDiagnosticsSnapshot,
  CoordinatorRejectionMetrics,
  CoordinatorResilienceSummary,
  CoordinatorRuntimeManagers,
  DogConfigData,
  FeedingComplianceEventPayload,
  FeedingComplianceLocalizedSummary,
  GPSTrackingConfigInput,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  PawControlRuntimeData,
  ServiceCallTelemetry,
  ServiceCallTelemetryEntry,
  ServiceContextMetadata,
  ServiceData,
  ServiceDetailsPayload,
  ServiceExecutionDiagnostics,
  ServiceExecutionResult,
)
from .utils import async_capture_service_guard_results, async_fire_event
from .walk_manager import WeatherCondition

_LOGGER = logging.getLogger(__name__)

compat.ensure_homeassistant_exception_symbols()
HomeAssistantError: type[Exception] = cast(
  type[Exception],
  compat.HomeAssistantError,
)
ServiceValidationError: type[Exception] = cast(
  type[Exception],
  compat.ServiceValidationError,
)
bind_exception_alias("HomeAssistantError", combine_with_current=True)
bind_exception_alias("ServiceValidationError")

_FALLBACK_EXCEPTION_MODULE = "custom_components.pawcontrol.compat"
_CACHED_SERVICE_VALIDATION_ERROR: type[Exception] | None
_SERVICE_VALIDATION_ALIAS_CACHE: dict[
  tuple[type[Exception], type[Exception]],
  type[Exception],
] = {}
if (
  isinstance(ServiceValidationError, type)
  and issubclass(ServiceValidationError, compat.HomeAssistantError)
  and ServiceValidationError.__module__ != _FALLBACK_EXCEPTION_MODULE
):
  _CACHED_SERVICE_VALIDATION_ERROR = ServiceValidationError
else:
  _CACHED_SERVICE_VALIDATION_ERROR = None


def __getattr__(name: str) -> object:
  """Expose compat-managed exception aliases at module scope."""

  if name == "HomeAssistantError":
    compat.ensure_homeassistant_exception_symbols()
    return HomeAssistantError
  raise AttributeError(name)


def _service_validation_error(message: str) -> Exception:
  """Return a ``ServiceValidationError`` that mirrors Home Assistant's class."""

  normalised_message = message.strip()
  if not normalised_message:
    raise AssertionError(
      "_service_validation_error requires a non-empty message",
    )

  message = normalised_message

  compat.ensure_homeassistant_exception_symbols()

  global _CACHED_SERVICE_VALIDATION_ERROR
  candidate: type[Exception] | None = None
  if isinstance(ServiceValidationError, type) and issubclass(
    ServiceValidationError,
    compat.HomeAssistantError,
  ):
    if ServiceValidationError.__module__ != _FALLBACK_EXCEPTION_MODULE:
      _CACHED_SERVICE_VALIDATION_ERROR = ServiceValidationError
      candidate = ServiceValidationError
    elif _CACHED_SERVICE_VALIDATION_ERROR is not None:
      candidate = _CACHED_SERVICE_VALIDATION_ERROR

  override = getattr(compat, "ServiceValidationError", None)
  if (
    isinstance(override, type)
    and issubclass(override, Exception)
    and (override.__module__ != _FALLBACK_EXCEPTION_MODULE or candidate is None)
  ):
    candidate = override
    if override.__module__ != _FALLBACK_EXCEPTION_MODULE and issubclass(
      override,
      compat.HomeAssistantError,
    ):
      _CACHED_SERVICE_VALIDATION_ERROR = override

  if candidate is None:
    cached = _CACHED_SERVICE_VALIDATION_ERROR
    candidate = cached if cached is not None else compat.ServiceValidationError

  candidate = _ensure_service_validation_alias(candidate)
  return candidate(message)


def _ensure_service_validation_alias(
  candidate: type[Exception],
) -> type[Exception]:
  """Ensure ``candidate`` inherits from :class:`HomeAssistantError`."""

  if issubclass(candidate, HomeAssistantError):
    return candidate

  cache_key = (candidate, HomeAssistantError)
  alias = _SERVICE_VALIDATION_ALIAS_CACHE.get(cache_key)
  if alias is not None:
    return alias

  alias = type(
    "PawControlServiceValidationErrorAlias",
    (candidate, HomeAssistantError),
    {"__module__": candidate.__module__},
  )
  _SERVICE_VALIDATION_ALIAS_CACHE[cache_key] = alias
  return alias


# PLATINUM: Enhanced validation ranges for service inputs
VALID_WEIGHT_RANGE = (0.5, 100.0)  # kg
VALID_TEMPERATURE_RANGE = (35.0, 42.0)  # °C
VALID_PORTION_RANGE = (10.0, 5000.0)  # grams
VALID_DURATION_RANGE = (1, 480)  # minutes
VALID_ACCURACY_RANGE = (1.0, 1000.0)  # meters
VALID_LATITUDE_RANGE = (-90.0, 90.0)  # degrees
VALID_LONGITUDE_RANGE = (-180.0, 180.0)  # degrees

# Service names - maintain backward compatibility
SERVICE_ADD_FEEDING = "add_feeding"
SERVICE_START_WALK = "start_walk"
SERVICE_END_WALK = "end_walk"
SERVICE_ADD_GPS_POINT = "add_gps_point"
SERVICE_UPDATE_HEALTH = "update_health"
SERVICE_SEND_NOTIFICATION = "send_notification"
SERVICE_ACKNOWLEDGE_NOTIFICATION = "acknowledge_notification"
SERVICE_CALCULATE_PORTION = "calculate_portion"
SERVICE_EXPORT_DATA = "export_data"
SERVICE_ANALYZE_PATTERNS = "analyze_patterns"
SERVICE_GENERATE_REPORT = "generate_report"
# NEW: Missing service from info.md
SERVICE_SETUP_AUTOMATIC_GPS = "setup_automatic_gps"

# NEW: Garden tracking services
SERVICE_START_GARDEN = "start_garden_session"
SERVICE_END_GARDEN = "end_garden_session"
SERVICE_ADD_GARDEN_ACTIVITY = "add_garden_activity"
SERVICE_CONFIRM_POOP = "confirm_garden_poop"

_ManagerT = TypeVar("_ManagerT")


class _CoordinatorResolver:
  """Resolve and cache the active PawControl coordinator instance."""

  __slots__ = ("_cached_coordinator", "_cached_entry_id", "_hass")

  def __init__(self, hass: HomeAssistant) -> None:
    """Create a resolver tied to the provided Home Assistant instance."""

    self._hass = hass
    self._cached_coordinator: PawControlCoordinator | None = None
    self._cached_entry_id: str | None = None

  def resolve(self) -> PawControlCoordinator:
    """Return the active coordinator, consulting cache when valid."""

    coordinator = self._get_cached_coordinator()
    if coordinator is not None:
      return coordinator

    coordinator = self._resolve_from_sources()
    self._cache_coordinator(coordinator)
    return coordinator

  def invalidate(self, *, entry_id: str | None = None) -> None:
    """Drop any cached coordinator when it is no longer valid."""

    if self._cached_coordinator is None:
      return

    if (
      entry_id is not None
      and self._cached_entry_id is not None
      and entry_id != self._cached_entry_id
    ):
      # An unrelated config entry changed state; keep the cached coordinator.
      return

    self._cached_coordinator = None
    self._cached_entry_id = None

  def _cache_coordinator(self, coordinator: PawControlCoordinator) -> None:
    config_entry = getattr(coordinator, "config_entry", None)
    self._cached_coordinator = coordinator
    self._cached_entry_id = getattr(config_entry, "entry_id", None)

  def _get_cached_coordinator(self) -> PawControlCoordinator | None:
    coordinator = self._cached_coordinator
    if coordinator is None:
      return None

    if getattr(coordinator, "hass", None) is not self._hass:
      # The coordinator was created for a different Home Assistant instance.
      self.invalidate()
      return None

    config_entry = getattr(coordinator, "config_entry", None)
    if config_entry is not None and config_entry.state is not ConfigEntryState.LOADED:
      # The entry is not ready yet; wait for a fresh lookup.
      self.invalidate(entry_id=getattr(config_entry, "entry_id", None))
      return None

    return coordinator

  def _resolve_from_sources(self) -> PawControlCoordinator:
    """Locate the active coordinator from config entries or stored data."""

    entries = list(self._hass.config_entries.async_entries(DOMAIN))

    for entry in entries:
      if entry.state is not ConfigEntryState.LOADED:
        continue

      runtime_data = get_runtime_data(self._hass, entry)
      if runtime_data and getattr(runtime_data, "coordinator", None):
        return cast(PawControlCoordinator, runtime_data.coordinator)

    if any(entry.state is ConfigEntryState.LOADED for entry in entries):
      raise _service_validation_error(
        "PawControl runtime data is not ready yet. Reload the integration.",
      )

    if entries:
      raise _service_validation_error(
        "PawControl is still initializing. Try again once setup has finished.",
      )

    raise _service_validation_error(
      "PawControl is not set up. Add the integration before calling its services.",
    )


@callback
def _coordinator_resolver(hass: HomeAssistant) -> _CoordinatorResolver:
  """Return a coordinator resolver stored within Home Assistant data."""

  domain_data = hass.data.setdefault(DOMAIN, {})
  resolver = domain_data.get("_service_coordinator_resolver")
  if isinstance(resolver, _CoordinatorResolver):
    return resolver

  resolver = _CoordinatorResolver(hass)
  domain_data["_service_coordinator_resolver"] = resolver
  return resolver


def _capture_cache_diagnostics(runtime_data: Any) -> CacheDiagnosticsCapture | None:
  """Return the most recent cache diagnostics snapshot if available."""

  capture = capture_cache_diagnostics(runtime_data)
  if capture is None:
    return None

  snapshots_raw = capture.get("snapshots")
  normalised_snapshots: CacheDiagnosticsMap = {}
  if isinstance(snapshots_raw, Mapping):
    for name, payload in snapshots_raw.items():
      if not isinstance(name, str):
        continue
      if isinstance(payload, CacheDiagnosticsSnapshot):
        normalised_snapshots[name] = payload
      elif isinstance(payload, Mapping):
        normalised_snapshots[name] = CacheDiagnosticsSnapshot.from_mapping(
          payload,
        )
      else:
        normalised_snapshots[name] = CacheDiagnosticsSnapshot(
          error=str(payload),
        )

  result: CacheDiagnosticsCapture = {"snapshots": normalised_snapshots}

  summary = capture.get("repair_summary")
  resolved_summary = ensure_cache_repair_aggregate(summary)
  if resolved_summary is not None:
    result["repair_summary"] = resolved_summary

  return result


def _get_runtime_data_for_coordinator(
  coordinator: PawControlCoordinator,
) -> Any | None:
  """Return runtime data associated with ``coordinator`` if available."""

  try:
    return get_runtime_data(coordinator.hass, coordinator.config_entry)
  except Exception:  # pragma: no cover - defensive guard
    return None


def _coerce_service_details_value(value: Any) -> JSONValue:
  """Return a JSON-compatible representation for service detail values."""

  if value is None or isinstance(value, bool | int | float | str):
    return value

  if isinstance(value, Mapping):
    return {
      str(key): _coerce_service_details_value(item) for key, item in value.items()
    }

  if isinstance(value, list | tuple | set):
    return [_coerce_service_details_value(item) for item in value]

  return str(value)


def _normalise_service_details(payload: Any) -> ServiceDetailsPayload | None:
  """Convert ``payload`` into a serialisable mapping for service telemetry."""

  if payload is None:
    return None

  if isinstance(payload, Mapping):
    return {
      str(key): _coerce_service_details_value(value) for key, value in payload.items()
    }

  if isinstance(payload, list | tuple | set):
    return {"items": _coerce_service_details_value(list(payload))}

  return {"value": _coerce_service_details_value(payload)}


def _record_service_result(
  runtime_data: Any,
  *,
  service: str,
  status: Literal["success", "error"],
  dog_id: str | None = None,
  message: str | None = None,
  diagnostics: CacheDiagnosticsCapture | None = None,
  metadata: Mapping[str, JSONValue] | None = None,
  details: ServiceDetailsPayload | None = None,
  guard: ServiceGuardResult | Sequence[ServiceGuardResult] | None = None,
) -> None:
  """Append a service execution result to runtime performance statistics."""

  if runtime_data is None:
    return

  performance_stats = get_runtime_performance_stats(runtime_data)
  if performance_stats is None:
    return

  result: ServiceExecutionResult = {"service": service, "status": status}

  resilience_summary = (
    get_runtime_resilience_summary(runtime_data) if runtime_data is not None else None
  )
  resilience_payload: CoordinatorResilienceSummary | None = None
  if isinstance(resilience_summary, Mapping):
    resilience_payload = cast(
      CoordinatorResilienceSummary,
      dict(resilience_summary),
    )

  rejection_snapshot: CoordinatorRejectionMetrics | None = None
  if resilience_payload is not None:
    rejection_snapshot = default_rejection_metrics()
    merge_rejection_metric_values(rejection_snapshot, resilience_payload)

  if dog_id:
    result["dog_id"] = dog_id

  if message:
    result["message"] = message

  diagnostics_payload: ServiceExecutionDiagnostics | None = None
  if diagnostics is not None:
    diagnostics_payload = {"cache": diagnostics}

  if metadata is not None:
    metadata_payload: ServiceDetailsPayload = {
      str(key): _coerce_service_details_value(value) for key, value in metadata.items()
    }
    if diagnostics_payload is None:
      diagnostics_payload = {"metadata": metadata_payload}
    else:
      diagnostics_payload["metadata"] = metadata_payload

  if resilience_payload is not None:
    if diagnostics_payload is None:
      diagnostics_payload = {"resilience_summary": resilience_payload}
    else:
      diagnostics_payload.setdefault(
        "resilience_summary",
        resilience_payload,
      )

  if rejection_snapshot is not None:
    if diagnostics_payload is None:
      diagnostics_payload = {"rejection_metrics": rejection_snapshot}
    else:
      diagnostics_payload.setdefault(
        "rejection_metrics",
        rejection_snapshot,
      )

  if diagnostics_payload:
    result["diagnostics"] = diagnostics_payload

  details_payload: ServiceDetailsPayload | None = None
  if details:
    details_payload = dict(details)

  guard_results: tuple[ServiceGuardResult, ...] = ()
  if guard is not None:
    if isinstance(guard, ServiceGuardResult):
      guard_results = (guard,)
    else:
      guard_results = tuple(
        entry for entry in guard if isinstance(entry, ServiceGuardResult)
      )

  guard_summary: ServiceGuardSummary | None = None
  if guard_results:
    guard_snapshot = ServiceGuardSnapshot.from_sequence(guard_results)
    guard_summary = guard_snapshot.to_summary()

    if details_payload is None:
      details_payload = {}
    details_payload.setdefault(
      "guard",
      _coerce_service_details_value(guard_summary),
    )

    if diagnostics_payload is None:
      diagnostics_payload = {}
    diagnostics_payload.setdefault("guard", guard_summary)

    guard_metrics = cast(
      ServiceGuardMetricsSnapshot,
      performance_stats.setdefault(
        "service_guard_metrics",
        ServiceGuardSnapshot.zero_metrics(),
      ),
    )
    guard_metrics["executed"] = (
      int(guard_metrics.get("executed", 0) or 0) + guard_snapshot.executed
    )
    guard_metrics["skipped"] = (
      int(guard_metrics.get("skipped", 0) or 0) + guard_snapshot.skipped
    )
    reason_bucket = guard_metrics.setdefault("reasons", {})
    for reason_key, count in guard_snapshot.reasons.items():
      reason_bucket[reason_key] = int(reason_bucket.get(reason_key, 0) or 0) + count
    guard_metrics["last_results"] = guard_snapshot.history()

  if rejection_snapshot is not None:
    stored_metrics = cast(
      CoordinatorRejectionMetrics,
      performance_stats.setdefault(
        "rejection_metrics",
        default_rejection_metrics(),
      ),
    )
    merge_rejection_metric_values(stored_metrics, rejection_snapshot)

    rejected = rejection_snapshot.get("rejected_call_count", 0) or 0
    breaker_count = (
      rejection_snapshot.get(
        "rejection_breaker_count",
        0,
      )
      or 0
    )
    if rejected > 0 or breaker_count > 0:
      filtered_rejection = {
        key: value
        for key, value in rejection_snapshot.items()
        if value not in (None, [], {}, 0)
      }
      if filtered_rejection:
        if details_payload is None:
          details_payload = {}
        details_payload.setdefault(
          "resilience",
          _coerce_service_details_value(filtered_rejection),
        )

  if details_payload:
    result["details"] = details_payload

  if guard_summary is not None:
    result["guard"] = guard_summary

  existing = performance_stats.setdefault("service_results", [])
  if isinstance(existing, list):
    existing.append(result)
  else:  # pragma: no cover - legacy guard
    performance_stats["service_results"] = [result]

  performance_stats["last_service_result"] = result


def _normalise_context_identifier(value: Any) -> str | None:
  """Return a normalised context identifier string or ``None``."""

  if value is None:
    return None

  if isinstance(value, str):
    trimmed = value.strip()
    return trimmed or None

  try:
    text = str(value)
  except Exception:  # pragma: no cover - defensive guard
    return None

  trimmed = text.strip()
  return trimmed or None


def _merge_service_context_metadata(
  target: MutableMapping[str, JSONValue],
  metadata: ServiceContextMetadata | None,
  *,
  include_none: bool = False,
) -> None:
  """Merge captured service context identifiers into ``target``."""

  if not metadata:
    return

  for key, value in metadata.items():
    if not isinstance(key, str):
      continue

    if value is None and not include_none:
      continue

    target[key] = _coerce_service_details_value(value)


def _extract_service_context(
  call: ServiceCall,
) -> tuple[Context | None, ServiceContextMetadata | None]:
  """Normalise service call context metadata for telemetry surfaces."""

  context_like: Any = getattr(call, "context", None)
  if context_like is None:
    return None, None

  mapping_source: JSONLikeMapping | None = None
  if isinstance(context_like, Mapping):
    mapping_source = cast(JSONLikeMapping, context_like)

  metadata: ServiceContextMetadata = {}

  def _capture(*attributes: str) -> tuple[bool, str | None]:
    present = False
    captured: str | None = None

    for attribute in attributes:
      if mapping_source is not None and attribute in mapping_source:
        present = True
        raw_value = mapping_source.get(attribute)
        normalised = _normalise_context_identifier(raw_value)
        if normalised is not None:
          return True, normalised
        if raw_value is None:
          captured = None
        continue

      if hasattr(context_like, attribute):
        present = True
        try:
          raw_value = getattr(context_like, attribute)
        except Exception:  # pragma: no cover - defensive guard
          continue

        normalised = _normalise_context_identifier(raw_value)
        if normalised is not None:
          return True, normalised
        if raw_value is None:
          captured = None

    return present, captured

  id_present, context_id = _capture("id", "context_id")
  if id_present:
    metadata["context_id"] = context_id

  parent_present, parent_id = _capture("parent_id")
  if parent_present:
    metadata["parent_id"] = parent_id

  user_present, user_id = _capture("user_id")
  if user_present:
    metadata["user_id"] = user_id

  context: Context | None
  if isinstance(context_like, Context):
    context = context_like
  elif (
    getattr(
      getattr(context_like, "__class__", None),
      "__name__",
      None,
    )
    == "Context"
  ):
    context = cast(Context, context_like)
  else:
    has_identifier = any(value is not None for value in metadata.values())
    if has_identifier:
      context = Context(
        context_id=metadata.get("context_id"),
        parent_id=metadata.get("parent_id"),
        user_id=metadata.get("user_id"),
      )
    else:
      context = None

  if not metadata:
    return context, None

  return context, metadata


# Service schemas
SERVICE_ADD_FEEDING_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("amount"): vol.Coerce(float),
    vol.Optional("meal_type"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("feeder"): cv.string,
    vol.Optional("scheduled", default=False): cv.boolean,
    vol.Optional("with_medication", default=False): cv.boolean,
    vol.Optional("medication_data"): vol.Schema(
      {
        vol.Optional("name"): cv.string,
        vol.Optional("dose"): cv.string,
        vol.Optional("time"): cv.string,
      },
    ),
  },
)

# Alternative feed_dog schema for backward compatibility
SERVICE_FEED_DOG_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("amount"): vol.Coerce(float),
    vol.Optional("meal_type"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("feeder"): cv.string,
  },
)

SERVICE_START_WALK_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("walker"): cv.string,
    vol.Optional("weather"): vol.In(
      ["sunny", "cloudy", "rainy", "snowy", "windy", "hot", "cold"],
    ),
    vol.Optional("leash_used", default=True): cv.boolean,
  },
)

SERVICE_END_WALK_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("dog_weight_kg"): vol.Coerce(float),
  },
)

SERVICE_ADD_GPS_POINT_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("latitude"): vol.Coerce(float),
    vol.Required("longitude"): vol.Coerce(float),
    vol.Optional("altitude"): vol.Coerce(float),
    vol.Optional("accuracy"): vol.Coerce(float),
  },
)

SERVICE_UPDATE_HEALTH_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("weight"): vol.Coerce(float),
    vol.Optional("ideal_weight"): vol.Coerce(float),
    vol.Optional("age_months"): vol.Coerce(int),
    vol.Optional("activity_level"): vol.In(
      ["very_low", "low", "moderate", "high", "very_high"],
    ),
    vol.Optional("body_condition_score"): vol.Range(min=1, max=9),
    vol.Optional("health_conditions"): [cv.string],
    vol.Optional("weight_goal"): vol.In(["maintain", "lose", "gain"]),
  },
)

SERVICE_LOG_HEALTH_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("weight"): vol.Coerce(float),
    vol.Optional("temperature"): vol.Coerce(float),
    vol.Optional("activity_level"): vol.In(
      ["very_low", "low", "moderate", "high", "very_high"],
    ),
    vol.Optional("mood"): vol.In(
      ["happy", "neutral", "sad", "angry", "anxious", "tired"],
    ),
    vol.Optional("symptoms"): [cv.string],
    vol.Optional("notes"): cv.string,
    vol.Optional("vet_visit", default=False): cv.boolean,
  },
)

SERVICE_LOG_MEDICATION_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("medication_name"): cv.string,
    vol.Required("dose"): cv.string,
    vol.Optional("administration_time"): cv.datetime,
    vol.Optional("with_meal", default=False): cv.boolean,
    vol.Optional("notes"): cv.string,
    vol.Optional("side_effects"): [cv.string],
  },
)

SERVICE_TOGGLE_VISITOR_MODE_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("visitor_name"): cv.string,
    vol.Optional("duration_hours"): vol.Coerce(int),
  },
)

SERVICE_GPS_START_WALK_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("walker"): cv.string,
    vol.Optional("track_route", default=True): cv.boolean,
    vol.Optional("safety_alerts", default=True): cv.boolean,
  },
)

SERVICE_GPS_END_WALK_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("save_route", default=True): cv.boolean,
    vol.Optional("notes"): cv.string,
  },
)

SERVICE_GPS_POST_LOCATION_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("latitude"): vol.Coerce(float),
    vol.Required("longitude"): vol.Coerce(float),
    vol.Optional("altitude"): vol.Coerce(float),
    vol.Optional("accuracy"): vol.Coerce(float),
    vol.Optional("timestamp"): cv.datetime,
  },
)

SERVICE_GPS_EXPORT_ROUTE_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("format", default="gpx"): vol.In(["gpx", "json", "csv"]),
    vol.Optional("last_n_walks", default=1): vol.Coerce(int),
  },
)

# NEW: Setup automatic GPS service schema - mentioned in info.md but missing
SERVICE_SETUP_AUTOMATIC_GPS_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("auto_start_walk", default=True): cv.boolean,
    vol.Optional("safe_zone_radius", default=50): vol.Range(
      min=MIN_GEOFENCE_RADIUS,
      max=MAX_GEOFENCE_RADIUS,
    ),
    vol.Optional("track_route", default=True): cv.boolean,
    vol.Optional("safety_alerts", default=True): cv.boolean,
    vol.Optional("geofence_notifications", default=True): cv.boolean,
    vol.Optional("auto_detect_home", default=True): cv.boolean,
    vol.Optional("gps_accuracy_threshold", default=50): vol.Range(min=5, max=500),
    vol.Optional("update_interval_seconds", default=60): vol.Range(min=30, max=600),
  },
)

SERVICE_SEND_NOTIFICATION_SCHEMA = vol.Schema(
  {
    vol.Required("title"): cv.string,
    vol.Required("message"): cv.string,
    vol.Optional("dog_id"): cv.string,
    vol.Optional("notification_type"): vol.In(
      [
        "feeding_reminder",
        "feeding_overdue",
        "walk_reminder",
        "walk_overdue",
        "health_alert",
        "medication_reminder",
        "veterinary_appointment",
        "weight_check",
        "system_info",
        "system_warning",
        "system_error",
      ],
    ),
    vol.Optional("priority"): vol.In(["low", "normal", "high", "urgent"]),
    vol.Optional("channels"): [
      vol.In(
        [
          "persistent",
          "mobile",
          "email",
          "sms",
          "webhook",
          "tts",
          "media_player",
          "slack",
          "discord",
        ],
      ),
    ],
    vol.Optional("expires_in_hours"): vol.Coerce(int),
  },
)

SERVICE_ACKNOWLEDGE_NOTIFICATION_SCHEMA = vol.Schema(
  {
    vol.Required("notification_id"): cv.string,
  },
)

SERVICE_CALCULATE_PORTION_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("meal_type"): cv.string,
    vol.Optional("override_health_data"): vol.Schema(
      {
        vol.Optional("weight"): vol.Coerce(float),
        vol.Optional("activity_level"): cv.string,
        vol.Optional("health_conditions"): [cv.string],
      },
    ),
  },
)

SERVICE_EXPORT_DATA_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("data_type"): vol.In(
      ["feeding", "walks", "health", "medication", "routes", "garden", "all"],
    ),
    vol.Optional("format", default="json"): vol.In(["json", "csv", "gpx", "pdf"]),
    vol.Optional("days"): vol.Coerce(int),
    vol.Optional(
      "date_from",
    ): cv.date,  # NEW: Missing parameter from comprehensive_readme.md
    vol.Optional(
      "date_to",
    ): cv.date,  # NEW: Missing parameter from comprehensive_readme.md
    vol.Optional("include_summary", default=True): cv.boolean,
    vol.Optional("compress", default=False): cv.boolean,
  },
)

SERVICE_ANALYZE_PATTERNS_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("analysis_type"): vol.In(
      ["feeding", "walking", "health", "comprehensive"],
    ),
    vol.Optional("days", default=30): vol.Coerce(int),
  },
)

SERVICE_GENERATE_REPORT_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("report_type"): vol.In(
      ["health", "activity", "nutrition", "comprehensive"],
    ),
    vol.Optional("include_recommendations", default=True): cv.boolean,
    vol.Optional("days", default=30): vol.Coerce(int),
  },
)

SERVICE_DAILY_RESET_SCHEMA = vol.Schema({vol.Optional("entry_id"): cv.string})

# Automation service schemas
SERVICE_RECALCULATE_HEALTH_PORTIONS_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("force_recalculation", default=False): cv.boolean,
    vol.Optional("update_feeding_schedule", default=True): cv.boolean,
  },
)

SERVICE_ADJUST_CALORIES_FOR_ACTIVITY_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("activity_level"): vol.In(
      ["very_low", "low", "moderate", "high", "very_high"],
    ),
    vol.Optional("duration_hours"): vol.Coerce(int),
    vol.Optional("temporary", default=True): cv.boolean,
  },
)

SERVICE_ACTIVATE_DIABETIC_FEEDING_MODE_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("meal_frequency", default=4): vol.Range(min=3, max=6),
    vol.Optional("carb_limit_percent", default=20): vol.Range(min=5, max=30),
    vol.Optional("monitor_blood_glucose", default=True): cv.boolean,
  },
)

SERVICE_FEED_WITH_MEDICATION_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("amount"): vol.Coerce(float),
    vol.Required("medication_name"): cv.string,
    vol.Required("dose"): cv.string,
    vol.Optional("meal_type", default="medication"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("administration_time"): cv.datetime,
  },
)

SERVICE_GENERATE_WEEKLY_HEALTH_REPORT_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("include_recommendations", default=True): cv.boolean,
    vol.Optional("include_charts", default=True): cv.boolean,
    vol.Optional("format", default="pdf"): vol.In(["pdf", "json", "markdown"]),
  },
)

SERVICE_ACTIVATE_EMERGENCY_FEEDING_MODE_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("emergency_type"): vol.In(
      ["illness", "surgery_recovery", "digestive_upset", "medication_reaction"],
    ),
    vol.Optional("duration_days", default=3): vol.Range(min=1, max=14),
    vol.Optional("portion_adjustment", default=0.8): vol.Range(min=0.5, max=1.2),
  },
)

SERVICE_START_DIET_TRANSITION_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("new_food_type"): cv.string,
    vol.Optional("transition_days", default=7): vol.Range(min=3, max=14),
    vol.Optional("gradual_increase_percent", default=25): vol.Range(min=10, max=50),
  },
)

SERVICE_CHECK_FEEDING_COMPLIANCE_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("days_to_check", default=7): vol.Range(min=1, max=30),
    vol.Optional("notify_on_issues", default=True): cv.boolean,
  },
)

SERVICE_ADJUST_DAILY_PORTIONS_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("adjustment_percent"): vol.Range(min=-50, max=50),
    vol.Optional("reason"): cv.string,
    vol.Optional("temporary", default=False): cv.boolean,
    vol.Optional("duration_days"): vol.Range(min=1, max=30),
  },
)

SERVICE_ADD_HEALTH_SNACK_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("snack_type"): cv.string,
    vol.Required("amount"): vol.Coerce(float),
    vol.Optional("health_benefit"): vol.In(
      ["digestive", "dental", "joint", "skin_coat", "immune", "calming"],
    ),
    vol.Optional("notes"): cv.string,
  },
)

SERVICE_LOG_POOP_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("quality"): vol.In(
      ["excellent", "good", "normal", "soft", "loose", "watery"],
    ),
    vol.Optional("color"): vol.In(
      [
        "brown",
        "dark_brown",
        "light_brown",
        "yellow",
        "green",
        "black",
        "red",
      ],
    ),
    vol.Optional("size"): vol.In(["small", "normal", "large"]),
    vol.Optional("location"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("timestamp"): cv.datetime,
  },
)

SERVICE_START_GROOMING_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("grooming_type"): vol.In(
      [
        "full_groom",
        "bath",
        "nail_trim",
        "brush",
        "ear_clean",
        "teeth_clean",
      ],
    ),
    vol.Optional("groomer"): cv.string,
    vol.Optional("location"): cv.string,
    vol.Optional("estimated_duration_minutes"): vol.Coerce(int),
    vol.Optional("notes"): cv.string,
    vol.Optional("reminder_id"): cv.string,
    vol.Optional("reminder_type"): cv.string,
    vol.Optional("reminder_sent_at"): cv.datetime,
  },
)

# NEW: Garden tracking service schemas
SERVICE_START_GARDEN_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("detection_method", default="manual"): vol.In(
      ["manual", "door_sensor", "auto"],
    ),
    vol.Optional("weather_conditions"): cv.string,
    vol.Optional("temperature"): vol.Coerce(float),
    vol.Optional("automation_fallback", default=False): cv.boolean,
    vol.Optional("fallback_reason"): cv.string,
    vol.Optional("automation_source"): cv.string,
  },
)

SERVICE_END_GARDEN_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("activities"): [
      vol.Schema(
        {
          vol.Required("type"): vol.In(
            [
              "general",
              "poop",
              "play",
              "sniffing",
              "digging",
              "resting",
            ],
          ),
          vol.Optional("duration_seconds"): vol.Coerce(int),
          vol.Optional("location"): cv.string,
          vol.Optional("notes"): cv.string,
          vol.Optional("confirmed", default=True): cv.boolean,
        },
      ),
    ],
  },
)

SERVICE_ADD_GARDEN_ACTIVITY_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("activity_type"): vol.In(
      ["general", "poop", "play", "sniffing", "digging", "resting"],
    ),
    vol.Optional("duration_seconds"): vol.Coerce(int),
    vol.Optional("location"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("confirmed", default=True): cv.boolean,
  },
)

SERVICE_CONFIRM_POOP_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("confirmed"): cv.boolean,
    vol.Optional("quality"): vol.In(
      ["excellent", "good", "normal", "soft", "loose", "watery"],
    ),
    vol.Optional("size"): vol.In(["small", "normal", "large"]),
    vol.Optional("location"): cv.string,
  },
)

# NEW: Weather service schemas
SERVICE_UPDATE_WEATHER_SCHEMA = vol.Schema(
  {
    vol.Optional("weather_entity_id"): cv.string,
    vol.Optional("force_update", default=False): cv.boolean,
  },
)

SERVICE_GET_WEATHER_ALERTS_SCHEMA = vol.Schema(
  {
    vol.Optional("dog_id"): cv.string,
    vol.Optional("severity_filter"): vol.In(["low", "moderate", "high", "extreme"]),
    vol.Optional("impact_filter"): vol.In(
      [
        "heat_stress",
        "cold_stress",
        "uv_exposure",
        "air_quality",
        "exercise_limitation",
        "hydration_risk",
        "paw_protection",
        "respiratory_risk",
      ],
    ),
  },
)

SERVICE_GET_WEATHER_RECOMMENDATIONS_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Optional("include_breed_specific", default=True): cv.boolean,
    vol.Optional("include_health_conditions", default=True): cv.boolean,
    vol.Optional("max_recommendations", default=5): vol.Range(min=1, max=10),
  },
)


async def async_setup_services(hass: HomeAssistant) -> None:
  """Set up PawControl services.

  Args:
      hass: Home Assistant instance
  """

  resolver = _coordinator_resolver(hass)
  resolver.invalidate()

  domain_data = hass.data.setdefault(DOMAIN, {})

  # Replace any previous listener so duplicate registrations do not accumulate.
  remove_listener = domain_data.pop("_service_coordinator_listener", None)
  if callable(remove_listener):
    remove_listener()

  @callback
  def _handle_config_entry_state(
    change: ConfigEntryChange,
    entry: ConfigEntry,
  ) -> None:
    """Invalidate cached coordinator when the active entry changes state."""

    if entry.domain != DOMAIN:
      return

    if change in (
      ConfigEntryChange.ADDED,
      ConfigEntryChange.REMOVED,
      ConfigEntryChange.UPDATED,
    ):
      resolver.invalidate(entry_id=entry.entry_id)

  domain_data["_service_coordinator_listener"] = async_dispatcher_connect(
    hass,
    SIGNAL_CONFIG_ENTRY_CHANGED,
    _handle_config_entry_state,
  )

  def _get_coordinator() -> PawControlCoordinator:
    """Return the active coordinator or raise a descriptive error."""

    return resolver.resolve()

  def _get_runtime_manager(
    coordinator: PawControlCoordinator,
    attribute: str,
  ) -> Any | None:
    """Return a runtime manager from the coordinator container when available."""

    managers = getattr(coordinator, "runtime_managers", None)
    if isinstance(managers, CoordinatorRuntimeManagers):
      return getattr(managers, attribute)
    return getattr(coordinator, attribute, None)

  def _require_manager(manager: _ManagerT | None, description: str) -> _ManagerT:
    """Ensure a runtime manager is available before using it."""

    if manager is None:
      raise HomeAssistantError(
        f"The PawControl {description} is not ready yet. "
        "Wait for the integration to finish setting up or reload it.",
      )

    return manager

  def _resolve_dog(
    coordinator: PawControlCoordinator,
    raw_dog_id: str,
  ) -> tuple[str, DogConfigData]:
    """Validate and normalize a dog identifier for service handling."""

    if not isinstance(raw_dog_id, str):
      raise _service_validation_error(
        "dog_id must be provided as a string",
      )

    dog_id = raw_dog_id.strip()
    if not dog_id:
      raise _service_validation_error(
        "dog_id must be a non-empty string",
      )

    dog_config = coordinator.get_dog_config(dog_id)
    if dog_config is None:
      known_ids = coordinator.get_configured_dog_ids()
      if known_ids:
        hint = ", ".join(sorted(known_ids))
        raise _service_validation_error(
          f"Unknown dog_id '{dog_id}'. Known dog_ids: {hint}",
        )
      raise _service_validation_error(
        "No dogs are configured for PawControl. Add a dog before calling services.",
      )

    return dog_id, dog_config

  def _update_latency_metrics(
    target: MutableMapping[str, JSONValue],
    duration_ms: float,
  ) -> None:
    """Update latency metrics for a service call."""

    latency_raw = target.get("latency_ms")
    if isinstance(latency_raw, MutableMapping):
      latency = latency_raw
    else:
      latency = cast(JSONMutableMapping, {})
      target["latency_ms"] = latency

    samples = int(latency.get("samples", 0) or 0)
    average = float(latency.get("average_ms", 0.0) or 0.0)
    next_samples = samples + 1
    latency["samples"] = next_samples
    latency["average_ms"] = ((average * samples) + duration_ms) / next_samples

    minimum = latency.get("minimum_ms")
    maximum = latency.get("maximum_ms")
    duration_value = float(duration_ms)
    if minimum is None or duration_value < float(minimum):
      latency["minimum_ms"] = duration_value
    if maximum is None or duration_value > float(maximum):
      latency["maximum_ms"] = duration_value
    latency["last_ms"] = duration_value

  def _apply_service_call_metrics(
    target: MutableMapping[str, JSONValue],
    *,
    status: Literal["success", "error"],
    duration_ms: float,
  ) -> None:
    """Accumulate service call metrics into ``target``."""

    total_calls = int(target.get("total_calls", 0) or 0) + 1
    success_calls = int(target.get("success_calls", 0) or 0)
    error_calls = int(target.get("error_calls", 0) or 0)
    if status == "success":
      success_calls += 1
    else:
      error_calls += 1

    target["total_calls"] = total_calls
    target["success_calls"] = success_calls
    target["error_calls"] = error_calls
    target["error_rate"] = (error_calls / total_calls) if total_calls else 0.0

    _update_latency_metrics(target, duration_ms)

  def _update_service_call_telemetry(
    runtime_data: PawControlRuntimeData | None,
    *,
    service: str,
    status: Literal["success", "error"],
    duration_ms: float,
  ) -> None:
    """Record service call telemetry in runtime performance stats."""

    if runtime_data is None:
      return

    performance_stats = ensure_runtime_performance_stats(runtime_data)
    telemetry_raw = performance_stats.setdefault(
      "service_call_telemetry",
      cast(ServiceCallTelemetry, {}),
    )
    if not isinstance(telemetry_raw, MutableMapping):
      telemetry_raw = {}
      performance_stats["service_call_telemetry"] = telemetry_raw

    _apply_service_call_metrics(
      telemetry_raw,
      status=status,
      duration_ms=duration_ms,
    )

    per_service_raw = telemetry_raw.setdefault("per_service", {})
    if not isinstance(per_service_raw, MutableMapping):
      per_service_raw = {}
      telemetry_raw["per_service"] = per_service_raw

    entry_raw = per_service_raw.setdefault(
      service,
      cast(ServiceCallTelemetryEntry, {}),
    )
    if not isinstance(entry_raw, MutableMapping):
      entry_raw = {}
      per_service_raw[service] = entry_raw

    _apply_service_call_metrics(
      entry_raw,
      status=status,
      duration_ms=duration_ms,
    )

  def _wrap_service_handler(
    service: str,
    handler: Callable[[ServiceCall], Awaitable[None]],
  ) -> Callable[[ServiceCall], Awaitable[None]]:
    """Wrap a service handler to capture runtime telemetry."""

    async def _wrapped(call: ServiceCall) -> None:
      start = time.perf_counter()
      status: Literal["success", "error"] = "success"
      try:
        await handler(call)
      except Exception:
        status = "error"
        raise
      finally:
        duration_ms = max((time.perf_counter() - start) * 1000.0, 0.0)
        runtime_data: PawControlRuntimeData | None = None
        try:
          coordinator = _get_coordinator()
          runtime_data = get_runtime_data(
            hass,
            coordinator.config_entry,
          )
        except Exception as err:  # pragma: no cover - telemetry guard
          dog_id = call.data.get("dog_id")
          _LOGGER.debug(
            "Skipping service telemetry update for %s (dog_id=%s): %s",
            service,
            dog_id,
            err,
          )
        else:
          _update_service_call_telemetry(
            runtime_data,
            service=service,
            status=status,
            duration_ms=duration_ms,
          )

    return _wrapped

  def _register_service(
    service: str,
    handler: Callable[[ServiceCall], Awaitable[None]],
    *,
    schema: vol.Schema,
  ) -> None:
    """Register a service with telemetry wrapping."""

    hass.services.async_register(
      DOMAIN,
      service,
      _wrap_service_handler(service, handler),
      schema=schema,
    )

  async def _async_handle_feeding_request(
    data: ServiceData,
    *,
    service_name: str,
  ) -> None:
    """Shared implementation for feeding-related services."""

    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    payload = dict(data)

    raw_dog_id = payload["dog_id"]
    if not isinstance(raw_dog_id, str):
      raise ServiceValidationError("dog_id must be a string")
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    amount = payload["amount"]
    meal_type = payload.get("meal_type")
    notes = payload.get("notes")
    feeder = payload.get("feeder")
    scheduled = bool(payload.get("scheduled", False))
    with_medication = bool(payload.get("with_medication", False))
    medication_data = payload.get("medication_data")
    if isinstance(medication_data, Mapping):
      medication_data = dict(medication_data)

    try:
      if with_medication and medication_data:
        await feeding_manager.async_add_feeding_with_medication(
          dog_id=dog_id,
          amount=amount,
          meal_type=meal_type,
          medication_data=medication_data,
          notes=notes,
          feeder=feeder,
        )
      else:
        await feeding_manager.async_add_feeding(
          dog_id=dog_id,
          amount=amount,
          meal_type=meal_type,
          notes=notes,
          feeder=feeder,
          scheduled=scheduled,
        )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Added feeding for %s: %.1fg %s",
        dog_id,
        amount,
        meal_type or "unknown",
      )

      details = _normalise_service_details(
        {
          "amount": amount,
          "meal_type": meal_type,
          "scheduled": scheduled,
          "with_medication": with_medication,
          "feeder": feeder,
          "notes": notes,
          "medication": medication_data if with_medication else None,
        },
      )
      _record_service_result(
        runtime_data,
        service=service_name,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=service_name,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to add feeding for %s: %s", dog_id, err)
      error_message = f"Failed to add feeding for {dog_id}. Check the logs for details."
      _record_service_result(
        runtime_data,
        service=service_name,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def add_feeding_service(call: ServiceCall) -> None:
    """Handle add feeding service call."""

    await _async_handle_feeding_request(call.data, service_name=SERVICE_ADD_FEEDING)

  async def feed_dog_service(call: ServiceCall) -> None:
    """Handle feed_dog service call (alias for add_feeding)."""

    payload = dict(call.data)
    payload.setdefault("scheduled", False)
    payload.setdefault("with_medication", False)
    await _async_handle_feeding_request(payload, service_name=SERVICE_FEED_DOG)

  async def start_walk_service(call: ServiceCall) -> None:
    """Handle start walk service call."""
    coordinator = _get_coordinator()
    walk_manager = _require_manager(
      _get_runtime_manager(coordinator, "walk_manager"),
      "walk manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    walker = call.data.get("walker")
    weather = call.data.get("weather")
    leash_used = call.data.get("leash_used", True)

    try:
      weather_enum: WeatherCondition | None = None
      if weather:
        try:
          weather_enum = WeatherCondition(weather)
        except ValueError:
          _LOGGER.warning(
            "Ignoring unknown weather condition '%s' for %s",
            weather,
            dog_id,
          )

      session_id = await walk_manager.async_start_walk(
        dog_id=dog_id,
        walk_type="manual",
        walker=walker,
        weather=weather_enum,
        leash_used=leash_used,
      )

      _LOGGER.info(
        "Started walk for %s (session: %s, walker: %s, weather: %s, leash_used: %s)",
        dog_id,
        session_id,
        walker or "unknown",
        weather_enum.value if weather_enum else "unspecified",
        "yes" if leash_used else "no",
      )

      details = _normalise_service_details(
        {
          "session_id": session_id,
          "walker": walker,
          "weather": weather_enum.value if weather_enum else weather,
          "leash_used": leash_used,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_START_WALK,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_START_WALK,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to start walk for %s: %s", dog_id, err)
      error_message = (
        f"Failed to start the walk for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_START_WALK,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def end_walk_service(call: ServiceCall) -> None:
    """Handle end walk service call."""
    coordinator = _get_coordinator()
    walk_manager = _require_manager(
      _get_runtime_manager(coordinator, "walk_manager"),
      "walk manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    notes = call.data.get("notes")
    dog_weight_kg = call.data.get("dog_weight_kg")

    try:
      walk_event = await walk_manager.async_end_walk(
        dog_id=dog_id,
        notes=notes,
        dog_weight_kg=dog_weight_kg,
      )

      if walk_event:
        await coordinator.async_request_refresh()

        distance_km = float(walk_event.get("distance") or 0.0) / 1000
        duration_minutes = (
          float(
            walk_event.get("duration") or 0.0,
          )
          / 60
        )

        _LOGGER.info(
          "Ended walk for %s: %.2f km in %.0f minutes",
          dog_id,
          distance_km,
          duration_minutes,
        )
        details = _normalise_service_details(
          {
            "distance_km": distance_km,
            "duration_minutes": duration_minutes,
            "notes": notes,
            "dog_weight_kg": dog_weight_kg,
          },
        )
        _record_service_result(
          runtime_data,
          service=SERVICE_END_WALK,
          status="success",
          dog_id=dog_id,
          details=details,
        )
      else:
        _LOGGER.warning("No active walk found for %s", dog_id)
        _record_service_result(
          runtime_data,
          service=SERVICE_END_WALK,
          status="success",
          dog_id=dog_id,
          details=_normalise_service_details(
            {
              "notes": notes,
              "dog_weight_kg": dog_weight_kg,
              "result": "no_active_walk",
            },
          ),
        )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_END_WALK,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to end walk for %s: %s", dog_id, err)
      error_message = (
        f"Failed to end the walk for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_END_WALK,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def add_gps_point_service(call: ServiceCall) -> None:
    """Handle add GPS point service call."""
    coordinator = _get_coordinator()
    walk_manager = _require_manager(
      _get_runtime_manager(coordinator, "walk_manager"),
      "walk manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    latitude = call.data["latitude"]
    longitude = call.data["longitude"]
    altitude = call.data.get("altitude")
    accuracy = call.data.get("accuracy")

    try:
      success = await walk_manager.async_add_gps_point(
        dog_id=dog_id,
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        accuracy=accuracy,
      )

      details = _normalise_service_details(
        {
          "latitude": latitude,
          "longitude": longitude,
          "altitude": altitude,
          "accuracy": accuracy,
          "result": "added" if success else "ignored",
        },
      )

      if success:
        _LOGGER.debug(
          "Added GPS point for %s: lat=%.6f lon=%.6f alt=%s accuracy=%s",
          dog_id,
          latitude,
          longitude,
          altitude,
          accuracy,
        )
      else:
        _LOGGER.warning("Failed to add GPS point for %s", dog_id)

      _record_service_result(
        runtime_data,
        service=SERVICE_ADD_GPS_POINT,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_ADD_GPS_POINT,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to add GPS point for %s: %s", dog_id, err)
      error_message = (
        f"Failed to add GPS point for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_ADD_GPS_POINT,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def update_health_service(call: ServiceCall) -> None:
    """Handle update health service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    health_data = {
      k: v for k, v in call.data.items() if k != "dog_id" and v is not None
    }

    try:
      success = await feeding_manager.async_update_health_data(
        dog_id=dog_id,
        health_data=health_data,
      )

      if success:
        await coordinator.async_request_refresh()

        _LOGGER.info(
          "Updated health data for %s: %s",
          dog_id,
          health_data,
        )
      else:
        _LOGGER.warning("Failed to update health data for %s", dog_id)

      details = _normalise_service_details(
        {
          "health_data": health_data,
          "result": "updated" if success else "no_update",
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_UPDATE_HEALTH,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_UPDATE_HEALTH,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to update health data for %s: %s",
        dog_id,
        err,
      )
      error_message = (
        f"Failed to update health data for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_UPDATE_HEALTH,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def log_health_service(call: ServiceCall) -> None:
    """Handle log health service call."""
    coordinator = _get_coordinator()
    data_manager = _require_manager(
      _get_runtime_manager(coordinator, "data_manager"),
      "data manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    health_data = {
      k: v for k, v in call.data.items() if k != "dog_id" and v is not None
    }
    health_data["timestamp"] = dt_util.utcnow()

    try:
      await data_manager.async_log_health_data(
        dog_id=dog_id,
        health_data=health_data,
      )
      await coordinator.async_request_refresh()

      _LOGGER.info("Logged health data for %s: %s", dog_id, health_data)

      details = _normalise_service_details({"health_data": health_data})
      _record_service_result(
        runtime_data,
        service=SERVICE_LOG_HEALTH,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_LOG_HEALTH,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to log health data for %s: %s", dog_id, err)
      error_message = (
        f"Failed to log health data for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_LOG_HEALTH,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def log_medication_service(call: ServiceCall) -> None:
    """Handle log medication service call."""
    coordinator = _get_coordinator()
    data_manager = _require_manager(
      _get_runtime_manager(coordinator, "data_manager"),
      "data manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    medication_data = {
      k: v for k, v in call.data.items() if k != "dog_id" and v is not None
    }

    if "administration_time" not in medication_data:
      medication_data["administration_time"] = dt_util.utcnow()

    try:
      await data_manager.async_log_medication(
        dog_id=dog_id,
        medication_data=medication_data,
      )
      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Logged medication for %s: %s %s",
        dog_id,
        medication_data.get("medication_name"),
        medication_data.get("dose"),
      )

      details = _normalise_service_details(
        {"medication_data": medication_data},
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_LOG_MEDICATION,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_LOG_MEDICATION,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to log medication for %s: %s", dog_id, err)
      error_message = (
        f"Failed to log medication for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_LOG_MEDICATION,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def toggle_visitor_mode_service(call: ServiceCall) -> None:
    """Handle toggle visitor mode service call."""
    coordinator = _get_coordinator()
    data_manager = _require_manager(
      _get_runtime_manager(coordinator, "data_manager"),
      "data manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    enabled = call.data.get("enabled")
    visitor_name = call.data.get("visitor_name")
    duration_hours = call.data.get("duration_hours")

    try:
      # Get current visitor mode state if not explicitly set
      if enabled is None:
        current_state = await data_manager.async_get_visitor_mode_status(dog_id)
        enabled = not current_state.get("enabled", False)

      visitor_data = {
        "enabled": enabled,
        "visitor_name": visitor_name,
        "duration_hours": duration_hours,
        "timestamp": dt_util.utcnow(),
      }

      await data_manager.async_set_visitor_mode(
        dog_id=dog_id,
        visitor_data=visitor_data,
      )
      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Visitor mode for %s: %s (visitor: %s, duration: %sh)",
        dog_id,
        "enabled" if enabled else "disabled",
        visitor_name or "unknown",
        duration_hours or "unlimited",
      )

      details = _normalise_service_details(
        {
          "enabled": enabled,
          "visitor_name": visitor_name,
          "duration_hours": duration_hours,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_TOGGLE_VISITOR_MODE,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_TOGGLE_VISITOR_MODE,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to toggle visitor mode for %s: %s",
        dog_id,
        err,
      )
      error_message = (
        f"Failed to toggle visitor mode for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_TOGGLE_VISITOR_MODE,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def gps_start_walk_service(call: ServiceCall) -> None:
    """Handle GPS start walk service call."""
    coordinator = _get_coordinator()
    gps_manager = _require_manager(
      coordinator.gps_geofence_manager,
      "GPS geofence manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    walker = call.data.get("walker")
    track_route = call.data.get("track_route", True)
    safety_alerts = call.data.get("safety_alerts", True)

    try:
      session_id = await gps_manager.async_start_gps_tracking(
        dog_id=dog_id,
        walker=walker,
        track_route=track_route,
        safety_alerts=safety_alerts,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Started GPS walk for %s (session: %s, tracking: %s, alerts: %s)",
        dog_id,
        session_id,
        "enabled" if track_route else "disabled",
        "enabled" if safety_alerts else "disabled",
      )

      details = _normalise_service_details(
        {
          "session_id": session_id,
          "walker": walker,
          "track_route": track_route,
          "safety_alerts": safety_alerts,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_START_WALK,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_START_WALK,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to start GPS walk for %s: %s", dog_id, err)
      error_message = (
        f"Failed to start GPS walk for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_START_WALK,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def gps_end_walk_service(call: ServiceCall) -> None:
    """Handle GPS end walk service call."""
    coordinator = _get_coordinator()
    gps_manager = _require_manager(
      coordinator.gps_geofence_manager,
      "GPS geofence manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    save_route = call.data.get("save_route", True)
    notes = call.data.get("notes")

    try:
      walk_route = await gps_manager.async_end_gps_tracking(
        dog_id=dog_id,
        save_route=save_route,
        notes=notes,
      )

      if walk_route:
        await coordinator.async_request_refresh()

        _LOGGER.info(
          "Ended GPS walk for %s: %.2f km in %.0f minutes (route %s)",
          dog_id,
          walk_route.distance_km,
          walk_route.duration_minutes,
          "saved" if save_route else "discarded",
        )
        details = _normalise_service_details(
          {
            "distance_km": walk_route.distance_km,
            "duration_minutes": walk_route.duration_minutes,
            "save_route": save_route,
            "notes": notes,
          },
        )
        _record_service_result(
          runtime_data,
          service=SERVICE_GPS_END_WALK,
          status="success",
          dog_id=dog_id,
          details=details,
        )
      else:
        _LOGGER.warning("No active GPS walk found for %s", dog_id)
        _record_service_result(
          runtime_data,
          service=SERVICE_GPS_END_WALK,
          status="success",
          dog_id=dog_id,
          details=_normalise_service_details(
            {
              "save_route": save_route,
              "notes": notes,
              "result": "no_active_walk",
            },
          ),
        )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_END_WALK,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to end GPS walk for %s: %s", dog_id, err)
      error_message = (
        f"Failed to end GPS walk for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_END_WALK,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def gps_post_location_service(call: ServiceCall) -> None:
    """Handle GPS post location service call."""
    coordinator = _get_coordinator()
    gps_manager = _require_manager(
      coordinator.gps_geofence_manager,
      "GPS geofence manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    latitude = call.data["latitude"]
    longitude = call.data["longitude"]
    altitude = call.data.get("altitude")
    accuracy = call.data.get("accuracy")
    timestamp = call.data.get("timestamp", dt_util.utcnow())

    try:
      from .gps_manager import LocationSource

      success = await gps_manager.async_add_gps_point(
        dog_id=dog_id,
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        accuracy=accuracy,
        timestamp=timestamp,
        source=LocationSource.EXTERNAL_API,
      )

      if success:
        _LOGGER.debug(
          "Posted GPS location for %s: %.6f,%.6f",
          dog_id,
          latitude,
          longitude,
        )
      else:
        _LOGGER.warning("Failed to post GPS location for %s", dog_id)

      details = _normalise_service_details(
        {
          "latitude": latitude,
          "longitude": longitude,
          "altitude": altitude,
          "accuracy": accuracy,
          "timestamp": timestamp.isoformat()
          if hasattr(timestamp, "isoformat")
          else timestamp,
          "result": "posted" if success else "ignored",
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_POST_LOCATION,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_POST_LOCATION,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to post GPS location for %s: %s",
        dog_id,
        err,
      )
      error_message = (
        f"Failed to post GPS location for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_POST_LOCATION,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def gps_export_route_service(call: ServiceCall) -> None:
    """Handle GPS export route service call."""
    coordinator = _get_coordinator()
    gps_manager = _require_manager(
      coordinator.gps_geofence_manager,
      "GPS geofence manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    export_format = call.data.get("format", "gpx")
    last_n_walks = call.data.get("last_n_walks", 1)

    try:
      export_data = await gps_manager.async_export_routes(
        dog_id=dog_id,
        export_format=export_format,
        last_n_routes=last_n_walks,
      )

      routes_count = export_data["routes_count"] if export_data else 0

      guard_snapshot: tuple[ServiceGuardResult, ...] = ()

      if export_data:
        _LOGGER.info(
          "Exported %d route(s) for %s in %s format",
          routes_count,
          dog_id,
          export_format,
        )

        # Send notification with export result
        notification_manager = _get_runtime_manager(
          coordinator,
          "notification_manager",
        )
        if notification_manager:
          async with async_capture_service_guard_results() as captured_guards:
            await notification_manager.async_send_notification(
              notification_type=NotificationType.SYSTEM_INFO,
              title="Route Export Complete",
              message=(
                f"Exported {routes_count} route(s) for {dog_id} "
                f"in {export_format} format"
              ),
              dog_id=dog_id,
            )
            guard_snapshot = tuple(captured_guards)
        details_result = "exported"
      else:
        _LOGGER.warning("No routes found for export for %s", dog_id)
        details_result = "no_routes"

      details = _normalise_service_details(
        {
          "export_format": export_format,
          "last_n_walks": last_n_walks,
          "routes_count": routes_count,
          "result": details_result,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_EXPORT_ROUTE,
        status="success",
        dog_id=dog_id,
        details=details,
        guard=guard_snapshot if guard_snapshot else None,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_EXPORT_ROUTE,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to export routes for %s: %s", dog_id, err)
      error_message = (
        f"Failed to export routes for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GPS_EXPORT_ROUTE,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  # NEW: Setup automatic GPS service - mentioned in info.md but was missing
  async def setup_automatic_gps_service(call: ServiceCall) -> None:
    """Handle setup automatic GPS service call.

    NEW: Implements the setup_automatic_gps service mentioned in info.md
    with parameters like auto_start_walk, safe_zone_radius, and track_route.
    """
    coordinator = _get_coordinator()
    gps_manager = _require_manager(
      coordinator.gps_geofence_manager,
      "GPS geofence manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    auto_start_walk = call.data.get("auto_start_walk", True)
    safe_zone_radius = call.data.get("safe_zone_radius", 50)
    track_route = call.data.get("track_route", True)
    safety_alerts = call.data.get("safety_alerts", True)
    geofence_notifications = call.data.get("geofence_notifications", True)
    auto_detect_home = call.data.get("auto_detect_home", True)
    gps_accuracy_threshold = call.data.get("gps_accuracy_threshold", 50)
    update_interval_seconds = call.data.get("update_interval_seconds", 60)

    guard_results: list[ServiceGuardResult] = []
    guard_snapshot: tuple[ServiceGuardResult, ...] = ()

    try:
      # Configure automatic GPS settings for the dog
      gps_config: GPSTrackingConfigInput = {
        "enabled": True,
        "auto_start_walk": auto_start_walk,
        "track_route": track_route,
        "safety_alerts": safety_alerts,
        "geofence_notifications": geofence_notifications,
        "auto_detect_home": auto_detect_home,
        "gps_accuracy_threshold": gps_accuracy_threshold,
        "update_interval_seconds": update_interval_seconds,
        "configured_at": dt_util.utcnow(),
      }

      # Configure GPS tracking for the dog
      await gps_manager.async_configure_dog_gps(dog_id=dog_id, config=gps_config)

      # Setup geofencing safe zone
      if auto_detect_home:
        # Use Home Assistant's home location
        home_lat = hass.config.latitude
        home_lon = hass.config.longitude

        await gps_manager.async_setup_safe_zone(
          dog_id=dog_id,
          center_lat=home_lat,
          center_lon=home_lon,
          radius_meters=safe_zone_radius,
          notifications_enabled=geofence_notifications,
        )

        _LOGGER.info(
          "Setup geofencing safe zone for %s: center=%.6f,%.6f radius=%dm",
          dog_id,
          home_lat,
          home_lon,
          safe_zone_radius,
        )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Setup automatic GPS for %s: auto_walk=%s, safe_zone=%dm, tracking=%s",
        dog_id,
        auto_start_walk,
        safe_zone_radius,
        track_route,
      )

      # Send notification about GPS setup
      notification_manager = _get_runtime_manager(
        coordinator,
        "notification_manager",
      )
      if notification_manager:
        async with async_capture_service_guard_results() as captured_guards:
          guard_results = captured_guards
          await notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title=f"🛰️ GPS Setup Complete: {dog_id}",
            message=(
              f"Automatic GPS tracking configured for {dog_id}. "
              f"Safe zone: {safe_zone_radius}m radius. "
              f"Auto-walk detection: {'enabled' if auto_start_walk else 'disabled'}."
            ),
            dog_id=dog_id,
          )
        guard_snapshot = tuple(guard_results)

      details = _normalise_service_details(
        {
          "auto_start_walk": auto_start_walk,
          "safe_zone_radius": safe_zone_radius,
          "track_route": track_route,
          "safety_alerts": safety_alerts,
          "geofence_notifications": geofence_notifications,
          "auto_detect_home": auto_detect_home,
          "gps_accuracy_threshold": gps_accuracy_threshold,
          "update_interval_seconds": update_interval_seconds,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_SETUP_AUTOMATIC_GPS,
        status="success",
        dog_id=dog_id,
        details=details,
        guard=guard_snapshot if guard_snapshot else None,
      )

    except HomeAssistantError as err:
      guard_snapshot = tuple(guard_results)
      _record_service_result(
        runtime_data,
        service=SERVICE_SETUP_AUTOMATIC_GPS,
        status="error",
        dog_id=dog_id,
        message=str(err),
        guard=guard_snapshot if guard_snapshot else None,
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to setup automatic GPS for %s: %s",
        dog_id,
        err,
      )
      error_message = (
        f"Failed to setup automatic GPS for {dog_id}. Check the logs for details."
      )
      guard_snapshot = tuple(guard_results)
      _record_service_result(
        runtime_data,
        service=SERVICE_SETUP_AUTOMATIC_GPS,
        status="error",
        dog_id=dog_id,
        message=error_message,
        guard=guard_snapshot if guard_snapshot else None,
      )
      raise HomeAssistantError(error_message) from err

  async def send_notification_service(call: ServiceCall) -> None:
    """Handle send notification service call."""
    coordinator = _get_coordinator()
    notification_manager = _require_manager(
      _get_runtime_manager(coordinator, "notification_manager"),
      "notification manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    title = call.data["title"]
    message = call.data["message"]
    dog_id = call.data.get("dog_id")
    notification_type_raw = call.data.get(
      "notification_type",
      NotificationType.SYSTEM_INFO,
    )
    priority_raw = call.data.get("priority", NotificationPriority.NORMAL)
    channels = call.data.get("channels")
    expires_in_hours_raw = call.data.get("expires_in_hours")

    guard_results: list[ServiceGuardResult] = []
    guard_snapshot: tuple[ServiceGuardResult, ...] = ()

    try:
      if not isinstance(title, str):
        raise _service_validation_error("title must be a string")
      title = title.strip()
      if not title:
        raise _service_validation_error(
          "title must be a non-empty string",
        )

      if not isinstance(message, str):
        raise _service_validation_error("message must be a string")
      message = message.strip()
      if not message:
        raise _service_validation_error(
          "message must be a non-empty string",
        )

      if dog_id is not None:
        if not isinstance(dog_id, str):
          raise _service_validation_error("dog_id must be a string")
        dog_id = dog_id.strip()
        if not dog_id:
          raise _service_validation_error(
            "dog_id must be a non-empty string",
          )
        dog_id, _ = _resolve_dog(coordinator, dog_id)

      try:
        notification_type_enum = NotificationType(
          notification_type_raw,
        )
      except (TypeError, ValueError):
        _LOGGER.warning(
          "Unknown notification type '%s'; defaulting to %s",
          notification_type_raw,
          NotificationType.SYSTEM_INFO.value,
        )
        notification_type_enum = NotificationType.SYSTEM_INFO

      try:
        priority_enum = NotificationPriority(priority_raw)
      except (TypeError, ValueError):
        _LOGGER.warning(
          "Unknown notification priority '%s'; defaulting to %s",
          priority_raw,
          NotificationPriority.NORMAL.value,
        )
        priority_enum = NotificationPriority.NORMAL

      channel_enums = None
      invalid_channels: list[str] = []
      normalised_channels: list[NotificationChannel] = []
      if channels is not None:
        candidate_channels: Iterable[Any]
        if isinstance(channels, NotificationChannel | str):
          candidate_channels = [channels]
        elif isinstance(channels, Iterable) and not isinstance(
          channels,
          str | bytes | bytearray,
        ):
          candidate_channels = channels
        else:
          candidate_channels = [channels]

        seen_channels: set[NotificationChannel] = set()
        for channel in candidate_channels:
          try:
            channel_enum = NotificationChannel(channel)
          except (TypeError, ValueError):
            invalid_channels.append(str(channel))
            continue

          if channel_enum in seen_channels:
            continue

          seen_channels.add(channel_enum)
          normalised_channels.append(channel_enum)

      if invalid_channels:
        invalid_channels = list(dict.fromkeys(invalid_channels))
        _LOGGER.warning(
          "Ignoring unsupported notification channel(s): %s",
          ", ".join(invalid_channels),
        )

      if normalised_channels:
        channel_enums = normalised_channels

      expires_in = None
      expires_in_hours: float | None = None
      if expires_in_hours_raw is not None:
        try:
          expires_in_hours = float(expires_in_hours_raw)
        except (TypeError, ValueError):
          raise _service_validation_error(
            "expires_in_hours must be a positive number",
          ) from None
        if expires_in_hours <= 0:
          raise _service_validation_error(
            "expires_in_hours must be greater than 0",
          )
        expires_in = timedelta(hours=expires_in_hours)

      async with async_capture_service_guard_results() as captured_guards:
        guard_results = captured_guards
        notification_id = await notification_manager.async_send_notification(
          notification_type=notification_type_enum,
          title=title,
          message=message,
          dog_id=dog_id,
          priority=priority_enum,
          expires_in=expires_in,
          force_channels=channel_enums,
        )
      guard_snapshot = tuple(guard_results)

      _LOGGER.info("Sent notification %s: %s", notification_id, title)

      details_payload: ServiceDetailsPayload = {
        "notification_id": notification_id,
        "notification_type": notification_type_enum.value,
        "priority": priority_enum.value,
        "channels": [channel.value for channel in channel_enums]
        if channel_enums
        else None,
        "expires_in_hours": expires_in_hours,
      }
      if invalid_channels:
        details_payload["ignored_channels"] = invalid_channels

      details = _normalise_service_details(details_payload)
      _record_service_result(
        runtime_data,
        service=SERVICE_SEND_NOTIFICATION,
        status="success",
        dog_id=dog_id,
        details=details,
        guard=guard_snapshot,
      )

    except HomeAssistantError as err:
      guard_snapshot = tuple(guard_results)
      _record_service_result(
        runtime_data,
        service=SERVICE_SEND_NOTIFICATION,
        status="error",
        dog_id=dog_id,
        message=str(err),
        guard=guard_snapshot if guard_snapshot else None,
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to send notification: %s", err)
      error_message = (
        "Failed to send the PawControl notification. Check the logs for details."
      )
      guard_snapshot = tuple(guard_results)
      _record_service_result(
        runtime_data,
        service=SERVICE_SEND_NOTIFICATION,
        status="error",
        dog_id=dog_id,
        message=error_message,
        guard=guard_snapshot if guard_snapshot else None,
      )
      raise HomeAssistantError(error_message) from err

  async def acknowledge_notification_service(call: ServiceCall) -> None:
    """Handle acknowledge notification service call."""
    coordinator = _get_coordinator()
    notification_manager = _require_manager(
      _get_runtime_manager(coordinator, "notification_manager"),
      "notification manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    notification_id = call.data["notification_id"]
    if not isinstance(notification_id, str):
      raise _service_validation_error("notification_id must be a string")
    notification_id = notification_id.strip()
    if not notification_id:
      raise _service_validation_error(
        "notification_id must be a non-empty string",
      )

    guard_results: list[ServiceGuardResult] = []
    guard_snapshot: tuple[ServiceGuardResult, ...] = ()

    try:
      async with async_capture_service_guard_results() as captured_guards:
        guard_results = captured_guards
        acknowledged = await notification_manager.async_acknowledge_notification(
          notification_id,
        )
      guard_snapshot = tuple(guard_results)
    except HomeAssistantError as err:
      guard_snapshot = tuple(guard_results)
      _record_service_result(
        runtime_data,
        service=SERVICE_ACKNOWLEDGE_NOTIFICATION,
        status="error",
        message=str(err),
        details=_normalise_service_details(
          {"notification_id": notification_id},
        ),
        guard=guard_snapshot if guard_snapshot else None,
      )
      raise
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.error(
        "Failed to acknowledge notification %s: %s",
        notification_id,
        err,
      )
      error_message = (
        "Failed to acknowledge the PawControl notification. Check the logs for details."
      )
      guard_snapshot = tuple(guard_results)
      _record_service_result(
        runtime_data,
        service=SERVICE_ACKNOWLEDGE_NOTIFICATION,
        status="error",
        message=error_message,
        details=_normalise_service_details(
          {"notification_id": notification_id},
        ),
        guard=guard_snapshot if guard_snapshot else None,
      )
      raise HomeAssistantError(error_message) from err

    if not acknowledged:
      error_message = f"No PawControl notification with ID {notification_id} exists."
      guard_snapshot = tuple(guard_results)
      _record_service_result(
        runtime_data,
        service=SERVICE_ACKNOWLEDGE_NOTIFICATION,
        status="error",
        message=error_message,
        details=_normalise_service_details(
          {"notification_id": notification_id},
        ),
        guard=guard_snapshot if guard_snapshot else None,
      )
      raise HomeAssistantError(error_message)

    await coordinator.async_request_refresh()
    _LOGGER.debug(
      "Acknowledged PawControl notification %s",
      notification_id,
    )

    details = _normalise_service_details(
      {"notification_id": notification_id, "acknowledged": True},
    )
    guard_snapshot = tuple(guard_results)
    _record_service_result(
      runtime_data,
      service=SERVICE_ACKNOWLEDGE_NOTIFICATION,
      status="success",
      details=details,
      guard=guard_snapshot if guard_snapshot else None,
    )

  async def calculate_portion_service(call: ServiceCall) -> None:
    """Handle calculate portion service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )

    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    meal_type = call.data["meal_type"]
    override_health_data = call.data.get("override_health_data")

    try:
      portion_data = await feeding_manager.async_calculate_portion(
        dog_id=dog_id,
        meal_type=meal_type,
        override_health_data=override_health_data,
      )

      _LOGGER.info(
        "Calculated portion for %s %s: %s",
        dog_id,
        meal_type,
        portion_data,
      )

      details = _normalise_service_details(portion_data)
      _record_service_result(
        runtime_data,
        service=SERVICE_CALCULATE_PORTION,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_CALCULATE_PORTION,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to calculate portion for %s: %s",
        dog_id,
        err,
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_CALCULATE_PORTION,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise HomeAssistantError(
        f"Failed to calculate portion for {dog_id}. Check the logs for details.",
      ) from err

  async def export_data_service(call: ServiceCall) -> None:
    """Handle export data service call."""
    coordinator = _get_coordinator()
    data_manager = _require_manager(
      _get_runtime_manager(coordinator, "data_manager"),
      "data manager",
    )

    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    data_type = call.data["data_type"]
    export_format = call.data.get("format", "json")
    days = call.data.get("days")
    date_from = call.data.get("date_from")
    date_to = call.data.get("date_to")

    try:
      await data_manager.async_export_data(
        dog_id=dog_id,
        data_type=data_type,
        format=export_format,
        days=days,
        date_from=date_from,
        date_to=date_to,
      )

      _LOGGER.info(
        "Exported %s data for %s in %s format",
        data_type,
        dog_id,
        export_format,
      )

      details = _normalise_service_details(
        {
          "data_type": data_type,
          "format": export_format,
          "days": days,
          "date_from": date_from,
          "date_to": date_to,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_EXPORT_DATA,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_EXPORT_DATA,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to export data for %s: %s", dog_id, err)
      _record_service_result(
        runtime_data,
        service=SERVICE_EXPORT_DATA,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise HomeAssistantError(
        f"Failed to export data for {dog_id}. Check the logs for details.",
      ) from err

  async def analyze_patterns_service(call: ServiceCall) -> None:
    """Handle analyze patterns service call."""
    coordinator = _get_coordinator()
    data_manager = _require_manager(
      _get_runtime_manager(coordinator, "data_manager"),
      "data manager",
    )

    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    analysis_type = call.data["analysis_type"]
    days = call.data.get("days", 30)

    try:
      await data_manager.async_analyze_patterns(
        dog_id=dog_id,
        analysis_type=analysis_type,
        days=days,
      )

      _LOGGER.info(
        "Analyzed %s patterns for %s over %d days",
        analysis_type,
        dog_id,
        days,
      )

      details = _normalise_service_details(
        {"analysis_type": analysis_type, "days": days},
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_ANALYZE_PATTERNS,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_ANALYZE_PATTERNS,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to analyze patterns for %s: %s", dog_id, err)
      _record_service_result(
        runtime_data,
        service=SERVICE_ANALYZE_PATTERNS,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise HomeAssistantError(
        f"Failed to analyze patterns for {dog_id}. Check the logs for details.",
      ) from err

  async def generate_report_service(call: ServiceCall) -> None:
    """Handle generate report service call."""
    coordinator = _get_coordinator()
    data_manager = _require_manager(
      _get_runtime_manager(coordinator, "data_manager"),
      "data manager",
    )

    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    report_type = call.data["report_type"]
    include_recommendations = call.data.get(
      "include_recommendations",
      True,
    )
    days = call.data.get("days", 30)

    try:
      await data_manager.async_generate_report(
        dog_id=dog_id,
        report_type=report_type,
        include_recommendations=include_recommendations,
        days=days,
      )

      _LOGGER.info(
        "Generated %s report for %s over %d days",
        report_type,
        dog_id,
        days,
      )

      details = _normalise_service_details(
        {
          "report_type": report_type,
          "include_recommendations": include_recommendations,
          "days": days,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GENERATE_REPORT,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_GENERATE_REPORT,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to generate report for %s: %s", dog_id, err)
      _record_service_result(
        runtime_data,
        service=SERVICE_GENERATE_REPORT,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise HomeAssistantError(
        f"Failed to generate report for {dog_id}. Check the logs for details.",
      ) from err

  async def daily_reset_service(call: ServiceCall) -> None:
    """Trigger a manual daily reset."""

    entry_id = call.data.get("entry_id")
    target_entry: ConfigEntry | None = None
    if entry_id:
      target_entry = hass.config_entries.async_get_entry(entry_id)

    if target_entry is None:
      entries = hass.config_entries.async_entries(DOMAIN)
      target_entry = entries[0] if entries else None

    if target_entry is None:
      _LOGGER.warning(
        "Daily reset requested but no PawControl entries are loaded",
      )
      return

    await _perform_daily_reset(hass, target_entry)

  # Automation service handlers
  async def recalculate_health_portions_service(call: ServiceCall) -> None:
    """Handle recalculate health portions service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )

    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    force_recalculation = call.data.get("force_recalculation", False)
    update_feeding_schedule = call.data.get(
      "update_feeding_schedule",
      True,
    )

    try:
      result = await feeding_manager.async_recalculate_health_portions(
        dog_id=dog_id,
        force_recalculation=force_recalculation,
        update_feeding_schedule=update_feeding_schedule,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Recalculated health portions for %s: %s",
        dog_id,
        result,
      )

      details = _normalise_service_details(result)
      _record_service_result(
        runtime_data,
        service=SERVICE_RECALCULATE_HEALTH_PORTIONS,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_RECALCULATE_HEALTH_PORTIONS,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to recalculate health portions for %s: %s",
        dog_id,
        err,
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_RECALCULATE_HEALTH_PORTIONS,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise HomeAssistantError(
        f"Failed to recalculate health portions for {dog_id}. Check the logs for details.",
      ) from err

  async def adjust_calories_for_activity_service(call: ServiceCall) -> None:
    """Handle adjust calories for activity service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )

    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    activity_level = call.data["activity_level"]
    duration_hours = call.data.get("duration_hours")
    temporary = call.data.get("temporary", True)

    try:
      await feeding_manager.async_adjust_calories_for_activity(
        dog_id=dog_id,
        activity_level=activity_level,
        duration_hours=duration_hours,
        temporary=temporary,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Adjusted calories for activity for %s: %s level for %sh (temporary: %s)",
        dog_id,
        activity_level,
        duration_hours or "unlimited",
        temporary,
      )

      details = _normalise_service_details(
        {
          "activity_level": activity_level,
          "duration_hours": duration_hours,
          "temporary": temporary,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_ADJUST_CALORIES_FOR_ACTIVITY,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_ADJUST_CALORIES_FOR_ACTIVITY,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to adjust calories for activity for %s: %s",
        dog_id,
        err,
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_ADJUST_CALORIES_FOR_ACTIVITY,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise HomeAssistantError(
        f"Failed to adjust calories for activity for {dog_id}. Check the logs for details.",
      ) from err

  async def activate_diabetic_feeding_mode_service(call: ServiceCall) -> None:
    """Handle activate diabetic feeding mode service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    meal_frequency = call.data.get("meal_frequency", 4)
    carb_limit_percent = call.data.get("carb_limit_percent", 20)
    monitor_blood_glucose = call.data.get("monitor_blood_glucose", True)

    try:
      await feeding_manager.async_activate_diabetic_feeding_mode(
        dog_id=dog_id,
        meal_frequency=meal_frequency,
        carb_limit_percent=carb_limit_percent,
        monitor_blood_glucose=monitor_blood_glucose,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Activated diabetic feeding mode for %s: %d meals/day, %d%% carb limit",
        dog_id,
        meal_frequency,
        carb_limit_percent,
      )

    except HomeAssistantError:
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to activate diabetic feeding mode for %s: %s",
        dog_id,
        err,
      )
      raise HomeAssistantError(
        f"Failed to activate diabetic feeding mode for {dog_id}. Check the logs for details.",
      ) from err

  async def feed_with_medication_service(call: ServiceCall) -> None:
    """Handle feed with medication service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    amount = call.data["amount"]
    medication_name = call.data["medication_name"]
    dose = call.data["dose"]
    meal_type = call.data.get("meal_type", "medication")
    notes = call.data.get("notes")
    administration_time = call.data.get(
      "administration_time",
      dt_util.utcnow(),
    )

    try:
      medication_data = {
        "name": medication_name,
        "dose": dose,
        "time": administration_time.isoformat(),
      }

      await feeding_manager.async_add_feeding_with_medication(
        dog_id=dog_id,
        amount=amount,
        meal_type=meal_type,
        medication_data=medication_data,
        notes=notes,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Fed %s with medication: %.1fg %s + %s %s",
        dog_id,
        amount,
        meal_type,
        medication_name,
        dose,
      )

    except HomeAssistantError:
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to feed with medication for %s: %s",
        dog_id,
        err,
      )
      raise HomeAssistantError(
        f"Failed to feed with medication for {dog_id}. Check the logs for details.",
      ) from err

  async def generate_weekly_health_report_service(call: ServiceCall) -> None:
    """Handle generate weekly health report service call."""
    coordinator = _get_coordinator()
    data_manager = _require_manager(
      _get_runtime_manager(coordinator, "data_manager"),
      "data manager",
    )

    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    include_recommendations = call.data.get(
      "include_recommendations",
      True,
    )
    include_charts = call.data.get("include_charts", True)
    report_format = call.data.get("format", "pdf")

    try:
      await data_manager.async_generate_weekly_health_report(
        dog_id=dog_id,
        include_recommendations=include_recommendations,
        include_charts=include_charts,
        format=report_format,
      )

      _LOGGER.info(
        "Generated weekly health report for %s in %s format",
        dog_id,
        report_format,
      )

      details = _normalise_service_details(
        {
          "format": report_format,
          "include_recommendations": include_recommendations,
          "include_charts": include_charts,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GENERATE_WEEKLY_HEALTH_REPORT,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_GENERATE_WEEKLY_HEALTH_REPORT,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to generate weekly health report for %s: %s",
        dog_id,
        err,
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_GENERATE_WEEKLY_HEALTH_REPORT,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise HomeAssistantError(
        f"Failed to generate weekly health report for {dog_id}. Check the logs for details.",
      ) from err

  async def activate_emergency_feeding_mode_service(call: ServiceCall) -> None:
    """Handle activate emergency feeding mode service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    emergency_type = call.data["emergency_type"]
    duration_days = call.data.get("duration_days", 3)
    portion_adjustment = call.data.get("portion_adjustment", 0.8)

    try:
      await feeding_manager.async_activate_emergency_feeding_mode(
        dog_id=dog_id,
        emergency_type=emergency_type,
        duration_days=duration_days,
        portion_adjustment=portion_adjustment,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Activated emergency feeding mode for %s: %s for %d days (%.1f%% portions)",
        dog_id,
        emergency_type,
        duration_days,
        portion_adjustment * 100,
      )

    except HomeAssistantError:
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to activate emergency feeding mode for %s: %s",
        dog_id,
        err,
      )
      raise HomeAssistantError(
        f"Failed to activate emergency feeding mode for {dog_id}. Check the logs for details.",
      ) from err

  async def start_diet_transition_service(call: ServiceCall) -> None:
    """Handle start diet transition service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    new_food_type = call.data["new_food_type"]
    transition_days = call.data.get("transition_days", 7)
    gradual_increase_percent = call.data.get(
      "gradual_increase_percent",
      25,
    )

    try:
      await feeding_manager.async_start_diet_transition(
        dog_id=dog_id,
        new_food_type=new_food_type,
        transition_days=transition_days,
        gradual_increase_percent=gradual_increase_percent,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Started diet transition for %s to %s over %d days",
        dog_id,
        new_food_type,
        transition_days,
      )

    except HomeAssistantError:
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to start diet transition for %s: %s",
        dog_id,
        err,
      )
      raise HomeAssistantError(
        f"Failed to start diet transition for {dog_id}. Check the logs for details.",
      ) from err

  async def check_feeding_compliance_service(call: ServiceCall) -> None:
    """Handle check feeding compliance service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )

    raw_dog_id = call.data["dog_id"]
    dog_id, dog_config = _resolve_dog(coordinator, raw_dog_id)
    days_to_check = call.data.get("days_to_check", 7)
    notify_on_issues = call.data.get("notify_on_issues", True)
    dog_name_value = dog_config.get("name")
    dog_name = (
      dog_name_value if isinstance(dog_name_value, str) and dog_name_value else None
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)
    context, context_metadata = _extract_service_context(call)
    notification_id: str | None = None
    request_metadata: ServiceDetailsPayload = {
      "days_to_check": days_to_check,
      "notify_on_issues": notify_on_issues,
    }
    _merge_service_context_metadata(
      request_metadata,
      context_metadata,
      include_none=True,
    )

    try:
      compliance_result = await feeding_manager.async_check_feeding_compliance(
        dog_id=dog_id,
        days_to_check=days_to_check,
        notify_on_issues=notify_on_issues,
      )

      notification_manager = _get_runtime_manager(
        coordinator,
        "notification_manager",
      )
      if notify_on_issues and notification_manager:
        notification_id = (
          await notification_manager.async_send_feeding_compliance_summary(
            dog_id=dog_id,
            dog_name=dog_name,
            compliance=compliance_result,
          )
        )

      compliance_payload = deepcopy(compliance_result)
      display_name = dog_name or dog_id
      language = getattr(getattr(hass, "config", None), "language", None)
      localized_summary: FeedingComplianceLocalizedSummary = (
        build_feeding_compliance_summary(
          language,
          display_name=display_name,
          compliance=compliance_payload,
        )
      )

      status = str(compliance_result.get("status"))

      sanitized_message = localized_summary.get("message")
      if sanitized_message and status != "completed":
        compliance_payload["message"] = sanitized_message

      event_payload: FeedingComplianceEventPayload = {
        "dog_id": dog_id,
        "dog_name": dog_name,
        "days_to_check": days_to_check,
        "notify_on_issues": notify_on_issues,
        "notification_sent": notification_id is not None,
        "result": compliance_payload,
        "localized_summary": localized_summary,
      }
      if notification_id is not None:
        event_payload["notification_id"] = notification_id
      _merge_service_context_metadata(
        cast(
          MutableMapping[str, JSONValue],
          event_payload,
        ),
        context_metadata,
      )

      await async_publish_feeding_compliance_issue(
        hass,
        coordinator.config_entry,
        event_payload,
        context_metadata=context_metadata,
      )

      await async_fire_event(
        hass,
        EVENT_FEEDING_COMPLIANCE_CHECKED,
        cast(JSONMutableMapping, event_payload),
        context=context,
        time_fired=dt_util.utcnow(),
      )
      details: ServiceDetailsPayload = {
        "status": status,
        "localized_summary": _coerce_service_details_value(
          dict(localized_summary),
        ),
      }
      if status == "completed":
        completed = cast(FeedingComplianceCompleted, compliance_result)
        details.update(
          {
            "score": completed["compliance_score"],
            "rate": completed["compliance_rate"],
            "days_analyzed": completed["days_analyzed"],
            "days_with_issues": completed["days_with_issues"],
            "issue_count": len(completed["compliance_issues"]),
            "missed_meal_count": len(completed["missed_meals"]),
          },
        )
      else:
        message: Any = compliance_payload.get("message")
        if not isinstance(message, str):
          message = localized_summary.get("message")
        if isinstance(message, str):
          details["message"] = message

      metadata: ServiceDetailsPayload = dict(request_metadata)
      metadata["notification_sent"] = notification_id is not None
      if notification_id is not None:
        metadata["notification_id"] = notification_id
      _merge_service_context_metadata(
        metadata,
        context_metadata,
        include_none=True,
      )

      _record_service_result(
        runtime_data,
        service=SERVICE_CHECK_FEEDING_COMPLIANCE,
        status="success",
        dog_id=dog_id,
        details=details,
        metadata=metadata,
      )

      _LOGGER.info(
        "Checked feeding compliance for %s over %d days: %s",
        dog_id,
        days_to_check,
        compliance_result,
      )

    except HomeAssistantError as err:
      error_metadata: ServiceDetailsPayload = dict(request_metadata)
      _record_service_result(
        runtime_data,
        service=SERVICE_CHECK_FEEDING_COMPLIANCE,
        status="error",
        dog_id=dog_id,
        message=str(err),
        metadata=error_metadata,
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to check feeding compliance for %s: %s",
        dog_id,
        err,
      )
      error_metadata = dict(request_metadata)
      _record_service_result(
        runtime_data,
        service=SERVICE_CHECK_FEEDING_COMPLIANCE,
        status="error",
        dog_id=dog_id,
        message=str(err),
        metadata=error_metadata,
      )
      raise HomeAssistantError(
        f"Failed to check feeding compliance for {dog_id}. Check the logs for details.",
      ) from err

  async def adjust_daily_portions_service(call: ServiceCall) -> None:
    """Handle adjust daily portions service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    adjustment_percent = call.data["adjustment_percent"]
    reason = call.data.get("reason")
    temporary = call.data.get("temporary", False)
    duration_days = call.data.get("duration_days")

    try:
      await feeding_manager.async_adjust_daily_portions(
        dog_id=dog_id,
        adjustment_percent=adjustment_percent,
        reason=reason,
        temporary=temporary,
        duration_days=duration_days,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Adjusted daily portions for %s by %+d%% (temporary: %s, reason: %s)",
        dog_id,
        adjustment_percent,
        temporary,
        reason or "unspecified",
      )

    except HomeAssistantError:
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to adjust daily portions for %s: %s",
        dog_id,
        err,
      )
      raise HomeAssistantError(
        f"Failed to adjust daily portions for {dog_id}. Check the logs for details.",
      ) from err

  async def add_health_snack_service(call: ServiceCall) -> None:
    """Handle add health snack service call."""
    coordinator = _get_coordinator()
    feeding_manager = _require_manager(
      _get_runtime_manager(
        coordinator,
        "feeding_manager",
      ),
      "feeding manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    snack_type = call.data["snack_type"]
    amount = call.data["amount"]
    health_benefit = call.data.get("health_benefit")
    notes = call.data.get("notes")

    try:
      await feeding_manager.async_add_health_snack(
        dog_id=dog_id,
        snack_type=snack_type,
        amount=amount,
        health_benefit=health_benefit,
        notes=notes,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Added health snack for %s: %.1fg %s (benefit: %s)",
        dog_id,
        amount,
        snack_type,
        health_benefit or "general",
      )

      details = _normalise_service_details(
        {
          "snack_type": snack_type,
          "amount": amount,
          "health_benefit": health_benefit,
          "notes": notes,
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_ADD_HEALTH_SNACK,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_ADD_HEALTH_SNACK,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to add health snack for %s: %s", dog_id, err)
      error_message = (
        f"Failed to add health snack for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_ADD_HEALTH_SNACK,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def log_poop_service(call: ServiceCall) -> None:
    """Handle log poop service call."""
    coordinator = _get_coordinator()
    data_manager = _require_manager(
      _get_runtime_manager(coordinator, "data_manager"),
      "data manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    poop_data = {k: v for k, v in call.data.items() if k != "dog_id" and v is not None}

    if "timestamp" not in poop_data:
      poop_data["timestamp"] = dt_util.utcnow()

    try:
      await data_manager.async_log_poop_data(dog_id=dog_id, poop_data=poop_data)
      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Logged poop data for %s: quality=%s, color=%s, size=%s",
        dog_id,
        poop_data.get("quality", "not_specified"),
        poop_data.get("color", "not_specified"),
        poop_data.get("size", "not_specified"),
      )

      timestamp = poop_data.get("timestamp")
      details = _normalise_service_details(
        {
          "quality": poop_data.get("quality"),
          "color": poop_data.get("color"),
          "size": poop_data.get("size"),
          "notes": poop_data.get("notes"),
          "timestamp": (
            dt_util.as_utc(timestamp).isoformat()
            if isinstance(timestamp, datetime)
            else timestamp
          ),
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_LOG_POOP,
        status="success",
        dog_id=dog_id,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_LOG_POOP,
        status="error",
        dog_id=dog_id,
        message=str(err),
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to log poop data for %s: %s", dog_id, err)
      error_message = (
        f"Failed to log poop data for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_LOG_POOP,
        status="error",
        dog_id=dog_id,
        message=error_message,
      )
      raise HomeAssistantError(error_message) from err

  async def start_grooming_service(call: ServiceCall) -> None:
    """Handle start grooming service call."""
    coordinator = _get_coordinator()
    data_manager = _require_manager(
      _get_runtime_manager(coordinator, "data_manager"),
      "data manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    grooming_type = call.data["grooming_type"]
    groomer = call.data.get("groomer")
    location = call.data.get("location")
    estimated_duration = call.data.get("estimated_duration_minutes")
    notes = call.data.get("notes")
    reminder_id = call.data.get("reminder_id")
    reminder_type = call.data.get("reminder_type")
    reminder_sent_at_input = call.data.get("reminder_sent_at")

    reminder_sent_at_iso: str | None = None
    if reminder_sent_at_input is not None:
      if isinstance(reminder_sent_at_input, datetime):
        reminder_sent_at_iso = dt_util.as_utc(
          reminder_sent_at_input,
        ).isoformat()
      else:
        parsed_dt = dt_util.parse_datetime(str(reminder_sent_at_input))
        if parsed_dt is not None:
          reminder_sent_at_iso = dt_util.as_utc(
            parsed_dt,
          ).isoformat()
        else:
          reminder_sent_at_iso = str(reminder_sent_at_input)

    reminder_metadata: ServiceDetailsPayload = {"reminder_attached": False}
    if any(
      value is not None for value in (reminder_id, reminder_type, reminder_sent_at_iso)
    ):
      reminder_metadata["reminder_attached"] = True
    if reminder_id is not None:
      reminder_metadata["reminder_id"] = reminder_id
    if reminder_type is not None:
      reminder_metadata["reminder_type"] = reminder_type
    if reminder_sent_at_iso is not None:
      reminder_metadata["reminder_sent_at"] = reminder_sent_at_iso

    guard_results: list[ServiceGuardResult] = []
    guard_snapshot: tuple[ServiceGuardResult, ...] = ()

    language_config = getattr(hass, "config", None)
    hass_language: str | None = None
    if language_config is not None:
      hass_language = getattr(language_config, "language", None)

    dog_label = coordinator.get_configured_dog_name(dog_id) or dog_id

    try:
      grooming_data = {
        "grooming_type": grooming_type,
        "groomer": groomer,
        "location": location,
        "estimated_duration_minutes": estimated_duration,
        "notes": notes,
        "start_time": dt_util.utcnow(),
        "status": "in_progress",
      }

      session_id = await data_manager.async_start_grooming_session(
        dog_id=dog_id,
        grooming_data=grooming_data,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Started grooming session for %s: %s (session: %s, groomer: %s)",
        dog_id,
        grooming_type,
        session_id,
        groomer or "unknown",
      )

      # Send notification about grooming start
      notification_manager = _get_runtime_manager(
        coordinator,
        "notification_manager",
      )
      if notification_manager:
        async with async_capture_service_guard_results() as captured_guards:
          guard_results = captured_guards
          title = translated_grooming_template(
            hass_language,
            "notification_title",
            dog_label=dog_label,
          )
          message_parts = [
            translated_grooming_template(
              hass_language,
              "notification_message",
              grooming_type=grooming_type,
              dog_label=dog_label,
            ),
          ]
          if groomer:
            message_parts.append(
              translated_grooming_template(
                hass_language,
                "notification_with_groomer",
                groomer=groomer,
              ),
            )
          if estimated_duration:
            message_parts.append(
              translated_grooming_template(
                hass_language,
                "notification_estimated_duration",
                minutes=estimated_duration,
              ),
            )
          await notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title=title,
            message=" ".join(part for part in message_parts if part),
            dog_id=dog_id,
          )
        guard_snapshot = tuple(guard_results)

      details_payload: ServiceDetailsPayload = {
        "session_id": session_id,
        "grooming_type": grooming_type,
        "groomer": groomer,
        "location": location,
        "estimated_duration_minutes": estimated_duration,
        "notes": notes,
        "reminder_attached": reminder_metadata["reminder_attached"],
      }
      if reminder_metadata["reminder_attached"]:
        reminder_details: ServiceDetailsPayload = {}
        if reminder_id is not None:
          reminder_details["id"] = reminder_id
        if reminder_type is not None:
          reminder_details["type"] = reminder_type
        if reminder_sent_at_iso is not None:
          reminder_details["sent_at"] = reminder_sent_at_iso
        if reminder_details:
          details_payload["reminder"] = reminder_details

      details = _normalise_service_details(details_payload)
      _record_service_result(
        runtime_data,
        service=SERVICE_START_GROOMING,
        status="success",
        dog_id=dog_id,
        metadata=reminder_metadata,
        details=details,
        guard=guard_snapshot if guard_snapshot else None,
      )

    except HomeAssistantError as err:
      guard_snapshot = tuple(guard_results)
      _record_service_result(
        runtime_data,
        service=SERVICE_START_GROOMING,
        status="error",
        dog_id=dog_id,
        message=str(err),
        metadata=reminder_metadata,
        guard=guard_snapshot if guard_snapshot else None,
      )
      raise
    except Exception as err:
      _LOGGER.error("Failed to start grooming for %s: %s", dog_id, err)
      error_message = translated_grooming_template(
        hass_language,
        "start_failure",
        dog_label=dog_label,
      )
      guard_snapshot = tuple(guard_results)
      _record_service_result(
        runtime_data,
        service=SERVICE_START_GROOMING,
        status="error",
        dog_id=dog_id,
        message=error_message,
        metadata=reminder_metadata,
        guard=guard_snapshot if guard_snapshot else None,
      )
      raise HomeAssistantError(error_message) from err

  # NEW: Garden tracking service handlers
  async def start_garden_session_service(call: ServiceCall) -> None:
    """Handle start garden session service call."""
    coordinator = _get_coordinator()
    garden_manager = _require_manager(
      getattr(coordinator, "garden_manager", None),
      "garden manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _dog_config = _resolve_dog(coordinator, raw_dog_id)
    detection_method = call.data.get("detection_method", "manual")
    weather_conditions = call.data.get("weather_conditions")
    temperature = call.data.get("temperature")
    dog_name = coordinator.get_configured_dog_name(dog_id) or dog_id
    automation_fallback = bool(call.data.get("automation_fallback", False))
    fallback_reason = call.data.get("fallback_reason")
    automation_source = call.data.get("automation_source")

    fallback_metadata: ServiceDetailsPayload = {
      "automation_fallback": automation_fallback,
    }
    if fallback_reason:
      fallback_metadata["fallback_reason"] = fallback_reason
    if automation_source:
      fallback_metadata["automation_source"] = automation_source

    try:
      session_id = await garden_manager.async_start_garden_session(
        dog_id=dog_id,
        dog_name=dog_name,
        detection_method=detection_method,
        weather_conditions=weather_conditions,
        temperature=temperature,
      )

      await coordinator.async_request_refresh()

      _LOGGER.info(
        "Started garden session for %s (session: %s, method: %s)",
        dog_name,
        session_id,
        detection_method,
      )

      if automation_fallback:
        _LOGGER.warning(
          "Garden automation fallback engaged for %s via %s%s",
          dog_name,
          automation_source or detection_method,
          f": {fallback_reason}" if fallback_reason else "",
        )

      details = _normalise_service_details(
        {
          "session_id": session_id,
          "detection_method": detection_method,
          "weather_conditions": weather_conditions,
          "temperature": temperature,
          "automation_fallback": automation_fallback,
          **({"fallback_reason": fallback_reason} if fallback_reason else {}),
          **({"automation_source": automation_source} if automation_source else {}),
        },
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_START_GARDEN,
        status="success",
        dog_id=dog_id,
        metadata=fallback_metadata,
        details=details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_START_GARDEN,
        status="error",
        dog_id=dog_id,
        message=str(err),
        metadata=fallback_metadata,
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to start garden session for %s: %s",
        dog_id,
        err,
      )
      error_message = (
        f"Failed to start garden session for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_START_GARDEN,
        status="error",
        dog_id=dog_id,
        message=error_message,
        metadata=fallback_metadata,
      )
      raise HomeAssistantError(error_message) from err

  async def end_garden_session_service(call: ServiceCall) -> None:
    """Handle end garden session service call."""
    coordinator = _get_coordinator()
    garden_manager = _require_manager(
      getattr(coordinator, "garden_manager", None),
      "garden manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    notes = call.data.get("notes")
    activities = call.data.get("activities")

    failure_details: ServiceDetailsPayload | None = None

    try:
      session = await garden_manager.async_end_garden_session(
        dog_id=dog_id,
        notes=notes,
        activities=activities,
      )

      if session:
        await coordinator.async_request_refresh()

        _LOGGER.info(
          "Ended garden session for %s: %.1f minutes, %d activities, %d poop events",
          session.dog_name,
          session.duration_minutes,
          len(session.activities),
          session.poop_count,
        )

        details = _normalise_service_details(
          {
            "duration_minutes": getattr(session, "duration_minutes", None),
            "activity_count": len(getattr(session, "activities", [])),
            "poop_count": getattr(session, "poop_count", None),
            "notes": notes,
          },
        )
        _record_service_result(
          runtime_data,
          service=SERVICE_END_GARDEN,
          status="success",
          dog_id=dog_id,
          details=details,
        )
      else:
        error_message = f"No active garden session is currently running for {dog_id}."
        failure_payload: ServiceDetailsPayload = {}
        if notes is not None:
          failure_payload["notes"] = notes
        if activities is not None:
          failure_payload["activities"] = activities
        failure_details = (
          _normalise_service_details(failure_payload) if failure_payload else None
        )
        _record_service_result(
          runtime_data,
          service=SERVICE_END_GARDEN,
          status="error",
          dog_id=dog_id,
          message=error_message,
          details=failure_details,
        )
        raise _service_validation_error(error_message)

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_END_GARDEN,
        status="error",
        dog_id=dog_id,
        message=str(err),
        details=failure_details,
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to end garden session for %s: %s",
        dog_id,
        err,
      )
      error_message = (
        f"Failed to end garden session for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_END_GARDEN,
        status="error",
        dog_id=dog_id,
        message=error_message,
        details=failure_details,
      )
      raise HomeAssistantError(error_message) from err

  async def add_garden_activity_service(call: ServiceCall) -> None:
    """Handle add garden activity service call."""
    coordinator = _get_coordinator()
    garden_manager = _require_manager(
      getattr(coordinator, "garden_manager", None),
      "garden manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    activity_type = call.data["activity_type"]
    duration_seconds = call.data.get("duration_seconds")
    location = call.data.get("location")
    notes = call.data.get("notes")
    confirmed = call.data.get("confirmed", True)

    details_payload: ServiceDetailsPayload = {
      "activity_type": activity_type,
      "confirmed": confirmed,
    }
    if duration_seconds is not None:
      details_payload["duration_seconds"] = duration_seconds
    if location is not None:
      details_payload["location"] = location
    if notes is not None:
      details_payload["notes"] = notes

    request_details = _normalise_service_details(details_payload)

    try:
      success = await garden_manager.async_add_activity(
        dog_id=dog_id,
        activity_type=activity_type,
        duration_seconds=duration_seconds,
        location=location,
        notes=notes,
        confirmed=confirmed,
      )

      if success:
        _LOGGER.info(
          "Added garden activity for %s: %s (location: %s)",
          dog_id,
          activity_type,
          location or "unspecified",
        )

        _record_service_result(
          runtime_data,
          service=SERVICE_ADD_GARDEN_ACTIVITY,
          status="success",
          dog_id=dog_id,
          details=request_details,
        )
      else:
        error_message = (
          f"No active garden session is currently running for {dog_id}. "
          "Start a garden session before adding activities."
        )
        _record_service_result(
          runtime_data,
          service=SERVICE_ADD_GARDEN_ACTIVITY,
          status="error",
          dog_id=dog_id,
          message=error_message,
          details=request_details,
        )
        raise _service_validation_error(error_message)

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_ADD_GARDEN_ACTIVITY,
        status="error",
        dog_id=dog_id,
        message=str(err),
        details=request_details,
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to add garden activity for %s: %s",
        dog_id,
        err,
      )
      error_message = (
        f"Failed to add garden activity for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_ADD_GARDEN_ACTIVITY,
        status="error",
        dog_id=dog_id,
        message=error_message,
        details=request_details,
      )
      raise HomeAssistantError(error_message) from err

  async def confirm_garden_poop_service(call: ServiceCall) -> None:
    """Handle confirm garden poop service call."""
    coordinator = _get_coordinator()
    garden_manager = _require_manager(
      getattr(coordinator, "garden_manager", None),
      "garden manager",
    )
    runtime_data = _get_runtime_data_for_coordinator(coordinator)

    raw_dog_id = call.data["dog_id"]
    dog_id, _ = _resolve_dog(coordinator, raw_dog_id)
    confirmed = call.data["confirmed"]
    quality = call.data.get("quality")
    size = call.data.get("size")
    location = call.data.get("location")

    details_payload: ServiceDetailsPayload = {"confirmed": confirmed}
    if quality is not None:
      details_payload["quality"] = quality
    if size is not None:
      details_payload["size"] = size
    if location is not None:
      details_payload["location"] = location

    request_details = _normalise_service_details(details_payload)

    if not garden_manager.has_pending_confirmation(dog_id):
      error_message = (
        f"No pending garden poop confirmation found for {dog_id}. "
        "Start a garden session and wait for detection first."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_CONFIRM_POOP,
        status="error",
        dog_id=dog_id,
        message=error_message,
        details=request_details,
      )
      raise _service_validation_error(error_message)

    try:
      await garden_manager.async_handle_poop_confirmation(
        dog_id=dog_id,
        confirmed=confirmed,
        quality=quality,
        size=size,
        location=location,
      )

      _LOGGER.info(
        "Processed poop confirmation for %s: %s (quality: %s, size: %s)",
        dog_id,
        "confirmed" if confirmed else "denied",
        quality or "not_specified",
        size or "not_specified",
      )

      _record_service_result(
        runtime_data,
        service=SERVICE_CONFIRM_POOP,
        status="success",
        dog_id=dog_id,
        details=request_details,
      )

    except HomeAssistantError as err:
      _record_service_result(
        runtime_data,
        service=SERVICE_CONFIRM_POOP,
        status="error",
        dog_id=dog_id,
        message=str(err),
        details=request_details,
      )
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to confirm garden poop for %s: %s",
        dog_id,
        err,
      )
      error_message = (
        f"Failed to confirm garden poop for {dog_id}. Check the logs for details."
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_CONFIRM_POOP,
        status="error",
        dog_id=dog_id,
        message=error_message,
        details=request_details,
      )
      raise HomeAssistantError(error_message) from err

  # NEW: Weather service handlers
  async def update_weather_service(call: ServiceCall) -> None:
    """Handle update weather service call."""
    coordinator = _get_coordinator()
    weather_manager = _require_manager(
      _get_runtime_manager(coordinator, "weather_health_manager"),
      "weather health manager",
    )

    weather_entity_id = call.data.get("weather_entity_id")
    call.data.get("force_update", False)

    try:
      # Update weather data
      weather_conditions = await weather_manager.async_update_weather_data(
        weather_entity_id,
      )

      if weather_conditions and weather_conditions.is_valid:
        await coordinator.async_request_refresh()

        _LOGGER.info(
          "Updated weather data: %.1f°C, %s, health score: %d",
          weather_conditions.temperature_c or 0,
          weather_conditions.condition or "unknown",
          weather_manager.get_weather_health_score(),
        )

        # Send notification about weather update if there are alerts
        active_alerts = weather_manager.get_active_alerts()
        notification_manager = _get_runtime_manager(
          coordinator,
          "notification_manager",
        )
        if active_alerts and notification_manager:
          high_severity_alerts = [
            alert
            for alert in active_alerts
            if alert.severity.value in ["high", "extreme"]
          ]

          if high_severity_alerts:
            alert = high_severity_alerts[0]  # Most severe
            await notification_manager.async_send_notification(
              notification_type=NotificationType.HEALTH_ALERT,
              title=f"🌡️ Weather Alert: {alert.title}",
              message=alert.message,
              priority=(
                NotificationPriority.HIGH
                if alert.severity.value == "extreme"
                else NotificationPriority.NORMAL
              ),
            )
      else:
        _LOGGER.warning(
          "Weather update failed or returned invalid data",
        )

    except HomeAssistantError:
      raise
    except Exception as err:
      _LOGGER.error("Failed to update weather data: %s", err)
      raise HomeAssistantError(
        "Failed to update weather data. Check the logs for details.",
      ) from err

  async def get_weather_alerts_service(call: ServiceCall) -> None:
    """Handle get weather alerts service call."""
    coordinator = _get_coordinator()
    weather_manager = _require_manager(
      _get_runtime_manager(coordinator, "weather_health_manager"),
      "weather health manager",
    )

    dog_id = call.data.get("dog_id")
    severity_filter = call.data.get("severity_filter")
    impact_filter = call.data.get("impact_filter")

    try:
      from .weather_manager import WeatherHealthImpact, WeatherSeverity

      # Convert string filters to enums
      severity_enum = None
      if severity_filter:
        severity_enum = WeatherSeverity(severity_filter)

      impact_enum = None
      if impact_filter:
        impact_enum = WeatherHealthImpact(impact_filter)

      # Get filtered alerts
      alerts = weather_manager.get_active_alerts(
        severity_filter=severity_enum,
        impact_filter=impact_enum,
      )

      _LOGGER.info(
        "Retrieved %d weather alerts (severity: %s, impact: %s)",
        len(alerts),
        severity_filter or "all",
        impact_filter or "all",
      )

      # Send notification with alert summary if requested for specific dog
      notification_manager = _get_runtime_manager(
        coordinator,
        "notification_manager",
      )
      if dog_id and alerts and notification_manager:
        alert_summary = f"Found {len(alerts)} weather alerts:\n"
        for alert in alerts[:3]:  # Limit to 3 for notification
          alert_summary += f"• {alert.title}\n"

        await notification_manager.async_send_notification(
          notification_type=NotificationType.SYSTEM_INFO,
          title=f"🌤️ Weather Alerts for {dog_id}",
          message=alert_summary.strip(),
          dog_id=dog_id,
        )

    except HomeAssistantError:
      raise
    except Exception as err:
      _LOGGER.error("Failed to get weather alerts: %s", err)
      raise HomeAssistantError(
        "Failed to get weather alerts. Check the logs for details.",
      ) from err

  async def get_weather_recommendations_service(call: ServiceCall) -> None:
    """Handle get weather recommendations service call."""
    coordinator = _get_coordinator()
    weather_manager = _require_manager(
      _get_runtime_manager(coordinator, "weather_health_manager"),
      "weather health manager",
    )

    raw_dog_id = call.data["dog_id"]
    dog_id, dog_config = _resolve_dog(coordinator, raw_dog_id)
    include_breed_specific = call.data.get("include_breed_specific", True)
    include_health_conditions = call.data.get(
      "include_health_conditions",
      True,
    )
    max_recommendations = call.data.get("max_recommendations", 5)

    try:
      # Get recommendations
      dog_breed = (
        dog_config.get(
          "breed",
        )
        if include_breed_specific
        else None
      )
      dog_age_months = dog_config.get("age_months")
      health_conditions = (
        dog_config.get("health_conditions", []) if include_health_conditions else None
      )

      recommendations = weather_manager.get_recommendations_for_dog(
        dog_breed=dog_breed,
        dog_age_months=dog_age_months,
        health_conditions=health_conditions,
      )

      # Limit recommendations
      recommendations = recommendations[:max_recommendations]

      _LOGGER.info(
        "Generated %d weather recommendations for %s",
        len(recommendations),
        dog_id,
      )

      # Send notification with recommendations
      notification_manager = _get_runtime_manager(
        coordinator,
        "notification_manager",
      )
      if recommendations and notification_manager:
        rec_message = f"Weather recommendations for {dog_id}:\n"
        for i, rec in enumerate(
          recommendations[:3],
          1,
        ):  # Limit to 3 for notification
          rec_message += f"{i}. {rec}\n"

        await notification_manager.async_send_notification(
          notification_type=NotificationType.SYSTEM_INFO,
          title=f"🐕 Weather Tips: {dog_id}",
          message=rec_message.strip(),
          dog_id=dog_id,
        )

    except HomeAssistantError:
      raise
    except Exception as err:
      _LOGGER.error(
        "Failed to get weather recommendations for %s: %s",
        dog_id,
        err,
      )
      raise HomeAssistantError(
        f"Failed to get weather recommendations for {dog_id}. Check the logs for details.",
      ) from err

  # Register all services
  _register_service(
    SERVICE_ADD_FEEDING,
    add_feeding_service,
    schema=SERVICE_ADD_FEEDING_SCHEMA,
  )

  # Register feed_dog as alias for backward compatibility
  _register_service(
    SERVICE_FEED_DOG,
    feed_dog_service,
    schema=SERVICE_FEED_DOG_SCHEMA,
  )

  _register_service(
    SERVICE_START_WALK,
    start_walk_service,
    schema=SERVICE_START_WALK_SCHEMA,
  )

  _register_service(
    SERVICE_END_WALK,
    end_walk_service,
    schema=SERVICE_END_WALK_SCHEMA,
  )

  _register_service(
    SERVICE_ADD_GPS_POINT,
    add_gps_point_service,
    schema=SERVICE_ADD_GPS_POINT_SCHEMA,
  )

  _register_service(
    SERVICE_UPDATE_HEALTH,
    update_health_service,
    schema=SERVICE_UPDATE_HEALTH_SCHEMA,
  )

  # Register new health and medication services
  _register_service(
    SERVICE_LOG_HEALTH,
    log_health_service,
    schema=SERVICE_LOG_HEALTH_SCHEMA,
  )

  _register_service(
    SERVICE_LOG_MEDICATION,
    log_medication_service,
    schema=SERVICE_LOG_MEDICATION_SCHEMA,
  )

  _register_service(
    SERVICE_TOGGLE_VISITOR_MODE,
    toggle_visitor_mode_service,
    schema=SERVICE_TOGGLE_VISITOR_MODE_SCHEMA,
  )

  # Register GPS services
  _register_service(
    SERVICE_GPS_START_WALK,
    gps_start_walk_service,
    schema=SERVICE_GPS_START_WALK_SCHEMA,
  )

  _register_service(
    SERVICE_GPS_END_WALK,
    gps_end_walk_service,
    schema=SERVICE_GPS_END_WALK_SCHEMA,
  )

  _register_service(
    SERVICE_GPS_POST_LOCATION,
    gps_post_location_service,
    schema=SERVICE_GPS_POST_LOCATION_SCHEMA,
  )

  _register_service(
    SERVICE_GPS_EXPORT_ROUTE,
    gps_export_route_service,
    schema=SERVICE_GPS_EXPORT_ROUTE_SCHEMA,
  )

  # NEW: Register the missing setup_automatic_gps service
  _register_service(
    SERVICE_SETUP_AUTOMATIC_GPS,
    setup_automatic_gps_service,
    schema=SERVICE_SETUP_AUTOMATIC_GPS_SCHEMA,
  )

  _register_service(
    SERVICE_SEND_NOTIFICATION,
    send_notification_service,
    schema=SERVICE_SEND_NOTIFICATION_SCHEMA,
  )

  _register_service(
    SERVICE_ACKNOWLEDGE_NOTIFICATION,
    acknowledge_notification_service,
    schema=SERVICE_ACKNOWLEDGE_NOTIFICATION_SCHEMA,
  )

  _register_service(
    SERVICE_CALCULATE_PORTION,
    calculate_portion_service,
    schema=SERVICE_CALCULATE_PORTION_SCHEMA,
  )

  _register_service(
    SERVICE_EXPORT_DATA,
    export_data_service,
    schema=SERVICE_EXPORT_DATA_SCHEMA,
  )

  _register_service(
    SERVICE_ANALYZE_PATTERNS,
    analyze_patterns_service,
    schema=SERVICE_ANALYZE_PATTERNS_SCHEMA,
  )

  _register_service(
    SERVICE_GENERATE_REPORT,
    generate_report_service,
    schema=SERVICE_GENERATE_REPORT_SCHEMA,
  )

  _register_service(
    SERVICE_DAILY_RESET,
    daily_reset_service,
    schema=SERVICE_DAILY_RESET_SCHEMA,
  )

  # Register automation services
  _register_service(
    SERVICE_RECALCULATE_HEALTH_PORTIONS,
    recalculate_health_portions_service,
    schema=SERVICE_RECALCULATE_HEALTH_PORTIONS_SCHEMA,
  )

  _register_service(
    SERVICE_ADJUST_CALORIES_FOR_ACTIVITY,
    adjust_calories_for_activity_service,
    schema=SERVICE_ADJUST_CALORIES_FOR_ACTIVITY_SCHEMA,
  )

  _register_service(
    SERVICE_ACTIVATE_DIABETIC_FEEDING_MODE,
    activate_diabetic_feeding_mode_service,
    schema=SERVICE_ACTIVATE_DIABETIC_FEEDING_MODE_SCHEMA,
  )

  _register_service(
    SERVICE_FEED_WITH_MEDICATION,
    feed_with_medication_service,
    schema=SERVICE_FEED_WITH_MEDICATION_SCHEMA,
  )

  _register_service(
    SERVICE_GENERATE_WEEKLY_HEALTH_REPORT,
    generate_weekly_health_report_service,
    schema=SERVICE_GENERATE_WEEKLY_HEALTH_REPORT_SCHEMA,
  )

  _register_service(
    SERVICE_ACTIVATE_EMERGENCY_FEEDING_MODE,
    activate_emergency_feeding_mode_service,
    schema=SERVICE_ACTIVATE_EMERGENCY_FEEDING_MODE_SCHEMA,
  )

  _register_service(
    SERVICE_START_DIET_TRANSITION,
    start_diet_transition_service,
    schema=SERVICE_START_DIET_TRANSITION_SCHEMA,
  )

  _register_service(
    SERVICE_CHECK_FEEDING_COMPLIANCE,
    check_feeding_compliance_service,
    schema=SERVICE_CHECK_FEEDING_COMPLIANCE_SCHEMA,
  )

  _register_service(
    SERVICE_ADJUST_DAILY_PORTIONS,
    adjust_daily_portions_service,
    schema=SERVICE_ADJUST_DAILY_PORTIONS_SCHEMA,
  )

  _register_service(
    SERVICE_ADD_HEALTH_SNACK,
    add_health_snack_service,
    schema=SERVICE_ADD_HEALTH_SNACK_SCHEMA,
  )

  # Register missing services
  _register_service(
    SERVICE_LOG_POOP,
    log_poop_service,
    schema=SERVICE_LOG_POOP_SCHEMA,
  )

  _register_service(
    SERVICE_START_GROOMING,
    start_grooming_service,
    schema=SERVICE_START_GROOMING_SCHEMA,
  )

  # NEW: Register garden tracking services
  _register_service(
    SERVICE_START_GARDEN,
    start_garden_session_service,
    schema=SERVICE_START_GARDEN_SCHEMA,
  )

  _register_service(
    SERVICE_END_GARDEN,
    end_garden_session_service,
    schema=SERVICE_END_GARDEN_SCHEMA,
  )

  _register_service(
    SERVICE_ADD_GARDEN_ACTIVITY,
    add_garden_activity_service,
    schema=SERVICE_ADD_GARDEN_ACTIVITY_SCHEMA,
  )

  _register_service(
    SERVICE_CONFIRM_POOP,
    confirm_garden_poop_service,
    schema=SERVICE_CONFIRM_POOP_SCHEMA,
  )

  # NEW: Register weather services
  _register_service(
    SERVICE_UPDATE_WEATHER,
    update_weather_service,
    schema=SERVICE_UPDATE_WEATHER_SCHEMA,
  )

  _register_service(
    SERVICE_GET_WEATHER_ALERTS,
    get_weather_alerts_service,
    schema=SERVICE_GET_WEATHER_ALERTS_SCHEMA,
  )

  _register_service(
    SERVICE_GET_WEATHER_RECOMMENDATIONS,
    get_weather_recommendations_service,
    schema=SERVICE_GET_WEATHER_RECOMMENDATIONS_SCHEMA,
  )

  _LOGGER.debug(
    "Registered PawControl services with enhanced automation, GPS setup, garden tracking, and weather health functionality",
  )


async def async_unload_services(hass: HomeAssistant) -> None:
  """Unload PawControl services.

  Args:
      hass: Home Assistant instance
  """
  services_to_remove = [
    SERVICE_ADD_FEEDING,
    SERVICE_FEED_DOG,
    SERVICE_START_WALK,
    SERVICE_END_WALK,
    SERVICE_ADD_GPS_POINT,
    SERVICE_UPDATE_HEALTH,
    SERVICE_LOG_HEALTH,
    SERVICE_LOG_MEDICATION,
    SERVICE_LOG_POOP,
    SERVICE_START_GROOMING,
    SERVICE_TOGGLE_VISITOR_MODE,
    SERVICE_GPS_START_WALK,
    SERVICE_GPS_END_WALK,
    SERVICE_GPS_POST_LOCATION,
    SERVICE_GPS_EXPORT_ROUTE,
    SERVICE_SETUP_AUTOMATIC_GPS,  # NEW: Include the new service
    SERVICE_SEND_NOTIFICATION,
    SERVICE_ACKNOWLEDGE_NOTIFICATION,
    SERVICE_CALCULATE_PORTION,
    SERVICE_EXPORT_DATA,
    SERVICE_ANALYZE_PATTERNS,
    SERVICE_GENERATE_REPORT,
    SERVICE_DAILY_RESET,
    # Automation services
    SERVICE_RECALCULATE_HEALTH_PORTIONS,
    SERVICE_ADJUST_CALORIES_FOR_ACTIVITY,
    SERVICE_ACTIVATE_DIABETIC_FEEDING_MODE,
    SERVICE_FEED_WITH_MEDICATION,
    SERVICE_GENERATE_WEEKLY_HEALTH_REPORT,
    SERVICE_ACTIVATE_EMERGENCY_FEEDING_MODE,
    SERVICE_START_DIET_TRANSITION,
    SERVICE_CHECK_FEEDING_COMPLIANCE,
    SERVICE_ADJUST_DAILY_PORTIONS,
    SERVICE_ADD_HEALTH_SNACK,
    # NEW: Garden tracking services
    SERVICE_START_GARDEN,
    SERVICE_END_GARDEN,
    SERVICE_ADD_GARDEN_ACTIVITY,
    SERVICE_CONFIRM_POOP,
    # NEW: Weather services
    SERVICE_UPDATE_WEATHER,
    SERVICE_GET_WEATHER_ALERTS,
    SERVICE_GET_WEATHER_RECOMMENDATIONS,
  ]

  for service in services_to_remove:
    hass.services.async_remove(DOMAIN, service)

  domain_data = hass.data.get(DOMAIN)
  if isinstance(domain_data, dict):
    listener = domain_data.pop("_service_coordinator_listener", None)
    if callable(listener):
      try:
        listener()
      except Exception as err:  # pragma: no cover - defensive cleanup
        _LOGGER.debug(
          "Failed to remove coordinator change listener during unload: %s",
          err,
        )

    resolver = domain_data.pop("_service_coordinator_resolver", None)
    if isinstance(resolver, _CoordinatorResolver):
      resolver.invalidate()

  _LOGGER.info("Unloaded PawControl services")


class PawControlServiceManager:
  """Manage registration of PawControl services."""

  def __init__(self, hass: HomeAssistant) -> None:
    """Initialize the service manager and register services when needed."""

    self._hass = hass
    self._services_task: asyncio.Task | None = None

    domain_data = hass.data.setdefault(DOMAIN, {})
    existing: PawControlServiceManager | None = domain_data.get(
      "service_manager",
    )
    if existing is not None:
      self._services_task = existing._services_task
      return

    domain_data["service_manager"] = self

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_FEEDING):
      self._services_task = hass.async_create_task(
        async_setup_services(hass),
      )

  async def async_shutdown(self) -> None:
    """Unload registered services when the integration is removed."""

    if self._services_task and not self._services_task.done():
      with suppress(asyncio.CancelledError):
        await self._services_task

    await async_unload_services(self._hass)

    domain_data = self._hass.data.get(DOMAIN)
    if domain_data and domain_data.get("service_manager") is self:
      domain_data.pop("service_manager")


async def _perform_daily_reset(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Perform maintenance tasks for the daily reset."""

  runtime_data = get_runtime_data(hass, entry)
  if runtime_data is None:
    _LOGGER.debug(
      "Skipping daily reset for entry %s: runtime data unavailable",
      entry.entry_id,
    )
    return

  coordinator = runtime_data.coordinator
  walk_manager = getattr(runtime_data, "walk_manager", None)
  notification_manager = getattr(runtime_data, "notification_manager", None)

  diagnostics: CacheDiagnosticsCapture | None = None
  walk_cleanup_performed = False
  notification_cleanup_count: int | None = None
  refresh_requested = False
  reconfigure_summary = update_runtime_reconfigure_summary(runtime_data)

  performance_stats = ensure_runtime_performance_stats(runtime_data)

  with performance_tracker(
    runtime_data,
    "daily_reset_metrics",
    max_samples=20,
  ) as perf:
    try:
      if walk_manager and hasattr(walk_manager, "async_cleanup"):
        await walk_manager.async_cleanup()
        walk_cleanup_performed = True

      if notification_manager and hasattr(
        notification_manager,
        "async_cleanup_expired_notifications",
      ):
        notification_cleanup_count = (
          await notification_manager.async_cleanup_expired_notifications()
        )

      await coordinator.async_request_refresh()
      refresh_requested = True

      diagnostics = _capture_cache_diagnostics(runtime_data)
      if diagnostics is not None:
        performance_stats["last_cache_diagnostics"] = diagnostics

      performance_stats.setdefault("daily_resets", 0)
      performance_stats["daily_resets"] = (
        int(performance_stats.get("daily_resets", 0) or 0) + 1
      )
      success_metadata: ServiceDetailsPayload = {
        "refresh_requested": refresh_requested,
      }
      if reconfigure_summary is not None:
        success_metadata["reconfigure"] = _coerce_service_details_value(
          reconfigure_summary,
        )
      service_details_payload: ServiceDetailsPayload = {
        key: value
        for key, value in {
          "walk_cleanup_performed": walk_cleanup_performed,
          "notifications_cleaned": notification_cleanup_count,
          "cache_snapshot": diagnostics is not None,
        }.items()
        if value is not None
      }
      _record_service_result(
        runtime_data,
        service=SERVICE_DAILY_RESET,
        status="success",
        diagnostics=diagnostics,
        metadata=success_metadata,
        details=(service_details_payload if service_details_payload else None),
      )
      record_maintenance_result(
        runtime_data,
        task="daily_reset",
        status="success",
        diagnostics=diagnostics,
        metadata=success_metadata,
        details=service_details_payload,
      )
      _LOGGER.debug("Daily reset completed for entry %s", entry.entry_id)
    except Exception as err:  # pragma: no cover - defensive logging
      perf.mark_failure(err)
      failure_metadata: ServiceDetailsPayload = {
        "refresh_requested": refresh_requested,
      }
      if reconfigure_summary is not None:
        failure_metadata["reconfigure"] = _coerce_service_details_value(
          reconfigure_summary,
        )
      failure_details: ServiceDetailsPayload = {
        key: value
        for key, value in {
          "walk_cleanup_performed": walk_cleanup_performed,
          "notifications_cleaned": notification_cleanup_count,
          "cache_snapshot": diagnostics is not None,
        }.items()
        if value is not None
      }
      record_maintenance_result(
        runtime_data,
        task="daily_reset",
        status="error",
        message=str(err),
        diagnostics=diagnostics,
        metadata=failure_metadata,
        details=failure_details,
      )
      _record_service_result(
        runtime_data,
        service=SERVICE_DAILY_RESET,
        status="error",
        message=str(err),
        metadata=failure_metadata,
        details=failure_details if failure_details else None,
      )
      _LOGGER.error(
        "Daily reset failed for entry %s: %s",
        entry.entry_id,
        err,
      )
      raise


async def async_setup_daily_reset_scheduler(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> Callable[[], None] | None:
  """Schedule the daily reset based on the configured reset time."""

  reset_time_str = entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)
  reset_time = dt_util.parse_time(reset_time_str)
  if reset_time is None:
    _LOGGER.warning(
      "Invalid reset time '%s', falling back to default '%s'",
      reset_time_str,
      DEFAULT_RESET_TIME,
    )
    reset_time = dt_util.parse_time(DEFAULT_RESET_TIME)

  if reset_time is None:
    return None

  runtime_data = get_runtime_data(hass, entry)
  if runtime_data and runtime_data.daily_reset_unsub:
    try:
      runtime_data.daily_reset_unsub()
    except Exception as err:  # pragma: no cover - best effort cleanup
      _LOGGER.debug(
        "Failed to cancel previous daily reset listener: %s",
        err,
      )

  async def _async_run_reset() -> None:
    await _perform_daily_reset(hass, entry)

  @callback
  def _scheduled_reset(_: datetime | None = None) -> None:
    hass.async_create_task(_async_run_reset())

  unsubscribe = async_track_time_change(
    hass,
    _scheduled_reset,
    hour=reset_time.hour,
    minute=reset_time.minute,
    second=reset_time.second,
  )

  entry.async_on_unload(unsubscribe)
  return unsubscribe
