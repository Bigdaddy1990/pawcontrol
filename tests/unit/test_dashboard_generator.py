"""Unit tests for the dashboard generator metadata exports."""

import asyncio
from collections.abc import Awaitable, Sequence
import contextlib
from datetime import UTC, datetime
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
    MODULE_WEATHER,
)
from custom_components.pawcontrol.coordinator_tasks import default_rejection_metrics
from custom_components.pawcontrol.dashboard_generator import (
    DashboardViewSummary,
    PawControlDashboardGenerator,
)
from custom_components.pawcontrol.dashboard_renderer import (
    DashboardRenderer,
    HomeAssistantError,
    RenderJob,
)


def test_copy_dashboard_options_returns_plain_dict() -> None:
    """Dashboard options should be copied into a JSON-compatible dict."""
    readonly_options = MappingProxyType({"theme": "modern", "layout": "full"})

    copied = PawControlDashboardGenerator._copy_dashboard_options(readonly_options)

    assert copied == {"theme": "modern", "layout": "full"}
    assert isinstance(copied, dict)
    assert copied is not readonly_options

    copied["theme"] = "legacy"
    assert readonly_options["theme"] == "modern"


def test_copy_dashboard_options_returns_empty_dict_for_none() -> None:
    """``None`` options should yield an empty JSON-compatible dict."""
    copied = PawControlDashboardGenerator._copy_dashboard_options(None)

    assert copied == {}
    assert isinstance(copied, dict)


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


def test_summarise_dashboard_views_skips_non_sequence_payload() -> None:
    """View summaries should return an empty list for invalid ``views`` payloads."""
    assert (
        PawControlDashboardGenerator._summarise_dashboard_views({"views": "invalid"})
        == []
    )


def test_normalize_view_summaries_backfills_module_and_notifications() -> None:
    """Normalised summaries should infer module paths and notification flags."""
    summaries = PawControlDashboardGenerator._normalize_view_summaries([
        {
            "path": MODULE_WEATHER,
            "title": "Weather",
            "icon": "mdi:weather-partly-cloudy",
            "card_count": "4",
        },
        {
            "path": MODULE_NOTIFICATIONS,
            "title": "Notifications",
            "icon": "mdi:bell",
            "card_count": -2,
        },
    ])

    assert summaries == [
        {
            "path": MODULE_WEATHER,
            "title": "Weather",
            "icon": "mdi:weather-partly-cloudy",
            "card_count": 4,
            "module": MODULE_WEATHER,
        },
        {
            "path": MODULE_NOTIFICATIONS,
            "title": "Notifications",
            "icon": "mdi:bell",
            "card_count": 0,
            "module": MODULE_NOTIFICATIONS,
            "notifications": True,
        },
    ]


def test_normalize_view_summaries_rejects_invalid_items() -> None:
    """Invalid normalisation payloads should produce ``None``."""
    assert PawControlDashboardGenerator._normalize_view_summaries("invalid") is None
    assert (
        PawControlDashboardGenerator._normalize_view_summaries([{"path": "ok"}, 1])
        is None
    )


def test_has_notifications_view_detects_module_path() -> None:
    """Notification view detection should use normalised summary paths."""
    assert PawControlDashboardGenerator._has_notifications_view([
        {"path": "overview", "title": "", "icon": "", "card_count": 0},
        {
            "path": MODULE_NOTIFICATIONS,
            "title": "Notifications",
            "icon": "mdi:bell",
            "card_count": 1,
        },
    ])
    assert not PawControlDashboardGenerator._has_notifications_view([
        {"path": "overview", "title": "", "icon": "", "card_count": 0}
    ])


