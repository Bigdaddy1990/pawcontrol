"""Provide a trimmed-down coverage plugin compatible with pytest-cov options."""

from __future__ import annotations

import io
import sys
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import coverage
import pytest

_REPORT_TERMINAL = {"term", "term-missing"}


@dataclass(slots=True)
class _CoverageReportSpec:
    kind: str
    options: tuple[str, ...]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the subset of pytest-cov CLI options used in CI."""

    group = parser.getgroup("cov")
    group.addoption(
        "--cov",
        action="append",
        dest="cov_sources",
        default=[],
        metavar="SOURCE",
        help="Measure coverage for the given package or path.",
    )
    group.addoption(
        "--cov-branch",
        action="store_true",
        dest="cov_branch",
        help="Enable branch coverage tracking.",
    )
    group.addoption(
        "--cov-report",
        action="append",
        dest="cov_reports",
        default=[],
        metavar="TYPE",
        help="Generate the specified coverage report (term, term-missing, xml, html).",
    )
    group.addoption(
        "--cov-fail-under",
        action="store",
        dest="cov_fail_under",
        type=float,
        help="Fail if total coverage is below the given percentage.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Activate the coverage controller when coverage options are provided."""

    options = config.option
    reports: list[str] = getattr(options, "cov_reports", [])
    sources: list[str] = getattr(options, "cov_sources", [])
    fail_under = getattr(options, "cov_fail_under", None)
    if reports or sources or fail_under is not None:
        controller = _CoverageController(config)
        config.pluginmanager.register(controller, "pawcontrol_cov_controller")


class _CoverageController:
    """Small subset of pytest-cov's orchestration for local coverage."""

    def __init__(self, config: pytest.Config) -> None:
        self._config = config
        options = config.option
        self._sources = list(getattr(options, "cov_sources", []))
        self._branch = bool(getattr(options, "cov_branch", False))
        self._reports = tuple(_parse_report_specs(getattr(options, "cov_reports", [])))
        self._fail_under = getattr(options, "cov_fail_under", None)
        self._coverage: coverage.Coverage | None = None
        self._terminal_total: float | None = None
        self._fail_message: str | None = None

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        """Initialise coverage before the test session executes."""

        self._coverage = coverage.Coverage(
            branch=self._branch,
            source=self._sources or None,
        )
        self._coverage.start()

    def pytest_runtest_call(
        self, item: pytest.Item
    ) -> None:  # pragma: no cover - executed under pytest
        """Ensure tracing stays active even if other plugins reset it."""

        if self._coverage is None:
            return

        tracer = getattr(self._coverage, "_trace", None)
        if tracer is not None:
            sys.settrace(tracer)
            threading.settrace(tracer)

    def pytest_sessionfinish(
        self, session: pytest.Session, exitstatus: int | pytest.ExitCode
    ) -> None:
        """Stop coverage collection and render the configured reports."""

        if self._coverage is None:
            return

        cov = self._coverage
        cov.stop()
        cov.save()

        total: float | None = None
        for report in self._reports:
            if report.kind in _REPORT_TERMINAL:
                total = self._write_terminal_report(cov, report)
            elif report.kind == "xml":
                self._write_xml_report(cov, report)
            elif report.kind == "html":
                self._write_html_report(cov, report)

        if self._fail_under is not None:
            if total is None:
                buffer = io.StringIO()
                total = cov.report(file=buffer, show_missing=False, skip_empty=True)
            if total < float(self._fail_under):
                message = (
                    "FAIL Required test coverage of "
                    f"{self._fail_under:.0f}% not reached. Total coverage: {total:.2f}%"
                )
                self._fail_message = message
                session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(
        self, terminalreporter: pytest.TerminalReporter
    ) -> None:
        """Surface fail-under violations at the end of the session."""

        if self._fail_message:
            terminalreporter.section("coverage", sep=" ")
            terminalreporter.write_line(self._fail_message, yellow=True, bold=True)

    def _write_terminal_report(
        self, cov: coverage.Coverage, report: _CoverageReportSpec
    ) -> float:
        show_missing = report.kind == "term-missing"
        skip_covered = "skip-covered" in report.options
        buffer = io.StringIO()
        total = cov.report(
            file=buffer,
            show_missing=show_missing,
            skip_covered=skip_covered,
            skip_empty=True,
        )
        sys.stdout.write(buffer.getvalue())
        self._terminal_total = total
        return total

    def _write_xml_report(
        self, cov: coverage.Coverage, report: _CoverageReportSpec
    ) -> None:
        output = _extract_single_option(report.options, default="coverage.xml")
        path = Path(output)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        cov.xml_report(outfile=str(path))

    def _write_html_report(
        self, cov: coverage.Coverage, report: _CoverageReportSpec
    ) -> None:
        directory = _extract_single_option(report.options, default="htmlcov")
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        cov.html_report(directory=str(path))


def _parse_report_specs(specs: Iterable[str]) -> Iterable[_CoverageReportSpec]:
    for spec in specs:
        if not spec:
            continue
        parts = tuple(part for part in spec.split(":") if part)
        kind = parts[0]
        options = parts[1:] if len(parts) > 1 else ()
        yield _CoverageReportSpec(kind=kind, options=options)


def _extract_single_option(options: tuple[str, ...], default: str) -> str:
    if not options:
        return default
    return options[-1]
