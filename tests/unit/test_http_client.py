"""Unit tests for the shared aiohttp session helper."""

from collections.abc import Coroutine
import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture(scope="module")
def http_client_module() -> ModuleType:
    """Load the http_client helper without importing the integration package."""  # noqa: E111

    module_path = (  # noqa: E111
        Path(__file__).resolve().parents[2]
        / "custom_components"
        / "pawcontrol"
        / "http_client.py"
    )
    spec = importlib.util.spec_from_file_location(  # noqa: E111
        "pawcontrol.http_client_test", module_path
    )
    assert spec and spec.loader  # noqa: E111
    module = importlib.util.module_from_spec(spec)  # noqa: E111
    spec.loader.exec_module(module)  # noqa: E111
    return module  # noqa: E111


@pytest.mark.unit
def test_ensure_shared_client_session_rejects_none(
    http_client_module: ModuleType,
) -> None:
    """Passing ``None`` should raise a descriptive ``ValueError``."""  # noqa: E111

    ensure_shared = http_client_module.ensure_shared_client_session  # noqa: E111

    with pytest.raises(ValueError) as excinfo:  # noqa: E111
        ensure_shared(None, owner="TestHelper")  # type: ignore[arg-type]

    assert "requires Home Assistant's shared aiohttp ClientSession" in str(
        excinfo.value
    )  # noqa: E111


@pytest.mark.unit
def test_ensure_shared_client_session_rejects_closed_pool(
    http_client_module: ModuleType, session_factory
) -> None:
    """A closed session must not be accepted by the helper."""  # noqa: E111

    ensure_shared = http_client_module.ensure_shared_client_session  # noqa: E111

    session = session_factory(closed=True)  # noqa: E111
    session.request = AsyncMock()  # noqa: E111

    with pytest.raises(ValueError) as excinfo:  # noqa: E111
        ensure_shared(session, owner="TestHelper")

    assert "received a closed aiohttp ClientSession" in str(excinfo.value)  # noqa: E111


@pytest.mark.unit
def test_ensure_shared_client_session_requires_coroutine_request(
    http_client_module: ModuleType, session_factory
) -> None:
    """A synchronous request attribute should be rejected."""  # noqa: E111

    ensure_shared = http_client_module.ensure_shared_client_session  # noqa: E111

    session = session_factory()  # noqa: E111
    session.request = Mock()  # noqa: E111

    with pytest.raises(ValueError) as excinfo:  # noqa: E111
        ensure_shared(session, owner="TestHelper")

    assert "aiohttp-compatible 'request' coroutine" in str(excinfo.value)  # noqa: E111


@pytest.mark.unit
def test_ensure_shared_client_session_returns_session(
    http_client_module: ModuleType, session_factory
) -> None:
    """A valid, open session should be returned unchanged."""  # noqa: E111

    ensure_shared = http_client_module.ensure_shared_client_session  # noqa: E111

    session = session_factory()  # noqa: E111
    session.request = AsyncMock()  # noqa: E111

    validated = ensure_shared(session, owner="TestHelper")  # noqa: E111

    assert validated is session  # noqa: E111


class _WrapperSession:
    """Minimal session mimic that proxies to an async ``_request`` method."""  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        self.closed = False

    async def _request(self, *args: object, **kwargs: object) -> str:  # noqa: E111
        return "ok"

    def request(self, *args: object, **kwargs: object) -> Coroutine[None, None, str]:  # noqa: E111
        return self._request(*args, **kwargs)


@pytest.mark.unit
def test_ensure_shared_client_session_accepts_wrapped_request(
    http_client_module: ModuleType,
) -> None:
    """Sessions that wrap a private coroutine should be accepted."""  # noqa: E111

    ensure_shared = http_client_module.ensure_shared_client_session  # noqa: E111

    session = _WrapperSession()  # noqa: E111

    validated = ensure_shared(session, owner="TestHelper")  # noqa: E111

    assert validated is session  # noqa: E111
