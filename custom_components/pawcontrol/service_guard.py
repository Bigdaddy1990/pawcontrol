"""Service guard telemetry models for Home Assistant service invocations."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any, NotRequired, Required, TypedDict, TypeVar, cast

from .types import JSONLikeMapping, JSONMutableMapping, JSONValue


@dataclass(slots=True, frozen=True)
class ServiceGuardResult:
  """Snapshot describing a guarded Home Assistant service invocation."""  # noqa: E111

  domain: str  # noqa: E111
  service: str  # noqa: E111
  executed: bool  # noqa: E111
  reason: str | None = None  # noqa: E111
  description: str | None = None  # noqa: E111

  def to_mapping(self) -> ServiceGuardResultPayload:  # noqa: E111
    """Return a serialisable mapping for diagnostics exports."""

    payload: ServiceGuardResultPayload = {
      "domain": self.domain,
      "service": self.service,
      "executed": self.executed,
    }

    if self.reason is not None:
      payload["reason"] = self.reason  # noqa: E111

    if self.description is not None:
      payload["description"] = self.description  # noqa: E111

    return payload

  def __bool__(
    self,
  ) -> bool:  # pragma: no cover - bool protocol passthrough  # noqa: E111
    """Allow guard results to be treated as booleans in guard checks."""

    return self.executed


class ServiceGuardResultPayload(TypedDict, total=False):
  """JSON-compatible payload describing a guarded service invocation."""  # noqa: E111

  executed: Required[bool]  # noqa: E111
  domain: NotRequired[str]  # noqa: E111
  service: NotRequired[str]  # noqa: E111
  reason: NotRequired[str]  # noqa: E111
  description: NotRequired[str]  # noqa: E111


type ServiceGuardResultHistory = list[ServiceGuardResultPayload]
"""Ordered telemetry entries for guarded service invocations."""


class ServiceGuardSummary(TypedDict, total=False):
  """Aggregated metrics describing guarded Home Assistant service calls."""  # noqa: E111

  executed: int  # noqa: E111
  skipped: int  # noqa: E111
  reasons: dict[str, int]  # noqa: E111
  results: ServiceGuardResultHistory  # noqa: E111


class ServiceGuardMetricsSnapshot(TypedDict, total=False):
  """Aggregated runtime metrics for guarded service calls."""  # noqa: E111

  executed: int  # noqa: E111
  skipped: int  # noqa: E111
  reasons: dict[str, int]  # noqa: E111
  last_results: ServiceGuardResultHistory  # noqa: E111


TGuardResult = TypeVar("TGuardResult", bound=ServiceGuardResult)


@dataclass(slots=True, frozen=True)
class ServiceGuardSnapshot[TGuardResult: ServiceGuardResult]:
  """Aggregated telemetry derived from a guard result sequence."""  # noqa: E111

  results: tuple[TGuardResult, ...]  # noqa: E111
  executed: int  # noqa: E111
  skipped: int  # noqa: E111
  reasons: dict[str, int]  # noqa: E111

  @classmethod  # noqa: E111
  def from_sequence(  # noqa: E111
    cls,
    results: Sequence[TGuardResult],
  ) -> ServiceGuardSnapshot[TGuardResult]:
    """Create a snapshot from an ordered guard result sequence."""

    ordered = tuple(results)
    executed = sum(1 for entry in ordered if entry.executed)
    skipped = len(ordered) - executed
    reasons: dict[str, int] = {}
    for entry in ordered:
      if entry.executed:  # noqa: E111
        continue
      reason_key = entry.reason or "unknown"  # noqa: E111
      reasons[reason_key] = reasons.get(reason_key, 0) + 1  # noqa: E111

    return cls(ordered, executed, skipped, reasons)

  @staticmethod  # noqa: E111
  def zero_metrics() -> ServiceGuardMetricsSnapshot:  # noqa: E111
    """Return an empty metrics payload for service guard aggregation."""

    return {
      "executed": 0,
      "skipped": 0,
      "reasons": {},
      "last_results": [],
    }

  def history(self) -> ServiceGuardResultHistory:  # noqa: E111
    """Serialise the guard result history for diagnostics exports."""

    return [entry.to_mapping() for entry in self.results]

  def to_summary(self) -> ServiceGuardSummary:  # noqa: E111
    """Return a diagnostics summary payload for the aggregated guard data."""

    return {
      "executed": self.executed,
      "skipped": self.skipped,
      "reasons": dict(self.reasons),
      "results": self.history(),
    }

  def to_metrics(self) -> ServiceGuardMetricsSnapshot:  # noqa: E111
    """Return a metrics snapshot representing the aggregated guard data."""

    metrics = self.zero_metrics()
    metrics["executed"] = self.executed
    metrics["skipped"] = self.skipped
    metrics["reasons"] = dict(self.reasons)
    metrics["last_results"] = self.history()
    return metrics

  def accumulate(  # noqa: E111
    self,
    metrics: MutableMapping[str, JSONValue],
  ) -> ServiceGuardMetricsSnapshot:
    """Accumulate snapshot counts into ``metrics`` and return the payload."""

    executed_value = metrics.get("executed", 0)
    executed = _coerce_int(executed_value)
    metrics["executed"] = executed + self.executed

    skipped_value = metrics.get("skipped", 0)
    skipped = _coerce_int(skipped_value)
    metrics["skipped"] = skipped + self.skipped

    reasons_payload_raw = metrics.get("reasons")
    if isinstance(reasons_payload_raw, MutableMapping):
      reasons_payload = cast(  # noqa: E111
        MutableMapping[str, JSONValue],
        reasons_payload_raw,
      )
    else:
      reasons_payload = cast(JSONMutableMapping, {})  # noqa: E111
      metrics["reasons"] = reasons_payload  # noqa: E111

    for reason_key, count in self.reasons.items():
      existing_value = reasons_payload.get(reason_key)  # noqa: E111
      existing = (  # noqa: E111
        int(existing_value)
        if isinstance(
          existing_value,
          int | float,
        )
        else 0
      )
      reasons_payload[reason_key] = existing + count  # noqa: E111

    metrics["last_results"] = cast(JSONValue, list(self.history()))

    reasons_snapshot = metrics.get("reasons")
    reasons_dict: dict[str, int]
    if isinstance(reasons_snapshot, Mapping):
      reasons_dict = {  # noqa: E111
        key: int(value) if isinstance(value, int | float) else 0
        for key, value in reasons_snapshot.items()
      }
    else:
      reasons_dict = {}  # noqa: E111

    last_results_raw = metrics.get("last_results", [])
    last_results = (
      last_results_raw if isinstance(last_results_raw, list) else list(self.history())
    )

    return {
      "executed": _coerce_int(metrics.get("executed", 0)),
      "skipped": _coerce_int(metrics.get("skipped", 0)),
      "reasons": reasons_dict,
      "last_results": cast(ServiceGuardResultHistory, last_results),
    }


def normalise_guard_result_payload(
  payload: JSONLikeMapping,
) -> ServiceGuardResultPayload:
  """Return a JSON-compatible payload for a guard result mapping."""  # noqa: E111

  result: ServiceGuardResultPayload = {  # noqa: E111
    "executed": bool(payload.get("executed")),
  }

  domain = payload.get("domain")  # noqa: E111
  if isinstance(domain, str) and domain:  # noqa: E111
    result["domain"] = domain

  service = payload.get("service")  # noqa: E111
  if isinstance(service, str) and service:  # noqa: E111
    result["service"] = service

  reason = payload.get("reason")  # noqa: E111
  if isinstance(reason, str) and reason:  # noqa: E111
    result["reason"] = reason

  description = payload.get("description")  # noqa: E111
  if isinstance(description, str) and description:  # noqa: E111
    result["description"] = description

  return result  # noqa: E111


def _coerce_int(value: object) -> int:
  """Return ``value`` coerced to an ``int`` when safe."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return int(value)

  if isinstance(value, int | float):  # noqa: E111
    return int(value)

  if isinstance(value, str):  # noqa: E111
    try:
      return int(value)  # noqa: E111
    except ValueError:
      return 0  # noqa: E111

  return 0  # noqa: E111


def normalise_guard_history(payload: Any) -> ServiceGuardResultHistory:
  """Convert an arbitrary sequence into a guard result history payload."""  # noqa: E111

  if not isinstance(payload, Sequence) or isinstance(  # noqa: E111
    payload,
    str | bytes | bytearray,
  ):
    return []

  history: ServiceGuardResultHistory = []  # noqa: E111
  for entry in payload:  # noqa: E111
    if isinstance(entry, ServiceGuardResult):
      history.append(entry.to_mapping())  # noqa: E111
    elif isinstance(entry, Mapping):
      history.append(normalise_guard_result_payload(entry))  # noqa: E111

  return history  # noqa: E111
