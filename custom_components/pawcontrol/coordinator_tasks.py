"""Coordinator task helpers.

Simplified: background maintenance hooks are now no-ops.
"""

from __future__ import annotations

from typing import Any, cast

from .types import (
  CoordinatorRejectionMetrics,
  EntityFactoryGuardMetricsSnapshot,
  HelperManagerGuardMetrics,
  RejectionMetricsSource,
)


def default_rejection_metrics() -> CoordinatorRejectionMetrics:
  """Return zeroed rejection metrics payload."""

  return {
    "schema_version": 4,
    "rejected_call_count": 0,
    "rejection_breaker_count": 0,
    "rejection_rate": None,
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
  base: CoordinatorRejectionMetrics,
  updates: RejectionMetricsSource | dict[str, Any] | None,
) -> CoordinatorRejectionMetrics:
  """Merge rejection metrics with defensive defaults."""

  merged = dict(base)
  if isinstance(updates, dict):
    merged.update(updates)
  merged.setdefault("schema_version", 4)
  return cast(CoordinatorRejectionMetrics, merged)


def derive_rejection_metrics(payload: Any) -> CoordinatorRejectionMetrics:
  """Derive rejection metrics from arbitrary payload."""

  if isinstance(payload, dict):
    return merge_rejection_metric_values(default_rejection_metrics(), payload)
  return default_rejection_metrics()


def resolve_service_guard_metrics(payload: Any) -> HelperManagerGuardMetrics:
  """Return normalised service guard metrics."""

  if isinstance(payload, dict):
    reasons = payload.get("reasons")
    last_results = payload.get("last_results")
    return {
      "executed": int(payload.get("executed", 0)),
      "skipped": int(payload.get("skipped", 0)),
      "reasons": reasons if isinstance(reasons, dict) else {},
      "last_results": last_results if isinstance(last_results, list) else [],
    }

  return {
    "executed": 0,
    "skipped": 0,
    "reasons": {},
    "last_results": [],
  }


def resolve_entity_factory_guard_metrics(
  payload: Any,
) -> EntityFactoryGuardMetricsSnapshot:
  """Return simplified entity factory guard metrics snapshot."""

  if isinstance(payload, dict):
    return cast(EntityFactoryGuardMetricsSnapshot, dict(payload))
  return cast(EntityFactoryGuardMetricsSnapshot, {})


async def run_maintenance(*args: Any) -> None:
  """No-op maintenance hook."""

  del args


def ensure_background_task(*args: Any) -> None:
  """No-op background-task hook."""

  del args


async def shutdown(*args: Any) -> None:
  """No-op shutdown hook."""

  del args
