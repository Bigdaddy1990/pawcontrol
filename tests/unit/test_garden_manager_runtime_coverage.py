"""Runtime-focused branch coverage tests for ``garden_manager.py``."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol import garden_manager as gm
from custom_components.pawcontrol.garden_manager import (
    GardenActivity,
    GardenActivityType,
    GardenManager,
    GardenSession,
    GardenSessionStatus,
    GardenStats,
)


def _new_session(
    dog_id: str,
    *,
    dog_name: str = "Buddy",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    status: GardenSessionStatus = GardenSessionStatus.ACTIVE,
) -> GardenSession:
    """Return a garden session with deterministic defaults for tests."""
    now = dt_util.utcnow()
    session = GardenSession(
        session_id=f"session-{dog_id}-{int(now.timestamp())}",
        dog_id=dog_id,
        dog_name=dog_name,
        start_time=start_time or (now - timedelta(minutes=10)),
        end_time=end_time,
        status=status,
    )
    if end_time is not None:
        session.calculate_duration()
    return session


def _local_export_root() -> Path:
    """Return a workspace-local export root for deterministic file IO tests."""
    root = Path("pytest_tmp_local").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_applies_config_and_initializes_stats(
    hass: HomeAssistant,
) -> None:
    """Initialize should apply config, load data, and seed per-dog stats."""
    manager = GardenManager(hass, "entry")
    manager._load_stored_data = AsyncMock()
    manager._start_background_tasks = AsyncMock()

    await manager.async_initialize(
        dogs=["dog-1", "dog-2"],
        notification_manager=object(),
        door_sensor_manager=object(),
        config={
            "session_timeout": 123,
            "auto_poop_detection": False,
            "confirmation_required": False,
        },
    )

    assert manager._session_timeout == 123
    assert manager._auto_poop_detection is False
    assert manager._confirmation_required is False
    assert set(manager._dog_stats) == {"dog-1", "dog-2"}
    manager._load_stored_data.assert_awaited_once()
    manager._start_background_tasks.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_and_save_roundtrip_serializes_sessions_and_stats(
    hass: HomeAssistant,
) -> None:
    """Stored payloads should hydrate and persist through the same shapes."""
    manager = GardenManager(hass, "entry")
    now = dt_util.utcnow()
    stored = {
        "sessions": [
            {
                "session_id": "stored-session",
                "dog_id": "dog-1",
                "dog_name": "Buddy",
                "start_time": (now - timedelta(minutes=20)).isoformat(),
                "end_time": (now - timedelta(minutes=5)).isoformat(),
                "status": "completed",
                "activities": [],
                "total_duration_seconds": 900,
                "poop_count": 1,
                "weather_conditions": "Cloudy",
                "temperature": 18.0,
                "notes": "stored",
            }
        ],
        "stats": {
            "dog-1": {
                "total_sessions": 1,
                "total_time_minutes": 15.0,
                "total_poop_count": 1,
                "average_session_duration": 15.0,
                "most_active_time_of_day": "morning",
                "favorite_activities": [],
                "total_activities": 0,
                "weekly_summary": {},
                "last_garden_visit": now.isoformat(),
            }
        },
    }
    manager._store.data = stored

    await manager._load_stored_data()

    assert len(manager._session_history) == 1
    assert manager._session_history[0].session_id == "stored-session"
    assert manager._dog_stats["dog-1"].total_sessions == 1

    await manager._save_data()

    assert manager._store.data is not None
    payload = manager._store.data
    assert isinstance(payload, dict)
    assert "sessions" in payload
    assert "stats" in payload
    assert "last_updated" in payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_stored_data_returns_early_for_empty_payload(
    hass: HomeAssistant,
) -> None:
    """Empty storage payloads should keep runtime state untouched."""
    manager = GardenManager(hass, "entry")
    manager._store.data = None

    await manager._load_stored_data()

    assert manager._session_history == []
    assert manager._dog_stats == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_task_uses_hass_async_create_task_with_typeerror_fallback(
    hass: HomeAssistant,
) -> None:
    """Task creation should retry without name when hass helper rejects kwargs."""
    manager = GardenManager(hass, "entry")

    def _create_without_name(coro: object) -> asyncio.Task[None]:
        return asyncio.create_task(cast_coroutine(coro))

    manager.hass.async_create_task = _create_without_name  # type: ignore[attr-defined]

    task = manager._create_task(_noop(), "named-task")
    await task
    assert task.done()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_task_falls_back_to_asyncio_when_hass_scheduler_missing(
    hass: HomeAssistant,
) -> None:
    """When hass has no async scheduler, manager should use asyncio directly."""
    manager = GardenManager(hass, "entry")
    manager.hass = SimpleNamespace()  # type: ignore[assignment]

    task = manager._create_task(_noop(), "fallback-task")
    await task
    assert task.done()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_task_handles_none_done_and_timeout(hass: HomeAssistant) -> None:
    """Cancellation helper should no-op on done tasks and handle timeouts."""
    manager = GardenManager(hass, "entry")

    await manager._cancel_task(None, "none-task")

    done = asyncio.get_running_loop().create_future()
    done.set_result(None)
    await manager._cancel_task(done, "done-task")

    pending = asyncio.create_task(asyncio.sleep(1))
    with patch(
        "custom_components.pawcontrol.garden_manager.asyncio.wait_for",
        new=AsyncMock(side_effect=TimeoutError),
    ):
        await manager._cancel_task(pending, "pending-task")
    pending.cancel()
    with suppress(asyncio.CancelledError):
        await pending


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_background_and_cancel_confirmation_tasks(
    hass: HomeAssistant,
) -> None:
    """Background setup should create two tasks and confirmation cancellation works."""
    manager = GardenManager(hass, "entry")
    await manager._start_background_tasks()

    assert manager._cleanup_task is not None
    assert manager._stats_update_task is not None

    confirmation_task = asyncio.create_task(asyncio.sleep(1))
    manager._confirmation_tasks["dog-1"] = confirmation_task
    await manager._cancel_confirmation_task("dog-1")
    assert "dog-1" not in manager._confirmation_tasks

    await manager._cancel_task(manager._cleanup_task, "cleanup")
    await manager._cancel_task(manager._stats_update_task, "stats")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_and_stats_loops_execute_both_wait_for_calls_once(
    hass: HomeAssistant,
) -> None:
    """Both wait_for calls should run in a normal loop iteration."""
    manager = GardenManager(hass, "entry")

    sleep_cleanup = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    wait_for_cleanup = AsyncMock(return_value=None)
    with (
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.sleep",
            sleep_cleanup,
        ),
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.wait_for",
            wait_for_cleanup,
        ),
    ):
        await manager._cleanup_loop()
    assert wait_for_cleanup.await_count == 2

    sleep_stats = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    wait_for_stats = AsyncMock(return_value=None)
    with (
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.sleep",
            sleep_stats,
        ),
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.wait_for",
            wait_for_stats,
        ),
    ):
        await manager._stats_update_loop()
    assert wait_for_stats.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_and_stats_loops_handle_timeout_and_generic_errors(
    hass: HomeAssistant,
) -> None:
    """Loop tasks should continue after timeout/errors and stop on cancellation."""
    manager = GardenManager(hass, "entry")

    sleep_cleanup = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    wait_for_cleanup = AsyncMock(side_effect=[TimeoutError(), RuntimeError("boom")])
    with (
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.sleep",
            sleep_cleanup,
        ),
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.wait_for",
            wait_for_cleanup,
        ),
    ):
        await manager._cleanup_loop()

    sleep_stats = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    wait_for_stats = AsyncMock(side_effect=[TimeoutError(), RuntimeError("boom")])
    with (
        patch("custom_components.pawcontrol.garden_manager.asyncio.sleep", sleep_stats),
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.wait_for",
            wait_for_stats,
        ),
    ):
        await manager._stats_update_loop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_and_stats_loops_handle_generic_error_paths(
    hass: HomeAssistant,
) -> None:
    """Loop tasks should also execute the generic error handlers."""
    manager = GardenManager(hass, "entry")

    cleanup_sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    cleanup_wait_for = AsyncMock(side_effect=RuntimeError("cleanup-boom"))
    with (
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.sleep",
            cleanup_sleep,
        ),
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.wait_for",
            cleanup_wait_for,
        ),
    ):
        await manager._cleanup_loop()

    stats_sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    stats_wait_for = AsyncMock(side_effect=RuntimeError("stats-boom"))
    with (
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.sleep",
            stats_sleep,
        ),
        patch(
            "custom_components.pawcontrol.garden_manager.asyncio.wait_for",
            stats_wait_for,
        ),
    ):
        await manager._stats_update_loop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_start_garden_session_fire_event_notification_and_autodetect(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Start should create an active session and schedule confirmation task."""
    manager = GardenManager(hass, "entry")
    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(),
    )
    manager._end_active_session_for_dog = AsyncMock()
    manager._cancel_confirmation_task = AsyncMock()
    manager._auto_poop_detection = True

    fire_event = AsyncMock()
    monkeypatch.setattr(gm, "async_fire_event", fire_event)

    def _fake_create_task(
        coro: asyncio.coroutines.Coroutine[Any, Any, None],
        name: str,
    ) -> asyncio.Task[None]:
        coro.close()
        return asyncio.create_task(_noop(), name=name)

    manager._create_task = MagicMock(side_effect=_fake_create_task)

    session_id = await manager.async_start_garden_session(
        "dog-1",
        "Buddy",
        detection_method="manual",
        weather_conditions="Sunny",
        temperature=21.5,
    )

    assert session_id.startswith("garden_dog-1_")
    assert manager.get_active_session("dog-1") is not None
    assert "dog-1" in manager._confirmation_tasks
    fire_event.assert_awaited_once()
    manager._notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_without_config_keeps_existing_stats_objects(
    hass: HomeAssistant,
) -> None:
    """Initializing without config should not replace existing stats objects."""
    manager = GardenManager(hass, "entry")
    existing = GardenStats(total_sessions=4)
    manager._dog_stats["dog-1"] = existing
    manager._load_stored_data = AsyncMock()
    manager._start_background_tasks = AsyncMock()

    await manager.async_initialize(["dog-1"], config=None)

    assert manager._dog_stats["dog-1"] is existing
    manager._load_stored_data.assert_awaited_once()
    manager._start_background_tasks.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_start_garden_session_without_autodetect(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Start should skip confirmation scheduling when auto detection is disabled."""
    manager = GardenManager(hass, "entry")
    manager._auto_poop_detection = False
    manager._end_active_session_for_dog = AsyncMock()
    monkeypatch.setattr(gm, "async_fire_event", AsyncMock())

    await manager.async_start_garden_session("dog-1", "Buddy")

    assert manager.get_active_session("dog-1") is not None
    assert manager._confirmation_tasks == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_end_garden_session_handles_missing_active_session(
    hass: HomeAssistant,
) -> None:
    """Ending a non-existent session should return ``None``."""
    manager = GardenManager(hass, "entry")
    manager._cancel_confirmation_task = AsyncMock()

    assert await manager.async_end_garden_session("dog-1") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_end_garden_session_completes_history_and_notifications(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ending a session should process activities, fire event, and persist data."""
    manager = GardenManager(hass, "entry")
    manager._cancel_confirmation_task = AsyncMock()
    manager._update_dog_statistics = AsyncMock()
    manager._save_data = AsyncMock()
    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(),
    )
    monkeypatch.setattr(gm, "async_fire_event", AsyncMock())

    manager._active_sessions["dog-1"] = _new_session("dog-1")
    completed = await manager.async_end_garden_session(
        "dog-1",
        notes="all good",
        activities=[
            {"type": "play", "duration_seconds": 30, "confirmed": True},
            {"type": "invalid-activity"},
        ],
    )

    assert completed is not None
    assert completed.status is GardenSessionStatus.COMPLETED
    assert completed.notes == "all good"
    assert completed.dog_id == "dog-1"
    assert len(manager._session_history) == 1
    assert "dog-1" not in manager._active_sessions
    manager._update_dog_statistics.assert_awaited_once_with("dog-1")
    manager._save_data.assert_awaited_once()
    manager._notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_end_garden_session_suppresses_notifications(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Suppress flag should skip completion notification delivery."""
    manager = GardenManager(hass, "entry")
    manager._cancel_confirmation_task = AsyncMock()
    manager._update_dog_statistics = AsyncMock()
    manager._save_data = AsyncMock()
    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(),
    )
    monkeypatch.setattr(gm, "async_fire_event", AsyncMock())

    manager._active_sessions["dog-1"] = _new_session("dog-1")
    await manager.async_end_garden_session("dog-1", suppress_notifications=True)

    manager._notification_manager.async_send_notification.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fmt", "suffix"),
    [
        ("csv", ".csv"),
        ("markdown", ".md"),
        ("txt", ".txt"),
        ("json", ".json"),
        ("invalid-format", ".json"),
    ],
)
async def test_async_export_sessions_writes_supported_formats(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    fmt: str,
    suffix: str,
) -> None:
    """Export should write csv/markdown/txt/json and fallback unknown to json."""
    manager = GardenManager(hass, "entry")
    hass.config.config_dir = str(_local_export_root())
    if not hasattr(gm.dt_util, "UTC"):
        monkeypatch.setattr(gm.dt_util, "UTC", UTC, raising=False)

    now = dt_util.utcnow()
    session = _new_session(
        "dog-1",
        start_time=now - timedelta(minutes=20),
        end_time=now - timedelta(minutes=5),
        status=GardenSessionStatus.COMPLETED,
    )
    session.notes = "exportable"
    manager._session_history = [session]

    exported = await manager.async_export_sessions(
        "dog-1",
        format=fmt,
        date_from=(now - timedelta(days=1)).date(),
        date_to=now.isoformat(),
    )

    assert exported.exists()
    assert exported.suffix == suffix


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_export_sessions_includes_active_session_and_days_filter(
    hass: HomeAssistant,
) -> None:
    """Export should include active sessions and respect `days` fallback range."""
    manager = GardenManager(hass, "entry")
    hass.config.config_dir = str(_local_export_root())

    now = dt_util.utcnow()
    manager._active_sessions["dog-1"] = _new_session(
        "dog-1",
        start_time=now - timedelta(minutes=8),
    )
    manager._session_history = [
        _new_session(
            "dog-1",
            start_time=now - timedelta(days=40),
            end_time=now - timedelta(days=40, minutes=-10),
            status=GardenSessionStatus.COMPLETED,
        )
    ]

    exported = await manager.async_export_sessions("dog-1", days=7, format="json")
    payload = exported.read_text(encoding="utf-8")

    assert '"data_type": "garden"' in payload
    assert '"entries"' in payload
    assert "session-dog-1" in payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_export_sessions_coerce_datetime_and_invalid_string_bounds(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Datetime input and invalid date strings should be coerced safely."""
    manager = GardenManager(hass, "entry")
    hass.config.config_dir = str(_local_export_root())
    if not hasattr(gm.dt_util, "UTC"):
        monkeypatch.setattr(gm.dt_util, "UTC", UTC, raising=False)

    now = dt_util.utcnow()
    manager._session_history = [
        _new_session(
            "dog-1",
            start_time=now - timedelta(minutes=20),
            end_time=now - timedelta(minutes=5),
            status=GardenSessionStatus.COMPLETED,
        )
    ]

    exported = await manager.async_export_sessions(
        "dog-1",
        format="json",
        date_from=now - timedelta(days=1),
        date_to="invalid-end",
    )
    assert exported.exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_export_sessions_csv_handles_empty_entry_sets(
    hass: HomeAssistant,
) -> None:
    """CSV export should handle empty entry lists without writing a header row."""
    manager = GardenManager(hass, "entry")
    hass.config.config_dir = str(_local_export_root())

    exported = await manager.async_export_sessions("dog-unknown", format="csv")

    assert exported.exists()
    assert exported.suffix == ".csv"
    assert exported.read_text(encoding="utf-8") == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_activity_success_and_error_paths(hass: HomeAssistant) -> None:
    """Add activity should handle no-session, valid, and invalid types."""
    manager = GardenManager(hass, "entry")

    assert await manager.async_add_activity("dog-1", "play") is False

    manager._active_sessions["dog-1"] = _new_session("dog-1")
    assert (
        await manager.async_add_activity("dog-1", "play", duration_seconds=15)
        is True
    )

    assert await manager.async_add_activity("dog-1", "not-a-type") is False
    assert len(manager._active_sessions["dog-1"].activities) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_log_poop_event_delegates_to_standalone_when_no_session(
    hass: HomeAssistant,
) -> None:
    """Without active session poop events should route to standalone logger."""
    manager = GardenManager(hass, "entry")
    manager._log_standalone_poop_event = AsyncMock(return_value=True)

    result = await manager.async_log_poop_event("dog-1")

    assert result is True
    manager._log_standalone_poop_event.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_log_poop_event_with_active_session_and_confirmation_flag(
    hass: HomeAssistant,
) -> None:
    """Active session poop logs should append activity and notify if confirmed."""
    manager = GardenManager(hass, "entry")
    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(),
    )
    manager._active_sessions["dog-1"] = _new_session("dog-1")

    assert await manager.async_log_poop_event("dog-1", confirmed=True) is True
    assert await manager.async_log_poop_event("dog-1", confirmed=False) is True
    assert manager._active_sessions["dog-1"].poop_count == 2
    manager._notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_log_poop_event_appends_optional_notes(
    hass: HomeAssistant,
) -> None:
    """Optional notes should be appended into the poop activity payload."""
    manager = GardenManager(hass, "entry")
    manager._active_sessions["dog-1"] = _new_session("dog-1")

    assert await manager.async_log_poop_event("dog-1", notes="observed quickly") is True
    latest = manager._active_sessions["dog-1"].activities[-1]
    assert latest.notes is not None
    assert "Notes: observed quickly" in latest.notes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_log_standalone_poop_event_updates_stats_and_notifies(
    hass: HomeAssistant,
) -> None:
    """Standalone logs should increment stored stats and persist changes."""
    manager = GardenManager(hass, "entry")
    manager._dog_stats["dog-1"] = GardenStats()
    manager._save_data = AsyncMock()
    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(),
    )

    result = await manager._log_standalone_poop_event(
        "dog-1",
        quality="soft",
        size="medium",
        location="north corner",
        notes="none",
    )

    assert result is True
    assert manager._dog_stats["dog-1"].total_poop_count == 1
    manager._save_data.assert_awaited_once()
    manager._notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_log_standalone_poop_event_covers_no_stats_and_no_notification(
    hass: HomeAssistant,
) -> None:
    """Standalone logger should also handle missing stats and notifier branches."""
    manager = GardenManager(hass, "entry")
    manager._save_data = AsyncMock()

    manager._notification_manager = None
    assert await manager._log_standalone_poop_event(
        "dog-missing",
        quality=None,
        size=None,
        location=None,
        notes=None,
    )
    manager._save_data.assert_not_awaited()

    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(),
    )
    assert await manager._log_standalone_poop_event(
        "dog-missing",
        quality="normal",
        size="small",
        location=None,
        notes=None,
    )
    manager._notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_schedule_poop_confirmation_creates_and_cleans_up_task_mapping(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduled confirmation should create pending record and pop own task."""
    manager = GardenManager(hass, "entry")
    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(),
    )
    manager._active_sessions["dog-1"] = _new_session("dog-1")
    session_id = manager._active_sessions["dog-1"].session_id

    monkeypatch.setattr(
        "custom_components.pawcontrol.garden_manager.asyncio.sleep",
        AsyncMock(),
    )
    task = asyncio.create_task(manager._schedule_poop_confirmation("dog-1", session_id))
    manager._confirmation_tasks["dog-1"] = task
    await task

    assert manager._pending_confirmations
    assert "dog-1" not in manager._confirmation_tasks
    manager._notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_schedule_poop_confirmation_returns_when_poop_already_logged(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler should early-return when a poop activity already exists."""
    manager = GardenManager(hass, "entry")
    manager._notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(),
    )
    session = _new_session("dog-1")
    session.add_activity(GardenActivity(GardenActivityType.POOP, dt_util.utcnow()))
    manager._active_sessions["dog-1"] = session

    monkeypatch.setattr(
        "custom_components.pawcontrol.garden_manager.asyncio.sleep",
        AsyncMock(),
    )
    await manager._schedule_poop_confirmation("dog-1", session.session_id)

    assert manager._pending_confirmations == {}
    manager._notification_manager.async_send_notification.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_schedule_poop_confirmation_returns_on_session_mismatch_and_no_notifier(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler should early-return for missing/mismatched sessions and no notifier."""
    manager = GardenManager(hass, "entry")
    monkeypatch.setattr(
        "custom_components.pawcontrol.garden_manager.asyncio.sleep",
        AsyncMock(),
    )

    await manager._schedule_poop_confirmation("dog-1", "unknown-session")

    manager._active_sessions["dog-1"] = _new_session("dog-1")
    await manager._schedule_poop_confirmation("dog-1", "other-session")

    manager._notification_manager = None
    await manager._schedule_poop_confirmation(
        "dog-1",
        manager._active_sessions["dog-1"].session_id,
    )
    assert manager._pending_confirmations == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_schedule_poop_confirmation_propagates_cancellation(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelled confirmation tasks should re-raise cancellation and self-clean."""
    manager = GardenManager(hass, "entry")
    manager._active_sessions["dog-1"] = _new_session("dog-1")
    monkeypatch.setattr(
        "custom_components.pawcontrol.garden_manager.asyncio.sleep",
        AsyncMock(side_effect=asyncio.CancelledError()),
    )
    task = asyncio.create_task(
        manager._schedule_poop_confirmation(
            "dog-1",
            manager._active_sessions["dog-1"].session_id,
        )
    )
    manager._confirmation_tasks["dog-1"] = task
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "dog-1" not in manager._confirmation_tasks


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_handle_poop_confirmation_paths(hass: HomeAssistant) -> None:
    """Confirmation handler should remove pending entry and branch by decision."""
    manager = GardenManager(hass, "entry")
    now = dt_util.utcnow()
    manager._pending_confirmations["c1"] = {
        "type": "poop_confirmation",
        "dog_id": "dog-1",
        "session_id": "s1",
        "timestamp": now,
        "timeout": now + timedelta(minutes=5),
    }
    manager.async_log_poop_event = AsyncMock(return_value=True)

    await manager.async_handle_poop_confirmation("dog-1", True, location="yard")
    assert "c1" not in manager._pending_confirmations
    manager.async_log_poop_event.assert_awaited_once_with(
        dog_id="dog-1",
        quality="normal",
        size="normal",
        location="yard",
        confirmed=True,
    )

    await manager.async_handle_poop_confirmation("dog-2", False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_handle_poop_confirmation_scans_until_matching_record(
    hass: HomeAssistant,
) -> None:
    """Handler should skip unrelated confirmations until a matching one is found."""
    manager = GardenManager(hass, "entry")
    now = dt_util.utcnow()
    manager._pending_confirmations["other"] = {
        "type": "poop_confirmation",
        "dog_id": "dog-x",
        "session_id": "sx",
        "timestamp": now,
        "timeout": now + timedelta(minutes=5),
    }
    manager._pending_confirmations["target"] = {
        "type": "poop_confirmation",
        "dog_id": "dog-1",
        "session_id": "s1",
        "timestamp": now,
        "timeout": now + timedelta(minutes=5),
    }
    manager.async_log_poop_event = AsyncMock(return_value=True)

    await manager.async_handle_poop_confirmation("dog-1", confirmed=False)

    assert "target" not in manager._pending_confirmations
    assert "other" in manager._pending_confirmations
    manager.async_log_poop_event.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_end_active_session_for_dog_invokes_end_only_when_needed(
    hass: HomeAssistant,
) -> None:
    """Auto-end helper should be a no-op when no active session exists."""
    manager = GardenManager(hass, "entry")
    manager.async_end_garden_session = AsyncMock()

    await manager._end_active_session_for_dog("dog-1")
    manager.async_end_garden_session.assert_not_called()

    manager._active_sessions["dog-1"] = _new_session("dog-1")
    await manager._end_active_session_for_dog("dog-1")
    manager.async_end_garden_session.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_expired_sessions_and_confirmations(hass: HomeAssistant) -> None:
    """Cleanup routines should expire timed-out sessions and stale confirmations."""
    manager = GardenManager(hass, "entry")
    manager._session_timeout = 60
    now = dt_util.utcnow()
    manager._active_sessions["expired"] = _new_session(
        "expired",
        dog_name="Oldie",
        start_time=now - timedelta(minutes=10),
    )
    manager._active_sessions["fresh"] = _new_session(
        "fresh",
        dog_name="Fresh",
        start_time=now - timedelta(seconds=30),
    )
    manager.async_end_garden_session = AsyncMock()

    await manager._cleanup_expired_sessions()

    assert manager._active_sessions["expired"].status is GardenSessionStatus.TIMEOUT
    manager.async_end_garden_session.assert_awaited_once_with(
        "expired",
        notes="Session timed out",
    )

    manager._pending_confirmations = {
        "old": {
            "type": "poop_confirmation",
            "dog_id": "expired",
            "session_id": "s1",
            "timestamp": now - timedelta(minutes=8),
            "timeout": now - timedelta(minutes=3),
        },
        "new": {
            "type": "poop_confirmation",
            "dog_id": "fresh",
            "session_id": "s2",
            "timestamp": now - timedelta(minutes=1),
            "timeout": now + timedelta(minutes=3),
        },
        "none-timeout": {
            "type": "poop_confirmation",
            "dog_id": "fresh",
            "session_id": "s3",
            "timestamp": now - timedelta(minutes=1),
            "timeout": None,
        },
    }
    await manager._cleanup_expired_confirmations()
    assert "old" not in manager._pending_confirmations
    assert "new" in manager._pending_confirmations
    assert "none-timeout" in manager._pending_confirmations


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hour", "expected_period"),
    [(7, "morning"), (13, "afternoon"), (19, "evening"), (2, "night")],
)
async def test_update_dog_statistics_time_of_day_buckets(
    hass: HomeAssistant,
    hour: int,
    expected_period: str,
) -> None:
    """Statistics should classify the dominant session start-hour bucket."""
    manager = GardenManager(hass, "entry")
    now = dt_util.utcnow()
    start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=15)
    session = _new_session(
        "dog-1",
        start_time=start,
        end_time=end,
        status=GardenSessionStatus.COMPLETED,
    )
    session.add_activity(GardenActivity(GardenActivityType.PLAY, start))
    manager._session_history = [session]

    await manager._update_dog_statistics("dog-1")

    stats = manager._dog_stats["dog-1"]
    assert stats.total_sessions == 1
    assert stats.most_active_time_of_day == expected_period
    assert stats.favorite_activities[0]["activity"] == "play"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_dog_statistics_handles_empty_and_old_weekly_summary(
    hass: HomeAssistant,
) -> None:
    """No sessions returns early; stale sessions clear weekly summary."""
    manager = GardenManager(hass, "entry")
    await manager._update_dog_statistics("dog-empty")
    assert "dog-empty" in manager._dog_stats
    assert manager._dog_stats["dog-empty"].total_sessions == 0

    now = dt_util.utcnow()
    old_start = now - timedelta(days=20)
    old_end = old_start + timedelta(minutes=10)
    stale = _new_session(
        "dog-old",
        start_time=old_start,
        end_time=old_end,
        status=GardenSessionStatus.COMPLETED,
    )
    manager._session_history = [stale]
    await manager._update_dog_statistics("dog-old")
    assert manager._dog_stats["dog-old"].weekly_summary == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_dog_statistics_reuses_existing_stats_object(
    hass: HomeAssistant,
) -> None:
    """Existing stats entries should be updated in place."""
    manager = GardenManager(hass, "entry")
    now = dt_util.utcnow()
    session = _new_session(
        "dog-1",
        start_time=now - timedelta(minutes=20),
        end_time=now - timedelta(minutes=5),
        status=GardenSessionStatus.COMPLETED,
    )
    manager._session_history = [session]
    existing = GardenStats(total_sessions=88)
    manager._dog_stats["dog-1"] = existing

    await manager._update_dog_statistics("dog-1")

    assert manager._dog_stats["dog-1"] is existing
    assert existing.total_sessions == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_all_statistics_iterates_known_dogs(hass: HomeAssistant) -> None:
    """Bulk statistics update should invoke per-dog calculation for each key."""
    manager = GardenManager(hass, "entry")
    manager._dog_stats = {
        "dog-1": GardenStats(),
        "dog-2": GardenStats(),
    }
    manager._update_dog_statistics = AsyncMock()

    await manager._update_all_statistics()

    assert manager._update_dog_statistics.await_count == 2


