"""Repairs support for Paw Control integration.

This module provides automated issue detection and user-guided repair flows
for common configuration and setup problems. It helps users resolve issues
independently and maintains system health. Designed to meet Home Assistant's
Platinum quality ambitions.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from inspect import isawaitable
from typing import Any, cast

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.selector import selector
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry
from .const import (
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOGS,
  DOMAIN,
  MODULE_FEEDING,
  MODULE_GARDEN,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_NOTIFICATIONS,
  MODULE_WALK,
)
from .coordinator_support import ensure_cache_repair_aggregate
from .error_classification import classify_error_reason
from .exceptions import RepairRequiredError
from .feeding_translations import build_feeding_compliance_summary
from .runtime_data import (
  RuntimeDataUnavailableError,
  describe_runtime_store_status,
  require_runtime_data,
)
from .telemetry import get_runtime_store_health
from .types import (
  DogConfigData,
  DogModulesConfig,
  FeedingComplianceDisplayMapping,
  FeedingComplianceEventPayload,
  FeedingComplianceLocalizedSummary,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  ReconfigureTelemetry,
  RuntimeStoreHealthLevel,
  RuntimeStoreLevelDurationAlert,
  ServiceContextMetadata,
)

_LOGGER = logging.getLogger(__name__)

# JSON serialisable payload used for issue registry metadata
type JSONPrimitive = str | int | float | bool | None
type JSONType = JSONPrimitive | list["JSONType"] | dict[str, "JSONType"]

# Issue types
ISSUE_MISSING_DOG_CONFIG = "missing_dog_configuration"
ISSUE_DUPLICATE_DOG_IDS = "duplicate_dog_ids"
ISSUE_INVALID_GPS_CONFIG = "invalid_gps_configuration"
ISSUE_MISSING_NOTIFICATIONS = "missing_notification_config"
ISSUE_NOTIFICATION_AUTH_ERROR = "notification_auth_error"
ISSUE_NOTIFICATION_DEVICE_UNREACHABLE = "notification_device_unreachable"
ISSUE_OUTDATED_CONFIG = "outdated_configuration"
ISSUE_PERFORMANCE_WARNING = "performance_warning"
ISSUE_GPS_UPDATE_INTERVAL = "gps_update_interval_warning"
ISSUE_STORAGE_WARNING = "storage_warning"
ISSUE_MODULE_CONFLICT = "module_configuration_conflict"
ISSUE_INVALID_DOG_DATA = "invalid_dog_data"
ISSUE_COORDINATOR_ERROR = "coordinator_error"
ISSUE_CACHE_HEALTH_SUMMARY = "cache_health_summary"
ISSUE_RECONFIGURE_WARNINGS = "reconfigure_warnings"
ISSUE_RECONFIGURE_HEALTH = "reconfigure_health"
ISSUE_FEEDING_COMPLIANCE_ALERT = "feeding_compliance_alert"
ISSUE_FEEDING_COMPLIANCE_NO_DATA = "feeding_compliance_no_data"
ISSUE_DOOR_SENSOR_PERSISTENCE_FAILURE = "door_sensor_persistence_failure"
ISSUE_RUNTIME_STORE_COMPATIBILITY = "runtime_store_compatibility"
ISSUE_RUNTIME_STORE_DURATION_ALERT = "runtime_store_duration_alert"

# Repair flow types
REPAIR_FLOW_DOG_CONFIG = "repair_dog_configuration"
REPAIR_FLOW_GPS_SETUP = "repair_gps_setup"
REPAIR_FLOW_NOTIFICATION_SETUP = "repair_notification_setup"
REPAIR_FLOW_CONFIG_MIGRATION = "repair_config_migration"
REPAIR_FLOW_PERFORMANCE_OPTIMIZATION = "repair_performance_optimization"


def _normalise_issue_severity(
  severity: str | ir.IssueSeverity,
) -> ir.IssueSeverity:
  """Return a valid ``IssueSeverity`` for the provided ``severity`` value."""

  if isinstance(severity, ir.IssueSeverity):
    return severity

  if isinstance(severity, str):
    try:
      return ir.IssueSeverity(severity.lower())
    except ValueError:
      _LOGGER.warning(
        "Unsupported issue severity '%s'; falling back to warning.",
        severity,
      )
      return ir.IssueSeverity.WARNING

  _LOGGER.warning(
    "Unexpected issue severity type %s; falling back to warning.",
    type(severity).__name__,
  )
  return ir.IssueSeverity.WARNING


_RUNTIME_STORE_STATUS_SEVERITY: dict[str, ir.IssueSeverity] = {
  "future_incompatible": ir.IssueSeverity.ERROR,
  "needs_migration": ir.IssueSeverity.ERROR,
  "diverged": ir.IssueSeverity.ERROR,
  "detached_entry": ir.IssueSeverity.WARNING,
  "detached_store": ir.IssueSeverity.WARNING,
}


async def async_create_issue(
  hass: HomeAssistant,
  entry: ConfigEntry,
  issue_id: str,
  issue_type: str,
  data: JSONLikeMapping | None = None,
  severity: str | ir.IssueSeverity = ir.IssueSeverity.WARNING,
) -> None:
  """Create a repair issue for the integration.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry
      issue_id: Unique issue identifier
      issue_type: Type of issue
      data: Additional issue data
      severity: Issue severity (``IssueSeverity`` or string such as ``"warning"``)
  """
  issue_severity = _normalise_issue_severity(severity)

  create_issue = getattr(ir, "async_create_issue", None)
  if not callable(create_issue):
    repair_error = RepairRequiredError(
      "Issue registry unavailable",
      context={"issue_id": issue_id, "issue_type": issue_type},
    )
    _LOGGER.debug(
      "Issue registry unavailable; skipping issue %s (type %s): %s",
      issue_id,
      issue_type,
      repair_error,
    )
    return

  issue_data: JSONMutableMapping = {
    "config_entry_id": entry.entry_id,
    "issue_type": issue_type,
    "created_at": dt_util.utcnow().isoformat(),
    "severity": issue_severity.value,
  }

  if data:
    issue_data.update(dict(data))

  def _serialise_issue_value(value: Any) -> JSONType:
    """Serialise issue metadata to JSON-compatible structures."""

    if value is None or isinstance(value, str | int | float | bool):
      return value

    if isinstance(value, list | tuple | set):
      return [_serialise_issue_value(item) for item in value]

    if isinstance(value, dict):
      return {str(key): _serialise_issue_value(item) for key, item in value.items()}

    return str(value)

  def _stringify_placeholder(value: JSONType) -> str:
    """Convert serialised metadata into user-friendly placeholder text."""

    if isinstance(value, list):
      return ", ".join(_stringify_placeholder(item) for item in value)

    if isinstance(value, dict):
      return ", ".join(
        f"{key}={_stringify_placeholder(item)}" for key, item in value.items()
      )

    return str(value)

  serialised_issue_data: dict[str, JSONType] = {
    key: _serialise_issue_value(value) for key, value in issue_data.items()
  }

  translation_placeholders = {
    key: _stringify_placeholder(value)
    for key, value in serialised_issue_data.items()
    if value is not None
  }

  try:
    result = create_issue(
      hass,
      DOMAIN,
      issue_id,
      breaks_in_ha_version=None,
      is_fixable=True,
      issue_domain=DOMAIN,
      severity=issue_severity,
      translation_key=issue_type,
      translation_placeholders=translation_placeholders,
      data=serialised_issue_data,
    )
  except Exception as err:  # pragma: no cover - depends on HA internals
    repair_error = RepairRequiredError(
      "Issue registry call failed",
      context={"issue_id": issue_id, "issue_type": issue_type},
    )
    _LOGGER.warning("Failed to create repair issue: %s (%s)", repair_error, err)
    return

  if not isawaitable(result):
    _LOGGER.debug(
      "Issue registry create_issue returned non-awaitable result for %s",
      issue_id,
    )
    return

  try:
    await result
  except Exception as err:  # pragma: no cover - depends on HA internals
    repair_error = RepairRequiredError(
      "Issue registry await failed",
      context={"issue_id": issue_id, "issue_type": issue_type},
    )
    _LOGGER.warning("Failed to await repair issue creation: %s (%s)", repair_error, err)
    return

  _LOGGER.info("Created repair issue: %s (%s)", issue_id, issue_type)


async def async_publish_feeding_compliance_issue(
  hass: HomeAssistant,
  entry: ConfigEntry,
  payload: FeedingComplianceEventPayload,
  *,
  context_metadata: ServiceContextMetadata | None = None,
) -> None:
  """Create or clear feeding compliance repair issues based on telemetry."""

  dog_id = payload["dog_id"]
  dog_name = payload.get("dog_name") or dog_id
  issue_id = f"{entry.entry_id}_feeding_compliance_{dog_id}"
  result = payload["result"]
  if not isinstance(result, Mapping):
    return

  language = getattr(getattr(hass, "config", None), "language", None)
  localized_summary = payload.get("localized_summary")
  if localized_summary is None:
    localized_summary = build_feeding_compliance_summary(
      language,
      display_name=dog_name,
      compliance=cast(FeedingComplianceDisplayMapping, result),
    )

  summary_copy: FeedingComplianceLocalizedSummary = {
    "title": localized_summary["title"],
    "message": localized_summary.get("message"),
    "score_line": localized_summary.get("score_line"),
    "missed_meals": list(localized_summary.get("missed_meals", [])),
    "issues": list(localized_summary.get("issues", [])),
    "recommendations": list(localized_summary.get("recommendations", [])),
  }

  result_copy = cast(JSONMutableMapping, dict(result))
  summary_json = cast(JSONMutableMapping, dict(summary_copy))

  issue_data: JSONMutableMapping = {
    "dog_id": dog_id,
    "dog_name": dog_name,
    "days_to_check": payload.get("days_to_check"),
    "notify_on_issues": payload.get("notify_on_issues"),
    "notification_sent": payload.get("notification_sent"),
    "notification_id": payload.get("notification_id"),
    "result": result_copy,
    "localized_summary": summary_json,
    "notification_title": cast(str, summary_json.get("title")),
    "notification_message": cast(str | None, summary_json.get("message")),
    "score_line": cast(str | None, summary_json.get("score_line")),
    "issue_summary": cast(list[str], summary_json.get("issues", [])),
    "missed_meal_summary": cast(list[str], summary_json.get("missed_meals", [])),
    "recommendations_summary": cast(
      list[str],
      summary_json.get("recommendations", []),
    ),
  }

  if context_metadata:
    issue_data["context_metadata"] = cast(
      JSONMutableMapping,
      dict(context_metadata),
    )

  summary_message = summary_copy.get("message")

  if cast(str, result.get("status")) != "completed":
    message_value: Any = result.get("message")
    if not isinstance(message_value, str):
      message_value = summary_message
    issue_data.update(
      {
        "status": cast(str | None, result.get("status")),
        "message": message_value,
        "checked_at": cast(str | None, result.get("checked_at")),
      },
    )

    await async_create_issue(
      hass,
      entry,
      issue_id,
      ISSUE_FEEDING_COMPLIANCE_NO_DATA,
      issue_data,
      severity=ir.IssueSeverity.WARNING,
    )
    return

  completed = cast(JSONMutableMapping, dict(result))
  missed_meals_raw = completed.get("missed_meals", [])
  missed_meals = (
    [dict(entry) for entry in missed_meals_raw if isinstance(entry, Mapping)]
    if isinstance(missed_meals_raw, Sequence)
    else []
  )
  issues_raw = completed.get("compliance_issues", [])
  issues = (
    [dict(issue) for issue in issues_raw if isinstance(issue, Mapping)]
    if isinstance(issues_raw, Sequence)
    else []
  )
  recommendations_raw = completed.get("recommendations", [])
  recommendations = (
    [str(rec) for rec in recommendations_raw if isinstance(rec, str)]
    if isinstance(recommendations_raw, Sequence)
    and not isinstance(recommendations_raw, str | bytes)
    else []
  )

  score_raw = completed.get("compliance_score", 0)
  score = (
    float(score_raw)
    if isinstance(
      score_raw,
      int | float | str,
    )
    else 0.0
  )
  has_issues = bool(
    completed.get(
      "days_with_issues",
    )
    or issues
    or missed_meals
    or score < 100,
  )

  delete_issue = getattr(ir, "async_delete_issue", None)
  if not has_issues:
    if callable(delete_issue):
      delete_result = delete_issue(hass, DOMAIN, issue_id)
      if isawaitable(delete_result):
        await delete_result
    return

  severity_enum = getattr(ir, "IssueSeverity", None)
  error_severity: str | ir.IssueSeverity
  warning_severity: str | ir.IssueSeverity
  critical_severity: str | ir.IssueSeverity | None
  warning_candidate: str | ir.IssueSeverity | None = None

  if severity_enum is None:
    error_severity = "error"
    warning_severity = "warning"
    critical_severity = None
  else:
    error_severity = getattr(severity_enum, "ERROR", "error")
    warning_candidate = getattr(severity_enum, "WARNING", None)
    warning_severity = (
      warning_candidate if warning_candidate is not None else error_severity
    )
    critical_severity = getattr(severity_enum, "CRITICAL", None)

  severity: str | ir.IssueSeverity = error_severity
  if score < 70:
    if critical_severity is not None:
      severity = critical_severity
    else:
      _LOGGER.debug(
        "IssueSeverity.CRITICAL unavailable; defaulting to %s severity",
        getattr(error_severity, "value", error_severity),
      )
      severity = error_severity
  elif score >= 90:
    if warning_candidate is None and severity_enum is not None:
      _LOGGER.debug(
        "IssueSeverity.WARNING unavailable; defaulting to %s severity",
        getattr(error_severity, "value", error_severity),
      )
    severity = warning_severity

  issue_data.update(
    {
      "status": completed.get("status"),
      "checked_at": completed.get("checked_at"),
      "compliance_score": score,
      "compliance_rate": completed.get("compliance_rate"),
      "days_analyzed": completed.get("days_analyzed"),
      "days_with_issues": completed.get("days_with_issues"),
      "issue_count": len(issues),
      "missed_meal_count": len(missed_meals),
      "issues": issues,
      "missed_meals": missed_meals,
      "recommendations": recommendations,
    },
  )

  await async_create_issue(
    hass,
    entry,
    issue_id,
    ISSUE_FEEDING_COMPLIANCE_ALERT,
    issue_data,
    severity=severity,
  )


async def async_check_for_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Check for common issues and create repair flows if needed.

  This function performs comprehensive health checks and identifies
  potential configuration or operational issues that require user attention.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry to check
  """
  _LOGGER.debug(
    "Checking for issues in Paw Control entry: %s",
    entry.entry_id,
  )

  try:
    # Check dog configuration issues
    await _check_dog_configuration_issues(hass, entry)

    # Check GPS configuration issues
    await _check_gps_configuration_issues(hass, entry)

  # Check notification configuration issues
  await _check_notification_configuration_issues(hass, entry)
  # Check recurring notification delivery errors (auth/unreachable)
  await _check_notification_delivery_errors(hass, entry)

    # Check for outdated configuration
    await _check_outdated_configuration(hass, entry)

    # Check telemetry gathered during reconfigure flows
    await _check_reconfigure_telemetry_issues(hass, entry)

    # Check performance issues
    await _check_performance_issues(hass, entry)

    # Check storage issues
    await _check_storage_issues(hass, entry)

    # Check runtime store compatibility issues
    await _check_runtime_store_health(hass, entry)

    # Surface runtime store duration guard alerts
    await _check_runtime_store_duration_alerts(hass, entry)

    # Publish cache health diagnostics
    await _publish_cache_health_issue(hass, entry)

    # Check coordinator health
    await _check_coordinator_health(hass, entry)

    _LOGGER.debug("Issue check completed for entry: %s", entry.entry_id)

  except Exception as err:
    _LOGGER.error(
      "Error during issue check for entry %s: %s",
      entry.entry_id,
      err,
    )


