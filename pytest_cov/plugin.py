"""Minimal pytest-cov plugin shim.

The real pytest-cov plugin is optional in lightweight environments. This shim
implements the expected entrypoint so ``-p pytest_cov.plugin`` resolves cleanly
without affecting coverage collection.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import coverage


class _CoverageController:
  """Minimal controller that starts/stops the coverage shim."""

  def __init__(self, config: Any) -> None:
    self._config = config
    self._coverage: coverage.Coverage | None = None

  def pytest_configure(self, config: Any) -> None:
    options = getattr(config, "option", SimpleNamespace(cov_sources=()))
    sources = tuple(getattr(options, "cov_sources", ()) or ())
    self._coverage = coverage.Coverage(source=sources)
    self._coverage.start()

  def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
    _ = session, exitstatus
    if self._coverage is None:
      return
    self._coverage.stop()


def pytest_configure(config: pytest.Config) -> None:
  """Register a marker placeholder when coverage plugin is absent."""

  config.addinivalue_line("markers", "cov: dummy marker for pytest-cov shim")
