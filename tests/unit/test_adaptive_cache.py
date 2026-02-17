"""Tests for the AdaptiveCache used by the PawControl data manager."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sys
import types
from typing import Self

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "pawcontrol"
    / "data_manager.py"
)

custom_components_pkg = types.ModuleType("custom_components")
custom_components_pkg.__path__ = [
    str(Path(__file__).resolve().parents[2] / "custom_components")
]
sys.modules.setdefault("custom_components", custom_components_pkg)

pawcontrol_pkg = types.ModuleType("custom_components.pawcontrol")
pawcontrol_pkg.__path__ = [
    str(Path(__file__).resolve().parents[2] / "custom_components" / "pawcontrol")
]
sys.modules.setdefault("custom_components.pawcontrol", pawcontrol_pkg)

spec = importlib.util.spec_from_file_location(
    "custom_components.pawcontrol.data_manager", MODULE_PATH
)
if spec is None or spec.loader is None:  # pragma: no cover - defensive programming
    raise RuntimeError("Failed to load pawcontrol data_manager module for testing")  # noqa: E111

# Provide lightweight Home Assistant stubs so the module can be imported without the
# full dependency tree. The AdaptiveCache implementation used in these tests only
# relies on dt_util.utcnow(), so the supporting APIs can be minimal.
ha_pkg = types.ModuleType("homeassistant")
ha_pkg.__path__ = []
sys.modules.setdefault("homeassistant", ha_pkg)

ha_core = types.ModuleType("homeassistant.core")


class _HomeAssistant:  # pragma: no cover - trivial stub for typing only
    pass  # noqa: E111


ha_core.HomeAssistant = _HomeAssistant
sys.modules.setdefault("homeassistant.core", ha_core)

ha_helpers = types.ModuleType("homeassistant.helpers")
sys.modules.setdefault("homeassistant.helpers", ha_helpers)

ha_helpers_storage = types.ModuleType("homeassistant.helpers.storage")


class _Store:  # pragma: no cover - minimal async storage stub for import compatibility
    async def async_load(self) -> dict[str, object]:  # noqa: E111
        return {}

    async def async_save(self, data: object) -> None:  # noqa: E111
        self.data = data


ha_helpers_storage.Store = _Store
sys.modules.setdefault("homeassistant.helpers.storage", ha_helpers_storage)

ha_helpers_device_registry = types.ModuleType("homeassistant.helpers.device_registry")


class _DeviceEntry:  # pragma: no cover - minimal registry stub
    id = "device"  # noqa: E111


class _DeviceInfo(dict):  # pragma: no cover - minimal registry stub
    pass  # noqa: E111


ha_helpers_device_registry.DeviceEntry = _DeviceEntry
ha_helpers_device_registry.DeviceInfo = _DeviceInfo
sys.modules.setdefault(
    "homeassistant.helpers.device_registry", ha_helpers_device_registry
)

ha_helpers_entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
ha_helpers_entity_registry.async_get = lambda hass: types.SimpleNamespace(
    async_get=lambda entity_id: None,
    async_update_entity=lambda entity_id, **kwargs: None,
)
sys.modules.setdefault(
    "homeassistant.helpers.entity_registry", ha_helpers_entity_registry
)

ha_helpers_entity = types.ModuleType("homeassistant.helpers.entity")


class _Entity:  # pragma: no cover - minimal entity stub
    pass  # noqa: E111


ha_helpers_entity.Entity = _Entity
sys.modules.setdefault("homeassistant.helpers.entity", ha_helpers_entity)

ha_util = types.ModuleType("homeassistant.util")
sys.modules.setdefault("homeassistant.util", ha_util)

ha_exceptions = types.ModuleType("homeassistant.exceptions")


class _HomeAssistantError(Exception):  # pragma: no cover - test stub
    pass  # noqa: E111


ha_exceptions.HomeAssistantError = _HomeAssistantError
sys.modules.setdefault("homeassistant.exceptions", ha_exceptions)

ha_config_entries = types.ModuleType("homeassistant.config_entries")


class _ConfigEntry:  # pragma: no cover - config entry stub
    entry_id = "test"  # noqa: E111


ha_config_entries.ConfigEntry = _ConfigEntry
sys.modules.setdefault("homeassistant.config_entries", ha_config_entries)

ha_const = types.ModuleType("homeassistant.const")


class _Platform:  # pragma: no cover - constant container stub
    SENSOR = "sensor"  # noqa: E111
    BINARY_SENSOR = "binary_sensor"  # noqa: E111
    BUTTON = "button"  # noqa: E111
    SWITCH = "switch"  # noqa: E111
    NUMBER = "number"  # noqa: E111
    SELECT = "select"  # noqa: E111
    TEXT = "text"  # noqa: E111
    DEVICE_TRACKER = "device_tracker"  # noqa: E111
    DATE = "date"  # noqa: E111
    DATETIME = "datetime"  # noqa: E111


ha_const.Platform = _Platform
sys.modules.setdefault("homeassistant.const", ha_const)

ha_helpers_selector = types.ModuleType("homeassistant.helpers.selector")


class _NumberSelectorConfig:  # pragma: no cover - test stub
    def __init__(self, **kwargs: object) -> None:  # noqa: E111
        self.config = kwargs


class _NumberSelectorMode:  # pragma: no cover - test stub
    BOX = "box"  # noqa: E111


@dataclass(slots=True)
class _NumberSelector:  # pragma: no cover - test stub
    config: _NumberSelectorConfig | None = None  # noqa: E111


ha_helpers_selector.NumberSelector = _NumberSelector
ha_helpers_selector.NumberSelectorConfig = _NumberSelectorConfig
ha_helpers_selector.NumberSelectorMode = _NumberSelectorMode
ha_helpers_selector.selector = lambda *args, **kwargs: None
sys.modules.setdefault("homeassistant.helpers.selector", ha_helpers_selector)

ha_util_dt = types.ModuleType("homeassistant.util.dt")
ha_util_dt.utcnow = lambda: datetime.now(datetime.UTC)
ha_util_dt.now = lambda: datetime.now(datetime.UTC)
ha_util_dt.as_utc = lambda value: (
    value if value.tzinfo else value.replace(tzinfo=datetime.UTC)
)
ha_util_dt.as_local = lambda value: value
ha_util_dt.parse_datetime = lambda value: (
    datetime.fromisoformat(value) if isinstance(value, str) else None
)
ha_util_dt.parse_date = lambda value: (
    datetime.fromisoformat(value).date() if isinstance(value, str) else None
)
sys.modules.setdefault("homeassistant.util.dt", ha_util_dt)
ha_util.dt = ha_util_dt

data_manager = importlib.util.module_from_spec(spec)
sys.modules.setdefault("pawcontrol_data_manager", data_manager)
spec.loader.exec_module(data_manager)

AdaptiveCache = data_manager.AdaptiveCache


UTC = UTC


@pytest.mark.asyncio
async def test_cleanup_expired_removes_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expired cache entries should be evicted and reported."""  # noqa: E111

    cache = AdaptiveCache()  # noqa: E111

    base_time = datetime(2024, 1, 1, tzinfo=UTC)  # noqa: E111
    monkeypatch.setattr(data_manager, "_utcnow", lambda: base_time)  # noqa: E111

    await cache.set("dog", {"name": "Otis"}, base_ttl=60)  # noqa: E111
    value, hit = await cache.get("dog")  # noqa: E111
    assert hit is True  # noqa: E111
    assert value == {"name": "Otis"}  # noqa: E111

    monkeypatch.setattr(  # noqa: E111
        data_manager,
        "_utcnow",
        lambda: base_time + timedelta(minutes=5),
    )

    removed = await cache.cleanup_expired()  # noqa: E111
    assert removed == 1  # noqa: E111

    value, hit = await cache.get("dog")  # noqa: E111
    assert hit is False  # noqa: E111
    assert value is None  # noqa: E111


