"""Tests for health summary helpers in the config flow."""

from __future__ import annotations

from typing import Any

from custom_components.pawcontrol.config_flow_health import HealthSummaryMixin


class _HealthSummaryFlow(HealthSummaryMixin):
  @staticmethod
  def _normalise_string_list(values: Any) -> list[str]:
    if not values:
      return []
    if isinstance(values, list):
      return [str(value).strip() for value in values if str(value).strip()]
    return [str(values).strip()] if str(values).strip() else []


def test_summarise_health_summary_defaults() -> None:
  """Missing health data should return a neutral summary."""

  flow = _HealthSummaryFlow()
  assert flow._summarise_health_summary(None) == "No recent health summary"


def test_summarise_health_summary_healthy() -> None:
  """Healthy summaries should be concise."""

  flow = _HealthSummaryFlow()
  summary = {"healthy": True, "issues": [], "warnings": []}
  assert flow._summarise_health_summary(summary) == "Healthy"


def test_summarise_health_summary_with_issues() -> None:
  """Issues and warnings should be rendered in the summary."""

  flow = _HealthSummaryFlow()
  summary = {
    "healthy": False,
    "issues": ["tracking offline"],
    "warnings": ["battery low"],
  }
  assert (
    flow._summarise_health_summary(summary)
    == "Issues detected | Issues: tracking offline | Warnings: battery low"
  )
