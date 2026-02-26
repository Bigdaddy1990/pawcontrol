"""Tests for entity update optimization helpers."""

import asyncio
from datetime import datetime

import pytest

from custom_components.pawcontrol import entity_optimization as eo


class _FakeEntity:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def async_write_ha_state(self) -> None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")


def test_entity_update_batcher_processes_pending_updates_in_batches() -> None:
    """The batcher should process pending entities and track statistics."""
    batcher = eo.EntityUpdateBatcher(hass=object(), batch_window_ms=0, max_batch_size=2)
    entity_a = _FakeEntity()
    entity_b = _FakeEntity()
    entity_c = _FakeEntity()
    batcher.register_entity("sensor.a", entity_a)
    batcher.register_entity("sensor.b", entity_b)
    batcher.register_entity("sensor.c", entity_c)

    async def _run() -> None:
        await batcher.schedule_update("sensor.a")
        await batcher.schedule_update("sensor.b")
        await batcher.schedule_update("sensor.c")

        while batcher._batch_task is not None and not batcher._batch_task.done():
            await batcher._batch_task

    asyncio.run(_run())

    assert entity_a.calls == 1
    assert entity_b.calls == 1
    assert entity_c.calls == 1
    assert batcher.get_stats()["batch_count"] == 2
    assert batcher.get_stats()["pending_updates"] == 0


def test_entity_update_batcher_handles_entity_write_failures() -> None:
    """Write failures should not interrupt remaining entity updates."""
    batcher = eo.EntityUpdateBatcher(hass=object(), batch_window_ms=0)
    ok_entity = _FakeEntity()
    failing_entity = _FakeEntity(fail=True)
    batcher.register_entity("sensor.ok", ok_entity)
    batcher.register_entity("sensor.bad", failing_entity)

    async def _run() -> None:
        await batcher.schedule_update("sensor.ok")
        await batcher.schedule_update("sensor.bad")
        if batcher._batch_task is not None:
            await batcher._batch_task

    asyncio.run(_run())

    stats = batcher.get_stats()
    assert stats["update_count"] == 1
    assert stats["batch_count"] == 1


def test_significant_change_tracker_thresholds_and_reset() -> None:
    """Threshold checks and reset operations should behave as expected."""
    tracker = eo.SignificantChangeTracker()
    tracker.set_threshold("sensor.temp", "value", absolute=0.5, percentage=0.2)

    assert tracker.is_significant_change("sensor.temp", "value", 10.0) is True
    assert tracker.is_significant_change("sensor.temp", "value", 10.3) is False
    assert tracker.is_significant_change("sensor.temp", "value", 12.5) is True
    assert tracker.is_significant_change("sensor.temp", "label", "ok") is True
    assert tracker.is_significant_change("sensor.temp", "label", "ok") is False
    assert tracker.is_significant_change("sensor.temp", "label", True) is True

    tracker.reset("sensor.temp")
    assert tracker.is_significant_change("sensor.temp", "value", 10.0) is True


def test_helper_functions_for_intervals_and_write_reduction() -> None:
    """Helper calculations should map volatility and reduction values correctly."""
    assert eo.calculate_optimal_update_interval("gps", "high") == 15
    assert eo.calculate_optimal_update_interval("unknown", "low") == 120
    assert eo.estimate_state_write_reduction(100, 70) == {
        "updates_before": 100,
        "updates_after": 70,
        "reduction": 30,
        "reduction_percentage": 30.0,
    }
    assert eo.estimate_state_write_reduction(0, 0)["reduction_percentage"] == 0.0


def test_skip_redundant_update_restores_previous_value_when_not_significant() -> None:
    """Decorator should restore old attribute when a change is insignificant."""
    tracker = eo.SignificantChangeTracker()

    class _Decorated:
        entity_id = "sensor.decorated"

        def __init__(self) -> None:
            self._attr_latitude = 1.0
            self._next = 1.0

        @eo.skip_redundant_update(tracker, "latitude", absolute_threshold=0.5)
        async def async_update(self) -> None:
            self._attr_latitude = self._next

    entity = _Decorated()
    asyncio.run(entity.async_update())

    entity._next = 1.3
    asyncio.run(entity.async_update())
    assert entity._attr_latitude == 1.0

    entity._next = 2.0
    asyncio.run(entity.async_update())
    assert entity._attr_latitude == 2.0


def test_entity_update_scheduler_registers_callbacks_and_updates_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler should register interval callbacks and support shutdown."""
    callbacks: dict[int, object] = {}
    unsubscribed: list[int] = []

    def _fake_track_time_interval(hass: object, action: object, interval: object):
        seconds = int(interval.total_seconds())
        callbacks[seconds] = action

        def _unsub() -> None:
            unsubscribed.append(seconds)

        return _unsub

    monkeypatch.setattr(eo, "async_track_time_interval", _fake_track_time_interval)

    scheduler = eo.EntityUpdateScheduler(hass=object())
    asyncio.run(scheduler.async_setup())

    ok_entity = _FakeEntity()
    bad_entity = _FakeEntity(fail=True)
    scheduler.register_entity("sensor.ok", ok_entity, update_interval=10)
    scheduler.register_entity("sensor.bad", bad_entity, update_interval=10)
    scheduler.register_entity("sensor.slow", _FakeEntity(), update_interval=60)

    callback = callbacks[10]
    callback(datetime.now())

    assert ok_entity.calls == 1
    assert bad_entity.calls == 1
    assert scheduler.get_stats()["intervals"]["10s"] == 2

    scheduler.unregister_entity("sensor.slow")
    assert scheduler.get_stats()["total_entities"] == 2

    scheduler.async_shutdown()
    assert set(unsubscribed) == {10, 30, 60, 300, 900}
