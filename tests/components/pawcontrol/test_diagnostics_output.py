"""Tests for PawControl diagnostics payload defaults."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol import diagnostics


@pytest.mark.asyncio
async def test_performance_metrics_defaults_include_rejection_metrics() -> None:
  """Ensure performance diagnostics always include rejection defaults."""

  payload = await diagnostics._get_performance_metrics(None)

  assert payload["available"] is False
  rejection_metrics = payload["rejection_metrics"]
  assert rejection_metrics["schema_version"] == 4
  assert rejection_metrics["rejected_call_count"] == 0


@pytest.mark.asyncio
async def test_notification_diagnostics_include_rejection_defaults() -> None:
  """Ensure notification diagnostics include rejection metrics defaults."""

  payload = await diagnostics._get_notification_diagnostics(None)

  assert payload["available"] is False
  rejection_metrics = payload["rejection_metrics"]
  assert rejection_metrics["schema_version"] == 1
  assert rejection_metrics["total_failures"] == 0


@pytest.mark.asyncio
async def test_service_execution_defaults_include_rejection_metrics() -> None:
  """Ensure service execution diagnostics include default metrics."""

  payload = await diagnostics._get_service_execution_diagnostics(None)

  assert payload["available"] is False
  rejection_metrics = payload["rejection_metrics"]
  assert rejection_metrics["schema_version"] == 4
  assert rejection_metrics["rejected_call_count"] == 0
  guard_metrics = payload["guard_metrics"]
  assert guard_metrics["executed"] == 0
  assert guard_metrics["skipped"] == 0
