"""Runtime-heavy coverage tests for ``dashboard_generator.py``."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
import json
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol import dashboard_generator as dg
from custom_components.pawcontrol.const import MODULE_NOTIFICATIONS, MODULE_WEATHER
from custom_components.pawcontrol.dashboard_generator import (
    PawControlDashboardGenerator,
)
from custom_components.pawcontrol.types import (
    DOG_BREED_FIELD,
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
)

pytestmark = pytest.mark.unit


def _metrics_payload() -> dg.DashboardPerformanceMetrics:
    """Return a fresh baseline metrics dictionary for generator tests."""
    return {
        "total_generations": 0,
        "avg_generation_time": 0.0,
        "cache_hits": 0,
        "cache_misses": 0,
        "file_operations": 0,
        "errors": 0,
    }


def _local_workspace_tmp_dir() -> Path:
    """Create and return an isolated workspace-local temporary directory."""
    root = Path("dashboard_runtime_tmp").resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = root / f"dashboard-generator-{time.time_ns()}"
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def _dog(
    dog_id: str,
    dog_name: str,
    *,
    breed: str | None = None,
    weather: bool = False,
    notifications: bool = False,
) -> dict[str, Any]:
    """Return a valid raw dog configuration used by dashboard tests."""
    modules: dict[str, bool] = {
        "feeding": True,
        "walk": True,
        MODULE_WEATHER: weather,
        MODULE_NOTIFICATIONS: notifications,
    }
    payload: dict[str, Any] = {
        DOG_ID_FIELD: dog_id,
        DOG_NAME_FIELD: dog_name,
        DOG_MODULES_FIELD: modules,
    }
    if breed is not None:
        payload[DOG_BREED_FIELD] = breed
    return payload


class _StoreStub:
    """Storage stub exposing async methods consumed by the generator."""

    def __init__(self, load_payload: Any = None) -> None:
        self.async_load = AsyncMock(return_value=load_payload)
        self.async_save = AsyncMock(return_value=None)
        self.async_remove = AsyncMock(return_value=None)


class _RendererStub:
    """Renderer stub with async hooks and deterministic payloads."""

    def __init__(self) -> None:
        self.async_initialize = AsyncMock(return_value=None)
        self.cleanup = AsyncMock(return_value=None)
        self.render_main_dashboard = AsyncMock(
            return_value={
                "views": [
                    {
                        "title": "Overview",
                        "icon": "mdi:home",
                        "path": "overview",
                        "cards": [{"type": "entities"}],
                    },
                ]
            }
        )
        self.render_dog_dashboard = AsyncMock(
            return_value={
                "views": [
                    {
                        "title": "Overview",
                        "icon": "mdi:home",
                        "path": "overview",
                        "cards": [{"type": "entities"}],
                    },
                ]
            }
        )
        self.get_render_stats = MagicMock(return_value={"jobs": 1})


class _TemplatesStub:
    """Weather template stub used for weather dashboard branches."""

    def __init__(self) -> None:
        self.async_initialize = AsyncMock(return_value=None)
        self.cleanup = AsyncMock(return_value=None)
        self.get_weather_dashboard_layout_template = AsyncMock(
            return_value={
                "type": "vertical-stack",
                "cards": [{"type": "markdown", "content": "weather"}],
            }
        )
        self.get_weather_status_card_template = AsyncMock(
            return_value={"type": "sensor", "entity": "sensor.weather_status"}
        )


def _configure_hass_for_files(hass: Any, base_dir: Path) -> None:
    """Configure Home Assistant stub paths and executor behavior for file IO."""
    storage_root = base_dir / ".storage"
    storage_root.mkdir(parents=True, exist_ok=True)
    hass.config = SimpleNamespace(
        path=lambda *parts: str(base_dir.joinpath(*parts)),
        language="en",
    )

    async def _run_in_executor(
        func: Callable[..., Any],
        *args: Any,
    ) -> Any:
        return func(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=_run_in_executor)
    if not hasattr(hass, "async_create_task"):
        hass.async_create_task = lambda awaitable, *, name=None: asyncio.create_task(  # type: ignore[assignment]
            awaitable,
            name=name,
        )
    hass.loop = asyncio.get_running_loop()


def _build_generator(
    hass: Any,
    entry: Any,
    base_dir: Path,
    *,
    initialized: bool = True,
    load_payload: Any = None,
) -> PawControlDashboardGenerator:
    """Construct a generator instance without invoking ``__init__``."""
    _configure_hass_for_files(hass, base_dir)
    generator = object.__new__(PawControlDashboardGenerator)
    generator.hass = hass
    generator.entry = entry
    generator._store = _StoreStub(load_payload)
    generator._renderer = _RendererStub()
    generator._dashboard_templates = _TemplatesStub()
    generator._dashboards = {}
    generator._initialized = initialized
    generator._lock = asyncio.Lock()
    generator._operation_semaphore = asyncio.Semaphore(
        dg.MAX_CONCURRENT_DASHBOARD_OPERATIONS,
    )
    generator._performance_metrics = _metrics_payload()
    generator._cleanup_tasks = set()
    return generator


@pytest.fixture
def local_tmp_dir() -> Path:
    """Yield and cleanup a workspace-local temporary test directory."""
    directory = _local_workspace_tmp_dir()
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_runtime_helper_paths_cover_runtime_resolution_and_coercions(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise runtime-data, coercion, and static helper branches."""
    entry = config_entry_factory(entry_id="coverage-entry-helpers")
    generator = object.__new__(PawControlDashboardGenerator)
    generator.hass = hass
    generator.entry = entry

    runtime_instance = object.__new__(dg.PawControlRuntimeData)
    entry.runtime_data = runtime_instance
    assert generator._get_runtime_data() is runtime_instance

    entry.runtime_data = object()
    fallback_instance = object.__new__(dg.PawControlRuntimeData)
    monkeypatch.setattr(
        dg,
        "get_runtime_data",
        lambda hass_obj, entry_obj: fallback_instance,
    )
    assert generator._get_runtime_data() is fallback_instance

    monkeypatch.setattr(dg, "get_runtime_data", lambda hass_obj, entry_obj: object())
    assert generator._get_runtime_data() is None

    generator._get_runtime_data = lambda: None  # type: ignore[method-assign]
    assert generator._resolve_coordinator_statistics() is None
    assert generator._resolve_service_execution_metrics() is None
    assert generator._resolve_service_guard_metrics() is None

    runtime_without_coordinator = SimpleNamespace(coordinator=None)
    generator._get_runtime_data = lambda: runtime_without_coordinator  # type: ignore[method-assign]
    assert generator._resolve_coordinator_statistics() is None

    runtime_with_bad_provider = SimpleNamespace(
        coordinator=SimpleNamespace(get_update_statistics="invalid"),
    )
    generator._get_runtime_data = lambda: runtime_with_bad_provider  # type: ignore[method-assign]
    assert generator._resolve_coordinator_statistics() is None

    runtime_with_stats = SimpleNamespace(
        coordinator=SimpleNamespace(
            get_update_statistics=lambda: {"pipeline": {"jobs": 3}},
        ),
    )
    generator._get_runtime_data = lambda: runtime_with_stats  # type: ignore[method-assign]
    assert generator._resolve_coordinator_statistics() == {"pipeline": {"jobs": 3}}

    runtime_with_non_mapping = SimpleNamespace(
        coordinator=SimpleNamespace(get_update_statistics=lambda: ["raw"]),
    )
    generator._get_runtime_data = lambda: runtime_with_non_mapping  # type: ignore[method-assign]
    assert generator._resolve_coordinator_statistics() == ["raw"]

    runtime_obj = SimpleNamespace()
    generator._get_runtime_data = lambda: runtime_obj  # type: ignore[method-assign]
    monkeypatch.setattr(dg, "get_runtime_performance_stats", lambda _: None)
    assert generator._resolve_service_execution_metrics() is None
    assert generator._resolve_service_guard_metrics() is None

    monkeypatch.setattr(
        dg,
        "get_runtime_performance_stats",
        lambda _: {"rejection_metrics": "bad", "service_guard_metrics": "bad"},
    )
    assert generator._resolve_service_execution_metrics() is None
    assert generator._resolve_service_guard_metrics() is None

    monkeypatch.setattr(
        dg,
        "get_runtime_performance_stats",
        lambda _: {
            "rejection_metrics": {"rejected_call_count": "5"},
            "service_guard_metrics": {
                "executed": "7",
                "skipped": 2,
                "reasons": {"quiet": 1, 2: 9},
                "last_results": [{"domain": "notify", "service": "mobile"}],
            },
        },
    )
    execution_metrics = generator._resolve_service_execution_metrics()
    guard_metrics = generator._resolve_service_guard_metrics()
    assert execution_metrics is not None
    assert int(execution_metrics["rejected_call_count"]) == 5
    assert guard_metrics is not None
    assert guard_metrics["executed"] == 7
    assert guard_metrics["reasons"] == {"quiet": 1}

    monkeypatch.setattr(
        dg,
        "get_runtime_performance_stats",
        lambda _: {
            "service_guard_metrics": {
                "executed": 1,
                "skipped": 0,
                "reasons": ["invalid"],
                "last_results": [],
            },
        },
    )
    guard_metrics_no_reasons = generator._resolve_service_guard_metrics()
    assert guard_metrics_no_reasons is not None
    assert guard_metrics_no_reasons["reasons"] == {}

    ensured = PawControlDashboardGenerator._ensure_dog_config(_dog("alpha", "Alpha"))
    assert ensured is not None
    assert ensured[DOG_ID_FIELD] == "alpha"
    assert ensured[DOG_NAME_FIELD] == "Alpha"
    assert ensured[DOG_MODULES_FIELD]["feeding"] is True
    assert ensured[DOG_MODULES_FIELD]["walk"] is True
    assert PawControlDashboardGenerator._ensure_dog_config("invalid") is None
    typed_dogs = generator._ensure_dog_configs([_dog("a", "A"), "bad", _dog("b", "B")])
    assert [dog[DOG_ID_FIELD] for dog in typed_dogs] == ["a", "b"]

    assert PawControlDashboardGenerator._ensure_modules_config(_dog("m", "M")) == {
        "feeding": True,
        "walk": True,
        MODULE_NOTIFICATIONS: False,
    }
    assert PawControlDashboardGenerator._ensure_modules_config("invalid") == {}

    assert PawControlDashboardGenerator._coerce_int_value(None) == 0
    assert PawControlDashboardGenerator._coerce_int_value(True) == 1
    assert PawControlDashboardGenerator._coerce_int_value(1.8) == 1
    assert PawControlDashboardGenerator._coerce_int_value("2") == 2
    assert PawControlDashboardGenerator._coerce_int_value("2.5") == 2
    assert PawControlDashboardGenerator._coerce_int_value("invalid") == 0
    assert PawControlDashboardGenerator._coerce_int_value(object()) == 0

    assert PawControlDashboardGenerator._coerce_float_value(None) == 0.0
    assert PawControlDashboardGenerator._coerce_float_value(True) == 1.0
    assert PawControlDashboardGenerator._coerce_float_value(3) == 3.0
    assert PawControlDashboardGenerator._coerce_float_value("3.5") == 3.5
    assert PawControlDashboardGenerator._coerce_float_value("invalid") == 0.0
    assert PawControlDashboardGenerator._coerce_float_value(object()) == 0.0

    assert PawControlDashboardGenerator._coerce_performance_metrics(
        {
            "total_generations": "2",
            "avg_generation_time": "1.75",
            "cache_hits": "4",
            "cache_misses": "1",
            "file_operations": "5",
            "errors": "0",
        },
    ) == {
        "total_generations": 2,
        "avg_generation_time": 1.75,
        "cache_hits": 4,
        "cache_misses": 1,
        "file_operations": 5,
        "errors": 0,
    }

    registry = PawControlDashboardGenerator._normalise_dashboard_registry(
        {
            "ok": {"url": "ok"},
            "invalid": "skip",
            1: {"url": "bad-key"},
        },
    )
    assert registry == {"ok": {"url": "ok"}}

    assert isinstance(PawControlDashboardGenerator._monotonic_time(), float)
    monkeypatch.setattr(
        dg.asyncio,
        "get_running_loop",
        MagicMock(side_effect=RuntimeError("no-loop")),
    )
    assert isinstance(PawControlDashboardGenerator._monotonic_time(), float)


