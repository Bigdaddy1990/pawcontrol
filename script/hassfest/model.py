"""Lightweight hassfest model implementation for tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationError:
    """Represents a validation error encountered while processing an integration."""

    error: str


@dataclass
class Config:
    """Configuration context passed to hassfest validators."""

    root: Path
    specific_integrations: Iterable[str] | None
    action: str
    requirements: bool = False
    errors: list[ValidationError] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Record a configuration level error."""

        self.errors.append(ValidationError(message))


class Integration:
    """Simplified integration model used by hassfest style tests."""

    def __init__(
        self,
        path: Path,
        *,
        _config: Config,
        _manifest: dict[str, Any] | None = None,
    ) -> None:
        self.path = Path(path)
        self._config = _config
        self._manifest: dict[str, Any] = _manifest or {}
        self.errors: list[ValidationError] = []

    @property
    def manifest(self) -> dict[str, Any]:
        """Return the manifest associated with the integration."""

        return self._manifest

    @property
    def domain(self) -> str:
        """Return the integration domain."""

        return self._manifest.get("domain", self.path.name)

    def add_error(self, message: str) -> None:
        """Record an integration level error."""

        self.errors.append(ValidationError(message))

    @property
    def is_custom_integration(self) -> bool:
        """Return ``True`` if the integration is considered custom."""

        return not self.path.parts or "custom_components" in self.path.parts

    def core(self) -> bool:  # pragma: no cover - patched in tests
        """Return ``True`` if the integration is part of Home Assistant core."""

        return not self.is_custom_integration


__all__ = ["Config", "Integration", "ValidationError"]
