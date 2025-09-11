"""Comprehensive tests for dashboard renderer async operations.

Tests dashboard rendering engine performance, job processing, error handling,
and memory management under various load conditions.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.pawcontrol.dashboard_renderer import DashboardRenderer
from custom_components.pawcontrol.dashboard_renderer import RenderJob


@pytest.fixture
def mock_hass_renderer() -> HomeAssistant:
    """Mock Home Assistant for renderer testing."""
    hass = Mock(spec=HomeAssistant)
    hass.states.get = Mock(return_value=Mock(state="active"))
    return hass


@pytest.fixture
async def dashboard_renderer(mock_hass_renderer: HomeAssistant) -> DashboardRenderer:
    """Create dashboard renderer with mocked dependencies."""
    renderer = DashboardRenderer(mock_hass_renderer)

    # Mock card generators
    renderer.overview_generator.generate_welcome_card = AsyncMock(
        return_value={"type": "markdown", "content": "Welcome"}
    )
    renderer.overview_generator.generate_dogs_grid = AsyncMock(
        return_value={"type": "grid", "cards": []}
    )
    renderer.overview_generator.generate_quick_actions = AsyncMock(
        return_value={"type": "horizontal-stack", "cards": []}
    )
    renderer.dog_generator.generate_dog_overview_cards = AsyncMock(
        return_value=[{"type": "entities", "title": "Status"}]
    )
    renderer.module_generator.generate_feeding_cards = AsyncMock(
        return_value=[{"type": "entities", "title": "Feeding"}]
    )
    renderer.stats_generator.generate_statistics_cards = AsyncMock(
        return_value=[{"type": "markdown", "content": "Stats"}]
    )

    return renderer


class TestRenderJob:
    """Test render job management."""

    def test_render_job_creation(self):
        """Test render job initialization."""
        job = RenderJob(
            job_id="test_001",
            job_type="main_dashboard",
            config={"dogs": []},
            options={"theme": "dark"},
        )

        assert job.job_id == "test_001"
        assert job.job_type == "main_dashboard"
        assert job.status == "pending"
        assert job.result is None
        assert job.error is None
        assert job.options["theme"] == "dark"

    def test_render_job_defaults(self):
        """Test render job with default options."""
        job = RenderJob(
            job_id="test_002",
            job_type="dog_dashboard",
            config={"dog": {"dog_id": "test"}},
        )

        assert job.options == {}
        assert job.config["dog"]["dog_id"] == "test"


class TestDashboardRendererCore:
    """Test core dashboard renderer functionality."""

    async def test_main_dashboard_rendering(
        self, dashboard_renderer: DashboardRenderer
    ):
        """Test main dashboard rendering with multiple dogs."""
        dogs_config = [
            {"dog_id": "max", "dog_name": "Max", "modules": {"feeding": True}},
            {"dog_id": "bella", "dog_name": "Bella", "modules": {"walk": True}},
        ]

        result = await dashboard_renderer.render_main_dashboard(dogs_config)

        assert "views" in result
        assert len(result["views"]) >= 3  # Overview + 2 dogs + stats/settings

        # Check overview view
        overview_view = next(
            view for view in result["views"] if view["title"] == "Overview"
        )
        assert overview_view["path"] == "overview"
        assert len(overview_view["cards"]) >= 3  # Welcome + grid + actions

    async def test_dog_dashboard_rendering(self, dashboard_renderer: DashboardRenderer):
        """Test individual dog dashboard rendering."""
        dog_config = {
            "dog_id": "max_shepherd",
            "dog_name": "Max",
            "modules": {"feeding": True, "health": True, "walk": True},
        }

        result = await dashboard_renderer.render_dog_dashboard(dog_config)

        assert "views" in result
        assert len(result["views"]) >= 4  # Overview + 3 modules

        # Check overview view exists
        overview_view = next(
            view for view in result["views"] if view["title"] == "Overview"
        )
        assert overview_view is not None

    async def test_concurrent_render_jobs_limit(
        self, dashboard_renderer: DashboardRenderer
    ):
        """Test concurrent render job limiting."""
        # Create many concurrent render tasks
        tasks = []
        for i in range(10):
            dogs_config = [{"dog_id": f"dog_{i}", "dog_name": f"Dog {i}"}]
            tasks.append(dashboard_renderer.render_main_dashboard(dogs_config))

        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete successfully
        assert len(results) == 10
        for result in results:
            assert not isinstance(result, Exception)
            assert "views" in result

    async def test_render_timeout_handling(self, dashboard_renderer: DashboardRenderer):
        """Test rendering timeout handling."""
        # Mock slow card generator
        slow_generator = AsyncMock()
        slow_generator.side_effect = lambda *args: asyncio.sleep(35)

        dashboard_renderer.overview_generator.generate_welcome_card = slow_generator

        with pytest.raises(HomeAssistantError, match="timeout"):
            await dashboard_renderer.render_main_dashboard(
                [{"dog_id": "test", "dog_name": "Test"}]
            )

    async def test_render_error_handling(self, dashboard_renderer: DashboardRenderer):
        """Test error handling during rendering."""
        # Mock failing card generator
        failing_generator = AsyncMock()
        failing_generator.side_effect = Exception("Card generation failed")

        dashboard_renderer.overview_generator.generate_welcome_card = failing_generator

        with pytest.raises(HomeAssistantError, match="rendering failed"):
            await dashboard_renderer.render_main_dashboard(
                [{"dog_id": "test", "dog_name": "Test"}]
            )

    async def test_job_cleanup_after_completion(
        self, dashboard_renderer: DashboardRenderer
    ):
        """Test job cleanup after completion."""
        initial_active_jobs = len(dashboard_renderer._active_jobs)

        await dashboard_renderer.render_main_dashboard(
            [{"dog_id": "test", "dog_name": "Test"}]
        )

        # No active jobs should remain
        assert len(dashboard_renderer._active_jobs) == initial_active_jobs

    async def test_job_cleanup_after_error(self, dashboard_renderer: DashboardRenderer):
        """Test job cleanup after error."""
        # Mock failing generator
        dashboard_renderer.overview_generator.generate_welcome_card = AsyncMock(
            side_effect=Exception("Test error")
        )

        initial_active_jobs = len(dashboard_renderer._active_jobs)

        with pytest.raises(HomeAssistantError):
            await dashboard_renderer.render_main_dashboard(
                [{"dog_id": "test", "dog_name": "Test"}]
            )

        # Jobs should be cleaned up even after error
        assert len(dashboard_renderer._active_jobs) == initial_active_jobs


class TestDashboardRendererPerformance:
    """Test dashboard renderer performance scenarios."""

    async def test_large_dog_configuration_rendering(
        self, dashboard_renderer: DashboardRenderer
    ):
        """Test rendering with large number of dogs."""
        # Create 50-dog configuration
        large_config = []
        for i in range(50):
            large_config.append(
                {
                    "dog_id": f"dog_{i:03d}",
                    "dog_name": f"Dog {i + 1}",
                    "modules": {"feeding": True, "health": True},
                }
            )

        result = await dashboard_renderer.render_main_dashboard(large_config)

        assert "views" in result
        # Should handle large configuration efficiently
        assert len(result["views"]) > 50  # Overview + individual dogs + stats

    async def test_memory_efficient_batch_processing(
        self, dashboard_renderer: DashboardRenderer
    ):
        """Test memory-efficient batch processing."""
        # Mock memory-conscious processing
        call_counts = {"dog_calls": 0}

        async def count_calls(*args, **kwargs):
            call_counts["dog_calls"] += 1
            return [{"type": "entities", "title": "Status"}]

        dashboard_renderer.dog_generator.generate_dog_overview_cards = count_calls

        # Process 20 dogs
        dogs_config = [
            {"dog_id": f"dog_{i}", "dog_name": f"Dog {i}"} for i in range(20)
        ]

        await dashboard_renderer.render_main_dashboard(dogs_config)

        # Verify all dogs were processed
        assert call_counts["dog_calls"] == 20

    async def test_render_statistics_accuracy(
        self, dashboard_renderer: DashboardRenderer
    ):
        """Test rendering statistics collection accuracy."""
        # Perform multiple render operations
        for i in range(5):
            await dashboard_renderer.render_main_dashboard(
                [{"dog_id": f"test_{i}", "dog_name": f"Test {i}"}]
            )

        stats = dashboard_renderer.get_render_stats()

        assert stats["active_jobs"] == 0
        assert stats["total_jobs_processed"] == 5

    async def test_concurrent_different_job_types(
        self, dashboard_renderer: DashboardRenderer
    ):
        """Test concurrent processing of different job types."""
        # Mix of main dashboard and dog dashboard jobs
        tasks = []

        # Main dashboard jobs
        for i in range(3):
            dogs_config = [{"dog_id": f"main_{i}", "dog_name": f"Main {i}"}]
            tasks.append(dashboard_renderer.render_main_dashboard(dogs_config))

        # Dog dashboard jobs
        for i in range(3):
            dog_config = {"dog_id": f"dog_{i}", "dog_name": f"Dog {i}"}
            tasks.append(dashboard_renderer.render_dog_dashboard(dog_config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete successfully
        assert len(results) == 6
        for result in results:
            assert not isinstance(result, Exception)
            assert "views" in result


class TestDashboardFileOperations:
    """Test dashboard file writing operations."""

    async def test_dashboard_file_writing(
        self, dashboard_renderer: DashboardRenderer, tmp_path
    ):
        """Test dashboard file writing functionality."""
        dashboard_config = {"views": [{"title": "Test", "cards": []}]}
        file_path = tmp_path / "test_dashboard.json"
        metadata = {"title": "Test Dashboard", "created": "2024-01-15"}

        await dashboard_renderer.write_dashboard_file(
            dashboard_config, file_path, metadata
        )

        # Verify file was created
        assert file_path.exists()

        # Verify file content
        import json

        with open(file_path, encoding="utf-8") as f:
            content = json.load(f)

        assert content["version"] == 1
        assert content["data"]["config"] == dashboard_config
        assert content["data"]["title"] == "Test Dashboard"

    async def test_file_writing_error_handling(
        self, dashboard_renderer: DashboardRenderer
    ):
        """Test file writing error handling."""
        dashboard_config = {"views": []}
        invalid_path = Path("/invalid/path/dashboard.json")

        with pytest.raises(HomeAssistantError, match="file write failed"):
            await dashboard_renderer.write_dashboard_file(
                dashboard_config, invalid_path
            )

    async def test_directory_creation(
        self, dashboard_renderer: DashboardRenderer, tmp_path
    ):
        """Test automatic directory creation."""
        nested_path = tmp_path / "nested" / "directory" / "dashboard.json"
        dashboard_config = {"views": []}

        await dashboard_renderer.write_dashboard_file(dashboard_config, nested_path)

        # Verify nested directories were created
        assert nested_path.parent.exists()
        assert nested_path.exists()


class TestDashboardRendererCleanup:
    """Test dashboard renderer cleanup operations."""

    async def test_renderer_cleanup(self, dashboard_renderer: DashboardRenderer):
        """Test renderer cleanup functionality."""
        # Add some active jobs (simulate)
        dashboard_renderer._active_jobs["test_job"] = RenderJob(
            "test_job", "main_dashboard", {"dogs": []}
        )

        # Mock templates cleanup
        dashboard_renderer.templates.cleanup = AsyncMock()

        await dashboard_renderer.cleanup()

        # Verify cleanup
        assert len(dashboard_renderer._active_jobs) == 0
        dashboard_renderer.templates.cleanup.assert_called_once()

    async def test_job_cancellation_on_cleanup(
        self, dashboard_renderer: DashboardRenderer
    ):
        """Test job cancellation during cleanup."""
        # Create some jobs
        jobs = {}
        for i in range(3):
            job = RenderJob(f"job_{i}", "main_dashboard", {"dogs": []})
            job.status = "running"
            jobs[f"job_{i}"] = job

        dashboard_renderer._active_jobs = jobs
        dashboard_renderer.templates.cleanup = AsyncMock()

        await dashboard_renderer.cleanup()

        # Verify all jobs were cancelled
        for job in jobs.values():
            assert job.status == "cancelled"
