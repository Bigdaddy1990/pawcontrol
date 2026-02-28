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
    """Load the device API helper without importing the integration package."""
    monkeypatch = MonkeyPatch()
    ha_module = ModuleType("homeassistant")
    ha_exceptions = ModuleType("homeassistant.exceptions")

    class ConfigEntryAuthFailedError(Exception):
        """Stubbed Home Assistant auth error."""

    ha_exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailedError
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

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args)
            self.kwargs = kwargs

    stub_exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailedError
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


@pytest.mark.unit
def test_validate_device_endpoint_rejects_invalid_values(
    device_api_module: ModuleType,
) -> None:
    """Endpoint validation should reject empty, hostless, and unsupported URLs."""
    with pytest.raises(ValueError, match="endpoint must be provided"):
        device_api_module.validate_device_endpoint("")

    with pytest.raises(ValueError, match="http or https"):
        device_api_module.validate_device_endpoint("ftp://example.com")

    with pytest.raises(ValueError, match="valid hostname"):
        device_api_module.validate_device_endpoint("https://")


@pytest.mark.unit
def test_validate_device_endpoint_accepts_http_and_https(
    device_api_module: ModuleType,
) -> None:
    """Endpoint validation should preserve valid URLs."""
    https_endpoint = device_api_module.validate_device_endpoint(
        "https://device.pawcontrol.invalid",
    )
    http_endpoint = device_api_module.validate_device_endpoint(
        "http://device.pawcontrol.invalid:8123",
    )

    assert str(https_endpoint) == "https://device.pawcontrol.invalid"
    assert str(http_endpoint) == "http://device.pawcontrol.invalid:8123"


@pytest.mark.unit
def test_device_client_forwards_bearer_token_and_feeding_path(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """The client should include auth headers and compose feeding endpoint paths."""
    session = session_factory()
    response = Mock()
    response.status = 200
    response.json = AsyncMock(return_value={"feeding": "ok"})
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
        api_key="secret",
    )

    payload = asyncio.run(client.async_get_feeding_payload("dog-123"))

    args, kwargs = session.request.await_args
    expected_url = client.base_url.join(
        device_api_module.URL("/api/dogs/dog-123/feeding")
    )
    assert args == ("GET", expected_url)
    assert kwargs["headers"] == {"Authorization": "Bearer secret"}
    assert payload == {"feeding": "ok"}


@pytest.mark.unit
def test_device_client_uses_resilience_manager_when_configured(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """When available, resilience manager should execute protected request path."""
    session = session_factory()
    response = Mock()
    response.status = 200
    response.json = AsyncMock(return_value={"status": "ok"})

    manager = Mock()
    manager.execute_with_resilience = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
        resilience_manager=manager,
    )

    payload = asyncio.run(client.async_get_json("/status"))

    manager.execute_with_resilience.assert_awaited_once()
    args, kwargs = manager.execute_with_resilience.await_args
    assert args[:3] == (client._async_request_protected, "GET", "/status")
    assert kwargs["circuit_breaker_name"] == "device_api_request"
    assert kwargs["retry_config"] is client._retry_config
    assert payload == {"status": "ok"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "headers", "body", "expected_exc", "message"),
    [
        (401, {}, "", "ConfigEntryAuthFailed", "Authentication with Paw Control"),
        (429, {"Retry-After": "120"}, "", "RateLimitError", "device_api"),
        (500, {}, "  fail  ", "NetworkError", "HTTP 500: fail"),
    ],
)
def test_device_client_http_error_mapping(
    device_api_module: ModuleType,
    session_factory,
    status: int,
    headers: dict[str, str],
    body: str,
    expected_exc: str,
    message: str,
) -> None:
    """HTTP status codes should be translated to integration exception types."""
    session = session_factory()
    response = Mock()
    response.status = status
    response.headers = headers
    response.text = AsyncMock(return_value=body)
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    exception_type = getattr(device_api_module, expected_exc)
    with pytest.raises(exception_type) as excinfo:
        asyncio.run(client.async_get_json("/status"))

    assert message in str(excinfo.value)


@pytest.mark.unit
def test_device_client_rate_limit_uses_default_retry_after_when_invalid(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """Rate-limit responses without a valid ``Retry-After`` should default to 60s."""
    session = session_factory()
    response = Mock()
    response.status = 429
    response.headers = {"Retry-After": "not-a-number"}
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    with pytest.raises(device_api_module.RateLimitError) as excinfo:
        asyncio.run(client.async_get_json("/status"))

    assert excinfo.value.kwargs["retry_after"] == 60


@pytest.mark.unit
def test_device_client_non_json_payload_raises_network_error(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """Non-JSON responses should be translated to ``NetworkError``."""
    session = session_factory()
    response = Mock()
    response.status = 200
    response.json = AsyncMock(side_effect=ValueError("not-json"))
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    with pytest.raises(device_api_module.NetworkError, match="non-JSON"):
        asyncio.run(client.async_get_json("/status"))


@pytest.mark.unit
def test_async_request_protected_delegates_to_request(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """Protected request wrapper should delegate directly to the request helper."""
    session = session_factory()
    response = Mock()
    response.status = 200
    response.json = AsyncMock(return_value={"status": "ok"})
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    result = asyncio.run(client._async_request_protected("GET", "/status"))

    assert result is response


@pytest.mark.unit
@pytest.mark.parametrize(
    ("error_kind", "message"),
    [
        ("timeout", "Timed out while contacting"),
        ("client", "Client error talking"),
        ("os", "Network error talking"),
    ],
)
def test_device_client_transport_errors_raise_network_error(
    device_api_module: ModuleType,
    session_factory,
    error_kind: str,
    message: str,
) -> None:
    """Transport-level failures should map to NetworkError with clear messaging."""
    if error_kind == "timeout":
        raised_error: Exception = TimeoutError()
    elif error_kind == "client":
        raised_error = device_api_module.ClientError("broken")
    else:
        raised_error = OSError("offline")

    session = session_factory()
    session.request = AsyncMock(side_effect=raised_error)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    with pytest.raises(device_api_module.NetworkError, match=message):
        asyncio.run(client.async_get_json("/status"))
