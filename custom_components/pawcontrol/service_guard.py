"""Service guard telemetry models for Home Assistant service invocations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


@dataclass(slots=True, frozen=True)
class ServiceGuardResult:
    """Snapshot describing a guarded Home Assistant service invocation."""

    domain: str
    service: str
    executed: bool
    reason: str | None = None
    description: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        """Return a serialisable mapping for diagnostics exports."""

        payload: dict[str, Any] = {
            "domain": self.domain,
            "service": self.service,
            "executed": self.executed,
        }

        if self.reason is not None:
            payload["reason"] = self.reason

        if self.description is not None:
            payload["description"] = self.description

        return payload

    def __bool__(self) -> bool:  # pragma: no cover - bool protocol passthrough
        """Allow guard results to be treated as booleans in guard checks."""

        return self.executed


class ServiceGuardSummary(TypedDict, total=False):
    """Aggregated metrics describing guarded Home Assistant service calls."""

    executed: int
    skipped: int
    reasons: dict[str, int]
    results: list[dict[str, Any]]
