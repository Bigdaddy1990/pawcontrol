"""Minimal pytest-asyncio stub for isolated test environments.

Provides the small subset of plugin behavior exercised by the PawControl
test suite without requiring the real pytest-asyncio dependency.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator

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
    loop.close()


event_loop = pytest.fixture(_event_loop)
event_loop._fixture_function = _event_loop
fixture = pytest.fixture

__all__ = [
  "event_loop",
  "fixture",
  "pytest_addoption",
]
