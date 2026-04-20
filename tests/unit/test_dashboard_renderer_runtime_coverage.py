"""Runtime-focused coverage tests for ``dashboard_renderer.py``."""

import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import time
from typing import Any

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol.const import (
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
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

    async def get_history_graph_template(
        self,
        entities: list[str],
        title: str,
        hours: int,
    ) -> dict[str, Any]:
        return {
            "type": "history-graph",
            "entities": entities,
            "title": title,
            "hours_to_show": hours,
        }

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
) -> None:
    """Unexpected temp-write failures should bubble as HomeAssistantError."""

    async def _explode_executor_job(func: Any, *args: Any) -> Any:
        if callable(func) and getattr(func, "__name__", "") == "_write_temp_file":
            raise OSError("open failed")
        return func(*args)

    renderer.hass.async_add_executor_job = _explode_executor_job  # type: ignore[assignment]

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


@pytest.mark.asyncio
async def test_runtime_entrypoint_helpers_and_dog_dashboard_branches(
    renderer: dr.DashboardRenderer,
) -> None:
    """Exercise helper coercion and dog dashboard entrypoint paths."""
    options = {"theme": "default"}
    assert dr._as_card_options(options) is options
    assert dr.DashboardRenderer._ensure_dog_config(
        {"dog_id": "rex", "dog_name": "Rex"},
    ) is not None
    assert dr.DashboardRenderer._ensure_dog_config("invalid") is None
    assert dr.DashboardRenderer._ensure_dog_configs("invalid") == []
    assert await renderer.render_main_dashboard("invalid") == {"views": []}

    invalid_result = await renderer.render_dog_dashboard({"dog_name": "Rex"})
    assert invalid_result == {"views": []}

    captured: dict[str, Any] = {}

    async def _capture(job: dr.RenderJob[Any, Any]) -> dict[str, Any]:
        captured["job"] = job
        return {"views": [{"title": "Captured"}]}

    renderer._execute_render_job = _capture  # type: ignore[method-assign]
    valid_result = await renderer.render_dog_dashboard(
        {"dog_id": "rex", "dog_name": "Rex"},
        options,
    )

    assert valid_result["views"][0]["title"] == "Captured"
    assert captured["job"].job_type == "dog_dashboard"
    assert captured["job"].config["dog"]["dog_id"] == "rex"