async def async_schedule_repair_evaluation(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Schedule an asynchronous evaluation of repair issues for ``entry``."""

  async def _async_run_checks() -> None:
    try:
      await async_check_for_issues(hass, entry)
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.debug("Repair evaluation skipped due to error: %s", err)

  hass.async_create_task(
    _async_run_checks(),
    name=f"{DOMAIN}-{entry.entry_id}-repair-evaluation",
  )


async def _check_dog_configuration_issues(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Check for dog configuration issues.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry
  """
  raw_dogs_obj = entry.data.get(CONF_DOGS, [])
  raw_dogs = (
    raw_dogs_obj
    if isinstance(raw_dogs_obj, Sequence) and not isinstance(raw_dogs_obj, str | bytes)
    else []
  )
  dogs: list[Mapping[str, JSONValue]] = [
    cast(Mapping[str, JSONValue], dog) for dog in raw_dogs if isinstance(dog, Mapping)
  ]

  # Check for empty dog configuration
  if not dogs:
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_no_dogs",
      ISSUE_MISSING_DOG_CONFIG,
      {"dogs_count": 0},
      severity="error",
    )
    return

  # Check for duplicate dog IDs
  dog_ids = [
    cast(str, dog_id)
    for dog_id in (dog.get(CONF_DOG_ID) for dog in dogs)
    if isinstance(dog_id, str)
  ]
  duplicate_ids = [
    dog_id
    for dog_id in set(
      dog_ids,
    )
    if dog_ids.count(dog_id) > 1
  ]

  if duplicate_ids:
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_duplicate_dogs",
      ISSUE_DUPLICATE_DOG_IDS,
      {
        "duplicate_ids": duplicate_ids,
        "total_dogs": len(dogs),
      },
      severity="error",
    )

  # Check for invalid dog data
  invalid_dogs = []
  for dog in dogs:
    dog_id = dog.get(CONF_DOG_ID)
    dog_name = dog.get(CONF_DOG_NAME)
    if not isinstance(dog_id, str) or not dog_id or not isinstance(dog_name, str):
      invalid_dogs.append(
        cast(str, dog_id) if isinstance(dog_id, str) else "unknown",
      )

  if invalid_dogs:
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_invalid_dogs",
      ISSUE_INVALID_DOG_DATA,
      {
        "invalid_dogs": invalid_dogs,
        "total_dogs": len(dogs),
      },
      severity="error",
    )


