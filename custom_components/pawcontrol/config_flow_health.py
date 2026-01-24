"""Health summary helpers for the PawControl config flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class HealthSummaryHost(Protocol):
  """Protocol describing the config flow host requirements."""

  def _normalise_string_list(self, values: Any) -> list[str]: ...


class HealthSummaryMixin(HealthSummaryHost):
  """Provide health summary formatting for reconfigure flows."""

  def _summarise_health_summary(self, summary: Any) -> str:
    """Convert a health summary mapping into a user-facing string."""

    if not isinstance(summary, Mapping):
      return "No recent health summary"

    healthy = bool(summary.get("healthy", True))
    issues = self._normalise_string_list(summary.get("issues"))
    warnings = self._normalise_string_list(summary.get("warnings"))

    if healthy and not issues and not warnings:
      return "Healthy"

    segments: list[str] = []
    if not healthy:
      segments.append("Issues detected")
    if issues:
      segments.append(f"Issues: {', '.join(issues)}")
    if warnings:
      segments.append(f"Warnings: {', '.join(warnings)}")

    return " | ".join(segments)
