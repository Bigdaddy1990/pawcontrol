"""Unit tests for the dashboard generator metadata exports."""

import asyncio
from collections.abc import Awaitable, Sequence
import contextlib
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_NOTIFICATIONS,
)
from custom_components.pawcontrol.coordinator_tasks import default_rejection_metrics
from custom_components.pawcontrol.dashboard_generator import (
    DashboardViewSummary,
    PawControlDashboardGenerator,
)
from custom_components.pawcontrol.dashboard_renderer import (
    DashboardRenderer,
    HomeAssistantError,
)


def test_copy_dashboard_options_returns_plain_dict() -> None:
    """Dashboard options should be copied into a JSON-compatible dict."""  # noqa: E111

    readonly_options = MappingProxyType({"theme": "modern", "layout": "full"})  # noqa: E111

    copied = PawControlDashboardGenerator._copy_dashboard_options(readonly_options)  # noqa: E111

    assert copied == {"theme": "modern", "layout": "full"}  # noqa: E111
    assert isinstance(copied, dict)  # noqa: E111
    assert copied is not readonly_options  # noqa: E111

    copied["theme"] = "legacy"  # noqa: E111
    assert readonly_options["theme"] == "modern"  # noqa: E111


def test_copy_dashboard_options_returns_empty_dict_for_none() -> None:
    """``None`` options should yield an empty JSON-compatible dict."""  # noqa: E111

    copied = PawControlDashboardGenerator._copy_dashboard_options(None)  # noqa: E111

    assert copied == {}  # noqa: E111
    assert isinstance(copied, dict)  # noqa: E111


def test_summarise_dashboard_views_marks_notifications() -> None:
    """The view summariser should flag the notifications module view."""  # noqa: E111

    dashboard_config = {  # noqa: E111
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
    )  # noqa: E111

    assert any(summary["path"] == "overview" for summary in summaries)  # noqa: E111

    notifications_summary = next(  # noqa: E111
        summary for summary in summaries if summary["path"] == MODULE_NOTIFICATIONS
    )

    assert notifications_summary["card_count"] == 2  # noqa: E111
    assert notifications_summary.get("module") == MODULE_NOTIFICATIONS  # noqa: E111
    assert notifications_summary.get("notifications") is True  # noqa: E111


def test_normalise_dashboard_registry_filters_invalid_entries() -> None:
    """Stored dashboard registry payloads should be normalised to plain dicts."""  # noqa: E111

    stored_dashboard = MappingProxyType({  # noqa: E111
        "url": "dashboard-1",
        "title": "Primary dashboard",
        "path": "/config/.storage/lovelace.dashboard-1",
        "options": {"theme": "modern", "layout": "full"},
        "updated": "2024-04-02T12:34:56+00:00",
    })

    registry = PawControlDashboardGenerator._normalise_dashboard_registry({  # noqa: E111
        "dashboard-1": stored_dashboard,
        "skipped": "not a mapping",
        42: {"url": "wrong-key"},
    })

    assert registry == {  # noqa: E111
        "dashboard-1": {
            "url": "dashboard-1",
            "title": "Primary dashboard",
            "path": "/config/.storage/lovelace.dashboard-1",
            "options": {"theme": "modern", "layout": "full"},
            "updated": "2024-04-02T12:34:56+00:00",
        }
    }

    restored_dashboard = registry["dashboard-1"]  # noqa: E111
    assert isinstance(restored_dashboard, dict)  # noqa: E111
    assert restored_dashboard is not stored_dashboard  # noqa: E111

    metrics = PawControlDashboardGenerator._coerce_performance_metrics({  # noqa: E111
        "total_generations": "5",
        "avg_generation_time": "2.5",
        "cache_hits": True,
        "cache_misses": 3.9,
        "file_operations": "7",
        "errors": "0",
    })

    assert metrics == {  # noqa: E111
        "total_generations": 5,
        "avg_generation_time": 2.5,
        "cache_hits": 1,
        "cache_misses": 3,
        "file_operations": 7,
        "errors": 0,
    }


@pytest.mark.asyncio
@patch("custom_components.pawcontrol.dashboard_generator.Store")
async def test_generator_initialises_cleanup_tracking(
    mock_store: MagicMock, hass, mock_config_entry
) -> None:
    """Generator initialisation should create the cleanup tracking set."""  # noqa: E111

    mock_store.return_value = MagicMock()  # noqa: E111

    generator = PawControlDashboardGenerator(hass, mock_config_entry)  # noqa: E111

    assert hasattr(generator, "_cleanup_tasks")  # noqa: E111
    assert generator._cleanup_tasks == set()  # noqa: E111


