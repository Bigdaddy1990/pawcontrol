"""Observability helpers that keep :mod:`coordinator` concise."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from logging import getLogger
from math import isfinite
from typing import Any

from .coordinator_runtime import EntityBudgetSnapshot, summarize_entity_budgets
from .coordinator_tasks import default_rejection_metrics, derive_rejection_metrics
from .types import CoordinatorRejectionMetrics

_LOGGER = getLogger(__name__)


class EntityBudgetTracker:
    """Track entity budget snapshots per dog."""

    __slots__ = ("_snapshots",)

    def __init__(self) -> None:
        """Initialise the budget tracker with an empty snapshot cache."""
        self._snapshots: dict[str, EntityBudgetSnapshot] = {}

    def record(self, snapshot: EntityBudgetSnapshot) -> None:
        """Store the latest snapshot for a dog."""

        self._snapshots[snapshot.dog_id] = snapshot

    def saturation(self) -> float:
        """Return aggregate utilisation across all tracked dogs."""

        if not self._snapshots:
            return 0.0

        total_capacity = sum(snapshot.capacity for snapshot in self._snapshots.values())
        if total_capacity <= 0:
            return 0.0

        total_allocated = sum(
            snapshot.total_allocated for snapshot in self._snapshots.values()
        )
        return max(0.0, min(1.0, total_allocated / total_capacity))

    def summary(self) -> dict[str, Any]:
        """Return a diagnostics friendly summary."""

        return summarize_entity_budgets(self._snapshots.values())

    def snapshots(self) -> Iterable[EntityBudgetSnapshot]:
        """Expose raw snapshots (used in diagnostics)."""

        return tuple(self._snapshots.values())


def build_performance_snapshot(
    *,
    metrics: Any,
    adaptive: Mapping[str, Any],
    entity_budget: Mapping[str, Any],
    update_interval: float,
    last_update_time: datetime | None,
    last_update_success: bool,
    webhook_status: Mapping[str, Any],
    resilience: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate the coordinator performance snapshot payload."""

    last_update = last_update_time.isoformat() if last_update_time else None

    snapshot = {
        "update_counts": {
            "total": metrics.update_count,
            "successful": metrics.successful_cycles,
            "failed": metrics.failed_cycles,
        },
        "performance_metrics": {
            "last_update": last_update,
            "last_update_success": last_update_success,
            "success_rate": round(metrics.success_rate_percent, 2),
            "consecutive_errors": metrics.consecutive_errors,
            "update_interval_s": round(update_interval, 3),
            "current_cycle_ms": adaptive.get("current_interval_ms"),
        },
        "adaptive_polling": dict(adaptive),
        "entity_budget": dict(entity_budget),
        "webhook_security": dict(webhook_status),
    }

    rejection_metrics: CoordinatorRejectionMetrics = default_rejection_metrics()

    if resilience:
        resilience_payload = dict(resilience)

        list_fields = (
            "open_breakers",
            "open_breaker_ids",
            "half_open_breakers",
            "half_open_breaker_ids",
            "unknown_breakers",
            "unknown_breaker_ids",
            "rejection_breakers",
            "rejection_breaker_ids",
        )

        for field in list_fields:
            value = resilience_payload.get(field)
            if isinstance(value, list):
                continue
            if value is None:
                resilience_payload[field] = []
                continue
            if isinstance(value, Iterable) and not isinstance(
                value, str | bytes | bytearray
            ):
                resilience_payload[field] = list(value)
            else:
                resilience_payload[field] = [value]

        rejection_metrics.update(derive_rejection_metrics(resilience_payload))
        snapshot["resilience_summary"] = resilience_payload

    snapshot["rejection_metrics"] = dict(rejection_metrics)
    snapshot["performance_metrics"].update(
        {
            key: value
            for key, value in rejection_metrics.items()
            if key != "schema_version"
        }
    )

    return snapshot


def _coerce_float(value: Any, default: float) -> float:
    """Return a finite float or the provided default."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if not isfinite(number):
        return default

    return number


def build_security_scorecard(
    *,
    adaptive: Mapping[str, Any],
    entity_summary: Mapping[str, Any],
    webhook_status: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a pass/fail scorecard for coordinator safety checks."""

    target_ms = _coerce_float(adaptive.get("target_cycle_ms"), 200.0)
    if target_ms <= 0:
        target_ms = 200.0

    current_ms = _coerce_float(adaptive.get("current_interval_ms"), target_ms)
    if current_ms < 0:
        current_ms = target_ms

    threshold_ms = 200.0
    adaptive_pass = current_ms <= threshold_ms
    adaptive_check: dict[str, Any] = {
        "pass": adaptive_pass,
        "current_ms": current_ms,
        "target_ms": target_ms,
        "threshold_ms": threshold_ms,
    }
    if not adaptive_pass:
        adaptive_check["reason"] = "Update interval exceeds 200ms target"

    peak_utilisation = _coerce_float(entity_summary.get("peak_utilization"), 0.0)
    peak_utilisation = max(0.0, min(100.0, peak_utilisation))
    entity_threshold = 95.0
    entity_pass = peak_utilisation <= entity_threshold
    entity_check: dict[str, Any] = {
        "pass": entity_pass,
        "summary": dict(entity_summary),
        "threshold_percent": entity_threshold,
    }
    if not entity_pass:
        entity_check["reason"] = "Entity budget utilisation above safe threshold"

    webhook_pass = (not webhook_status.get("configured")) or bool(
        webhook_status.get("secure")
    )
    webhook_check: dict[str, Any] = {"pass": webhook_pass, **webhook_status}
    if not webhook_pass:
        webhook_check.setdefault(
            "reason", "Webhook configurations missing HMAC protection"
        )

    checks = {
        "adaptive_polling": adaptive_check,
        "entity_budget": entity_check,
        "webhooks": webhook_check,
    }
    status = "pass" if all(check["pass"] for check in checks.values()) else "fail"
    return {"status": status, "checks": checks}


def normalise_webhook_status(manager: Any) -> dict[str, Any]:
    """Normalise webhook security payloads coming from notification manager."""

    if manager is None or not hasattr(manager, "webhook_security_status"):
        return {
            "configured": False,
            "secure": True,
            "hmac_ready": False,
            "insecure_configs": (),
        }

    try:
        status = dict(manager.webhook_security_status())
    except Exception as err:  # pragma: no cover - defensive logging
        _LOGGER.debug("Webhook security inspection failed: %s", err)
        return {
            "configured": True,
            "secure": False,
            "hmac_ready": False,
            "insecure_configs": (),
            "error": str(err),
        }

    status.setdefault("configured", False)
    status.setdefault("secure", False)
    status.setdefault("hmac_ready", False)
    insecure = status.get("insecure_configs", ())
    if isinstance(insecure, Iterable) and not isinstance(
        insecure, str | bytes | bytearray
    ):
        status["insecure_configs"] = tuple(insecure)
    else:
        status["insecure_configs"] = (insecure,) if insecure else ()
    return status