def test_runtime_view_normalisation_edge_cases() -> None:
    """Cover summary/normalisation branches for malformed dashboard payloads."""

    class _NonMappingConfig:
        def __getitem__(self, key: str) -> Any:
            if key == "views":
                return ["skip", {"path": "custom", "title": "Custom", "cards": []}]
            raise KeyError(key)

    summaries = PawControlDashboardGenerator._summarise_dashboard_views(
        _NonMappingConfig()
    )
    assert summaries == [
        {
            "path": "custom",
            "title": "Custom",
            "icon": "",
            "card_count": 0,
            "module": "custom",
        },
    ]

    assert PawControlDashboardGenerator._summarise_dashboard_views(
        {"views": [{"path": "overview"}, "skip"]},
    ) == [{"path": "overview", "title": "", "icon": "", "card_count": 0}]

    class _TypeErrorInt(int):
        def __int__(self) -> int:
            raise TypeError("cannot-int")

    normalised = PawControlDashboardGenerator._normalize_view_summaries(
        [
            {
                "path": MODULE_NOTIFICATIONS,
                "title": "Notifications",
                "icon": "mdi:bell",
                "card_count": _TypeErrorInt(1),
                "notifications": False,
            },
            {
                "path": "module-a",
                "title": "A",
                "icon": "mdi:a",
                "card_count": "bad-int",
                "module": "",
            },
        ],
    )
    assert normalised == [
        {
            "path": MODULE_NOTIFICATIONS,
            "title": "Notifications",
            "icon": "mdi:bell",
            "card_count": 0,
            "module": MODULE_NOTIFICATIONS,
            "notifications": False,
        },
        {
            "path": "module-a",
            "title": "A",
            "icon": "mdi:a",
            "card_count": 0,
            "module": "module-a",
        },
    ]


