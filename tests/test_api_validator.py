"""Unit tests for API validation helpers."""

from collections.abc import Sequence
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import pytest

from custom_components.pawcontrol.api_validator import (
    APIValidator,
    _extract_api_version,
    _extract_capabilities,
)


class _MockResponse:
    def __init__(
        self, status: int, payload: Any = None, *, json_raises: bool = False
    ) -> None:
        self.status = status
        self._payload = payload
        self._json_raises = json_raises

    async def __aenter__(self) -> _MockResponse:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def json(self) -> Any:
        if self._json_raises:
            raise ValueError("invalid json")
        return self._payload


class _AwaitableResponse:
    def __init__(self, response: _MockResponse) -> None:
        self._response = response

    def __await__(self):
        async def _resolve() -> _MockResponse:
            return self._response

        return _resolve().__await__()

    async def __aenter__(self) -> _MockResponse:
        return await self._response.__aenter__()

    async def __aexit__(self, *args: object) -> None:
        await self._response.__aexit__(*args)


class _SequentialGetSession:
    def __init__(self, responses: Sequence[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    async def request(self, *_args: object, **_kwargs: object) -> object:
        return None

    def get(self, url: str, **kwargs: object) -> object:
        self.calls.append((url, dict(kwargs)))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return _AwaitableResponse(response)


@pytest.mark.asyncio
async def test_api_validation_rejects_invalid_endpoint(hass, mock_session) -> None:
    validator = APIValidator(hass, mock_session)
    # type: ignore[method-assign]
    validator._validate_endpoint_format = lambda _endpoint: False

    result = await validator.async_validate_api_connection("invalid")

    assert result.valid is False
    assert result.error_message == "Invalid API endpoint format"


@pytest.mark.asyncio
async def test_api_validation_handles_missing_token(hass, mock_session) -> None:
    validator = APIValidator(hass, mock_session)
    # type: ignore[method-assign]
    validator._validate_endpoint_format = lambda _endpoint: True
    validator._test_endpoint_reachability = AsyncMock(
        return_value=True,
    )  # type: ignore[method-assign]

    result = await validator.async_validate_api_connection("https://example.com")

    assert result.valid is True
    assert result.reachable is True
    assert result.authenticated is False


@pytest.mark.asyncio
async def test_api_validator_session_property_exposes_shared_session(
    hass,
    mock_session,
) -> None:
    validator = APIValidator(hass, mock_session)

    assert validator.session is mock_session


@pytest.mark.asyncio
async def test_api_validation_reports_unreachable_endpoint(hass, mock_session) -> None:
    validator = APIValidator(hass, mock_session)
    # type: ignore[method-assign]
    validator._validate_endpoint_format = lambda _endpoint: True
    validator._test_endpoint_reachability = AsyncMock(  # type: ignore[method-assign]
        return_value=False,
    )

    result = await validator.async_validate_api_connection("https://example.com")

    assert result.valid is False
    assert result.reachable is False
    assert result.error_message == "API endpoint not reachable"


@pytest.mark.asyncio
async def test_api_validation_accepts_authenticated_response(
    hass, mock_session
) -> None:
    validator = APIValidator(hass, mock_session)
    # type: ignore[method-assign]
    validator._validate_endpoint_format = lambda _endpoint: True
    validator._test_endpoint_reachability = AsyncMock(  # type: ignore[method-assign]
        return_value=True,
    )
    validator._test_authentication = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "authenticated": True,
            "api_version": "2026.2",
            "capabilities": ["sync"],
        },
    )

    result = await validator.async_validate_api_connection(
        "https://example.com",
        "token",
    )

    assert result.valid is True
    assert result.authenticated is True
    assert result.api_version == "2026.2"
    assert result.capabilities == ["sync"]


