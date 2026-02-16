"""Tests for health summary helpers in the config flow."""

from typing import Any

from custom_components.pawcontrol.flow_steps.health import HealthSummaryMixin


class _HealthSummaryFlow(HealthSummaryMixin):
  @staticmethod  # noqa: E111
  def _normalise_string_list(values: Any) -> list[str]:  # noqa: E111
    if not values:
      return []  # noqa: E111
    if isinstance(values, list):
      return [str(value).strip() for value in values if str(value).strip()]  # noqa: E111
    return [str(values).strip()] if str(values).strip() else []


def test_summarise_health_summary_defaults() -> None:
  """Missing health data should return a neutral summary."""  # noqa: E111

  flow = _HealthSummaryFlow()  # noqa: E111
  assert flow._summarise_health_summary(None) == "No recent health summary"  # noqa: E111


def test_summarise_health_summary_healthy() -> None:
  """Healthy summaries should be concise."""  # noqa: E111

  flow = _HealthSummaryFlow()  # noqa: E111
  summary = {"healthy": True, "issues": [], "warnings": []}  # noqa: E111
  assert flow._summarise_health_summary(summary) == "Healthy"  # noqa: E111


def test_summarise_health_summary_with_issues() -> None:
  """Issues and warnings should be rendered in the summary."""  # noqa: E111

  flow = _HealthSummaryFlow()  # noqa: E111
  summary = {  # noqa: E111
    "healthy": False,
    "issues": ["tracking offline"],
    "warnings": ["battery low"],
  }
  assert (  # noqa: E111
    flow._summarise_health_summary(summary)
    == "Issues detected | Issues: tracking offline | Warnings: battery low"
  )
