"""Unit tests for dashboard renderer helper behavior."""

import os
from types import SimpleNamespace
from typing import Any

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol.const import (
    MODULE_GPS,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
)
import custom_components.pawcontrol.dashboard_renderer as dashboard_renderer


class _DummyTemplates:
    def __init__(self, hass: Any) -> None:
        self._hass = hass
        self.cleaned = False

    async def get_history_graph_template(
        self,
        entities: list[str],
        title: str,
        hours: int,
    ) -> dict[str, object]:
        return {
            "type": "history-graph",
            "entities": entities,
            "title": title,
            "hours_to_show": hours,
        }

    async def cleanup(self) -> None:
        self.cleaned = True

    def get_cache_stats(self) -> dict[str, int]:
        return {"hits": 0, "misses": 0}


class _DummyOverviewGenerator:
    def __init__(self, hass: Any, templates: _DummyTemplates) -> None:
        self._hass = hass
        self._templates = templates

    async def generate_welcome_card(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        return {"type": "markdown", "content": "Welcome"}

    async def generate_dogs_grid(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        return {"type": "grid"}

    async def generate_quick_actions(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        return {"type": "buttons"}


class _DummyDogGenerator:
    def __init__(self, hass: Any, templates: _DummyTemplates) -> None:
        self._hass = hass
        self._templates = templates

    async def generate_dog_overview_cards(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, str]]:
        return [{"type": "entities"}]


class _DummyModuleGenerator:
    def __init__(self, hass: Any, templates: _DummyTemplates) -> None:
        self._hass = hass
        self._templates = templates

    async def generate_feeding_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, str]]:
        return [{"type": "feeding"}]

    async def generate_walk_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, str]]:
        return []

    async def generate_health_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, str]]:
        return []

    async def generate_notification_cards(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, str]]:
        return [{"type": "notifications"}]

    async def generate_gps_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, str]]:
        return [{"type": "gps"}]

    async def generate_visitor_cards(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, str]]:
        return [{"type": "visitor"}]


class _DummyStatisticsGenerator:
    def __init__(self, hass: Any, templates: _DummyTemplates) -> None:
        self._hass = hass
        self._templates = templates

    async def generate_statistics_cards(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, str]]:
        return [{"type": "statistics"}]


@pytest.fixture
def renderer(monkeypatch: pytest.MonkeyPatch) -> dashboard_renderer.DashboardRenderer:
    """Build renderer with lightweight async test doubles."""

    class _DummyStates:
        def get(self, entity_id: str) -> object | None:
            return object() if entity_id.endswith("_activity_level") else None

    class _DummyHass:
        def __init__(self) -> None:
            self.states = _DummyStates()

        async def async_add_executor_job(self, func: Any, *args: Any) -> Any:
            return func(*args)

    monkeypatch.setattr(dashboard_renderer, "DashboardTemplates", _DummyTemplates)
    monkeypatch.setattr(
        dashboard_renderer, "OverviewCardGenerator", _DummyOverviewGenerator
    )
    monkeypatch.setattr(dashboard_renderer, "DogCardGenerator", _DummyDogGenerator)
    monkeypatch.setattr(
        dashboard_renderer, "ModuleCardGenerator", _DummyModuleGenerator
    )
    monkeypatch.setattr(
        dashboard_renderer,
        "StatisticsCardGenerator",
        _DummyStatisticsGenerator,
    )

    return dashboard_renderer.DashboardRenderer(_DummyHass())