@pytest.mark.asyncio
@patch("custom_components.pawcontrol.dashboard_generator.Store")
async def test_track_task_registers_and_clears(
    mock_store: MagicMock, hass, mock_config_entry
) -> None:
    """Tracked tasks should be cancelled during cleanup and removed on completion."""  # noqa: E111

    mock_store.return_value = MagicMock()  # noqa: E111
    generator = PawControlDashboardGenerator(hass, mock_config_entry)  # noqa: E111

    async def short_task() -> None:  # noqa: E111
        await asyncio.sleep(0)

    task = generator._track_task(short_task(), name="test-short-task")  # noqa: E111
    assert task in generator._cleanup_tasks  # noqa: E111

    await task  # noqa: E111
    await asyncio.sleep(0)  # noqa: E111
    assert task not in generator._cleanup_tasks  # noqa: E111


@pytest.mark.asyncio
async def test_track_task_falls_back_to_asyncio(mock_config_entry) -> None:
    """Use ``asyncio.create_task`` when Home Assistant helper is unavailable."""  # noqa: E111

    generator = object.__new__(PawControlDashboardGenerator)  # noqa: E111
    generator.hass = SimpleNamespace()  # noqa: E111
    generator._cleanup_tasks = set()  # noqa: E111

    async def completes_immediately() -> None:  # noqa: E111
        await asyncio.sleep(0)

    with patch(  # noqa: E111
        "custom_components.pawcontrol.dashboard_generator.asyncio.create_task",
        wraps=asyncio.create_task,
    ) as patched_create_task:
        task = generator._track_task(completes_immediately(), name="fallback-task")

    patched_create_task.assert_called()  # noqa: E111
    assert task in generator._cleanup_tasks  # noqa: E111

    await task  # noqa: E111
    await asyncio.sleep(0)  # noqa: E111

    assert task not in generator._cleanup_tasks  # noqa: E111


