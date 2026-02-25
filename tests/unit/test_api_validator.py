from collections.abc import Generator, Iterable
from types import TracebackType
from typing import TypeAlias, cast

import aiohttp
from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol.api_validator import (
    APIValidationResult,
    APIValidator,
    JSONValue,
    _extract_capabilities,
)

type DummyPayload = dict[str, JSONValue]


class DummyResponse:
    """Minimal async context manager used to emulate aiohttp responses."""

    def __init__(
        self,
        status: int,
        payload: DummyPayload | None = None,
        *,
        json_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._payload: DummyPayload = payload or {}
        self._json_error = json_error

    async def __aenter__(self) -> DummyResponse:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    async def json(self) -> DummyPayload:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class DummyRequestContext:
    """Awaitable context manager matching aiohttp's request API."""

    def __init__(self, response: DummyResponse) -> None:
        self._response = response

    def __await__(self) -> Generator[DummyResponse, None, DummyResponse]:
        async def _inner() -> DummyResponse:
            return self._response

        return _inner().__await__()

    async def __aenter__(self) -> DummyResponse:
        return await self._response.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return await self._response.__aexit__(exc_type, exc, tb)


class DummySession:
    """Session stub accepted by :func:`ensure_shared_client_session`."""

    closed = False

    def __init__(self, responses: Iterable[DummyResponse]) -> None:
        self._responses: list[DummyResponse] = list(responses)
        self._index: int = 0

    async def request(self, *args: object, **kwargs: object) -> DummyResponse:
        context = self.get(*args, **kwargs)
        return await context

    def get(self, *args: object, **kwargs: object) -> DummyRequestContext:
        if self._index >= len(self._responses):
            raise AssertionError(
                "DummySession received more get() calls than configured responses"
            )
        response = self._responses[self._index]
        self._index += 1
        return DummyRequestContext(response)


class RaisingSession:
    """Session stub that raises when issuing HTTP GET requests."""

    closed = False

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def request(self, *args: object, **kwargs: object) -> DummyResponse:
        context = self.get(*args, **kwargs)
        return await context

    def get(self, *args: object, **kwargs: object) -> DummyRequestContext:
        raise self._error


class FlakySession(DummySession):
    """Session stub that fails once before returning configured responses."""

    def __init__(self, responses: Iterable[DummyResponse]) -> None:
        super().__init__(responses)
        self._attempts = 0

    def get(self, *args: object, **kwargs: object) -> DummyRequestContext:
        self._attempts += 1
        if self._attempts == 1:
            raise aiohttp.ClientError("temporary failure")
        return super().get(*args, **kwargs)


@pytest.mark.asyncio
async def test_async_validate_api_connection_filters_capabilities(
    hass: HomeAssistant,
) -> None:
    """Only string capabilities from the JSON payload should be exposed."""
    session = DummySession([
        DummyResponse(200),
        DummyResponse(
            200, {"version": "1.2.3", "capabilities": ["status", 42, "metrics"]}
        ),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))

    result = await validator.async_validate_api_connection(
        "https://example.test", "secret-token"
    )

    assert result.valid is True
    assert result.api_version == "1.2.3"
    assert result.capabilities == ["status", "metrics"]


@pytest.mark.asyncio
async def test_async_validate_api_connection_accepts_tuple_capabilities(
    hass: HomeAssistant,
) -> None:
    """Tuple-based capability payloads should normalise to list[str]."""
    session = DummySession([
        DummyResponse(200),
        DummyResponse(
            200,
            {
                "version": "9.9.9",
                "capabilities": ("status", {"ignored": True}, "insights"),
            },
        ),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))

    result = await validator.async_validate_api_connection(
        "https://example.test", "secret-token"
    )

    assert result.valid is True
    assert result.capabilities == ["status", "insights"]


@pytest.mark.asyncio
async def test_async_validate_api_connection_handles_json_failure(
    hass: HomeAssistant,
) -> None:
    """Successful authentication without JSON keeps optional fields ``None``."""
    session = DummySession([
        DummyResponse(200),
        DummyResponse(200, json_error=ValueError("boom")),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))

    result = await validator.async_validate_api_connection(
        "https://example.test", "secret-token"
    )

    assert result.valid is True
    assert result.api_version is None
    assert result.capabilities is None


@pytest.mark.asyncio
async def test_async_validate_api_connection_supports_empty_capabilities(
    hass: HomeAssistant,
) -> None:
    """An empty capabilities array should normalise to an empty list."""
    session = DummySession([
        DummyResponse(200),
        DummyResponse(200, {"version": "2.0.0", "capabilities": []}),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))

    result = await validator.async_validate_api_connection(
        "https://example.test", "secret-token"
    )

    assert result.valid is True
    assert result.capabilities == []


@pytest.mark.asyncio
async def test_async_test_api_health_authentication_failure(
    hass: HomeAssistant,
) -> None:
    """Authentication errors should surface a dedicated health status."""
    session = DummySession([
        DummyResponse(200),
        DummyResponse(401),
        DummyResponse(401),
        DummyResponse(401),
        DummyResponse(401),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))

    health = await validator.async_test_api_health(
        "https://example.test", "secret-token"
    )

    assert health["healthy"] is False
    assert health["reachable"] is True
    assert health["status"] == "authentication_failed"
    assert health["capabilities"] is None


@pytest.mark.asyncio
async def test_test_endpoint_reachability_handles_client_error(
    hass: HomeAssistant,
) -> None:
    """Client errors should report the endpoint as unreachable."""
    session = RaisingSession(aiohttp.ClientError("network down"))
    validator = APIValidator(hass, cast(ClientSession, session))

    assert await validator._test_endpoint_reachability("https://example.test") is False


@pytest.mark.asyncio
async def test_test_endpoint_reachability_handles_unexpected_error(
    hass: HomeAssistant,
) -> None:
    """Unexpected errors should also report the endpoint as unreachable."""
    session = RaisingSession(RuntimeError("boom"))
    validator = APIValidator(hass, cast(ClientSession, session))

    assert await validator._test_endpoint_reachability("https://example.test") is False


@pytest.mark.asyncio
async def test_async_test_api_health_reports_timeout(hass: HomeAssistant) -> None:
    """Health checks should map timeouts to ``status=timeout`` payloads."""
    session = DummySession([])
    validator = APIValidator(hass, cast(ClientSession, session))

    async def _raise_timeout(*args: object, **kwargs: object) -> object:
        raise TimeoutError

    validator.async_validate_api_connection = _raise_timeout  # type: ignore[method-assign]

    health = await validator.async_test_api_health("https://example.test")

    assert health["healthy"] is False
    assert health["status"] == "timeout"
    assert health["error"] == "Health check timeout"


@pytest.mark.asyncio
async def test_async_test_api_health_reports_unexpected_errors(
    hass: HomeAssistant,
) -> None:
    """Unexpected health-check failures should return an error payload."""
    session = DummySession([])
    validator = APIValidator(hass, cast(ClientSession, session))

    async def _raise_runtime_error(*args: object, **kwargs: object) -> object:
        raise RuntimeError("validation exploded")

    validator.async_validate_api_connection = _raise_runtime_error  # type: ignore[method-assign]

    health = await validator.async_test_api_health("https://example.test")

    assert health["healthy"] is False
    assert health["status"] == "error"
    assert health["error"] == "validation exploded"


class CapturingSession(DummySession):
    """Session stub that records GET call arguments for assertions."""

    def __init__(self, responses: Iterable[DummyResponse]) -> None:
        super().__init__(responses)
        self.calls: list[tuple[object, dict[str, object]]] = []

    def get(self, *args: object, **kwargs: object) -> DummyRequestContext:
        self.calls.append((args[0] if args else None, dict(kwargs)))
        return super().get(*args, **kwargs)


def test_validate_endpoint_format_validates_required_parts(
    hass: HomeAssistant,
) -> None:
    """Endpoint validation should require scheme and netloc."""
    validator = APIValidator(hass, cast(ClientSession, DummySession([])))

    assert validator._validate_endpoint_format("https://example.test") is True
    assert validator._validate_endpoint_format("http://127.0.0.1:8123") is True
    assert validator._validate_endpoint_format("example.test") is False
    assert validator._validate_endpoint_format("https:///missing-host") is False


@pytest.mark.asyncio
async def test_test_endpoint_reachability_respects_ssl_override(
    hass: HomeAssistant,
) -> None:
    """Reachability checks should forward the configured ssl override."""
    session = CapturingSession([DummyResponse(200)])
    validator = APIValidator(hass, cast(ClientSession, session), verify_ssl=False)

    reachable = await validator._test_endpoint_reachability("https://example.test")

    assert reachable is True
    assert session.calls[0][0] == "https://example.test"
    assert session.calls[0][1] == {"allow_redirects": True, "ssl": False}


@pytest.mark.asyncio
async def test_test_authentication_handles_non_mapping_json_payload(
    hass: HomeAssistant,
) -> None:
    """Authentication should succeed even when JSON payload is not a mapping."""
    session = CapturingSession([
        DummyResponse(200, cast(DummyPayload, {"ignored": True})),
    ])
    validator = APIValidator(hass, cast(ClientSession, session), verify_ssl=False)

    result = await validator._test_authentication("https://example.test", "token")

    assert result == {
        "authenticated": True,
        "api_version": None,
        "capabilities": None,
    }
    assert session.calls[0][0] == "https://example.test/auth/validate"
    assert session.calls[0][1]["ssl"] is False


@pytest.mark.asyncio
async def test_async_close_keeps_shared_session_open(hass: HomeAssistant) -> None:
    """APIValidator should never close shared Home Assistant sessions."""
    session = DummySession([])
    validator = APIValidator(hass, cast(ClientSession, session))

    await validator.async_close()

    assert session.closed is False


def test_session_property_returns_configured_session(hass: HomeAssistant) -> None:
    """The public session property should expose the shared session reference."""
    session = DummySession([])
    validator = APIValidator(hass, cast(ClientSession, session))

    assert validator.session is session


@pytest.mark.asyncio
async def test_async_validate_api_connection_unreachable_endpoint(
    hass: HomeAssistant,
) -> None:
    """Validation should stop when the reachability probe reports False."""
    session = DummySession([])
    validator = APIValidator(hass, cast(ClientSession, session))

    async def _unreachable(*args: object, **kwargs: object) -> bool:
        return False

    validator._test_endpoint_reachability = _unreachable  # type: ignore[method-assign]
    result = await validator.async_validate_api_connection("https://example.test")

    assert result.valid is False
    assert result.reachable is False
    assert result.error_message == "API endpoint not reachable"


def test_validate_endpoint_format_handles_non_string_and_parse_errors(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Endpoint validation should reject invalid types and parser failures."""
    validator = APIValidator(hass, cast(ClientSession, DummySession([])))

    assert validator._validate_endpoint_format(cast(str, 123)) is False

    def _explode(_: str) -> object:
        raise ValueError("bad url")

    monkeypatch.setattr("urllib.parse.urlparse", _explode)
    assert validator._validate_endpoint_format("https://example.test") is False


@pytest.mark.asyncio
async def test_test_authentication_non_mapping_payload_and_retry(
    hass: HomeAssistant,
) -> None:
    """Authentication should continue after client errors and accept list JSON."""
    session = FlakySession([DummyResponse(200, cast(DummyPayload, ["ok"]))])
    validator = APIValidator(hass, cast(ClientSession, session))

    result = await validator._test_authentication("https://example.test", "token")

    assert result["authenticated"] is True
    assert result["api_version"] is None
    assert result["capabilities"] is None


@pytest.mark.asyncio
async def test_test_authentication_handles_unexpected_errors(
    hass: HomeAssistant,
) -> None:
    """Unexpected authentication failures should return unauthenticated results."""
    validator = APIValidator(
        hass, cast(ClientSession, RaisingSession(RuntimeError("boom")))
    )

    result = await validator._test_authentication("https://example.test", "token")

    assert result == {
        "authenticated": False,
        "api_version": None,
        "capabilities": None,
    }


@pytest.mark.asyncio
async def test_async_test_api_health_reports_unreachable_and_healthy_statuses(
    hass: HomeAssistant,
) -> None:
    """Health checks should label unreachable and healthy validation states."""
    validator = APIValidator(hass, cast(ClientSession, DummySession([])))

    async def _unreachable(*args: object, **kwargs: object) -> APIValidationResult:
        return APIValidationResult(
            valid=False,
            reachable=False,
            authenticated=False,
            response_time_ms=None,
            error_message="down",
            api_version=None,
            capabilities=None,
        )

    validator.async_validate_api_connection = _unreachable  # type: ignore[method-assign]
    unreachable = await validator.async_test_api_health("https://example.test", "token")
    assert unreachable["status"] == "unreachable"

    async def _healthy(*args: object, **kwargs: object) -> APIValidationResult:
        return APIValidationResult(
            valid=True,
            reachable=True,
            authenticated=False,
            response_time_ms=1.5,
            error_message=None,
            api_version="1.0",
            capabilities=["status"],
        )

    validator.async_validate_api_connection = _healthy  # type: ignore[method-assign]
    healthy = await validator.async_test_api_health("https://example.test")
    assert healthy["status"] == "healthy"


@pytest.mark.asyncio
async def test_async_validate_api_connection_rejects_invalid_endpoint(
    hass: HomeAssistant,
) -> None:
    """Invalid endpoints should fail before issuing any network requests."""
    validator = APIValidator(hass, cast(ClientSession, DummySession([])))

    result = await validator.async_validate_api_connection("not-a-url")

    assert result.valid is False
    assert result.error_message == "Invalid API endpoint format"


@pytest.mark.asyncio
async def test_async_validate_api_connection_handles_timeout(
    hass: HomeAssistant,
) -> None:
    """Validation should map timeouts to a dedicated timeout error message."""
    validator = APIValidator(hass, cast(ClientSession, DummySession([])))

    async def _raise_timeout(*args: object, **kwargs: object) -> bool:
        raise TimeoutError

    validator._test_endpoint_reachability = _raise_timeout  # type: ignore[method-assign]
    result = await validator.async_validate_api_connection("https://example.test")

    assert result.valid is False
    assert result.error_message == "API connection timeout"


@pytest.mark.asyncio
async def test_async_validate_api_connection_handles_unexpected_error(
    hass: HomeAssistant,
) -> None:
    """Unexpected validation errors should be surfaced in the result payload."""
    validator = APIValidator(hass, cast(ClientSession, DummySession([])))

    async def _raise_error(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("kaputt")

    validator._test_endpoint_reachability = _raise_error  # type: ignore[method-assign]
    result = await validator.async_validate_api_connection("https://example.test")

    assert result.valid is False
    assert result.error_message == "Validation error: kaputt"


def test_extract_capabilities_returns_none_for_non_mapping_payloads() -> None:
    """Capability extraction should ignore non-dictionary payloads."""
    assert _extract_capabilities(cast(dict[str, JSONValue], ["status"])) is None