async def _check_gps_configuration_issues(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Check for GPS configuration issues.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry
  """
  raw_dogs_obj = entry.data.get(CONF_DOGS, [])
  raw_dogs = (
    raw_dogs_obj
    if isinstance(raw_dogs_obj, Sequence) and not isinstance(raw_dogs_obj, str | bytes)
    else []
  )
  dogs: list[Mapping[str, JSONValue]] = [
    cast(Mapping[str, JSONValue], dog) for dog in raw_dogs if isinstance(dog, Mapping)
  ]
  gps_enabled_dogs = []
  for dog in dogs:
    modules_raw = dog.get("modules", {})
    modules = modules_raw if isinstance(modules_raw, Mapping) else {}
    if modules.get(MODULE_GPS, False):
      gps_enabled_dogs.append(dog)

  if not gps_enabled_dogs:
    return  # No GPS configuration to check

  # Check if GPS sources are properly configured
  gps_config_raw = entry.options.get("gps", {})
  gps_config = gps_config_raw if isinstance(gps_config_raw, Mapping) else {}

  # Check for missing GPS source configuration
  if not gps_config.get("gps_source"):
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_missing_gps_source",
      ISSUE_INVALID_GPS_CONFIG,
      {
        "issue": "missing_gps_source",
        "gps_enabled_dogs": len(gps_enabled_dogs),
      },
      severity="warning",
    )

  # Check for unrealistic GPS update intervals
  update_interval_raw = gps_config.get("gps_update_interval", 60)
  update_interval = (
    int(update_interval_raw)
    if isinstance(update_interval_raw, int | float | str)
    else 60
  )
  if update_interval < 10:  # Less than 10 seconds
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_gps_update_too_frequent",
      ISSUE_GPS_UPDATE_INTERVAL,
      {
        "current_interval": update_interval,
        "recommended_interval": 30,
      },
      severity=ir.IssueSeverity.WARNING,
    )


async def _check_notification_configuration_issues(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Check for notification configuration issues.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry
  """
  raw_dogs_obj = entry.data.get(CONF_DOGS, [])
  raw_dogs = (
    raw_dogs_obj
    if isinstance(raw_dogs_obj, Sequence) and not isinstance(raw_dogs_obj, str | bytes)
    else []
  )
  dogs: list[Mapping[str, JSONValue]] = [
    cast(Mapping[str, JSONValue], dog) for dog in raw_dogs if isinstance(dog, Mapping)
  ]
  notification_enabled_dogs = []
  for dog in dogs:
    modules_raw = dog.get("modules", {})
    modules = modules_raw if isinstance(modules_raw, Mapping) else {}
    if modules.get(MODULE_NOTIFICATIONS, False):
      notification_enabled_dogs.append(dog)

  if not notification_enabled_dogs:
    return  # No notification configuration to check

  # Check if notification services are available
  notification_config_raw = entry.options.get("notifications", {})
  notification_config = (
    notification_config_raw
    if isinstance(
      notification_config_raw,
      Mapping,
    )
    else {}
  )

  # Check for mobile app availability
  mobile_enabled_raw = notification_config.get("mobile_notifications", True)
  mobile_enabled = mobile_enabled_raw if isinstance(mobile_enabled_raw, bool) else True
  if mobile_enabled:
    has_mobile_app_service = hass.services.has_service(
      "notify",
      "mobile_app",
    )

    if not has_mobile_app_service:
      async_services = getattr(hass.services, "async_services", None)
      if callable(async_services):
        notify_services: Any
        try:
          notify_services = async_services().get("notify", {})
        except Exception:  # pragma: no cover - defensive fallback
          notify_services = {}

        if isinstance(notify_services, dict):
          has_mobile_app_service = any(
            service.startswith("mobile_app") for service in notify_services
          )

    if not has_mobile_app_service:
      await async_create_issue(
        hass,
        entry,
        f"{entry.entry_id}_mobile_app_missing",
        ISSUE_MISSING_NOTIFICATIONS,
        {
          "missing_service": "mobile_app",
          "notification_enabled_dogs": len(notification_enabled_dogs),
        },
        severity="warning",
      )


# -----------------------------------------------------------------------------
# Notification delivery error handling
# -----------------------------------------------------------------------------

def _coerce_int(value: object) -> int | None:
    """Return ``value`` coerced into an integer when safe.

    This helper is shared between repairs and diagnostics to safely convert
    arbitrary objects into integers for metrics.
    """
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


async def _check_notification_delivery_errors(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Surface recurring notification delivery errors as repair issues.

    This function inspects the runtime delivery status snapshot and creates
    repair issues when notification services repeatedly fail due to
    authentication or reachability errors. It uses the ``classify_error_reason``
    helper to map free-form errors into known categories. When an error class
    goes away, the corresponding issue is automatically cleared.
    """

    # Definitions for each classification we care about
    issue_definitions = {
        "auth_error": {
            "issue_id": f"{entry.entry_id}_notification_auth_error",
            "issue_type": ISSUE_NOTIFICATION_AUTH_ERROR,
            "severity": ir.IssueSeverity.ERROR,
        },
        "device_unreachable": {
            "issue_id": f"{entry.entry_id}_notification_device_unreachable",
            "issue_type": ISSUE_NOTIFICATION_DEVICE_UNREACHABLE,
            "severity": ir.IssueSeverity.WARNING,
        },
    }

    try:
        runtime_data = require_runtime_data(hass, entry)
    except RuntimeDataUnavailableError:
        # If runtime data is unavailable, remove any lingering issues
        delete_issue = getattr(ir, "async_delete_issue", None)
        if callable(delete_issue):
            for issue in issue_definitions.values():
                await delete_issue(hass, DOMAIN, issue["issue_id"])
        return

    notification_manager = getattr(runtime_data, "notification_manager", None)
    if notification_manager is None:
        delete_issue = getattr(ir, "async_delete_issue", None)
        if callable(delete_issue):
            for issue in issue_definitions.values():
                await delete_issue(hass, DOMAIN, issue["issue_id"])
        return

    delivery_status = notification_manager.get_delivery_status_snapshot()
    if not isinstance(delivery_status, Mapping):
        delete_issue = getattr(ir, "async_delete_issue", None)
        if callable(delete_issue):
            for issue in issue_definitions.values():
                await delete_issue(hass, DOMAIN, issue["issue_id"])
        return

    services = delivery_status.get("services")
    if not isinstance(services, Mapping):
        delete_issue = getattr(ir, "async_delete_issue", None)
        if callable(delete_issue):
            for issue in issue_definitions.values():
                await delete_issue(hass, DOMAIN, issue["issue_id"])
        return

    # We consider an error recurring if there are >=3 consecutive failures
    recurring_threshold = 3
    classified_services: dict[str, dict[str, object]] = {
        key: {"services": [], "total_failures": 0, "consecutive_failures": 0}
        for key in issue_definitions
    }
    reasons_by_class: dict[str, set[str]] = {key: set() for key in issue_definitions}

    for service_name, payload in services.items():
        if not isinstance(service_name, str) or not isinstance(payload, Mapping):
            continue
        total_failures = _coerce_int(payload.get("total_failures")) or 0
        consecutive_failures = _coerce_int(payload.get("consecutive_failures")) or 0
        # Only trigger if consecutive failures meet the threshold
        if consecutive_failures < recurring_threshold or total_failures <= 0:
            continue
        last_error_reason = payload.get("last_error_reason")
        reason_text = (
            last_error_reason if isinstance(last_error_reason, str) and last_error_reason else None
        )
        last_error = payload.get("last_error")
        error_text = last_error if isinstance(last_error, str) else None
        classification = classify_error_reason(reason_text, error=error_text)
        if classification not in issue_definitions:
            continue
        classified_entry = classified_services[classification]
        # Append service name and accumulate counts
        classified_entry["services"].append(service_name)
        classified_entry["total_failures"] = cast(int, classified_entry["total_failures"]) + total_failures
        classified_entry["consecutive_failures"] = cast(int, classified_entry["consecutive_failures"]) + consecutive_failures
        if reason_text:
            reasons_by_class[classification].add(reason_text)

    # Create or clear issues based on classification results
    delete_issue = getattr(ir, "async_delete_issue", None)
    for classification, definition in issue_definitions.items():
        services_list = classified_services[classification]["services"]
        if not services_list:
            if callable(delete_issue):
                await delete_issue(hass, DOMAIN, definition["issue_id"])
            continue
        issue_data: JSONMutableMapping = {
            "services": ", ".join(sorted(services_list)),
            "service_count": len(services_list),
            "total_failures": classified_services[classification]["total_failures"],
            "consecutive_failures": classified_services[classification]["consecutive_failures"],
            "last_error_reasons": (
                ", ".join(sorted(reasons_by_class[classification]))
                if reasons_by_class[classification]
                else "n/a"
            ),
        }
        await async_create_issue(
            hass,
            entry,
            definition["issue_id"],
            definition["issue_type"],
            issue_data,
            severity=definition["severity"],
        )


async def _check_outdated_configuration(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Check for outdated configuration that needs migration.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry
  """
  # Check config entry version
  if entry.version < 1:  # Current version is 1
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_outdated_config",
      ISSUE_OUTDATED_CONFIG,
      {
        "current_version": entry.version,
        "required_version": 1,
      },
      severity=ir.IssueSeverity.WARNING,
    )


async def _check_reconfigure_telemetry_issues(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Surface reconfigure warnings and health summaries via repairs."""

  options: JSONLikeMapping = (
    cast(JSONLikeMapping, entry.options) if isinstance(entry.options, Mapping) else {}
  )
  telemetry_raw = options.get("reconfigure_telemetry")

  delete_issue = getattr(ir, "async_delete_issue", None)
  warnings_issue_id = f"{entry.entry_id}_reconfigure_warnings"
  health_issue_id = f"{entry.entry_id}_reconfigure_health"

  if not isinstance(telemetry_raw, Mapping):
    if callable(delete_issue):
      await delete_issue(hass, DOMAIN, warnings_issue_id)
      await delete_issue(hass, DOMAIN, health_issue_id)
    return

  telemetry = cast(ReconfigureTelemetry, telemetry_raw)

  def _as_list(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
      return [str(item) for item in value if item is not None]
    return []

  timestamp = str(
    telemetry.get("timestamp") or options.get("last_reconfigure") or "",
  )
  requested_profile = str(telemetry.get("requested_profile", ""))
  previous_profile = str(telemetry.get("previous_profile", ""))
  warnings = _as_list(telemetry.get("compatibility_warnings"))

  if warnings:
    await async_create_issue(
      hass,
      entry,
      warnings_issue_id,
      ISSUE_RECONFIGURE_WARNINGS,
      {
        "timestamp": timestamp,
        "requested_profile": requested_profile,
        "previous_profile": previous_profile,
        "warnings": warnings,
      },
      severity=ir.IssueSeverity.WARNING,
    )
  elif callable(delete_issue):
    await delete_issue(hass, DOMAIN, warnings_issue_id)

  health_summary = telemetry.get("health_summary")
  if isinstance(health_summary, Mapping):
    healthy = bool(health_summary.get("healthy", True))
    health_issues = _as_list(health_summary.get("issues"))
    health_warnings = _as_list(health_summary.get("warnings"))

    if not healthy or health_issues or health_warnings:
      severity = (
        ir.IssueSeverity.ERROR
        if (not healthy and health_issues)
        else ir.IssueSeverity.WARNING
      )
      await async_create_issue(
        hass,
        entry,
        health_issue_id,
        ISSUE_RECONFIGURE_HEALTH,
        {
          "timestamp": timestamp,
          "requested_profile": requested_profile,
          "health_issues": health_issues,
          "health_warnings": health_warnings,
        },
        severity=severity,
      )
    elif callable(delete_issue):
      await delete_issue(hass, DOMAIN, health_issue_id)
  elif callable(delete_issue):
    await delete_issue(hass, DOMAIN, health_issue_id)


async def _check_performance_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Check for performance-related issues.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry
  """
  raw_dogs_obj = entry.data.get(CONF_DOGS, [])
  raw_dogs = (
    raw_dogs_obj
    if isinstance(raw_dogs_obj, Sequence) and not isinstance(raw_dogs_obj, str | bytes)
    else []
  )
  dogs: list[Mapping[str, JSONValue]] = [
    cast(Mapping[str, JSONValue], dog) for dog in raw_dogs if isinstance(dog, Mapping)
  ]

  # Check for too many dogs (performance warning)
  if len(dogs) > 10:
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_too_many_dogs",
      ISSUE_PERFORMANCE_WARNING,
      {
        "dog_count": len(dogs),
        "recommended_max": 10,
        "suggestion": "Consider performance mode optimization",
      },
      severity=ir.IssueSeverity.WARNING,
    )

  # Check for conflicting module configurations
  high_resource_modules = [MODULE_GPS, MODULE_HEALTH]
  dogs_with_all_modules = []
  for dog in dogs:
    modules_raw = dog.get("modules", {})
    modules = modules_raw if isinstance(modules_raw, Mapping) else {}
    if all(modules.get(module, False) for module in high_resource_modules):
      dogs_with_all_modules.append(dog)

  if len(dogs_with_all_modules) > 5:
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_resource_intensive_config",
      ISSUE_MODULE_CONFLICT,
      {
        "intensive_dogs": len(dogs_with_all_modules),
        "total_dogs": len(dogs),
        "suggestion": "Consider selective module enabling",
      },
      severity=ir.IssueSeverity.WARNING,
    )


