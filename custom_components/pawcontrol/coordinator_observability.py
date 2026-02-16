"""Observability helpers that keep :mod:`coordinator` concise."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from logging import getLogger
from math import isfinite
import sys
from typing import Any, Final, Literal, cast

from .coordinator_runtime import EntityBudgetSnapshot, summarize_entity_budgets
from .coordinator_support import CoordinatorMetrics
from .coordinator_tasks import default_rejection_metrics, derive_rejection_metrics
from .telemetry import summarise_bool_coercion_metrics
from .types import (
  AdaptivePollingDiagnostics,
  BoolCoercionSummary,
  CoordinatorPerformanceSnapshot,
  CoordinatorPerformanceSnapshotCounts,
  CoordinatorPerformanceSnapshotMetrics,
  CoordinatorRejectionMetrics,
  CoordinatorResilienceSummary,
  CoordinatorSecurityAdaptiveCheck,
  CoordinatorSecurityChecks,
  CoordinatorSecurityEntityCheck,
  CoordinatorSecurityScorecard,
  CoordinatorSecurityWebhookCheck,
  EntityBudgetSummary,
  JSONMapping,
  WebhookSecurityStatus,
)

type ResilienceListField = Literal[
  "open_breakers",
  "open_breaker_ids",
  "half_open_breakers",
  "half_open_breaker_ids",
  "unknown_breakers",
  "unknown_breaker_ids",
  "rejection_breakers",
  "rejection_breaker_ids",
]

_RESILIENCE_LIST_FIELDS: Final[tuple[ResilienceListField, ...]] = (
  "open_breakers",
  "open_breaker_ids",
  "half_open_breakers",
  "half_open_breaker_ids",
  "unknown_breakers",
  "unknown_breaker_ids",
  "rejection_breakers",
  "rejection_breaker_ids",
)

_LOGGER = getLogger(__name__)


class EntityBudgetTracker:
  """Track entity budget snapshots per dog."""  # noqa: E111

  __slots__ = ("_snapshots",)  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    """Initialise the budget tracker with an empty snapshot cache."""
    self._snapshots: dict[str, EntityBudgetSnapshot] = {}

  def record(self, snapshot: EntityBudgetSnapshot) -> None:  # noqa: E111
    """Store the latest snapshot for a dog."""

    self._snapshots[snapshot.dog_id] = snapshot

  def saturation(self) -> float:  # noqa: E111
    """Return aggregate utilisation across all tracked dogs."""

    if not self._snapshots:
      return 0.0  # noqa: E111

    total_capacity = sum(snapshot.capacity for snapshot in self._snapshots.values())
    if total_capacity <= 0:
      return 0.0  # noqa: E111

    total_allocated = sum(
      snapshot.total_allocated for snapshot in self._snapshots.values()
    )
    return max(0.0, min(1.0, total_allocated / total_capacity))

  def summary(self) -> EntityBudgetSummary:  # noqa: E111
    """Return a diagnostics friendly summary."""

    return summarize_entity_budgets(self._snapshots.values())

  def snapshots(self) -> Iterable[EntityBudgetSnapshot]:  # noqa: E111
    """Expose raw snapshots (used in diagnostics)."""

    return tuple(self._snapshots.values())


def build_performance_snapshot(
  *,
  metrics: CoordinatorMetrics,
  adaptive: AdaptivePollingDiagnostics,
  entity_budget: EntityBudgetSummary,
  update_interval: float,
  last_update_time: datetime | None,
  last_update_success: bool,
  webhook_status: WebhookSecurityStatus,
  resilience: CoordinatorResilienceSummary | None = None,
) -> CoordinatorPerformanceSnapshot:
  """Generate the coordinator performance snapshot payload."""  # noqa: E111

  last_update = last_update_time.isoformat() if last_update_time else None  # noqa: E111

  update_counts: CoordinatorPerformanceSnapshotCounts = {  # noqa: E111
    "total": metrics.update_count,
    "successful": metrics.successful_cycles,
    "failed": metrics.failed_cycles,
  }
  performance_metrics: CoordinatorPerformanceSnapshotMetrics = {  # noqa: E111
    "last_update": last_update,
    "last_update_success": last_update_success,
    "success_rate": round(metrics.success_rate_percent, 2),
    "consecutive_errors": metrics.consecutive_errors,
    "update_interval_s": round(update_interval, 3),
    "current_cycle_ms": adaptive.get("current_interval_ms"),
    "rejected_call_count": 0,
    "rejection_breaker_count": 0,
    "rejection_rate": None,
    "last_rejection_time": None,
    "last_rejection_breaker_id": None,
    "last_rejection_breaker_name": None,
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
  adaptive_snapshot = cast(AdaptivePollingDiagnostics, dict(adaptive))  # noqa: E111
  entity_budget_snapshot = cast(EntityBudgetSummary, dict(entity_budget))  # noqa: E111
  webhook_snapshot = cast(WebhookSecurityStatus, dict(webhook_status))  # noqa: E111

  snapshot: CoordinatorPerformanceSnapshot = {  # noqa: E111
    "update_counts": update_counts,
    "performance_metrics": performance_metrics,
    "adaptive_polling": adaptive_snapshot,
    "entity_budget": entity_budget_snapshot,
    "webhook_security": webhook_snapshot,
  }

  rejection_metrics: CoordinatorRejectionMetrics = default_rejection_metrics()  # noqa: E111

  if resilience:  # noqa: E111
    resilience_payload = _normalise_resilience_summary(resilience)
    rejection_metrics.update(derive_rejection_metrics(resilience_payload))
    snapshot["resilience_summary"] = resilience_payload

  snapshot["rejection_metrics"] = rejection_metrics  # noqa: E111
  _apply_rejection_metrics_to_performance(  # noqa: E111
    performance_metrics,
    rejection_metrics,
  )

  telemetry_module = sys.modules.get(  # noqa: E111
    "custom_components.pawcontrol.telemetry",
  )
  bool_summary: BoolCoercionSummary = summarise_bool_coercion_metrics()  # noqa: E111
  if telemetry_module is not None and hasattr(  # noqa: E111
    telemetry_module,
    "summarise_bool_coercion_metrics",
  ):
    summary_func = cast(
      Callable[[], BoolCoercionSummary],
      telemetry_module.summarise_bool_coercion_metrics,
    )
    module_summary = summary_func()
    if (
      module_summary.get("total") or module_summary.get("reset_count")
    ) and module_summary.get("total", 0) >= bool_summary.get("total", 0):
      bool_summary = module_summary  # noqa: E111
  snapshot["bool_coercion"] = bool_summary  # noqa: E111

  return snapshot  # noqa: E111


def _coerce_float(value: Any, default: float) -> float:
  """Return a finite float or the provided default."""  # noqa: E111

  try:  # noqa: E111
    number = float(value)
  except ValueError:  # noqa: E111
    return default
  except TypeError:  # noqa: E111
    return default

  if not isfinite(number):  # noqa: E111
    return default

  return number  # noqa: E111


def _normalise_resilience_summary(
  summary: CoordinatorResilienceSummary | Mapping[str, object],
) -> CoordinatorResilienceSummary:
  """Return a resilience summary with stable string list payloads."""  # noqa: E111

  payload = cast(CoordinatorResilienceSummary, dict(summary))  # noqa: E111

  for field in _RESILIENCE_LIST_FIELDS:  # noqa: E111
    payload[field] = _coerce_string_list(payload.get(field))

  return payload  # noqa: E111


def _coerce_string_list(value: object) -> list[str]:
  """Return a list of strings for resilience diagnostics fields."""  # noqa: E111

  if value is None:  # noqa: E111
    return []

  if isinstance(value, str | bytes | bytearray):  # noqa: E111
    return [_stringify_resilience_value(value)]

  if isinstance(value, Iterable):  # noqa: E111
    items: list[str] = []
    for item in value:
      if item is None:  # noqa: E111
        continue
      items.append(_stringify_resilience_value(item))  # noqa: E111
    return items

  return [_stringify_resilience_value(value)]  # noqa: E111


def _stringify_resilience_value(value: object) -> str:
  """Convert resilience identifiers to safe diagnostic strings."""  # noqa: E111

  if isinstance(value, str):  # noqa: E111
    return value
  if isinstance(value, bytes | bytearray):  # noqa: E111
    try:
      return value.decode()  # noqa: E111
    except Exception:  # pragma: no cover - defensive fallback
      return value.decode(errors="ignore")  # noqa: E111
  return str(value)  # noqa: E111


def _apply_rejection_metrics_to_performance(
  performance_metrics: CoordinatorPerformanceSnapshotMetrics,
  rejection_metrics: CoordinatorRejectionMetrics,
) -> None:
  """Merge rejection diagnostics into the performance snapshot payload."""  # noqa: E111

  performance_metrics.update(  # noqa: E111
    {
      "rejected_call_count": rejection_metrics["rejected_call_count"],
      "rejection_breaker_count": rejection_metrics["rejection_breaker_count"],
      "rejection_rate": rejection_metrics["rejection_rate"],
      "last_rejection_time": rejection_metrics["last_rejection_time"],
      "last_rejection_breaker_id": rejection_metrics["last_rejection_breaker_id"],
      "last_rejection_breaker_name": rejection_metrics["last_rejection_breaker_name"],
      "open_breaker_count": rejection_metrics["open_breaker_count"],
      "half_open_breaker_count": rejection_metrics["half_open_breaker_count"],
      "unknown_breaker_count": rejection_metrics["unknown_breaker_count"],
      "open_breakers": list(rejection_metrics["open_breakers"]),
      "open_breaker_ids": list(rejection_metrics["open_breaker_ids"]),
      "half_open_breakers": list(rejection_metrics["half_open_breakers"]),
      "half_open_breaker_ids": list(rejection_metrics["half_open_breaker_ids"]),
      "unknown_breakers": list(rejection_metrics["unknown_breakers"]),
      "unknown_breaker_ids": list(rejection_metrics["unknown_breaker_ids"]),
      "rejection_breaker_ids": list(rejection_metrics["rejection_breaker_ids"]),
      "rejection_breakers": list(rejection_metrics["rejection_breakers"]),
    },
  )


def build_security_scorecard(
  *,
  adaptive: JSONMapping,
  entity_summary: JSONMapping,
  webhook_status: WebhookSecurityStatus,
) -> CoordinatorSecurityScorecard:
  """Return a pass/fail scorecard for coordinator safety checks."""  # noqa: E111

  target_ms = _coerce_float(adaptive.get("target_cycle_ms"), 200.0)  # noqa: E111
  if target_ms <= 0:  # noqa: E111
    target_ms = 200.0

  current_ms = _coerce_float(adaptive.get("current_interval_ms"), target_ms)  # noqa: E111
  if current_ms < 0:  # noqa: E111
    current_ms = target_ms

  threshold_ms = 200.0  # noqa: E111
  adaptive_pass = current_ms <= threshold_ms  # noqa: E111
  adaptive_check: CoordinatorSecurityAdaptiveCheck = {  # noqa: E111
    "pass": adaptive_pass,
    "current_ms": current_ms,
    "target_ms": target_ms,
    "threshold_ms": threshold_ms,
  }
  if not adaptive_pass:  # noqa: E111
    adaptive_check["reason"] = "Update interval exceeds 200ms target"

  peak_utilisation = _coerce_float(  # noqa: E111
    entity_summary.get("peak_utilization"),
    0.0,
  )
  peak_utilisation = max(0.0, min(100.0, peak_utilisation))  # noqa: E111
  entity_threshold = 95.0  # noqa: E111
  entity_pass = peak_utilisation <= entity_threshold  # noqa: E111
  entity_summary_snapshot = cast(EntityBudgetSummary, dict(entity_summary))  # noqa: E111
  entity_check: CoordinatorSecurityEntityCheck = {  # noqa: E111
    "pass": entity_pass,
    "summary": entity_summary_snapshot,
    "threshold_percent": entity_threshold,
  }
  if not entity_pass:  # noqa: E111
    entity_check["reason"] = "Entity budget utilisation above safe threshold"

  webhook_pass = (not webhook_status.get("configured")) or bool(  # noqa: E111
    webhook_status.get("secure"),
  )
  webhook_payload = dict(webhook_status)  # noqa: E111
  webhook_payload.setdefault("configured", False)  # noqa: E111
  webhook_payload.setdefault("secure", False)  # noqa: E111
  webhook_payload.setdefault("hmac_ready", False)  # noqa: E111
  webhook_payload.setdefault("insecure_configs", ())  # noqa: E111
  webhook_snapshot = cast(WebhookSecurityStatus, webhook_payload)  # noqa: E111
  webhook_check: CoordinatorSecurityWebhookCheck = {  # noqa: E111
    "pass": webhook_pass,
    "configured": webhook_snapshot["configured"],
    "secure": webhook_snapshot["secure"],
    "hmac_ready": webhook_snapshot["hmac_ready"],
    "insecure_configs": webhook_snapshot["insecure_configs"],
  }
  if "error" in webhook_snapshot:  # noqa: E111
    webhook_check["error"] = webhook_snapshot["error"]
  if not webhook_pass:  # noqa: E111
    webhook_check.setdefault(
      "reason",
      "Webhook configurations missing HMAC protection",
    )

  checks: CoordinatorSecurityChecks = {  # noqa: E111
    "adaptive_polling": adaptive_check,
    "entity_budget": entity_check,
    "webhooks": webhook_check,
  }
  all_checks = (  # noqa: E111
    checks["adaptive_polling"],
    checks["entity_budget"],
    checks["webhooks"],
  )
  status_literal: Literal["pass", "fail"] = (  # noqa: E111
    "pass" if all(check["pass"] for check in all_checks) else "fail"
  )
  scorecard: CoordinatorSecurityScorecard = {  # noqa: E111
    "status": status_literal,
    "checks": checks,
  }
  return scorecard  # noqa: E111


def normalise_webhook_status(manager: Any) -> WebhookSecurityStatus:
  """Normalise webhook security payloads coming from notification manager."""  # noqa: E111

  if manager is None or not hasattr(manager, "webhook_security_status"):  # noqa: E111
    return {
      "configured": False,
      "secure": True,
      "hmac_ready": False,
      "insecure_configs": (),
    }

  try:  # noqa: E111
    status = dict(manager.webhook_security_status())
  except Exception as err:  # pragma: no cover - defensive logging  # noqa: E111
    _LOGGER.debug("Webhook security inspection failed: %s", err)
    return {
      "configured": True,
      "secure": False,
      "hmac_ready": False,
      "insecure_configs": (),
      "error": str(err),
    }

  status.setdefault("configured", False)  # noqa: E111
  status.setdefault("secure", False)  # noqa: E111
  status.setdefault("hmac_ready", False)  # noqa: E111
  insecure = status.get("insecure_configs", ())  # noqa: E111
  if isinstance(insecure, Iterable) and not isinstance(  # noqa: E111
    insecure,
    str | bytes | bytearray,
  ):
    status["insecure_configs"] = tuple(insecure)
  else:  # noqa: E111
    status["insecure_configs"] = (insecure,) if insecure else ()
  return cast(WebhookSecurityStatus, status)  # noqa: E111
