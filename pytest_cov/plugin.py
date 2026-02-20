"""Minimal pytest-cov plugin shim for the local test environment."""

from __future__ import annotations

import coverage


def pytest_addoption(parser: object) -> None:
    addoption = getattr(parser, "addoption", None)
    if callable(addoption):
        addoption("--cov", action="append", default=[])
        addoption("--cov-report", action="append", default=[])
        addoption("--cov-branch", action="store_true", default=False)
        addoption("--no-cov-on-fail", action="store_true", default=False)


def pytest_configure(config: object) -> None:
    """Register compatibility marker used by tests."""
    add_line = getattr(config, "addinivalue_line", None)
    if callable(add_line):
        add_line("markers", "cov: dummy marker for pytest-cov shim")


class _CoverageController:
    """Small subset of pytest-cov's controller API used in unit tests."""

    def __init__(self, config: object) -> None:
        self._config = config
        self._coverage: coverage.Coverage | None = None

    def pytest_configure(self, config: object) -> None:
        options = getattr(config, "option", None)
        sources = tuple(getattr(options, "cov_sources", ()) or ())
        branch = bool(getattr(options, "cov_branch", False))
        self._coverage = coverage.Coverage(source=sources, branch=branch)
        self._coverage.start()

    def pytest_sessionfinish(self, _session: object, _exitstatus: object) -> None:
        if self._coverage is not None:
            self._coverage.stop()
            self._coverage.save()