async def _check_storage_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Check for storage-related issues.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry
  """
  # Check data retention settings
  retention_raw = entry.options.get("data_retention_days", 90)
  retention_days = (
    int(retention_raw)
    if isinstance(
      retention_raw,
      int | float | str,
    )
    else 90
  )

  if retention_days > 365:  # More than 1 year
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_high_storage_retention",
      ISSUE_STORAGE_WARNING,
      {
        "current_retention": retention_days,
        "recommended_max": 365,
        "suggestion": "Consider reducing data retention period",
      },
      severity=ir.IssueSeverity.WARNING,
    )


async def _check_runtime_store_health(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Surface runtime store compatibility issues through repairs."""

  issue_id = f"{entry.entry_id}_runtime_store"
  snapshot = describe_runtime_store_status(hass, entry)
  status = snapshot.get("status", "current")
  severity = _RUNTIME_STORE_STATUS_SEVERITY.get(status)

  delete_issue = getattr(ir, "async_delete_issue", None)

  if severity is None:
    if callable(delete_issue):
      await delete_issue(hass, DOMAIN, issue_id)
    return

  entry_snapshot = snapshot.get("entry", {})
  store_snapshot = snapshot.get("store", {})

  def _string_or_unknown(value: Any) -> str:
    if value is None:
      return "n/a"
    return str(value)

  issue_data: JSONMutableMapping = {
    "status": status,
    "current_version": snapshot.get("current_version"),
    "minimum_compatible_version": snapshot.get("minimum_compatible_version"),
    "entry_status": entry_snapshot.get("status"),
    "store_status": store_snapshot.get("status"),
    "divergence_detected": snapshot.get("divergence_detected", False),
  }

  issue_data["entry_version"] = _string_or_unknown(
    entry_snapshot.get("version"),
  )
  issue_data["entry_created_version"] = _string_or_unknown(
    entry_snapshot.get("created_version"),
  )
  issue_data["store_version"] = _string_or_unknown(
    store_snapshot.get("version"),
  )
  issue_data["store_created_version"] = _string_or_unknown(
    store_snapshot.get("created_version"),
  )

  await async_create_issue(
    hass,
    entry,
    issue_id,
    ISSUE_RUNTIME_STORE_COMPATIBILITY,
    issue_data,
    severity=severity,
  )


