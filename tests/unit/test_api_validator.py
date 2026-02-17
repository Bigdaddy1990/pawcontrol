from collections.abc import Generator, Iterable
from types import TracebackType
from typing import TypeAlias, cast

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol.api_validator import APIValidator, JSONValue

type DummyPayload = dict[str, JSONValue]


class DummyResponse:
    """Minimal async context manager used to emulate aiohttp responses."""  # noqa: E111

    def __init__(  # noqa: E111
        self,
        status: int,
        payload: DummyPayload | None = None,
        *,
        json_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._payload: DummyPayload = payload or {}
        self._json_error = json_error

    async def __aenter__(self) -> DummyResponse:  # noqa: E111
        return self

    async def __aexit__(  # noqa: E111
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    async def json(self) -> DummyPayload:  # noqa: E111
        if self._json_error is not None:
            raise self._json_error  # noqa: E111
        return self._payload


class DummyRequestContext:
    """Awaitable context manager matching aiohttp's request API."""  # noqa: E111

    def __init__(self, response: DummyResponse) -> None:  # noqa: E111
        self._response = response

    def __await__(self) -> Generator[DummyResponse, None, DummyResponse]:  # noqa: E111
        async def _inner() -> DummyResponse:
            return self._response  # noqa: E111

        return _inner().__await__()

    async def __aenter__(self) -> DummyResponse:  # noqa: E111
        return await self._response.__aenter__()

    async def __aexit__(  # noqa: E111
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return await self._response.__aexit__(exc_type, exc, tb)


class DummySession:
    """Session stub accepted by :func:`ensure_shared_client_session`."""  # noqa: E111

    closed = False  # noqa: E111

    def __init__(self, responses: Iterable[DummyResponse]) -> None:  # noqa: E111
        self._responses: list[DummyResponse] = list(responses)
        self._index: int = 0

    async def request(self, *args: object, **kwargs: object) -> DummyResponse:  # noqa: E111
        context = self.get(*args, **kwargs)
        return await context

    def get(self, *args: object, **kwargs: object) -> DummyRequestContext:  # noqa: E111
        if self._index >= len(self._responses):
            raise AssertionError(  # noqa: E111
                "DummySession received more get() calls than configured responses"
            )
        response = self._responses[self._index]
        self._index += 1
        return DummyRequestContext(response)


@pytest.mark.asyncio
async def test_async_validate_api_connection_filters_capabilities(
    hass: HomeAssistant,
) -> None:
    """Only string capabilities from the JSON payload should be exposed."""  # noqa: E111

    session = DummySession([  # noqa: E111
        DummyResponse(200),
        DummyResponse(
            200, {"version": "1.2.3", "capabilities": ["status", 42, "metrics"]}
        ),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))  # noqa: E111

    result = await validator.async_validate_api_connection(  # noqa: E111
        "https://example.test", "secret-token"
    )

    assert result.valid is True  # noqa: E111
    assert result.api_version == "1.2.3"  # noqa: E111
    assert result.capabilities == ["status", "metrics"]  # noqa: E111


@pytest.mark.asyncio
async def test_async_validate_api_connection_accepts_tuple_capabilities(
    hass: HomeAssistant,
) -> None:
    """Tuple-based capability payloads should normalise to list[str]."""  # noqa: E111

    session = DummySession([  # noqa: E111
        DummyResponse(200),
        DummyResponse(
            200,
            {
                "version": "9.9.9",
                "capabilities": ("status", {"ignored": True}, "insights"),
            },
        ),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))  # noqa: E111

    result = await validator.async_validate_api_connection(  # noqa: E111
        "https://example.test", "secret-token"
    )

    assert result.valid is True  # noqa: E111
    assert result.capabilities == ["status", "insights"]  # noqa: E111


@pytest.mark.asyncio
async def test_async_validate_api_connection_handles_json_failure(
    hass: HomeAssistant,
) -> None:
    """Successful authentication without JSON keeps optional fields ``None``."""  # noqa: E111

    session = DummySession([  # noqa: E111
        DummyResponse(200),
        DummyResponse(200, json_error=ValueError("boom")),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))  # noqa: E111

    result = await validator.async_validate_api_connection(  # noqa: E111
        "https://example.test", "secret-token"
    )

    assert result.valid is True  # noqa: E111
    assert result.api_version is None  # noqa: E111
    assert result.capabilities is None  # noqa: E111


@pytest.mark.asyncio
async def test_async_validate_api_connection_supports_empty_capabilities(
    hass: HomeAssistant,
) -> None:
    """An empty capabilities array should normalise to an empty list."""  # noqa: E111

    session = DummySession([  # noqa: E111
        DummyResponse(200),
        DummyResponse(200, {"version": "2.0.0", "capabilities": []}),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))  # noqa: E111

    result = await validator.async_validate_api_connection(  # noqa: E111
        "https://example.test", "secret-token"
    )

    assert result.valid is True  # noqa: E111
    assert result.capabilities == []  # noqa: E111


@pytest.mark.asyncio
async def test_async_test_api_health_authentication_failure(
    hass: HomeAssistant,
) -> None:
    """Authentication errors should surface a dedicated health status."""  # noqa: E111

    session = DummySession([  # noqa: E111
        DummyResponse(200),
        DummyResponse(401),
        DummyResponse(401),
        DummyResponse(401),
        DummyResponse(401),
    ])
    validator = APIValidator(hass, cast(ClientSession, session))  # noqa: E111

    health = await validator.async_test_api_health(
        "https://example.test", "secret-token"
    )  # noqa: E111

    assert health["healthy"] is False  # noqa: E111
    assert health["reachable"] is True  # noqa: E111
    assert health["status"] == "authentication_failed"  # noqa: E111
    assert health["capabilities"] is None  # noqa: E111
