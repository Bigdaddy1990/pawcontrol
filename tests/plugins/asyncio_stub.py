"""Pytest plugin that provides a minimal asyncio event loop fixture."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator

import pytest

_ORIGINAL_GET_EVENT_LOOP: Callable[[], asyncio.AbstractEventLoop] = (
    asyncio.get_event_loop
)


def _patched_get_event_loop() -> asyncio.AbstractEventLoop:
    try:
        return _ORIGINAL_GET_EVENT_LOOP()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


asyncio.get_event_loop = _patched_get_event_loop  # type: ignore[assignment]


def _ensure_main_thread_loop() -> asyncio.AbstractEventLoop | None:
    """Return the existing loop or create a replacement when missing."""

    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def pytest_configure(config: pytest.Config) -> None:
    """Ensure a default event loop exists for plugins executed at import time."""

    loop = _ensure_main_thread_loop()
    if loop is not None:
        config._pawcontrol_asyncio_loop = loop  # type: ignore[attr-defined]


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """Re-create the loop after other plugins tweak the event loop policy."""

    loop = _ensure_main_thread_loop()
    if loop is not None:
        # type: ignore[attr-defined]
        session.config._pawcontrol_asyncio_loop = loop


def pytest_unconfigure(config: pytest.Config) -> None:
    """Close the temporary loop created during :func:`pytest_configure`."""

    loop = getattr(config, "_pawcontrol_asyncio_loop", None)
    if isinstance(loop, asyncio.AbstractEventLoop):
        loop.close()

    # type: ignore[assignment]
    asyncio.get_event_loop = _ORIGINAL_GET_EVENT_LOOP


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create an event loop for the session when pytest-asyncio is unavailable."""

    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def enable_event_loop_debug() -> Generator[None]:
    """Override the HACC debug fixture to avoid requiring a default loop."""

    yield
