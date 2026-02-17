"""Tests for the adaptive polling controller."""

import pytest

from custom_components.pawcontrol.coordinator_runtime import AdaptivePollingController


@pytest.mark.parametrize("cycles", [8, 10])
def test_adaptive_polling_reaches_idle_interval(cycles: int) -> None:
    """Low-activity cycles should expand towards the idle interval."""  # noqa: E111

    controller = AdaptivePollingController(  # noqa: E111
        initial_interval_seconds=60.0,
        min_interval_seconds=30.0,
        max_interval_seconds=1800.0,
        idle_interval_seconds=900.0,
        idle_grace_seconds=0.0,
    )
    controller.update_entity_saturation(0.0)  # noqa: E111

    interval = 0.0  # noqa: E111
    for _ in range(cycles):  # noqa: E111
        interval = controller.record_cycle(
            duration=0.2,
            success=True,
            error_ratio=0.0,
        )

    assert pytest.approx(interval, rel=0.05) == 900.0  # noqa: E111


def test_adaptive_polling_reduces_when_system_busy() -> None:
    """High utilisation should shrink the polling window."""  # noqa: E111

    controller = AdaptivePollingController(  # noqa: E111
        initial_interval_seconds=600.0,
        min_interval_seconds=60.0,
        max_interval_seconds=1800.0,
        idle_interval_seconds=900.0,
        idle_grace_seconds=600.0,
    )
    controller.update_entity_saturation(0.9)  # noqa: E111

    interval = controller.record_cycle(  # noqa: E111
        duration=20.0,
        success=True,
        error_ratio=0.1,
    )

    assert interval < 600.0  # noqa: E111
    assert interval >= 60.0  # noqa: E111


def test_adaptive_polling_backs_off_after_errors() -> None:
    """Consecutive failures should quickly expand the interval."""  # noqa: E111

    controller = AdaptivePollingController(  # noqa: E111
        initial_interval_seconds=120.0,
        min_interval_seconds=60.0,
        max_interval_seconds=1800.0,
        idle_interval_seconds=1200.0,
        idle_grace_seconds=0.0,
    )
    controller.update_entity_saturation(0.0)  # noqa: E111

    first = controller.record_cycle(  # noqa: E111
        duration=5.0,
        success=False,
        error_ratio=1.0,
    )
    second = controller.record_cycle(  # noqa: E111
        duration=5.0,
        success=False,
        error_ratio=1.0,
    )

    assert first > 120.0  # noqa: E111
    assert second > first  # noqa: E111
    assert second <= 1800.0  # noqa: E111
