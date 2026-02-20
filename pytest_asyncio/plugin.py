"""Compatibility subset of pytest-asyncio's plugin API."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
import contextlib
import inspect

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    with contextlib.suppress(ValueError):
        parser.addoption(
            "--asyncio-mode", action="store", default="auto", dest="asyncio_mode"
        )
    parser.addini("asyncio_mode", "Select asyncio integration mode", default="auto")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: run test in an event loop")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    test_fn = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_fn):
        return None

    loop = pyfuncitem.funcargs.get("event_loop")
    created_loop = False
    if loop is None:
        loop = asyncio.new_event_loop()
        created_loop = True

    kwargs = {
        name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames
    }
    loop.run_until_complete(test_fn(**kwargs))

    if created_loop and not loop.is_closed():
        loop.close()
    return True


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        if not loop.is_closed():
            loop.close()


fixture = pytest.fixture
