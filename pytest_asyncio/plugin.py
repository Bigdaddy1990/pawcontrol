"""Compat module for pytest-asyncio entrypoint loading."""
from __future__ import annotations

from . import event_loop
from . import fixture
from . import pytest_addoption
from . import pytest_fixture_setup
from . import pytest_pyfunc_call
from . import pytest_unconfigure

__all__ = [
  "event_loop",
  "fixture",
  "pytest_addoption",
  "pytest_fixture_setup",
  "pytest_pyfunc_call",
  "pytest_unconfigure",
]
