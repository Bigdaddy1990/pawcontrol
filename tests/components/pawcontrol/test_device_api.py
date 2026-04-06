"""Tests for PawControl device API client helpers."""

from collections.abc import Mapping
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import ClientError, ClientTimeout
from aiohttp.client_exceptions import ContentTypeError
import pytest

from custom_components.pawcontrol.device_api import (
    PawControlDeviceClient,
    _coerce_json_mutable,
    validate_device_endpoint,
)
from custom_components.pawcontrol.exceptions import (
    ConfigEntryAuthFailed,
    NetworkError,
    RateLimitError,
)
from custom_components.pawcontrol.resilience import ResilienceManager, RetryConfig


def test_coerce_json_mutable_handles_none_and_mapping_inputs() -> None:
    """Coercion helper should normalize optional and mapping payloads."""
    assert _coerce_json_mutable(None) == {}
    assert _coerce_json_mutable({"dog": "Milo"}) == {"dog": "Milo"}

    mapping_view = {"steps": 3}.items().mapping
    assert _coerce_json_mutable(mapping_view) == {"steps": 3}


class _FakeResponse:
    _MISSING = object()

    def __init__(
        self,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        json_payload: object = _MISSING,
        text_payload: str = "",
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._json_payload = {} if json_payload is self._MISSING else json_payload
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


class _FailingSession:
    closed = False

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def request(self, *args: object, **kwargs: object) -> _FakeResponse:
        raise self._error


class _SequencedSession:
    closed = False

    def __init__(self, steps: list[_FakeResponse | Exception]) -> None:
        self._steps = steps
        self.call_count = 0

    async def request(self, *args: object, **kwargs: object) -> _FakeResponse:
        self.call_count += 1
        step = self._steps[self.call_count - 1]
        if isinstance(step, Exception):
            raise step
        return step


class _MappingPayload(Mapping[str, object]):
    """Simple mapping implementation used to exercise mapping coercion paths."""

    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> object:
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


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
async def test_async_request_rate_limit_defaults_to_60_when_header_is_invalid() -> None:
    """HTTP 429 should fall back to 60 seconds for non-numeric Retry-After values."""
    session = _FakeSession(_FakeResponse(status=429, headers={"Retry-After": "later"}))
    client = PawControlDeviceClient(session, endpoint="https://example.test")

    with pytest.raises(RateLimitError) as err:
        await client._async_request("GET", "/api/status")

    assert err.value.retry_after == 60


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
    assert manager.execute_with_resilience.call_args.kwargs == {
        "circuit_breaker_name": "device_api_request",
        "retry_config": client._retry_config,
    }


@pytest.mark.asyncio
async def test_async_get_json_without_api_key_sends_no_headers() -> None:
    """Requests should not include auth headers when no API key is configured."""
    session = _FakeSession(_FakeResponse(json_payload={"ok": True}))
    client = PawControlDeviceClient(session, endpoint="https://example.test")

    await client.async_get_json("/api/status")

    _, kwargs = session.calls[0]
    assert kwargs["headers"] is None


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
async def test_async_get_json_passes_timeout_configuration_to_session() -> None:
    """Raw request path should forward custom timeout values unchanged."""
    timeout = ClientTimeout(total=42.0)
    session = _FakeSession(_FakeResponse(json_payload={"ok": True}))
    client = PawControlDeviceClient(
        session,
        endpoint="https://example.test",
        timeout=timeout,
    )

    await client.async_get_json("/api/status")

    _, kwargs = session.calls[0]
    assert kwargs["timeout"] is timeout


@pytest.mark.asyncio
async def test_async_get_json_coerces_none_payload_to_empty_mapping() -> None:
    """JSON helper should normalise null payloads into mutable empty mappings."""
    session = _FakeSession(_FakeResponse(json_payload=None))
    client = PawControlDeviceClient(session, endpoint="https://example.test")

    assert await client.async_get_json("/api/status") == {}


@pytest.mark.asyncio
async def test_async_get_json_coerces_mapping_payload_to_mutable_mapping() -> None:
    """JSON helper should copy generic mappings into mutable dict payloads."""
    session = _FakeSession(_FakeResponse(json_payload=_MappingPayload({"ok": True})))
    client = PawControlDeviceClient(session, endpoint="https://example.test")

    payload = await client.async_get_json("/api/status")

    assert payload == {"ok": True}
    assert isinstance(payload, dict)


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


@pytest.mark.asyncio
async def test_async_request_maps_transport_exceptions_to_network_error() -> None:
    """Transport exceptions should be normalized into network errors."""
    timeout_client = PawControlDeviceClient(
        _FailingSession(TimeoutError()),
        endpoint="https://example.test",
    )
    with pytest.raises(NetworkError, match="Timed out while contacting"):
        await timeout_client._async_request("GET", "/api/status")

    client_error_client = PawControlDeviceClient(
        _FailingSession(ClientError("boom")),
        endpoint="https://example.test",
    )
    with pytest.raises(NetworkError, match="Client error talking to device API"):
        await client_error_client._async_request("GET", "/api/status")

    os_error_client = PawControlDeviceClient(
        _FailingSession(OSError("offline")),
        endpoint="https://example.test",
    )
    with pytest.raises(NetworkError, match="Network error talking to device API"):
        await os_error_client._async_request("GET", "/api/status")


@pytest.mark.asyncio
async def test_async_get_json_raises_network_error_for_non_json_payload() -> None:
    """Invalid JSON responses should raise a normalized network error."""

    class _NonJsonResponse(_FakeResponse):
        async def json(self) -> object:
            request_info = SimpleNamespace(real_url="https://example.test/api/status")
            raise ContentTypeError(
                request_info=request_info,
                history=(),
                message="Not JSON",
            )

    session = _FakeSession(_NonJsonResponse())
    client = PawControlDeviceClient(session, endpoint="https://example.test")

    with pytest.raises(NetworkError, match="non-JSON response"):
        await client.async_get_json("/api/status")


@pytest.mark.asyncio
async def test_async_get_json_raises_network_error_for_unexpected_payload_type() -> (
    None
):
    """List payloads should be rejected as unexpected API responses."""
    session = _FakeSession(_FakeResponse(json_payload=[{"dog": "Milo"}]))
    client = PawControlDeviceClient(session, endpoint="https://example.test")

    with pytest.raises(NetworkError, match="unexpected response payload"):
        await client.async_get_json("/api/status")


@pytest.mark.asyncio
async def test_async_get_json_retries_network_errors_with_deterministic_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resilience path should retry transient failures using configured delay."""
    session = _SequencedSession([
        TimeoutError(),
        _FakeResponse(json_payload={"ok": True}),
    ])
    client = PawControlDeviceClient(
        session,
        endpoint="https://example.test",
        resilience_manager=ResilienceManager(),
    )
    client._retry_config = RetryConfig(
        max_attempts=2,
        initial_delay=0.25,
        max_delay=1.0,
        exponential_base=2.0,
        jitter=False,
    )
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("custom_components.pawcontrol.resilience.asyncio.sleep", _sleep)

    payload = await client.async_get_json("/api/status")

    assert payload == {"ok": True}
    assert session.call_count == 2
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_async_get_json_does_not_retry_auth_failures() -> None:
    """Authentication failures are non-retryable and should bubble immediately."""
    session = _SequencedSession([
        _FakeResponse(status=401),
        _FakeResponse(json_payload={"unexpected": "retry"}),
    ])
    client = PawControlDeviceClient(
        session,
        endpoint="https://example.test",
        resilience_manager=ResilienceManager(),
    )
    client._retry_config = RetryConfig(max_attempts=3, jitter=False)

    with pytest.raises(ConfigEntryAuthFailed):
        await client.async_get_json("/api/status")

    assert session.call_count == 1


@pytest.mark.asyncio
async def test_async_get_json_propagates_rate_limit_error_without_json_parsing() -> (
    None
):
    """Guard path should bubble API throttling errors immediately."""
    client = PawControlDeviceClient(
        _FakeSession(_FakeResponse(status=429)),
        endpoint="https://example.test",
    )

    with pytest.raises(RateLimitError):
        await client.async_get_json("/api/status")
