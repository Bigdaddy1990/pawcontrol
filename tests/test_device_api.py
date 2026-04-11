"""Unit tests for device API HTTP helpers."""

from typing import Any

from aiohttp import ClientError
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


class _Response:
    def __init__(
        self,
        *,
        status: int = 200,
        payload: Any | None = None,
        text_payload: str = "",
        headers: dict[str, str] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._payload = payload
        self._text_payload = text_payload
        self.headers = headers or {}
        self._json_error = json_error

    async def json(self) -> Any:
        if self._json_error:
            raise self._json_error
        return self._payload

    async def text(self) -> str:
        return self._text_payload


class _Session:
    def __init__(self, response: _Response | Exception) -> None:
        self.closed = False
        self._response = response
        self.calls: list[tuple[str, Any, Any, Any]] = []

    async def request(
        self,
        method: str,
        url: Any,
        *,
        timeout: Any = None,
        headers: dict[str, str] | None = None,
    ) -> _Response:
        self.calls.append((method, url, timeout, headers))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


@pytest.mark.parametrize("endpoint", ["http://example.com", "https://example.com"])
def test_validate_device_endpoint_accepts_http_and_https(endpoint: str) -> None:
    assert str(validate_device_endpoint(endpoint)) == endpoint


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        ("", "endpoint must be provided for device client"),
        ("ftp://example.com", "endpoint must use http or https scheme"),
        ("http:///path", "endpoint must include a valid hostname"),
    ],
)
def test_validate_device_endpoint_rejects_invalid_values(
    endpoint: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_device_endpoint(endpoint)


@pytest.mark.asyncio
async def test_async_request_adds_bearer_header_and_returns_response() -> None:
    session = _Session(_Response(status=200, payload={"ok": True}))
    client = PawControlDeviceClient(
        session,
        endpoint="https://device.local",
        api_key="abc123",
    )

    response = await client._async_request("GET", "/api/status")

    assert response.status == 200
    method, url, _, headers = session.calls[0]
    assert method == "GET"
    assert str(url) == "https://device.local/api/status"
    assert headers == {"Authorization": "Bearer abc123"}


@pytest.mark.asyncio
async def test_async_request_raises_auth_failed_for_401() -> None:
    client = PawControlDeviceClient(
        _Session(_Response(status=401)), endpoint="https://device.local"
    )

    with pytest.raises(
        ConfigEntryAuthFailed, match="Authentication with Paw Control device failed"
    ):
        await client._async_request("GET", "/api/status")


@pytest.mark.asyncio
async def test_async_request_raises_rate_limit_and_parses_retry_after() -> None:
    client = PawControlDeviceClient(
        _Session(_Response(status=429, headers={"Retry-After": "12"})),
        endpoint="https://device.local",
    )

    with pytest.raises(RateLimitError) as err:
        await client._async_request("GET", "/api/status")

    assert err.value.retry_after == 12


@pytest.mark.asyncio
async def test_async_request_raises_network_error_on_http_failure() -> None:
    client = PawControlDeviceClient(
        _Session(_Response(status=500, text_payload=" boom ")),
        endpoint="https://device.local",
    )

    with pytest.raises(NetworkError, match="Device API returned HTTP 500: boom"):
        await client._async_request("GET", "/api/status")


@pytest.mark.asyncio
async def test_async_request_maps_timeout_error_to_network_error() -> None:
    client = PawControlDeviceClient(
        _Session(TimeoutError("timed out")),
        endpoint="https://device.local",
    )

    with pytest.raises(
        NetworkError, match="Timed out while contacting the Paw Control device API"
    ):
        await client._async_request("GET", "/api/status")


@pytest.mark.asyncio
async def test_async_get_json_maps_invalid_json_to_network_error() -> None:
    client = PawControlDeviceClient(
        _Session(_Response(status=200, json_error=ValueError("invalid"))),
        endpoint="https://device.local",
    )

    with pytest.raises(NetworkError, match="Device API returned a non-JSON response"):
        await client.async_get_json("/api/status")


@pytest.mark.asyncio
async def test_async_get_json_rejects_non_mapping_payloads() -> None:
    """List/primitive JSON responses should fail with a stable network error."""
    client = PawControlDeviceClient(
        _Session(_Response(status=200, payload=["unexpected"])),
        endpoint="https://device.local",
    )

    with pytest.raises(NetworkError, match="unexpected response payload"):
        await client.async_get_json("/api/status")


@pytest.mark.asyncio
async def test_async_get_json_coerces_mapping_payload_to_mutable_copy() -> None:
    """Mapping payloads should be returned as a detached mutable dict."""

    class _ReadOnlyMapping(dict[str, Any]):
        pass

    payload = _ReadOnlyMapping({"status": "ok"})
    client = PawControlDeviceClient(
        _Session(_Response(status=200, payload=payload)),
        endpoint="https://device.local",
    )

    result = await client.async_get_json("/api/status")

    assert result == {"status": "ok"}
    assert result is not payload


@pytest.mark.asyncio
async def test_async_get_json_uses_resilience_manager_when_available() -> None:
    response = _Response(status=200, payload={"status": "ok"})
    session = _Session(response)

    class _ResilienceManager:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        async def execute_with_resilience(self, func, method: str, path: str, **kwargs):
            self.calls.append((func.__name__, method, path))
            assert kwargs["circuit_breaker_name"] == "device_api_request"
            return response

    resilience = _ResilienceManager()
    client = PawControlDeviceClient(
        session,
        endpoint="https://device.local",
        resilience_manager=resilience,
    )

    payload = await client.async_get_json("/api/status")

    assert payload == {"status": "ok"}
    assert resilience.calls == [("_async_request_protected", "GET", "/api/status")]
    assert session.calls == []


@pytest.mark.asyncio
async def test_async_request_without_api_key_omits_authorization_header() -> None:
    """Requests without API keys should not send an Authorization header."""
    session = _Session(_Response(status=200, payload={"ok": True}))
    client = PawControlDeviceClient(session, endpoint="https://device.local")

    await client._async_request("GET", "/api/status")

    _, _, _, headers = session.calls[0]
    assert headers is None


@pytest.mark.asyncio
async def test_async_request_uses_default_retry_after_when_missing() -> None:
    """429 responses without Retry-After should default to 60 seconds."""
    client = PawControlDeviceClient(
        _Session(_Response(status=429, headers={})),
        endpoint="https://device.local",
    )

    with pytest.raises(RateLimitError) as err:
        await client._async_request("GET", "/api/status")

    assert err.value.retry_after == 60


@pytest.mark.asyncio
async def test_async_request_maps_client_and_os_errors_to_network_error() -> None:
    """Transport-level client and socket errors should normalize to NetworkError."""
    for error in (ClientError("broken"), OSError("offline")):
        client = PawControlDeviceClient(
            _Session(error),
            endpoint="https://device.local",
        )

        with pytest.raises(NetworkError):
            await client._async_request("GET", "/api/status")


@pytest.mark.asyncio
async def test_endpoint_property_and_wrapper_helpers_delegate_to_async_request() -> (
    None
):
    """Thin helper methods should delegate to the shared request implementation."""
    session = _Session(_Response(status=200, payload={"ok": True}))
    client = PawControlDeviceClient(session, endpoint="https://device.local")

    assert str(client.base_url) == "https://device.local"

    protected = await client._async_request_protected("GET", "/api/status")
    assert protected.status == 200

    async def _fake_get_json(path: str) -> dict[str, str]:
        assert path == "/api/dogs/fido/feeding"
        return {"dog": "fido"}

    client.async_get_json = _fake_get_json  # type: ignore[method-assign]
    payload = await client.async_get_feeding_payload("fido")

    assert payload == {"dog": "fido"}
