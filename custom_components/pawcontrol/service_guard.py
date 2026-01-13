"""Service guard telemetry models for Home Assistant service invocations."""
from __future__ import annotations

from collections.abc import Mapping
from collections.abc import MutableMapping
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from typing import cast
from typing import NotRequired
from typing import Required
from typing import TypedDict

from .types import JSONLikeMapping
from .types import JSONMutableMapping
from .types import JSONValue


@dataclass(slots=True, frozen=True)
class ServiceGuardResult:
    """Snapshot describing a guarded Home Assistant service invocation."""

    domain: str
    service: str
    executed: bool
    reason: str | None = None
    description: str | None = None

    def to_mapping(self) -> ServiceGuardResultPayload:
        """Return a serialisable mapping for diagnostics exports."""

        payload: ServiceGuardResultPayload = {
            'domain': self.domain,
            'service': self.service,
            'executed': self.executed,
        }

        if self.reason is not None:
            payload['reason'] = self.reason

        if self.description is not None:
            payload['description'] = self.description

        return payload

    def __bool__(self) -> bool:  # pragma: no cover - bool protocol passthrough
        """Allow guard results to be treated as booleans in guard checks."""

        return self.executed


class ServiceGuardResultPayload(TypedDict, total=False):
    """JSON-compatible payload describing a guarded service invocation."""

    executed: Required[bool]
    domain: NotRequired[str]
    service: NotRequired[str]
    reason: NotRequired[str]
    description: NotRequired[str]


type ServiceGuardResultHistory = list[ServiceGuardResultPayload]
"""Ordered telemetry entries for guarded service invocations."""


class ServiceGuardSummary(TypedDict, total=False):
    """Aggregated metrics describing guarded Home Assistant service calls."""

    executed: int
    skipped: int
    reasons: dict[str, int]
    results: ServiceGuardResultHistory


class ServiceGuardMetricsSnapshot(TypedDict, total=False):
    """Aggregated runtime metrics for guarded service calls."""

    executed: int
    skipped: int
    reasons: dict[str, int]
    last_results: ServiceGuardResultHistory


@dataclass(slots=True, frozen=True)
class ServiceGuardSnapshot[TGuardResult: ServiceGuardResult]:
    """Aggregated telemetry derived from a guard result sequence."""

    results: tuple[TGuardResult, ...]
    executed: int
    skipped: int
    reasons: dict[str, int]

    @classmethod
    def from_sequence(
        cls, results: Sequence[TGuardResult]
    ) -> ServiceGuardSnapshot[TGuardResult]:
        """Create a snapshot from an ordered guard result sequence."""

        ordered = tuple(results)
        executed = sum(1 for entry in ordered if entry.executed)
        skipped = len(ordered) - executed
        reasons: dict[str, int] = {}
        for entry in ordered:
            if entry.executed:
                continue
            reason_key = entry.reason or 'unknown'
            reasons[reason_key] = reasons.get(reason_key, 0) + 1

        return cls(ordered, executed, skipped, reasons)

    @staticmethod
    def zero_metrics() -> ServiceGuardMetricsSnapshot:
        """Return an empty metrics payload for service guard aggregation."""

        return {
            'executed': 0,
            'skipped': 0,
            'reasons': {},
            'last_results': [],
        }

    def history(self) -> ServiceGuardResultHistory:
        """Serialise the guard result history for diagnostics exports."""

        return [entry.to_mapping() for entry in self.results]

    def to_summary(self) -> ServiceGuardSummary:
        """Return a diagnostics summary payload for the aggregated guard data."""

        return {
            'executed': self.executed,
            'skipped': self.skipped,
            'reasons': dict(self.reasons),
            'results': self.history(),
        }

    def to_metrics(self) -> ServiceGuardMetricsSnapshot:
        """Return a metrics snapshot representing the aggregated guard data."""

        metrics = self.zero_metrics()
        metrics['executed'] = self.executed
        metrics['skipped'] = self.skipped
        metrics['reasons'] = dict(self.reasons)
        metrics['last_results'] = self.history()
        return metrics

    def accumulate(
        self, metrics: MutableMapping[str, JSONValue]
    ) -> ServiceGuardMetricsSnapshot:
        """Accumulate snapshot counts into ``metrics`` and return the payload."""

        executed_value = metrics.get('executed', 0)
        executed = _coerce_int(executed_value)
        metrics['executed'] = executed + self.executed

        skipped_value = metrics.get('skipped', 0)
        skipped = _coerce_int(skipped_value)
        metrics['skipped'] = skipped + self.skipped

        reasons_payload_raw = metrics.get('reasons')
        if isinstance(reasons_payload_raw, MutableMapping):
            reasons_payload = cast(MutableMapping[str, JSONValue], reasons_payload_raw)
        else:
            reasons_payload = cast(JSONMutableMapping, {})
            metrics['reasons'] = reasons_payload

        for reason_key, count in self.reasons.items():
            existing_value = reasons_payload.get(reason_key)
            existing = (
                int(existing_value) if isinstance(existing_value, (int, float)) else 0
            )
            reasons_payload[reason_key] = existing + count

        metrics['last_results'] = cast(JSONValue, list(self.history()))

        reasons_snapshot = metrics.get('reasons')
        reasons_dict: dict[str, int]
        if isinstance(reasons_snapshot, Mapping):
            reasons_dict = {
                key: int(value) if isinstance(value, (int, float)) else 0
                for key, value in reasons_snapshot.items()
            }
        else:
            reasons_dict = {}

        last_results_raw = metrics.get('last_results', [])
        last_results = (
            last_results_raw
            if isinstance(last_results_raw, list)
            else list(self.history())
        )

        return {
            'executed': _coerce_int(metrics.get('executed', 0)),
            'skipped': _coerce_int(metrics.get('skipped', 0)),
            'reasons': reasons_dict,
            'last_results': cast(ServiceGuardResultHistory, last_results),
        }


def normalise_guard_result_payload(
    payload: JSONLikeMapping,
) -> ServiceGuardResultPayload:
    """Return a JSON-compatible payload for a guard result mapping."""

    result: ServiceGuardResultPayload = {'executed': bool(payload.get('executed'))}

    domain = payload.get('domain')
    if isinstance(domain, str) and domain:
        result['domain'] = domain

    service = payload.get('service')
    if isinstance(service, str) and service:
        result['service'] = service

    reason = payload.get('reason')
    if isinstance(reason, str) and reason:
        result['reason'] = reason

    description = payload.get('description')
    if isinstance(description, str) and description:
        result['description'] = description

    return result


def _coerce_int(value: object) -> int:
    """Return ``value`` coerced to an ``int`` when safe."""

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0

    return 0


def normalise_guard_history(payload: Any) -> ServiceGuardResultHistory:
    """Convert an arbitrary sequence into a guard result history payload."""

    if not isinstance(payload, Sequence) or isinstance(
        payload, str | bytes | bytearray
    ):
        return []

    history: ServiceGuardResultHistory = []
    for entry in payload:
        if isinstance(entry, ServiceGuardResult):
            history.append(entry.to_mapping())
        elif isinstance(entry, Mapping):
            history.append(normalise_guard_result_payload(entry))

    return history