@pytest.mark.asyncio
async def test_runtime_track_task_scheduling_and_error_paths(
    config_entry_factory: Callable[..., Any],
) -> None:
    """Exercise task scheduling fallbacks, unwrap logging, and hard-failure paths."""
    generator = object.__new__(PawControlDashboardGenerator)
    entry = config_entry_factory(entry_id="coverage-track-task")
    generator.entry = entry
    generator._cleanup_tasks = set()

    class _LoopFallback:
        def create_task(
            self, awaitable: Awaitable[Any], name: str | None = None
        ) -> Any:
            if name is not None:
                raise TypeError("no name support")
            return asyncio.create_task(awaitable)

    class _HassFallback:
        loop = _LoopFallback()

        @staticmethod
        def async_create_task(awaitable: Awaitable[Any]) -> None:
            _ = awaitable
            return None

    generator.hass = _HassFallback()

    async def _quick() -> str:
        await asyncio.sleep(0)
        return "ok"

    scheduled = generator._track_task(_quick(), name="fallback-task")
    assert scheduled in generator._cleanup_tasks
    assert await scheduled == "ok"
    await asyncio.sleep(0)
    assert scheduled not in generator._cleanup_tasks

    # Existing task path without a task name
    existing = asyncio.create_task(_quick())
    tracked_existing = generator._track_task(existing)
    assert tracked_existing is existing
    await tracked_existing
    await asyncio.sleep(0)

    # Exception logging path
    unwrap_calls: list[str] = []

    def _capture_unwrap(
        result: Any,
        *,
        context: str,
        level: int = 0,
        suppress_cancelled: bool = False,
        **_: Any,
    ) -> Any:
        _ = result, level, suppress_cancelled
        unwrap_calls.append(context)
        return None

    class _ExplodingTask(asyncio.Task[None]):
        def cancelled(self) -> bool:
            return False

        def exception(self) -> BaseException | None:
            raise asyncio.CancelledError

    async def _raises() -> None:
        raise RuntimeError("boom")

    with patch.object(dg, "_unwrap_async_result", side_effect=_capture_unwrap):
        failing = generator._track_task(
            _raises(), name="failing-task", log_exceptions=True
        )
        with suppress(RuntimeError):
            await failing
        await asyncio.sleep(0)

        strange = _ExplodingTask(_quick(), loop=asyncio.get_running_loop())
        tracked_strange = generator._track_task(strange, name="strange-task")
        await tracked_strange
        await asyncio.sleep(0)

    assert unwrap_calls == ["Unhandled error in failing-task"]

    generator.hass = SimpleNamespace()
    with (
        patch.object(
            dg.asyncio,
            "create_task",
            side_effect=RuntimeError("closed-loop"),
        ),
        pytest.raises(RuntimeError, match="Unable to schedule"),
    ):
        generator._track_task(_quick(), name="runtime-error")

    coro = _quick()
    with (
        patch.object(dg.asyncio, "create_task", return_value=None),
        pytest.raises(RuntimeError, match="Unable to schedule"),
    ):
        generator._track_task(coro, name="none-task")
    coro.close()

    generator.hass = None
    fallback_without_hass = generator._track_task(_quick(), name="no-hass")
    await fallback_without_hass


@pytest.mark.asyncio
async def test_runtime_load_dashboard_config_variants(local_tmp_dir: Path) -> None:
    """Cover file loader branches for valid, invalid, missing, and IO errors."""
    generator = object.__new__(PawControlDashboardGenerator)

    valid_file = local_tmp_dir / "valid.json"
    valid_file.write_text(
        json.dumps({"data": {"config": {"views": [{"path": "overview"}]}}}),
        encoding="utf-8",
    )
    invalid_json = local_tmp_dir / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    non_mapping = local_tmp_dir / "non-mapping.json"
    non_mapping.write_text(json.dumps(["not", "mapping"]), encoding="utf-8")
    missing_config = local_tmp_dir / "missing-config.json"
    missing_config.write_text(json.dumps({"data": {}}), encoding="utf-8")

    assert await generator._load_dashboard_config(valid_file) == {
        "views": [{"path": "overview"}],
    }
    assert await generator._load_dashboard_config(invalid_json) is None
    assert await generator._load_dashboard_config(non_mapping) is None
    assert await generator._load_dashboard_config(missing_config) is None
    assert (
        await generator._load_dashboard_config(local_tmp_dir / "does-not-exist.json")
        is None
    )

    with patch(
        "custom_components.pawcontrol.dashboard_generator.aiofiles.open"
    ) as mocked_open:
        mocked_open.side_effect = OSError("io-failure")
        assert await generator._load_dashboard_config(valid_file) is None


@pytest.mark.asyncio
async def test_runtime_initialization_paths(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover initialize success, timeout cleanup, and generic fallback behavior."""
    entry = config_entry_factory(entry_id="coverage-init-success")
    generator = _build_generator(hass, entry, local_tmp_dir, initialized=False)
    generator._renderer_async_initialize = AsyncMock(return_value=None)
    generator._dashboard_templates_async_initialize = AsyncMock(return_value=None)
    generator._load_stored_data = AsyncMock(return_value=None)

    await generator.async_initialize()
    assert generator._initialized is True
    await generator.async_initialize()
    generator._renderer_async_initialize.assert_awaited_once()

    timeout_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-init-timeout"),
        local_tmp_dir,
        initialized=False,
    )
    timeout_generator._renderer_async_initialize = AsyncMock(return_value=None)
    timeout_generator._dashboard_templates_async_initialize = AsyncMock(
        return_value=None
    )
    timeout_generator._load_stored_data = AsyncMock(return_value=None)
    timeout_generator._cleanup_failed_initialization = AsyncMock(return_value=None)

    with (
        patch.object(
            dg.asyncio,
            "wait_for",
            side_effect=TimeoutError,
        ),
        pytest.raises(HomeAssistantError, match="initialization timeout"),
    ):
        await timeout_generator.async_initialize()
    timeout_generator._cleanup_failed_initialization.assert_awaited_once()

    fallback_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-init-fallback"),
        local_tmp_dir,
        initialized=False,
    )
    fallback_generator._renderer_async_initialize = AsyncMock(
        side_effect=RuntimeError("init-failure"),
    )
    fallback_generator._dashboard_templates_async_initialize = AsyncMock(
        return_value=None
    )
    fallback_generator._load_stored_data = AsyncMock(return_value=None)
    fallback_generator._dashboards = {"kept": {"url": "kept"}}

    await fallback_generator.async_initialize()
    assert fallback_generator._initialized is True
    assert fallback_generator._dashboards == {}


@pytest.mark.asyncio
async def test_runtime_load_store_validation_and_cleanup_paths(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover stored payload loading, timeout/error fallback, and init cleanup."""
    entry = config_entry_factory(entry_id="coverage-load-store")
    load_payload = {
        "dashboards": {"main": {"url": "main", "title": "Main", "path": "p"}},
        "performance_metrics": {
            "total_generations": "4",
            "avg_generation_time": "3.5",
            "cache_hits": "1",
            "cache_misses": "2",
            "file_operations": "7",
            "errors": "0",
        },
    }
    generator = _build_generator(
        hass,
        entry,
        local_tmp_dir,
        initialized=True,
        load_payload=load_payload,
    )
    generator._validate_stored_dashboards = AsyncMock(return_value=None)
    await generator._load_stored_data()
    assert list(generator._dashboards) == ["main"]
    assert generator._performance_metrics["total_generations"] == 4

    non_mapping_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-load-store-nonmap"),
        local_tmp_dir,
        initialized=True,
        load_payload=["invalid"],
    )
    non_mapping_generator._validate_stored_dashboards = AsyncMock(return_value=None)
    await non_mapping_generator._load_stored_data()
    assert non_mapping_generator._dashboards == {}

    timeout_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-load-store-timeout"),
        local_tmp_dir,
        initialized=True,
        load_payload={"dashboards": {}},
    )
    timeout_generator._validate_stored_dashboards = AsyncMock(return_value=None)
    with patch.object(dg.asyncio, "wait_for", side_effect=TimeoutError):
        await timeout_generator._load_stored_data()
    assert timeout_generator._dashboards == {}

    error_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-load-store-error"),
        local_tmp_dir,
        initialized=True,
    )
    error_generator._store.async_load = AsyncMock(
        side_effect=RuntimeError("load-error")
    )
    await error_generator._load_stored_data()
    assert error_generator._dashboards == {}

    cleanup_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-cleanup-failed-init"),
        local_tmp_dir,
        initialized=False,
    )
    cleanup_generator._renderer.cleanup = AsyncMock(
        side_effect=[None, RuntimeError("cleanup-fail")],
    )
    await cleanup_generator._cleanup_failed_initialization()
    await cleanup_generator._cleanup_failed_initialization()
    assert cleanup_generator._renderer.cleanup.await_count == 2


