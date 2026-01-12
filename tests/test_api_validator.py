"""Unit tests for API validation helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.api_validator import APIValidator


@pytest.mark.asyncio
async def test_api_validation_rejects_invalid_endpoint(hass, mock_session) -> None:
    validator = APIValidator(hass, mock_session)
    validator._validate_endpoint_format = lambda _endpoint: False  # type: ignore[method-assign]

    result = await validator.async_validate_api_connection("invalid")

    assert result.valid is False
    assert result.error_message == "Invalid API endpoint format"


@pytest.mark.asyncio
async def test_api_validation_handles_missing_token(hass, mock_session) -> None:
    validator = APIValidator(hass, mock_session)
    validator._validate_endpoint_format = lambda _endpoint: True  # type: ignore[method-assign]
    validator._test_endpoint_reachability = AsyncMock(return_value=True)  # type: ignore[method-assign]

    result = await validator.async_validate_api_connection("https://example.com")

    assert result.valid is True
    assert result.reachable is True
    assert result.authenticated is False


@pytest.mark.asyncio
async def test_api_validation_reports_auth_failure(hass, mock_session) -> None:
    validator = APIValidator(hass, mock_session)
    validator._validate_endpoint_format = lambda _endpoint: True  # type: ignore[method-assign]
    validator._test_endpoint_reachability = AsyncMock(return_value=True)  # type: ignore[method-assign]
    validator._test_authentication = AsyncMock(  # type: ignore[method-assign]
        return_value={"authenticated": False, "api_version": None, "capabilities": None}
    )

    result = await validator.async_validate_api_connection(
        "https://example.com", "missing-token"
    )

    assert result.valid is False
    assert result.authenticated is False
    assert result.error_message == "API token authentication failed"
