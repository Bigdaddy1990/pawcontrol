"""Minimal pytest-cov plugin shim.

The real pytest-cov plugin is optional in lightweight environments. This shim
implements the expected entrypoint so ``-p pytest_cov.plugin`` resolves cleanly
without affecting coverage collection.
"""

from types import SimpleNamespace
from typing import Any

import coverage
import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register coverage-related options so pytest can parse addopts."""  # noqa: E111

    group = parser.getgroup("cov")  # noqa: E111
    group.addoption(  # noqa: E111
        "--cov",
        action="append",
        default=[],
        dest="cov_sources",
        metavar="SOURCE",
        help="(shim) Measure coverage for file or package.",
    )
    group.addoption(  # noqa: E111
        "--cov-report",
        action="append",
        default=[],
        metavar="TYPE",
        help="(shim) Type of coverage report to generate.",
    )
    group.addoption(  # noqa: E111
        "--cov-branch",
        action="store_true",
        default=False,
        help="(shim) Enable branch coverage.",
    )
    group.addoption(  # noqa: E111
        "--no-cov-on-fail",
        action="store_true",
        default=False,
        help="(shim) Do not report coverage if tests fail.",
    )


class _CoverageController:
    """Minimal controller that starts/stops the coverage shim."""  # noqa: E111

    def __init__(self, config: Any) -> None:  # noqa: E111
        self._config = config
        self._coverage: coverage.Coverage | None = None

    def pytest_configure(self, config: Any) -> None:  # noqa: E111
        options = getattr(config, "option", SimpleNamespace(cov_sources=()))
        sources = tuple(getattr(options, "cov_sources", ()) or ())
        self._coverage = coverage.Coverage(source=sources)
        self._coverage.start()

    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:  # noqa: E111
        _ = session, exitstatus
        if self._coverage is None:
            return  # noqa: E111
        self._coverage.stop()


def pytest_configure(config: pytest.Config) -> None:
    """Register a marker placeholder when coverage plugin is absent."""  # noqa: E111

    config.addinivalue_line("markers", "cov: dummy marker for pytest-cov shim")  # noqa: E111
    controller = _CoverageController(config)  # noqa: E111
    controller.pytest_configure(config)  # noqa: E111
    pluginmanager = getattr(config, "pluginmanager", None)  # noqa: E111
    register = getattr(pluginmanager, "register", None)  # noqa: E111
    if callable(register):  # noqa: E111
        register(controller, "cov-controller-shim")
