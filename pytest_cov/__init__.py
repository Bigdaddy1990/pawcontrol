"""Stub package for pytest-cov to satisfy plugin discovery in isolated CI runs."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
  """Register coverage-related options so pytest can parse addopts."""

  group = parser.getgroup("cov")
  group.addoption(
    "--cov",
    action="append",
    default=[],
    metavar="SOURCE",
    help="(shim) Measure coverage for file or package.",
  )
  group.addoption(
    "--cov-report",
    action="append",
    default=[],
    metavar="TYPE",
    help="(shim) Type of coverage report to generate.",
  )
  group.addoption(
    "--cov-branch",
    action="store_true",
    default=False,
    help="(shim) Enable branch coverage.",
  )
  group.addoption(
    "--no-cov-on-fail",
    action="store_true",
    default=False,
    help="(shim) Do not report coverage if tests fail.",
  )


def pytest_configure(config: pytest.Config) -> None:
  """Register a marker placeholder when coverage plugin is absent."""

  config.addinivalue_line("markers", "cov: dummy marker for pytest-cov shim")
