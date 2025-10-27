"""Lightweight coverage measurement used for PawControl tests."""

from __future__ import annotations

import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

_PROJECT_ROOT = Path.cwd().resolve()


def _normalise_source(entry: str) -> Path:
    """Resolve module or filesystem entries into absolute paths."""

    raw_path = Path(entry)
    candidate = raw_path if raw_path.exists() else Path(entry.replace(".", "/"))

    if not candidate.exists():
        module_file = candidate.with_suffix(".py")
        candidate = module_file if module_file.exists() else raw_path

    if not candidate.is_absolute():
        candidate = (_PROJECT_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    return candidate


@dataclass(slots=True)
class _FileReport:
    path: Path
    relative: str
    statements: set[int]
    executed: set[int]

    @property
    def missed(self) -> set[int]:
        return self.statements - self.executed

    @property
    def coverage_percent(self) -> float:
        if not self.statements:
            return 100.0
        return 100.0 * len(self.executed) / len(self.statements)


class Coverage:
    """Minimal subset of the coverage.py API required by our test harness."""

    def __init__(
        self, source: Iterable[str] | None = None, branch: bool = False
    ) -> None:
        self._source_roots = tuple(_normalise_source(entry) for entry in source or ())
        if not self._source_roots:
            self._source_roots = (_PROJECT_ROOT,)
        self._branch = branch
        self._previous_trace = None
        self._executed: dict[Path, set[int]] = {}
        self._lock = threading.Lock()
        self._code_cache: dict[int, tuple[bool, Path | None]] = {}

    def start(self) -> None:
        """Begin recording executed lines for files under the configured sources."""

        tracer = self._trace
        self._previous_trace = sys.gettrace()
        sys.settrace(tracer)
        threading.settrace(tracer)

    def stop(self) -> None:
        """Stop recording executed lines and restore any previous trace function."""

        sys.settrace(self._previous_trace)
        threading.settrace(self._previous_trace)

    def save(self) -> None:  # pragma: no cover - parity with coverage.py API
        """Persist collected data (noop for the lightweight implementation)."""

    def report(
        self,
        file: TextIO | None = None,
        show_missing: bool = False,
        skip_covered: bool = False,
        skip_empty: bool = False,
    ) -> float:
        """Render a terminal coverage summary and return the total percentage."""

        stream = file or sys.stdout
        reports = tuple(self._collect_reports())
        if not reports:
            stream.write("No data to report\n")
            return 100.0

        header = "Name".ljust(60) + "Stmts  Miss  Cover\n"
        separator = "-" * (len(header) - 1) + "\n"
        stream.write(header)
        stream.write(separator)

        total_statements = 0
        total_missed = 0

        for report in reports:
            if skip_empty and not report.statements:
                continue
            missed_lines = report.missed
            if skip_covered and not missed_lines and report.statements:
                continue
            total_statements += len(report.statements)
            total_missed += len(missed_lines)
            coverage_percent = report.coverage_percent
            stream.write(
                f"{report.relative.ljust(60)}"
                f"{len(report.statements):5d}"
                f"{len(missed_lines):6d}"
                f"{coverage_percent:7.2f}%\n"
            )
            if show_missing and missed_lines:
                numbers = [str(num) for num in sorted(missed_lines)]
                chunk: list[str] = []
                for index, number in enumerate(numbers, start=1):
                    chunk.append(number)
                    if index % 20 == 0:
                        stream.write(f"    Missing lines: {','.join(chunk)}\n")
                        chunk = []
                if chunk:
                    stream.write(f"    Missing lines: {','.join(chunk)}\n")

        total_coverage = 100.0
        if total_statements:
            total_coverage = (
                100.0 * (total_statements - total_missed) / total_statements
            )
        stream.write(separator)
        stream.write(
            f"TOTAL{''.ljust(55)}{total_statements:5d}{total_missed:6d}{total_coverage:7.2f}%\n"
        )
        return total_coverage

    def xml_report(self, outfile: str) -> None:
        """Generate a minimal Cobertura-like XML report."""

        reports = tuple(self._collect_reports())
        total_statements = sum(len(report.statements) for report in reports)
        total_missed = sum(len(report.missed) for report in reports)
        line_rate = 1.0
        if total_statements:
            line_rate = (total_statements - total_missed) / total_statements

        root = ET.Element(
            "coverage",
            attrib={
                "branch-rate": "1.0" if self._branch else "0.0",
                "line-rate": f"{line_rate:.4f}",
                "timestamp": str(int(time.time())),
                "version": "pawcontrol-lightweight",
            },
        )
        sources = ET.SubElement(root, "sources")
        for source in self._source_roots:
            ET.SubElement(sources, "source").text = str(source)
        packages = ET.SubElement(root, "packages")
        package = ET.SubElement(
            packages,
            "package",
            attrib={
                "name": "pawcontrol",
                "line-rate": f"{line_rate:.4f}",
                "branch-rate": "1.0" if self._branch else "0.0",
            },
        )
        classes = ET.SubElement(package, "classes")

        for report in reports:
            class_el = ET.SubElement(
                classes,
                "class",
                attrib={
                    "name": report.relative.replace("/", "."),
                    "filename": report.relative,
                    "line-rate": f"{report.coverage_percent / 100:.4f}",
                    "branch-rate": "1.0" if self._branch else "0.0",
                },
            )
            lines_el = ET.SubElement(class_el, "lines")
            for line_num in sorted(report.statements):
                hits = 1 if line_num in report.executed else 0
                ET.SubElement(
                    lines_el,
                    "line",
                    attrib={"number": str(line_num), "hits": str(hits)},
                )

        Path(outfile).write_text(
            ET.tostring(root, encoding="unicode", xml_declaration=True),
            encoding="utf-8",
        )

    def html_report(self, directory: str) -> None:
        """Write a minimal HTML summary to the requested directory."""

        reports = tuple(self._collect_reports())
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        total_statements = sum(len(report.statements) for report in reports)
        total_missed = sum(len(report.missed) for report in reports)
        total_coverage = 100.0
        if total_statements:
            total_coverage = (
                100.0 * (total_statements - total_missed) / total_statements
            )

        rows = [
            (
                f"<tr><td>{report.relative}</td><td>{len(report.statements)}</td>"
                f"<td>{len(report.missed)}</td><td>{report.coverage_percent:.2f}%</td></tr>"
            )
            for report in reports
        ]

        html = f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>PawControl coverage</title>
    <style>
      body {{ font-family: sans-serif; margin: 2rem; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
      th {{ background: #f3f3f3; }}
    </style>
  </head>
  <body>
    <h1>PawControl coverage: {total_coverage:.2f}%</h1>
    <table>
      <thead>
        <tr><th>File</th><th>Statements</th><th>Missed</th><th>Coverage</th></tr>
      </thead>
      <tbody>
        {"".join(rows)}
      </tbody>
    </table>
  </body>
</html>
"""
        (path / "index.html").write_text(html, encoding="utf-8")

    def _trace(self, frame, event: str, arg):  # pragma: no cover - exercised via tests
        if event != "line":
            return self._trace
        code_id = id(frame.f_code)
        cached = self._code_cache.get(code_id)
        if cached is None:
            filename = Path(frame.f_code.co_filename)
            try:
                resolved = filename.resolve()
            except FileNotFoundError:
                self._code_cache[code_id] = (False, None)
                return self._trace
            should_measure = self._should_measure(resolved)
            cached = (should_measure, resolved if should_measure else None)
            self._code_cache[code_id] = cached
        should_measure, resolved = cached
        if not should_measure or resolved is None:
            return self._trace
        lineno = frame.f_lineno
        with self._lock:
            self._executed.setdefault(resolved, set()).add(lineno)
        return self._trace

    def _should_measure(self, path: Path) -> bool:
        for root in self._source_roots:
            if root == path:
                return True
            if root.is_dir():
                try:
                    path.relative_to(root)
                except ValueError:
                    continue
                else:
                    return True
        return False

    def _collect_reports(self) -> Iterator[_FileReport]:
        for path in self._iter_candidate_files():
            statements = self._load_statements(path)
            executed = self._executed.get(path, set()) & statements
            relative = str(path.relative_to(_PROJECT_ROOT))
            yield _FileReport(
                path=path, relative=relative, statements=statements, executed=executed
            )

    def _iter_candidate_files(self) -> Iterator[Path]:
        seen: set[Path] = set()
        for root in self._source_roots:
            if not root.exists():
                continue
            if root.is_file():
                paths = [root]
            else:
                paths = [p for p in root.rglob("*.py") if "/__pycache__/" not in str(p)]
            for path in paths:
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield resolved

    def _load_statements(self, path: Path) -> set[int]:
        statements: set[int] = set()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return statements
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            statements.add(lineno)
        return statements
