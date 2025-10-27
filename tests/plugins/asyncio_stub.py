"""Minimal asyncio plugin to execute ``async def`` tests without pytest-asyncio."""

from __future__ import annotations

import asyncio
import inspect
import sys
from collections.abc import Iterator, Mapping
from contextlib import suppress
from importlib import import_module
from types import ModuleType
from typing import Any

import pytest

_SESSION_LOOP: asyncio.AbstractEventLoop | None = None


def _ensure_homeassistant_logging_stub() -> None:
    """Expose ``homeassistant.util.logging`` helpers required by HA fixtures."""

    try:
        ha_pkg = import_module("homeassistant")
    except ModuleNotFoundError:
        ha_pkg = ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha_pkg

    try:
        ha_util = import_module("homeassistant.util")
    except ModuleNotFoundError:
        ha_util = ModuleType("homeassistant.util")
        sys.modules["homeassistant.util"] = ha_util
    if not hasattr(ha_pkg, "util"):
        ha_pkg.util = ha_util  # type: ignore[attr-defined]

    try:
        ha_logging = import_module("homeassistant.util.logging")
    except ModuleNotFoundError:
        ha_logging = ModuleType("homeassistant.util.logging")
        sys.modules["homeassistant.util.logging"] = ha_logging

    if not hasattr(ha_util, "logging"):
        ha_util.logging = ha_logging  # type: ignore[attr-defined]

    if not hasattr(ha_logging, "log_exception"):

        def log_exception(*args: Any, **kwargs: Any) -> None:
            del args, kwargs

        ha_logging.log_exception = log_exception  # type: ignore[attr-defined]


def _ensure_aiohttp_resolver_stub() -> None:
    """Provide Home Assistant's aiohttp resolver shim when missing."""

    try:
        aiohttp_client = import_module("homeassistant.helpers.aiohttp_client")
    except ModuleNotFoundError:
        return

    if not hasattr(aiohttp_client, "_async_make_resolver"):

        async def _async_make_resolver(*args: Any, **kwargs: Any) -> None:
            del args, kwargs

        aiohttp_client._async_make_resolver = _async_make_resolver  # type: ignore[attr-defined]


def _get_active_loop() -> asyncio.AbstractEventLoop | None:
    """Return the currently active event loop if it exists."""

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return None
    return None if loop.is_closed() else loop


def _cancel_pending(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel any pending tasks that are still attached to ``loop``."""

    if loop.is_closed():
        return

    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """Provision an event loop before any fixtures execute."""

    del session  # session is unused but kept for signature parity.

    global _SESSION_LOOP

    loop = _SESSION_LOOP
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _SESSION_LOOP = loop

    asyncio.set_event_loop(loop)

    with suppress(Exception):
        _ensure_homeassistant_logging_stub()
    with suppress(Exception):
        _ensure_aiohttp_resolver_stub()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Tear down the session loop once the test session ends."""

    del session, exitstatus

    global _SESSION_LOOP

    loop = _SESSION_LOOP
    _SESSION_LOOP = None
    if loop is None:
        return

    _cancel_pending(loop)
    asyncio.set_event_loop(None)
    loop.close()


@pytest.fixture(autouse=True)
def _autouse_event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Expose an event loop for each test, reusing existing loops when possible."""

    previous_loop = _get_active_loop()
    session_loop = _SESSION_LOOP

    loop = None
    if session_loop is not None and not session_loop.is_closed():
        loop = session_loop
    elif previous_loop is not None and not previous_loop.is_closed():
        loop = previous_loop

    created_loop = False
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        created_loop = True

    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        _cancel_pending(loop)
        asyncio.set_event_loop(None)
        if previous_loop is not None and not previous_loop.is_closed():
            asyncio.set_event_loop(previous_loop)
        elif (
            not created_loop
            and _SESSION_LOOP is not None
            and not _SESSION_LOOP.is_closed()
        ):
            asyncio.set_event_loop(_SESSION_LOOP)
        if created_loop:
            loop.close()


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run coroutine test functions inside the active event loop."""

    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None

    loop = asyncio.get_event_loop()
    funcargs: Mapping[str, Any] = pyfuncitem.funcargs
    argnames = pyfuncitem._fixtureinfo.argnames
    call_args = {name: funcargs[name] for name in argnames}
    loop.run_until_complete(test_func(**call_args))
    return True


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef[Any], request: pytest.FixtureRequest
) -> Any:
    """Allow async fixtures to behave like pytest-asyncio's implementation."""

    outcome = yield
    result = outcome.get_result()
    if inspect.isawaitable(result):
        loop = asyncio.get_event_loop()
        outcome.force_result(loop.run_until_complete(result))
