"""Minimal pytest-asyncio stub for isolated test environments.

Provides the small subset of plugin behavior exercised by the PawControl
test suite without requiring the real pytest-asyncio dependency.
"""

import asyncio
from collections.abc import Generator
import contextlib
import inspect
from typing import Any

import pytest


def pytest_addoption(parser) -> None:
    """Register asyncio configuration defaults used by pytest-asyncio."""  # noqa: E111

    with contextlib.suppress(ValueError):  # noqa: E111
        parser.addoption(
            "--asyncio-mode",
            action="store",
            dest="asyncio_mode",
            default=None,
            help="Select asyncio integration mode",
        )
    with contextlib.suppress(ValueError):  # noqa: E111
        parser.addini(
            "asyncio_mode",
            "Select asyncio integration mode",
            default="auto",
        )


def _event_loop() -> Generator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()  # noqa: E111
    try:  # noqa: E111
        yield loop
    finally:  # noqa: E111
        if not loop.is_closed():
            loop.close()  # noqa: E111


event_loop = pytest.fixture(_event_loop)
event_loop._fixture_function = _event_loop
fixture = pytest.fixture

_shared_loop: asyncio.AbstractEventLoop | None = None


def _resolve_event_loop(
    request: pytest.FixtureRequest | None,
) -> tuple[asyncio.AbstractEventLoop, bool]:
    if request is not None and "event_loop" in request.fixturenames:  # noqa: E111
        return request.getfixturevalue("event_loop"), False
    global _shared_loop  # noqa: E111
    if _shared_loop is None or _shared_loop.is_closed():  # noqa: E111
        _shared_loop = asyncio.new_event_loop()
    return _shared_loop, False  # noqa: E111


def _run_coroutine(
    coro: Any,
    loop: asyncio.AbstractEventLoop,
) -> Any:
    if loop.is_running():  # noqa: E111
        runner_loop = asyncio.new_event_loop()
        try:
            return runner_loop.run_until_complete(coro)  # noqa: E111
        finally:
            runner_loop.close()  # noqa: E111
    return loop.run_until_complete(coro)  # noqa: E111


def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef,
    request: pytest.FixtureRequest,
) -> Any:
    func = fixturedef.func  # noqa: E111
    if inspect.iscoroutinefunction(func):  # noqa: E111
        loop, close_loop = _resolve_event_loop(request)
        kwargs = {name: request.getfixturevalue(name) for name in fixturedef.argnames}
        result = _run_coroutine(func(**kwargs), loop)
        if close_loop and not loop.is_closed():
            loop.close()  # noqa: E111
        return result
    if inspect.isasyncgenfunction(func):  # noqa: E111
        loop, close_loop = _resolve_event_loop(request)
        kwargs = {name: request.getfixturevalue(name) for name in fixturedef.argnames}
        agen = func(**kwargs)
        result = _run_coroutine(agen.__anext__(), loop)

        def _finalize_asyncgen() -> None:
            _run_coroutine(agen.aclose(), loop)  # noqa: E111
            if close_loop and not loop.is_closed():  # noqa: E111
                loop.close()

        request.addfinalizer(_finalize_asyncgen)
        return result
    return None  # noqa: E111


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    if inspect.iscoroutinefunction(pyfuncitem.obj):  # noqa: E111
        loop, close_loop = _resolve_event_loop(pyfuncitem._request)
        argnames = getattr(pyfuncitem, "_fixtureinfo", None)
        if argnames is not None:
            requested = set(pyfuncitem._fixtureinfo.argnames)  # type: ignore[attr-defined]  # noqa: E111
        else:
            requested = set(pyfuncitem.funcargs)  # noqa: E111
        kwargs = {name: pyfuncitem.funcargs[name] for name in requested}
        result = _run_coroutine(pyfuncitem.obj(**kwargs), loop)
        if result is not None:
            return True  # noqa: E111
        return True
    return None  # noqa: E111


def pytest_unconfigure(config: pytest.Config) -> None:
    """Close the shared event loop after the test session."""  # noqa: E111

    _ = config  # noqa: E111
    global _shared_loop  # noqa: E111
    loop = _shared_loop  # noqa: E111
    if loop is None or loop.is_closed():  # noqa: E111
        return
    asyncio.set_event_loop(loop)  # noqa: E111
    pending = asyncio.all_tasks(loop)  # noqa: E111
    for task in pending:  # noqa: E111
        task.cancel()
    if pending:  # noqa: E111
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()  # noqa: E111
    _shared_loop = None  # noqa: E111


__all__ = [
    "event_loop",
    "fixture",
    "pytest_addoption",
    "pytest_fixture_setup",
    "pytest_pyfunc_call",
    "pytest_unconfigure",
]
