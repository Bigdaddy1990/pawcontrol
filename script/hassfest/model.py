"""Minimal hassfest model stubs for PawControl tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any


@dataclass(slots=True)
class Config:
    """Subset of hassfest configuration used by the tests."""

    root: Path
    integrations: dict[str, "Integration"] = field(default_factory=dict)
    errors: list[Any] = field(default_factory=list)
    specific_integrations: set[str] | None = None
    action: str = "validate"
    requirements: bool = True
    warnings: list[Any] = field(default_factory=list)

    def get_integration(self, domain: str) -> "Integration | None":
        return self.integrations.get(domain)


@dataclass(slots=True)
class Integration:
    """Representation of a Home Assistant integration for hassfest tests."""

    path: Path
    _config: Config
    _manifest: dict[str, Any]
    errors: list[Any] = field(default_factory=list)

    @property
    def domain(self) -> str:
        return self._manifest.get("domain", self.path.name)

    @property
    def manifest(self) -> dict[str, Any]:
        return self._manifest

    def add_error(self, _section: str, error: str) -> None:  # pragma: no cover - stub
        """Compatibility hook for tests expecting hassfest validation."""

        self.errors.append(SimpleNamespace(error=error))

    def add_warning(self, _section: str, error: str) -> None:  # pragma: no cover - stub
        """Record warnings similar to hassfest's behaviour."""

        self.warnings.append(SimpleNamespace(error=error))

    def core(self) -> bool:
        """Return True when the integration refers to Home Assistant core."""

        return "homeassistant/components" in str(self.path)


__all__ = ["Config", "Integration"]
