"""Unit tests for the shared aiohttp session helper."""

from __future__ import annotations

import importlib.util
from collections.abc import Coroutine
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture(scope="module")
def http_client_module() -> ModuleType:
  """Load the http_client helper without importing the integration package."""

  module_path = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "pawcontrol"
    / "http_client.py"
  )
  spec = importlib.util.spec_from_file_location(
    "pawcontrol.http_client_test", module_path
  )
  assert spec and spec.loader
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


@pytest.mark.unit
def test_ensure_shared_client_session_rejects_none(
  http_client_module: ModuleType,
) -> None:
  """Passing ``None`` should raise a descriptive ``ValueError``."""

  ensure_shared = http_client_module.ensure_shared_client_session

  with pytest.raises(ValueError) as excinfo:
    ensure_shared(None, owner="TestHelper")  # type: ignore[arg-type]

  assert "requires Home Assistant's shared aiohttp ClientSession" in str(excinfo.value)


@pytest.mark.unit
def test_ensure_shared_client_session_rejects_closed_pool(
  http_client_module: ModuleType, session_factory
) -> None:
  """A closed session must not be accepted by the helper."""

  ensure_shared = http_client_module.ensure_shared_client_session

  session = session_factory(closed=True)
  session.request = AsyncMock()

  with pytest.raises(ValueError) as excinfo:
    ensure_shared(session, owner="TestHelper")

  assert "received a closed aiohttp ClientSession" in str(excinfo.value)


@pytest.mark.unit
def test_ensure_shared_client_session_requires_coroutine_request(
  http_client_module: ModuleType, session_factory
) -> None:
  """A synchronous request attribute should be rejected."""

  ensure_shared = http_client_module.ensure_shared_client_session

  session = session_factory()
  session.request = Mock()

  with pytest.raises(ValueError) as excinfo:
    ensure_shared(session, owner="TestHelper")

  assert "aiohttp-compatible 'request' coroutine" in str(excinfo.value)


@pytest.mark.unit
def test_ensure_shared_client_session_returns_session(
  http_client_module: ModuleType, session_factory
) -> None:
  """A valid, open session should be returned unchanged."""

  ensure_shared = http_client_module.ensure_shared_client_session

  session = session_factory()
  session.request = AsyncMock()

  validated = ensure_shared(session, owner="TestHelper")

  assert validated is session


class _WrapperSession:
  """Minimal session mimic that proxies to an async ``_request`` method."""

  def __init__(self) -> None:
    self.closed = False

  async def _request(self, *args: object, **kwargs: object) -> str:
    return "ok"

  def request(self, *args: object, **kwargs: object) -> Coroutine[None, None, str]:
    return self._request(*args, **kwargs)


@pytest.mark.unit
def test_ensure_shared_client_session_accepts_wrapped_request(
  http_client_module: ModuleType,
) -> None:
  """Sessions that wrap a private coroutine should be accepted."""

  ensure_shared = http_client_module.ensure_shared_client_session

  session = _WrapperSession()

  validated = ensure_shared(session, owner="TestHelper")

  assert validated is session