@pytest.mark.asyncio
async def test_runtime_branch_fillers_for_scheduler_initialization_and_batches(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover less-traveled scheduler/initialization branches in one place."""
    entry = config_entry_factory(entry_id="coverage-branch-fillers")
    generator = object.__new__(PawControlDashboardGenerator)
    generator.hass = hass
    generator.entry = entry
    generator._cleanup_tasks = set()

    generator._renderer = SimpleNamespace(async_initialize=AsyncMock(return_value=None))
    await generator._renderer_async_initialize()
    generator._renderer = SimpleNamespace(async_initialize=None)
    await generator._renderer_async_initialize()

    class _RuntimeErrorLoop:
        @staticmethod
        def create_task(awaitable: Awaitable[Any], name: str | None = None) -> Any:
            _ = awaitable, name
            raise RuntimeError("loop-closed")

    generator.hass = SimpleNamespace(
        async_create_task="not-callable", loop=_RuntimeErrorLoop()
    )

    async def _quick() -> None:
        await asyncio.sleep(0)

    def _create_task_with_typeerror_fallback(
        awaitable: Awaitable[Any],
        name: str | None = None,
    ) -> asyncio.Task[Any]:
        if name is not None:
            raise TypeError("no-name-support")
        return asyncio.get_running_loop().create_task(awaitable)

    with patch.object(
        dg.asyncio,
        "create_task",
        side_effect=_create_task_with_typeerror_fallback,
    ):
        task = generator._track_task(_quick(), name="typeerror-fallback")
    await task
    await asyncio.sleep(0)

    flip_init_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-init-flip"),
        local_tmp_dir,
        initialized=False,
    )

    class _FlipLock:
        async def __aenter__(self) -> None:
            flip_init_generator._initialized = True

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            _ = exc_type, exc, tb
            return False

    flip_init_generator._lock = _FlipLock()
    await flip_init_generator.async_initialize()

    slow_init_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-init-slow"),
        local_tmp_dir,
        initialized=False,
    )
    slow_init_generator._renderer_async_initialize = AsyncMock(return_value=None)
    slow_init_generator._dashboard_templates_async_initialize = AsyncMock(
        return_value=None
    )
    slow_init_generator._load_stored_data = AsyncMock(return_value=None)
    slow_init_generator._monotonic_time = MagicMock(
        side_effect=[0.0, dg.PERFORMANCE_LOG_THRESHOLD + 0.1],
    )
    await slow_init_generator.async_initialize()

    non_mapping_dashboards = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-load-non-mapping"),
        local_tmp_dir,
        initialized=True,
        load_payload={"dashboards": []},
    )
    non_mapping_dashboards._validate_stored_dashboards = AsyncMock(return_value=None)
    await non_mapping_dashboards._load_stored_data()
    assert non_mapping_dashboards._dashboards == {}

    no_renderer_cleanup = object.__new__(PawControlDashboardGenerator)
    no_renderer_cleanup._dashboards = {}
    await no_renderer_cleanup._cleanup_failed_initialization()

    slow_create_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-create-slow"),
        local_tmp_dir,
        initialized=True,
    )
    slow_create_generator._monotonic_time = MagicMock(
        side_effect=[0.0, 0.1, dg.PERFORMANCE_LOG_THRESHOLD + 1.0],
    )
    await slow_create_generator.async_create_dashboard(
        [_dog("slow", "Slow")], {"url": "slow"}
    )

    update_needs_init = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-update-init"),
        local_tmp_dir,
        initialized=False,
    )
    update_needs_init.async_initialize = AsyncMock(
        side_effect=lambda: setattr(update_needs_init, "_initialized", True),
    )
    assert (
        await update_needs_init.async_update_dashboard("missing", [_dog("id", "Name")])
        is False
    )

    batch_needs_init = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-batch-init"),
        local_tmp_dir,
        initialized=False,
    )
    batch_needs_init.async_initialize = AsyncMock(
        side_effect=lambda: setattr(batch_needs_init, "_initialized", True),
    )
    batch_needs_init.async_update_dashboard = AsyncMock(return_value=True)
    assert await batch_needs_init.async_batch_update_dashboards(
        [("url", [_dog("id", "Name")], None)],
    ) == {"url": True}


@pytest.mark.asyncio
async def test_runtime_create_dashboard_success_and_failures(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover create-dashboard success path plus input and renderer failures."""
    entry = config_entry_factory(entry_id="coverage-create-main")
    generator = _build_generator(hass, entry, local_tmp_dir, initialized=False)
    generator.async_initialize = AsyncMock(
        side_effect=lambda: setattr(generator, "_initialized", True),
    )

    result = await generator.async_create_dashboard(
        [_dog("buddy", "Buddy", notifications=True)],
        {"title": "Paw Main", "icon": "mdi:dog", "url": "paw-main"},
    )
    assert result.startswith("/")
    assert generator._performance_metrics["total_generations"] == 1
    assert generator._performance_metrics["file_operations"] >= 1

    with pytest.raises(ValueError, match="At least one dog configuration is required"):
        await generator.async_create_dashboard([])
    with pytest.raises(ValueError, match="At least one valid dog"):
        await generator.async_create_dashboard(["invalid"])

    failing_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-create-main-fail"),
        local_tmp_dir,
        initialized=True,
    )
    failing_generator._renderer.render_main_dashboard = AsyncMock(
        side_effect=RuntimeError("render-failed"),
    )
    with pytest.raises(HomeAssistantError, match="Dashboard creation failed"):
        await failing_generator.async_create_dashboard([_dog("x", "X")])
    assert failing_generator._performance_metrics["errors"] == 1