def _normalise_duration_alerts(
  summary: Mapping[str, object] | None,
) -> list[RuntimeStoreLevelDurationAlert]:
  """Return guard alerts derived from ``summary`` when present."""

  if not isinstance(summary, Mapping):
    return []

  alerts_raw = summary.get("level_duration_guard_alerts")
  if not isinstance(alerts_raw, Sequence):
    return []

  alerts: list[RuntimeStoreLevelDurationAlert] = []
  for candidate in alerts_raw:
    if not isinstance(candidate, Mapping):
      continue
    level = candidate.get("level")
    percentile_seconds = candidate.get("percentile_seconds")
    guard_limit_seconds = candidate.get("guard_limit_seconds")
    if (
      not isinstance(level, str)
      or not isinstance(percentile_seconds, int | float)
      or not isinstance(guard_limit_seconds, int | float)
    ):
      continue
    alert: RuntimeStoreLevelDurationAlert = {
      "level": cast(RuntimeStoreHealthLevel, level),
      "percentile_label": cast(str, candidate.get("percentile_label", "p95")),
      "percentile_rank": float(candidate.get("percentile_rank", 0.95) or 0.95),
      "percentile_seconds": float(percentile_seconds),
      "guard_limit_seconds": float(guard_limit_seconds),
      "severity": cast(str, candidate.get("severity", "warning")),
      "recommended_action": cast(str | None, candidate.get("recommended_action")),
    }
    alerts.append(alert)
  return alerts


def _resolve_duration_alert_severity(
  alerts: Sequence[RuntimeStoreLevelDurationAlert],
) -> str | ir.IssueSeverity:
  """Return the issue severity matching ``alerts``."""

  severity_enum = getattr(ir, "IssueSeverity", None)
  highest = "warning"
  for alert in alerts:
    severity = str(alert.get("severity", "warning")).lower()
    if severity in {"critical", "error"}:
      highest = "critical"
      break
    if severity == "warning" and highest != "critical":
      highest = "warning"

  if severity_enum is None:
    return "error" if highest == "critical" else "warning"

  if highest == "critical":
    critical_value = getattr(severity_enum, "CRITICAL", None)
    if critical_value is not None:
      return critical_value
    return getattr(severity_enum, "ERROR", severity_enum.WARNING)

  warning_value = getattr(severity_enum, "WARNING", None)
  if warning_value is not None:
    return warning_value
  return getattr(severity_enum, "ERROR", severity_enum.WARNING)


def _format_duration_summary(seconds: float) -> str:
  """Return a compact human-readable representation for ``seconds``."""

  hours = seconds / 3600.0
  if hours >= 1:
    return f"{hours:.1f}h"
  minutes = seconds / 60.0
  if minutes >= 1:
    return f"{minutes:.0f}m"
  return f"{seconds:.0f}s"


async def _check_runtime_store_duration_alerts(
  hass: HomeAssistant,
  entry: ConfigEntry,
) -> None:
  """Raise a repair issue when timeline durations exceed guard limits."""

  issue_id = f"{entry.entry_id}_runtime_store_duration_alerts"
  try:
    runtime_data = require_runtime_data(hass, entry)
  except RuntimeDataUnavailableError:
    delete_issue = getattr(ir, "async_delete_issue", None)
    if callable(delete_issue):
      await delete_issue(hass, DOMAIN, issue_id)
    return

  history = get_runtime_store_health(runtime_data)
  if not isinstance(history, Mapping):
    delete_issue = getattr(ir, "async_delete_issue", None)
    if callable(delete_issue):
      await delete_issue(hass, DOMAIN, issue_id)
    return

  timeline_summary = None
  summary_candidate = history.get("assessment_timeline_summary")
  if isinstance(summary_candidate, Mapping):
    timeline_summary = summary_candidate
  else:
    assessment = history.get("assessment")
    if isinstance(assessment, Mapping):
      nested_summary = assessment.get("timeline_summary")
      if isinstance(nested_summary, Mapping):
        timeline_summary = nested_summary

  alerts = _normalise_duration_alerts(timeline_summary)
  if not alerts:
    delete_issue = getattr(ir, "async_delete_issue", None)
    if callable(delete_issue):
      await delete_issue(hass, DOMAIN, issue_id)
    return

  severity = _resolve_duration_alert_severity(alerts)
  triggered_levels = ", ".join(sorted({alert["level"] for alert in alerts}))
  alert_summaries = "; ".join(
    f"{alert['level']}: {alert['percentile_label']} "
    f"{_format_duration_summary(alert['percentile_seconds'])} "
    f"(guard {_format_duration_summary(alert['guard_limit_seconds'])})"
    for alert in alerts
  )
  recommendations = "; ".join(
    cast(str, action)
    for action in (alert.get("recommended_action") for alert in alerts)
    if isinstance(action, str)
  )

  timeline_window = None
  last_event_timestamp = None
  if isinstance(timeline_summary, Mapping):
    timeline_window = timeline_summary.get("timeline_window_days")
    last_event_timestamp = timeline_summary.get("last_event_timestamp")

  issue_data: JSONMutableMapping = {
    "alert_count": len(alerts),
    "triggered_levels": triggered_levels,
    "alert_summaries": alert_summaries,
    "timeline_window_days": timeline_window if timeline_window is not None else "n/a",
    "last_event_timestamp": last_event_timestamp
    if last_event_timestamp is not None
    else "n/a",
  }
  issue_data["recommended_actions"] = recommendations or "n/a"

  await async_create_issue(
    hass,
    entry,
    issue_id,
    ISSUE_RUNTIME_STORE_DURATION_ALERT,
    issue_data,
    severity=severity,
  )


async def _publish_cache_health_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Publish aggregated cache diagnostics to the repairs dashboard."""

  issue_id = f"{entry.entry_id}_cache_health"
  try:
    runtime_data = require_runtime_data(hass, entry)
  except RuntimeDataUnavailableError:
    delete_issue = getattr(ir, "async_delete_issue", None)
    if callable(delete_issue):
      await delete_issue(hass, DOMAIN, issue_id)
    return

  data_manager = getattr(runtime_data, "data_manager", None)
  if data_manager is None:
    delete_issue = getattr(ir, "async_delete_issue", None)
    if callable(delete_issue):
      await delete_issue(hass, DOMAIN, issue_id)
    return

  summary_method = getattr(data_manager, "cache_repair_summary", None)
  if not callable(summary_method):
    return

  try:
    summary = summary_method()
  except Exception as err:  # pragma: no cover - diagnostics guard
    _LOGGER.debug("Skipping cache health issue publication: %s", err)
    return

  if summary is None:
    delete_issue = getattr(ir, "async_delete_issue", None)
    if callable(delete_issue):
      await delete_issue(hass, DOMAIN, issue_id)
    return

  resolved_summary = ensure_cache_repair_aggregate(summary)
  if resolved_summary is None:
    _LOGGER.debug(
      "Cache repair summary returned unexpected payload: %r",
      summary,
    )
    return

  summary = resolved_summary

  if summary.anomaly_count == 0:
    delete_issue = getattr(ir, "async_delete_issue", None)
    if callable(delete_issue):
      await delete_issue(hass, DOMAIN, issue_id)
    return

  severity = summary.severity or ir.IssueSeverity.WARNING.value
  await async_create_issue(
    hass,
    entry,
    issue_id,
    ISSUE_CACHE_HEALTH_SUMMARY,
    {"summary": summary.to_mapping()},
    severity=severity,
  )


async def _check_coordinator_health(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Check coordinator health and functionality.

  Args:
      hass: Home Assistant instance
      entry: Configuration entry
  """
  try:
    runtime_data = require_runtime_data(hass, entry)
  except RuntimeDataUnavailableError:
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_coordinator_missing",
      ISSUE_COORDINATOR_ERROR,
      {
        "error": "coordinator_not_initialized",
        "suggestion": "Try reloading the integration",
      },
      severity="error",
    )
    return
  except Exception as err:
    _LOGGER.error("Error checking coordinator health: %s", err)
    return

  coordinator = runtime_data.coordinator

  if not getattr(coordinator, "last_update_success", True):
    last_update_time = getattr(coordinator, "last_update_time", None)
    await async_create_issue(
      hass,
      entry,
      f"{entry.entry_id}_coordinator_failed",
      ISSUE_COORDINATOR_ERROR,
      {
        "error": "last_update_failed",
        "last_update": last_update_time.isoformat() if last_update_time else None,
        "suggestion": "Check logs for detailed error information",
      },
      severity="warning",
    )


