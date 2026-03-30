"""Tests for the adaptive polling controller."""

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol.coordinator_runtime import (
    AdaptivePollingController,
    EntityBudgetSnapshot,
)


@pytest.mark.parametrize("cycles", [8, 10])
def test_adaptive_polling_reaches_idle_interval(cycles: int) -> None:
    """Low-activity cycles should expand towards the idle interval."""
    controller = AdaptivePollingController(
        initial_interval_seconds=60.0,
        min_interval_seconds=30.0,
        max_interval_seconds=1800.0,
        idle_interval_seconds=900.0,
        idle_grace_seconds=0.0,
    )
    controller.update_entity_saturation(0.0)

    interval = 0.0
    for _ in range(cycles):
        interval = controller.record_cycle(
            duration=0.2,
            success=True,
            error_ratio=0.0,
        )

    assert pytest.approx(interval, rel=0.05) == 900.0


def test_adaptive_polling_reduces_when_system_busy() -> None:
    """Fast cycles with high entity saturation should shrink the polling window.

    Patch 9: _target_cycle is now 0.2 s (200 ms) instead of being clamped to
    _min_interval (≥ 15 s).  Tests must use sub-target cycle durations to reach
    the reduction branch of record_cycle().  The 20 s duration used previously
    hit the "slow cycle" increase branch because 20 s >> 0.2 s target.
    """
    controller = AdaptivePollingController(
        initial_interval_seconds=600.0,
        min_interval_seconds=60.0,
        max_interval_seconds=1800.0,
        idle_interval_seconds=900.0,
        idle_grace_seconds=600.0,
    )
    controller.update_entity_saturation(0.9)

    interval = controller.record_cycle(
        duration=0.05,  # 50 ms — fast cycle, below 0.8 × 200 ms target
        success=True,
        error_ratio=0.1,
    )

    assert interval < 600.0
    assert interval >= 60.0


def test_adaptive_polling_backs_off_after_errors() -> None:
    """Consecutive failures should quickly expand the interval."""
    controller = AdaptivePollingController(
        initial_interval_seconds=120.0,
        min_interval_seconds=60.0,
        max_interval_seconds=1800.0,
        idle_interval_seconds=1200.0,
        idle_grace_seconds=0.0,
    )
    controller.update_entity_saturation(0.0)

    first = controller.record_cycle(
        duration=5.0,
        success=False,
        error_ratio=1.0,
    )
    second = controller.record_cycle(
        duration=5.0,
        success=False,
        error_ratio=1.0,
    )

    assert first > 120.0
    assert second > first
    assert second <= 1800.0


def test_adaptive_polling_honours_idle_grace_before_idle_ramp() -> None:
    """Idle grace should apply a gentle ramp before idle interval escalation.

    Patch 9: _target_cycle is now 0.2 s.  Using duration=0.2 s keeps the cycle
    inside the neutral zone (0.16–0.22 s) so neither the reduction nor the
    increase branch fires, leaving next_interval unchanged at 100.  The idle
    grace path then applies the 1.25× gentle multiplier → 125 → 156.25.
    """
    controller = AdaptivePollingController(
        initial_interval_seconds=100.0,
        min_interval_seconds=30.0,
        max_interval_seconds=1800.0,
        idle_interval_seconds=600.0,
        idle_grace_seconds=3600.0,
    )
    controller.update_entity_saturation(0.0)

    first = controller.record_cycle(
        duration=0.2,  # neutral zone: 0.16 s < 0.2 s < 0.22 s
        success=True,
        error_ratio=0.0,
    )
    second = controller.record_cycle(
        duration=0.2,
        success=True,
        error_ratio=0.0,
    )

    assert first == pytest.approx(125.0)
    assert second == pytest.approx(156.25)


def test_adaptive_polling_increases_interval_for_slow_cycles() -> None:
    """Slow successful cycles should increase the polling interval."""
    controller = AdaptivePollingController(
        initial_interval_seconds=120.0,
        min_interval_seconds=30.0,
        max_interval_seconds=900.0,
        idle_interval_seconds=900.0,
        idle_grace_seconds=600.0,
    )
    controller.update_entity_saturation(0.1)

    interval = controller.record_cycle(
        duration=240.0,
        success=True,
        error_ratio=0.0,
    )

    assert interval > 120.0
    assert interval <= 900.0


def test_adaptive_polling_resets_idle_tracking_after_activity() -> None:
    """High error ratio marks activity and prevents immediate idle ramping.

    Patch 9: _target_cycle is now 0.2 s.  duration=0.05 s (fast cycle) hits the
    reduction branch and lowers the interval below 120.  The second cycle with
    error_ratio=0 and idle_grace=0 triggers the idle ramp above active_interval.
    """
    controller = AdaptivePollingController(
        initial_interval_seconds=120.0,
        min_interval_seconds=30.0,
        max_interval_seconds=1800.0,
        idle_interval_seconds=900.0,
        idle_grace_seconds=0.0,
    )
    controller.update_entity_saturation(0.0)

    active_interval = controller.record_cycle(
        duration=0.05,  # fast cycle: below 0.8 × 0.2 s target → reduction branch
        success=True,
        error_ratio=0.2,
    )
    idle_interval = controller.record_cycle(
        duration=0.05,
        success=True,
        error_ratio=0.0,
    )

    assert active_interval < 120.0
    assert idle_interval > active_interval
    assert idle_interval < 900.0


def test_adaptive_polling_diagnostics_and_budget_saturation() -> None:
    """Diagnostics should include history metadata and saturation should clamp."""
    controller = AdaptivePollingController(
        initial_interval_seconds=45.0,
        min_interval_seconds=20.0,
        max_interval_seconds=90.0,
        idle_interval_seconds=120.0,
        idle_grace_seconds=10.0,
    )
    controller.update_entity_saturation(2.0)
    controller.record_cycle(
        duration=0.0,
        success=False,
        error_ratio=0.5,
    )
    diagnostics = controller.as_diagnostics()

    assert diagnostics["history_samples"] == 1
    assert diagnostics["error_streak"] == 1
    assert diagnostics["entity_saturation"] == 1.0
    assert diagnostics["current_interval_ms"] > 0

    budget = EntityBudgetSnapshot(
        dog_id="dog-1",
        profile="standard",
        capacity=0,
        base_allocation=2,
        dynamic_allocation=3,
        requested_entities=("sensor.a",),
        denied_requests=(),
        recorded_at=datetime.now(UTC),
    )
    assert budget.total_allocated == 5
    assert budget.remaining == 0
    assert budget.saturation == 0.0
