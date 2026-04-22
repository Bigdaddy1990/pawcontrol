"""Small coverage.py shim used for dependency-light test collection."""


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


class Coverage:
    """Tiny subset of ``coverage.Coverage`` used during tests."""

    def __init__(self, *args, **kwargs) -> None:
        """Store constructor arguments for compatibility checks."""
        self.args = args
        self.kwargs = kwargs

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
        """Return minimal coverage data object."""
        return _CoverageData()

    def report(self, **_kwargs: object) -> float:
        """Return synthetic terminal coverage percentage."""
        return 100.0

    def xml_report(self, outfile: str, **_kwargs: object) -> None:
        """Emit placeholder XML report output."""
        from pathlib import Path

        Path(outfile).write_text('<coverage line-rate="1"/>\n', encoding="utf-8")

    def html_report(self, directory: str, **_kwargs: object) -> None:
        """Emit placeholder HTML report output."""
        from pathlib import Path

        Path(directory).mkdir(parents=True, exist_ok=True)


__all__ = ["Coverage"]
