"""Unit tests for the lightweight parts of module_adapters."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
import importlib
from pathlib import Path
import sys
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.types import JSONMutableMapping


class _DtUtilStub(ModuleType):
  """Minimal stub emulating homeassistant.util.dt."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    super().__init__("homeassistant.util.dt")
    self._now = datetime(2024, 1, 1, tzinfo=UTC)

  def utcnow(self) -> datetime:  # noqa: E111
    return self._now

  def advance(self, delta: timedelta) -> None:  # noqa: E111
    self._now += delta


@pytest.fixture
def module_adapters(monkeypatch: pytest.MonkeyPatch):
  """Import module_adapters with a stubbed Home Assistant dt helper."""  # noqa: E111

  dt_stub = _DtUtilStub()  # noqa: E111
  package_path = (  # noqa: E111
    Path(__file__).resolve().parents[2] / "custom_components" / "pawcontrol"
  )
  ha_module = ModuleType("homeassistant")  # noqa: E111
  util_module = ModuleType("homeassistant.util")  # noqa: E111
  util_module.dt = dt_stub  # noqa: E111
  ha_module.util = util_module  # noqa: E111

  monkeypatch.setitem(sys.modules, "homeassistant", ha_module)  # noqa: E111
  monkeypatch.setitem(sys.modules, "homeassistant.util", util_module)  # noqa: E111
  monkeypatch.setitem(sys.modules, "homeassistant.util.dt", dt_stub)  # noqa: E111
  namespace_pkg = ModuleType("custom_components")  # noqa: E111
  namespace_pkg.__path__ = [str(package_path.parent)]  # noqa: E111
  monkeypatch.setitem(sys.modules, "custom_components", namespace_pkg)  # noqa: E111
  package = ModuleType("custom_components.pawcontrol")  # noqa: E111
  package.__path__ = [str(package_path)]  # noqa: E111
  package.__package__ = "custom_components.pawcontrol"  # noqa: E111
  monkeypatch.setitem(sys.modules, "custom_components.pawcontrol", package)  # noqa: E111

  const_stub = ModuleType("custom_components.pawcontrol.const")  # noqa: E111
  const_stub.CONF_DOGS = "dogs"  # noqa: E111
  const_stub.CONF_DOG_ID = "dog_id"  # noqa: E111
  const_stub.CONF_DOG_BREED = "dog_breed"  # noqa: E111
  const_stub.CONF_DOG_AGE = "dog_age"  # noqa: E111
  const_stub.CONF_WEATHER_ENTITY = "weather_entity"  # noqa: E111
  const_stub.MODULE_FEEDING = "feeding"  # noqa: E111
  const_stub.MODULE_GARDEN = "garden"  # noqa: E111
  const_stub.MODULE_GPS = "gps"  # noqa: E111
  const_stub.MODULE_HEALTH = "health"  # noqa: E111
  const_stub.MODULE_WALK = "walk"  # noqa: E111
  const_stub.MODULE_WEATHER = "weather"  # noqa: E111
  monkeypatch.setitem(sys.modules, "custom_components.pawcontrol.const", const_stub)  # noqa: E111

  exceptions_stub = ModuleType("custom_components.pawcontrol.exceptions")  # noqa: E111

  class NetworkError(Exception):  # noqa: E111
    """Stubbed network error for tests."""

  class RateLimitError(Exception):  # noqa: E111
    """Stubbed rate limit error for tests."""

  class GPSUnavailableError(Exception):  # noqa: E111
    """Stubbed GPS error with dog context."""

    def __init__(self, dog_id: str, message: str) -> None:
      super().__init__(message)  # noqa: E111
      self.dog_id = dog_id  # noqa: E111

  exceptions_stub.NetworkError = NetworkError  # noqa: E111
  exceptions_stub.RateLimitError = RateLimitError  # noqa: E111
  exceptions_stub.GPSUnavailableError = GPSUnavailableError  # noqa: E111
  monkeypatch.setitem(  # noqa: E111
    sys.modules, "custom_components.pawcontrol.exceptions", exceptions_stub
  )

  device_api_stub = ModuleType("custom_components.pawcontrol.device_api")  # noqa: E111

  class PawControlDeviceClient:  # pragma: no cover - only used for typing  # noqa: E111
    async def async_get_feeding_payload(self, dog_id: str) -> JSONMutableMapping:
      raise NotImplementedError  # noqa: E111

  device_api_stub.PawControlDeviceClient = PawControlDeviceClient  # noqa: E111
  monkeypatch.setitem(  # noqa: E111
    sys.modules, "custom_components.pawcontrol.device_api", device_api_stub
  )

  sys.modules.pop("custom_components.pawcontrol.module_adapters", None)  # noqa: E111
  module = importlib.import_module("custom_components.pawcontrol.module_adapters")  # noqa: E111
  return module, dt_stub  # noqa: E111


