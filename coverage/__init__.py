"""Small coverage.py shim used for dependency-light test collection."""

from pathlib import Path

from .exceptions import CoverageWarning, DataError, NoDataError


class _CoverageData:
    """Minimal coverage-data object used by the shim."""

    def __init__(self) -> None:
        self._lines: dict[str, set[int]] = {}

    def measured_files(self) -> list[str]:
        """Return measured file paths."""
        return list(self._lines)

    def add_lines(self, lines: dict[str, set[int]]) -> None:
        """Merge measured line numbers into tracked files."""
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
        """Write a Cobertura-like XML report and return a fake percentage."""
        classes_xml = "\n".join(
            (
                "      "
                f'<class name="{Path(path).stem}" filename="{path}" '
                'line-rate="1.0" branch-rate="1.0" complexity="0">'
                "<lines/></class>"
            )
            for path in sorted(self._data.measured_files())
        )
        if classes_xml:
            classes_xml = f"\n{classes_xml}\n"
        xml_payload = (
            '<?xml version="1.0" ?>\n'
            '<coverage line-rate="1.0" branch-rate="1.0" '
            'lines-covered="1" lines-valid="1" '
            'branches-covered="1" branches-valid="1" '
            'complexity="0" version="0" timestamp="0">\n'
            "  <sources><source>.</source></sources>\n"
            '  <packages><package name="." line-rate="1.0" '
            'branch-rate="1.0" complexity="0">\n'
            f"    <classes>{classes_xml}    </classes>\n"
            "  </package></packages>\n"
            "</coverage>\n"
        )
        Path(outfile).write_text(xml_payload, encoding="utf-8")
        return 100.0

    def html_report(self, directory: str = "htmlcov", **kwargs) -> float:  # noqa: ARG002
        """Create an HTML directory target and return a fake percentage."""
        Path(directory).mkdir(parents=True, exist_ok=True)
        return 100.0


__all__ = ["Coverage", "CoverageWarning", "DataError", "NoDataError"]