@pytest.mark.asyncio
async def test_cleanup_expired_honours_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cleanup_expired should prefer the shorter override TTL when supplied."""  # noqa: E111

    cache = AdaptiveCache()  # noqa: E111

    base_time = datetime(2024, 3, 1, tzinfo=UTC)  # noqa: E111
    monkeypatch.setattr(data_manager, "_utcnow", lambda: base_time)  # noqa: E111

    await cache.set("dog", {"name": "Luna"}, base_ttl=600)  # noqa: E111

    monkeypatch.setattr(  # noqa: E111
        data_manager,
        "_utcnow",
        lambda: base_time + timedelta(minutes=3),
    )

    removed = await cache.cleanup_expired(ttl_seconds=120)  # noqa: E111
    assert removed == 1  # noqa: E111

    value, hit = await cache.get("dog")  # noqa: E111
    assert hit is False  # noqa: E111
    assert value is None  # noqa: E111


class _TrackingAsyncLock:
    """Helper async lock that records acquisition counts."""  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        self._lock = asyncio.Lock()
        self.acquire_count = 0

    async def __aenter__(self) -> Self:  # noqa: E111
        self.acquire_count += 1
        await self._lock.acquire()
        return self

    async def __aexit__(  # noqa: E111
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        self._lock.release()


@pytest.mark.asyncio
async def test_cleanup_expired_uses_internal_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cleanup routine should acquire the cache lock to avoid races."""  # noqa: E111

    cache = AdaptiveCache()  # noqa: E111
    tracking_lock = _TrackingAsyncLock()  # noqa: E111
    cache._lock = tracking_lock  # type: ignore[attr-defined]  # noqa: E111

    base_time = datetime(2024, 2, 1, tzinfo=UTC)  # noqa: E111
    monkeypatch.setattr(data_manager, "_utcnow", lambda: base_time)  # noqa: E111
    await cache.set("dog", {"value": 1}, base_ttl=60)  # noqa: E111

    initial_acquisitions = tracking_lock.acquire_count  # noqa: E111

    monkeypatch.setattr(  # noqa: E111
        data_manager,
        "_utcnow",
        lambda: base_time + timedelta(hours=2),
    )

    removed = await cache.cleanup_expired()  # noqa: E111

    assert removed == 1  # noqa: E111
    assert tracking_lock.acquire_count == initial_acquisitions + 1  # noqa: E111


