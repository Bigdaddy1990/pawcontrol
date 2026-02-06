"""Unit tests for API validation helpers."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.api_validator import async_validate_api
from custom_components.pawcontrol.exceptions import PawControlError


@pytest.mark.asyncio
async def test_async_validate_api_accepts_valid_endpoint(mock_session) -> None:
  assert await async_validate_api(mock_session, "https://example.com", None) is True


@pytest.mark.asyncio
async def test_async_validate_api_rejects_invalid_endpoint(mock_session) -> None:
  with pytest.raises(PawControlError):
    await async_validate_api(mock_session, "", None)
