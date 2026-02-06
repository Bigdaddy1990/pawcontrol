"""Tests for the fixed polling compatibility controller."""

from __future__ import annotations

from custom_components.pawcontrol.coordinator_runtime import AdaptivePollingController


def test_adaptive_polling_keeps_fixed_interval() -> None:
  """Polling interval should remain constant across successful cycles."""

  controller = AdaptivePollingController(initial_interval_seconds=60.0)
  controller.update_entity_saturation(0.9)

  first = controller.record_cycle(duration=0.2, success=True, error_ratio=0.0)
  second = controller.record_cycle(duration=20.0, success=True, error_ratio=0.5)

  assert first == 60.0
  assert second == 60.0


def test_adaptive_polling_keeps_fixed_interval_on_errors() -> None:
  """Failures should not alter the fixed interval controller."""

  controller = AdaptivePollingController(initial_interval_seconds=120.0)

  first = controller.record_cycle(duration=5.0, success=False, error_ratio=1.0)
  second = controller.record_cycle(duration=1.0, success=True, error_ratio=0.0)

  assert first == 120.0
  assert second == 120.0
