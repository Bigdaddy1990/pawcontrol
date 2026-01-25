"""Unit tests for the dashboard generator metadata exports."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Sequence
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

  summaries = PawControlDashboardGenerator._summarise_dashboard_views(dashboard_config)

  assert any(summary["path"] == "overview" for summary in summaries)

  notifications_summary = next(
    summary for summary in summaries if summary["path"] == MODULE_NOTIFICATIONS
  )

  assert notifications_summary["card_count"] == 2
  assert notifications_summary.get("module") == MODULE_NOTIFICATIONS
  assert notifications_summary.get("notifications") is True


def test_normalise_dashboard_registry_filters_invalid_entries() -> None:
  """Stored dashboard registry payloads should be normalised to plain dicts."""

  stored_dashboard = MappingProxyType(
    {
      "url": "dashboard-1",
      "title": "Primary dashboard",
      "path": "/config/.storage/lovelace.dashboard-1",
      "options": {"theme": "modern", "layout": "full"},
      "updated": "2024-04-02T12:34:56+00:00",
    }
  )

  registry = PawControlDashboardGenerator._normalise_dashboard_registry(
    {
      "dashboard-1": stored_dashboard,
      "skipped": "not a mapping",
      42: {"url": "wrong-key"},
    }
  )

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

  metrics = PawControlDashboardGenerator._coerce_performance_metrics(
    {
      "total_generations": "5",
      "avg_generation_time": "2.5",
      "cache_hits": True,
      "cache_misses": 3.9,
      "file_operations": "7",
      "errors": "0",
    }
  )

  assert metrics == {
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
def test_resolve_service_execution_metrics_uses_runtime_data(
  mock_store: MagicMock, hass, mock_config_entry, monkeypatch: pytest.MonkeyPatch
) -> None:
  """Service execution metrics should reuse runtime performance stats."""

  mock_store.return_value = MagicMock()
  generator = PawControlDashboardGenerator(hass, mock_config_entry)

  service_metrics = default_rejection_metrics()
  service_metrics.update(
    {
      "rejected_call_count": 4,
      "rejection_breaker_count": 1,
      "last_rejection_time": 42.0,
      "last_rejection_breaker_id": "automation",
    }
  )

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