@pytest.mark.asyncio
async def test_runtime_create_dashboard_optimized_and_file_io_error_paths(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover optimized creation, URL generation, and file write failures."""
    generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-create-optimized"),
        local_tmp_dir,
        initialized=True,
    )

    assert (
        await generator._generate_unique_dashboard_url({"url": "My Main Url"})
        == "my-main-url-coverage"
    )

    dashboard_url = "coverage-main-dashboard"
    dashboard_config = {
        "views": [
            {"path": "overview", "title": "Overview", "icon": "mdi:home", "cards": []}
        ]
    }
    created_path = await generator._create_dashboard_file_async(
        dashboard_url,
        "Coverage Main",
        dashboard_config,
        "mdi:dog",
        True,
    )
    assert created_path.exists()

    await generator._store_dashboard_metadata_batch(
        dashboard_url,
        "Coverage Main",
        str(created_path),
        {
            "views": [
                {
                    "path": "overview",
                    "title": "Overview",
                    "icon": "mdi:home",
                    "cards": [],
                },
                {
                    "path": MODULE_NOTIFICATIONS,
                    "title": "Notifications",
                    "icon": "mdi:bell",
                    "cards": [{"type": "entities"}],
                },
            ],
        },
        [_dog("buddy", "Buddy", notifications=True)],
        {"theme": "modern"},
    )
    assert dashboard_url in generator._dashboards
    assert generator._dashboards[dashboard_url]["has_notifications_view"] is True

    cleanup_spy = AsyncMock(return_value=None)
    generator._cleanup_failed_dashboard = cleanup_spy
    generator._create_dashboard_file_async = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        await generator._create_dashboard_optimized(
            "cleanup-url",
            dashboard_config,
            [_dog("buddy", "Buddy")],
            {"title": "Title"},
        )
    cleanup_spy.assert_awaited_once_with("cleanup-url")

    file_error_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-create-file-error"),
        local_tmp_dir,
        initialized=True,
    )
    with patch(
        "custom_components.pawcontrol.dashboard_generator.aiofiles.open"
    ) as mocked_open:
        mocked_open.side_effect = OSError("disk-full")
        with pytest.raises(HomeAssistantError, match="Dashboard file creation failed"):
            await file_error_generator._create_dashboard_file_async(
                "error-url",
                "Error",
                {"views": []},
                "mdi:dog",
                True,
            )


@pytest.mark.asyncio
async def test_runtime_create_dog_dashboard_success_and_failures(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover dog dashboard creation, invalid input checks, and render failures."""
    generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-create-dog"),
        local_tmp_dir,
        initialized=False,
    )
    generator.async_initialize = AsyncMock(
        side_effect=lambda: setattr(generator, "_initialized", True),
    )

    result = await generator.async_create_dog_dashboard(
        _dog("dog-1", "Fido"),
        {"show_in_sidebar": False},
    )
    assert result == "/paw-dog-1"
    assert generator._dashboards["paw-dog-1"]["type"] == "dog"

    with pytest.raises(ValueError, match="invalid"):
        await generator.async_create_dog_dashboard({"dog_id": "missing-name"})

    original_ensure_dog_config = generator._ensure_dog_config
    generator._ensure_dog_config = lambda dog: {DOG_ID_FIELD: "", DOG_NAME_FIELD: ""}  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="Dog ID and name are required"):
        await generator.async_create_dog_dashboard(_dog("ignored", "Ignored"))
    generator._ensure_dog_config = original_ensure_dog_config

    failing_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-create-dog-fail"),
        local_tmp_dir,
        initialized=True,
    )
    failing_generator._renderer.render_dog_dashboard = AsyncMock(
        side_effect=RuntimeError("dog-render-failed"),
    )
    with pytest.raises(HomeAssistantError, match="Dog dashboard creation failed"):
        await failing_generator.async_create_dog_dashboard(_dog("dog-2", "Max"))
    assert failing_generator._performance_metrics["errors"] == 1


