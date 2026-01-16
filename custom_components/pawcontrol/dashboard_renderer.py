"""Async dashboard rendering engine for Paw Control.

This module provides high-performance, non-blocking dashboard rendering with
batch operations, lazy loading, and memory management. It processes dashboard
generation requests asynchronously to prevent blocking the event loop.

Quality Scale: Platinum target
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

from typing import Generic, TypeVar
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Literal, cast

import aiofiles  # type: ignore[import-not-found, import-untyped]
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import compat
from .compat import bind_exception_alias, ensure_homeassistant_exception_symbols
from .const import (
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
)
from .dashboard_cards import (
    DogCardGenerator,
    ModuleCardGenerator,
    OverviewCardGenerator,
    StatisticsCardGenerator,
)
from .dashboard_shared import coerce_dog_config, coerce_dog_configs, unwrap_async_result
from .dashboard_templates import DashboardTemplates
from .types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    CoordinatorRejectionMetrics,
    CoordinatorStatisticsPayload,
    DashboardCardOptions,
    DashboardRendererOptions,
    DashboardRendererStatistics,
    DashboardRenderJobConfig,
    DashboardRenderResult,
    DogConfigData,
    HelperManagerGuardMetrics,
    JSONMapping,
    JSONMutableMapping,
    LovelaceCardConfig,
    LovelaceViewConfig,
    RawDogConfig,
    coerce_dog_modules_config,
)

_LOGGER = logging.getLogger(__name__)

# Rendering configuration
MAX_CONCURRENT_RENDERS = 3
RENDER_TIMEOUT_SECONDS = 30
MAX_CARDS_PER_BATCH = 50


RenderJobType = Literal["main_dashboard", "dog_dashboard"]


def _as_card_options(options: DashboardRendererOptions) -> DashboardCardOptions:
    """Return ``options`` as card generator payload."""

    return cast(DashboardCardOptions, options)


ConfigT = TypeVar("ConfigT", bound=DashboardRenderJobConfig)
OptionsT = TypeVar("OptionsT", bound=DashboardRendererOptions)
class RenderJob(Generic[ConfigT, OptionsT]):
    """Represents a dashboard rendering job."""

    def __init__(
        self,
        job_id: str,
        job_type: RenderJobType,
        config: ConfigT,
        options: OptionsT | None = None,
    ) -> None:
        """Initialize render job."""

        self.job_id = job_id
        self.job_type: RenderJobType = job_type
        self.config: ConfigT = config
        self.options: OptionsT = (
            options
            if options is not None
            else cast(
                OptionsT,
                {},
            )
        )
        self.created_at = dt_util.utcnow().timestamp()
        self.status = "pending"
        self.result: DashboardRenderResult | None = None
        self.error: str | None = None


DashboardRenderJobState = RenderJob[
    DashboardRenderJobConfig,
    DashboardRendererOptions,
]


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
        self._active_jobs: dict[str, DashboardRenderJobState] = {}
        self._job_counter = 0

    @staticmethod
    def _ensure_dog_config(dog_config: RawDogConfig) -> DogConfigData | None:
        """Return a typed dog configuration for downstream rendering."""

        return coerce_dog_config(dog_config)

    @staticmethod
    def _ensure_dog_configs(
        dogs_config: Sequence[RawDogConfig] | None,
    ) -> list[DogConfigData]:
        """Return typed dog configurations from ``dogs_config`` when possible."""

        if not dogs_config or isinstance(dogs_config, str | bytes):
            return []

        return coerce_dog_configs(dogs_config)

    async def render_main_dashboard(
        self,
        dogs_config: Sequence[RawDogConfig],
        options: DashboardRendererOptions | None = None,
        *,
        coordinator_statistics: CoordinatorStatisticsPayload
        | JSONMapping
        | None = None,
        service_execution_metrics: CoordinatorRejectionMetrics
        | JSONMapping
        | None = None,
        service_guard_metrics: HelperManagerGuardMetrics | JSONMapping | None = None,
    ) -> DashboardRenderResult:
        """Render main dashboard configuration.

        Args:
            dogs_config: List of dog configurations
            options: Optional rendering options
            coordinator_statistics: Latest coordinator snapshot for resilience
                metrics
            service_execution_metrics: Rejection metrics captured during
                service execution for diagnostics parity
            service_guard_metrics: Guard metrics captured during service
                execution for diagnostics parity

        Returns:
            Complete dashboard configuration

        Raises:
            HomeAssistantError: If rendering fails
        """
        typed_dogs = self._ensure_dog_configs(dogs_config)
        if not typed_dogs:
            _LOGGER.warning(
                "No valid dog configurations supplied for dashboard render",
            )
            empty_result: DashboardRenderResult = {"views": []}
            return empty_result

        job_config: DashboardRenderJobConfig = {
            "dogs": typed_dogs,
        }
        if coordinator_statistics is not None:
            job_config["coordinator_statistics"] = coordinator_statistics
        if service_execution_metrics is not None:
            job_config["service_execution_metrics"] = service_execution_metrics
        if service_guard_metrics is not None:
            job_config["service_guard_metrics"] = service_guard_metrics

        job = RenderJob(
            job_id=self._generate_job_id(),
            job_type="main_dashboard",
            config=job_config,
            options=options,
        )

        return await self._execute_render_job(job)

    async def render_dog_dashboard(
        self,
        dog_config: RawDogConfig,
        options: DashboardRendererOptions | None = None,
    ) -> DashboardRenderResult:
        """Render individual dog dashboard configuration.

        Args:
            dog_config: Dog configuration
            options: Optional rendering options

        Returns:
            Complete dog dashboard configuration

        Raises:
            HomeAssistantError: If rendering fails
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            _LOGGER.warning(
                "Dog dashboard render skipped: configuration payload is empty",
            )
            empty_result: DashboardRenderResult = {"views": []}
            return empty_result

        job_config: DashboardRenderJobConfig = {"dog": typed_dog}

        job = RenderJob(
            job_id=self._generate_job_id(),
            job_type="dog_dashboard",
            config=job_config,
            options=options,
        )

        return await self._execute_render_job(job)

    async def _execute_render_job(
        self,
        job: DashboardRenderJobState,
    ) -> DashboardRenderResult:
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
                _LOGGER.error(
                    "Dashboard rendering timeout for job %s",
                    job.job_id,
                )

                raise HomeAssistantError(
                    f"Dashboard rendering timeout: {job.job_id}",
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
                raise HomeAssistantError(
                    f"Dashboard rendering failed: {err}",
                ) from err

            finally:
                self._active_jobs.pop(job.job_id, None)

    async def _render_main_dashboard_job(
        self,
        job: DashboardRenderJobState,
    ) -> DashboardRenderResult:
        """Render main dashboard job.

        Args:
            job: Render job configuration

        Returns:
            Main dashboard configuration
        """
        dogs_config = self._ensure_dog_configs(
            cast(Sequence[RawDogConfig] | None, job.config.get("dogs")),
        )
        if not dogs_config:
            _LOGGER.warning(
                "Main dashboard job aborted: typed dog configurations missing",
            )
            empty_result: DashboardRenderResult = {"views": []}
            return empty_result
        options = job.options
        coordinator_statistics = cast(
            CoordinatorStatisticsPayload | JSONMapping | None,
            job.config.get("coordinator_statistics"),
        )
        service_execution_metrics = cast(
            CoordinatorRejectionMetrics | JSONMapping | None,
            job.config.get("service_execution_metrics"),
        )
        service_guard_metrics = cast(
            HelperManagerGuardMetrics | JSONMapping | None,
            job.config.get("service_guard_metrics"),
        )

        views: list[LovelaceViewConfig] = []

        # Overview view - render lazily
        overview_view = await self._render_overview_view(dogs_config, options)
        views.append(overview_view)

        # Individual dog views - batch process
        dog_views = await self._render_dog_views_batch(dogs_config, options)
        views.extend(dog_views)

        # Statistics view if enabled
        if options.get("show_statistics", True):
            stats_view = await self._render_statistics_view(
                dogs_config,
                options,
                coordinator_statistics=coordinator_statistics,
                service_execution_metrics=service_execution_metrics,
                service_guard_metrics=service_guard_metrics,
            )
            views.append(stats_view)

        # Settings view if enabled
        if options.get("show_settings", True):
            settings_view = await self._render_settings_view(dogs_config, options)
            views.append(settings_view)

        render_result: DashboardRenderResult = {"views": views}
        return render_result

    async def _render_dog_dashboard_job(
        self,
        job: DashboardRenderJobState,
    ) -> DashboardRenderResult:
        """Render dog dashboard job.

        Args:
            job: Render job configuration

        Returns:
            Dog dashboard configuration
        """
        dog_config = self._ensure_dog_config(
            cast(RawDogConfig, job.config.get("dog")),
        )
        if dog_config is None:
            _LOGGER.warning(
                "Dog dashboard job aborted: typed dog configuration missing",
            )
            empty_result: DashboardRenderResult = {"views": []}
            return empty_result
        options = job.options

        views: list[LovelaceViewConfig] = []

        # Main dog overview view
        overview_view = await self._render_dog_overview_view(dog_config, options)
        views.append(overview_view)

        # Module-specific views based on enabled modules
        module_views = await self._render_module_views(dog_config, options)
        views.extend(module_views)

        render_result: DashboardRenderResult = {"views": views}
        return render_result

    async def _render_overview_view(
        self,
        dogs_config: Sequence[DogConfigData],
        options: DashboardRendererOptions,
    ) -> LovelaceViewConfig:
        """Render overview view asynchronously.

        Args:
            dogs_config: List of dog configurations
            options: Rendering options

        Returns:
            Overview view configuration
        """
        # Process cards in parallel for better performance
        card_options = _as_card_options(options)
        dashboard_url = card_options.get("dashboard_url")
        navigation_url = (
            dashboard_url
            if isinstance(dashboard_url, str) and dashboard_url
            else "/paw-control"
        )
        task_definitions: list[tuple[str, Awaitable[LovelaceCardConfig | None]]] = [
            (
                "welcome",
                self.overview_generator.generate_welcome_card(
                    dogs_config,
                    card_options,
                ),
            ),
            (
                "dog_grid",
                self.overview_generator.generate_dogs_grid(
                    dogs_config,
                    navigation_url,
                ),
            ),
            (
                "quick_actions",
                self.overview_generator.generate_quick_actions(dogs_config),
            ),
        ]

        if options.get("show_activity_summary", True):
            task_definitions.append(
                (
                    "activity_summary",
                    self._render_activity_summary(dogs_config),
                ),
            )

        results = await asyncio.gather(
            *(task for _, task in task_definitions),
            return_exceptions=True,
        )

        cards: list[LovelaceCardConfig] = []
        for (task_name, _), result in zip(task_definitions, results, strict=False):
            card_payload = _unwrap_async_result(
                result,
                context=f"Overview card generation failed ({task_name})",
            )
            if card_payload is None:
                continue
            cards.append(card_payload)

        overview_view: LovelaceViewConfig = {
            "title": "Overview",
            "path": "overview",
            "icon": "mdi:view-dashboard",
            "cards": cards,
        }
        return overview_view

    async def _render_activity_summary(
        self,
        dogs_config: Sequence[DogConfigData],
    ) -> LovelaceCardConfig | None:
        """Render activity summary card.

        Args:
            dogs_config: List of dog configurations

        Returns:
            Activity summary card or None
        """
        activity_entities = []

        for dog in dogs_config:
            dog_id = dog.get(DOG_ID_FIELD)
            if not dog_id:
                continue

            entity_id = f"sensor.{dog_id}_activity_level"
            # Check if entity exists before adding
            if self.hass.states.get(entity_id):
                activity_entities.append(entity_id)

        if not activity_entities:
            return None

        return await self.templates.get_history_graph_template(
            activity_entities,
            "Activity Summary",
            24,
        )

    async def _render_dog_views_batch(
        self,
        dogs_config: Sequence[DogConfigData],
        options: DashboardRendererOptions,
    ) -> list[LovelaceViewConfig]:
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

        dogs_list = list(dogs_config)
        views: list[LovelaceViewConfig] = []

        # Process dogs in batches to prevent memory issues
        estimated_cards_per_dog = max(1, MAX_CARDS_PER_BATCH // 10)
        batch_size = min(
            estimated_cards_per_dog,
            len(dogs_list),
        )  # Estimate cards per dog

        for i in range(0, len(dogs_list), batch_size):
            batch = dogs_list[i : i + batch_size]

            # Process batch concurrently
            batch_jobs: list[
                tuple[DogConfigData, Awaitable[LovelaceViewConfig | None]]
            ] = [
                (
                    dog,
                    self._render_single_dog_view(dog, i + idx, options),
                )
                for idx, dog in enumerate(batch)
            ]

            batch_results = await asyncio.gather(
                *(job for _, job in batch_jobs),
                return_exceptions=True,
            )

            for (dog, _), result in zip(batch_jobs, batch_results, strict=False):
                dog_name = dog.get(DOG_NAME_FIELD)
                dog_identifier = (
                    dog_name
                    or dog.get(
                        DOG_ID_FIELD,
                    )
                    or f"dog_{id(dog)}"
                )
                view_payload = _unwrap_async_result(
                    result,
                    context=f"Dog view generation failed for {dog_identifier}",
                )
                if view_payload is None:
                    continue
                views.append(view_payload)

        return views

    async def _render_single_dog_view(
        self,
        dog_config: DogConfigData,
        index: int,
        options: DashboardRendererOptions,
    ) -> LovelaceViewConfig | None:
        """Render view for a single dog.

        Args:
            dog_config: Dog configuration
            index: Dog index for theme selection
            options: Rendering options

        Returns:
            Dog view configuration or None if invalid
        """
        dog_id = dog_config.get(DOG_ID_FIELD)
        dog_name = dog_config.get(DOG_NAME_FIELD)

        if not dog_id or not dog_name:
            return None

        # Get theme colors (cycling through available themes)
        theme_colors = self._get_dog_theme(index)

        # Generate dog cards
        cards = await self.dog_generator.generate_dog_overview_cards(
            dog_config,
            theme_colors,
            _as_card_options(options),
        )

        view_config: LovelaceViewConfig = {
            "title": dog_name,
            "path": dog_id.replace(" ", "_").lower(),
            "icon": "mdi:dog",
            "theme": options.get("theme", "default"),
            "cards": cards,
        }
        return view_config

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
        self,
        dog_config: DogConfigData,
        options: DashboardRendererOptions,
    ) -> LovelaceViewConfig:
        """Render dog overview view.

        Args:
            dog_config: Dog configuration
            options: Rendering options

        Returns:
            Dog overview view configuration
        """
        theme = self._get_dog_theme(
            0,
        )  # Use first theme for individual dashboards

        cards = await self.dog_generator.generate_dog_overview_cards(
            dog_config,
            theme,
            _as_card_options(options),
        )

        overview_view: LovelaceViewConfig = {
            "title": "Overview",
            "path": "overview",
            "icon": "mdi:dog",
            "cards": cards,
        }
        return overview_view

    async def _render_module_views(
        self,
        dog_config: DogConfigData,
        options: DashboardRendererOptions,
    ) -> list[LovelaceViewConfig]:
        """Render module-specific views for dog.

        Args:
            dog_config: Dog configuration
            options: Rendering options

        Returns:
            List of module view configurations
        """
        views: list[LovelaceViewConfig] = []
        modules = coerce_dog_modules_config(dog_config.get(DOG_MODULES_FIELD))

        # Define module views with their generators
        module_configs = [
            (
                MODULE_FEEDING,
                "Feeding",
                "mdi:food-drumstick",
                self.module_generator.generate_feeding_cards,
            ),
            (
                MODULE_WALK,
                "Walks",
                "mdi:walk",
                self.module_generator.generate_walk_cards,
            ),
            (
                MODULE_HEALTH,
                "Health",
                "mdi:heart-pulse",
                self.module_generator.generate_health_cards,
            ),
            (
                MODULE_NOTIFICATIONS,
                "Notifications",
                "mdi:bell",
                self.module_generator.generate_notification_cards,
            ),
            (
                MODULE_GPS,
                "Location",
                "mdi:map-marker",
                self.module_generator.generate_gps_cards,
            ),
            (
                MODULE_VISITOR,
                "Visitors",
                "mdi:home-account",
                self.module_generator.generate_visitor_cards,
            ),
        ]

        # Generate views for enabled modules concurrently
        task_definitions: list[
            tuple[
                str,
                Awaitable[LovelaceViewConfig | None],
            ]
        ] = []
        for module_key, title, icon, generator in module_configs:
            if modules.get(module_key):
                task_definitions.append(
                    (
                        module_key,
                        self._render_module_view(
                            dog_config,
                            options,
                            module_key,
                            title,
                            icon,
                            generator,
                        ),
                    ),
                )

        if task_definitions:
            results = await asyncio.gather(
                *(task for _, task in task_definitions),
                return_exceptions=True,
            )

            for (module_key, _), result in zip(task_definitions, results, strict=False):
                view_payload = _unwrap_async_result(
                    result,
                    context=f"Module view generation failed ({module_key})",
                )
                if view_payload is None:
                    continue
                views.append(view_payload)

        return views

    async def _render_module_view(
        self,
        dog_config: DogConfigData,
        options: DashboardRendererOptions,
        module_key: str,
        title: str,
        icon: str,
        generator: Callable[
            [JSONMapping | DogConfigData, DashboardCardOptions],
            Awaitable[list[LovelaceCardConfig]],
        ],
    ) -> LovelaceViewConfig | None:
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
            cards = await generator(dog_config, _as_card_options(options))

            if not cards:
                return None

            view_config: LovelaceViewConfig = {
                "title": title,
                "path": module_key,
                "icon": icon,
                "cards": cards,
            }
            return view_config

        except Exception as err:
            _LOGGER.warning(
                "Failed to render %s view for dog %s: %s",
                module_key,
                dog_config.get(DOG_NAME_FIELD, "unknown"),
                err,
            )
            return None

    async def _render_statistics_view(
        self,
        dogs_config: Sequence[DogConfigData],
        options: DashboardRendererOptions,
        *,
        coordinator_statistics: CoordinatorStatisticsPayload
        | JSONMapping
        | None = None,
        service_execution_metrics: CoordinatorRejectionMetrics
        | JSONMapping
        | None = None,
        service_guard_metrics: HelperManagerGuardMetrics | JSONMapping | None = None,
    ) -> LovelaceViewConfig:
        """Render statistics view.

        Args:
            dogs_config: List of dog configurations
            options: Rendering options
            coordinator_statistics: Coordinator resilience metrics snapshot
            service_execution_metrics: Service execution rejection metrics
            service_guard_metrics: Guard metrics recorded during service execution

        Returns:
            Statistics view configuration
        """
        cards = await self.stats_generator.generate_statistics_cards(
            dogs_config,
            _as_card_options(options),
            coordinator_statistics=coordinator_statistics,
            service_execution_metrics=service_execution_metrics,
            service_guard_metrics=service_guard_metrics,
        )

        statistics_view: LovelaceViewConfig = {
            "title": "Statistics",
            "path": "statistics",
            "icon": "mdi:chart-line",
            "cards": cards,
        }
        return statistics_view

    async def _render_settings_view(
        self,
        dogs_config: Sequence[DogConfigData],
        options: DashboardRendererOptions,
    ) -> LovelaceViewConfig:
        """Render settings view.

        Args:
            dogs_config: List of dog configurations
            options: Rendering options

        Returns:
            Settings view configuration
        """
        cards: list[LovelaceCardConfig] = []

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
            },
        )

        # Per-dog settings
        for dog in dogs_config:
            dog_id = dog.get(DOG_ID_FIELD)
            dog_name = dog.get(DOG_NAME_FIELD)

            if not dog_id or not dog_name:
                continue

            dog_entities = [f"switch.{dog_id}_notifications_enabled"]

            # Add module-specific settings
            modules = coerce_dog_modules_config(dog.get(DOG_MODULES_FIELD))
            if modules.get(MODULE_GPS):
                dog_entities.append(f"switch.{dog_id}_gps_tracking_enabled")
            if modules.get(MODULE_VISITOR):
                dog_entities.append(f"switch.{dog_id}_visitor_mode")
            if modules.get(MODULE_NOTIFICATIONS):
                dog_entities.append(f"select.{dog_id}_notification_priority")

            cards.append(
                {
                    "type": "entities",
                    "title": f"{dog_name} Settings",
                    "entities": dog_entities,
                },
            )

        settings_view: LovelaceViewConfig = {
            "title": "Settings",
            "path": "settings",
            "icon": "mdi:cog",
            "cards": cards,
        }
        return settings_view

    async def write_dashboard_file(
        self,
        dashboard_config: DashboardRenderResult,
        file_path: Path,
        metadata: JSONMutableMapping | None = None,
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
            metadata_payload: JSONMutableMapping
            if metadata is not None:
                metadata_payload = metadata
            else:
                metadata_payload = cast(JSONMutableMapping, {})

            dashboard_data = cast(
                JSONMutableMapping,
                {
                    "version": 1,
                    "minor_version": 1,
                    "key": f"lovelace.{file_path.stem}",
                    "data": {
                        "config": dashboard_config,
                        **metadata_payload,
                    },
                },
            )

            # Ensure parent directory exists without blocking the event loop
            await self.hass.async_add_executor_job(
                partial(file_path.parent.mkdir, parents=True, exist_ok=True),
            )

            # Write file asynchronously
            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                content = json.dumps(
                    dashboard_data,
                    indent=2,
                    ensure_ascii=False,
                )
                await file.write(content)

            _LOGGER.debug("Dashboard file written: %s", file_path)

        except Exception as err:
            _LOGGER.error(
                "Failed to write dashboard file %s: %s",
                file_path,
                err,
                exc_info=True,
            )
            raise HomeAssistantError(
                f"Dashboard file write failed: {err}",
            ) from err

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

    def get_render_stats(self) -> DashboardRendererStatistics:
        """Get rendering statistics.

        Returns:
            Rendering statistics
        """
        active_jobs = len(self._active_jobs)
        template_stats = self.templates.get_cache_stats()

        render_stats: DashboardRendererStatistics = {
            "active_jobs": active_jobs,
            "total_jobs_processed": self._job_counter,
            "template_cache": template_stats,
        }
        return render_stats


_unwrap_async_result = partial(unwrap_async_result, logger=_LOGGER)


ensure_homeassistant_exception_symbols()
HomeAssistantError: type[Exception] = cast(
    type[Exception],
    compat.HomeAssistantError,
)
bind_exception_alias("HomeAssistantError", combine_with_current=True)
