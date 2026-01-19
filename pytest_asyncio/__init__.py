"""Minimal pytest-asyncio stub for isolated test environments.

Provides the small subset of plugin behavior exercised by the PawControl
test suite without requiring the real pytest-asyncio dependency.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
import inspect
from typing import Any

import pytest


def pytest_addoption(parser) -> None:
  """Register asyncio configuration defaults used by pytest-asyncio."""

  parser.addini(
    "asyncio_mode",
    "Select asyncio integration mode",
    default="auto",
  )


def _event_loop() -> Generator[asyncio.AbstractEventLoop]:
  loop = asyncio.new_event_loop()
  try:
    yield loop
  finally:
    if not loop.is_closed():
      loop.close()


event_loop = pytest.fixture(_event_loop)
event_loop._fixture_function = _event_loop
fixture = pytest.fixture

_shared_loop: asyncio.AbstractEventLoop | None = None


def _resolve_event_loop(
  request: pytest.FixtureRequest | None,
) -> tuple[asyncio.AbstractEventLoop, bool]:
  if request is not None and "event_loop" in request.fixturenames:
    return request.getfixturevalue("event_loop"), False
  global _shared_loop
  if _shared_loop is None or _shared_loop.is_closed():
    _shared_loop = asyncio.new_event_loop()
  return _shared_loop, False


def _run_coroutine(
  coro: Any,
  loop: asyncio.AbstractEventLoop,
) -> Any:
  if loop.is_running():
    runner_loop = asyncio.new_event_loop()
    try:
      return runner_loop.run_until_complete(coro)
    finally:
      runner_loop.close()
  return loop.run_until_complete(coro)


def pytest_fixture_setup(
  fixturedef: pytest.FixtureDef,
  request: pytest.FixtureRequest,
) -> Any:
  func = fixturedef.func
  if inspect.iscoroutinefunction(func):
    loop, close_loop = _resolve_event_loop(request)
    kwargs = {name: request.getfixturevalue(name) for name in fixturedef.argnames}
    result = _run_coroutine(func(**kwargs), loop)
    if close_loop and not loop.is_closed():
      loop.close()
    return result
  if inspect.isasyncgenfunction(func):
    loop, close_loop = _resolve_event_loop(request)
    kwargs = {name: request.getfixturevalue(name) for name in fixturedef.argnames}
    agen = func(**kwargs)
    result = _run_coroutine(agen.__anext__(), loop)

    def _finalize_asyncgen() -> None:
      _run_coroutine(agen.aclose(), loop)
      if close_loop and not loop.is_closed():
        loop.close()

    request.addfinalizer(_finalize_asyncgen)
    return result
  return None


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
  if inspect.iscoroutinefunction(pyfuncitem.obj):
    loop, close_loop = _resolve_event_loop(pyfuncitem._request)
    argnames = getattr(pyfuncitem, "_fixtureinfo", None)
    if argnames is not None:
      requested = set(pyfuncitem._fixtureinfo.argnames)  # type: ignore[attr-defined]
    else:
      requested = set(pyfuncitem.funcargs)
    kwargs = {name: pyfuncitem.funcargs[name] for name in requested}
    result = _run_coroutine(pyfuncitem.obj(**kwargs), loop)
    if result is not None:
      return True
    return True
  return None


def pytest_unconfigure(config: pytest.Config) -> None:
  """Close the shared event loop after the test session."""

  _ = config
  global _shared_loop
  loop = _shared_loop
  if loop is None or loop.is_closed():
    return
  asyncio.set_event_loop(loop)
  pending = asyncio.all_tasks(loop)
  for task in pending:
    task.cancel()
  if pending:
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
  loop.close()
  _shared_loop = None


__all__ = [
  "event_loop",
  "fixture",
  "pytest_addoption",
  "pytest_fixture_setup",
  "pytest_pyfunc_call",
  "pytest_unconfigure",
]