@pytest.mark.asyncio
@pytest.mark.unit
async def test_render_dog_dashboard_returns_empty_for_invalid_payload(
    renderer: dashboard_renderer.DashboardRenderer,
) -> None:
    """Invalid dog payloads should be rejected without executing a job."""
    result = await renderer.render_dog_dashboard({"dog_name": "Only name"})

    assert result == {"views": []}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_render_settings_view_adds_module_specific_controls(
    renderer: dashboard_renderer.DashboardRenderer,
) -> None:
    """Settings view should include per-module entities when modules are enabled."""
    settings_view = await renderer._render_settings_view(
        [
            {
                "dog_id": "buddy",
                "dog_name": "Buddy",
                "modules": {
                    MODULE_GPS: True,
                    MODULE_VISITOR: True,
                    MODULE_NOTIFICATIONS: True,
                },
            },
        ],
        {},
    )

    buddy_card = settings_view["cards"][1]
    assert buddy_card["title"] == "Buddy Settings"
    assert "switch.buddy_gps_tracking_enabled" in buddy_card["entities"]
    assert "switch.buddy_visitor_mode" in buddy_card["entities"]
    assert "select.buddy_notification_priority" in buddy_card["entities"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execute_render_job_unknown_type_marks_error_and_clears_job(
    renderer: dashboard_renderer.DashboardRenderer,
) -> None:
    """Unknown job types should be wrapped as HomeAssistantError and cleaned up."""
    job = dashboard_renderer.RenderJob(
        job_id="job-unknown",
        job_type="main_dashboard",
        config={"dogs": [{"dog_id": "rex", "dog_name": "Rex"}]},
    )
    job.job_type = "unexpected"  # type: ignore[assignment]

    with pytest.raises(HomeAssistantError):
        await renderer._execute_render_job(job)

    assert job.status == "error"
    assert "Unknown job type" in (job.error or "")
    assert "job-unknown" not in renderer._active_jobs


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_marks_jobs_cancelled_and_reports_stats(
    renderer: dashboard_renderer.DashboardRenderer,
) -> None:
    """Cleanup should cancel active jobs and keep processed counter in stats."""
    renderer._active_jobs["job-a"] = SimpleNamespace(status="running")
    renderer._active_jobs["job-b"] = SimpleNamespace(status="running")
    renderer._job_counter = 4

    await renderer.cleanup()

    assert renderer._active_jobs == {}
    stats = renderer.get_render_stats()
    assert stats["active_jobs"] == 0
    assert stats["total_jobs_processed"] == 4
    assert stats["template_cache"] == {"hits": 0, "misses": 0}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_render_main_dashboard_returns_empty_when_dogs_config_invalid(
    renderer: dashboard_renderer.DashboardRenderer,
) -> None:
    """Main dashboard render should short-circuit when no valid dogs are provided."""
    result = await renderer.render_main_dashboard("invalid")

    assert result == {"views": []}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_render_module_view_returns_none_when_generator_raises(
    renderer: dashboard_renderer.DashboardRenderer,
) -> None:
    """Module view rendering should swallow generator exceptions."""

    async def _failing_generator(*args: Any, **kwargs: Any) -> list[dict[str, str]]:
        raise RuntimeError("broken cards")

    view = await renderer._render_module_view(
        {"dog_id": "buddy", "dog_name": "Buddy"},
        {},
        MODULE_GPS,
        "Location",
        "mdi:map-marker",
        _failing_generator,
    )

    assert view is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_write_dashboard_file_writes_metadata_payload(
    renderer: dashboard_renderer.DashboardRenderer,
    tmp_path: Any,
) -> None:
    """Dashboard writes should include metadata and preserve unicode content."""
    output = tmp_path / "dashboards" / "buddy.json"
    metadata = {"owner": "Jürgen"}

    await renderer.write_dashboard_file(
        {"views": [{"title": "Übersicht"}]},
        output,
        metadata=metadata,
    )

    assert output.exists()
    payload = output.read_text(encoding="utf-8")
    assert "Jürgen" in payload
    assert "Übersicht" in payload


@pytest.mark.asyncio
@pytest.mark.unit
async def test_write_dashboard_file_cleans_temp_file_when_replace_fails(
    renderer: dashboard_renderer.DashboardRenderer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Failed file replacement should remove temporary file and raise HA error."""
    output = tmp_path / "dashboard.json"
    created_temp_paths: list[os.PathLike[str] | str] = []
    original_replace = dashboard_renderer.os.replace

    def _tracking_replace(
        src: os.PathLike[str] | str,
        dst: os.PathLike[str] | str,
    ) -> None:
        created_temp_paths.append(src)
        raise OSError("replace failed")

    monkeypatch.setattr(dashboard_renderer.os, "replace", _tracking_replace)

    with pytest.raises(HomeAssistantError, match="Dashboard file write failed"):
        await renderer.write_dashboard_file({"views": []}, output)

    for path in created_temp_paths:
        if os.path.exists(path):
            # Some Windows sandbox setups allow file creation but deny delete rights
            # in the temp directory; in that case verify cleanup failed due ACLs.
            with pytest.raises(PermissionError):
                os.unlink(path)

    monkeypatch.setattr(dashboard_renderer.os, "replace", original_replace)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_write_dashboard_file_replace_success_path_is_covered(
    renderer: dashboard_renderer.DashboardRenderer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Successful replace should take the fast return path in retry helper."""
    output = tmp_path / "dashboards" / "success.json"
    replace_calls: list[tuple[os.PathLike[str] | str, os.PathLike[str] | str]] = []

    def _successful_replace(
        src: os.PathLike[str] | str,
        dst: os.PathLike[str] | str,
    ) -> None:
        replace_calls.append((src, dst))
        source = dashboard_renderer.Path(src)
        destination = dashboard_renderer.Path(dst)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        source.unlink(missing_ok=True)

    monkeypatch.setattr(dashboard_renderer.os, "replace", _successful_replace)

    await renderer.write_dashboard_file({"views": []}, output)

    assert replace_calls
    assert output.exists()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_write_dashboard_file_cleanup_reaches_final_exists_check(
    renderer: dashboard_renderer.DashboardRenderer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Cleanup should tolerate repeated unlink failures and use final exists check."""
    output = tmp_path / "dashboards" / "cleanup-final-check.json"
    temp_exists_checks = 0
    original_exists = dashboard_renderer.Path.exists
    original_unlink = dashboard_renderer.Path.unlink

    def _failing_replace(
        src: os.PathLike[str] | str,
        dst: os.PathLike[str] | str,
    ) -> None:
        _ = src
        _ = dst
        raise OSError("replace failed")

    def _patched_exists(path: dashboard_renderer.Path) -> bool:
        nonlocal temp_exists_checks
        if str(path).endswith(".tmp"):
            temp_exists_checks += 1
            return temp_exists_checks <= 20
        return original_exists(path)

    def _patched_unlink(
        path: dashboard_renderer.Path, *args: Any, **kwargs: Any
    ) -> None:
        if str(path).endswith(".tmp"):
            return None
        original_unlink(path, *args, **kwargs)
        return None

    monkeypatch.setattr(dashboard_renderer.os, "replace", _failing_replace)
    monkeypatch.setattr(dashboard_renderer.Path, "exists", _patched_exists)
    monkeypatch.setattr(dashboard_renderer.Path, "unlink", _patched_unlink)
    monkeypatch.setattr(dashboard_renderer.time, "sleep", lambda _seconds: None)

    with pytest.raises(HomeAssistantError, match="Dashboard file write failed"):
        await renderer.write_dashboard_file({"views": []}, output)

    assert temp_exists_checks >= 21
