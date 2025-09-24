"""Async dashboard rendering engine for Paw Control.

This module provides high-performance, non-blocking dashboard rendering with
batch operations, lazy loading, and memory management. It processes dashboard
generation requests asynchronously to prevent blocking the event loop.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import Any

import aiofiles
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .dashboard_cards import (
    DogCardGenerator,
    ModuleCardGenerator,
    OverviewCardGenerator,
    StatisticsCardGenerator,
)
from .dashboard_templates import DashboardTemplates

_LOGGER = logging.getLogger(__name__)

# Rendering configuration
MAX_CONCURRENT_RENDERS = 3
RENDER_TIMEOUT_SECONDS = 30
MAX_CARDS_PER_BATCH = 50


class RenderJob:
    """Represents a dashboard rendering job."""

    def __init__(
        self,
        job_id: str,
        job_type: str,
        config: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> None:
        """Initialize render job.

        Args:
            job_id: Unique job identifier
            job_type: Type of rendering job
            config: Configuration data
            options: Optional rendering options
        """
        self.job_id = job_id
        self.job_type = job_type
        self.config = config
        self.options = options or {}
        self.created_at = dt_util.utcnow().timestamp()
        self.status = "pending"
        self.result: dict[str, Any] | None = None
        self.error: str | None = None


class DashboardRenderer:
    """High-performance async dashboard rendering engine.

    Provides non-blocking dashboard generation with batch processing,
    lazy loading, and efficient memory management. Supports concurrent
    rendering jobs with proper resource isolation.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize dashboard renderer.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self.templates = DashboardTemplates(hass)

        # Initialize card generators
        self.overview_generator = OverviewCardGenerator(hass, self.templates)
        self.dog_generator = DogCardGenerator(hass, self.templates)
        self.module_generator = ModuleCardGenerator(hass, self.templates)
        self.stats_generator = StatisticsCardGenerator(hass, self.templates)

        # Rendering queue and semaphore
        self._render_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)
        self._active_jobs: dict[str, RenderJob] = {}
        self._job_counter = 0

    async def render_main_dashboard(
        self,
        dogs_config: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Render main dashboard configuration.

        Args:
            dogs_config: List of dog configurations
            options: Optional rendering options

        Returns:
            Complete dashboard configuration

        Raises:
            HomeAssistantError: If rendering fails
        """
        job = RenderJob(
            job_id=self._generate_job_id(),
            job_type="main_dashboard",
            config={"dogs": dogs_config},
            options=options,
        )

        return await self._execute_render_job(job)

    async def render_dog_dashboard(
        self,
        dog_config: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Render individual dog dashboard configuration.

        Args:
            dog_config: Dog configuration
            options: Optional rendering options

        Returns:
            Complete dog dashboard configuration

        Raises:
            HomeAssistantError: If rendering fails
        """
        job = RenderJob(
            job_id=self._generate_job_id(),
            job_type="dog_dashboard",
            config={"dog": dog_config},
            options=options,
        )

        return await self._execute_render_job(job)

    async def _execute_render_job(self, job: RenderJob) -> dict[str, Any]:
        """Execute a rendering job with resource management.

        Args:
            job: Render job to execute

        Returns:
            Rendered dashboard configuration

        Raises:
            HomeAssistantError: If rendering fails
        """
        async with self._render_semaphore:
            self._active_jobs[job.job_id] = job
            job.status = "running"

            try:
                async with asyncio.timeout(RENDER_TIMEOUT_SECONDS):
                    if job.job_type == "main_dashboard":
                        result = await self._render_main_dashboard_job(job)
                    elif job.job_type == "dog_dashboard":
                        result = await self._render_dog_dashboard_job(job)
                    else:
                        raise ValueError(f"Unknown job type: {job.job_type}")

                    job.status = "completed"
                    job.result = result

                    return result

            except TimeoutError as err:
                job.status = "timeout"
                job.error = "Rendering timed out"
                _LOGGER.error("Dashboard rendering timeout for job %s", job.job_id)

                raise HomeAssistantError(
                    f"Dashboard rendering timeout: {job.job_id}"
                ) from err

            except Exception as err:
                job.status = "error"
                job.error = str(err)
                _LOGGER.error(
                    "Dashboard rendering error for job %s: %s",
                    job.job_id,
                    err,
                    exc_info=True,
                )
                raise HomeAssistantError(f"Dashboard rendering failed: {err}") from err

            finally:
                self._active_jobs.pop(job.job_id, None)

    async def _render_main_dashboard_job(self, job: RenderJob) -> dict[str, Any]:
        """Render main dashboard job.

        Args:
            job: Render job configuration

        Returns:
            Main dashboard configuration
        """
        dogs_config = job.config["dogs"]
        options = job.options

        views = []

        # Overview view - render lazily
        overview_view = await self._render_overview_view(dogs_config, options)
        views.append(overview_view)

        # Individual dog views - batch process
        dog_views = await self._render_dog_views_batch(dogs_config, options)
        views.extend(dog_views)

        # Statistics view if enabled
        if options.get("show_statistics", True):
            stats_view = await self._render_statistics_view(dogs_config, options)
            views.append(stats_view)

        # Settings view if enabled
        if options.get("show_settings", True):
            settings_view = await self._render_settings_view(dogs_config, options)
            views.append(settings_view)

        return {"views": views}

    async def _render_dog_dashboard_job(self, job: RenderJob) -> dict[str, Any]:
        """Render dog dashboard job.

        Args:
            job: Render job configuration

        Returns:
            Dog dashboard configuration
        """
        dog_config = job.config["dog"]
        options = job.options

        views = []

        # Main dog overview view
        overview_view = await self._render_dog_overview_view(dog_config, options)
        views.append(overview_view)

        # Module-specific views based on enabled modules
        module_views = await self._render_module_views(dog_config, options)
        views.extend(module_views)

        return {"views": views}

    async def _render_overview_view(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> dict[str, Any]:
        """Render overview view asynchronously.

        Args:
            dogs_config: List of dog configurations
            options: Rendering options

        Returns:
            Overview view configuration
        """
        # Process cards in parallel for better performance
        tasks = [
            self.overview_generator.generate_welcome_card(dogs_config, options),
            self.overview_generator.generate_dogs_grid(
                dogs_config, options.get("dashboard_url", "/paw-control")
            ),
            self.overview_generator.generate_quick_actions(dogs_config),
        ]

        # Add activity summary if enabled
        if options.get("show_activity_summary", True):
            tasks.append(self._render_activity_summary(dogs_config))

        # Execute tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful results and handle exceptions
        cards: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, BaseException):
                _LOGGER.warning("Overview card generation failed: %s", result)
                continue

            if isinstance(result, dict):
                cards.append(result)

        return {
            "title": "Overview",
            "path": "overview",
            "icon": "mdi:view-dashboard",
            "cards": cards,
        }

    async def _render_activity_summary(
        self, dogs_config: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Render activity summary card.

        Args:
            dogs_config: List of dog configurations

        Returns:
            Activity summary card or None
        """
        activity_entities = []

        for dog in dogs_config:
            dog_id = dog.get("dog_id")
            if dog_id:
                entity_id = f"sensor.{dog_id}_activity_level"
                # Check if entity exists before adding
                if self.hass.states.get(entity_id):
                    activity_entities.append(entity_id)

        if not activity_entities:
            return None

        return await self.templates.get_history_graph_template(
            activity_entities, "Activity Summary", 24
        )

    async def _render_dog_views_batch(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Render dog views in batches for performance.

        Args:
            dogs_config: List of dog configurations
            options: Rendering options

        Returns:
            List of dog view configurations
        """
        if not dogs_config:
            # Nothing to render; avoid zero batch size that would break range.
            return []

        views: list[dict[str, Any]] = []

        # Process dogs in batches to prevent memory issues
        estimated_cards_per_dog = max(1, MAX_CARDS_PER_BATCH // 10)
        batch_size = min(
            estimated_cards_per_dog, len(dogs_config)
        )  # Estimate cards per dog

        for i in range(0, len(dogs_config), batch_size):
            batch = dogs_config[i : i + batch_size]

            # Process batch concurrently
            batch_tasks = [
                self._render_single_dog_view(dog, i + idx, options)
                for idx, dog in enumerate(batch)
            ]

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Add successful results
            for result in batch_results:
                if isinstance(result, BaseException):
                    _LOGGER.warning("Dog view generation failed: %s", result)
                    continue

                if isinstance(result, dict):
                    views.append(result)

        return views

    async def _render_single_dog_view(
        self, dog_config: dict[str, Any], index: int, options: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Render view for a single dog.

        Args:
            dog_config: Dog configuration
            index: Dog index for theme selection
            options: Rendering options

        Returns:
            Dog view configuration or None if invalid
        """
        dog_id = dog_config.get("dog_id")
        dog_name = dog_config.get("dog_name")

        if not dog_id or not dog_name:
            return None

        # Get theme colors (cycling through available themes)
        theme_colors = self._get_dog_theme(index)

        # Generate dog cards
        cards = await self.dog_generator.generate_dog_overview_cards(
            dog_config, theme_colors, options
        )

        return {
            "title": dog_name,
            "path": dog_id.replace(" ", "_").lower(),
            "icon": "mdi:dog",
            "theme": options.get("theme", "default"),
            "cards": cards,
        }

    def _get_dog_theme(self, index: int) -> dict[str, str]:
        """Get theme colors for dog based on index.

        Args:
            index: Dog index

        Returns:
            Theme color dictionary
        """
        # Predefined theme colors
        themes = [
            {"primary": "#4CAF50", "accent": "#8BC34A"},  # Green
            {"primary": "#2196F3", "accent": "#03A9F4"},  # Blue
            {"primary": "#FF9800", "accent": "#FFC107"},  # Orange
            {"primary": "#9C27B0", "accent": "#E91E63"},  # Purple
            {"primary": "#00BCD4", "accent": "#009688"},  # Cyan
            {"primary": "#795548", "accent": "#607D8B"},  # Brown
        ]

        return themes[index % len(themes)]

    async def _render_dog_overview_view(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        """Render dog overview view.

        Args:
            dog_config: Dog configuration
            options: Rendering options

        Returns:
            Dog overview view configuration
        """
        theme = self._get_dog_theme(0)  # Use first theme for individual dashboards

        cards = await self.dog_generator.generate_dog_overview_cards(
            dog_config, theme, options
        )

        return {
            "title": "Overview",
            "path": "overview",
            "icon": "mdi:dog",
            "cards": cards,
        }

    async def _render_module_views(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Render module-specific views for dog.

        Args:
            dog_config: Dog configuration
            options: Rendering options

        Returns:
            List of module view configurations
        """
        views: list[dict[str, Any]] = []
        modules = dog_config.get("modules", {})

        # Define module views with their generators
        module_configs = [
            (
                "feeding",
                "Feeding",
                "mdi:food-drumstick",
                self.module_generator.generate_feeding_cards,
            ),
            ("walk", "Walks", "mdi:walk", self.module_generator.generate_walk_cards),
            (
                "health",
                "Health",
                "mdi:heart-pulse",
                self.module_generator.generate_health_cards,
            ),
            (
                "gps",
                "Location",
                "mdi:map-marker",
                self.module_generator.generate_gps_cards,
            ),
        ]

        # Generate views for enabled modules concurrently
        tasks = []
        for module_key, title, icon, generator in module_configs:
            if modules.get(module_key):
                tasks.append(
                    self._render_module_view(
                        dog_config, options, module_key, title, icon, generator
                    )
                )

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, BaseException):
                    _LOGGER.warning("Module view generation failed: %s", result)
                    continue

                if isinstance(result, dict):
                    views.append(result)

        return views

    async def _render_module_view(
        self,
        dog_config: dict[str, Any],
        options: dict[str, Any],
        module_key: str,
        title: str,
        icon: str,
        generator: Callable[
            [dict[str, Any], dict[str, Any]],
            Awaitable[list[dict[str, Any]]],
        ],
    ) -> dict[str, Any] | None:
        """Render a single module view.

        Args:
            dog_config: Dog configuration
            options: Rendering options
            module_key: Module identifier
            title: View title
            icon: View icon
            generator: Card generator function

        Returns:
            Module view configuration or None if failed
        """
        try:
            cards = await generator(dog_config, options)

            if not cards:
                return None

            return {
                "title": title,
                "path": module_key,
                "icon": icon,
                "cards": cards,
            }

        except Exception as err:
            _LOGGER.warning(
                "Failed to render %s view for dog %s: %s",
                module_key,
                dog_config.get("dog_name", "unknown"),
                err,
            )
            return None

    async def _render_statistics_view(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> dict[str, Any]:
        """Render statistics view.

        Args:
            dogs_config: List of dog configurations
            options: Rendering options

        Returns:
            Statistics view configuration
        """
        cards = await self.stats_generator.generate_statistics_cards(
            dogs_config, options
        )

        return {
            "title": "Statistics",
            "path": "statistics",
            "icon": "mdi:chart-line",
            "cards": cards,
        }

    async def _render_settings_view(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> dict[str, Any]:
        """Render settings view.

        Args:
            dogs_config: List of dog configurations
            options: Rendering options

        Returns:
            Settings view configuration
        """
        cards = []

        # Integration-wide settings
        cards.append(
            {
                "type": "entities",
                "title": "Integration Settings",
                "entities": [
                    "switch.paw_control_notifications_enabled",
                    "select.paw_control_data_retention_days",
                    "switch.paw_control_advanced_logging",
                ],
            }
        )

        # Per-dog settings
        for dog in dogs_config:
            dog_id = dog.get("dog_id")
            dog_name = dog.get("dog_name")

            if not dog_id or not dog_name:
                continue

            dog_entities = [f"switch.{dog_id}_notifications_enabled"]

            # Add module-specific settings
            modules = dog.get("modules", {})
            if modules.get("gps"):
                dog_entities.append(f"switch.{dog_id}_gps_tracking_enabled")
            if modules.get("visitor"):
                dog_entities.append(f"switch.{dog_id}_visitor_mode")
            if modules.get("notifications"):
                dog_entities.append(f"select.{dog_id}_notification_priority")

            cards.append(
                {
                    "type": "entities",
                    "title": f"{dog_name} Settings",
                    "entities": dog_entities,
                }
            )

        return {
            "title": "Settings",
            "path": "settings",
            "icon": "mdi:cog",
            "cards": cards,
        }

    async def write_dashboard_file(
        self,
        dashboard_config: dict[str, Any],
        file_path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Write dashboard configuration to file asynchronously.

        Args:
            dashboard_config: Dashboard configuration
            file_path: Path to write file
            metadata: Optional metadata to include

        Raises:
            HomeAssistantError: If file write fails
        """
        try:
            # Prepare dashboard data
            dashboard_data = {
                "version": 1,
                "minor_version": 1,
                "key": f"lovelace.{file_path.stem}",
                "data": {
                    "config": dashboard_config,
                    **(metadata or {}),
                },
            }

            # Ensure parent directory exists without blocking the event loop
            await self.hass.async_add_executor_job(
                partial(file_path.parent.mkdir, parents=True, exist_ok=True)
            )

            # Write file asynchronously
            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                content = json.dumps(dashboard_data, indent=2, ensure_ascii=False)
                await file.write(content)

            _LOGGER.debug("Dashboard file written: %s", file_path)

        except Exception as err:
            _LOGGER.error(
                "Failed to write dashboard file %s: %s", file_path, err, exc_info=True
            )
            raise HomeAssistantError(f"Dashboard file write failed: {err}") from err

    def _generate_job_id(self) -> str:
        """Generate unique job ID.

        Returns:
            Unique job identifier
        """
        self._job_counter += 1
        return f"render_{self._job_counter}_{int(dt_util.utcnow().timestamp())}"

    async def cleanup(self) -> None:
        """Clean up renderer resources."""
        # Clear active jobs
        for job in self._active_jobs.values():
            job.status = "cancelled"

        self._active_jobs.clear()

        # Clean up templates
        await self.templates.cleanup()

    def get_render_stats(self) -> dict[str, Any]:
        """Get rendering statistics.

        Returns:
            Rendering statistics
        """
        active_jobs = len(self._active_jobs)
        template_stats = self.templates.get_cache_stats()

        return {
            "active_jobs": active_jobs,
            "total_jobs_processed": self._job_counter,
            "template_cache": template_stats,
        }
