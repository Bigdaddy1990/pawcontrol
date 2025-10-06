"""Minimal pytest-asyncio compatibility layer for the PawControl tests."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

import pytest

__all__ = ["fixture"]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the minimal asyncio configuration knobs used in tests."""

    parser.addini(
        "asyncio_mode",
        "Integration strategy for asyncio event loops (auto, strict, legacy).",
        default="auto",
    )
    parser.addoption(
        "--asyncio-mode",
        action="store",
        dest="asyncio_mode",
        choices=("auto", "strict", "legacy"),
        help=(
            "Override the asyncio mode exposed by the PawControl pytest-asyncio "
            "compatibility layer."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Store the resolved asyncio mode for debugging parity with pytest-asyncio."""

    mode = config.getoption("asyncio_mode") or config.getini("asyncio_mode")
    setattr(config, "_pawcontrol_asyncio_mode", mode)


def fixture(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate async fixtures so they return their resolved value."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if not inspect.iscoroutinefunction(func):
            return pytest.fixture(*args, **kwargs)(func)

        base_fixture = pytest.fixture(*args, **kwargs)

        def sync_wrapper(*wrapper_args: Any, **wrapper_kwargs: Any) -> Any:
            loop = asyncio.get_event_loop()
            coro = func(*wrapper_args, **wrapper_kwargs)
            return loop.run_until_complete(coro)

        return base_fixture(sync_wrapper)

    if args and len(args) == 1 and callable(args[0]) and not kwargs:
        return decorator(args[0])
    return decorator


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef[Any], request: pytest.FixtureRequest
) -> Any:
    """Await coroutine results returned by fixtures."""

    outcome = yield
    result = outcome.get_result()
    if inspect.isawaitable(result):
        loop = asyncio.get_event_loop()
        outcome.force_result(loop.run_until_complete(result))