@pytest.mark.asyncio
async def test_api_validation_reports_auth_failure(hass, mock_session) -> None:
    validator = APIValidator(hass, mock_session)
    # type: ignore[method-assign]
    validator._validate_endpoint_format = lambda _endpoint: True
    validator._test_endpoint_reachability = AsyncMock(
        return_value=True,
    )  # type: ignore[method-assign]
    validator._test_authentication = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "authenticated": False,
            "api_version": None,
            "capabilities": None,
        },
    )

    result = await validator.async_validate_api_connection(
        "https://example.com",
        "missing-token",
    )

    assert result.valid is False
    assert result.authenticated is False
    assert result.error_message == "API token authentication failed"


@pytest.mark.asyncio
async def test_api_validation_reports_timeout(hass, mock_session) -> None:
    """Timeout failures should map to the dedicated timeout error message."""
    validator = APIValidator(hass, mock_session)
    # type: ignore[method-assign]
    validator._validate_endpoint_format = lambda _endpoint: True
    validator._test_endpoint_reachability = AsyncMock(  # type: ignore[method-assign]
        side_effect=TimeoutError,
    )

    result = await validator.async_validate_api_connection("https://example.com")

    assert result.valid is False
    assert result.reachable is False
    assert result.error_message == "API connection timeout"


@pytest.mark.asyncio
async def test_api_validation_reports_unexpected_error(hass, mock_session) -> None:
    """Unexpected exceptions should be wrapped into a validation error."""
    validator = APIValidator(hass, mock_session)
    # type: ignore[method-assign]
    validator._validate_endpoint_format = lambda _endpoint: True
    validator._test_endpoint_reachability = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("boom"),
    )

    result = await validator.async_validate_api_connection("https://example.com")

    assert result.valid is False
    assert result.reachable is False
    assert result.error_message == "Validation error: boom"


