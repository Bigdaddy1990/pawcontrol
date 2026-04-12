"""Runtime-focused coverage tests for ``dashboard_renderer.py``."""

import asyncio
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol.const import (
    MODULE_GPS,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
)
import custom_components.pawcontrol.dashboard_renderer as dr

pytestmark = pytest.mark.unit


def _local_workspace_tmp_dir() -> Path:
    """Create and return an isolated workspace-local temporary directory."""
    root = Path("dashboard_runtime_tmp").resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = root / f"dashboard-renderer-{time.time_ns()}"
    directory.mkdir(parents=True, exist_ok=False)
    return directory


@pytest.fixture
def local_tmp_dir() -> Path:
    """Yield and clean up a workspace-local temporary directory."""
    directory = _local_workspace_tmp_dir()
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


class _DummyTemplates:
    """Template double exposing the API expected by ``DashboardRenderer``."""

    def __init__(self, hass: Any) -> None:
        _ = hass
        self._cleaned = False

    async def cleanup(self) -> None:
        self._cleaned = True

    def get_cache_stats(self) -> dict[str, int]:
        return {"hits": 0, "misses": 0}


class _DummyOverviewGenerator:
    """Overview generator double used by renderer initialization."""

    def __init__(self, hass: Any, templates: Any) -> None:
        _ = hass, templates

    async def generate_welcome_card(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = args, kwargs
        return {"type": "markdown"}

    async def generate_dogs_grid(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = args, kwargs
        return {"type": "grid"}

    async def generate_quick_actions(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = args, kwargs
        return {"type": "buttons"}


class _DummyDogGenerator:
    """Dog generator double used by renderer initialization."""

    def __init__(self, hass: Any, templates: Any) -> None:
        _ = hass, templates

    async def generate_dog_overview_cards(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        _ = args, kwargs
        return [{"type": "entities"}]


class _DummyModuleGenerator:
    """Module generator double with deterministic card payloads."""

    def __init__(self, hass: Any, templates: Any) -> None:
        _ = hass, templates

    async def generate_feeding_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        _ = args, kwargs
        return [{"type": "feeding"}]

    async def generate_walk_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        _ = args, kwargs
        return [{"type": "walk"}]

    async def generate_health_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        _ = args, kwargs
        return [{"type": "health"}]

    async def generate_notification_cards(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        _ = args, kwargs
        return [{"type": "notifications"}]

    async def generate_gps_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        _ = args, kwargs
        return [{"type": "gps"}]

    async def generate_visitor_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        _ = args, kwargs
        return [{"type": "visitor"}]


class _DummyStatisticsGenerator:
    """Statistics generator double used by renderer initialization."""

    def __init__(self, hass: Any, templates: Any) -> None:
        _ = hass, templates

    async def generate_statistics_cards(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        _ = args, kwargs
        return [{"type": "statistics"}]


class _DummyStates:
    """State-machine double supporting activity entity lookups."""

    @staticmethod
    def get(entity_id: str) -> object | None:
        if entity_id.endswith("_activity_level"):
            return object()
        return None


class _DummyHass:
    """Minimal hass double with executor scheduling support."""

    def __init__(self) -> None:
        self.states = _DummyStates()

    async def async_add_executor_job(self, func: Any, *args: Any) -> Any:
        return func(*args)


@pytest.fixture
def renderer(monkeypatch: pytest.MonkeyPatch) -> dr.DashboardRenderer:
    """Construct a renderer with lightweight test doubles."""
    monkeypatch.setattr(dr, "DashboardTemplates", _DummyTemplates)
    monkeypatch.setattr(dr, "OverviewCardGenerator", _DummyOverviewGenerator)
    monkeypatch.setattr(dr, "DogCardGenerator", _DummyDogGenerator)
    monkeypatch.setattr(dr, "ModuleCardGenerator", _DummyModuleGenerator)
    monkeypatch.setattr(dr, "StatisticsCardGenerator", _DummyStatisticsGenerator)
    return dr.DashboardRenderer(_DummyHass())


@pytest.mark.asyncio
async def test_runtime_main_job_config_optional_metrics_branches(
    renderer: dr.DashboardRenderer,
) -> None:
    """Main render should include optional metrics only when values are provided."""
    captured: dict[str, Any] = {}

    async def _capture(job: dr.RenderJob[Any, Any]) -> dict[str, Any]:
        captured["config"] = dict(job.config)
        return {"views": []}

    renderer._execute_render_job = _capture  # type: ignore[method-assign]

    await renderer.render_main_dashboard([{"dog_id": "a", "dog_name": "A"}], {})
    config_without_metrics = captured["config"]
    assert "coordinator_statistics" not in config_without_metrics
    assert "service_execution_metrics" not in config_without_metrics
    assert "service_guard_metrics" not in config_without_metrics

    await renderer.render_main_dashboard(
        [{"dog_id": "b", "dog_name": "B"}],
        {},
        coordinator_statistics={"updates": 1},
        service_execution_metrics={"rejected_call_count": 2},
        service_guard_metrics={"executed": 3, "skipped": 0},
    )
    config_with_metrics = captured["config"]
    assert config_with_metrics["coordinator_statistics"] == {"updates": 1}
    assert config_with_metrics["service_execution_metrics"] == {
        "rejected_call_count": 2,
    }
    assert config_with_metrics["service_guard_metrics"] == {"executed": 3, "skipped": 0}


@pytest.mark.asyncio
async def test_runtime_module_and_settings_views_cover_false_branches(
    renderer: dr.DashboardRenderer,
) -> None:
    """Module/settings rendering should handle empty modules and disabled alerts."""
    empty_module_views = await renderer._render_module_views(
        {"dog_id": "buddy", "dog_name": "Buddy", "modules": {}},
        {},
    )
    assert empty_module_views == []

    settings_view = await renderer._render_settings_view(
        [
            {
                "dog_id": "buddy",
                "dog_name": "Buddy",
                "modules": {
                    MODULE_GPS: True,
                    MODULE_VISITOR: True,
                    MODULE_NOTIFICATIONS: False,
                },
            },
        ],
        {},
    )
    buddy_card = settings_view["cards"][1]
    assert "switch.buddy_gps_tracking_enabled" in buddy_card["entities"]
    assert "switch.buddy_visitor_mode" in buddy_card["entities"]
    assert "select.buddy_notification_priority" not in buddy_card["entities"]


@pytest.mark.asyncio
async def test_runtime_write_dashboard_file_success_and_failure_paths(
    renderer: dr.DashboardRenderer,
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File writing should clean up correctly when replace fails."""
    output = local_tmp_dir / "dashboards" / "buddy.json"
    original_replace = dr.os.replace

    async def _executor_with_safe_replace(func: Any, *args: Any) -> Any:
        if func is original_replace:
            src = Path(args[0])
            dst = Path(args[1])
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            return None
        if callable(func):
            try:
                return func(*args)
            except PermissionError:
                return None
        return None

    renderer.hass.async_add_executor_job = _executor_with_safe_replace  # type: ignore[assignment]

    await renderer.write_dashboard_file(
        {"views": [{"title": "Overview"}]},
        output,
        metadata=None,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["data"]["config"]["views"][0]["title"] == "Overview"
    assert payload["minor_version"] == 1

    await renderer.write_dashboard_file(
        {"views": [{"title": "With Metadata"}]},
        local_tmp_dir / "dashboards" / "with-metadata.json",
        metadata={"owner": "coverage"},
    )
    metadata_payload = json.loads(
        (local_tmp_dir / "dashboards" / "with-metadata.json").read_text(
            encoding="utf-8",
        ),
    )
    assert metadata_payload["data"]["owner"] == "coverage"

    created_temp_paths: list[Path] = []

    def _failing_replace(
        src: os.PathLike[str] | str, dst: os.PathLike[str] | str
    ) -> None:
        created_temp_paths.append(Path(src))
        _ = dst
        raise OSError("replace failed")

    monkeypatch.setattr(dr.os, "replace", _failing_replace)

    with pytest.raises(HomeAssistantError, match="Dashboard file write failed"):
        await renderer.write_dashboard_file(
            {"views": []},
            local_tmp_dir / "dashboards" / "fail.json",
        )

    assert created_temp_paths


@pytest.mark.asyncio
async def test_runtime_write_dashboard_file_handles_aiofiles_failure(
    renderer: dr.DashboardRenderer,
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected file open failures should bubble as HomeAssistantError."""

    async def _explode_executor_job(func: Any, *args: Any) -> Any:
        if callable(func) and getattr(func, "__name__", "") == "_create_temp_path":
            return Path(local_tmp_dir / "temp-write-error.json")
        return func(*args)

    renderer.hass.async_add_executor_job = _explode_executor_job  # type: ignore[assignment]

    class _BadAsyncOpen:
        async def __aenter__(self) -> Any:
            raise OSError("open failed")

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            _ = exc_type, exc, tb
            return False

    monkeypatch.setattr(dr.aiofiles, "open", lambda *args, **kwargs: _BadAsyncOpen())

    with pytest.raises(HomeAssistantError, match="Dashboard file write failed"):
        await renderer.write_dashboard_file(
            {"views": []},
            local_tmp_dir / "dashboards" / "open-fail.json",
        )


@pytest.mark.asyncio
async def test_runtime_write_dashboard_file_early_failure_without_temp_cleanup(
    renderer: dr.DashboardRenderer,
    local_tmp_dir: Path,
) -> None:
    """Early executor failures should raise HA error before temp path creation."""

    async def _explode_before_temp_path(func: Any, *args: Any) -> Any:
        if callable(func):
            raise OSError("mkdir failed")
        _ = args
        return None

    renderer.hass.async_add_executor_job = _explode_before_temp_path  # type: ignore[assignment]

    with pytest.raises(HomeAssistantError, match="Dashboard file write failed"):
        await renderer.write_dashboard_file(
            {"views": []},
            local_tmp_dir / "dashboards" / "early-fail.json",
            metadata={"source": "test"},
        )
