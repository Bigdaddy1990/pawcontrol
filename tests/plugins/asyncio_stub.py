"""Minimal asyncio plugin to execute ``async def`` tests without pytest-asyncio."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _autouse_event_loop() -> asyncio.AbstractEventLoop:
    """Provide a fresh event loop for each test."""

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        asyncio.set_event_loop(None)
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