@pytest.mark.asyncio
async def test_cleanup_diagnostics_track_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagnostics should record override-driven cleanup activity."""  # noqa: E111

    cache = AdaptiveCache()  # noqa: E111

    diagnostics = cache.get_diagnostics()  # noqa: E111
    assert diagnostics["cleanup_invocations"] == 0  # noqa: E111
    assert diagnostics["expired_entries"] == 0  # noqa: E111
    assert diagnostics["last_cleanup"] is None  # noqa: E111

    base_time = datetime(2024, 5, 1, tzinfo=UTC)  # noqa: E111
    monkeypatch.setattr(data_manager, "_utcnow", lambda: base_time)  # noqa: E111
    await cache.set("dog", {"name": "Bolt"}, base_ttl=600)  # noqa: E111

    monkeypatch.setattr(  # noqa: E111
        data_manager,
        "_utcnow",
        lambda: base_time + timedelta(seconds=200),
    )

    removed = await cache.cleanup_expired(ttl_seconds=90)  # noqa: E111
    assert removed == 1  # noqa: E111

    diagnostics = cache.get_diagnostics()  # noqa: E111
    assert diagnostics["cleanup_invocations"] == 1  # noqa: E111
    assert diagnostics["expired_entries"] == 1  # noqa: E111
    assert diagnostics["expired_via_override"] == 1  # noqa: E111
    assert diagnostics["last_expired_count"] == 1  # noqa: E111
    assert diagnostics["last_override_ttl"] == 90  # noqa: E111
    assert diagnostics["last_cleanup"] is not None  # noqa: E111
