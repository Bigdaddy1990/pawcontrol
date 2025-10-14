"""Optimized Dashboard Generator for Paw Control integration.

PERFORMANCE-OPTIMIZED: Enhanced dashboard creation with async file operations,
intelligent caching, batch processing, and comprehensive error recovery.

Quality Scale: Bronze target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any, Final, NotRequired, TypedDict, TypeVar

import aiofiles
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .compat import ConfigEntry, HomeAssistantError
from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_NOTIFICATIONS,
    MODULE_WEATHER,
)
from .dashboard_renderer import DashboardRenderer
from .dashboard_shared import (
    coerce_dog_config,
    coerce_dog_configs,
    unwrap_async_result,
)
from .dashboard_templates import DashboardTemplates
from .types import (
    DogConfigData,
    DogModulesConfig,
    RawDogConfig,
    coerce_dog_modules_config,
)

_LOGGER = logging.getLogger(__name__)

# Dashboard configuration constants
DASHBOARD_STORAGE_KEY: Final[str] = f"{DOMAIN}_dashboards"
DASHBOARD_STORAGE_VERSION: Final[int] = (
    4  # OPTIMIZED: Version bump for performance improvements
)
DEFAULT_DASHBOARD_TITLE: Final[str] = "🐕 Paw Control"
DEFAULT_DASHBOARD_ICON: Final[str] = "mdi:dog"
DEFAULT_DASHBOARD_URL: Final[str] = "paw-control"
NON_MODULE_VIEW_PATHS: Final[frozenset[str]] = frozenset(
    {"overview", "statistics", "settings", "weather-overview"}
)

# OPTIMIZED: Performance monitoring constants
DASHBOARD_GENERATION_TIMEOUT: Final[float] = 30.0
MAX_CONCURRENT_DASHBOARD_OPERATIONS: Final[int] = 3
PERFORMANCE_LOG_THRESHOLD: Final[float] = 2.0  # Log if operation takes > 2s


class DashboardViewSummary(TypedDict):
    """Summary describing an exported Lovelace view."""

    path: str
    title: str
    icon: str
    card_count: int
    module: NotRequired[str]
    notifications: NotRequired[bool]


_TrackedResultT = TypeVar("_TrackedResultT")


class PawControlDashboardGenerator:
    """Performance-optimized dashboard generator.

    PERFORMANCE IMPROVEMENTS:
    - Async file operations prevent event loop blocking
    - Intelligent batching for multiple dashboard operations
    - Enhanced caching with automatic cleanup
    - Resource pooling for concurrent operations
    - Comprehensive performance monitoring
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize optimized dashboard generator."""
        self.hass = hass
        self.entry = entry

        # OPTIMIZED: Enhanced storage with better versioning
        self._store = Store[dict[str, Any]](
            hass,
            DASHBOARD_STORAGE_VERSION,
            f"{DASHBOARD_STORAGE_KEY}_{entry.entry_id}",
            minor_version=1,  # Allow minor version updates
        )

        # OPTIMIZED: Renderer with resource pooling
        self._renderer = DashboardRenderer(hass)

        # Weather dashboard templates
        self._dashboard_templates = DashboardTemplates(hass)

        # Dashboard registry with performance metadata
        self._dashboards: dict[str, dict[str, Any]] = {}

        # OPTIMIZED: Enhanced state management
        self._initialized = False
        self._lock = asyncio.Lock()
        self._operation_semaphore = asyncio.Semaphore(
            MAX_CONCURRENT_DASHBOARD_OPERATIONS
        )

        # OPTIMIZED: Performance monitoring
        self._performance_metrics = {
            "total_generations": 0,
            "avg_generation_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "file_operations": 0,
            "errors": 0,
        }
        # OPTIMIZED: Track pending cleanup tasks for asynchronous resource release
        self._cleanup_tasks: set[asyncio.Task[Any]] = set()

    def _track_task(
        self,
        awaitable: Awaitable[_TrackedResultT] | asyncio.Task[_TrackedResultT],
        *,
        name: str | None = None,
        log_exceptions: bool = False,
    ) -> asyncio.Task[_TrackedResultT]:
        """Create, name, and track a task for later cleanup."""

        def _set_task_name(task_to_name: asyncio.Task[Any]) -> None:
            if not name or not hasattr(task_to_name, "set_name"):
                return

            with contextlib.suppress(Exception):
                task_to_name.set_name(name)

        if isinstance(awaitable, asyncio.Task):
            task: asyncio.Task[_TrackedResultT] = awaitable
        else:
            scheduled: asyncio.Task[_TrackedResultT] | None = None
            hass = getattr(self, "hass", None)

            if hass is not None:
                create_task = getattr(hass, "async_create_task", None)
                if callable(create_task):
                    try:
                        scheduled = create_task(awaitable, name=name)
                    except TypeError:
                        scheduled = create_task(awaitable)
                    except RuntimeError:
                        scheduled = None

                if scheduled is None:
                    loop = getattr(hass, "loop", None)
                    if loop is not None:
                        try:
                            scheduled = loop.create_task(awaitable, name=name)
                        except TypeError:
                            scheduled = loop.create_task(awaitable)
                        except RuntimeError:
                            scheduled = None

            if scheduled is None:
                try:
                    scheduled = asyncio.create_task(awaitable, name=name)
                except TypeError:
                    scheduled = asyncio.create_task(awaitable)
                except RuntimeError as err:
                    raise RuntimeError(
                        "Unable to schedule dashboard background task"
                    ) from err

            if scheduled is None:
                raise RuntimeError("Unable to schedule dashboard background task")

            task = scheduled

        _set_task_name(task)

        self._cleanup_tasks.add(task)

        def _on_task_done(completed: asyncio.Task[_TrackedResultT]) -> None:
            self._cleanup_tasks.discard(completed)

            if completed.cancelled():
                return

            try:
                exception = completed.exception()
            except asyncio.CancelledError:
                return

            if exception is not None and log_exceptions:
                context = name or completed.get_name() or "dashboard background task"
                _unwrap_async_result(
                    exception,
                    context=f"Unhandled error in {context}",
                    level=logging.ERROR,
                    suppress_cancelled=True,
                )

        task.add_done_callback(_on_task_done)
        return task

    @staticmethod
    def _ensure_dog_config(dog_config: RawDogConfig) -> DogConfigData | None:
        """Return a typed dog configuration extracted from ``dog_config``."""

        return coerce_dog_config(dog_config)

    def _ensure_dog_configs(
        self, dogs_config: Sequence[RawDogConfig]
    ) -> list[DogConfigData]:
        """Return typed dog configurations for downstream operations."""

        return coerce_dog_configs(dogs_config)

    @staticmethod
    def _ensure_modules_config(
        dog: Mapping[str, Any] | DogConfigData,
    ) -> DogModulesConfig:
        """Return a typed modules payload extracted from ``dog``."""

        modules_payload = dog.get("modules") if isinstance(dog, Mapping) else None
        return coerce_dog_modules_config(modules_payload)

    @staticmethod
    def _monotonic_time() -> float:
        """Return monotonic time for performance tracking."""

        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:
            return time.perf_counter()

    @staticmethod
    def _summarise_dashboard_views(
        dashboard_config: Mapping[str, Any],
    ) -> list[DashboardViewSummary]:
        """Return a compact summary of the Lovelace views in ``dashboard_config``."""

        views = dashboard_config.get("views")
        if not isinstance(views, Sequence) or isinstance(views, str | bytes):
            return []

        summaries: list[DashboardViewSummary] = []
        for view in views:
            if not isinstance(view, Mapping):
                continue

            path = str(view.get("path", ""))
            title_value = view.get("title", "")
            icon_value = view.get("icon", "")
            cards = view.get("cards")

            summary: DashboardViewSummary = {
                "path": path,
                "title": str(title_value) if title_value is not None else "",
                "icon": str(icon_value) if icon_value is not None else "",
                "card_count": (
                    len(cards)
                    if isinstance(cards, Sequence)
                    and not isinstance(cards, str | bytes)
                    else 0
                ),
            }

            if path and path not in NON_MODULE_VIEW_PATHS:
                summary["module"] = path

            if path == MODULE_NOTIFICATIONS:
                summary["notifications"] = True

            summaries.append(summary)

        return summaries

    @staticmethod
    def _normalize_view_summaries(
        value: Any,
    ) -> list[DashboardViewSummary] | None:
        """Return a normalised ``DashboardViewSummary`` list when ``value`` is valid."""

        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            return None

        normalised: list[DashboardViewSummary] = []
        for item in value:
            if not isinstance(item, Mapping):
                return None

            card_count_raw = item.get("card_count")
            try:
                card_count = int(card_count_raw)
            except (TypeError, ValueError):
                card_count = 0

            path_value = str(item.get("path", ""))

            summary: DashboardViewSummary = {
                "path": path_value,
                "title": str(item.get("title", "")),
                "icon": str(item.get("icon", "")),
                "card_count": max(card_count, 0),
            }

            module = item.get("module")
            if isinstance(module, str) and module:
                summary["module"] = module
            elif path_value and path_value not in NON_MODULE_VIEW_PATHS:
                summary["module"] = path_value

            notifications = item.get("notifications")
            if isinstance(notifications, bool):
                summary["notifications"] = notifications
            elif path_value == MODULE_NOTIFICATIONS:
                summary["notifications"] = True

            normalised.append(summary)

        return normalised

    async def _load_dashboard_config(self, path: Path) -> Mapping[str, Any] | None:
        """Load the stored Lovelace config from ``path`` if the file exists."""

        try:
            async with aiofiles.open(path, encoding="utf-8") as file_handle:
                data = json.loads(await file_handle.read())
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as err:
            _LOGGER.debug("Invalid dashboard JSON at %s: %s", path, err)
            return None
        except OSError as err:
            _LOGGER.debug("Unable to read dashboard file %s: %s", path, err)
            return None

        config = (
            data.get("data", {}).get("config") if isinstance(data, Mapping) else None
        )
        return config if isinstance(config, Mapping) else None

    @staticmethod
    def _has_notifications_view(
        view_summaries: Sequence[DashboardViewSummary],
    ) -> bool:
        """Return True when a notifications module view is present."""

        return any(view.get("path") == MODULE_NOTIFICATIONS for view in view_summaries)

    async def async_initialize(self) -> None:
        """Initialize with enhanced error recovery and performance monitoring."""
        if self._initialized:
            return

        start_time = self._monotonic_time()

        async with self._lock:
            if self._initialized:
                return

            try:
                # OPTIMIZED: Parallel initialization of renderer, templates, and storage
                renderer_task = self._track_task(
                    self._renderer.async_initialize(),
                    name="pawcontrol_dashboard_renderer_init",
                )
                templates_task = self._track_task(
                    self._dashboard_templates.async_initialize(),
                    name="pawcontrol_dashboard_templates_init",
                )
                storage_task = self._track_task(
                    self._load_stored_data(),
                    name="pawcontrol_dashboard_load_stored_data",
                )

                # Wait for all with timeout
                await asyncio.wait_for(
                    asyncio.gather(renderer_task, templates_task, storage_task),
                    timeout=DASHBOARD_GENERATION_TIMEOUT,
                )

                _LOGGER.info(
                    "Dashboard generator initialized: %d existing dashboards",
                    len(self._dashboards),
                )

            except TimeoutError:
                _LOGGER.error("Dashboard generator initialization timeout")
                await self._cleanup_failed_initialization()
                raise HomeAssistantError("Dashboard initialization timeout")  # noqa: B904
            except Exception as err:
                _LOGGER.warning(
                    "Dashboard initialization error: %s, using defaults", err
                )
                self._dashboards = {}
            finally:
                self._initialized = True
                init_time = self._monotonic_time() - start_time
                if init_time > PERFORMANCE_LOG_THRESHOLD:
                    _LOGGER.info("Dashboard init took %.2fs", init_time)

    async def _load_stored_data(self) -> None:
        """Load stored data with validation and cleanup."""
        try:
            stored_data = await self._store.async_load() or {}
            self._dashboards = stored_data.get("dashboards", {})

            # OPTIMIZED: Async validation to prevent blocking
            validation_task = self._track_task(
                self._validate_stored_dashboards(),
                name="pawcontrol_dashboard_validate_stored",
            )
            await asyncio.wait_for(validation_task, timeout=10.0)

        except TimeoutError:
            _LOGGER.warning("Dashboard validation timeout, using empty state")
            self._dashboards = {}
        except Exception as err:
            _LOGGER.warning("Error loading stored dashboards: %s", err)
            self._dashboards = {}

    async def _cleanup_failed_initialization(self) -> None:
        """Cleanup resources after failed initialization."""
        cleanup_jobs: list[tuple[str, Awaitable[Any]]] = []

        if hasattr(self, "_renderer"):
            cleanup_jobs.append(("renderer cleanup", self._renderer.cleanup()))

        if cleanup_jobs:
            results = await asyncio.gather(
                *(job for _, job in cleanup_jobs),
                return_exceptions=True,
            )
            for (label, _), result in zip(cleanup_jobs, results, strict=False):
                _unwrap_async_result(
                    result,
                    context=f"Failed during {label}",
                    level=logging.DEBUG,
                    suppress_cancelled=True,
                )

    async def async_create_dashboard(
        self,
        dogs_config: Sequence[RawDogConfig],
        options: dict[str, Any] | None = None,
    ) -> str:
        """Create dashboard with enhanced performance monitoring."""
        if not self._initialized:
            await self.async_initialize()

        if not dogs_config:
            raise ValueError("At least one dog configuration is required")

        typed_dogs = self._ensure_dog_configs(dogs_config)
        if not typed_dogs:
            raise ValueError("At least one valid dog configuration is required")

        options = options or {}
        start_time = self._monotonic_time()

        async with self._operation_semaphore:  # OPTIMIZED: Control concurrency
            try:
                # OPTIMIZED: Parallel config generation and URL preparation
                config_task = self._track_task(
                    self._renderer.render_main_dashboard(typed_dogs, options),
                    name="pawcontrol_dashboard_render_main",
                )

                url_task = self._track_task(
                    self._generate_unique_dashboard_url(options),
                    name="pawcontrol_dashboard_generate_url",
                )

                dashboard_config, dashboard_url = await asyncio.gather(
                    config_task, url_task
                )

                # OPTIMIZED: Async dashboard creation with batching
                result_url = await self._create_dashboard_optimized(
                    dashboard_url, dashboard_config, typed_dogs, options
                )

                # OPTIMIZED: Update performance metrics
                generation_time = self._monotonic_time() - start_time
                await self._update_performance_metrics("generation", generation_time)

                if generation_time > PERFORMANCE_LOG_THRESHOLD:
                    _LOGGER.info(
                        "Dashboard creation took %.2fs for %d dogs",
                        generation_time,
                        len(typed_dogs),
                    )

                return result_url

            except Exception as err:
                self._performance_metrics["errors"] += 1
                _LOGGER.error("Dashboard creation failed: %s", err, exc_info=True)
                raise HomeAssistantError(f"Dashboard creation failed: {err}") from err

    async def _generate_unique_dashboard_url(self, options: dict[str, Any]) -> str:
        """Generate unique URL for dashboard."""
        base_url = options.get("url", DEFAULT_DASHBOARD_URL)
        dashboard_url = f"{base_url}-{self.entry.entry_id[:8]}"
        return slugify(dashboard_url)

    async def _create_dashboard_optimized(
        self,
        dashboard_url: str,
        dashboard_config: dict[str, Any],
        dogs_config: Sequence[RawDogConfig],
        options: dict[str, Any],
    ) -> str:
        """Create dashboard with optimized file operations."""
        typed_dogs = self._ensure_dog_configs(dogs_config)

        async with self._lock:
            dashboard_title = options.get("title", DEFAULT_DASHBOARD_TITLE)
            dashboard_icon = options.get("icon", DEFAULT_DASHBOARD_ICON)

            # OPTIMIZED: Async file creation with error recovery
            try:
                dashboard_path = await self._create_dashboard_file_async(
                    dashboard_url,
                    dashboard_title,
                    dashboard_config,
                    dashboard_icon,
                    options.get("show_in_sidebar", True),
                )

                # OPTIMIZED: Batch metadata operations
                await self._store_dashboard_metadata_batch(
                    dashboard_url,
                    dashboard_title,
                    str(dashboard_path),
                    dashboard_config,
                    typed_dogs,
                    options,
                )

                _LOGGER.info(
                    "Created dashboard '%s' at /%s for %d dogs",
                    dashboard_title,
                    dashboard_url,
                    len(typed_dogs),
                )

                return f"/{dashboard_url}"

            except Exception:
                # OPTIMIZED: Cleanup on failure
                await self._cleanup_failed_dashboard(dashboard_url)
                raise

    async def _create_dashboard_file_async(
        self,
        url_path: str,
        title: str,
        config: dict[str, Any],
        icon: str,
        show_in_sidebar: bool,
    ) -> Path:
        """Create dashboard file with async operations."""
        storage_dir = Path(self.hass.config.path(".storage"))
        dashboard_file = storage_dir / f"lovelace.{url_path}"

        # OPTIMIZED: Build complete dashboard data structure
        dashboard_data = {
            "data": {
                "config": {
                    "title": title,
                    "icon": icon,
                    "path": url_path,
                    "require_admin": False,
                    "show_in_sidebar": show_in_sidebar,
                    "views": config.get("views", []),
                }
            }
        }

        # OPTIMIZED: Async file writing with proper encoding
        try:
            async with aiofiles.open(dashboard_file, "w", encoding="utf-8") as f:
                json_str = json.dumps(dashboard_data, indent=2, ensure_ascii=False)
                await f.write(json_str)

            self._performance_metrics["file_operations"] += 1
            return dashboard_file

        except Exception as err:
            _LOGGER.error("Failed to write dashboard file %s: %s", dashboard_file, err)
            # OPTIMIZED: Cleanup partial file
            with contextlib.suppress(Exception):
                await asyncio.to_thread(dashboard_file.unlink, missing_ok=True)
            raise HomeAssistantError(f"Dashboard file creation failed: {err}") from err

    async def _store_dashboard_metadata_batch(
        self,
        dashboard_url: str,
        title: str,
        path: str,
        dashboard_config: Mapping[str, Any],
        dogs_config: Sequence[RawDogConfig],
        options: dict[str, Any],
    ) -> None:
        """Store dashboard metadata with batching."""
        typed_dogs = self._ensure_dog_configs(dogs_config)
        view_summaries = self._summarise_dashboard_views(dashboard_config)

        self._dashboards[dashboard_url] = {
            "url": dashboard_url,
            "title": title,
            "path": path,
            "created": dt_util.utcnow().isoformat(),
            "type": "main",
            "dogs": [dog[CONF_DOG_ID] for dog in typed_dogs],
            "options": options,
            "entry_id": self.entry.entry_id,
            "version": DASHBOARD_STORAGE_VERSION,
            "performance": {
                "generation_time": self._monotonic_time(),
                "entity_count": sum(
                    len(self._ensure_modules_config(dog)) for dog in typed_dogs
                ),
            },
            "views": view_summaries,
            "has_notifications_view": self._has_notifications_view(view_summaries),
        }

        await self._save_dashboard_metadata_async()

    async def async_create_dog_dashboard(
        self,
        dog_config: RawDogConfig,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Create optimized dog dashboard with performance tracking."""
        if not self._initialized:
            await self.async_initialize()

        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            raise ValueError("Dog configuration is invalid")

        dog_config = typed_dog
        dog_id = dog_config[CONF_DOG_ID]
        dog_name = dog_config[CONF_DOG_NAME]

        if not dog_id or not dog_name:
            raise ValueError("Dog ID and name are required")

        options = options or {}
        start_time = self._monotonic_time()

        async with self._operation_semaphore:
            try:
                # OPTIMIZED: Concurrent rendering and URL generation
                render_task = self._track_task(
                    self._renderer.render_dog_dashboard(dog_config, options),
                    name=f"pawcontrol_dashboard_render_dog_{slugify(dog_id)}",
                )

                dashboard_url = f"paw-{slugify(dog_id)}"
                dashboard_title = f"🐕 {dog_name}"

                dashboard_config = await render_task

                # OPTIMIZED: Async file operations
                dashboard_path = await self._create_dashboard_file_async(
                    dashboard_url,
                    dashboard_title,
                    dashboard_config,
                    "mdi:dog-side",
                    options.get("show_in_sidebar", False),
                )

                # Store metadata
                view_summaries = self._summarise_dashboard_views(dashboard_config)

                async with self._lock:
                    self._dashboards[dashboard_url] = {
                        "url": dashboard_url,
                        "title": dashboard_title,
                        "path": str(dashboard_path),
                        "created": dt_util.utcnow().isoformat(),
                        "type": "dog",
                        "dog_id": dog_id,
                        "dog_name": dog_name,
                        "options": options,
                        "entry_id": self.entry.entry_id,
                        "version": DASHBOARD_STORAGE_VERSION,
                        "views": view_summaries,
                        "has_notifications_view": self._has_notifications_view(
                            view_summaries
                        ),
                    }

                    await self._save_dashboard_metadata_async()

                generation_time = self._monotonic_time() - start_time
                await self._update_performance_metrics(
                    "dog_generation", generation_time
                )

                _LOGGER.info(
                    "Created dog dashboard for '%s' at /%s", dog_name, dashboard_url
                )

                return f"/{dashboard_url}"

            except Exception as err:
                self._performance_metrics["errors"] += 1
                _LOGGER.error(
                    "Dog dashboard creation failed for %s: %s",
                    dog_name,
                    err,
                    exc_info=True,
                )
                raise HomeAssistantError(
                    f"Dog dashboard creation failed: {err}"
                ) from err

    async def async_update_dashboard(
        self,
        dashboard_url: str,
        dogs_config: Sequence[RawDogConfig],
        options: dict[str, Any] | None = None,
    ) -> bool:
        """Update dashboard with optimized async operations."""
        if not self._initialized:
            await self.async_initialize()

        if dashboard_url not in self._dashboards:
            _LOGGER.warning("Dashboard %s not found for update", dashboard_url)
            return False

        dashboard_info = self._dashboards[dashboard_url]
        start_time = self._monotonic_time()

        async with self._operation_semaphore:
            try:
                dashboard_type = dashboard_info.get("type", "main")
                stored_options = dashboard_info.get("options", {})
                options_merged = {**(options or {}), **stored_options}

                if dashboard_type == "main":
                    dashboard_config = await self._renderer.render_main_dashboard(
                        dogs_config, options_merged
                    )

                    if self._has_weather_module(dogs_config):
                        await self._add_weather_components_to_dashboard(
                            dashboard_config, dogs_config, options_merged
                        )

                elif dashboard_type == "dog":
                    dog_id = dashboard_info.get("dog_id")
                    dog_config = next(
                        (d for d in dogs_config if d.get(CONF_DOG_ID) == dog_id), None
                    )
                    if not dog_config:
                        _LOGGER.warning("Dog %s not found for update", dog_id)
                        return False

                    dashboard_config = await self._renderer.render_dog_dashboard(
                        dog_config, options_merged
                    )

                    if self._has_weather_module([dog_config]):
                        await self._add_weather_components_to_dog_dashboard(
                            dashboard_config, dog_config, options_merged
                        )

                elif dashboard_type == "weather":
                    dog_id = dashboard_info.get("dog_id")
                    dog_name = dashboard_info.get("dog_name")
                    if not dog_id or not dog_name:
                        _LOGGER.warning(
                            "Weather dashboard %s is missing dog metadata",
                            dashboard_url,
                        )
                        return False

                    dog_config = next(
                        (d for d in dogs_config if d.get(CONF_DOG_ID) == dog_id), None
                    )
                    breed = (
                        dog_config.get("breed")
                        if isinstance(dog_config, Mapping)
                        else dashboard_info.get("breed", "Mixed")
                    )
                    theme = options_merged.get(
                        "theme", dashboard_info.get("theme", "modern")
                    )
                    layout = options_merged.get(
                        "layout", dashboard_info.get("layout", "full")
                    )

                    weather_layout = await self._dashboard_templates.get_weather_dashboard_layout_template(
                        dog_id, dog_name, breed, theme, layout
                    )
                    dashboard_config = {
                        "views": [
                            {
                                "title": f"🌤️ {dog_name} Weather",
                                "icon": "mdi:weather-partly-cloudy",
                                "path": "weather",
                                "type": "panel",
                                "cards": [weather_layout],
                            }
                        ]
                    }

                    dashboard_info["theme"] = theme
                    dashboard_info["layout"] = layout

                else:
                    _LOGGER.warning(
                        "Unsupported dashboard type %s for %s",
                        dashboard_type,
                        dashboard_url,
                    )
                    return False

                # OPTIMIZED: Async file update
                dashboard_path = Path(dashboard_info["path"])
                await self._update_dashboard_file_async(
                    dashboard_path, dashboard_config, dashboard_info
                )

                # Update metadata
                view_summaries = self._summarise_dashboard_views(dashboard_config)

                async with self._lock:
                    dashboard_info["updated"] = dt_util.utcnow().isoformat()
                    dashboard_info["views"] = view_summaries
                    dashboard_info["has_notifications_view"] = (
                        self._has_notifications_view(view_summaries)
                    )

                    if options is not None:
                        dashboard_info["options"] = options_merged

                    await self._save_dashboard_metadata_async()

                update_time = self._monotonic_time() - start_time
                await self._update_performance_metrics("update", update_time)

                _LOGGER.info(
                    "Updated dashboard %s in %.2fs", dashboard_url, update_time
                )
                return True

            except Exception as err:
                self._performance_metrics["errors"] += 1
                _LOGGER.error(
                    "Dashboard update failed for %s: %s",
                    dashboard_url,
                    err,
                    exc_info=True,
                )
                return False

    async def _update_dashboard_file_async(
        self,
        dashboard_path: Path,
        dashboard_config: dict[str, Any],
        dashboard_info: dict[str, Any],
    ) -> None:
        """Update dashboard file with async operations."""
        dashboard_data = {
            "data": {
                "config": {
                    "title": dashboard_info["title"],
                    "icon": dashboard_info.get("icon", DEFAULT_DASHBOARD_ICON),
                    "path": dashboard_info["url"],
                    "require_admin": False,
                    "show_in_sidebar": dashboard_info.get("show_in_sidebar", True),
                    "views": dashboard_config.get("views", []),
                    "updated": dt_util.utcnow().isoformat(),
                }
            }
        }

        try:
            async with aiofiles.open(dashboard_path, "w", encoding="utf-8") as f:
                json_str = json.dumps(dashboard_data, indent=2, ensure_ascii=False)
                await f.write(json_str)

            self._performance_metrics["file_operations"] += 1

        except Exception as err:
            raise HomeAssistantError(f"Dashboard file update failed: {err}") from err

    async def async_delete_dashboard(self, dashboard_url: str) -> bool:
        """Delete dashboard with optimized cleanup."""
        if dashboard_url not in self._dashboards:
            _LOGGER.warning("Dashboard %s not found for deletion", dashboard_url)
            return False

        async with self._lock:
            try:
                dashboard_info = self._dashboards[dashboard_url]
                dashboard_path = Path(dashboard_info["path"])

                # OPTIMIZED: Async file deletion
                await asyncio.to_thread(dashboard_path.unlink, missing_ok=True)

                # Remove from registry
                del self._dashboards[dashboard_url]
                await self._save_dashboard_metadata_async()

                _LOGGER.info("Deleted dashboard %s", dashboard_url)
                return True

            except Exception as err:
                self._performance_metrics["errors"] += 1
                _LOGGER.error(
                    "Dashboard deletion failed for %s: %s",
                    dashboard_url,
                    err,
                    exc_info=True,
                )
                return False

    async def async_batch_update_dashboards(
        self,
        updates: list[tuple[str, list[dict[str, Any]], dict[str, Any] | None]],
    ) -> dict[str, bool]:
        """OPTIMIZED: Batch update multiple dashboards for better performance."""
        if not self._initialized:
            await self.async_initialize()

        results = {}
        start_time = self._monotonic_time()

        # OPTIMIZED: Process updates in controlled batches
        batch_size = MAX_CONCURRENT_DASHBOARD_OPERATIONS
        for i in range(0, len(updates), batch_size):
            batch = updates[i : i + batch_size]

            # Process batch concurrently
            batch_tasks = [
                self._track_task(
                    self.async_update_dashboard(url, dogs_config, options),
                    name=f"pawcontrol_dashboard_update_{slugify(url)}",
                )
                for url, dogs_config, options in batch
            ]

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Process results
            for (url, _, _), result in zip(batch, batch_results, strict=False):
                resolved = _unwrap_async_result(
                    result,
                    context=f"Batch update failed for {url}",
                    level=logging.ERROR,
                )
                if resolved is None:
                    results[url] = False
                    continue
                results[url] = resolved

        batch_time = self._monotonic_time() - start_time
        _LOGGER.info("Batch updated %d dashboards in %.2fs", len(updates), batch_time)

        return results

    async def _save_dashboard_metadata_async(self) -> None:
        """Save metadata with async operations and error recovery."""
        try:
            metadata = {
                "dashboards": self._dashboards,
                "updated": dt_util.utcnow().isoformat(),
                "version": DASHBOARD_STORAGE_VERSION,
                "entry_id": self.entry.entry_id,
                "performance_metrics": self._performance_metrics.copy(),
            }

            await self._store.async_save(metadata)

        except Exception as err:
            _LOGGER.error("Dashboard metadata save failed: %s", err, exc_info=True)
            # Don't raise - metadata save failure shouldn't break dashboard creation

    async def _update_performance_metrics(
        self, operation_type: str, duration: float
    ) -> None:
        """Update performance metrics with new operation data."""
        self._performance_metrics["total_generations"] += 1

        # Update rolling average
        current_avg = self._performance_metrics["avg_generation_time"]
        count = self._performance_metrics["total_generations"]

        self._performance_metrics["avg_generation_time"] = (
            current_avg * (count - 1) + duration
        ) / count

        # Log slow operations
        if duration > PERFORMANCE_LOG_THRESHOLD:
            _LOGGER.info(
                "Slow dashboard %s: %.2fs (avg: %.2fs)",
                operation_type,
                duration,
                self._performance_metrics["avg_generation_time"],
            )

    async def _cleanup_failed_dashboard(self, dashboard_url: str) -> None:
        """Cleanup failed dashboard creation."""
        try:
            # Remove from registry if exists
            self._dashboards.pop(dashboard_url, None)

            # Try to remove file
            storage_dir = Path(self.hass.config.path(".storage"))
            dashboard_file = storage_dir / f"lovelace.{dashboard_url}"
            await asyncio.to_thread(dashboard_file.unlink, missing_ok=True)

        except Exception as err:
            _LOGGER.debug("Error during dashboard cleanup: %s", err)

    async def async_cleanup(self) -> None:
        """Enhanced cleanup with resource management."""
        _LOGGER.info("Cleaning up dashboards for entry %s", self.entry.entry_id)

        # OPTIMIZED: Cancel any running cleanup tasks
        for task in self._cleanup_tasks.copy():
            if not task.done():
                task.cancel()

        # Wait for cancellation
        if self._cleanup_tasks:
            cancellation_results = await asyncio.gather(
                *self._cleanup_tasks,
                return_exceptions=True,
            )
            for result in cancellation_results:
                _unwrap_async_result(
                    result,
                    context="Cleanup task finalisation",
                    level=logging.DEBUG,
                    suppress_cancelled=True,
                )
            self._cleanup_tasks.clear()

        async with self._lock:
            # OPTIMIZED: Concurrent file cleanup
            cleanup_jobs: list[tuple[str, Awaitable[Any]]] = []
            for dashboard_info in self._dashboards.values():
                try:
                    dashboard_path = Path(dashboard_info["path"])
                    cleanup_jobs.append(
                        (
                            str(dashboard_path),
                            asyncio.to_thread(dashboard_path.unlink, missing_ok=True),
                        )
                    )
                except Exception as err:
                    _LOGGER.warning("Error preparing dashboard cleanup: %s", err)

            # Execute cleanup concurrently
            if cleanup_jobs:
                cleanup_results = await asyncio.gather(
                    *(job for _, job in cleanup_jobs),
                    return_exceptions=True,
                )
                for (path, _), result in zip(
                    cleanup_jobs, cleanup_results, strict=False
                ):
                    _unwrap_async_result(
                        result,
                        context=f"Dashboard file cleanup failed for {path}",
                        level=logging.DEBUG,
                        suppress_cancelled=True,
                    )

            # Remove storage
            try:
                await self._store.async_remove()
            except Exception as err:
                _LOGGER.warning("Error removing dashboard storage: %s", err)

            self._dashboards.clear()

        # Clean up renderer and templates
        if hasattr(self, "_renderer"):
            await self._renderer.cleanup()

        if hasattr(self, "_dashboard_templates"):
            await self._dashboard_templates.cleanup()

    async def _dashboard_templates_async_initialize(self) -> None:
        """Async initialize dashboard templates if method exists."""
        # Handle case where dashboard templates might not have async_initialize
        if hasattr(self._dashboard_templates, "async_initialize"):
            await self._dashboard_templates.async_initialize()
        # Templates are ready to use immediately

        _LOGGER.info("Dashboard generator cleanup completed")

    async def _validate_stored_dashboards(self) -> None:
        """Validate stored dashboards with async operations."""
        if not self._dashboards:
            return

        invalid_dashboards: list[str] = []
        validation_tasks = []
        metadata_updated = False

        # OPTIMIZED: Prepare validation tasks
        for url, dashboard_info in self._dashboards.items():
            validation_tasks.append(
                self._validate_single_dashboard(url, dashboard_info)
            )

        # Execute validations concurrently
        validation_results = await asyncio.gather(
            *validation_tasks, return_exceptions=True
        )

        # Process results
        for (url, dashboard_info), result in zip(  # noqa: B007
            self._dashboards.items(), validation_results, strict=False
        ):
            resolved = _unwrap_async_result(
                result,
                context=f"Error validating dashboard {url}",
            )

            if resolved is None:
                invalid_dashboards.append(url)
                continue

            if isinstance(resolved, tuple):
                valid, changed = resolved
            else:
                valid, changed = (bool(resolved), False)

            if not valid:
                invalid_dashboards.append(url)
                continue

            if changed:
                metadata_updated = True

        # Remove invalid dashboards
        for url in invalid_dashboards:
            _LOGGER.info("Removing invalid dashboard: %s", url)
            self._dashboards.pop(url, None)
            metadata_updated = True

        if metadata_updated:
            await self._save_dashboard_metadata_async()

    async def _validate_single_dashboard(
        self, url: str, dashboard_info: dict[str, Any]
    ) -> tuple[bool, bool]:
        """Validate single dashboard asynchronously."""

        metadata_updated = False

        try:
            dashboard_path = dashboard_info.get("path")
            if not dashboard_path:
                return (False, metadata_updated)

            path_obj = Path(dashboard_path)
            exists = await asyncio.to_thread(path_obj.exists)
            if not exists:
                return (False, metadata_updated)

            required_fields = ["title", "created", "type"]
            if not all(field in dashboard_info for field in required_fields):
                return (False, metadata_updated)

            stored_version = dashboard_info.get("version", 1)
            if stored_version < DASHBOARD_STORAGE_VERSION:
                _LOGGER.info(
                    "Dashboard %s has old version %d, needs regeneration",
                    url,
                    stored_version,
                )
                dashboard_info["needs_regeneration"] = True
                metadata_updated = True

            view_summaries = self._normalize_view_summaries(dashboard_info.get("views"))
            if view_summaries is None:
                config = await self._load_dashboard_config(path_obj)
                config_mapping: Mapping[str, Any] = (
                    config if config is not None else {"views": []}
                )
                view_summaries = self._summarise_dashboard_views(config_mapping)
                dashboard_info["views"] = view_summaries
                metadata_updated = True
            elif dashboard_info.get("views") != view_summaries:
                dashboard_info["views"] = view_summaries
                metadata_updated = True

            notifications_view = self._has_notifications_view(view_summaries)
            stored_notifications = dashboard_info.get("has_notifications_view")
            if stored_notifications is not notifications_view:
                dashboard_info["has_notifications_view"] = notifications_view
                metadata_updated = True

            return (True, metadata_updated)

        except Exception as err:
            _LOGGER.warning("Dashboard validation error for %s: %s", url, err)
            return (False, metadata_updated)

    # OPTIMIZED: Enhanced callback methods with performance data
    @callback
    def get_dashboard_info(self, dashboard_url: str) -> dict[str, Any] | None:
        """Get dashboard information with performance data."""
        info = self._dashboards.get(dashboard_url)
        if info:
            info = info.copy()
            info["performance_metrics"] = self._get_dashboard_performance_metrics()
        return info

    @callback
    def get_all_dashboards(self) -> dict[str, dict[str, Any]]:
        """Get all dashboards with enhanced metadata."""
        dashboards = self._dashboards.copy()
        performance_data = self._get_dashboard_performance_metrics()

        for dashboard_info in dashboards.values():
            dashboard_info["system_performance"] = performance_data

        return dashboards

    @callback
    def is_initialized(self) -> bool:
        """Check initialization status."""
        return self._initialized

    @callback
    def get_performance_stats(self) -> dict[str, Any]:
        """Get comprehensive performance statistics."""
        base_stats = {
            "dashboards_count": len(self._dashboards),
            "initialized": self._initialized,
            "storage_version": DASHBOARD_STORAGE_VERSION,
            "metrics": self._performance_metrics.copy(),
        }

        # Add renderer stats if available
        if hasattr(self, "_renderer") and self._renderer:
            try:
                render_stats = self._renderer.get_render_stats()
                base_stats["renderer"] = render_stats
            except Exception as err:
                _LOGGER.debug("Error getting renderer stats: %s", err)

        return base_stats

    def _get_dashboard_performance_metrics(self) -> dict[str, Any]:
        """Get current performance metrics."""
        return {
            "avg_generation_time": self._performance_metrics["avg_generation_time"],
            "total_operations": self._performance_metrics["total_generations"],
            "error_rate": (
                self._performance_metrics["errors"]
                / max(self._performance_metrics["total_generations"], 1)
            )
            * 100,
            "cache_efficiency": (
                self._performance_metrics["cache_hits"]
                / max(
                    self._performance_metrics["cache_hits"]
                    + self._performance_metrics["cache_misses"],
                    1,
                )
            )
            * 100,
        }

    async def async_create_weather_dashboard(
        self,
        dog_config: RawDogConfig,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Create dedicated weather dashboard for a dog.

        Args:
            dog_config: Dog configuration
            options: Dashboard options

        Returns:
            Dashboard URL path

        Raises:
            ValueError: If dog config is invalid
            HomeAssistantError: If dashboard creation fails
        """
        if not self._initialized:
            await self.async_initialize()

        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            raise ValueError("Dog configuration is invalid")

        dog_id = typed_dog.get(CONF_DOG_ID)
        dog_name = typed_dog.get(CONF_DOG_NAME)
        breed = typed_dog.get("breed", "Mixed")

        if not dog_id or not dog_name:
            raise ValueError("Dog ID and name are required")

        modules = self._ensure_modules_config(typed_dog)
        if not modules.get(MODULE_WEATHER, False):
            raise ValueError(f"Weather module not enabled for {dog_name}")

        options = options or {}
        start_time = self._monotonic_time()

        async with self._operation_semaphore:
            try:
                # Generate weather dashboard configuration
                theme = options.get("theme", "modern")
                layout = options.get("layout", "full")

                weather_config = await self._dashboard_templates.get_weather_dashboard_layout_template(
                    dog_id, dog_name, breed, theme, layout
                )

                # Create dashboard structure
                dashboard_config = {
                    "views": [
                        {
                            "title": f"🌤️ {dog_name} Weather",
                            "icon": "mdi:weather-partly-cloudy",
                            "path": "weather",
                            "type": "panel",
                            "cards": [weather_config],
                        }
                    ]
                }

                # Generate unique URL
                dashboard_url = f"paw-weather-{slugify(dog_id)}"
                dashboard_title = f"🌤️ {dog_name} Weather"

                # Create dashboard file
                dashboard_path = await self._create_dashboard_file_async(
                    dashboard_url,
                    dashboard_title,
                    dashboard_config,
                    "mdi:weather-partly-cloudy",
                    options.get("show_in_sidebar", False),
                )

                # Store metadata
                view_summaries = self._summarise_dashboard_views(dashboard_config)

                async with self._lock:
                    self._dashboards[dashboard_url] = {
                        "url": dashboard_url,
                        "title": dashboard_title,
                        "path": str(dashboard_path),
                        "created": dt_util.utcnow().isoformat(),
                        "type": "weather",
                        "dog_id": dog_id,
                        "dog_name": dog_name,
                        "breed": breed,
                        "theme": theme,
                        "layout": layout,
                        "options": options,
                        "entry_id": self.entry.entry_id,
                        "version": DASHBOARD_STORAGE_VERSION,
                        "weather_features": {
                            "health_monitoring": True,
                            "breed_specific": True,
                            "interactive_charts": True,
                            "recommendations": True,
                        },
                        "views": view_summaries,
                        "has_notifications_view": self._has_notifications_view(
                            view_summaries
                        ),
                    }

                    await self._save_dashboard_metadata_async()

                generation_time = self._monotonic_time() - start_time
                await self._update_performance_metrics(
                    "weather_generation", generation_time
                )

                _LOGGER.info(
                    "Created weather dashboard for '%s' at /%s (theme: %s, layout: %s)",
                    dog_name,
                    dashboard_url,
                    theme,
                    layout,
                )

                return f"/{dashboard_url}"

            except Exception as err:
                self._performance_metrics["errors"] += 1
                _LOGGER.error(
                    "Weather dashboard creation failed for %s: %s",
                    dog_name,
                    err,
                    exc_info=True,
                )
                raise HomeAssistantError(
                    f"Weather dashboard creation failed: {err}"
                ) from err

    def _has_weather_module(self, dogs_config: Sequence[RawDogConfig]) -> bool:
        """Check if any dog has weather module enabled.

        Args:
            dogs_config: List of dog configurations

        Returns:
            True if weather module is enabled for any dog
        """
        for dog in self._ensure_dog_configs(dogs_config):
            modules = self._ensure_modules_config(dog)
            if modules.get(MODULE_WEATHER, False):
                return True
        return False

    async def _add_weather_components_to_dashboard(
        self,
        dashboard_config: dict[str, Any],
        dogs_config: Sequence[RawDogConfig],
        options: dict[str, Any],
    ) -> None:
        """Add weather components to main dashboard.

        Args:
            dashboard_config: Dashboard configuration to modify
            dogs_config: List of dog configurations
            options: Dashboard options
        """
        typed_dogs = self._ensure_dog_configs(dogs_config)
        theme = options.get("theme", "modern")
        views = dashboard_config.setdefault("views", [])

        # Create weather overview view for all dogs with weather enabled
        weather_dogs: list[DogConfigData] = []
        for dog in typed_dogs:
            modules = self._ensure_modules_config(dog)
            if modules.get(MODULE_WEATHER, False):
                weather_dogs.append(dog)

        if not weather_dogs:
            return

        # Weather overview cards
        weather_cards = []

        for dog in weather_dogs:
            dog_id = dog.get(CONF_DOG_ID)
            dog_name = dog.get(CONF_DOG_NAME)

            if not dog_id or not dog_name:
                continue

            # Add compact weather status card for each dog
            weather_status = (
                await self._dashboard_templates.get_weather_status_card_template(
                    dog_id, dog_name, theme, compact=True
                )
            )
            weather_cards.append(weather_status)

        # Group weather cards
        if weather_cards:
            if len(weather_cards) == 1:
                weather_view_cards = weather_cards
            elif len(weather_cards) <= 4:
                # Horizontal layout for 2-4 dogs
                weather_view_cards = [
                    {
                        "type": "horizontal-stack",
                        "cards": weather_cards,
                    }
                ]
            else:
                # Grid layout for 5+ dogs
                weather_view_cards = [
                    {
                        "type": "grid",
                        "columns": 3,
                        "cards": weather_cards,
                    }
                ]

            # Add weather overview view
            weather_view = {
                "title": "🌤️ Weather Overview",
                "icon": "mdi:weather-partly-cloudy",
                "path": "weather-overview",
                "cards": weather_view_cards,
            }

            views.append(weather_view)

            _LOGGER.debug(
                "Added weather overview to main dashboard with %d dogs",
                len(weather_dogs),
            )

    async def _add_weather_components_to_dog_dashboard(
        self,
        dashboard_config: dict[str, Any],
        dog_config: RawDogConfig,
        options: dict[str, Any],
    ) -> None:
        """Add weather components to individual dog dashboard.

        Args:
            dashboard_config: Dashboard configuration to modify
            dog_config: Dog configuration
            options: Dashboard options
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return

        dog_config = typed_dog
        dog_id = dog_config.get(CONF_DOG_ID)
        dog_name = dog_config.get(CONF_DOG_NAME)
        breed = dog_config.get("breed", "Mixed")
        theme = options.get("theme", "modern")

        if not dog_id or not dog_name:
            return

        views = dashboard_config.setdefault("views", [])

        # Create comprehensive weather view for this dog
        weather_layout = (
            await self._dashboard_templates.get_weather_dashboard_layout_template(
                dog_id, dog_name, breed, theme, "compact"
            )
        )

        weather_view = {
            "title": "🌤️ Weather",
            "icon": "mdi:weather-partly-cloudy",
            "path": "weather",
            "cards": [weather_layout],
        }

        views.append(weather_view)

        # Also add weather status to overview if it exists
        overview_view = next(
            (view for view in views if view.get("path") == "overview"), None
        )

        if overview_view:
            overview_cards = overview_view.setdefault("cards", [])

            # Add weather status card to overview
            weather_status = (
                await self._dashboard_templates.get_weather_status_card_template(
                    dog_id, dog_name, theme, compact=True
                )
            )

            # Insert weather card after existing status cards
            insert_index = min(2, len(overview_cards))  # Insert at position 2 or end
            overview_cards.insert(insert_index, weather_status)

        _LOGGER.debug(
            "Added weather components to %s dashboard (breed: %s, theme: %s)",
            dog_name,
            breed,
            theme,
        )

    async def async_batch_create_weather_dashboards(
        self,
        dogs_config: Sequence[RawDogConfig],
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Create weather dashboards for multiple dogs in batch.

        Args:
            dogs_config: List of dog configurations
            options: Dashboard options

        Returns:
            Dictionary mapping dog_id to dashboard URL
        """
        if not self._initialized:
            await self.async_initialize()

        # Filter dogs with weather module enabled
        typed_dogs = self._ensure_dog_configs(dogs_config)
        weather_dogs: list[DogConfigData] = []
        for dog in typed_dogs:
            modules = self._ensure_modules_config(dog)
            if modules.get(MODULE_WEATHER, False):
                weather_dogs.append(dog)

        if not weather_dogs:
            _LOGGER.info("No dogs with weather module enabled")
            return {}

        options = options or {}
        results = {}
        start_time = self._monotonic_time()

        # Process in batches to avoid overwhelming the system
        batch_size = MAX_CONCURRENT_DASHBOARD_OPERATIONS
        for i in range(0, len(weather_dogs), batch_size):
            batch = weather_dogs[i : i + batch_size]

            # Create batch tasks
            batch_tasks = [
                self._track_task(
                    self.async_create_weather_dashboard(dog, options),
                    name=f"pawcontrol_dashboard_weather_{dog.get(CONF_DOG_ID, 'unknown')}",
                )
                for dog in batch
            ]

            # Execute batch
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Process results
            for dog, result in zip(batch, batch_results, strict=False):
                dog_id = dog.get(CONF_DOG_ID)
                if not dog_id:
                    continue

                resolved = _unwrap_async_result(
                    result,
                    context=f"Weather dashboard creation failed for {dog_id}",
                    level=logging.ERROR,
                )
                if resolved is None:
                    error_message = (
                        str(result)
                        if isinstance(result, Exception)
                        else "unknown error"
                    )
                    results[dog_id] = f"Error: {error_message}"
                    continue

                results[dog_id] = resolved

        batch_time = self._monotonic_time() - start_time
        _LOGGER.info(
            "Batch created %d weather dashboards in %.2fs",
            len([r for r in results.values() if not r.startswith("Error:")]),
            batch_time,
        )

        return results

    @callback
    def get_weather_dashboards(self) -> dict[str, dict[str, Any]]:
        """Get all weather dashboards.

        Returns:
            Dictionary of weather dashboard information
        """
        return {
            url: info
            for url, info in self._dashboards.items()
            if info.get("type") == "weather"
        }

    @callback
    def has_weather_dashboard(self, dog_id: str) -> bool:
        """Check if weather dashboard exists for dog.

        Args:
            dog_id: Dog identifier

        Returns:
            True if weather dashboard exists
        """
        for dashboard_info in self._dashboards.values():
            if (
                dashboard_info.get("type") == "weather"
                and dashboard_info.get("dog_id") == dog_id
            ):
                return True
        return False


_unwrap_async_result = partial(unwrap_async_result, logger=_LOGGER)
# Typed dog configuration input accepted by the generator is provided via the
# shared ``RawDogConfig`` alias imported from ``types``.