@pytest.mark.asyncio
async def test_track_task_uses_hass_loop_when_available(mock_config_entry) -> None:
    """Fallback to ``hass.loop.create_task`` before raw asyncio scheduling."""  # noqa: E111

    loop_mock = MagicMock()  # noqa: E111
    generator = object.__new__(PawControlDashboardGenerator)  # noqa: E111
    generator.hass = SimpleNamespace(loop=loop_mock)  # noqa: E111
    generator._cleanup_tasks = set()  # noqa: E111

    async def completes_immediately() -> None:  # noqa: E111
        await asyncio.sleep(0)

    created: list[asyncio.Task[None]] = []  # noqa: E111

    def _create_task_side_effect(  # noqa: E111
        awaitable: Awaitable[None], *, name: str | None = None
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(awaitable)
        if name and hasattr(task, "set_name"):
            with contextlib.suppress(Exception):  # noqa: E111
                task.set_name(name)
        created.append(task)
        return task

    loop_mock.create_task.side_effect = _create_task_side_effect  # noqa: E111

    task = generator._track_task(completes_immediately(), name="loop-fallback")  # noqa: E111

    loop_mock.create_task.assert_called()  # noqa: E111
    assert created == [task]  # noqa: E111
    assert task in generator._cleanup_tasks  # noqa: E111

    await task  # noqa: E111
    await asyncio.sleep(0)  # noqa: E111

    assert task not in generator._cleanup_tasks  # noqa: E111


@pytest.mark.asyncio
@patch("custom_components.pawcontrol.dashboard_generator.Store")
async def test_track_task_accepts_existing_task(
    mock_store: MagicMock, hass, mock_config_entry
) -> None:
    """Existing tasks should be tracked without being recreated."""  # noqa: E111

    mock_store.return_value = MagicMock()  # noqa: E111

    generator = PawControlDashboardGenerator(hass, mock_config_entry)  # noqa: E111

    async def completes_immediately() -> None:  # noqa: E111
        await asyncio.sleep(0)

    existing_task = hass.async_create_task(completes_immediately())  # noqa: E111

    tracked = generator._track_task(existing_task, name="existing")  # noqa: E111

    assert tracked is existing_task  # noqa: E111
    assert tracked in generator._cleanup_tasks  # noqa: E111

    await tracked  # noqa: E111
    await asyncio.sleep(0)  # noqa: E111

    assert tracked not in generator._cleanup_tasks  # noqa: E111


@pytest.mark.asyncio
async def test_track_task_handles_helper_runtime_error(mock_config_entry) -> None:
    """Gracefully fall back when Home Assistant helper raises ``RuntimeError``."""  # noqa: E111

    class HassStub(SimpleNamespace):  # noqa: E111
        def async_create_task(
            self, awaitable: Awaitable[None], *, name: str | None = None
        ) -> asyncio.Task[None]:
            raise RuntimeError("loop closed")  # noqa: E111

    generator = object.__new__(PawControlDashboardGenerator)  # noqa: E111
    generator.hass = HassStub()  # noqa: E111
    generator._cleanup_tasks = set()  # noqa: E111

    async def completes_immediately() -> None:  # noqa: E111
        await asyncio.sleep(0)

    with patch(  # noqa: E111
        "custom_components.pawcontrol.dashboard_generator.asyncio.create_task",
        wraps=asyncio.create_task,
    ) as patched_create_task:
        task = generator._track_task(completes_immediately(), name="asyncio-fallback")

    patched_create_task.assert_called()  # noqa: E111
    assert task in generator._cleanup_tasks  # noqa: E111

    await task  # noqa: E111
    await asyncio.sleep(0)  # noqa: E111

    assert task not in generator._cleanup_tasks  # noqa: E111


@patch("custom_components.pawcontrol.dashboard_generator.Store")
def test_resolve_coordinator_statistics_uses_runtime_data(
    mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator statistics should be sourced from runtime data helpers."""  # noqa: E111

    mock_store.return_value = MagicMock()  # noqa: E111
    generator = PawControlDashboardGenerator(hass, mock_config_entry)  # noqa: E111
    sentinel_stats = {"rejection_metrics": default_rejection_metrics()}  # noqa: E111

    class CoordinatorStub:  # noqa: E111
        def get_update_statistics(self) -> dict[str, object]:
            return sentinel_stats  # noqa: E111

    class RuntimeStub:  # noqa: E111
        coordinator = CoordinatorStub()

    monkeypatch.setattr(generator, "_get_runtime_data", lambda: RuntimeStub())  # noqa: E111

    resolved = generator._resolve_coordinator_statistics()  # noqa: E111

    assert resolved == sentinel_stats  # noqa: E111
    assert resolved is not sentinel_stats  # noqa: E111


@patch("custom_components.pawcontrol.dashboard_generator.Store")
def test_resolve_service_execution_metrics_uses_runtime_data(
    mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Service execution metrics should reuse runtime performance stats."""  # noqa: E111

    mock_store.return_value = MagicMock()  # noqa: E111
    generator = PawControlDashboardGenerator(hass, mock_config_entry)  # noqa: E111

    service_metrics = default_rejection_metrics()  # noqa: E111
    service_metrics.update({  # noqa: E111
        "rejected_call_count": 4,
        "rejection_breaker_count": 1,
        "last_rejection_time": 42.0,
        "last_rejection_breaker_id": "automation",
    })

    class RuntimeStub:  # noqa: E111
        def __init__(self) -> None:
            self.performance_stats = {"rejection_metrics": service_metrics}  # noqa: E111

    monkeypatch.setattr(generator, "_get_runtime_data", lambda: RuntimeStub())  # noqa: E111

    resolved = generator._resolve_service_execution_metrics()  # noqa: E111

    assert resolved is not None  # noqa: E111
    assert resolved["rejected_call_count"] == 4  # noqa: E111
    assert resolved["rejection_breaker_count"] == 1  # noqa: E111
    assert resolved["last_rejection_breaker_id"] == "automation"  # noqa: E111
    assert resolved["schema_version"] == default_rejection_metrics()["schema_version"]  # noqa: E111


@patch("custom_components.pawcontrol.dashboard_generator.Store")
def test_resolve_service_guard_metrics_uses_runtime_data(
    mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard metrics should be normalised from runtime performance stats."""  # noqa: E111

    mock_store.return_value = MagicMock()  # noqa: E111
    generator = PawControlDashboardGenerator(hass, mock_config_entry)  # noqa: E111

    guard_metrics = {  # noqa: E111
        "executed": 3,
        "skipped": 2,
        "reasons": {"quiet_hours": 2},
        "last_results": [
            {
                "domain": "notify",
                "service": "mobile_app",
                "executed": False,
                "reason": "quiet_hours",
            }
        ],
    }

    class RuntimeStub:  # noqa: E111
        def __init__(self) -> None:
            self.performance_stats = {"service_guard_metrics": guard_metrics}  # noqa: E111

    monkeypatch.setattr(generator, "_get_runtime_data", lambda: RuntimeStub())  # noqa: E111

    resolved = generator._resolve_service_guard_metrics()  # noqa: E111

    assert resolved is not None  # noqa: E111
    assert resolved is not guard_metrics  # noqa: E111
    assert resolved["executed"] == 3  # noqa: E111
    assert resolved["skipped"] == 2  # noqa: E111
    assert resolved["reasons"] == {"quiet_hours": 2}  # noqa: E111
    assert resolved["last_results"][0]["service"] == "mobile_app"  # noqa: E111


@pytest.mark.asyncio
async def test_renderer_forwards_statistics_context(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The statistics renderer should receive coordinator and service metrics."""  # noqa: E111

    renderer = DashboardRenderer(hass)  # noqa: E111
    sentinel_stats = {"rejection_metrics": default_rejection_metrics()}  # noqa: E111
    service_metrics = default_rejection_metrics()  # noqa: E111
    guard_metrics = {  # noqa: E111
        "executed": 5,
        "skipped": 1,
        "reasons": {"quiet_hours": 1},
        "last_results": [],
    }

    monkeypatch.setattr(  # noqa: E111
        renderer,
        "_render_overview_view",
        AsyncMock(return_value={"path": "overview", "cards": []}),
    )
    monkeypatch.setattr(  # noqa: E111
        renderer,
        "_render_dog_views_batch",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(  # noqa: E111
        renderer,
        "_render_settings_view",
        AsyncMock(return_value={"path": "settings", "cards": []}),
    )

    captured: dict[str, object] = {}  # noqa: E111

    async def _capture_statistics(  # noqa: E111
        dogs_config: Sequence[dict[str, object]],
        options: dict[str, object],
        *,
        coordinator_statistics: dict[str, object] | None = None,
        service_execution_metrics: dict[str, object] | None = None,
        service_guard_metrics: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        captured["coordinator_statistics"] = coordinator_statistics
        captured["service_execution_metrics"] = service_execution_metrics
        captured["service_guard_metrics"] = service_guard_metrics
        return []

    monkeypatch.setattr(  # noqa: E111
        renderer.stats_generator,
        "generate_statistics_cards",
        AsyncMock(side_effect=_capture_statistics),
    )

    await renderer.render_main_dashboard(  # noqa: E111
        [
            {
                CONF_DOG_ID: "fido",
                CONF_DOG_NAME: "Fido",
                "modules": {MODULE_NOTIFICATIONS: True},
            }
        ],
        coordinator_statistics=sentinel_stats,
        service_execution_metrics=service_metrics,
        service_guard_metrics=guard_metrics,
    )

    assert captured["coordinator_statistics"] == sentinel_stats  # noqa: E111
    assert captured["service_execution_metrics"] == service_metrics  # noqa: E111
    assert captured["service_guard_metrics"] == guard_metrics  # noqa: E111


@pytest.mark.asyncio
async def test_write_dashboard_file_preserves_existing_file_on_error(
    hass, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed writes should not corrupt the existing dashboard file."""  # noqa: E111

    renderer = DashboardRenderer(hass)  # noqa: E111
    file_path = tmp_path / "dashboard.json"  # noqa: E111
    file_path.write_text("original", encoding="utf-8")  # noqa: E111

    def _raise_open(*args: object, **kwargs: object) -> None:  # noqa: E111
        raise OSError("disk full")

    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.dashboard_renderer.aiofiles.open",
        _raise_open,
    )

    with pytest.raises(HomeAssistantError):  # noqa: E111
        await renderer.write_dashboard_file({"views": []}, file_path)

    assert file_path.read_text(encoding="utf-8") == "original"  # noqa: E111
    remaining = {path for path in tmp_path.iterdir() if path != file_path}  # noqa: E111
    assert remaining == set()  # noqa: E111


@pytest.mark.asyncio
@patch("custom_components.pawcontrol.dashboard_generator.Store")
async def test_async_cleanup_cancels_tracked_tasks(
    mock_store: MagicMock, hass, mock_config_entry
) -> None:
    """Pending tasks tracked by the generator should be cancelled during cleanup."""  # noqa: E111

    mock_store.return_value = MagicMock()  # noqa: E111
    generator = PawControlDashboardGenerator(hass, mock_config_entry)  # noqa: E111

    cleanup_event = asyncio.Event()  # noqa: E111

    async def pending_task() -> None:  # noqa: E111
        await cleanup_event.wait()

    tracked = generator._track_task(pending_task(), name="test-pending-task")  # noqa: E111

    generator._renderer.cleanup = AsyncMock(return_value=None)  # noqa: E111
    generator._dashboard_templates.cleanup = AsyncMock(return_value=None)  # noqa: E111

    await generator.async_cleanup()  # noqa: E111

    assert tracked.cancelled()  # noqa: E111
    assert generator._cleanup_tasks == set()  # noqa: E111


@pytest.mark.asyncio
async def test_store_metadata_includes_notifications_view(
    mock_config_entry,
    tmp_path: Path,
) -> None:
    """Storing dashboard metadata should export the notifications view summary."""  # noqa: E111

    generator = object.__new__(PawControlDashboardGenerator)  # noqa: E111
    generator.entry = mock_config_entry  # noqa: E111
    generator._dashboards = {}  # noqa: E111
    generator._save_dashboard_metadata_async = AsyncMock(return_value=None)  # noqa: E111
    generator._performance_metrics = {  # noqa: E111
        "total_generations": 0,
        "avg_generation_time": 0.0,
        "cache_hits": 0,
        "cache_misses": 0,
        "file_operations": 0,
        "errors": 0,
    }

    dashboard_config = {  # noqa: E111
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

    dogs_config = [  # noqa: E111
        {
            CONF_DOG_ID: "buddy",
            CONF_DOG_NAME: "Buddy",
            "modules": {MODULE_NOTIFICATIONS: True},
        }
    ]

    await generator._store_dashboard_metadata_batch(  # noqa: E111
        "pawcontrol-main",
        "Paw Control",
        str(tmp_path / "lovelace.pawcontrol-main"),
        dashboard_config,
        dogs_config,
        {"theme": "modern"},
    )

    metadata = generator.get_dashboard_info("pawcontrol-main")  # noqa: E111
    assert metadata is not None  # noqa: E111
    assert metadata["has_notifications_view"] is True  # noqa: E111

    views: list[DashboardViewSummary] = metadata["views"]  # noqa: E111
    assert any(view["path"] == MODULE_NOTIFICATIONS for view in views)  # noqa: E111
    notifications_view = next(  # noqa: E111
        view for view in views if view["path"] == MODULE_NOTIFICATIONS
    )
    assert notifications_view["card_count"] == 3  # noqa: E111
    assert notifications_view.get("notifications") is True  # noqa: E111


@pytest.mark.asyncio
async def test_validate_single_dashboard_rehydrates_notifications_view(
    tmp_path: Path,
) -> None:
    """Stored dashboards missing metadata should be refreshed during validation."""  # noqa: E111

    generator = object.__new__(PawControlDashboardGenerator)  # noqa: E111

    dashboard_file = tmp_path / "lovelace.test-dashboard"  # noqa: E111
    config_payload = {  # noqa: E111
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
    dashboard_file.write_text(  # noqa: E111
        json.dumps({"data": {"config": config_payload}}, ensure_ascii=False),
        encoding="utf-8",
    )

    dashboard_info = {  # noqa: E111
        "path": str(dashboard_file),
        "title": "Paw Control",
        "created": "2024-01-01T00:00:00+00:00",
        "type": "main",
        "version": 3,
    }

    valid, updated = await generator._validate_single_dashboard("test", dashboard_info)  # noqa: E111

    assert valid is True  # noqa: E111
    assert updated is True  # noqa: E111
    assert dashboard_info["has_notifications_view"] is True  # noqa: E111

    views = dashboard_info["views"]  # noqa: E111
    assert isinstance(views, list)  # noqa: E111
    notifications_view = next(  # noqa: E111
        view for view in views if view["path"] == MODULE_NOTIFICATIONS
    )
    assert notifications_view["card_count"] == 2  # noqa: E111
    assert notifications_view.get("module") == MODULE_NOTIFICATIONS  # noqa: E111
    assert notifications_view.get("notifications") is True  # noqa: E111
