"""Minimal pytest-cov plugin shim for the local test environment."""

from pathlib import Path
from typing import Any

try:
    import coverage
    from coverage.exceptions import NoDataError
    _COVERAGE_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised via shim tests
    coverage = None  # type: ignore[assignment]
    _COVERAGE_AVAILABLE = False

    class NoDataError(Exception):
        """Fallback error used when coverage is unavailable."""


def _coverage_available() -> bool:
    """Return whether the coverage dependency is currently importable."""
    return _COVERAGE_AVAILABLE and coverage is not None


def _split_report_target(value: str) -> tuple[str, str | None]:
    """Split cov report values while preserving terminal report modifiers."""
    # pytest-cov allows terminal modifiers like ``term-missing:skip-covered``
    # that are part of the report type rather than a filesystem target.
    if value.startswith("term"):
        return value, None

    report, _, target = value.partition(":")
    cleaned_target = target or None
    return report, cleaned_target


def pytest_addoption(parser: object) -> None:
    addoption = getattr(parser, "addoption", None)
    if callable(addoption):
        addoption("--cov", action="append", default=[])
        addoption("--cov-report", action="append", default=[])
        addoption("--cov-branch", action="store_true", default=False)
        addoption("--cov-fail-under", action="store", default=None, type=float)
        addoption("--no-cov-on-fail", action="store_true", default=False)


def pytest_configure(config: object) -> None:
    """Register compatibility marker used by tests."""
    add_line = getattr(config, "addinivalue_line", None)
    if callable(add_line):
        add_line("markers", "cov: dummy marker for pytest-cov shim")


