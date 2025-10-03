"""Session reuse safeguards for the device API client."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest
from pytest import MonkeyPatch


@pytest.fixture(scope="module")
def device_api_module() -> ModuleType:
    """Load the device API helper without importing the integration package."""

    monkeypatch = MonkeyPatch()
    ha_module = ModuleType("homeassistant")
    ha_exceptions = ModuleType("homeassistant.exceptions")

    class ConfigEntryAuthFailed(Exception):
        """Stubbed Home Assistant auth error."""

    ha_exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    ha_module.exceptions = ha_exceptions
    monkeypatch.setitem(sys.modules, "homeassistant", ha_module)
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", ha_exceptions)

    namespace_pkg = ModuleType("custom_components")
    namespace_pkg.__path__ = [
        str(Path(__file__).resolve().parents[2] / "custom_components")
    ]
    integration_pkg = ModuleType("custom_components.pawcontrol")
    integration_pkg.__path__ = [
        str(Path(__file__).resolve().parents[2] / "custom_components" / "pawcontrol")
    ]
    stub_exceptions = ModuleType("custom_components.pawcontrol.exceptions")
    stub_resilience = ModuleType("custom_components.pawcontrol.resilience")

    class NetworkError(Exception):
        """Stubbed network error."""

    class RateLimitError(Exception):
        """Stubbed rate limit error."""

    stub_exceptions.NetworkError = NetworkError
    stub_exceptions.RateLimitError = RateLimitError

    class RetryConfig:  # pragma: no cover - simple stub
        """Minimal RetryConfig replacement for tests."""

        def __init__(self, **kwargs: object) -> None:
            self.options = kwargs

    class ResilienceManager:  # pragma: no cover - simple stub
        """Stubbed resilience manager used in tests."""

        def __init__(self, hass: object) -> None:
            self.hass = hass

        async def execute_with_resilience(self, func, *args, **kwargs):
            if args or kwargs:
                return await func(*args, **kwargs)
            return await func()

    stub_resilience.RetryConfig = RetryConfig
    stub_resilience.ResilienceManager = ResilienceManager

    monkeypatch.setitem(sys.modules, "custom_components", namespace_pkg)
    monkeypatch.setitem(sys.modules, "custom_components.pawcontrol", integration_pkg)
    monkeypatch.setitem(
        sys.modules, "custom_components.pawcontrol.exceptions", stub_exceptions
    )
    monkeypatch.setitem(
        sys.modules, "custom_components.pawcontrol.resilience", stub_resilience
    )

    module_path = (
        Path(__file__).resolve().parents[2]
        / "custom_components"
        / "pawcontrol"
        / "device_api.py"
    )
    spec = importlib.util.spec_from_file_location(
        "custom_components.pawcontrol.device_api_test", module_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.undo()
    return module


@pytest.mark.unit
def test_device_client_uses_injected_session(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """The device client should proxy requests through the shared session."""

    session = session_factory()
    response = Mock()
    response.status = 200
    response.json = AsyncMock(return_value={"status": "ok"})
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    payload = asyncio.run(client.async_get_json("/status"))

    session.request.assert_awaited_once()
    args, kwargs = session.request.await_args
    expected_url = client.base_url.join(device_api_module.URL("/status"))
    assert args == ("GET", expected_url)
    assert kwargs["headers"] is None
    assert kwargs["timeout"].total == pytest.approx(15.0)
    assert payload == {"status": "ok"}


@pytest.mark.unit
def test_device_client_rejects_missing_session(
    device_api_module: ModuleType,
) -> None:
    """Passing ``None`` should raise a descriptive error."""

    with pytest.raises(ValueError) as excinfo:
        device_api_module.PawControlDeviceClient(  # type: ignore[arg-type]
            session=None,
            endpoint="https://device.pawcontrol.invalid",
        )

    assert "requires Home Assistant's shared aiohttp ClientSession" in str(
        excinfo.value
    )


@pytest.mark.unit
def test_device_client_rejects_closed_session(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """Closed sessions must not be accepted."""

    session = session_factory(closed=True)

    with pytest.raises(ValueError) as excinfo:
        device_api_module.PawControlDeviceClient(
            session=session,
            endpoint="https://device.pawcontrol.invalid",
        )

    assert "received a closed aiohttp ClientSession" in str(excinfo.value)