@pytest.mark.unit
def test_feeding_adapter_rejects_missing_or_closed_session(
  module_adapters: tuple[Any, _DtUtilStub],
  session_factory,
) -> None:
  """The adapter must enforce Home Assistant's shared session lifecycle."""  # noqa: E111

  module, _ = module_adapters  # noqa: E111

  with pytest.raises(ValueError):  # noqa: E111
    module.FeedingModuleAdapter(  # type: ignore[arg-type]
      session=None,
      use_external_api=False,
      ttl=timedelta(minutes=5),
      api_client=None,
    )

  closed_session = session_factory(closed=True)  # noqa: E111

  with pytest.raises(ValueError):  # noqa: E111
    module.FeedingModuleAdapter(
      session=closed_session,
      use_external_api=False,
      ttl=timedelta(minutes=5),
      api_client=None,
    )


def test_expiring_cache_handles_hits_and_expiration(
  module_adapters: tuple[Any, _DtUtilStub],
) -> None:
  """_ExpiringCache should track hits, misses and cleanup correctly."""  # noqa: E111

  module, dt_stub = module_adapters  # noqa: E111
  cache = module._ExpiringCache(ttl=timedelta(seconds=30))  # noqa: E111

  cache.set("buddy", {"meals": 2})  # noqa: E111
  assert cache.get("buddy") == {"meals": 2}  # noqa: E111

  cache.set("max", {"meals": 1})  # noqa: E111
  dt_stub.advance(timedelta(seconds=31))  # noqa: E111

  # Entry for "buddy" was accessed before expiration, so the metrics track a hit.  # noqa: E114, E501
  metrics = cache.metrics()  # noqa: E111
  assert metrics.hits == 1  # noqa: E111
  assert metrics.misses == 0  # noqa: E111

  # Both entries should be evicted once the TTL has passed.  # noqa: E114
  evicted = cache.cleanup(dt_stub.utcnow())  # noqa: E111
  assert evicted == 2  # noqa: E111
  assert cache.get("buddy") is None  # noqa: E111

  metrics = cache.metrics()  # noqa: E111
  assert metrics.hits == 1  # noqa: E111
  assert metrics.misses == 1  # noqa: E111
  assert metrics.entries == 0  # noqa: E111


def test_feeding_adapter_uses_manager_and_cache(
  module_adapters: tuple[Any, _DtUtilStub],
  session_factory,
) -> None:
  """FeedingModuleAdapter should use the manager and cache results."""  # noqa: E111

  module, dt_stub = module_adapters  # noqa: E111
  adapter = module.FeedingModuleAdapter(  # noqa: E111
    session=session_factory(),
    use_external_api=False,
    ttl=timedelta(minutes=5),
    api_client=None,
  )

  manager = AsyncMock()  # noqa: E111
  manager.async_get_feeding_data = AsyncMock(return_value={"last_feeding": "08:00"})  # noqa: E111
  adapter.attach(manager)  # noqa: E111

  async def _exercise() -> None:  # noqa: E111
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

  asyncio.run(_exercise())  # noqa: E111


def test_feeding_adapter_external_api_fallback(
  module_adapters: tuple[Any, _DtUtilStub],
  session_factory,
) -> None:
  """External API is used when the manager is unavailable."""  # noqa: E111

  module, _ = module_adapters  # noqa: E111
  api_client = AsyncMock()  # noqa: E111
  api_client.async_get_feeding_payload = AsyncMock(return_value={"feedings_today": {}})  # noqa: E111

  adapter = module.FeedingModuleAdapter(  # noqa: E111
    session=session_factory(),
    use_external_api=True,
    ttl=timedelta(minutes=5),
    api_client=api_client,
  )

  async def _exercise() -> None:  # noqa: E111
    result = await adapter.async_get_data("max")
    assert result["status"] == "ready"
    api_client.async_get_feeding_payload.assert_awaited_once_with("max")

  asyncio.run(_exercise())  # noqa: E111


def test_feeding_adapter_default_payload(
  module_adapters: tuple[Any, _DtUtilStub],
  session_factory,
) -> None:
  """A deterministic default payload is returned when no sources are available."""  # noqa: E111

  module, _ = module_adapters  # noqa: E111
  adapter = module.FeedingModuleAdapter(  # noqa: E111
    session=session_factory(),
    use_external_api=False,
    ttl=timedelta(minutes=5),
    api_client=None,
  )

  async def _exercise() -> None:  # noqa: E111
    result = await adapter.async_get_data("luna")
    assert result["status"] == "ready"
    assert result["feedings_today"] == {}
    assert result["total_feedings_today"] == 0
    # ensure repeated calls use cached default
    assert await adapter.async_get_data("luna") is result

  asyncio.run(_exercise())  # noqa: E111
