"""Tests for PawControl device API client helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.device_api import (
    PawControlDeviceClient,
    validate_device_endpoint,
)
from custom_components.pawcontrol.exceptions import (
    ConfigEntryAuthFailed,
    NetworkError,
    RateLimitError,
)


class _FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        json_payload: object | None = None,
        text_payload: str = "",
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._json_payload = json_payload if json_payload is not None else {}
        self._text_payload = text_payload

    async def json(self) -> object:
        return self._json_payload

    async def text(self) -> str:
        return self._text_payload


class _FakeSession:
    closed = False

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def request(self, *args: object, **kwargs: object) -> _FakeResponse:
        self.calls.append((args, kwargs))
        return self._response


def test_validate_device_endpoint_requires_http_and_hostname() -> None:
    """Endpoints should be normalized and validated."""
    url = validate_device_endpoint("https://example.test:443")
    assert str(url) == "https://example.test"

    with pytest.raises(ValueError, match="endpoint must use http or https"):
        validate_device_endpoint("ftp://example.test")

    with pytest.raises(ValueError, match="endpoint must include a valid hostname"):
        validate_device_endpoint("https:///missing-host")

    with pytest.raises(ValueError, match="endpoint must be provided"):
        validate_device_endpoint("")


@pytest.mark.asyncio
async def test_async_request_adds_authorization_header() -> None:
    """Requests should include bearer auth when an API key is configured."""
    session = _FakeSession(_FakeResponse(json_payload={"ok": True}))
    client = PawControlDeviceClient(
        session,
        endpoint="https://example.test",
        api_key="secret",
    )

    payload = await client.async_get_json("/api/status")

    assert payload == {"ok": True}
    args, kwargs = session.calls[0]
    assert args[:2] == ("GET", client.base_url.joinpath("api/status"))
    assert kwargs["headers"] == {"Authorization": "Bearer secret"}


@pytest.mark.asyncio
async def test_async_request_raises_auth_failed_on_401() -> None:
    """HTTP 401 from the device endpoint should map to auth failure."""
    session = _FakeSession(_FakeResponse(status=401))
    client = PawControlDeviceClient(session, endpoint="https://example.test")

    with pytest.raises(ConfigEntryAuthFailed):
        await client._async_request("GET", "/api/status")


@pytest.mark.asyncio
async def test_async_request_raises_rate_limit_with_retry_after_header() -> None:
    """HTTP 429 should include retry-after duration when provided."""
    session = _FakeSession(_FakeResponse(status=429, headers={"Retry-After": "12"}))
    client = PawControlDeviceClient(session, endpoint="https://example.test")

    with pytest.raises(RateLimitError) as err:
        await client._async_request("GET", "/api/status")

    assert err.value.retry_after == 12


@pytest.mark.asyncio
async def test_async_request_raises_network_error_for_http_failures() -> None:
    """HTTP errors should include endpoint status and body details."""
    session = _FakeSession(_FakeResponse(status=500, text_payload=" boom "))
    client = PawControlDeviceClient(session, endpoint="https://example.test")

    with pytest.raises(NetworkError, match="HTTP 500: boom"):
        await client._async_request("GET", "/api/status")


@pytest.mark.asyncio
async def test_async_get_json_uses_resilience_manager_when_available() -> None:
    """The resilience manager should wrap JSON fetches when configured."""
    response = _FakeResponse(json_payload={"dog": "Milo"})
    manager = SimpleNamespace(execute_with_resilience=AsyncMock(return_value=response))
    client = PawControlDeviceClient(
        _FakeSession(response),
        endpoint="https://example.test",
        resilience_manager=manager,
    )

    payload = await client.async_get_json("/api/dogs/1/feeding")

    assert payload == {"dog": "Milo"}
    manager.execute_with_resilience.assert_awaited_once()
    assert manager.execute_with_resilience.call_args.args[1:] == (
        "GET",
        "/api/dogs/1/feeding",
    )


@pytest.mark.asyncio
async def test_async_get_feeding_payload_uses_expected_resource_path() -> None:
    """Feeding payload helper should resolve to the dog feeding endpoint."""
    response = _FakeResponse(json_payload={"scheduled": True})
    client = PawControlDeviceClient(
        _FakeSession(response), endpoint="https://example.test"
    )
    client.async_get_json = AsyncMock(return_value={"scheduled": True})

    payload = await client.async_get_feeding_payload("dog-42")

    assert payload == {"scheduled": True}
    client.async_get_json.assert_awaited_once_with("/api/dogs/dog-42/feeding")


@pytest.mark.asyncio
async def test_async_request_protected_delegates_to_raw_request() -> None:
    """Protected request wrapper should delegate to the underlying request helper."""
    response = _FakeResponse(status=200)
    client = PawControlDeviceClient(
        _FakeSession(response), endpoint="https://example.test"
    )
    client._async_request = AsyncMock(return_value=response)

    result = await client._async_request_protected("GET", "/api/status")

    assert result is response
    client._async_request.assert_awaited_once_with("GET", "/api/status")
