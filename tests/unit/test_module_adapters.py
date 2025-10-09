"""Unit tests for the lightweight parts of module_adapters."""

from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock

import pytest


class _DtUtilStub(ModuleType):
    """Minimal stub emulating homeassistant.util.dt."""

    def __init__(self) -> None:
        super().__init__("homeassistant.util.dt")
        self._now = datetime(2024, 1, 1, tzinfo=UTC)

    def utcnow(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


@pytest.fixture
def module_adapters(monkeypatch: pytest.MonkeyPatch):
    """Import module_adapters with a stubbed Home Assistant dt helper."""

    dt_stub = _DtUtilStub()
    package_path = (
        Path(__file__).resolve().parents[2] / "custom_components" / "pawcontrol"
    )
    ha_module = ModuleType("homeassistant")
    util_module = ModuleType("homeassistant.util")
    util_module.dt = dt_stub
    ha_module.util = util_module

    monkeypatch.setitem(sys.modules, "homeassistant", ha_module)
    monkeypatch.setitem(sys.modules, "homeassistant.util", util_module)
    monkeypatch.setitem(sys.modules, "homeassistant.util.dt", dt_stub)
    namespace_pkg = ModuleType("custom_components")
    namespace_pkg.__path__ = [str(package_path.parent)]
    monkeypatch.setitem(sys.modules, "custom_components", namespace_pkg)
    package = ModuleType("custom_components.pawcontrol")
    package.__path__ = [str(package_path)]
    package.__package__ = "custom_components.pawcontrol"
    monkeypatch.setitem(sys.modules, "custom_components.pawcontrol", package)

    const_stub = ModuleType("custom_components.pawcontrol.const")
    const_stub.CONF_DOGS = "dogs"
    const_stub.CONF_DOG_ID = "dog_id"
    const_stub.CONF_DOG_BREED = "dog_breed"
    const_stub.CONF_DOG_AGE = "dog_age"
    const_stub.CONF_WEATHER_ENTITY = "weather_entity"
    const_stub.MODULE_FEEDING = "feeding"
    const_stub.MODULE_GARDEN = "garden"
    const_stub.MODULE_GPS = "gps"
    const_stub.MODULE_HEALTH = "health"
    const_stub.MODULE_WALK = "walk"
    const_stub.MODULE_WEATHER = "weather"
    monkeypatch.setitem(sys.modules, "custom_components.pawcontrol.const", const_stub)

    exceptions_stub = ModuleType("custom_components.pawcontrol.exceptions")

    class NetworkError(Exception):
        """Stubbed network error for tests."""

    class RateLimitError(Exception):
        """Stubbed rate limit error for tests."""

    class GPSUnavailableError(Exception):
        """Stubbed GPS error with dog context."""

        def __init__(self, dog_id: str, message: str) -> None:
            super().__init__(message)
            self.dog_id = dog_id

    exceptions_stub.NetworkError = NetworkError
    exceptions_stub.RateLimitError = RateLimitError
    exceptions_stub.GPSUnavailableError = GPSUnavailableError
    monkeypatch.setitem(
        sys.modules, "custom_components.pawcontrol.exceptions", exceptions_stub
    )

    device_api_stub = ModuleType("custom_components.pawcontrol.device_api")

    class PawControlDeviceClient:  # pragma: no cover - only used for typing
        async def async_get_feeding_payload(self, dog_id: str) -> dict[str, Any]:
            raise NotImplementedError

    device_api_stub.PawControlDeviceClient = PawControlDeviceClient
    monkeypatch.setitem(
        sys.modules, "custom_components.pawcontrol.device_api", device_api_stub
    )

    sys.modules.pop("custom_components.pawcontrol.module_adapters", None)
    module = importlib.import_module("custom_components.pawcontrol.module_adapters")
    return module, dt_stub


@pytest.mark.unit
def test_feeding_adapter_rejects_missing_or_closed_session(
    module_adapters: tuple[Any, _DtUtilStub],
    session_factory,
) -> None:
    """The adapter must enforce Home Assistant's shared session lifecycle."""

    module, _ = module_adapters

    with pytest.raises(ValueError):
        module.FeedingModuleAdapter(  # type: ignore[arg-type]
            session=None,
            use_external_api=False,
            ttl=timedelta(minutes=5),
            api_client=None,
        )

    closed_session = session_factory(closed=True)

    with pytest.raises(ValueError):
        module.FeedingModuleAdapter(
            session=closed_session,
            use_external_api=False,
            ttl=timedelta(minutes=5),
            api_client=None,
        )


def test_expiring_cache_handles_hits_and_expiration(
    module_adapters: tuple[Any, _DtUtilStub],
) -> None:
    """_ExpiringCache should track hits, misses and cleanup correctly."""

    module, dt_stub = module_adapters
    cache = module._ExpiringCache(ttl=timedelta(seconds=30))

    cache.set("buddy", {"meals": 2})
    assert cache.get("buddy") == {"meals": 2}

    cache.set("max", {"meals": 1})
    dt_stub.advance(timedelta(seconds=31))

    # Entry for "buddy" was accessed before expiration, so the metrics track a hit.
    metrics = cache.metrics()
    assert metrics.hits == 1
    assert metrics.misses == 0

    # Both entries should be evicted once the TTL has passed.
    evicted = cache.cleanup(dt_stub.utcnow())
    assert evicted == 2
    assert cache.get("buddy") is None

    metrics = cache.metrics()
    assert metrics.hits == 1
    assert metrics.misses == 1
    assert metrics.entries == 0


def test_feeding_adapter_uses_manager_and_cache(
    module_adapters: tuple[Any, _DtUtilStub],
    session_factory,
) -> None:
    """FeedingModuleAdapter should use the manager and cache results."""

    module, dt_stub = module_adapters
    adapter = module.FeedingModuleAdapter(
        session=session_factory(),
        use_external_api=False,
        ttl=timedelta(minutes=5),
        api_client=None,
    )

    manager = AsyncMock()
    manager.async_get_feeding_data = AsyncMock(return_value={"last_feeding": "08:00"})
    adapter.attach(manager)

    async def _exercise() -> None:
        result_first = await adapter.async_get_data("buddy")
        assert result_first["status"] == "ready"
        manager.async_get_feeding_data.assert_awaited_once_with("buddy")

        result_second = await adapter.async_get_data("buddy")
        # Cached response should be returned without additional manager calls.
        assert result_second is result_first
        assert manager.async_get_feeding_data.await_count == 1

        dt_stub.advance(timedelta(minutes=10))
        await adapter.async_get_data("buddy")
        assert manager.async_get_feeding_data.await_count == 2

    asyncio.run(_exercise())


def test_feeding_adapter_external_api_fallback(
    module_adapters: tuple[Any, _DtUtilStub],
    session_factory,
) -> None:
    """External API is used when the manager is unavailable."""

    module, _ = module_adapters
    api_client = AsyncMock()
    api_client.async_get_feeding_payload = AsyncMock(
        return_value={"feedings_today": {}}
    )

    adapter = module.FeedingModuleAdapter(
        session=session_factory(),
        use_external_api=True,
        ttl=timedelta(minutes=5),
        api_client=api_client,
    )

    async def _exercise() -> None:
        result = await adapter.async_get_data("max")
        assert result["status"] == "ready"
        api_client.async_get_feeding_payload.assert_awaited_once_with("max")

    asyncio.run(_exercise())


def test_feeding_adapter_default_payload(
    module_adapters: tuple[Any, _DtUtilStub],
    session_factory,
) -> None:
    """A deterministic default payload is returned when no sources are available."""

    module, _ = module_adapters
    adapter = module.FeedingModuleAdapter(
        session=session_factory(),
        use_external_api=False,
        ttl=timedelta(minutes=5),
        api_client=None,
    )

    async def _exercise() -> None:
        result = await adapter.async_get_data("luna")
        assert result["status"] == "ready"
        assert result["feedings_today"] == {}
        assert result["total_feedings_today"] == 0
        # ensure repeated calls use cached default
        assert await adapter.async_get_data("luna") is result

    asyncio.run(_exercise())
