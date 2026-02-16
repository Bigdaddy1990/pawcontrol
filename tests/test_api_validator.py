"""Unit tests for API validation helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.api_validator import APIValidator


@pytest.mark.asyncio
async def test_api_validation_rejects_invalid_endpoint(hass, mock_session) -> None:
  validator = APIValidator(hass, mock_session)  # noqa: E111
  # type: ignore[method-assign]  # noqa: E114
  validator._validate_endpoint_format = lambda _endpoint: False  # noqa: E111

  result = await validator.async_validate_api_connection("invalid")  # noqa: E111

  assert result.valid is False  # noqa: E111
  assert result.error_message == "Invalid API endpoint format"  # noqa: E111


@pytest.mark.asyncio
async def test_api_validation_handles_missing_token(hass, mock_session) -> None:
  validator = APIValidator(hass, mock_session)  # noqa: E111
  # type: ignore[method-assign]  # noqa: E114
  validator._validate_endpoint_format = lambda _endpoint: True  # noqa: E111
  validator._test_endpoint_reachability = AsyncMock(  # noqa: E111
    return_value=True,
  )  # type: ignore[method-assign]

  result = await validator.async_validate_api_connection("https://example.com")  # noqa: E111

  assert result.valid is True  # noqa: E111
  assert result.reachable is True  # noqa: E111
  assert result.authenticated is False  # noqa: E111


@pytest.mark.asyncio
async def test_api_validation_reports_auth_failure(hass, mock_session) -> None:
  validator = APIValidator(hass, mock_session)  # noqa: E111
  # type: ignore[method-assign]  # noqa: E114
  validator._validate_endpoint_format = lambda _endpoint: True  # noqa: E111
  validator._test_endpoint_reachability = AsyncMock(  # noqa: E111
    return_value=True,
  )  # type: ignore[method-assign]
  validator._test_authentication = AsyncMock(  # type: ignore[method-assign]  # noqa: E111
    return_value={
      "authenticated": False,
      "api_version": None,
      "capabilities": None,
    },
  )

  result = await validator.async_validate_api_connection(  # noqa: E111
    "https://example.com",
    "missing-token",
  )

  assert result.valid is False  # noqa: E111
  assert result.authenticated is False  # noqa: E111
  assert result.error_message == "API token authentication failed"  # noqa: E111