@pytest.mark.unit
def test_getters_pending_and_recent_session_helpers(hass: HomeAssistant) -> None:
    """Getter helpers should filter, sort, and map pending confirmations."""
    manager = GardenManager(hass, "entry")
    now = dt_util.utcnow()
    s1 = _new_session(
        "dog-1",
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(hours=1, minutes=45),
        status=GardenSessionStatus.COMPLETED,
    )
    s2 = _new_session(
        "dog-2",
        start_time=now - timedelta(minutes=15),
        end_time=now - timedelta(minutes=5),
        status=GardenSessionStatus.COMPLETED,
    )
    manager._session_history = [s1, s2]
    manager._active_sessions["dog-1"] = _new_session("dog-1")
    manager._dog_stats["dog-1"] = GardenStats(total_sessions=3)

    assert manager.get_active_session("dog-1") is not None
    assert manager.get_dog_statistics("dog-1") is not None
    assert manager.is_dog_in_garden("dog-1") is True
    assert manager.is_dog_in_garden("dog-x") is False

    all_recent = manager.get_recent_sessions(limit=10)
    assert all_recent[0].dog_id == "dog-2"
    dog_recent = manager.get_recent_sessions("dog-1", limit=10)
    assert len(dog_recent) == 1
    assert dog_recent[0].dog_id == "dog-1"

    manager._pending_confirmations = {
        "c1": {
            "type": "poop_confirmation",
            "dog_id": "dog-1",
            "session_id": "s1",
            "timestamp": now,
            "timeout": now + timedelta(minutes=5),
        },
        "c2": {
            "type": "poop_confirmation",
            "dog_id": "dog-2",
            "session_id": "s2",
            "timestamp": None,
            "timeout": None,
        },
    }

    assert manager.has_pending_confirmation("dog-1") is True
    assert manager.has_pending_confirmation("dog-x") is False
    pending = manager.get_pending_confirmations("dog-1")
    assert len(pending) == 1
    assert pending[0]["session_id"] == "s1"