@pytest.mark.asyncio
async def test_runtime_update_dashboard_all_type_paths(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover update branches for missing/main/dog/weather/unsupported/errors."""
    generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-update"),
        local_tmp_dir,
        initialized=True,
    )

    main_file = local_tmp_dir / ".storage" / "lovelace.main"
    main_file.write_text("{}", encoding="utf-8")
    dog_file = local_tmp_dir / ".storage" / "lovelace.dog"
    dog_file.write_text("{}", encoding="utf-8")
    weather_file = local_tmp_dir / ".storage" / "lovelace.weather"
    weather_file.write_text("{}", encoding="utf-8")
    unsupported_file = local_tmp_dir / ".storage" / "lovelace.unsupported"
    unsupported_file.write_text("{}", encoding="utf-8")

    generator._dashboards = {
        "main": {
            "url": "main",
            "title": "Main",
            "path": str(main_file),
            "type": "main",
            "options": {"theme": "modern"},
            "show_in_sidebar": True,
        },
        "dog": {
            "url": "dog",
            "title": "Dog",
            "path": str(dog_file),
            "type": "dog",
            "dog_id": "dog-1",
            "options": {},
            "show_in_sidebar": False,
        },
        "weather_missing_id": {
            "url": "weather_missing_id",
            "title": "Weather",
            "path": str(weather_file),
            "type": "weather",
            "dog_name": "Buddy",
            "options": {},
        },
        "weather_missing_name": {
            "url": "weather_missing_name",
            "title": "Weather",
            "path": str(weather_file),
            "type": "weather",
            "dog_id": "dog-1",
            "options": {},
        },
        "weather": {
            "url": "weather",
            "title": "Weather",
            "path": str(weather_file),
            "type": "weather",
            "dog_id": "dog-1",
            "dog_name": "Buddy",
            "options": {"theme": "modern", "layout": "full"},
            "show_in_sidebar": False,
        },
        "unsupported": {
            "url": "unsupported",
            "title": "Unsupported",
            "path": str(unsupported_file),
            "type": "legacy",
            "options": {},
        },
    }

    generator._add_weather_components_to_dashboard = AsyncMock(return_value=None)
    generator._add_weather_components_to_dog_dashboard = AsyncMock(return_value=None)
    generator._has_weather_module = lambda dogs: True  # type: ignore[method-assign]

    dogs = [
        _dog("dog-1", "Buddy", breed="Labrador", weather=True),
        _dog("dog-2", "Max", weather=False),
    ]

    assert await generator.async_update_dashboard("missing", dogs, {}) is False
    assert (
        await generator.async_update_dashboard("main", dogs, {"show_in_sidebar": True})
        is True
    )
    assert (
        await generator.async_update_dashboard("dog", dogs, {"show_in_sidebar": False})
        is True
    )
    assert (
        await generator.async_update_dashboard("weather_missing_id", dogs, {}) is False
    )
    assert (
        await generator.async_update_dashboard("weather_missing_name", dogs, {})
        is False
    )
    assert (
        await generator.async_update_dashboard("weather", dogs, {"theme": "night"})
        is True
    )
    assert await generator.async_update_dashboard("unsupported", dogs, {}) is False
    assert await generator.async_update_dashboard("main", dogs, None) is True
    assert generator._dashboards["weather"]["theme"] == "modern"

    missing_dog_result = await generator.async_update_dashboard(
        "dog",
        [_dog("other", "Other")],
        {},
    )
    assert missing_dog_result is False

    generator._update_dashboard_file_async = AsyncMock(
        side_effect=RuntimeError("update-file-fail")
    )
    assert await generator.async_update_dashboard("main", dogs, {}) is False
    assert generator._performance_metrics["errors"] >= 1

    no_weather_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-update-no-weather"),
        local_tmp_dir,
        initialized=True,
    )
    no_weather_generator._dashboards = {
        "main": {
            "url": "main",
            "title": "Main",
            "path": str(main_file),
            "type": "main",
            "options": {},
        },
        "dog": {
            "url": "dog",
            "title": "Dog",
            "path": str(dog_file),
            "type": "dog",
            "dog_id": "dog-1",
            "options": {},
        },
    }
    no_weather_generator._has_weather_module = lambda dogs: False  # type: ignore[method-assign]
    no_weather_generator._add_weather_components_to_dashboard = AsyncMock(
        return_value=None
    )
    no_weather_generator._add_weather_components_to_dog_dashboard = AsyncMock(
        return_value=None
    )
    assert await no_weather_generator.async_update_dashboard("main", dogs, {}) is True
    assert await no_weather_generator.async_update_dashboard("dog", dogs, {}) is True
    no_weather_generator._add_weather_components_to_dashboard.assert_not_awaited()
    no_weather_generator._add_weather_components_to_dog_dashboard.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_update_file_delete_batch_and_save_paths(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover update-file I/O, delete paths, aggregation, and metadata save."""
    generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-update-delete-batch"),
        local_tmp_dir,
        initialized=True,
    )
    dashboard_file = local_tmp_dir / ".storage" / "lovelace.update"
    dashboard_file.write_text("{}", encoding="utf-8")

    await generator._update_dashboard_file_async(
        dashboard_file,
        {"views": [{"path": "overview", "cards": []}]},
        {
            "title": "Updated",
            "url": "updated",
            "show_in_sidebar": True,
            "icon": "mdi:dog",
        },
    )
    payload = json.loads(dashboard_file.read_text(encoding="utf-8"))
    assert payload["data"]["config"]["title"] == "Updated"
    assert generator._performance_metrics["file_operations"] == 1

    with patch(
        "custom_components.pawcontrol.dashboard_generator.aiofiles.open"
    ) as mocked_open:
        mocked_open.side_effect = OSError("cannot-write")
        with pytest.raises(HomeAssistantError, match="Dashboard file update failed"):
            await generator._update_dashboard_file_async(
                dashboard_file,
                {"views": []},
                {"title": "Bad", "url": "bad"},
            )

    generator._dashboards = {
        "delete-me": {
            "url": "delete-me",
            "title": "Delete",
            "path": str(dashboard_file),
            "type": "main",
            "options": {},
        },
    }
    generator.hass.async_add_executor_job = AsyncMock(return_value=None)
    assert await generator.async_delete_dashboard("missing") is False
    assert await generator.async_delete_dashboard("delete-me") is True
    assert "delete-me" not in generator._dashboards

    generator._dashboards = {
        "delete-error": {
            "url": "delete-error",
            "title": "Delete Error",
            "path": str(dashboard_file),
            "type": "main",
            "options": {},
        },
    }
    generator.hass.async_add_executor_job = AsyncMock(
        side_effect=RuntimeError("delete-fail")
    )
    assert await generator.async_delete_dashboard("delete-error") is False
    assert generator._performance_metrics["errors"] >= 1

    batch_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-batch-update"),
        local_tmp_dir,
        initialized=False,
    )
    batch_generator.async_initialize = AsyncMock(
        side_effect=lambda: setattr(batch_generator, "_initialized", True),
    )

    async def _update_side_effect(
        dashboard_url: str,
        dogs_config: Sequence[Mapping[str, Any]],
        options: Mapping[str, Any] | None = None,
    ) -> bool:
        _ = dogs_config, options
        if dashboard_url == "boom":
            raise RuntimeError("batch-failure")
        return dashboard_url != "false"

    batch_generator.async_update_dashboard = AsyncMock(side_effect=_update_side_effect)
    batch_results = await batch_generator.async_batch_update_dashboards(
        [
            ("ok", [_dog("d1", "D1")], {}),
            ("false", [_dog("d1", "D1")], {}),
            ("boom", [_dog("d1", "D1")], {}),
        ],
    )
    assert batch_results == {"ok": True, "false": False, "boom": False}

    already_initialized_batch = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-batch-update-initialized"),
        local_tmp_dir,
        initialized=True,
    )
    already_initialized_batch.async_update_dashboard = AsyncMock(return_value=True)
    assert await already_initialized_batch.async_batch_update_dashboards(
        [("ready", [_dog("d1", "D1")], None)],
    ) == {"ready": True}

    await generator._save_dashboard_metadata_async()
    assert generator._store.async_save.await_count >= 1
    generator._store.async_save = AsyncMock(side_effect=RuntimeError("save-fail"))
    await generator._save_dashboard_metadata_async()


