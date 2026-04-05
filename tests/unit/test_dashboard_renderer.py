"""Unit tests for dashboard renderer helper behavior."""

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
