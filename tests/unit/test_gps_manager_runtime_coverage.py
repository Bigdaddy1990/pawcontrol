"""Runtime coverage tests for less-traveled GPS manager branches."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.pawcontrol import gps_manager as gm
from custom_components.pawcontrol.gps_manager import (
    GeofenceEvent,
    GeofenceEventType,
    GeofenceZone,
    GPSAccuracy,
    GPSPoint,
    LocationSource,
    WalkRoute,
)


async def _configure_active_tracking(
    manager,
    dog_id: str = "dog-1",
    update_interval_seconds: int = 0,
) -> None:
    """Configure an enabled dog and create an active route for task tests."""
    await manager.async_configure_dog_gps(
        dog_id,
        {
            "enabled": True,
            "track_route": True,
            "update_interval_seconds": update_interval_seconds,
        },
    )
    manager._active_routes[dog_id] = WalkRoute(
        dog_id=dog_id,
        start_time=datetime.now(UTC),
    )


@pytest.mark.unit
def test_set_notification_manager_assigns_and_clears(mock_gps_manager) -> None:
    """Notification manager assignment should support attach and detach."""
    manager = mock_gps_manager
    sentinel = object()

    manager.set_notification_manager(sentinel)  # type: ignore[arg-type]
    assert manager._notification_manager is sentinel

    manager.set_notification_manager(None)
    assert manager._notification_manager is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_configure_dog_gps_re_raises_builder_errors(
    mock_gps_manager,
) -> None:
    """Configuration should propagate builder failures."""
    with patch.object(gm, "_build_tracking_config", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            await mock_gps_manager.async_configure_dog_gps("dog-1", {"enabled": True})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_geofence_zone_validates_coordinates(
    mock_gps_manager,
) -> None:
    """Latitude and longitude bounds should be validated explicitly."""
    with pytest.raises(ValueError, match="latitude"):
        await mock_gps_manager.async_setup_geofence_zone(
            "dog-1",
            "yard",
            91.0,
            13.4,
            100.0,
        )

    with pytest.raises(ValueError, match="longitude"):
        await mock_gps_manager.async_setup_geofence_zone(
            "dog-1",
            "yard",
            52.5,
            181.0,
            100.0,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_geofence_zone_re_raises_constructor_errors(
    mock_gps_manager,
) -> None:
    """Zone construction errors should bubble up to callers."""
    with patch.object(gm, "GeofenceZone", side_effect=RuntimeError("zone-fail")):
        with pytest.raises(RuntimeError, match="zone-fail"):
            await mock_gps_manager.async_setup_geofence_zone(
                "dog-1",
                "yard",
                52.5,
                13.4,
                100.0,
            )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_start_gps_tracking_re_raises_tracking_task_errors(
    mock_gps_manager,
) -> None:
    """Starting tracking should re-raise task scheduling failures."""
    await mock_gps_manager.async_configure_dog_gps(
        "dog-1",
        {"enabled": True, "track_route": True},
    )

    with patch.object(
        mock_gps_manager,
        "_start_tracking_task",
        AsyncMock(side_effect=RuntimeError("task-fail")),
    ):
        with pytest.raises(RuntimeError, match="task-fail"):
            await mock_gps_manager.async_start_gps_tracking("dog-1", track_route=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_end_gps_tracking_initializes_history_when_missing(
    mock_gps_manager,
) -> None:
    """Ending a tracked route should create history buckets when absent."""
    now = datetime.now(UTC)
    route = WalkRoute(dog_id="dog-1", start_time=now - timedelta(minutes=5))
    route.gps_points.append(
        GPSPoint(
            latitude=52.5,
            longitude=13.4,
            timestamp=now - timedelta(minutes=4),
        )
    )
    mock_gps_manager._active_routes["dog-1"] = route
    mock_gps_manager._route_history.pop("dog-1", None)

    result = await mock_gps_manager.async_end_gps_tracking("dog-1", save_route=True)

    assert result is route
    assert "dog-1" in mock_gps_manager._route_history
    assert route in mock_gps_manager._route_history["dog-1"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_end_gps_tracking_re_raises_stop_errors(mock_gps_manager) -> None:
    """Failures while stopping tracking should propagate."""
    mock_gps_manager._active_routes["dog-1"] = WalkRoute(
        dog_id="dog-1",
        start_time=datetime.now(UTC),
    )
    with patch.object(
        mock_gps_manager,
        "_stop_tracking_task",
        AsyncMock(side_effect=RuntimeError("stop-fail")),
    ):
        with pytest.raises(RuntimeError, match="stop-fail"):
            await mock_gps_manager.async_end_gps_tracking("dog-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_gps_point_validates_longitude_range(mock_gps_manager) -> None:
    """Longitude outside [-180, 180] should be rejected."""
    with pytest.raises(ValueError, match="Longitude"):
        await mock_gps_manager.async_add_gps_point(
            dog_id="dog-1",
            latitude=52.5,
            longitude=181.0,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_gps_point_returns_false_on_internal_errors(
    mock_gps_manager,
) -> None:
    """Internal geofence failures should be handled gracefully."""
    with patch.object(
        mock_gps_manager,
        "_check_geofence_zones",
        AsyncMock(side_effect=RuntimeError("zone-check-fail")),
    ):
        result = await mock_gps_manager.async_add_gps_point(
            dog_id="dog-1",
            latitude=52.5,
            longitude=13.4,
        )

    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_export_routes_filters_to_empty_result(mock_gps_manager) -> None:
    """Date filtering that removes all routes should return None."""
    route = WalkRoute(
        dog_id="dog-1",
        start_time=datetime.now(UTC) - timedelta(days=3),
        end_time=datetime.now(UTC) - timedelta(days=3, minutes=-30),
    )
    mock_gps_manager._route_history["dog-1"] = [route]

    filtered = await mock_gps_manager.async_export_routes(
        dog_id="dog-1",
        date_from=datetime.now(UTC) - timedelta(days=1),
    )

    assert filtered is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_export_routes_re_raises_unsupported_format(mock_gps_manager) -> None:
    """Unsupported export formats should raise ValueError."""
    route = WalkRoute(
        dog_id="dog-1",
        start_time=datetime.now(UTC) - timedelta(minutes=45),
        end_time=datetime.now(UTC),
    )
    mock_gps_manager._route_history["dog-1"] = [route]

    with pytest.raises(ValueError, match="Unsupported export format"):
        await mock_gps_manager.async_export_routes(
            dog_id="dog-1",
            export_format="xml",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_configure_dog_gps_keeps_existing_status_and_history(
    mock_gps_manager,
) -> None:
    """Configuring an existing dog should not reset existing tracking containers."""
    manager = mock_gps_manager
    existing_route = WalkRoute(dog_id="dog-1", start_time=datetime.now(UTC))
    manager._zone_status["dog-1"] = {"existing-zone": True}
    manager._route_history["dog-1"] = [existing_route]

    await manager.async_configure_dog_gps("dog-1", {"enabled": True})

    assert manager._zone_status["dog-1"] == {"existing-zone": True}
    assert manager._route_history["dog-1"] == [existing_route]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_geofence_zone_reuses_existing_collections(
    mock_gps_manager,
) -> None:
    """Existing zone/status dictionaries should be reused."""
    manager = mock_gps_manager
    manager._zone_status["dog-1"] = {"legacy": False}
    manager._geofence_zones["dog-1"] = [
        GeofenceZone("yard", 52.5, 13.4, 100.0),
        GeofenceZone("old", 52.5, 13.4, 50.0),
    ]

    await manager.async_setup_geofence_zone(
        "dog-1",
        "yard",
        52.52,
        13.41,
        120.0,
    )

    names = [zone.name for zone in manager._geofence_zones["dog-1"]]
    assert names.count("yard") == 1
    assert "old" in names
    assert "legacy" in manager._zone_status["dog-1"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_end_gps_tracking_save_false_skips_history_append(
    mock_gps_manager,
) -> None:
    """When save_route is false, existing history should remain unchanged."""
    manager = mock_gps_manager
    now = datetime.now(UTC)
    route = WalkRoute(dog_id="dog-1", start_time=now - timedelta(minutes=10))
    route.gps_points.append(
        GPSPoint(latitude=52.5, longitude=13.4, timestamp=now - timedelta(minutes=9))
    )
    manager._active_routes["dog-1"] = route
    sentinel_route = WalkRoute(dog_id="dog-1", start_time=now - timedelta(days=1))
    manager._route_history["dog-1"] = [sentinel_route]

    await manager.async_end_gps_tracking("dog-1", save_route=False)

    assert manager._route_history["dog-1"] == [sentinel_route]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_end_gps_tracking_appends_when_history_exists(
    mock_gps_manager,
) -> None:
    """Routes should append to existing history lists."""
    manager = mock_gps_manager
    now = datetime.now(UTC)
    route = WalkRoute(dog_id="dog-1", start_time=now - timedelta(minutes=10))
    route.gps_points.append(
        GPSPoint(latitude=52.5, longitude=13.4, timestamp=now - timedelta(minutes=9))
    )
    manager._active_routes["dog-1"] = route
    manager._route_history["dog-1"] = []

    await manager.async_end_gps_tracking("dog-1", save_route=True)

    assert manager._route_history["dog-1"][-1] is route


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_gps_point_filters_small_movement_when_configured(
    mock_gps_manager,
) -> None:
    """Distance filtering should reject points below the minimum threshold."""
    manager = mock_gps_manager
    await manager.async_configure_dog_gps(
        "dog-1",
        {"enabled": True, "min_distance_for_point": 500.0},
    )
    route = WalkRoute(dog_id="dog-1", start_time=datetime.now(UTC))
    route.gps_points.append(
        GPSPoint(latitude=52.5, longitude=13.4, timestamp=datetime.now(UTC))
    )
    manager._active_routes["dog-1"] = route

    accepted = await manager.async_add_gps_point(
        dog_id="dog-1",
        latitude=52.500001,
        longitude=13.400001,
        timestamp=datetime.now(UTC),
    )

    assert accepted is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_export_routes_respects_date_to_and_zero_limit(
    mock_gps_manager,
) -> None:
    """Export should apply date_to filtering and skip slicing when limit is zero."""
    manager = mock_gps_manager
    old_route = WalkRoute(
        dog_id="dog-1",
        start_time=datetime.now(UTC) - timedelta(days=2),
        end_time=datetime.now(UTC) - timedelta(days=2, minutes=-20),
    )
    new_route = WalkRoute(
        dog_id="dog-1",
        start_time=datetime.now(UTC) - timedelta(hours=2),
        end_time=datetime.now(UTC) - timedelta(hours=1, minutes=40),
    )
    manager._route_history["dog-1"] = [old_route, new_route]

    payload = await manager.async_export_routes(
        dog_id="dog-1",
        export_format="json",
        date_to=datetime.now(UTC) - timedelta(days=1),
        last_n_routes=0,
    )

    assert payload is not None
    assert payload["routes_count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_tracking_task_returns_when_config_missing_or_disabled(
    mock_gps_manager,
) -> None:
    """Tracking task startup should no-op without active configuration."""
    manager = mock_gps_manager
    manager._active_routes["dog-1"] = WalkRoute(
        dog_id="dog-1",
        start_time=datetime.now(UTC),
    )

    await manager._start_tracking_task("dog-1")
    assert "dog-1" not in manager._tracking_tasks

    await manager.async_configure_dog_gps("dog-1", {"enabled": False})
    await manager._start_tracking_task("dog-1")
    assert "dog-1" not in manager._tracking_tasks


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stop_tracking_task_logs_timeout_when_cancel_wait_expires(
    mock_gps_manager,
) -> None:
    """Stopping tasks should tolerate cancellation wait timeouts."""
    manager = mock_gps_manager
    task = asyncio.create_task(asyncio.sleep(60))
    manager._tracking_tasks["dog-1"] = task

    with patch.object(gm.asyncio, "wait_for", side_effect=TimeoutError):
        await manager._stop_tracking_task("dog-1")

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_location_from_device_tracker_adds_matching_entity_point(
    mock_gps_manager,
) -> None:
    """Device tracker updates should add points for matching entities."""
    manager = mock_gps_manager
    fake_entity = SimpleNamespace(
        platform="device_tracker",
        name="Dog-1 Collar",
        entity_id="device_tracker.dog_1",
    )
    fake_registry = SimpleNamespace(entities={"device_tracker.dog_1": fake_entity})
    fake_state = SimpleNamespace(
        state="home",
        attributes={"latitude": 52.5, "longitude": 13.4, "gps_accuracy": 8.0},
    )

    async def _execute_with_resilience(func, **_kwargs):  # type: ignore[no-untyped-def]
        return await func()

    manager.resilience_manager.execute_with_resilience = _execute_with_resilience
    manager.async_add_gps_point = AsyncMock()  # type: ignore[method-assign]
    manager.hass.states.get = lambda _entity_id: fake_state  # type: ignore[assignment]

    with (
        patch.object(gm.er, "async_get", return_value=fake_registry),
        patch.object(gm.dr, "async_get", return_value=SimpleNamespace()),
    ):
        await manager._update_location_from_device_tracker("dog-1")

    manager.async_add_gps_point.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_location_from_device_tracker_handles_resilience_failures(
    mock_gps_manager,
) -> None:
    """Resilience wrapper failures should be swallowed with debug logging."""
    manager = mock_gps_manager
    manager.resilience_manager.execute_with_resilience = AsyncMock(
        side_effect=RuntimeError("resilience-fail")
    )

    await manager._update_location_from_device_tracker("dog-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_geofence_zones_skips_disabled_zones_and_notifications_opt_out(
    mock_gps_manager,
) -> None:
    """Disabled zones are ignored, and opt-out zones still update stats."""
    manager = mock_gps_manager
    disabled = GeofenceZone("disabled", 52.5, 13.4, 100.0, enabled=False)
    no_notify = GeofenceZone(
        "yard",
        52.5,
        13.4,
        10.0,
        notifications_enabled=False,
    )
    manager._geofence_zones["dog-1"] = [disabled, no_notify]
    manager._zone_status["dog-1"] = {"disabled": True, "yard": True}
    manager._send_geofence_notification = AsyncMock()  # type: ignore[method-assign]

    far_point = GPSPoint(latitude=53.0, longitude=14.0, timestamp=datetime.now(UTC))
    before = manager._stats["geofence_events"]
    await manager._check_geofence_zones("dog-1", far_point)

    assert manager._zone_status["dog-1"]["disabled"] is True
    manager._send_geofence_notification.assert_not_called()
    assert manager._stats["geofence_events"] == before + 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_geofence_notification_handles_return_and_breach_payloads(
    mock_gps_manager,
) -> None:
    """Return and breach events should build branch-specific messages and payloads."""
    manager = mock_gps_manager
    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock()
    )
    zone = GeofenceZone("yard", 52.5, 13.4, 100.0, zone_type="safe_zone")
    point = GPSPoint(
        latitude=52.5001,
        longitude=13.4001,
        timestamp=datetime.now(UTC),
        source=LocationSource.DEVICE_TRACKER,
    )

    return_event = GeofenceEvent(
        dog_id="dog-1",
        zone=zone,
        event_type=GeofenceEventType.RETURN,
        location=point,
        distance_from_center=20.0,
    )
    breach_event = GeofenceEvent(
        dog_id="dog-1",
        zone=zone,
        event_type=GeofenceEventType.BREACH,
        location=point,
        distance_from_center=200.0,
        duration_outside=timedelta(minutes=12),
    )

    await manager._send_geofence_notification(return_event)
    await manager._send_geofence_notification(breach_event)

    assert manager._notification_manager.async_send_notification.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_geofence_notification_swallows_notifier_failures(
    mock_gps_manager,
) -> None:
    """Notification send failures should not propagate exceptions."""
    manager = mock_gps_manager
    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(side_effect=RuntimeError("notify-fail"))
    )
    zone = GeofenceZone("yard", 52.5, 13.4, 100.0)
    point = GPSPoint(latitude=52.5, longitude=13.4, timestamp=datetime.now(UTC))
    event = GeofenceEvent(
        dog_id="dog-1",
        zone=zone,
        event_type=GeofenceEventType.ENTERED,
        location=point,
        distance_from_center=1.0,
    )

    await manager._send_geofence_notification(event)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_route_statistics_handles_empty_and_invalid_segments(
    mock_gps_manager,
) -> None:
    """Statistics should early-return for empty routes and skip invalid segments."""
    manager = mock_gps_manager
    empty_route = WalkRoute(dog_id="dog-1", start_time=datetime.now(UTC))
    await manager._calculate_route_statistics(empty_route)
    assert empty_route.total_distance_meters == 0.0

    invalid_route = WalkRoute(
        dog_id="dog-1",
        start_time=datetime.now(UTC) - timedelta(minutes=20),
    )
    p1 = GPSPoint(latitude=52.5, longitude=13.4, timestamp=datetime.now(UTC) - timedelta(minutes=10))
    p2 = GPSPoint(latitude=60.0, longitude=25.0, timestamp=datetime.now(UTC) - timedelta(minutes=9))
    invalid_route.gps_points = [p1, p2]
    await manager._calculate_route_statistics(invalid_route)
    assert invalid_route.segments == []


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("accuracies", "expected_quality"),
    [
        ([1.0, 1.0, 1.0, 1.0, 80.0], GPSAccuracy.GOOD),
        ([1.0, 1.0, 80.0, 80.0], GPSAccuracy.FAIR),
        ([1.0, 80.0, 80.0, 80.0], GPSAccuracy.POOR),
    ],
)
async def test_calculate_route_statistics_sets_quality_buckets(
    mock_gps_manager,
    accuracies,
    expected_quality,
) -> None:
    """Route quality should map to good/fair/poor thresholds."""
    manager = mock_gps_manager
    start = datetime.now(UTC) - timedelta(minutes=10)
    route = WalkRoute(dog_id="dog-1", start_time=start)
    points = []
    for idx, acc in enumerate(accuracies):
        points.append(
            GPSPoint(
                latitude=52.5 + (idx * 0.0001),
                longitude=13.4 + (idx * 0.0001),
                timestamp=start + timedelta(minutes=idx + 1),
                accuracy=acc,
            )
        )
    route.gps_points = points

    await manager._calculate_route_statistics(route)

    assert route.route_quality == expected_quality


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_route_with_new_point_ignores_single_point_routes(
    mock_gps_manager,
) -> None:
    """Incremental route updates should no-op until at least two points exist."""
    manager = mock_gps_manager
    route = WalkRoute(dog_id="dog-1", start_time=datetime.now(UTC))
    only_point = GPSPoint(latitude=52.5, longitude=13.4, timestamp=datetime.now(UTC))
    route.gps_points = [only_point]
    await manager._update_route_with_new_point(route, only_point)
    assert route.total_distance_meters == 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_routes_gpx_includes_altitude_when_available(
    mock_gps_manager,
) -> None:
    """GPX exports should include <ele> tags for altitude-capable points."""
    manager = mock_gps_manager
    route = WalkRoute(dog_id="dog-1", start_time=datetime.now(UTC))
    route.gps_points.append(
        GPSPoint(
            latitude=52.5,
            longitude=13.4,
            timestamp=datetime.now(UTC),
            altitude=12.3,
        )
    )

    payload = await manager._export_routes_gpx("dog-1", [route])
    assert "<ele>12.3</ele>" in payload["content"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_routes_json_includes_geofence_event_payloads(
    mock_gps_manager,
) -> None:
    """JSON exports should serialize geofence events when present."""
    manager = mock_gps_manager
    point = GPSPoint(latitude=52.5, longitude=13.4, timestamp=datetime.now(UTC))
    zone = GeofenceZone("yard", 52.5, 13.4, 100.0)
    event = GeofenceEvent(
        dog_id="dog-1",
        zone=zone,
        event_type=GeofenceEventType.EXITED,
        location=point,
        distance_from_center=150.0,
    )
    route = WalkRoute(dog_id="dog-1", start_time=datetime.now(UTC), end_time=datetime.now(UTC))
    route.gps_points.append(point)
    route.geofence_events.append(event)

    payload = await manager._export_routes_json("dog-1", [route])
    routes = payload["content"]["routes"]
    assert routes
    assert routes[0]["geofence_events"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_tracking_task_loop_handles_timeout_branch(
    mock_gps_manager,
) -> None:
    """Tracking loop should tolerate update timeouts and continue."""
    manager = mock_gps_manager
    await _configure_active_tracking(manager)
    original_sleep = gm.asyncio.sleep

    async def _sleep_and_stop(_seconds: float) -> None:
        manager._active_routes.pop("dog-1", None)
        await original_sleep(0)

    with (
        patch.object(gm.asyncio, "wait_for", AsyncMock(side_effect=TimeoutError)),
        patch.object(gm.asyncio, "sleep", AsyncMock(side_effect=_sleep_and_stop)),
    ):
        await manager._start_tracking_task("dog-1")
        await manager._tracking_tasks["dog-1"]

    await manager._stop_tracking_task("dog-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_tracking_task_loop_handles_cancelled_error_branch(
    mock_gps_manager,
) -> None:
    """Cancelling the task should hit the cancellation guard branch."""
    manager = mock_gps_manager
    await _configure_active_tracking(manager)
    blocker = asyncio.Event()

    async def _never_returns(_dog_id: str) -> None:
        await blocker.wait()

    manager._update_location_from_device_tracker = AsyncMock(side_effect=_never_returns)  # type: ignore[method-assign]
    manager.hass.async_create_task = (
        lambda coro, name=None: asyncio.create_task(coro, name=name)
    )

    await manager._start_tracking_task("dog-1")
    task = manager._tracking_tasks["dog-1"]
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert task.done()

    await manager._stop_tracking_task("dog-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_tracking_task_loop_handles_generic_error_branch(
    mock_gps_manager,
) -> None:
    """Unexpected update errors should be caught by the outer loop guard."""
    manager = mock_gps_manager
    await _configure_active_tracking(manager)
    manager._update_location_from_device_tracker = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("loop-boom")
    )
    manager.hass.async_create_task = (
        lambda coro, name=None: asyncio.create_task(coro, name=name)
    )

    await manager._start_tracking_task("dog-1")
    task = manager._tracking_tasks["dog-1"]
    await task
    assert task.done()

    await manager._stop_tracking_task("dog-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_tracking_task_accepts_future_scheduler_return(
    mock_gps_manager,
) -> None:
    """Scheduler futures should be accepted as resolved tracking handles."""
    manager = mock_gps_manager
    await _configure_active_tracking(manager)
    loop = asyncio.get_running_loop()

    def _schedule_future(coro, name=None):  # type: ignore[no-untyped-def]
        coro.close()
        future = loop.create_future()
        future.set_result(None)
        return future

    manager.hass.async_create_task = _schedule_future

    await manager._start_tracking_task("dog-1")

    task_handle = manager._tracking_tasks["dog-1"]
    assert isinstance(task_handle, asyncio.Future)
    assert task_handle.done()

    await manager._stop_tracking_task("dog-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_tracking_task_retries_hass_scheduler_without_name(
    mock_gps_manager,
) -> None:
    """TypeError from named hass scheduling should retry without name."""
    manager = mock_gps_manager
    await _configure_active_tracking(manager)
    scheduler_calls: list[str | None] = []

    async def _finish_first_iteration(_dog_id: str) -> None:
        manager._active_routes.pop("dog-1", None)

    manager._update_location_from_device_tracker = AsyncMock(  # type: ignore[method-assign]
        side_effect=_finish_first_iteration
    )

    def _schedule(coro, name=None):  # type: ignore[no-untyped-def]
        scheduler_calls.append(name)
        if name is not None:
            raise TypeError("scheduler has no name kwarg")
        return asyncio.create_task(coro)

    manager.hass.async_create_task = _schedule

    await manager._start_tracking_task("dog-1")
    await manager._tracking_tasks["dog-1"]

    assert scheduler_calls[0] is not None
    assert scheduler_calls[1] is None

    await manager._stop_tracking_task("dog-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_tracking_task_falls_back_to_loop_scheduler_when_missing(
    mock_gps_manager,
) -> None:
    """When hass scheduler is missing, loop.create_task fallback should run."""
    manager = mock_gps_manager
    await _configure_active_tracking(manager)
    loop_calls: list[str | None] = []
    manager.hass.async_create_task = None

    async def _finish_first_iteration(_dog_id: str) -> None:
        manager._active_routes.pop("dog-1", None)

    manager._update_location_from_device_tracker = AsyncMock(  # type: ignore[method-assign]
        side_effect=_finish_first_iteration
    )

    def _loop_create_task(coro, name=None):  # type: ignore[no-untyped-def]
        loop_calls.append(name)
        if name is not None:
            coro.close()
            raise TypeError("loop has no name kwarg")
        return asyncio.create_task(coro)

    manager.hass.loop = SimpleNamespace(create_task=_loop_create_task)

    await manager._start_tracking_task("dog-1")
    await manager._tracking_tasks["dog-1"]

    assert loop_calls[0] is not None
    assert loop_calls[1] is None

    await manager._stop_tracking_task("dog-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_tracking_task_raises_when_scheduler_returns_no_task(
    mock_gps_manager,
) -> None:
    """Task startup should fail loudly when no scheduler produces a task."""
    manager = mock_gps_manager
    await _configure_active_tracking(manager)
    manager.hass.async_create_task = None

    def _null_task_factory(coro, name=None):  # type: ignore[no-untyped-def]
        coro.close()
        return None

    manager.hass.loop = SimpleNamespace(create_task=_null_task_factory)

    with pytest.raises(RuntimeError, match="Failed to schedule GPS tracking task"):
        await manager._start_tracking_task("dog-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_location_from_device_tracker_continues_until_match_found(
    mock_gps_manager,
) -> None:
    """Entity iteration should continue past non-match, bad state and no coords."""
    manager = mock_gps_manager
    manager.async_add_gps_point = AsyncMock()  # type: ignore[method-assign]

    registry_entities = {
        "sensor.other_platform": SimpleNamespace(
            platform="sensor",
            name="Dog-1 Tracker",
            entity_id="sensor.other_platform",
        ),
        "device_tracker.unavailable": SimpleNamespace(
            platform="device_tracker",
            name="Dog-1 Tracker",
            entity_id="device_tracker.unavailable",
        ),
        "device_tracker.no_coords": SimpleNamespace(
            platform="device_tracker",
            name="Dog-1 Tracker",
            entity_id="device_tracker.no_coords",
        ),
        "device_tracker.good": SimpleNamespace(
            platform="device_tracker",
            name="Dog-1 Tracker",
            entity_id="device_tracker.good",
        ),
    }
    fake_registry = SimpleNamespace(entities=registry_entities)
    fake_states = {
        "device_tracker.unavailable": SimpleNamespace(
            state="unavailable",
            attributes={"latitude": 52.5, "longitude": 13.4, "gps_accuracy": 8.0},
        ),
        "device_tracker.no_coords": SimpleNamespace(
            state="home",
            attributes={"latitude": None, "longitude": 13.4, "gps_accuracy": 8.0},
        ),
        "device_tracker.good": SimpleNamespace(
            state="home",
            attributes={"latitude": 52.6, "longitude": 13.5, "gps_accuracy": 5.0},
        ),
    }
    manager.hass.states.get = lambda entity_id: fake_states.get(entity_id)  # type: ignore[assignment]

    with (
        patch.object(gm.er, "async_get", return_value=fake_registry),
        patch.object(gm.dr, "async_get", return_value=SimpleNamespace()),
    ):
        await manager._update_location_from_device_tracker("dog-1")

    manager.async_add_gps_point.assert_awaited_once()
