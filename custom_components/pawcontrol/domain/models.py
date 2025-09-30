"""Domain snapshot models for PawControl."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


@dataclass(slots=True)
class ModuleSnapshot:
    """Normalized representation of a single module payload."""

    name: str
    error: str | None = None
    latency: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    received_at: datetime | None = None
    status: str = "unknown"

    def with_defaults(
        self,
        *,
        name: str,
        fallback_status: str,
        received_at: datetime,
        latency: float | None,
    ) -> "ModuleSnapshot":
        """Return a copy populated with orchestration runtime defaults."""

        return ModuleSnapshot(
            name=name or self.name,
            status=self.status or fallback_status,
            payload=dict(self.payload),
            error=self.error,
            received_at=self.received_at or received_at,
            latency=self.latency if self.latency is not None else latency,
        )

    @classmethod
    def empty(cls, name: str, status: str = "unknown") -> "ModuleSnapshot":
        """Create a deterministic empty snapshot for a module."""

        return cls(name=name, status=status)

    def as_dict(self) -> dict[str, Any]:
        """Convert the snapshot to the dictionary format used by entities."""

        data = dict(self.payload)
        data.setdefault("status", self.status)
        if self.error and "error" not in data:
            data["error"] = self.error
        if self.received_at and "last_update" not in data:
            data["last_update"] = self.received_at.isoformat()
        if self.latency is not None and "latency" not in data:
            data["latency"] = self.latency
        return data


@dataclass(slots=True)
class DomainSnapshot:
    """Normalized runtime snapshot for a PawControl dog domain."""

    dog_id: str
    status: str
    dog_info: Mapping[str, Any]
    modules: dict[str, ModuleSnapshot] = field(default_factory=dict)
    last_updated: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation for downstream consumers."""

        base = {
            "dog_info": dict(self.dog_info),
            "status": self.status,
            "last_update": self.last_updated.isoformat()
            if self.last_updated
            else None,
            "modules": {name: snapshot.as_dict() for name, snapshot in self.modules.items()},
            "metadata": dict(self.metadata),
        }
        flattened_modules = {
            name: snapshot.as_dict() for name, snapshot in self.modules.items()
        }
        return {**flattened_modules, **base}
