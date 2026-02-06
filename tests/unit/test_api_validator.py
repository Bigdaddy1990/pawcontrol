from __future__ import annotations

import pytest

from custom_components.pawcontrol.api_validator import async_validate_api


@pytest.mark.asyncio
async def test_async_validate_api_returns_true_when_probe_fails(
  mock_session,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  async def _raise(*args: object, **kwargs: object) -> object:
    raise RuntimeError("status missing")

  monkeypatch.setattr(mock_session, "request", _raise)

  assert await async_validate_api(mock_session, "https://example.com", "token") is True
