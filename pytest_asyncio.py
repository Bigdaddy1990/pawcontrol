"""Local pytest-asyncio shim for environments without the plugin dependency.

This stub ensures the ``-p pytest_asyncio`` addopts entry resolves without
requiring the PyPI package.  It provides the minimal configuration hook and
``event_loop`` fixture expected by the test suite while deferring detailed loop
management to ``tests.plugins.asyncio_stub``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ``asyncio_mode`` ini option used by the suite."""

    parser.addini('asyncio_mode', 'Select asyncio integration mode', default='auto')


@pytest.fixture(scope='session')
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Provide a session-scoped event loop when pytest-asyncio is unavailable."""

    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()
