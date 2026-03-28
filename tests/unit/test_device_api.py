"""Session reuse safeguards for the device API client."""

import asyncio
import importlib
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def device_api_module() -> ModuleType:
    """Load the device API helper module under test."""
    return importlib.import_module("custom_components.pawcontrol.device_api")


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
    assert payload == {"status": "ok"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "headers", "text", "expected_exc", "message"),
    [
        (401, {}, "", "ConfigEntryAuthFailed", "Authentication with Paw Control"),
        (429, {"Retry-After": "9"}, "", "RateLimitError", "device_api"),
        (500, {}, "  fail  ", "NetworkError", "HTTP 500: fail"),
    ],
)
def test_device_client_http_error_mapping(
    device_api_module: ModuleType,
    session_factory,
    status: int,
    headers: dict[str, str],
    text: str,
    expected_exc: str,
    message: str,
) -> None:
    """HTTP failures should map onto domain-specific exceptions."""
    session = session_factory()
    response = Mock()
    response.status = status
    response.headers = headers
    response.text = AsyncMock(return_value=text)
    response.json = AsyncMock(return_value={})
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    exc_type = getattr(device_api_module, expected_exc)
    with pytest.raises(exc_type) as excinfo:
        asyncio.run(client.async_get_json("/status"))

    assert message in str(excinfo.value)


@pytest.mark.unit
def test_device_client_rate_limit_uses_default_retry_after_when_invalid(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """Malformed Retry-After headers should fall back to default retry seconds."""
    session = session_factory()
    response = Mock()
    response.status = 429
    response.headers = {"Retry-After": "invalid"}
    response.text = AsyncMock(return_value="")
    response.json = AsyncMock(return_value={})
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    with pytest.raises(device_api_module.RateLimitError) as excinfo:
        asyncio.run(client.async_get_json("/status"))

    assert getattr(excinfo.value, "retry_after", None) == 60


@pytest.mark.unit
def test_device_client_non_json_payload_raises_network_error(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """Invalid JSON responses should surface as network errors."""
    session = session_factory()
    response = Mock()
    response.status = 200
    response.json = AsyncMock(side_effect=ValueError("bad json"))
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    with pytest.raises(device_api_module.NetworkError) as excinfo:
        asyncio.run(client.async_get_json("/status"))

    assert "non-JSON" in str(excinfo.value)


@pytest.mark.unit
def test_async_request_protected_delegates_to_request(
    device_api_module: ModuleType,
    session_factory,
) -> None:
    """Protected request wrapper should delegate to the shared request helper."""
    session = session_factory()
    response = Mock(status=200, headers={})
    session.request = AsyncMock(return_value=response)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    returned = asyncio.run(client._async_request_protected("GET", "/status"))

    assert returned is response
    session.request.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "expected_message"),
    [
        ("timeout", "Timed out while contacting"),
        ("client", "Client error talking"),
        ("os", "Network error talking"),
    ],
)
def test_device_client_transport_errors_raise_network_error(
    device_api_module: ModuleType,
    session_factory,
    kind: str,
    expected_message: str,
) -> None:
    """Transport exceptions should be normalized into ``NetworkError``."""
    session = session_factory()
    if kind == "timeout":
        side_effect = TimeoutError("slow")
    elif kind == "client":
        side_effect = device_api_module.ClientError("broken")
    else:
        side_effect = OSError("offline")

    session.request = AsyncMock(side_effect=side_effect)

    client = device_api_module.PawControlDeviceClient(
        session=session,
        endpoint="https://device.pawcontrol.invalid",
    )

    with pytest.raises(device_api_module.NetworkError) as excinfo:
        asyncio.run(client.async_get_json("/status"))

    assert expected_message in str(excinfo.value)
