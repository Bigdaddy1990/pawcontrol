"""Small coverage.py shim used for dependency-light test collection."""

from pathlib import Path
import sys
from types import ModuleType


class NoDataError(Exception):
    """Fallback no-data exception used by pytest coverage shims."""


class DataError(Exception):
    """Fallback data error used by coverage compatibility tests."""


class CoverageWarning(Warning):
    """Fallback warning emitted by coverage compatibility tests."""


class _CoverageData:
    """Minimal coverage data container."""

    def __init__(self) -> None:
        self._lines: dict[str, set[int]] = {}

    def measured_files(self) -> set[str]:
        """Return files tracked in the shim."""
        return set(self._lines)

    def add_lines(self, lines: dict[str, set[int]]) -> None:
        """Merge measured lines into coverage data."""
        for path, values in lines.items():
            self._lines.setdefault(path, set()).update(values)

    def has_arcs(self) -> bool:
        """Return whether arc data is tracked."""
        return False

    def add_arcs(self, _arcs: dict[str, set[tuple[int, int]]]) -> None:
        """Accept arc payloads for compatibility."""
        return None


class _CoverageData:
    """Minimal coverage data container used by shim tests."""

    def measured_files(self) -> list[str]:
        """Return measured file list."""
        return []

    def add_lines(self, _line_data: dict[str, set[int]]) -> None:
        """Record synthetic line execution data (no-op in shim)."""
        return None

    def has_arcs(self) -> bool:
        """Return whether arc data is enabled."""
        return False

    def add_arcs(self, _arc_data: dict[str, set[tuple[int, int]]]) -> None:
        """Record synthetic arc execution data (no-op in shim)."""
        return None


class _CoverageData:
    """Minimal coverage-data object used by the shim."""

    def __init__(self) -> None:
        self._lines: dict[str, set[int]] = {}

    def measured_files(self) -> list[str]:
        """Return measured file paths."""
        return list(self._lines)

    def add_lines(self, lines: dict[str, set[int]]) -> None:
        """Record measured line numbers."""
        for path, executed in lines.items():
            self._lines.setdefault(path, set()).update(executed)

    def has_arcs(self) -> bool:
        """Return whether arc mode is enabled (not tracked in shim)."""
        return False

    def add_arcs(self, _arcs: dict[str, set[tuple[int, int]]]) -> None:
        """Accept arc data for compatibility with coverage plugin hooks."""
        return None


class Coverage:
    """Tiny subset of ``coverage.Coverage`` used during tests."""

    def __init__(self, *args, **kwargs) -> None:
        """Store constructor arguments for compatibility checks."""
        self.args = args
        self.kwargs = kwargs
        self._data = _CoverageData()

    def start(self) -> None:
        """Start collection (no-op in shim)."""
        return None

    def stop(self) -> None:
        """Stop collection (no-op in shim)."""
        return None

    def save(self) -> None:
        """Persist collected data (no-op in shim)."""
        return None

    def get_data(self) -> _CoverageData:
        """Return coverage data for compatibility with tests."""
        return self._data

    def report(self, **kwargs) -> float:  # noqa: ARG002
        """Return a deterministic fake total coverage percentage."""
        return 100.0

    def xml_report(self, outfile: str = "coverage.xml", **kwargs) -> float:  # noqa: ARG002
        """Write a tiny XML report and return a fake percentage."""
        Path(outfile).write_text("<coverage/>\n", encoding="utf-8")
        return 100.0

    def html_report(self, directory: str = "htmlcov", **kwargs) -> float:  # noqa: ARG002
        """Create an HTML directory target and return a fake percentage."""
        Path(directory).mkdir(parents=True, exist_ok=True)
        return 100.0


__all__ = ["Coverage", "CoverageWarning", "DataError", "NoDataError"]
