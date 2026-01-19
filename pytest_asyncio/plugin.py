"""Compat module for pytest-asyncio entrypoint loading."""

from __future__ import annotations

from . import (  # noqa: F401
  event_loop,
  fixture,
  pytest_addoption,
  pytest_fixture_setup,
  pytest_pyfunc_call,
  pytest_unconfigure,
)

__all__ = [
  "event_loop",
  "fixture",
  "pytest_addoption",
  "pytest_fixture_setup",
  "pytest_pyfunc_call",
  "pytest_unconfigure",
]
