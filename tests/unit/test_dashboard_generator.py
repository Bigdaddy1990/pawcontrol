"""Unit tests for the dashboard generator metadata exports."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_NOTIFICATIONS,
)
from custom_components.pawcontrol.dashboard_generator import (
    DashboardViewSummary,
    PawControlDashboardGenerator,
)


def test_summarise_dashboard_views_marks_notifications() -> None:
    """The view summariser should flag the notifications module view."""

    dashboard_config = {
        "views": [
            {
                "path": "overview",
                "title": "Overview",
                "icon": "mdi:home",
                "cards": [{"type": "entities"}],
            },
            {
                "path": MODULE_NOTIFICATIONS,
                "title": "Notifications",
                "icon": "mdi:bell",
                "cards": [
                    {"type": "entities"},
                    {"type": "markdown"},
                ],
            },
        ]
    }

    summaries = PawControlDashboardGenerator._summarise_dashboard_views(
        dashboard_config
    )

    assert any(summary["path"] == "overview" for summary in summaries)

    notifications_summary = next(
        summary for summary in summaries if summary["path"] == MODULE_NOTIFICATIONS
    )

    assert notifications_summary["card_count"] == 2
    assert notifications_summary.get("module") == MODULE_NOTIFICATIONS
    assert notifications_summary.get("notifications") is True


@pytest.mark.asyncio
@patch("custom_components.pawcontrol.dashboard_generator.Store")
async def test_generator_initialises_cleanup_tracking(
    mock_store: MagicMock, hass, mock_config_entry
) -> None:
    """Generator initialisation should create the cleanup tracking set."""

    mock_store.return_value = MagicMock()

    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    assert hasattr(generator, "_cleanup_tasks")
    assert generator._cleanup_tasks == set()


@pytest.mark.asyncio
@patch("custom_components.pawcontrol.dashboard_generator.Store")
async def test_track_task_registers_and_clears(
    mock_store: MagicMock, hass, mock_config_entry
) -> None:
    """Tracked tasks should be cancelled during cleanup and removed on completion."""

    mock_store.return_value = MagicMock()
    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    async def short_task() -> None:
        await asyncio.sleep(0)

    task = generator._track_task(short_task(), name="test-short-task")
    assert task in generator._cleanup_tasks

    await task
    await asyncio.sleep(0)
    assert task not in generator._cleanup_tasks


@pytest.mark.asyncio
async def test_track_task_falls_back_to_asyncio(mock_config_entry) -> None:
    """Use ``asyncio.create_task`` when Home Assistant helper is unavailable."""

    generator = object.__new__(PawControlDashboardGenerator)
    generator.hass = SimpleNamespace()
    generator._cleanup_tasks = set()

    async def completes_immediately() -> None:
        await asyncio.sleep(0)

    with patch(
        "custom_components.pawcontrol.dashboard_generator.asyncio.create_task",
        wraps=asyncio.create_task,
    ) as patched_create_task:
        task = generator._track_task(completes_immediately(), name="fallback-task")

    patched_create_task.assert_called()
    assert task in generator._cleanup_tasks

    await task
    await asyncio.sleep(0)

    assert task not in generator._cleanup_tasks


@pytest.mark.asyncio
async def test_track_task_uses_hass_loop_when_available(mock_config_entry) -> None:
    """Fallback to ``hass.loop.create_task`` before raw asyncio scheduling."""

    loop_mock = MagicMock()
    generator = object.__new__(PawControlDashboardGenerator)
    generator.hass = SimpleNamespace(loop=loop_mock)
    generator._cleanup_tasks = set()

    async def completes_immediately() -> None:
        await asyncio.sleep(0)

    created: list[asyncio.Task[None]] = []

    def _create_task_side_effect(
        awaitable: Awaitable[None], *, name: str | None = None
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(awaitable)
        if name and hasattr(task, "set_name"):
            with contextlib.suppress(Exception):
                task.set_name(name)
        created.append(task)
        return task

    loop_mock.create_task.side_effect = _create_task_side_effect

    task = generator._track_task(completes_immediately(), name="loop-fallback")

    loop_mock.create_task.assert_called()
    assert created == [task]
    assert task in generator._cleanup_tasks

    await task
    await asyncio.sleep(0)

    assert task not in generator._cleanup_tasks


@pytest.mark.asyncio
@patch("custom_components.pawcontrol.dashboard_generator.Store")
async def test_track_task_accepts_existing_task(
    mock_store: MagicMock, hass, mock_config_entry
) -> None:
    """Existing tasks should be tracked without being recreated."""

    mock_store.return_value = MagicMock()

    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    async def completes_immediately() -> None:
        await asyncio.sleep(0)

    existing_task = hass.async_create_task(completes_immediately())

    tracked = generator._track_task(existing_task, name="existing")

    assert tracked is existing_task
    assert tracked in generator._cleanup_tasks

    await tracked
    await asyncio.sleep(0)

    assert tracked not in generator._cleanup_tasks


@pytest.mark.asyncio
async def test_track_task_handles_helper_runtime_error(mock_config_entry) -> None:
    """Gracefully fall back when Home Assistant helper raises ``RuntimeError``."""

    class HassStub(SimpleNamespace):
        def async_create_task(
            self, awaitable: Awaitable[None], *, name: str | None = None
        ) -> asyncio.Task[None]:
            raise RuntimeError("loop closed")

    generator = object.__new__(PawControlDashboardGenerator)
    generator.hass = HassStub()
    generator._cleanup_tasks = set()

    async def completes_immediately() -> None:
        await asyncio.sleep(0)

    with patch(
        "custom_components.pawcontrol.dashboard_generator.asyncio.create_task",
        wraps=asyncio.create_task,
    ) as patched_create_task:
        task = generator._track_task(completes_immediately(), name="asyncio-fallback")

    patched_create_task.assert_called()
    assert task in generator._cleanup_tasks

    await task
    await asyncio.sleep(0)

    assert task not in generator._cleanup_tasks


@pytest.mark.asyncio
@patch("custom_components.pawcontrol.dashboard_generator.Store")
async def test_async_cleanup_cancels_tracked_tasks(
    mock_store: MagicMock, hass, mock_config_entry
) -> None:
    """Pending tasks tracked by the generator should be cancelled during cleanup."""

    mock_store.return_value = MagicMock()
    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    cleanup_event = asyncio.Event()

    async def pending_task() -> None:
        await cleanup_event.wait()

    tracked = generator._track_task(pending_task(), name="test-pending-task")

    generator._renderer.cleanup = AsyncMock(return_value=None)
    generator._dashboard_templates.cleanup = AsyncMock(return_value=None)

    await generator.async_cleanup()

    assert tracked.cancelled()
    assert generator._cleanup_tasks == set()


@pytest.mark.asyncio
async def test_store_metadata_includes_notifications_view(
    mock_config_entry,
    tmp_path: Path,
) -> None:
    """Storing dashboard metadata should export the notifications view summary."""

    generator = object.__new__(PawControlDashboardGenerator)
    generator.entry = mock_config_entry
    generator._dashboards = {}
    generator._save_dashboard_metadata_async = AsyncMock(return_value=None)
    generator._performance_metrics = {
        "total_generations": 0,
        "avg_generation_time": 0.0,
        "cache_hits": 0,
        "cache_misses": 0,
        "file_operations": 0,
        "errors": 0,
    }

    dashboard_config = {
        "views": [
            {
                "path": "overview",
                "title": "Overview",
                "icon": "mdi:dog",
                "cards": [{"type": "entities"}],
            },
            {
                "path": MODULE_NOTIFICATIONS,
                "title": "Notifications",
                "icon": "mdi:bell",
                "cards": [
                    {"type": "entities"},
                    {"type": "markdown"},
                    {"type": "horizontal-stack"},
                ],
            },
        ]
    }

    dogs_config = [
        {
            CONF_DOG_ID: "buddy",
            CONF_DOG_NAME: "Buddy",
            "modules": {MODULE_NOTIFICATIONS: True},
        }
    ]

    await generator._store_dashboard_metadata_batch(
        "pawcontrol-main",
        "Paw Control",
        str(tmp_path / "lovelace.pawcontrol-main"),
        dashboard_config,
        dogs_config,
        {"theme": "modern"},
    )

    metadata = generator.get_dashboard_info("pawcontrol-main")
    assert metadata is not None
    assert metadata["has_notifications_view"] is True

    views: list[DashboardViewSummary] = metadata["views"]
    assert any(view["path"] == MODULE_NOTIFICATIONS for view in views)
    notifications_view = next(
        view for view in views if view["path"] == MODULE_NOTIFICATIONS
    )
    assert notifications_view["card_count"] == 3
    assert notifications_view.get("notifications") is True


@pytest.mark.asyncio
async def test_validate_single_dashboard_rehydrates_notifications_view(
    tmp_path: Path,
) -> None:
    """Stored dashboards missing metadata should be refreshed during validation."""

    generator = object.__new__(PawControlDashboardGenerator)

    dashboard_file = tmp_path / "lovelace.test-dashboard"
    config_payload = {
        "views": [
            {
                "path": "overview",
                "title": "Overview",
                "icon": "mdi:dog",
                "cards": [{"type": "entities"}],
            },
            {
                "path": MODULE_NOTIFICATIONS,
                "title": "Notifications",
                "icon": "mdi:bell",
                "cards": [
                    {"type": "entities"},
                    {"type": "markdown"},
                ],
            },
        ]
    }
    dashboard_file.write_text(
        json.dumps({"data": {"config": config_payload}}, ensure_ascii=False),
        encoding="utf-8",
    )

    dashboard_info = {
        "path": str(dashboard_file),
        "title": "Paw Control",
        "created": "2024-01-01T00:00:00+00:00",
        "type": "main",
        "version": 3,
    }

    valid, updated = await generator._validate_single_dashboard("test", dashboard_info)

    assert valid is True
    assert updated is True
    assert dashboard_info["has_notifications_view"] is True

    views = dashboard_info["views"]
    assert isinstance(views, list)
    notifications_view = next(
        view for view in views if view["path"] == MODULE_NOTIFICATIONS
    )
    assert notifications_view["card_count"] == 2
    assert notifications_view.get("module") == MODULE_NOTIFICATIONS
    assert notifications_view.get("notifications") is True