class PawControlRepairsFlow(RepairsFlow):
  """Handle repair flows for Paw Control integration."""

  def __init__(self) -> None:
    """Initialize the repair flow."""
    super().__init__()
    self._issue_data: JSONMutableMapping = {}
    self._repair_type: str = ""

  async def async_step_init(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle the initial step of a repair flow.

    Args:
        user_input: User provided data

    Returns:
        Flow result for next step or completion
    """
    self._issue_data = cast(
      JSONMutableMapping,
      self.hass.data[ir.DOMAIN][self.issue_id].data,
    )
    issue_type_raw = self._issue_data.get("issue_type", "")
    self._repair_type = (
      issue_type_raw
      if isinstance(
        issue_type_raw,
        str,
      )
      else ""
    )

    # Route to appropriate repair flow based on issue type
    if self._repair_type == ISSUE_MISSING_DOG_CONFIG:
      return await self.async_step_missing_dog_config()
    if self._repair_type == ISSUE_DUPLICATE_DOG_IDS:
      return await self.async_step_duplicate_dog_ids()
    if self._repair_type == ISSUE_INVALID_GPS_CONFIG:
      return await self.async_step_invalid_gps_config()
    if self._repair_type == ISSUE_MISSING_NOTIFICATIONS:
      return await self.async_step_missing_notifications()
    if self._repair_type == ISSUE_OUTDATED_CONFIG:
      return await self.async_step_outdated_config()
    if self._repair_type in {
      ISSUE_PERFORMANCE_WARNING,
      ISSUE_GPS_UPDATE_INTERVAL,
    }:
      return await self.async_step_performance_warning()
    if self._repair_type == ISSUE_STORAGE_WARNING:
      return await self.async_step_storage_warning()
    if self._repair_type == ISSUE_MODULE_CONFLICT:
      return await self.async_step_module_conflict()
    if self._repair_type == ISSUE_INVALID_DOG_DATA:
      return await self.async_step_invalid_dog_data()
    if self._repair_type == ISSUE_COORDINATOR_ERROR:
      return await self.async_step_coordinator_error()
    return await self.async_step_unknown_issue()

  async def async_step_missing_dog_config(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle repair flow for missing dog configuration.

    Args:
        user_input: User provided data

    Returns:
        Flow result for next step or completion
    """
    if user_input is not None:
      action = user_input.get("action")

      if action == "add_dog":
        return await self.async_step_add_first_dog()
      if action == "reconfigure":
        # Redirect to reconfigure flow
        return self.async_external_step(
          step_id="reconfigure",
          url="/config/integrations",
        )
      return await self.async_step_complete_repair()

    return self.async_show_form(
      step_id="missing_dog_config",
      data_schema=vol.Schema(
        {
          vol.Required("action"): selector(
            {
              "select": {
                "options": [
                  {"value": "add_dog", "label": "Add a dog now"},
                  {
                    "value": "reconfigure",
                    "label": "Go to integration settings",
                  },
                  {"value": "ignore", "label": "Ignore for now"},
                ],
              },
            },
          ),
        },
      ),
      description_placeholders={
        "dogs_count": self._issue_data.get("dogs_count", 0),
      },
    )

  async def async_step_add_first_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle adding the first dog.

    Args:
        user_input: User provided data

    Returns:
        Flow result for next step or completion
    """
    errors = {}

    if user_input is not None:
      try:
        # Validate dog data
        dog_id_raw = user_input.get("dog_id")
        dog_name_raw = user_input.get("dog_name")

        if not isinstance(dog_id_raw, str) or not isinstance(dog_name_raw, str):
          errors["base"] = "incomplete_data"
        else:
          dog_id = dog_id_raw.lower().strip()
          dog_name = dog_name_raw.strip()

          if not dog_id or not dog_name:
            errors["base"] = "incomplete_data"
          else:
            # Get the config entry and update it
            config_entry_id = self._issue_data["config_entry_id"]
            entry = self.hass.config_entries.async_get_entry(
              config_entry_id,
            )

            if entry:
              # Create new dog configuration
              dog_breed_raw = user_input.get("dog_breed", "")
              dog_age_raw = user_input.get("dog_age", 3)
              dog_weight_raw = user_input.get("dog_weight", 20.0)
              dog_size_raw = user_input.get("dog_size", "medium")
              new_dog = {
                CONF_DOG_ID: dog_id,
                CONF_DOG_NAME: dog_name,
                "dog_breed": dog_breed_raw if isinstance(dog_breed_raw, str) else "",
                "dog_age": int(dog_age_raw)
                if isinstance(dog_age_raw, int | float | str)
                else 3,
                "dog_weight": float(dog_weight_raw)
                if isinstance(dog_weight_raw, int | float | str)
                else 20.0,
                "dog_size": dog_size_raw if isinstance(dog_size_raw, str) else "medium",
                "modules": {
                  "feeding": True,
                  "walk": True,
                  "gps": False,
                  "health": True,
                  "notifications": True,
                },
              }

            # Update the config entry
            new_data = entry.data.copy()
            new_data[CONF_DOGS] = [new_dog]

            self.hass.config_entries.async_update_entry(
              entry,
              data=new_data,
            )

            return await self.async_step_complete_repair()
          errors["base"] = "config_entry_not_found"

      except Exception as err:
        _LOGGER.error("Error adding first dog: %s", err)
        errors["base"] = "unexpected_error"

    return self.async_show_form(
      step_id="add_first_dog",
      data_schema=vol.Schema(
        {
          vol.Required("dog_id"): str,
          vol.Required("dog_name"): str,
          vol.Optional("dog_breed", default=""): str,
          vol.Optional("dog_age", default=3): int,
          vol.Optional("dog_weight", default=20.0): float,
          vol.Optional("dog_size", default="medium"): selector(
            {
              "select": {
                "options": ["toy", "small", "medium", "large", "giant"],
              },
            },
          ),
        },
      ),
      errors=errors,
    )

  async def async_step_duplicate_dog_ids(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle repair flow for duplicate dog IDs.

    Args:
        user_input: User provided data

    Returns:
        Flow result for next step or completion
    """
    if user_input is not None:
      action = user_input.get("action")

      if action == "auto_fix":
        # Automatically fix duplicate IDs
        await self._fix_duplicate_dog_ids()
        return await self.async_step_complete_repair()
      if action == "manual_fix":
        return self.async_external_step(
          step_id="reconfigure",
          url="/config/integrations",
        )
      return await self.async_step_complete_repair()

    duplicate_ids_raw = self._issue_data.get("duplicate_ids", [])
    duplicate_ids = (
      [str(item) for item in duplicate_ids_raw]
      if isinstance(duplicate_ids_raw, Sequence)
      and not isinstance(duplicate_ids_raw, str | bytes)
      else []
    )
    total_dogs_raw = self._issue_data.get("total_dogs", 0)
    total_dogs = (
      int(total_dogs_raw)
      if isinstance(
        total_dogs_raw,
        int | float | str,
      )
      else 0
    )

    return self.async_show_form(
      step_id="duplicate_dog_ids",
      data_schema=vol.Schema(
        {
          vol.Required("action"): selector(
            {
              "select": {
                "options": [
                  {
                    "value": "auto_fix",
                    "label": "Automatically fix duplicate IDs",
                  },
                  {
                    "value": "manual_fix",
                    "label": "Manually fix in integration settings",
                  },
                  {"value": "ignore", "label": "Ignore for now"},
                ],
              },
            },
          ),
        },
      ),
      description_placeholders={
        "duplicate_ids": ", ".join(duplicate_ids),
        "total_dogs": total_dogs,
      },
    )

  async def async_step_invalid_gps_config(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle repair flow for invalid GPS configuration.

    Args:
        user_input: User provided data

    Returns:
        Flow result for next step or completion
    """
    if user_input is not None:
      action = user_input.get("action")

      if action == "configure_gps":
        return await self.async_step_configure_gps()
      if action == "disable_gps":
        await self._disable_gps_for_all_dogs()
        return await self.async_step_complete_repair()
      return await self.async_step_complete_repair()

    return self.async_show_form(
      step_id="invalid_gps_config",
      data_schema=vol.Schema(
        {
          vol.Required("action"): selector(
            {
              "select": {
                "options": [
                  {
                    "value": "configure_gps",
                    "label": "Configure GPS settings",
                  },
                  {
                    "value": "disable_gps",
                    "label": "Disable GPS for all dogs",
                  },
                  {"value": "ignore", "label": "Ignore for now"},
                ],
              },
            },
          ),
        },
      ),
      description_placeholders={
        "issue": self._issue_data.get("issue", "unknown"),
        "gps_enabled_dogs": self._issue_data.get("gps_enabled_dogs", 0),
      },
    )

  async def async_step_configure_gps(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle GPS configuration step.

    Args:
        user_input: User provided data

    Returns:
        Flow result for next step or completion
    """
    if user_input is not None:
      try:
        # Update GPS configuration
        config_entry_id = self._issue_data["config_entry_id"]
        entry = self.hass.config_entries.async_get_entry(
          config_entry_id,
        )

        if entry:
          new_options = entry.options.copy()
          new_options.setdefault("gps", {}).update(
            {
              "gps_source": user_input["gps_source"],
              "gps_update_interval": user_input["update_interval"],
              "gps_accuracy_filter": user_input["accuracy_filter"],
            },
          )

          self.hass.config_entries.async_update_entry(
            entry,
            options=new_options,
          )

          return await self.async_step_complete_repair()
        return self.async_abort(reason="config_entry_not_found")

      except Exception as err:
        _LOGGER.error("Error configuring GPS: %s", err)
        return self.async_abort(reason="unexpected_error")

    return self.async_show_form(
      step_id="configure_gps",
      data_schema=vol.Schema(
        {
          vol.Required("gps_source", default="device_tracker"): selector(
            {
              "select": {
                "options": [
                  "device_tracker",
                  "person_entity",
                  "manual",
                  "smartphone",
                ],
              },
            },
          ),
          vol.Required("update_interval", default=60): vol.All(
            int,
            vol.Range(min=30, max=600),
          ),
          vol.Required("accuracy_filter", default=100): vol.All(
            int,
            vol.Range(min=5, max=500),
          ),
        },
      ),
    )

  async def async_step_missing_notifications(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle repair flow for missing notification services.

    Args:
        user_input: User provided data

    Returns:
        Flow result for next step or completion
    """
    if user_input is not None:
      action = user_input.get("action")

      if action == "setup_mobile_app":
        return self.async_external_step(
          step_id="setup_mobile",
          url="/config/mobile_app",
        )
      if action == "disable_mobile":
        await self._disable_mobile_notifications()
        return await self.async_step_complete_repair()
      return await self.async_step_complete_repair()

    return self.async_show_form(
      step_id="missing_notifications",
      data_schema=vol.Schema(
        {
          vol.Required("action"): selector(
            {
              "select": {
                "options": [
                  {
                    "value": "setup_mobile_app",
                    "label": "Set up Mobile App integration",
                  },
                  {
                    "value": "disable_mobile",
                    "label": "Disable mobile notifications",
                  },
                  {"value": "ignore", "label": "Ignore for now"},
                ],
              },
            },
          ),
        },
      ),
      description_placeholders={
        "missing_service": self._issue_data.get("missing_service", "unknown"),
        "notification_enabled_dogs": self._issue_data.get(
          "notification_enabled_dogs",
          0,
        ),
      },
    )

  async def async_step_performance_warning(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle performance warning repair flow.

    Args:
        user_input: User provided data

    Returns:
        Flow result for next step or completion
    """
    if user_input is not None:
      action = user_input.get("action")

      if action == "optimize":
        await self._apply_performance_optimizations()
        return await self.async_step_complete_repair()
      if action == "configure":
        return self.async_external_step(
          step_id="configure",
          url="/config/integrations",
        )
      return await self.async_step_complete_repair()

    return self.async_show_form(
      step_id="performance_warning",
      data_schema=vol.Schema(
        {
          vol.Required("action"): selector(
            {
              "select": {
                "options": [
                  {
                    "value": "optimize",
                    "label": "Apply automatic optimizations",
                  },
                  {
                    "value": "configure",
                    "label": "Configure settings manually",
                  },
                  {"value": "ignore", "label": "Ignore warning"},
                ],
              },
            },
          ),
        },
      ),
      description_placeholders=self._issue_data,
    )

  async def async_step_storage_warning(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle repair flow for storage warnings."""

    if user_input is not None:
      action = user_input.get("action")

      if action == "reduce_retention":
        await self._reduce_data_retention()
        return await self.async_step_complete_repair()
      if action == "configure":
        return self.async_external_step(
          step_id="configure_storage",
          url="/config/integrations",
        )
      return await self.async_step_complete_repair()

    return self.async_show_form(
      step_id="storage_warning",
      data_schema=vol.Schema(
        {
          vol.Required("action"): selector(
            {
              "select": {
                "options": [
                  {
                    "value": "reduce_retention",
                    "label": "Reduce data retention to recommended value",
                  },
                  {
                    "value": "configure",
                    "label": "Review storage settings manually",
                  },
                  {"value": "ignore", "label": "Ignore warning"},
                ],
              },
            },
          ),
        },
      ),
      description_placeholders={
        "current_retention": self._issue_data.get("current_retention"),
        "recommended_max": self._issue_data.get("recommended_max"),
        "suggestion": self._issue_data.get("suggestion"),
      },
    )

  async def async_step_module_conflict(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle repair flow for high resource module conflicts."""

    if user_input is not None:
      action = user_input.get("action")

      if action == "reduce_load":
        await self._limit_high_resource_modules()
        return await self.async_step_complete_repair()
      if action == "optimize":
        await self._apply_performance_optimizations()
        return await self.async_step_complete_repair()
      if action == "configure":
        return self.async_external_step(
          step_id="configure_modules",
          url="/config/integrations",
        )
      return await self.async_step_complete_repair()

    return self.async_show_form(
      step_id="module_conflict",
      data_schema=vol.Schema(
        {
          vol.Required("action"): selector(
            {
              "select": {
                "options": [
                  {
                    "value": "reduce_load",
                    "label": "Disable intensive modules for extra dogs",
                  },
                  {
                    "value": "optimize",
                    "label": "Apply automatic optimizations",
                  },
                  {
                    "value": "configure",
                    "label": "Adjust modules manually",
                  },
                  {"value": "ignore", "label": "Ignore warning"},
                ],
              },
            },
          ),
        },
      ),
      description_placeholders={
        "intensive_dogs": self._issue_data.get("intensive_dogs"),
        "total_dogs": self._issue_data.get("total_dogs"),
        "suggestion": self._issue_data.get("suggestion"),
      },
    )

  async def async_step_invalid_dog_data(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle repair flow for invalid dog configuration data."""

    if user_input is not None:
      action = user_input.get("action")

      if action == "clean_up":
        await self._remove_invalid_dogs()
        return await self.async_step_complete_repair()
      if action == "reconfigure":
        return self.async_external_step(
          step_id="reconfigure",
          url="/config/integrations",
        )
      return await self.async_step_complete_repair()

    invalid_dogs_raw = self._issue_data.get("invalid_dogs", [])
    invalid_dogs = (
      [str(dog) for dog in invalid_dogs_raw]
      if isinstance(invalid_dogs_raw, Sequence)
      and not isinstance(invalid_dogs_raw, str | bytes)
      else []
    )
    total_dogs_raw = self._issue_data.get("total_dogs")
    total_dogs = (
      int(total_dogs_raw)
      if isinstance(
        total_dogs_raw,
        int | float | str,
      )
      else 0
    )

    return self.async_show_form(
      step_id="invalid_dog_data",
      data_schema=vol.Schema(
        {
          vol.Required("action"): selector(
            {
              "select": {
                "options": [
                  {
                    "value": "clean_up",
                    "label": "Remove invalid dog entries",
                  },
                  {
                    "value": "reconfigure",
                    "label": "Fix dog data manually",
                  },
                  {"value": "ignore", "label": "Ignore for now"},
                ],
              },
            },
          ),
        },
      ),
      description_placeholders={
        "invalid_dogs": ", ".join(invalid_dogs),
        "total_dogs": total_dogs,
      },
    )

  async def async_step_coordinator_error(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle repair flow for coordinator errors."""

    errors: dict[str, str] = {}

    if user_input is not None:
      action = user_input.get("action")

      if action == "reload":
        if await self._reload_config_entry():
          return await self.async_step_complete_repair()
        errors["base"] = "reload_failed"
      elif action == "view_logs":
        return self.async_external_step(step_id="view_logs", url="/config/logs")
      else:
        return await self.async_step_complete_repair()

    data_schema = vol.Schema(
      {
        vol.Required("action"): selector(
          {
            "select": {
              "options": [
                {
                  "value": "reload",
                  "label": "Reload Paw Control",
                },
                {
                  "value": "view_logs",
                  "label": "Open system logs",
                },
                {"value": "ignore", "label": "Ignore for now"},
              ],
            },
          },
        ),
      },
    )

    return self.async_show_form(
      step_id="coordinator_error",
      data_schema=data_schema,
      description_placeholders={
        "error": self._issue_data.get("error", "unknown"),
        "last_update": self._issue_data.get("last_update"),
        "suggestion": self._issue_data.get("suggestion"),
      },
      errors=errors,
    )

  async def async_step_complete_repair(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Complete the repair flow.

    Args:
        user_input: User provided data

    Returns:
        Flow result indicating completion
    """
    # Remove the issue from the issue registry
    await ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)

    return self.async_create_entry(
      title="Repair completed",
      data={"repaired_issue": self._repair_type},
    )

  async def async_step_unknown_issue(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Handle unknown issue types.

    Args:
        user_input: User provided data

    Returns:
        Flow result for completion
    """
    return self.async_abort(reason="unknown_issue_type")

  # Helper methods for repair actions

  async def _fix_duplicate_dog_ids(self) -> None:
    """Automatically fix duplicate dog IDs."""
    config_entry_id = self._issue_data["config_entry_id"]
    entry = self.hass.config_entries.async_get_entry(config_entry_id)

    if not entry:
      return

    dogs = entry.data.get(CONF_DOGS, [])
    seen_ids = set()
    fixed_dogs = []

    for dog in dogs:
      original_id = dog.get(CONF_DOG_ID, "")
      dog_id = original_id
      counter = 1

      # Generate unique ID
      while dog_id in seen_ids:
        dog_id = f"{original_id}_{counter}"
        counter += 1

      seen_ids.add(dog_id)

      # Update dog configuration
      fixed_dog = dog.copy()
      fixed_dog[CONF_DOG_ID] = dog_id
      fixed_dogs.append(fixed_dog)

    # Update config entry
    new_data = entry.data.copy()
    new_data[CONF_DOGS] = fixed_dogs

    self.hass.config_entries.async_update_entry(entry, data=new_data)

  async def _disable_gps_for_all_dogs(self) -> None:
    """Disable GPS module for all dogs."""
    config_entry_id = self._issue_data["config_entry_id"]
    entry = self.hass.config_entries.async_get_entry(config_entry_id)

    if not entry:
      return

    dogs = entry.data.get(CONF_DOGS, [])
    updated_dogs = []

    for dog in dogs:
      updated_dog = dog.copy()
      modules = updated_dog.setdefault("modules", {})
      modules[MODULE_GPS] = False
      updated_dogs.append(updated_dog)

    new_data = entry.data.copy()
    new_data[CONF_DOGS] = updated_dogs

    self.hass.config_entries.async_update_entry(entry, data=new_data)

  async def _disable_mobile_notifications(self) -> None:
    """Disable mobile app notifications."""
    config_entry_id = self._issue_data["config_entry_id"]
    entry = self.hass.config_entries.async_get_entry(config_entry_id)

    if not entry:
      return

    new_options = entry.options.copy()
    notifications = new_options.setdefault("notifications", {})
    notifications["mobile_notifications"] = False

    self.hass.config_entries.async_update_entry(entry, options=new_options)

  async def _apply_performance_optimizations(self) -> None:
    """Apply automatic performance optimizations."""
    config_entry_id = self._issue_data["config_entry_id"]
    entry = self.hass.config_entries.async_get_entry(config_entry_id)

    if not entry:
      return

    new_options = entry.options.copy()

    # Set performance mode to minimal
    new_options["performance_mode"] = "minimal"

    # Optimize GPS settings if present
    if "gps" in new_options:
      gps_settings = new_options["gps"]
      gps_settings["gps_update_interval"] = max(
        gps_settings.get("gps_update_interval", 60),
        120,
      )

    # Reduce data retention
    new_options["data_retention_days"] = min(
      new_options.get("data_retention_days", 90),
      30,
    )

    self.hass.config_entries.async_update_entry(entry, options=new_options)

  async def _reduce_data_retention(self) -> None:
    """Reduce stored history to the recommended value."""

    config_entry_id = self._issue_data.get("config_entry_id")
    if not config_entry_id:
      return

    entry = self.hass.config_entries.async_get_entry(config_entry_id)
    if not entry:
      return

    recommended_max = self._issue_data.get("recommended_max")
    if not isinstance(recommended_max, int):
      recommended_max = 365

    new_options = entry.options.copy()
    if new_options.get("data_retention_days") == recommended_max:
      return

    new_options["data_retention_days"] = recommended_max
    self.hass.config_entries.async_update_entry(entry, options=new_options)

  async def _limit_high_resource_modules(self) -> None:
    """Disable heavy modules for dogs beyond the recommended threshold."""

    config_entry_id = self._issue_data.get("config_entry_id")
    if not config_entry_id:
      return

    entry = self.hass.config_entries.async_get_entry(config_entry_id)
    if not entry:
      return

    dogs = entry.data.get(CONF_DOGS, [])
    updated_dogs: list[DogConfigData] = []
    high_resource_limit = 5
    high_resource_count = 0

    for dog in dogs:
      updated_dog = cast(DogConfigData, dict(dog))
      modules_raw = updated_dog.get("modules", {})
      modules = cast(
        DogModulesConfig,
        {
          MODULE_FEEDING: bool(
            cast(Mapping[str, object], modules_raw).get(
              MODULE_FEEDING,
              True,
            ),
          )
          if isinstance(modules_raw, Mapping)
          else True,
          MODULE_WALK: bool(
            cast(Mapping[str, object], modules_raw).get(
              MODULE_WALK,
              True,
            ),
          )
          if isinstance(modules_raw, Mapping)
          else True,
          MODULE_GPS: bool(
            cast(Mapping[str, object], modules_raw).get(
              MODULE_GPS,
              False,
            ),
          )
          if isinstance(modules_raw, Mapping)
          else False,
          MODULE_HEALTH: bool(
            cast(Mapping[str, object], modules_raw).get(
              MODULE_HEALTH,
              True,
            ),
          )
          if isinstance(modules_raw, Mapping)
          else True,
          MODULE_NOTIFICATIONS: bool(
            cast(Mapping[str, object], modules_raw).get(
              MODULE_NOTIFICATIONS,
              True,
            ),
          )
          if isinstance(modules_raw, Mapping)
          else True,
          MODULE_GARDEN: bool(
            cast(Mapping[str, object], modules_raw).get(
              MODULE_GARDEN,
              False,
            ),
          )
          if isinstance(modules_raw, Mapping)
          else False,
        },
      )

      if modules.get(MODULE_GPS) and modules.get(MODULE_HEALTH):
        high_resource_count += 1
        if high_resource_count > high_resource_limit:
          modules["gps"] = False

      updated_dog["modules"] = modules
      updated_dogs.append(updated_dog)

    if updated_dogs == dogs:
      return

    new_data = entry.data.copy()
    new_data[CONF_DOGS] = updated_dogs
    self.hass.config_entries.async_update_entry(entry, data=new_data)

  async def _remove_invalid_dogs(self) -> None:
    """Remove dogs that are missing required identifiers."""

    config_entry_id = self._issue_data.get("config_entry_id")
    if not config_entry_id:
      return

    entry = self.hass.config_entries.async_get_entry(config_entry_id)
    if not entry:
      return

    dogs = entry.data.get(CONF_DOGS, [])
    valid_dogs = [
      dog for dog in dogs if dog.get(CONF_DOG_ID) and dog.get(CONF_DOG_NAME)
    ]

    if len(valid_dogs) == len(dogs):
      return

    new_data = entry.data.copy()
    new_data[CONF_DOGS] = valid_dogs
    self.hass.config_entries.async_update_entry(entry, data=new_data)

  async def _reload_config_entry(self) -> bool:
    """Reload the integration config entry to recover from coordinator errors."""

    config_entry_id = self._issue_data.get("config_entry_id")
    if not config_entry_id:
      _LOGGER.error(
        "Missing config entry id while handling coordinator repair",
      )
      return False

    try:
      result = await self.hass.config_entries.async_reload(config_entry_id)
    except Exception as err:  # pragma: no cover - defensive logging
      _LOGGER.error(
        "Error reloading config entry %s during repair flow: %s",
        config_entry_id,
        err,
      )
      return False

    if result is False:
      _LOGGER.error(
        "Reload of config entry %s reported failure during repair flow",
        config_entry_id,
      )
      return False

    return True


async def async_create_fix_flow(
  hass: HomeAssistant,
  issue_id: str,
  data: JSONLikeMapping | None,
) -> PawControlRepairsFlow:
  """Create a repair flow compatible with the Repairs integration.

  Home Assistant loads `repairs.py` integration platforms via
  :func:`homeassistant.helpers.integration_platform.async_process_integration_platforms`
  and expects them to expose an ``async_create_fix_flow`` coroutine that
  returns a :class:`~homeassistant.components.repairs.RepairsFlow` instance.

  Args:
      hass: Home Assistant instance
      issue_id: Identifier of the repair issue
      data: Issue metadata provided by the registry

  Returns:
      Repair flow instance bound to the Paw Control handler
  """
  return PawControlRepairsFlow()


async def async_register_repairs(hass: HomeAssistant) -> None:
  """Register initial repair checks for Paw Control integration."""
  _LOGGER.debug("Registering Paw Control repair checks")

  # Iterate over all loaded entries and run checks for those with runtime data
  for entry in hass.config_entries.async_entries(DOMAIN):
    try:
      require_runtime_data(hass, entry)
    except RuntimeDataUnavailableError:
      continue
    await async_check_for_issues(hass, entry)