@pytest.mark.unit
def test_build_garden_snapshot_idle_defaults_without_sessions(
    hass: HomeAssistant,
) -> None:
    """Snapshot should keep idle defaults when no data is present."""
    manager = GardenManager(hass, "entry")

    snapshot = manager.build_garden_snapshot("dog-1")

    assert snapshot["status"] == "idle"
    assert snapshot["sessions_today"] == 0
    assert snapshot["active_session"] is None
    assert snapshot["last_session"] is None
    assert snapshot["weather_summary"] is None


@pytest.mark.unit
def test_build_garden_snapshot_excludes_old_session_and_empty_weather(
    hass: HomeAssistant,
) -> None:
    """Old sessions should not count for today and empty weather stays omitted."""
    manager = GardenManager(hass, "entry")
    now = dt_util.utcnow()
    old_session = _new_session(
        "dog-1",
        start_time=now - timedelta(days=2, minutes=10),
        end_time=now - timedelta(days=2),
        status=GardenSessionStatus.COMPLETED,
    )
    old_session.weather_conditions = None
    old_session.temperature = None
    manager._session_history = [old_session]

    snapshot = manager.build_garden_snapshot("dog-1")

    assert snapshot["sessions_today"] == 0
    assert snapshot["weather_summary"] is None


@pytest.mark.unit
def test_build_garden_snapshot_skips_hours_since_when_reference_time_falsey(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hours-since field should stay unset when reference time evaluates falsey."""

    class _FalseyTime:
        def __init__(self, value: datetime) -> None:
            self._value = value

        def isoformat(self) -> str:
            return self._value.isoformat()

        def __bool__(self) -> bool:
            return False

    class _FakeSession:
        def __init__(self, now: datetime) -> None:
            self.session_id = "fake"
            self.start_time = _FalseyTime(now)
            self.end_time = None
            self.status = GardenSessionStatus.COMPLETED
            self.activities: list[GardenActivity] = []
            self.poop_count = 0
            self.weather_conditions = None
            self.temperature = None
            self.notes = None

        def calculate_duration(self) -> int:
            return 0

    manager = GardenManager(hass, "entry")
    now = dt_util.utcnow()
    fake = _FakeSession(now)
    monkeypatch.setattr(gm.dt_util, "as_local", lambda _: now)
    monkeypatch.setattr(
        manager,
        "get_recent_sessions",
        lambda *_args, **_kwargs: [fake],
    )

    snapshot = manager.build_garden_snapshot("dog-1")

    assert snapshot["last_session"] is not None
    assert snapshot["hours_since_last_session"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_cleanup_cancels_tasks_ends_sessions_and_saves(
    hass: HomeAssistant,
) -> None:
    """Cleanup should cancel all background work and persist final state."""
    manager = GardenManager(hass, "entry")
    manager._cleanup_task = asyncio.create_task(_noop())
    manager._stats_update_task = asyncio.create_task(_noop())
    manager._confirmation_tasks = {
        "dog-1": asyncio.create_task(_noop()),
        "dog-2": asyncio.create_task(_noop()),
    }
    manager._active_sessions = {
        "dog-1": _new_session("dog-1"),
        "dog-2": _new_session("dog-2"),
    }
    manager._cancel_task = AsyncMock()
    manager._cancel_confirmation_task = AsyncMock()
    manager.async_end_garden_session = AsyncMock()
    manager._save_data = AsyncMock()

    await manager.async_cleanup()

    assert manager._cancel_task.await_count == 2
    assert manager._cancel_confirmation_task.await_count == 2
    assert manager.async_end_garden_session.await_count == 2
    manager._save_data.assert_awaited_once()


def cast_coroutine(coro: object) -> asyncio.coroutines.Coroutine[Any, Any, None]:
    """Return a coroutine with a precise type for task helpers."""
    return coro  # type: ignore[return-value]


async def _noop() -> None:
    """Shared no-op coroutine for scheduling tests."""
    return None