@pytest.mark.asyncio
async def test_runtime_performance_cleanup_and_template_init_paths(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover metrics updates, cleanup fallback, full cleanup, and template init."""
    generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-cleanup"),
        local_tmp_dir,
        initialized=True,
    )
    await generator._update_performance_metrics("generation", 3.0)
    await generator._update_performance_metrics("update", 1.0)
    assert generator._performance_metrics["total_generations"] == 2
    assert generator._performance_metrics["avg_generation_time"] == 2.0

    await generator._cleanup_failed_dashboard("missing")
    cleanup_file = local_tmp_dir / ".storage" / "lovelace.cleanup-url"
    cleanup_file.write_text("{}", encoding="utf-8")
    generator._dashboards["cleanup-url"] = {
        "url": "cleanup-url",
        "title": "Cleanup",
        "path": str(cleanup_file),
        "type": "main",
        "options": {},
    }
    await generator._cleanup_failed_dashboard("cleanup-url")
    assert "cleanup-url" not in generator._dashboards
    generator.hass.async_add_executor_job = AsyncMock(
        side_effect=RuntimeError("executor-fail")
    )
    await generator._cleanup_failed_dashboard("cleanup-url")

    pending = asyncio.create_task(asyncio.sleep(10))
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    generator._cleanup_tasks = {pending, done}
    problematic_dashboard = {"path": 123}
    generator._dashboards = {
        "a": {
            "url": "a",
            "title": "A",
            "path": str(local_tmp_dir / ".storage" / "lovelace.a"),
            "type": "main",
            "options": {},
        },
        "b": problematic_dashboard,
    }
    (local_tmp_dir / ".storage" / "lovelace.a").write_text("{}", encoding="utf-8")
    generator._store.async_remove = AsyncMock(side_effect=RuntimeError("remove-fail"))
    await generator.async_cleanup()
    assert pending.cancelled()
    assert generator._cleanup_tasks == set()
    assert generator._dashboards == {}

    template_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-template-init"),
        local_tmp_dir,
        initialized=True,
    )
    await template_generator._dashboard_templates_async_initialize()
    template_generator._dashboard_templates = SimpleNamespace(
        cleanup=AsyncMock(return_value=None)
    )
    await template_generator._dashboard_templates_async_initialize()

    no_template_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-cleanup-no-template"),
        local_tmp_dir,
        initialized=True,
    )
    del no_template_generator._dashboard_templates
    await no_template_generator.async_cleanup()

    no_renderer_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-cleanup-no-renderer"),
        local_tmp_dir,
        initialized=True,
    )
    del no_renderer_generator._renderer
    await no_renderer_generator.async_cleanup()


@pytest.mark.asyncio
async def test_runtime_validation_and_getter_paths(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover stored dashboard validation branches and public getter callbacks."""
    entry = config_entry_factory(entry_id="coverage-validation")
    generator = _build_generator(hass, entry, local_tmp_dir, initialized=True)

    # No dashboards shortcut
    generator._dashboards = {}
    await generator._validate_stored_dashboards()

    valid_file = local_tmp_dir / ".storage" / "lovelace.valid"
    valid_file.write_text(
        json.dumps(
            {
                "data": {
                    "config": {
                        "views": [
                            {
                                "path": "overview",
                                "title": "Overview",
                                "icon": "mdi:home",
                                "cards": [],
                            },
                            {
                                "path": MODULE_NOTIFICATIONS,
                                "title": "Notifications",
                                "icon": "mdi:bell",
                                "cards": [{"type": "entities"}],
                            },
                        ]
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    valid_info = {
        "path": str(valid_file),
        "title": "Valid",
        "created": "2024-01-01T00:00:00+00:00",
        "type": "main",
        "version": dg.DASHBOARD_STORAGE_VERSION - 1,
    }
    invalid_info = {
        "path": str(local_tmp_dir / ".storage" / "missing-file"),
        "title": "Invalid",
        "created": "2024-01-01T00:00:00+00:00",
        "type": "main",
    }

    dashboard_info_for_normalisation = {
        "path": str(valid_file),
        "title": "Normalise",
        "created": "2024-01-01T00:00:00+00:00",
        "type": "main",
        "views": [
            {
                "path": MODULE_NOTIFICATIONS,
                "title": "N",
                "icon": "mdi:bell",
                "card_count": "1",
            },
        ],
        "has_notifications_view": False,
    }

    valid_result = await generator._validate_single_dashboard("valid", valid_info)
    invalid_result = await generator._validate_single_dashboard("invalid", invalid_info)
    normalised_result = await generator._validate_single_dashboard(
        "normalised",
        dashboard_info_for_normalisation,
    )

    assert valid_result == (True, True)
    assert invalid_result == (False, False)
    assert normalised_result == (True, True)
    assert valid_info["needs_regeneration"] is True
    assert valid_info["has_notifications_view"] is True
    assert dashboard_info_for_normalisation["has_notifications_view"] is True

    # Exception branch in single validation
    generator._load_dashboard_config = AsyncMock(
        side_effect=RuntimeError("load-failed")
    )
    exception_result = await generator._validate_single_dashboard(
        "exception",
        {
            "path": str(valid_file),
            "title": "Exception",
            "created": "2024-01-01T00:00:00+00:00",
            "type": "main",
            "views": "invalid",
        },
    )
    assert exception_result == (False, False)

    generator._dashboards = {
        "valid": valid_info,
        "invalid": invalid_info,
        "normalised": dashboard_info_for_normalisation,
    }
    generator._save_dashboard_metadata_async = AsyncMock(return_value=None)
    await generator._validate_stored_dashboards()
    assert "invalid" not in generator._dashboards
    generator._save_dashboard_metadata_async.assert_awaited()

    info = generator.get_dashboard_info("valid")
    assert info is not None
    assert "performance_metrics" in info
    assert generator.get_dashboard_info("missing") is None

    all_dashboards = generator.get_all_dashboards()
    assert "valid" in all_dashboards
    assert all("system_performance" in payload for payload in all_dashboards.values())
    assert generator.is_initialized() is True

    stats = generator.get_performance_stats()
    assert stats["dashboards_count"] == len(generator._dashboards)
    assert "renderer" in stats

    generator._renderer.get_render_stats = MagicMock(
        side_effect=RuntimeError("stats-failed")
    )
    stats_without_renderer = generator.get_performance_stats()
    assert "renderer" not in stats_without_renderer

    snapshot = generator._get_dashboard_performance_metrics()
    assert "error_rate" in snapshot
    assert "cache_efficiency" in snapshot

    # Validate direct-path branch without async executor job
    generator_no_executor = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-validation-no-executor"),
        local_tmp_dir,
        initialized=True,
    )
    generator_no_executor.hass = SimpleNamespace()
    assert await generator_no_executor._validate_single_dashboard(
        "invalid-path",
        {
            "path": None,
            "title": "Broken",
            "created": "2024-01-01T00:00:00+00:00",
            "type": "main",
        },
    ) == (False, False)
    assert await generator_no_executor._validate_single_dashboard(
        "missing-fields",
        {"path": str(valid_file), "title": "Missing", "type": "main"},
    ) == (False, False)

    # Cover gather processing branches in _validate_stored_dashboards.
    gather_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-validation-gather"),
        local_tmp_dir,
        initialized=True,
    )
    gather_generator._dashboards = {
        "none-result": {
            "path": str(valid_file),
            "title": "N",
            "created": "x",
            "type": "main",
        },
        "bool-result": {
            "path": str(valid_file),
            "title": "B",
            "created": "x",
            "type": "main",
        },
    }
    gather_generator._validate_single_dashboard = AsyncMock(  # type: ignore[method-assign]
        side_effect=[RuntimeError("boom"), True],
    )
    gather_generator._save_dashboard_metadata_async = AsyncMock(return_value=None)
    await gather_generator._validate_stored_dashboards()
    assert "none-result" not in gather_generator._dashboards

    unchanged_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-validation-unchanged"),
        local_tmp_dir,
        initialized=True,
    )
    unchanged_generator._dashboards = {
        "stable": {
            "path": str(valid_file),
            "title": "S",
            "created": "x",
            "type": "main",
        },
    }
    unchanged_generator._validate_single_dashboard = AsyncMock(  # type: ignore[method-assign]
        return_value=(True, False),
    )
    unchanged_generator._save_dashboard_metadata_async = AsyncMock(return_value=None)
    await unchanged_generator._validate_stored_dashboards()
    unchanged_generator._save_dashboard_metadata_async.assert_not_awaited()

    generator._renderer = None
    stats_no_renderer = generator.get_performance_stats()
    assert "renderer" not in stats_no_renderer


@pytest.mark.asyncio
async def test_runtime_weather_dashboard_and_component_paths(
    hass: Any,
    config_entry_factory: Callable[..., Any],
    local_tmp_dir: Path,
) -> None:
    """Cover weather creation, component injection, batch creation, and lookups."""
    entry = config_entry_factory(entry_id="coverage-weather")
    generator = _build_generator(hass, entry, local_tmp_dir, initialized=False)
    generator.async_initialize = AsyncMock(
        side_effect=lambda: setattr(generator, "_initialized", True),
    )

    def _ensure_weather_modules(dog: Any) -> dict[str, bool]:
        if not isinstance(dog, Mapping):
            return {MODULE_WEATHER: False}
        dog_id = dog.get(DOG_ID_FIELD)
        if not isinstance(dog_id, str):
            return {MODULE_WEATHER: False}
        enabled_ids = {
            "weather-dog",
            "fail-weather",
            "ok",
            "bad",
            "a",
            "b",
            "c",
            "d",
            "e",
        }
        return {MODULE_WEATHER: dog_id in enabled_ids}

    generator._ensure_modules_config = _ensure_weather_modules  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="invalid"):
        await generator.async_create_weather_dashboard({"dog_id": "missing"})
    with pytest.raises(ValueError, match="Weather module not enabled"):
        await generator.async_create_weather_dashboard(
            _dog("no-weather", "NoWeather", weather=False)
        )

    weather_url = await generator.async_create_weather_dashboard(
        _dog("weather-dog", "Storm", breed="Husky", weather=True),
        {"theme": "night", "layout": "compact", "show_in_sidebar": True},
    )
    assert weather_url == "/paw-weather-weather-dog"
    assert generator._dashboards["paw-weather-weather-dog"]["type"] == "weather"

    failing_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-weather-fail"),
        local_tmp_dir,
        initialized=True,
    )
    failing_generator._ensure_modules_config = generator._ensure_modules_config  # type: ignore[assignment]
    failing_generator._dashboard_templates.get_weather_dashboard_layout_template = (
        AsyncMock(
            side_effect=RuntimeError("template-failed"),
        )
    )
    with pytest.raises(HomeAssistantError, match="Weather dashboard creation failed"):
        await failing_generator.async_create_weather_dashboard(
            _dog("fail-weather", "Fail", weather=True),
        )
    assert failing_generator._performance_metrics["errors"] == 1

    assert generator._has_weather_module([_dog("x", "X", weather=False)]) is False
    assert generator._has_weather_module([_dog("ok", "OK", weather=True)]) is True

    overview_payload: dict[str, Any] = {"views": []}
    await generator._add_weather_components_to_dashboard(
        overview_payload,
        [_dog("a", "A", weather=True)],
        {"theme": "modern"},
    )
    assert overview_payload["views"][-1]["path"] == "weather-overview"
    assert (
        overview_payload["views"][-1]["cards"][0]["entity"] == "sensor.weather_status"
    )

    overview_payload_many: dict[str, Any] = {"views": []}
    await generator._add_weather_components_to_dashboard(
        overview_payload_many,
        [
            _dog("a", "A", weather=True),
            _dog("b", "B", weather=True),
            _dog("c", "C", weather=True),
            _dog("d", "D", weather=True),
            _dog("e", "E", weather=True),
        ],
        {"theme": "modern"},
    )
    assert overview_payload_many["views"][-1]["cards"][0]["type"] == "grid"

    overview_payload_medium: dict[str, Any] = {"views": []}
    await generator._add_weather_components_to_dashboard(
        overview_payload_medium,
        [
            _dog("a", "A", weather=True),
            _dog("b", "B", weather=True),
        ],
        {"theme": "modern"},
    )
    assert (
        overview_payload_medium["views"][-1]["cards"][0]["type"] == "horizontal-stack"
    )

    no_weather_payload: dict[str, Any] = {"views": []}
    await generator._add_weather_components_to_dashboard(
        no_weather_payload,
        [_dog("x", "X", weather=False)],
        {"theme": "modern"},
    )
    assert no_weather_payload["views"] == []

    missing_card_payload: dict[str, Any] = {"views": []}
    generator_missing_cards = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-weather-missing-cards"),
        local_tmp_dir,
        initialized=True,
    )
    generator_missing_cards._ensure_modules_config = lambda dog: {MODULE_WEATHER: True}  # type: ignore[method-assign]
    generator_missing_cards._ensure_dog_configs = lambda dogs: [  # type: ignore[method-assign]
        {
            DOG_ID_FIELD: "",
            DOG_NAME_FIELD: "",
            DOG_MODULES_FIELD: {MODULE_WEATHER: True},
        }
    ]
    await generator_missing_cards._add_weather_components_to_dashboard(
        missing_card_payload,
        [_dog("ignored", "Ignored", weather=True)],
        {"theme": "modern"},
    )
    assert missing_card_payload["views"] == []

    dog_dashboard_payload: dict[str, Any] = {
        "views": [{"path": "overview", "cards": [{"type": "entities"}]}],
    }
    await generator._add_weather_components_to_dog_dashboard(
        dog_dashboard_payload,
        _dog("weather-dog", "Storm", breed="Husky", weather=True),
        {"theme": "night"},
    )
    assert any(view["path"] == "weather" for view in dog_dashboard_payload["views"])
    overview_cards = dog_dashboard_payload["views"][0]["cards"]
    assert any(card.get("entity") == "sensor.weather_status" for card in overview_cards)

    before_views = list(dog_dashboard_payload["views"])
    await generator._add_weather_components_to_dog_dashboard(
        dog_dashboard_payload,
        "invalid",
        {"theme": "night"},
    )
    assert len(dog_dashboard_payload["views"]) == len(before_views)

    no_overview_payload: dict[str, Any] = {"views": [{"path": "status", "cards": []}]}
    await generator._add_weather_components_to_dog_dashboard(
        no_overview_payload,
        _dog("weather-dog", "Storm", breed="Husky", weather=True),
        {"theme": "night"},
    )

    batch_generator = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-weather-batch"),
        local_tmp_dir,
        initialized=False,
    )
    batch_generator.async_initialize = AsyncMock(
        side_effect=lambda: setattr(batch_generator, "_initialized", True),
    )
    batch_generator._ensure_modules_config = generator._ensure_modules_config  # type: ignore[assignment]
    empty_batch = await batch_generator.async_batch_create_weather_dashboards(
        [_dog("n1", "N1", weather=False)],
    )
    assert empty_batch == {}

    async def _weather_create_side_effect(
        dog_config: Mapping[str, Any],
        options: Mapping[str, Any] | None = None,
    ) -> str:
        _ = options
        dog_id = dog_config[DOG_ID_FIELD]
        if dog_id == "bad":
            raise RuntimeError("weather-boom")
        return f"/paw-weather-{dog_id}"

    batch_generator.async_create_weather_dashboard = AsyncMock(
        side_effect=_weather_create_side_effect,
    )
    mixed_batch = await batch_generator.async_batch_create_weather_dashboards(
        [
            _dog("ok", "OK", weather=True),
            _dog("bad", "Bad", weather=True),
            _dog("skip", "Skip", weather=False),
        ],
        {"theme": "night"},
    )
    assert mixed_batch["ok"] == "/paw-weather-ok"
    assert mixed_batch["bad"].startswith("Error:")

    batch_generator_missing_id = _build_generator(
        hass,
        config_entry_factory(entry_id="coverage-weather-batch-missing-id"),
        local_tmp_dir,
        initialized=True,
    )
    batch_generator_missing_id._ensure_modules_config = lambda dog: {
        MODULE_WEATHER: True
    }  # type: ignore[method-assign]
    batch_generator_missing_id._ensure_dog_configs = lambda dogs: [  # type: ignore[method-assign]
        {
            DOG_NAME_FIELD: "MissingId",
            DOG_MODULES_FIELD: {MODULE_WEATHER: True},
        }
    ]
    assert (
        await batch_generator_missing_id.async_batch_create_weather_dashboards(
            [_dog("ignored", "Ignored", weather=True)],
        )
        == {}
    )

    batch_generator._dashboards = {
        "weather-ok": {"type": "weather", "dog_id": "ok", "url": "weather-ok"},
        "main": {"type": "main", "dog_id": "ok", "url": "main"},
    }
    assert batch_generator.get_weather_dashboards() == {
        "weather-ok": {"type": "weather", "dog_id": "ok", "url": "weather-ok"},
    }
    assert batch_generator.has_weather_dashboard("ok") is True
    assert batch_generator.has_weather_dashboard("missing") is False