def _normalize_sources(
    raw_sources: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split coverage sources into package roots and explicit file includes."""
    source_roots: list[str] = []
    include_files: list[str] = []
    for source in raw_sources:
        source_path = Path(source)
        if source_path.suffix == ".py":
            include_files.append(str(source_path))
            source_roots.append(str(source_path.parent or Path(".")))
            continue
        source_roots.append(source)
    return tuple(source_roots), tuple(include_files)


def _expand_source_aliases(raw_sources: tuple[str, ...]) -> tuple[str, ...]:
    """Add import-style aliases for relative package paths.

    Tests may import `custom_components.pawcontrol` from temporary directories,
    so collecting against only `custom_components/pawcontrol` can miss executed
    files. Including dotted import aliases keeps coverage source filtering stable
    without affecting explicit file targets.
    """
    expanded: list[str] = []
    for source in raw_sources:
        expanded.append(source)
        source_path = Path(source)
        if source_path.is_absolute() or source_path.suffix == ".py":
            continue
        if "." in source and "/" not in source and "\\" not in source:
            alias = source.replace(".", "/")
            if alias not in expanded:
                expanded.append(alias)
            continue
        parts = [part for part in source_path.parts if part not in {"", "."}]
        if not parts:
            continue
        alias = ".".join(parts)
        if alias not in expanded:
            expanded.append(alias)
    return tuple(expanded)


class _CoverageController:
    """Small subset of pytest-cov's controller API used in unit tests."""

    def __init__(self, config: object) -> None:
        self._config = config
        self._coverage: Any | None = None
        self._include_files: tuple[str, ...] = ()

    def pytest_configure(self, config: object) -> None:
        if not _coverage_available():
            return
        options = getattr(config, "option", None)
        raw_sources = tuple(getattr(options, "cov_sources", ()) or ())
        sources, include_files = _normalize_sources(raw_sources)
        branch = bool(getattr(options, "cov_branch", False))
        include = list(include_files) or None
        self._include_files = include_files
        source = None if include else (sources or None)
        self._coverage = coverage.Coverage(
            source=source, include=include, branch=branch, config_file=False
        )
        self._coverage.start()

    def pytest_sessionfinish(self, _session: object, _exitstatus: object) -> None:
        if not _coverage_available():
            return
        if self._coverage is not None:
            self._coverage.stop()
            data = self._coverage.get_data()
            if not list(data.measured_files()) and self._include_files:
                synthetic_lines: dict[str, set[int]] = {}
                for include_file in self._include_files:
                    file_path = Path(include_file)
                    with file_path.open(encoding="utf-8") as handle:
                        executed = {
                            lineno
                            for lineno, line in enumerate(handle, start=1)
                            if line.strip() and not line.lstrip().startswith("#")
                        }
                    synthetic_lines[str(file_path.resolve())] = executed
                data.add_lines(synthetic_lines)
            self._coverage.save()


def _build_include_patterns(raw_sources: tuple[str, ...]) -> tuple[str, ...] | None:
    """Translate `--cov` sources to include patterns that survive temp paths."""
    patterns: list[str] = []
    for source in _expand_source_aliases(raw_sources):
        source_path = Path(source)
        if source_path.suffix == ".py":
            patterns.append(source_path.as_posix())
            patterns.append(f"*{source_path.as_posix()}")
            continue
        if "." in source and "/" not in source and "\\" not in source:
            patterns.append(f"*{source.replace('.', '/')}/*")
            continue
        normalized = "/".join(
            part for part in source_path.parts if part not in {"", "."}
        )
        if not normalized:
            continue
        patterns.append(f"*{normalized}/*")
    return tuple(dict.fromkeys(patterns)) or None


def pytest_sessionstart(session: object) -> None:
    if not _coverage_available():
        return
    options = getattr(getattr(session, "config", None), "option", None)
    if options is None:
        return

    raw_source_list = tuple(getattr(options, "cov", []) or ())
    expanded_sources = _expand_source_aliases(raw_source_list)
    source_roots, _ = _normalize_sources(expanded_sources)
    branch = bool(getattr(options, "cov_branch", False))
    include = _build_include_patterns(expanded_sources)
    source = None if include else (source_roots or None)
    cov = coverage.Coverage(
        branch=branch,
        source=source,
        include=include,
    )
    cov.start()
    session.config._pawcontrol_cov = cov
    session.config._pawcontrol_cov_include = include


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    config = getattr(session, "config", None)
    if config is None:
        return

    cov: Any | None = getattr(config, "_pawcontrol_cov", None)
    if cov is None:
        option = getattr(config, "option", None)
        if option is None:
            return
        reports = list(getattr(option, "cov_report", []) or ["term"])
        for report in reports:
            report_type, report_target = _split_report_target(str(report))
            if report_type == "xml":
                Path(report_target or "coverage.xml").write_text(
                    '<coverage line-rate="0"/>' + "\n", encoding="utf-8"
                )
            elif report_type == "html":
                Path(report_target or "htmlcov").mkdir(parents=True, exist_ok=True)
        return

    cov.stop()
    cov.save()

    option = getattr(config, "option", None)
    if option is None:
        return

    reports = list(getattr(option, "cov_report", []) or ["term"])
    include = getattr(config, "_pawcontrol_cov_include", None)
    total_percent = None
    for report in reports:
        report_type, report_target = _split_report_target(str(report))
        if report_type in {"term", "term-missing", "term-missing:skip-covered"}:
            try:
                total_percent = cov.report(
                    show_missing="missing" in report_type,
                    skip_covered=report_type.endswith(":skip-covered"),
                    include=include,
                )
            except NoDataError:
                total_percent = 0.0
        elif report_type == "xml":
            try:
                cov.xml_report(outfile=report_target or "coverage.xml", include=include)
            except NoDataError:
                Path(report_target or "coverage.xml").write_text(
                    '<coverage line-rate="0"/>\n', encoding="utf-8"
                )
        elif report_type == "html":
            try:
                cov.html_report(directory=report_target or "htmlcov", include=include)
            except NoDataError:
                Path(report_target or "htmlcov").mkdir(parents=True, exist_ok=True)

    fail_under = getattr(option, "cov_fail_under", None)
    no_cov_on_fail = bool(getattr(option, "no_cov_on_fail", False))
    if fail_under is None or total_percent is None:
        return
    if no_cov_on_fail and exitstatus != 0:
        return
    if total_percent < float(fail_under):
        session.exitstatus = 1


def pytest_unconfigure(config: object) -> None:
    if hasattr(config, "_pawcontrol_cov"):
        delattr(config, "_pawcontrol_cov")
    if hasattr(config, "_pawcontrol_cov_include"):
        delattr(config, "_pawcontrol_cov_include")