def test_validate_endpoint_format_checks_structure(
    hass,
    mock_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = APIValidator(hass, mock_session)

    assert validator._validate_endpoint_format("") is False
    assert validator._validate_endpoint_format("ftp://example.com") is False
    assert validator._validate_endpoint_format("https:///path-only") is False

    def _raise_url_error(_value: str) -> object:
        raise ValueError("bad url")

    monkeypatch.setattr("urllib.parse.urlparse", _raise_url_error)
    assert validator._validate_endpoint_format("https://example.com") is False


@pytest.mark.asyncio
async def test_test_endpoint_reachability_success_and_ssl_override(hass) -> None:
    session = _SequentialGetSession([_MockResponse(200), _MockResponse(200)])
    validator = APIValidator(hass, session, verify_ssl=False)

    assert await validator._test_endpoint_reachability("https://example.com") is True

    assert session.calls[0][1]["allow_redirects"] is True
    assert session.calls[0][1]["ssl"] is False


@pytest.mark.asyncio
async def test_test_endpoint_reachability_handles_client_and_generic_errors(
    hass,
) -> None:
    session = _SequentialGetSession([
        aiohttp.ClientError("boom"),
        RuntimeError("unexpected"),
    ])
    validator = APIValidator(hass, session)

    assert await validator._test_endpoint_reachability("https://example.com") is False
    assert await validator._test_endpoint_reachability("https://example.com") is False


@pytest.mark.asyncio
async def test_test_authentication_uses_payload_when_available(hass) -> None:
    session = _SequentialGetSession([
        _MockResponse(200, {"version": "1.0", "capabilities": ["walk", 1]})
    ])
    validator = APIValidator(hass, session)

    result = await validator._test_authentication("https://example.com", "token")

    assert result == {
        "authenticated": True,
        "api_version": "1.0",
        "capabilities": ["walk"],
    }


@pytest.mark.asyncio
async def test_test_authentication_handles_non_mapping_and_json_error(hass) -> None:
    non_mapping_session = _SequentialGetSession([_MockResponse(200, ["bad"])])
    validator_non_mapping = APIValidator(hass, non_mapping_session)
    assert await validator_non_mapping._test_authentication(
        "https://example.com", "token"
    ) == {
        "authenticated": True,
        "api_version": None,
        "capabilities": None,
    }

    json_error_session = _SequentialGetSession([_MockResponse(200, json_raises=True)])
    validator_json_error = APIValidator(hass, json_error_session)
    assert await validator_json_error._test_authentication(
        "https://example.com", "token"
    ) == {
        "authenticated": True,
        "api_version": None,
        "capabilities": None,
    }


@pytest.mark.asyncio
async def test_test_authentication_retries_endpoints_and_reports_failure(hass) -> None:
    session = _SequentialGetSession([
        aiohttp.ClientError("bad"),
        _MockResponse(401, {}),
        _MockResponse(404, {}),
        _MockResponse(403, {}),
    ])
    validator = APIValidator(hass, session, verify_ssl=False)

    result = await validator._test_authentication("https://example.com", "token")

    assert result["authenticated"] is False
    assert len(session.calls) == 4
    assert session.calls[0][1]["ssl"] is False


@pytest.mark.asyncio
async def test_test_authentication_returns_false_on_outer_exception(hass) -> None:
    session = _SequentialGetSession([RuntimeError("session broke")])
    validator = APIValidator(hass, session)

    result = await validator._test_authentication("https://example.com", "token")

    assert result == {
        "authenticated": False,
        "api_version": None,
        "capabilities": None,
    }


@pytest.mark.asyncio
async def test_async_test_api_health_status_mappings(hass, mock_session) -> None:
    validator = APIValidator(hass, mock_session)

    validator.async_validate_api_connection = AsyncMock(  # type: ignore[method-assign]
        return_value=type(
            "Result",
            (),
            {
                "valid": False,
                "reachable": False,
                "authenticated": False,
                "response_time_ms": 12.0,
                "error_message": "no route",
                "api_version": None,
                "capabilities": None,
            },
        )()
    )
    unreachable = await validator.async_test_api_health("https://example.com", "token")
    assert unreachable["status"] == "unreachable"

    validator.async_validate_api_connection = AsyncMock(  # type: ignore[method-assign]
        return_value=type(
            "Result",
            (),
            {
                "valid": False,
                "reachable": True,
                "authenticated": False,
                "response_time_ms": 13.0,
                "error_message": "auth",
                "api_version": None,
                "capabilities": None,
            },
        )()
    )
    auth_failed = await validator.async_test_api_health("https://example.com", "token")
    assert auth_failed["status"] == "authentication_failed"

    validator.async_validate_api_connection = AsyncMock(  # type: ignore[method-assign]
        return_value=type(
            "Result",
            (),
            {
                "valid": True,
                "reachable": True,
                "authenticated": True,
                "response_time_ms": 14.0,
                "error_message": None,
                "api_version": "1.0",
                "capabilities": ["walk"],
            },
        )()
    )
    healthy = await validator.async_test_api_health("https://example.com", "token")
    assert healthy["status"] == "healthy"


@pytest.mark.asyncio
async def test_async_test_api_health_handles_timeout_and_error(
    hass, mock_session
) -> None:
    validator = APIValidator(hass, mock_session)
    validator.async_validate_api_connection = AsyncMock(  # type: ignore[method-assign]
        side_effect=TimeoutError,
    )
    timeout_result = await validator.async_test_api_health("https://example.com")
    assert timeout_result["status"] == "timeout"

    validator.async_validate_api_connection = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("boom"),
    )
    error_result = await validator.async_test_api_health("https://example.com")
    assert error_result["status"] == "error"
    assert error_result["error"] == "boom"


@pytest.mark.asyncio
async def test_async_close_is_noop_for_shared_sessions(hass) -> None:
    open_session = _SequentialGetSession([])
    open_validator = APIValidator(hass, open_session)
    await open_validator.async_close()
    assert open_session.closed is False

    open_validator._session.closed = True
    await open_validator.async_close()
    assert open_session.closed is True


def test_extract_helpers_cover_supported_shapes() -> None:
    assert _extract_api_version({"version": "1.2.3"}) == "1.2.3"
    assert _extract_api_version({"version": 1}) is None
    assert _extract_capabilities({"capabilities": ["a", 1]}) == ["a"]
    assert _extract_capabilities({"capabilities": []}) == []
    assert _extract_capabilities({"capabilities": "flat"}) is None
    assert _extract_capabilities(["invalid"]) is None
