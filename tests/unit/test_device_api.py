"""Session reuse safeguards for the device API client."""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest
from pytest import MonkeyPatch


@pytest.fixture(scope="module")
def device_api_module() -> ModuleType:
    """Load the device API helper without importing the integration package."""  # noqa: E111

    monkeypatch = MonkeyPatch()  # noqa: E111
    ha_module = ModuleType("homeassistant")  # noqa: E111
    ha_exceptions = ModuleType("homeassistant.exceptions")  # noqa: E111

    class ConfigEntryAuthFailedError(Exception):  # noqa: E111
        """Stubbed Home Assistant auth error."""

    ha_exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailedError  # noqa: E111
    ha_module.exceptions = ha_exceptions  # noqa: E111
    monkeypatch.setitem(sys.modules, "homeassistant", ha_module)  # noqa: E111
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", ha_exceptions)  # noqa: E111

    namespace_pkg = ModuleType("custom_components")  # noqa: E111
    namespace_pkg.__path__ = [  # noqa: E111
        str(Path(__file__).resolve().parents[2] / "custom_components")
    ]
    integration_pkg = ModuleType("custom_components.pawcontrol")  # noqa: E111
    integration_pkg.__path__ = [  # noqa: E111
        str(Path(__file__).resolve().parents[2] / "custom_components" / "pawcontrol")
    ]
    stub_exceptions = ModuleType("custom_components.pawcontrol.exceptions")  # noqa: E111
    stub_resilience = ModuleType("custom_components.pawcontrol.resilience")  # noqa: E111

    class NetworkError(Exception):  # noqa: E111
        """Stubbed network error."""

    class RateLimitError(Exception):  # noqa: E111
        """Stubbed rate limit error."""

    stub_exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailedError  # noqa: E111
    stub_exceptions.NetworkError = NetworkError  # noqa: E111
    stub_exceptions.RateLimitError = RateLimitError  # noqa: E111

    class RetryConfig:  # pragma: no cover - simple stub  # noqa: E111
        """Minimal RetryConfig replacement for tests."""

        def __init__(self, **kwargs: object) -> None:
            self.options = kwargs  # noqa: E111

    class ResilienceManager:  # pragma: no cover - simple stub  # noqa: E111
        """Stubbed resilience manager used in tests."""

        def __init__(self, hass: object) -> None:
            self.hass = hass  # noqa: E111

        async def execute_with_resilience(self, func, *args, **kwargs):
            if args or kwargs:  # noqa: E111
                return await func(*args, **kwargs)
            return await func()  # noqa: E111

    stub_resilience.RetryConfig = RetryConfig  # noqa: E111
    stub_resilience.ResilienceManager = ResilienceManager  # noqa: E111

    monkeypatch.setitem(sys.modules, "custom_components", namespace_pkg)  # noqa: E111
    monkeypatch.setitem(sys.modules, "custom_components.pawcontrol", integration_pkg)  # noqa: E111
    monkeypatch.setitem(  # noqa: E111
        sys.modules, "custom_components.pawcontrol.exceptions", stub_exceptions
    )
    monkeypatch.setitem(  # noqa: E111
        sys.modules, "custom_components.pawcontrol.resilience", stub_resilience
    )

    module_path = (  # noqa: E111
        Path(__file__).resolve().parents[2]
        / "custom_components"
        / "pawcontrol"
        / "device_api.py"
    )
    spec = importlib.util.spec_from_file_location(  # noqa: E111
        "custom_components.pawcontrol.device_api_test", module_path
    )
    assert spec and spec.loader  # noqa: E111
    module = importlib.util.module_from_spec(spec)  # noqa: E111
    sys.modules[spec.name] = module  # noqa: E111
    spec.loader.exec_module(module)  # noqa: E111
    monkeypatch.undo()  # noqa: E111
    return module  # noqa: E111


@pytest.mark.unit
def test_device_client_uses_injected_session(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """The device client should proxy requests through the shared session."""  # noqa: E111

    session = session_factory()  # noqa: E111
    response = Mock()  # noqa: E111
    response.status = 200  # noqa: E111
    response.json = AsyncMock(return_value={"status": "ok"})  # noqa: E111
    session.request = AsyncMock(return_value=response)  # noqa: E111

    client = device_api_module.PawControlDeviceClient(  # noqa: E111
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    payload = asyncio.run(client.async_get_json("/status"))  # noqa: E111

    session.request.assert_awaited_once()  # noqa: E111
    args, kwargs = session.request.await_args  # noqa: E111
    expected_url = client.base_url.join(device_api_module.URL("/status"))  # noqa: E111
    assert args == ("GET", expected_url)  # noqa: E111
    assert kwargs["headers"] is None  # noqa: E111
    assert kwargs["timeout"].total == pytest.approx(15.0)  # noqa: E111
    assert payload == {"status": "ok"}  # noqa: E111


@pytest.mark.unit
def test_device_client_rejects_missing_session(
    device_api_module: ModuleType,
) -> None:
    """Passing ``None`` should raise a descriptive error."""  # noqa: E111

    with pytest.raises(ValueError) as excinfo:  # noqa: E111
        device_api_module.PawControlDeviceClient(  # type: ignore[arg-type]
            session=None,
            endpoint="https://device.pawcontrol.invalid",
        )

    assert "requires Home Assistant's shared aiohttp ClientSession" in str(
        excinfo.value
    )  # noqa: E111


@pytest.mark.unit
def test_device_client_rejects_closed_session(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """Closed sessions must not be accepted."""  # noqa: E111

    session = session_factory(closed=True)  # noqa: E111

    with pytest.raises(ValueError) as excinfo:  # noqa: E111
        device_api_module.PawControlDeviceClient(
            session=session,
            endpoint="https://device.pawcontrol.invalid",
        )

    assert "received a closed aiohttp ClientSession" in str(excinfo.value)  # noqa: E111