@pytest.mark.asyncio
async def test_runtime_execute_render_job_main_dog_error_and_timeout_paths(
    renderer: dr.DashboardRenderer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover success, error and timeout branches in render job execution."""

    async def _main_result(job: dr.RenderJob[Any, Any]) -> dict[str, Any]:
        _ = job
        return {"views": [{"title": "Main"}]}

    async def _dog_result(job: dr.RenderJob[Any, Any]) -> dict[str, Any]:
        _ = job
        return {"views": [{"title": "Dog"}]}

    renderer._render_main_dashboard_job = _main_result  # type: ignore[method-assign]
    renderer._render_dog_dashboard_job = _dog_result  # type: ignore[method-assign]

    main_job = dr.RenderJob(
        job_id="main-job",
        job_type="main_dashboard",
        config={"dogs": [{"dog_id": "a", "dog_name": "A"}]},
        options={},
    )
    dog_job = dr.RenderJob(
        job_id="dog-job",
        job_type="dog_dashboard",
        config={"dog": {"dog_id": "a", "dog_name": "A"}},
        options={},
    )

    main_result = await renderer._execute_render_job(main_job)
    dog_result = await renderer._execute_render_job(dog_job)

    assert main_result["views"][0]["title"] == "Main"
    assert dog_result["views"][0]["title"] == "Dog"
    assert main_job.status == "completed"
    assert dog_job.status == "completed"
    assert main_job.job_id not in renderer._active_jobs
    assert dog_job.job_id not in renderer._active_jobs

    unknown_job = dr.RenderJob(
        job_id="unknown-job",
        job_type="main_dashboard",
        config={"dogs": [{"dog_id": "a", "dog_name": "A"}]},
        options={},
    )
    unknown_job.job_type = "unexpected"  # type: ignore[assignment]
    with pytest.raises(HomeAssistantError, match="Dashboard rendering failed"):
        await renderer._execute_render_job(unknown_job)
    assert unknown_job.status == "error"
    assert "Unknown job type" in (unknown_job.error or "")

    class _TimeoutContext:
        async def __aenter__(self) -> None:
            raise TimeoutError("timed out")

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: Any,
        ) -> bool:
            _ = exc_type, exc, tb
            return False

    monkeypatch.setattr(dr.asyncio, "timeout", lambda *_args, **_kwargs: _TimeoutContext())

    timeout_job = dr.RenderJob(
        job_id="timeout-job",
        job_type="main_dashboard",
        config={"dogs": [{"dog_id": "a", "dog_name": "A"}]},
        options={},
    )
    with pytest.raises(HomeAssistantError, match="Dashboard rendering timeout"):
        await renderer._execute_render_job(timeout_job)
    assert timeout_job.status == "timeout"
    assert timeout_job.error == "Rendering timed out"
    assert timeout_job.job_id not in renderer._active_jobs


@pytest.mark.asyncio
async def test_runtime_render_main_and_dog_job_paths_cover_optional_views(
    renderer: dr.DashboardRenderer,
) -> None:
    """Cover dashboard job rendering with and without optional views."""
    empty_main_job = dr.RenderJob(
        job_id="main-empty",
        job_type="main_dashboard",
        config={"dogs": "invalid"},
        options={},
    )
    assert await renderer._render_main_dashboard_job(empty_main_job) == {"views": []}

    async def _overview(
        dogs_config: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        _ = dogs_config, options
        return {"title": "Overview", "path": "overview", "cards": []}

    async def _dog_views(
        dogs_config: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> list[dict[str, Any]]:
        _ = dogs_config, options
        return [{"title": "Dog", "path": "dog", "cards": []}]

    async def _stats(
        dogs_config: list[dict[str, Any]],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        _ = dogs_config, options
        assert kwargs["coordinator_statistics"] == {"updates": 7}
        assert kwargs["service_execution_metrics"] == {"rejected_call_count": 1}
        assert kwargs["service_guard_metrics"] == {"executed": 2, "skipped": 1}
        return {"title": "Statistics", "path": "statistics", "cards": []}

    async def _settings(
        dogs_config: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        _ = dogs_config, options
        return {"title": "Settings", "path": "settings", "cards": []}

    renderer._render_overview_view = _overview  # type: ignore[method-assign]
    renderer._render_dog_views_batch = _dog_views  # type: ignore[method-assign]
    renderer._render_statistics_view = _stats  # type: ignore[method-assign]
    renderer._render_settings_view = _settings  # type: ignore[method-assign]

    full_job = dr.RenderJob(
        job_id="main-full",
        job_type="main_dashboard",
        config={
            "dogs": [{"dog_id": "rex", "dog_name": "Rex"}],
            "coordinator_statistics": {"updates": 7},
            "service_execution_metrics": {"rejected_call_count": 1},
            "service_guard_metrics": {"executed": 2, "skipped": 1},
        },
        options={"show_statistics": True, "show_settings": True},
    )
    full_result = await renderer._render_main_dashboard_job(full_job)
    assert [view["title"] for view in full_result["views"]] == [
        "Overview",
        "Dog",
        "Statistics",
        "Settings",
    ]

    trimmed_job = dr.RenderJob(
        job_id="main-trimmed",
        job_type="main_dashboard",
        config={"dogs": [{"dog_id": "rex", "dog_name": "Rex"}]},
        options={"show_statistics": False, "show_settings": False},
    )
    trimmed_result = await renderer._render_main_dashboard_job(trimmed_job)
    assert [view["title"] for view in trimmed_result["views"]] == ["Overview", "Dog"]

    empty_dog_job = dr.RenderJob(
        job_id="dog-empty",
        job_type="dog_dashboard",
        config={"dog": "invalid"},
        options={},
    )
    assert await renderer._render_dog_dashboard_job(empty_dog_job) == {"views": []}

    async def _dog_overview(
        dog_config: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        _ = dog_config, options
        return {"title": "Overview", "path": "overview", "cards": []}

    async def _module_views(
        dog_config: dict[str, Any],
        options: dict[str, Any],
    ) -> list[dict[str, Any]]:
        _ = dog_config, options
        return [{"title": "Health", "path": "health", "cards": []}]

    renderer._render_dog_overview_view = _dog_overview  # type: ignore[method-assign]
    renderer._render_module_views = _module_views  # type: ignore[method-assign]

    full_dog_job = dr.RenderJob(
        job_id="dog-full",
        job_type="dog_dashboard",
        config={"dog": {"dog_id": "rex", "dog_name": "Rex"}},
        options={},
    )
    full_dog_result = await renderer._render_dog_dashboard_job(full_dog_job)
    assert [view["title"] for view in full_dog_result["views"]] == ["Overview", "Health"]


@pytest.mark.asyncio
async def test_runtime_overview_activity_and_dog_batch_paths(
    renderer: dr.DashboardRenderer,
) -> None:
    """Cover overview generation, activity summary, and batched dog views."""
    captured_navigation_urls: list[str] = []

    async def _welcome(
        dogs_config: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        _ = dogs_config, options
        return {"type": "welcome"}

    async def _grid(
        dogs_config: list[dict[str, Any]],
        navigation_url: str,
    ) -> dict[str, Any]:
        _ = dogs_config
        captured_navigation_urls.append(navigation_url)
        return {"type": "grid"}

    async def _quick_actions(
        dogs_config: list[dict[str, Any]],
    ) -> dict[str, Any]:
        _ = dogs_config
        raise RuntimeError("quick actions failed")

    async def _summary(
        dogs_config: list[dict[str, Any]],
    ) -> dict[str, Any]:
        _ = dogs_config
        return {"type": "summary"}

    renderer.overview_generator = SimpleNamespace(
        generate_welcome_card=_welcome,
        generate_dogs_grid=_grid,
        generate_quick_actions=_quick_actions,
    )
    renderer._render_activity_summary = _summary  # type: ignore[method-assign]

    first_view = await renderer._render_overview_view(
        [{"dog_id": "rex", "dog_name": "Rex"}],
        {"dashboard_url": "/paw", "show_activity_summary": True},
    )
    assert captured_navigation_urls[0] == "/paw"
    assert [card["type"] for card in first_view["cards"]] == ["welcome", "grid", "summary"]

    async def _quick_actions_ok(
        dogs_config: list[dict[str, Any]],
    ) -> dict[str, Any]:
        _ = dogs_config
        return {"type": "quick_actions"}

    renderer.overview_generator = SimpleNamespace(
        generate_welcome_card=_welcome,
        generate_dogs_grid=_grid,
        generate_quick_actions=_quick_actions_ok,
    )
    second_view = await renderer._render_overview_view(
        [{"dog_id": "rex", "dog_name": "Rex"}],
        {"dashboard_url": 42, "show_activity_summary": False},
    )
    assert captured_navigation_urls[1] == "/paw-control"
    assert [card["type"] for card in second_view["cards"]] == [
        "welcome",
        "grid",
        "quick_actions",
    ]

    class _SelectiveStates:
        @staticmethod
        def get(entity_id: str) -> object | None:
            if entity_id == "sensor.rex_activity_level":
                return object()
            return None

    renderer.hass.states = _SelectiveStates()
    summary_card = await dr.DashboardRenderer._render_activity_summary(
        renderer,
        [
            {"dog_name": "Missing ID"},
            {"dog_id": "rex", "dog_name": "Rex"},
            {"dog_id": "ghost", "dog_name": "Ghost"},
        ],
    )
    assert summary_card is not None
    assert summary_card["entities"] == ["sensor.rex_activity_level"]

    renderer.hass.states = SimpleNamespace(get=lambda _entity: None)
    assert (
        await dr.DashboardRenderer._render_activity_summary(
            renderer,
            [{"dog_id": "none"}],
        )
        is None
    )

    assert await renderer._render_dog_views_batch([], {}) == []

    async def _single_dog_view(
        dog_config: dict[str, Any],
        index: int,
        options: dict[str, Any],
    ) -> dict[str, Any] | None:
        _ = index, options
        if dog_config.get("dog_id") == "ok":
            return {
                "title": "OK",
                "path": "ok",
                "icon": "mdi:dog",
                "theme": "default",
                "cards": [],
            }
        if dog_config.get("dog_id") == "skip":
            return None
        raise RuntimeError("dog view failure")

    renderer._render_single_dog_view = _single_dog_view  # type: ignore[method-assign]
    batch_views = await renderer._render_dog_views_batch(
        [
            {"dog_name": "Name Only"},
            {"dog_id": "id-only"},
            {},
            {"dog_id": "skip", "dog_name": "Skip"},
            {"dog_id": "ok", "dog_name": "OK"},
        ],
        {},
    )
    assert len(batch_views) == 1
    assert batch_views[0]["title"] == "OK"


@pytest.mark.asyncio
async def test_runtime_single_dog_module_statistics_settings_cleanup_and_stats(
    renderer: dr.DashboardRenderer,
) -> None:
    """Cover remaining single-dog, module, statistics, settings, and cleanup paths."""
    assert await renderer._render_single_dog_view({"dog_name": "No ID"}, 0, {}) is None
    valid_dog_view = await renderer._render_single_dog_view(
        {"dog_id": "Rex Alpha", "dog_name": "Rex Alpha"},
        7,
        {"theme": "night"},
    )
    assert valid_dog_view is not None
    assert valid_dog_view["path"] == "rex_alpha"
    assert valid_dog_view["theme"] == "night"

    assert renderer._get_dog_theme(0) == {"primary": "#4CAF50", "accent": "#8BC34A"}
    assert renderer._get_dog_theme(8) == renderer._get_dog_theme(2)

    dog_overview = await renderer._render_dog_overview_view(
        {"dog_id": "rex", "dog_name": "Rex"},
        {},
    )
    assert dog_overview["title"] == "Overview"
    assert dog_overview["icon"] == "mdi:dog"

    async def _cards_ok(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        _ = args, kwargs
        return [{"type": "entities"}]

    async def _cards_empty(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        _ = args, kwargs
        return []

    async def _cards_error(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        _ = args, kwargs
        raise RuntimeError("broken cards")

    ok_module_view = await renderer._render_module_view(
        {"dog_id": "rex", "dog_name": "Rex"},
        {},
        MODULE_GPS,
        "Location",
        "mdi:map-marker",
        _cards_ok,
    )
    assert ok_module_view is not None
    assert ok_module_view["path"] == MODULE_GPS

    assert (
        await renderer._render_module_view(
            {"dog_id": "rex", "dog_name": "Rex"},
            {},
            MODULE_GPS,
            "Location",
            "mdi:map-marker",
            _cards_empty,
        )
        is None
    )
    assert (
        await renderer._render_module_view(
            {"dog_id": "rex", "dog_name": "Rex"},
            {},
            MODULE_GPS,
            "Location",
            "mdi:map-marker",
            _cards_error,
        )
        is None
    )

    async def _module_view_runtime(
        dog_config: dict[str, Any],
        options: dict[str, Any],
        module_key: str,
        title: str,
        icon: str,
        generator: Any,
    ) -> dict[str, Any] | None:
        _ = dog_config, options, title, icon, generator
        if module_key == MODULE_FEEDING:
            return {"title": "Feeding", "path": MODULE_FEEDING, "icon": "mdi:food", "cards": []}
        if module_key == MODULE_WALK:
            raise RuntimeError("walk failed")
        return None

    renderer._render_module_view = _module_view_runtime  # type: ignore[method-assign]
    module_views = await renderer._render_module_views(
        {
            "dog_id": "rex",
            "dog_name": "Rex",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: False,
            },
        },
        {},
    )
    assert len(module_views) == 1
    assert module_views[0]["path"] == MODULE_FEEDING

    captured_statistics: dict[str, Any] = {}

    async def _capture_statistics_cards(
        dogs_config: list[dict[str, Any]],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        _ = dogs_config, options
        captured_statistics.update(kwargs)
        return [{"type": "statistics"}]

    renderer.stats_generator.generate_statistics_cards = (  # type: ignore[method-assign]
        _capture_statistics_cards
    )
    stats_view = await renderer._render_statistics_view(
        [{"dog_id": "rex", "dog_name": "Rex"}],
        {"show_statistics": True},
        coordinator_statistics={"updates": 2},
        service_execution_metrics={"rejected_call_count": 3},
        service_guard_metrics={"executed": 4, "skipped": 1},
    )
    assert stats_view["title"] == "Statistics"
    assert captured_statistics["coordinator_statistics"] == {"updates": 2}
    assert captured_statistics["service_execution_metrics"] == {"rejected_call_count": 3}
    assert captured_statistics["service_guard_metrics"] == {"executed": 4, "skipped": 1}

    settings_view = await renderer._render_settings_view(
        [
            {"dog_name": "Missing ID"},
            {
                "dog_id": "rex",
                "dog_name": "Rex",
                "modules": {
                    MODULE_GPS: False,
                    MODULE_VISITOR: False,
                    MODULE_NOTIFICATIONS: True,
                },
            },
        ],
        {},
    )
    assert len(settings_view["cards"]) == 2
    rex_entities = settings_view["cards"][1]["entities"]
    assert "switch.rex_notifications_enabled" in rex_entities
    assert "switch.rex_gps_tracking_enabled" not in rex_entities
    assert "switch.rex_visitor_mode" not in rex_entities
    assert "select.rex_notification_priority" in rex_entities

    job_a = SimpleNamespace(status="running")
    job_b = SimpleNamespace(status="running")
    renderer._active_jobs = {"a": job_a, "b": job_b}
    renderer._job_counter = 11
    await renderer.cleanup()
    assert job_a.status == "cancelled"
    assert job_b.status == "cancelled"
    assert renderer._active_jobs == {}
    assert renderer.templates._cleaned is True  # type: ignore[attr-defined]

    stats = renderer.get_render_stats()
    assert stats["active_jobs"] == 0
    assert stats["total_jobs_processed"] == 11
    assert stats["template_cache"] == {"hits": 0, "misses": 0}
