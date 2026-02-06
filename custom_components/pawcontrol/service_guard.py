"""Service guard telemetry models for Home Assistant service invocations.

Simplified to lightweight result snapshots.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any, NotRequired, Required, TypedDict, cast

from .types import JSONLikeMapping, JSONValue


@dataclass(slots=True, frozen=True)
class ServiceGuardResult:
  """Snapshot describing a guarded Home Assistant service invocation."""

  domain: str
  service: str
  executed: bool
  reason: str | None = None
  description: str | None = None

  def to_mapping(self) -> ServiceGuardResultPayload:
    payload: ServiceGuardResultPayload = {
      "domain": self.domain,
      "service": self.service,
      "executed": self.executed,
    }
    if self.reason:
      payload["reason"] = self.reason
    if self.description:
      payload["description"] = self.description
    return payload

  def __bool__(self) -> bool:  # pragma: no cover
    return self.executed


class ServiceGuardResultPayload(TypedDict, total=False):
  """JSON-compatible payload describing a guarded service invocation."""

  executed: Required[bool]
  domain: NotRequired[str]
  service: NotRequired[str]
  reason: NotRequired[str]
  description: NotRequired[str]


type ServiceGuardResultHistory = list[ServiceGuardResultPayload]


class ServiceGuardSummary(TypedDict, total=False):
  executed: int
  skipped: int
  reasons: dict[str, int]
  results: ServiceGuardResultHistory


class ServiceGuardMetricsSnapshot(TypedDict, total=False):
  executed: int
  skipped: int
  reasons: dict[str, int]
  last_results: ServiceGuardResultHistory


@dataclass(slots=True, frozen=True)
class ServiceGuardSnapshot:
  """Minimal aggregated telemetry derived from a guard result sequence."""

  results: tuple[ServiceGuardResult, ...]
  executed: int
  skipped: int
  reasons: dict[str, int]

  @classmethod
  def from_sequence(cls, results: Sequence[ServiceGuardResult]) -> ServiceGuardSnapshot:
    ordered = tuple(results)
    executed = sum(1 for entry in ordered if entry.executed)
    skipped = len(ordered) - executed
    reasons: dict[str, int] = {}
    for entry in ordered:
      if entry.executed:
        continue
      reason = entry.reason or "unknown"
      reasons[reason] = reasons.get(reason, 0) + 1
    return cls(ordered, executed, skipped, reasons)

  @staticmethod
  def zero_metrics() -> ServiceGuardMetricsSnapshot:
    return {"executed": 0, "skipped": 0, "reasons": {}, "last_results": []}

  def history(self) -> ServiceGuardResultHistory:
    return [entry.to_mapping() for entry in self.results]

  def to_summary(self) -> ServiceGuardSummary:
    return {
      "executed": self.executed,
      "skipped": self.skipped,
      "reasons": dict(self.reasons),
      "results": self.history(),
    }

  def to_metrics(self) -> ServiceGuardMetricsSnapshot:
    return {
      "executed": self.executed,
      "skipped": self.skipped,
      "reasons": dict(self.reasons),
      "last_results": self.history(),
    }

  def accumulate(
    self,
    metrics: MutableMapping[str, JSONValue],
  ) -> ServiceGuardMetricsSnapshot:
    current_executed = (
      int(metrics.get("executed", 0))
      if isinstance(metrics.get("executed", 0), int | float)
      else 0
    )
    current_skipped = (
      int(metrics.get("skipped", 0))
      if isinstance(metrics.get("skipped", 0), int | float)
      else 0
    )

    reasons_payload = metrics.get("reasons")
    reason_counts: dict[str, int] = {}
    if isinstance(reasons_payload, Mapping):
      for key, value in reasons_payload.items():
        if isinstance(key, str) and isinstance(value, int | float):
          reason_counts[key] = int(value)

    for key, value in self.reasons.items():
      reason_counts[key] = reason_counts.get(key, 0) + value

    payload: ServiceGuardMetricsSnapshot = {
      "executed": current_executed + self.executed,
      "skipped": current_skipped + self.skipped,
      "reasons": reason_counts,
      "last_results": self.history(),
    }
    metrics.update(cast(Mapping[str, JSONValue], payload))
    return payload


def normalise_guard_result_payload(
  payload: JSONLikeMapping,
) -> ServiceGuardResultPayload:
  result: ServiceGuardResultPayload = {"executed": bool(payload.get("executed"))}
  domain = payload.get("domain")
  if isinstance(domain, str) and domain:
    result["domain"] = domain
  service = payload.get("service")
  if isinstance(service, str) and service:
    result["service"] = service
  reason = payload.get("reason")
  if isinstance(reason, str) and reason:
    result["reason"] = reason
  description = payload.get("description")
  if isinstance(description, str) and description:
    result["description"] = description
  return result


def normalise_guard_history(payload: Any) -> ServiceGuardResultHistory:
  if not isinstance(payload, Sequence) or isinstance(payload, str | bytes | bytearray):
    return []

  history: ServiceGuardResultHistory = []
  for entry in payload:
    if isinstance(entry, ServiceGuardResult):
      history.append(entry.to_mapping())
    elif isinstance(entry, Mapping):
      history.append(normalise_guard_result_payload(entry))
  return history