def test_normalise_dashboard_registry_filters_invalid_entries() -> None:
    """Stored dashboard registry payloads should be normalised to plain dicts."""
    stored_dashboard = MappingProxyType({
        "url": "dashboard-1",
        "title": "Primary dashboard",
        "path": "/config/.storage/lovelace.dashboard-1",
        "options": {"theme": "modern", "layout": "full"},
        "updated": "2024-04-02T12:34:56+00:00",
    })

    registry = PawControlDashboardGenerator._normalise_dashboard_registry({
        "dashboard-1": stored_dashboard,
        "skipped": "not a mapping",
        42: {"url": "wrong-key"},
    })

    assert registry == {
        "dashboard-1": {
            "url": "dashboard-1",
            "title": "Primary dashboard",
            "path": "/config/.storage/lovelace.dashboard-1",
            "options": {"theme": "modern", "layout": "full"},
            "updated": "2024-04-02T12:34:56+00:00",
        }
    }

    restored_dashboard = registry["dashboard-1"]
    assert isinstance(restored_dashboard, dict)
    assert restored_dashboard is not stored_dashboard

    metrics = PawControlDashboardGenerator._coerce_performance_metrics({
        "total_generations": "5",
        "avg_generation_time": "2.5",
        "cache_hits": True,
        "cache_misses": 3.9,
        "file_operations": "7",
        "errors": "0",
    })

    assert metrics == {
        "total_generations": 5,
        "avg_generation_time": 2.5,
        "cache_hits": 1,
        "cache_misses": 3,
        "file_operations": 7,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_load_dashboard_config_handles_valid_and_invalid_files(
    tmp_path: Path,
) -> None:
    """Dashboard config loader should parse valid files and ignore invalid content."""
    generator = object.__new__(PawControlDashboardGenerator)

    valid_file = tmp_path / "valid.json"
    valid_file.write_text(
        json.dumps({"data": {"config": {"views": [{"path": "overview"}]}}}),
        encoding="utf-8",
    )

    invalid_json_file = tmp_path / "invalid.json"
    invalid_json_file.write_text("{", encoding="utf-8")

    no_config_file = tmp_path / "no-config.json"
    no_config_file.write_text(json.dumps({"data": {}}), encoding="utf-8")

    assert await generator._load_dashboard_config(valid_file) == {
        "views": [{"path": "overview"}]
    }
    assert await generator._load_dashboard_config(invalid_json_file) is None
    assert await generator._load_dashboard_config(no_config_file) is None
    assert await generator._load_dashboard_config(tmp_path / "missing.json") is None


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


@patch("custom_components.pawcontrol.dashboard_generator.Store")
def test_resolve_coordinator_statistics_uses_runtime_data(
    mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator statistics should be sourced from runtime data helpers."""
    mock_store.return_value = MagicMock()
    generator = PawControlDashboardGenerator(hass, mock_config_entry)
    sentinel_stats = {"rejection_metrics": default_rejection_metrics()}

    class CoordinatorStub:
        def get_update_statistics(self) -> dict[str, object]:
            return sentinel_stats

    class RuntimeStub:
        coordinator = CoordinatorStub()

    monkeypatch.setattr(generator, "_get_runtime_data", lambda: RuntimeStub())

    resolved = generator._resolve_coordinator_statistics()

    assert resolved == sentinel_stats
    assert resolved is not sentinel_stats


@patch("custom_components.pawcontrol.dashboard_generator.Store")
def test_resolve_coordinator_statistics_requires_callable_provider(
    mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator statistics require a callable provider on the coordinator."""
    mock_store.return_value = MagicMock()
    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    class RuntimeStub:
        coordinator = SimpleNamespace(get_update_statistics="not-callable")

    monkeypatch.setattr(generator, "_get_runtime_data", lambda: RuntimeStub())

    assert generator._resolve_coordinator_statistics() is None


@patch("custom_components.pawcontrol.dashboard_generator.Store")
def test_resolve_coordinator_statistics_handles_provider_exception(
    mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Statistics resolution should return ``None`` when provider raises."""
    mock_store.return_value = MagicMock()
    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    class CoordinatorStub:
        @staticmethod
        def get_update_statistics() -> dict[str, object]:
            msg = "boom"
            raise RuntimeError(msg)

    class RuntimeStub:
        coordinator = CoordinatorStub()

    monkeypatch.setattr(generator, "_get_runtime_data", lambda: RuntimeStub())

    assert generator._resolve_coordinator_statistics() is None


@patch("custom_components.pawcontrol.dashboard_generator.Store")
def test_resolve_coordinator_statistics_returns_non_mapping_payload(
    mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-mapping statistics payloads should be returned unchanged."""
    mock_store.return_value = MagicMock()
    generator = PawControlDashboardGenerator(hass, mock_config_entry)
    sentinel = ["unexpected", "payload"]

    class CoordinatorStub:
        @staticmethod
        def get_update_statistics() -> list[str]:
            return sentinel

    class RuntimeStub:
        coordinator = CoordinatorStub()

    monkeypatch.setattr(generator, "_get_runtime_data", lambda: RuntimeStub())

    assert generator._resolve_coordinator_statistics() == sentinel


@patch("custom_components.pawcontrol.dashboard_generator.Store")
def test_resolve_service_execution_metrics_uses_runtime_data(
    mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Service execution metrics should reuse runtime performance stats."""
    mock_store.return_value = MagicMock()
    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    service_metrics = default_rejection_metrics()
    service_metrics.update({
        "rejected_call_count": 4,
        "rejection_breaker_count": 1,
        "last_rejection_time": 42.0,
        "last_rejection_breaker_id": "automation",
    })

    class RuntimeStub:
        def __init__(self) -> None:
            self.performance_stats = {"rejection_metrics": service_metrics}

    monkeypatch.setattr(generator, "_get_runtime_data", lambda: RuntimeStub())

    resolved = generator._resolve_service_execution_metrics()

    assert resolved is not None
    assert resolved["rejected_call_count"] == 4
    assert resolved["rejection_breaker_count"] == 1
    assert resolved["last_rejection_breaker_id"] == "automation"
    assert resolved["schema_version"] == default_rejection_metrics()["schema_version"]


@patch("custom_components.pawcontrol.dashboard_generator.Store")
def test_resolve_service_guard_metrics_uses_runtime_data(
    mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard metrics should be normalised from runtime performance stats."""
    mock_store.return_value = MagicMock()
    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    guard_metrics = {
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

    class RuntimeStub:
        def __init__(self) -> None:
            self.performance_stats = {"service_guard_metrics": guard_metrics}

    monkeypatch.setattr(generator, "_get_runtime_data", lambda: RuntimeStub())

    resolved = generator._resolve_service_guard_metrics()

    assert resolved is not None
    assert resolved is not guard_metrics
    assert resolved["executed"] == 3
    assert resolved["skipped"] == 2
    assert resolved["reasons"] == {"quiet_hours": 2}
    assert resolved["last_results"][0]["service"] == "mobile_app"


@pytest.mark.asyncio
async def test_renderer_forwards_statistics_context(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The statistics renderer should receive coordinator and service metrics."""
    renderer = DashboardRenderer(hass)
    sentinel_stats = {"rejection_metrics": default_rejection_metrics()}
    service_metrics = default_rejection_metrics()
    guard_metrics = {
        "executed": 5,
        "skipped": 1,
        "reasons": {"quiet_hours": 1},
        "last_results": [],
    }

    monkeypatch.setattr(
        renderer,
        "_render_overview_view",
        AsyncMock(return_value={"path": "overview", "cards": []}),
    )
    monkeypatch.setattr(
        renderer,
        "_render_dog_views_batch",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        renderer,
        "_render_settings_view",
        AsyncMock(return_value={"path": "settings", "cards": []}),
    )

    captured: dict[str, object] = {}

    async def _capture_statistics(
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

    monkeypatch.setattr(
        renderer.stats_generator,
        "generate_statistics_cards",
        AsyncMock(side_effect=_capture_statistics),
    )

    await renderer.render_main_dashboard(
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

    assert captured["coordinator_statistics"] == sentinel_stats
    assert captured["service_execution_metrics"] == service_metrics
    assert captured["service_guard_metrics"] == guard_metrics


@pytest.mark.asyncio
async def test_renderer_main_dashboard_returns_empty_for_invalid_payload(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid dashboard payloads should short-circuit with an empty result."""
    renderer = DashboardRenderer(hass)
    execute_job = AsyncMock()
    monkeypatch.setattr(renderer, "_execute_render_job", execute_job)

    empty_for_none = await renderer.render_main_dashboard(None)
    empty_for_string = await renderer.render_main_dashboard("invalid")

    assert empty_for_none == {"views": []}
    assert empty_for_string == {"views": []}
    execute_job.assert_not_called()


@pytest.mark.asyncio
async def test_renderer_dog_dashboard_returns_empty_for_invalid_payload(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid per-dog payloads should skip rendering and return empty views."""
    renderer = DashboardRenderer(hass)
    execute_job = AsyncMock()
    monkeypatch.setattr(renderer, "_execute_render_job", execute_job)

    empty_for_none = await renderer.render_dog_dashboard(None)
    empty_for_mapping = await renderer.render_dog_dashboard({"name": "Buddy"})

    assert empty_for_none == {"views": []}
    assert empty_for_mapping == {"views": []}
    execute_job.assert_not_called()


@pytest.mark.asyncio
async def test_renderer_activity_summary_uses_available_entities(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Activity summary should include only dogs with tracked activity sensors."""
    renderer = DashboardRenderer(hass)
    hass.states.async_set("sensor.fido_activity_level", "active")

    template_result = {
        "type": "history-graph",
        "entities": ["sensor.fido_activity_level"],
    }
    history_graph_template = AsyncMock(return_value=template_result)
    monkeypatch.setattr(
        renderer.templates,
        "get_history_graph_template",
        history_graph_template,
    )

    activity_summary = await renderer._render_activity_summary([
        {CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido"},
        {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"},
        {CONF_DOG_NAME: "Missing Id"},
    ])

    assert activity_summary == template_result
    history_graph_template.assert_awaited_once_with(
        ["sensor.fido_activity_level"],
        "Activity Summary",
        24,
    )


@pytest.mark.asyncio
async def test_renderer_activity_summary_returns_none_without_entities(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Activity summary should be skipped when no activity entities exist."""
    renderer = DashboardRenderer(hass)
    history_graph_template = AsyncMock()
    monkeypatch.setattr(
        renderer.templates,
        "get_history_graph_template",
        history_graph_template,
    )

    activity_summary = await renderer._render_activity_summary(
        [{CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"}],
    )

    assert activity_summary is None
    history_graph_template.assert_not_awaited()


@pytest.mark.asyncio
async def test_renderer_dog_dashboard_creates_and_executes_job(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid dog dashboard payloads should build a dog render job."""
    renderer = DashboardRenderer(hass)
    captured: dict[str, object] = {}

    async def _capture_job(job: RenderJob) -> dict[str, object]:
        captured["job"] = job
        return {"views": [{"path": "overview", "cards": []}]}

    monkeypatch.setattr(renderer, "_execute_render_job", _capture_job)

    result = await renderer.render_dog_dashboard(
        {CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}},
        {"theme": "night"},
    )

    job = captured["job"]
    assert isinstance(job, RenderJob)
    assert job.job_type == "dog_dashboard"
    assert job.config == {
        "dog": {CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}}
    }
    assert job.options == {"theme": "night"}
    assert result == {"views": [{"path": "overview", "cards": []}]}


@pytest.mark.asyncio
async def test_renderer_execute_render_job_processes_dog_dashboard_jobs(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dog dashboard jobs should use the dedicated dog renderer path."""
    renderer = DashboardRenderer(hass)
    job = RenderJob(
        "dog-job-1",
        "dog_dashboard",
        {"dog": {CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}}},
    )
    render_dog_job = AsyncMock(return_value={"views": [{"path": "overview"}]})
    monkeypatch.setattr(renderer, "_render_dog_dashboard_job", render_dog_job)

    result = await renderer._execute_render_job(job)

    render_dog_job.assert_awaited_once_with(job)
    assert job.status == "completed"
    assert job.result == result
    assert renderer._active_jobs == {}


@pytest.mark.asyncio
async def test_renderer_dog_overview_module_views_and_settings_skip_empty_results(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dog overview helpers should skip empty module views and invalid dogs."""
    renderer = DashboardRenderer(hass)
    dog = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_NOTIFICATIONS: True},
    }
    overview_cards = [{"type": "entities", "title": "Overview"}]
    monkeypatch.setattr(
        renderer.dog_generator,
        "generate_dog_overview_cards",
        AsyncMock(return_value=overview_cards),
    )
    monkeypatch.setattr(
        renderer.module_generator,
        "generate_notification_cards",
        AsyncMock(return_value=[]),
    )

    overview = await renderer._render_dog_overview_view(dog, {"theme": "night"})
    module_views = await renderer._render_module_views(dog, {"theme": "night"})
    settings = await renderer._render_settings_view(
        [dog, {CONF_DOG_ID: "missing-name"}, {CONF_DOG_NAME: "Missing Id"}],
        {},
    )

    assert overview == {
        "title": "Overview",
        "path": "overview",
        "icon": "mdi:dog",
        "cards": overview_cards,
    }
    assert module_views == []
    assert len(settings["cards"]) == 2
    assert settings["cards"][1]["title"] == "Fido Settings"


@pytest.mark.asyncio
async def test_renderer_execute_render_job_marks_timeout(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timeouts should be converted into Home Assistant errors with job cleanup."""
    renderer = DashboardRenderer(hass)
    job = RenderJob(
        "timeout-1",
        "main_dashboard",
        {"dogs": [{CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}}]},
    )

    monkeypatch.setattr(
        renderer,
        "_render_main_dashboard_job",
        AsyncMock(side_effect=TimeoutError()),
    )

    with pytest.raises(HomeAssistantError, match="Dashboard rendering timeout"):
        await renderer._execute_render_job(job)

    assert job.status == "timeout"
    assert job.error == "Rendering timed out"
    assert renderer._active_jobs == {}


@pytest.mark.asyncio
async def test_renderer_jobs_return_empty_views_when_job_payloads_are_invalid(
    hass,
) -> None:
    """Renderer job helpers should short-circuit when config coercion fails."""
    renderer = DashboardRenderer(hass)

    main_job = RenderJob("main-invalid", "main_dashboard", {"dogs": "invalid"})
    dog_job = RenderJob(
        "dog-invalid", "dog_dashboard", {"dog": {CONF_DOG_NAME: "Buddy"}}
    )

    assert await renderer._render_main_dashboard_job(main_job) == {"views": []}
    assert await renderer._render_dog_dashboard_job(dog_job) == {"views": []}


@pytest.mark.asyncio
async def test_renderer_single_dog_view_validates_required_fields_and_normalises_path(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Single-dog rendering should skip incomplete configs and normalise paths."""
    renderer = DashboardRenderer(hass)
    cards = [{"type": "entities"}]

    monkeypatch.setattr(
        renderer.dog_generator,
        "generate_dog_overview_cards",
        AsyncMock(return_value=cards),
    )

    assert (
        await renderer._render_single_dog_view({CONF_DOG_NAME: "Buddy"}, 0, {}) is None
    )
    assert await renderer._render_single_dog_view({CONF_DOG_ID: "buddy"}, 0, {}) is None

    rendered = await renderer._render_single_dog_view(
        {CONF_DOG_ID: "Sir Barks A Lot", CONF_DOG_NAME: "Sir Barks A Lot"},
        8,
        {"theme": "midnight"},
    )

    assert rendered == {
        "title": "Sir Barks A Lot",
        "path": "sir_barks_a_lot",
        "icon": "mdi:dog",
        "theme": "midnight",
        "cards": cards,
    }
    assert renderer._get_dog_theme(8) == renderer._get_dog_theme(2)


@pytest.mark.asyncio
async def test_renderer_batch_and_module_helpers_handle_empty_and_failed_paths(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batch and module helpers should safely ignore empty inputs and failures."""
    renderer = DashboardRenderer(hass)

    assert await renderer._render_dog_views_batch([], {"theme": "modern"}) == []

    module_view = await renderer._render_module_view(
        {CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}},
        {},
        "notifications",
        "Notifications",
        "mdi:bell",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    assert module_view is None


@pytest.mark.asyncio
async def test_renderer_execute_render_job_wraps_unknown_job_types(
    hass,
) -> None:
    """Unknown render jobs should surface a Home Assistant friendly error."""
    renderer = DashboardRenderer(hass)
    job = RenderJob("job-1", "unsupported", {"dogs": []})

    with pytest.raises(HomeAssistantError, match="Dashboard rendering failed"):
        await renderer._execute_render_job(job)  # type: ignore[arg-type]

    assert job.status == "error"
    assert "Unknown job type" in (job.error or "")
    assert renderer._active_jobs == {}


@pytest.mark.asyncio
async def test_renderer_main_and_dog_jobs_build_expected_views(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dashboard jobs should aggregate the views returned by helper renderers."""
    renderer = DashboardRenderer(hass)

    overview_view = {"path": "overview", "cards": []}
    statistics_view = {"path": "statistics", "cards": []}
    settings_view = {"path": "settings", "cards": []}
    dog_overview_view = {"path": "overview", "cards": []}
    module_view = {"path": "feeding", "cards": []}

    monkeypatch.setattr(
        renderer,
        "_render_overview_view",
        AsyncMock(return_value=overview_view),
    )
    monkeypatch.setattr(
        renderer,
        "_render_dog_views_batch",
        AsyncMock(return_value=[{"path": "fido", "cards": []}]),
    )
    monkeypatch.setattr(
        renderer,
        "_render_statistics_view",
        AsyncMock(return_value=statistics_view),
    )
    monkeypatch.setattr(
        renderer,
        "_render_settings_view",
        AsyncMock(return_value=settings_view),
    )
    monkeypatch.setattr(
        renderer,
        "_render_dog_overview_view",
        AsyncMock(return_value=dog_overview_view),
    )
    monkeypatch.setattr(
        renderer,
        "_render_module_views",
        AsyncMock(return_value=[module_view]),
    )

    main_job = RenderJob(
        "main-1",
        "main_dashboard",
        {"dogs": [{CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}}]},
        {"show_statistics": True, "show_settings": True},
    )
    dog_job = RenderJob(
        "dog-1",
        "dog_dashboard",
        {"dog": {CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}}},
        {},
    )

    main_result = await renderer._render_main_dashboard_job(main_job)
    dog_result = await renderer._render_dog_dashboard_job(dog_job)

    assert [view["path"] for view in main_result["views"]] == [
        "overview",
        "fido",
        "statistics",
        "settings",
    ]
    assert [view["path"] for view in dog_result["views"]] == [
        "overview",
        "feeding",
    ]


@pytest.mark.asyncio
async def test_renderer_overview_view_uses_navigation_url_and_skips_failures(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overview rendering should keep successful cards even when one task fails."""
    renderer = DashboardRenderer(hass)
    dog_config = [{CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}}]

    welcome_card = {"type": "markdown"}
    dog_grid_card = {"type": "grid"}

    monkeypatch.setattr(
        renderer.overview_generator,
        "generate_welcome_card",
        AsyncMock(return_value=welcome_card),
    )
    dogs_grid = AsyncMock(return_value=dog_grid_card)
    monkeypatch.setattr(
        renderer.overview_generator,
        "generate_dogs_grid",
        dogs_grid,
    )
    monkeypatch.setattr(
        renderer.overview_generator,
        "generate_quick_actions",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(
        renderer,
        "_render_activity_summary",
        AsyncMock(return_value=None),
    )

    result = await renderer._render_overview_view(
        dog_config,
        {"dashboard_url": "/lovelace/paws", "show_activity_summary": True},
    )

    assert result["path"] == "overview"
    assert result["cards"] == [welcome_card, dog_grid_card]
    dogs_grid.assert_awaited_once_with(dog_config, "/lovelace/paws")


@pytest.mark.asyncio
async def test_renderer_overview_view_uses_default_navigation_without_activity_summary(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overview rendering should fall back to the default URL when invalid options are provided."""  # noqa: E501
    renderer = DashboardRenderer(hass)
    dog_config = [{CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}}]

    monkeypatch.setattr(
        renderer.overview_generator,
        "generate_welcome_card",
        AsyncMock(return_value={"type": "markdown", "content": "welcome"}),
    )
    dogs_grid = AsyncMock(return_value={"type": "grid", "cards": []})
    monkeypatch.setattr(
        renderer.overview_generator,
        "generate_dogs_grid",
        dogs_grid,
    )
    monkeypatch.setattr(
        renderer.overview_generator,
        "generate_quick_actions",
        AsyncMock(return_value={"type": "entities", "entities": []}),
    )
    activity_summary = AsyncMock(return_value={"type": "history-graph"})
    monkeypatch.setattr(renderer, "_render_activity_summary", activity_summary)

    result = await renderer._render_overview_view(
        dog_config,
        {"dashboard_url": 123, "show_activity_summary": False},
    )

    assert result["path"] == "overview"
    assert len(result["cards"]) == 3
    dogs_grid.assert_awaited_once_with(dog_config, "/paw-control")
    activity_summary.assert_not_called()


@pytest.mark.asyncio
async def test_renderer_dog_view_batch_and_module_rendering_skip_invalid_results(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dog and module batch renderers should discard invalid or failing payloads."""
    renderer = DashboardRenderer(hass)
    dogs = [
        {CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {"feeding": True}},
        {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy", "modules": {"feeding": True}},
    ]

    async def _single_dog_view(
        dog_config: dict[str, object], index: int, options: dict[str, object]
    ) -> dict[str, object] | None:
        if dog_config[CONF_DOG_ID] == "fido":
            return {"path": "fido", "cards": [], "index": index, **options}
        raise RuntimeError("dog view failure")

    monkeypatch.setattr(renderer, "_render_single_dog_view", _single_dog_view)

    dog_views = await renderer._render_dog_views_batch(dogs, {"theme": "modern"})

    assert [view["path"] for view in dog_views] == ["fido"]

    feeding_cards = [{"type": "entities"}]
    monkeypatch.setattr(
        renderer.module_generator,
        "generate_feeding_cards",
        AsyncMock(return_value=feeding_cards),
    )
    monkeypatch.setattr(
        renderer.module_generator,
        "generate_walk_cards",
        AsyncMock(side_effect=AssertionError("walk cards should not run")),
    )

    module_views = await renderer._render_module_views(dogs[0], {"theme": "modern"})

    assert module_views == [
        {
            "title": "Feeding",
            "path": "feeding",
            "icon": "mdi:food-drumstick",
            "cards": feeding_cards,
        }
    ]


@pytest.mark.asyncio
async def test_renderer_module_settings_and_stats_helpers(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Renderer helpers should expose module views, settings, and stats cleanly."""
    renderer = DashboardRenderer(hass)
    dog_config = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {
            "gps": True,
            "visitor": True,
            MODULE_NOTIFICATIONS: True,
        },
    }

    cards = [{"type": "entities"}]

    async def _generator(
        dog: dict[str, object], options: dict[str, object]
    ) -> list[dict[str, object]]:
        assert dog == dog_config
        assert options == {"theme": "midnight"}
        return cards

    module_view = await renderer._render_module_view(
        dog_config,
        {"theme": "midnight"},
        "notifications",
        "Notifications",
        "mdi:bell",
        _generator,
    )
    empty_view = await renderer._render_module_view(
        dog_config,
        {},
        "notifications",
        "Notifications",
        "mdi:bell",
        AsyncMock(return_value=[]),
    )

    settings_view = await renderer._render_settings_view([dog_config], {})

    renderer._active_jobs = {
        "job-1": RenderJob("job-1", "main_dashboard", {"dogs": []}),
    }
    renderer._job_counter = 4
    monkeypatch.setattr(
        renderer.templates,
        "get_cache_stats",
        MagicMock(return_value={"entries": 2}),
    )

    stats_before_cleanup = renderer.get_render_stats()
    await renderer.cleanup()

    assert module_view == {
        "title": "Notifications",
        "path": "notifications",
        "icon": "mdi:bell",
        "cards": cards,
    }
    assert empty_view is None
    assert settings_view["cards"][1]["entities"] == [
        "switch.fido_notifications_enabled",
        "switch.fido_gps_tracking_enabled",
        "switch.fido_visitor_mode",
        "select.fido_notification_priority",
    ]
    assert stats_before_cleanup == {
        "active_jobs": 1,
        "total_jobs_processed": 4,
        "template_cache": {"entries": 2},
    }
    assert renderer._active_jobs == {}


@pytest.mark.asyncio
async def test_write_dashboard_file_preserves_existing_file_on_error(
    hass, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed writes should not corrupt the existing dashboard file."""
    renderer = DashboardRenderer(hass)
    file_path = tmp_path / "dashboard.json"
    file_path.write_text("original", encoding="utf-8")

    def _raise_open(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "custom_components.pawcontrol.dashboard_renderer.aiofiles.open",
        _raise_open,
    )

    with pytest.raises(HomeAssistantError):
        await renderer.write_dashboard_file({"views": []}, file_path)

    assert file_path.read_text(encoding="utf-8") == "original"
    remaining = {path for path in tmp_path.iterdir() if path != file_path}
    assert remaining == set()


@pytest.mark.asyncio
async def test_write_dashboard_file_includes_metadata(hass, tmp_path: Path) -> None:
    """Successful writes should persist metadata alongside the config payload."""
    renderer = DashboardRenderer(hass)
    file_path = tmp_path / "dashboard.json"

    await renderer.write_dashboard_file(
        {"views": [{"path": "overview", "cards": []}]},
        file_path,
        metadata={"generated_by": "tests"},
    )

    written_payload = json.loads(file_path.read_text(encoding="utf-8"))

    assert written_payload["data"]["config"]["views"][0]["path"] == "overview"
    assert written_payload["data"]["generated_by"] == "tests"


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


@pytest.mark.asyncio
async def test_renderer_main_job_skips_optional_views_when_disabled(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Main jobs should not render statistics/settings when disabled in options."""
    renderer = DashboardRenderer(hass)
    overview_view = {"path": "overview", "cards": []}
    dog_view = {"path": "fido", "cards": []}

    monkeypatch.setattr(
        renderer,
        "_render_overview_view",
        AsyncMock(return_value=overview_view),
    )
    monkeypatch.setattr(
        renderer,
        "_render_dog_views_batch",
        AsyncMock(return_value=[dog_view]),
    )
    render_statistics_view = AsyncMock(return_value={"path": "statistics", "cards": []})
    render_settings_view = AsyncMock(return_value={"path": "settings", "cards": []})
    monkeypatch.setattr(renderer, "_render_statistics_view", render_statistics_view)
    monkeypatch.setattr(renderer, "_render_settings_view", render_settings_view)

    job = RenderJob(
        "main-disabled-views",
        "main_dashboard",
        {"dogs": [{CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido", "modules": {}}]},
        {"show_statistics": False, "show_settings": False},
    )

    result = await renderer._render_main_dashboard_job(job)

    assert result == {"views": [overview_view, dog_view]}
    render_statistics_view.assert_not_awaited()
    render_settings_view.assert_not_awaited()


def test_renderer_generate_job_id_increments_counter_and_uses_timestamp(hass) -> None:
    """Job IDs should increment monotonically and embed the UTC timestamp."""
    renderer = DashboardRenderer(hass)
    now = datetime(2026, 4, 4, 12, 34, 56, tzinfo=UTC)

    with patch(
        "custom_components.pawcontrol.dashboard_renderer.dt_util.utcnow",
        return_value=now,
    ):
        first_id = renderer._generate_job_id()
        second_id = renderer._generate_job_id()

    assert first_id == "render_1_1775306096"
    assert second_id == "render_2_1775306096"
