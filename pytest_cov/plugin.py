"""Minimal pytest-cov plugin shim.

The real pytest-cov plugin is optional in lightweight environments. This shim
implements the expected entrypoint so ``-p pytest_cov.plugin`` resolves cleanly
without affecting coverage collection.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
  """Register a marker placeholder when coverage plugin is absent."""

  config.addinivalue_line("markers", "cov: dummy marker for pytest-cov shim")
