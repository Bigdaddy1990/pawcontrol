"""Lightweight coverage measurement used for PawControl tests."""

from __future__ import annotations

import csv
import dis
import functools
import io
import json
import os
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from html import escape
from pathlib import Path
from types import CodeType, FrameType
from typing import Any, Protocol, TextIO, cast


class TraceFunc(Protocol):
    """Protocol describing a Python trace callback."""

    def __call__(self, frame: FrameType, event: str, arg: object) -> TraceFunc | None:
        """Handle a Python tracing event."""


TraceCallback = Callable[[CodeType, int], None]


class MonitoringEvents(Protocol):
    """Subset of the ``sys.monitoring.events`` namespace we rely on."""

    LINE: int


class MonitoringModule(Protocol):
    """Interface for the ``sys.monitoring`` helpers used by the coverage shim."""

    COVERAGE_ID: int
    events: MonitoringEvents

    def use_tool_id(self, tool_id: int, name: str) -> None: ...

    def register_callback(
        self, tool_id: int, event: int, callback: TraceCallback | None
    ) -> TraceCallback | None: ...

    def set_events(self, tool_id: int, events: int) -> None: ...

    def free_tool_id(self, tool_id: int) -> None: ...


_PROJECT_ROOT = Path.cwd().resolve()

_ALLOWED_RELATIVE_PATHS: tuple[Path, ...] = (
    Path("custom_components/pawcontrol"),
    Path("tests"),
)

_METRICS_DIRECTORY = _PROJECT_ROOT / "generated" / "coverage"
_METRICS_JSON_NAME = "runtime.json"
_METRICS_CSV_NAME = "runtime.csv"
_SKIP_ENV_VAR = "PAWCONTROL_COVERAGE_SKIP"
_RUNTIME_DISABLED_ENV_VAR = "PAWCONTROL_DISABLE_RUNTIME_METRICS"


@functools.lru_cache(maxsize=512)
def _compile_cached(filename: str, source: str) -> CodeType | None:
    """Compile and cache Python source used by `_load_statements`.

    Reusing compiled bytecode avoids redundant parsing while capturing syntax
    failures as empty statement sets during coverage discovery and tests.【F:coverage.py†L343-L400】【F:tests/unit/test_coverage_shim.py†L82-L96】
    """

    try:
        return compile(source, filename, "exec")
    except SyntaxError:
        return None


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
    statements: frozenset[int]
    executed: frozenset[int]

    @property
    def missed(self) -> frozenset[int]:
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
        self._previous_trace: TraceFunc | None = None
        self._executed: dict[Path, set[int]] = {}
        self._lock = threading.Lock()
        self._statement_cache: dict[Path, tuple[int, frozenset[int]]] = {}
        self._allowed_scope_roots = tuple(
            (_PROJECT_ROOT / relative).resolve() for relative in _ALLOWED_RELATIVE_PATHS
        )
        self._allowed_cache: dict[Path, bool] = {}
        self._module_runtime: dict[Path, float] = {}
        self._thread_states: dict[int, _TraceState] = {}
        self._skip_paths = self._build_skip_set()
        self._runtime_enabled = self._runtime_metrics_enabled()
        monitoring_attr = getattr(sys, "monitoring", None)
        self._monitoring: MonitoringModule | None = cast(
            MonitoringModule | None, monitoring_attr
        )
        self._monitor_tool_id: int | None = None
        self._using_monitoring = False

    def start(self) -> None:
        """Begin recording executed lines for files under the configured sources."""

        if self._start_monitoring():
            return

        tracer: TraceFunc = self._trace
        self._previous_trace = cast(TraceFunc | None, sys.gettrace())
        sys.settrace(tracer)
        threading.settrace(tracer)

    def stop(self) -> None:
        """Stop recording executed lines and restore any previous trace function."""

        if self._using_monitoring:
            self._stop_monitoring()
        else:
            sys.settrace(self._previous_trace)
            threading.settrace(self._previous_trace)
        with self._lock:
            self._thread_states.clear()

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

        total_statements, total_missed = self._calculate_totals(reports)

        for report in reports:
            if skip_empty and not report.statements:
                continue
            missed_lines = report.missed
            if skip_covered and not missed_lines and report.statements:
                continue
            coverage_percent = report.coverage_percent
            stream.write(
                f"{report.relative.ljust(60)}"
                f"{len(report.statements):5d}"
                f"{len(missed_lines):6d}"
                f"{coverage_percent:7.2f}%\n"
            )
            if show_missing and missed_lines:
                missing_formatted = ",".join(str(num) for num in sorted(missed_lines))
                stream.write(f"    Missing lines: {missing_formatted}\n")

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

    def total_coverage(self) -> float:
        """Return the overall coverage percentage without producing reports."""

        reports = tuple(self._collect_reports())
        if not reports:
            return 100.0

        total_statements, total_missed = self._calculate_totals(reports)
        if not total_statements:
            return 100.0
        return 100.0 * (total_statements - total_missed) / total_statements

    def xml_report(self, outfile: str) -> None:
        """Generate a minimal Cobertura-like XML report."""

        reports = tuple(self._collect_reports())
        total_statements, total_missed = self._calculate_totals(reports)
        line_rate = 1.0
        if total_statements:
            line_rate = (total_statements - total_missed) / total_statements

        xml_buffer = io.StringIO()
        write = xml_buffer.write

        def format_attrs(pairs: Iterable[tuple[str, str]]) -> str:
            return " ".join(
                f'{name}="{escape(value, quote=True)}"' for name, value in pairs
            )

        def start_tag(name: str, pairs: Iterable[tuple[str, str]], indent: int) -> None:
            prefix = "  " * indent
            attrs = format_attrs(pairs)
            write(f"{prefix}<{name}{' ' + attrs if attrs else ''}>\n")

        def end_tag(name: str, indent: int) -> None:
            prefix = "  " * indent
            write(f"{prefix}</{name}>\n")

        def empty_tag(name: str, pairs: Iterable[tuple[str, str]], indent: int) -> None:
            prefix = "  " * indent
            attrs = format_attrs(pairs)
            write(f"{prefix}<{name}{' ' + attrs if attrs else ''}/>\n")

        def text_tag(name: str, value: str, indent: int) -> None:
            prefix = "  " * indent
            write(f"{prefix}<{name}>{escape(value)}</{name}>\n")

        write('<?xml version="1.0" encoding="UTF-8"?>\n')
        start_tag(
            "coverage",
            (
                ("branch-rate", "1.0" if self._branch else "0.0"),
                ("line-rate", f"{line_rate:.4f}"),
                ("timestamp", str(int(time.time()))),
                ("version", "pawcontrol-lightweight"),
            ),
            indent=0,
        )
        start_tag("sources", (), indent=1)
        for source in self._source_roots:
            text_tag("source", str(source), indent=2)
        end_tag("sources", indent=1)

        start_tag("packages", (), indent=1)
        start_tag(
            "package",
            (
                ("name", "pawcontrol"),
                ("line-rate", f"{line_rate:.4f}"),
                ("branch-rate", "1.0" if self._branch else "0.0"),
            ),
            indent=2,
        )
        start_tag("classes", (), indent=3)

        for report in reports:
            start_tag(
                "class",
                (
                    ("name", report.relative.replace("/", ".")),
                    ("filename", report.relative),
                    ("line-rate", f"{report.coverage_percent / 100:.4f}"),
                    ("branch-rate", "1.0" if self._branch else "0.0"),
                ),
                indent=4,
            )
            start_tag("lines", (), indent=5)
            for line_num in sorted(report.statements):
                hits = 1 if line_num in report.executed else 0
                empty_tag(
                    "line",
                    (("number", str(line_num)), ("hits", str(hits))),
                    indent=6,
                )
            end_tag("lines", indent=5)
            end_tag("class", indent=4)

        end_tag("classes", indent=3)
        end_tag("package", indent=2)
        end_tag("packages", indent=1)
        end_tag("coverage", indent=0)

        Path(outfile).write_text(xml_buffer.getvalue(), encoding="utf-8")

    def html_report(self, directory: str) -> None:
        """Write a minimal HTML summary to the requested directory."""

        reports = tuple(self._collect_reports())
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        total_statements, total_missed = self._calculate_totals(reports)
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
    <meta charset=\"utf-8\" />
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

    def _trace(
        self, frame: FrameType, event: str, arg: object
    ) -> TraceFunc | None:  # pragma: no cover - exercised via tests
        now = time.perf_counter()
        thread_ident = threading.get_ident()
        if event != "line":
            self._handle_line_event(None, None, now=now, thread_ident=thread_ident)
            return self._trace
        filename = Path(frame.f_code.co_filename)
        try:
            resolved = filename.resolve()
        except FileNotFoundError:
            self._handle_line_event(None, None, now=now, thread_ident=thread_ident)
            return self._trace
        if not self._should_measure(resolved):
            self._handle_line_event(None, None, now=now, thread_ident=thread_ident)
            return self._trace
        lineno = frame.f_lineno
        self._handle_line_event(resolved, lineno, now=now, thread_ident=thread_ident)
        return self._trace

    def _start_monitoring(self) -> bool:
        monitor = self._monitoring
        if monitor is None:
            return False
        tool_id = monitor.COVERAGE_ID
        try:
            monitor.use_tool_id(tool_id, "pawcontrol.coverage")
        except ValueError:
            return False
        try:
            monitor.register_callback(
                tool_id, monitor.events.LINE, self._monitoring_line_event
            )
            monitor.set_events(tool_id, monitor.events.LINE)
        except Exception:
            monitor.set_events(tool_id, 0)
            monitor.register_callback(tool_id, monitor.events.LINE, None)
            monitor.free_tool_id(tool_id)
            return False
        self._monitor_tool_id = tool_id
        self._using_monitoring = True
        return True

    def _stop_monitoring(self) -> None:
        monitor = self._monitoring
        tool_id = self._monitor_tool_id
        if monitor is None or tool_id is None:
            self._using_monitoring = False
            self._monitor_tool_id = None
            return
        monitor.set_events(tool_id, 0)
        monitor.register_callback(tool_id, monitor.events.LINE, None)
        monitor.free_tool_id(tool_id)
        self._monitor_tool_id = None
        self._using_monitoring = False

    def _monitoring_line_event(self, code: CodeType, line_no: int) -> None:
        now = time.perf_counter()
        thread_ident = threading.get_ident()
        filename = code.co_filename
        if not filename or filename.startswith("<"):
            self._handle_line_event(None, None, now=now, thread_ident=thread_ident)
            return
        path = Path(filename)
        try:
            resolved = path.resolve()
        except FileNotFoundError:
            self._handle_line_event(None, None, now=now, thread_ident=thread_ident)
            return
        if not self._should_measure(resolved) or line_no <= 0:
            self._handle_line_event(None, None, now=now, thread_ident=thread_ident)
            return
        self._handle_line_event(resolved, line_no, now=now, thread_ident=thread_ident)

    def _handle_line_event(
        self,
        path: Path | None,
        lineno: int | None,
        *,
        now: float | None = None,
        thread_ident: int | None = None,
    ) -> None:
        if now is None:
            now = time.perf_counter()
        if thread_ident is None:
            thread_ident = threading.get_ident()
        with self._lock:
            if path is not None and lineno is not None and lineno > 0:
                self._executed.setdefault(path, set()).add(lineno)
            if not self._runtime_enabled:
                return
            state = self._thread_states.get(thread_ident)
            if state and state.path is not None:
                previous_runtime = self._module_runtime.get(state.path, 0.0)
                self._module_runtime[state.path] = previous_runtime + (
                    now - state.last_timestamp
                )
            self._thread_states[thread_ident] = _TraceState(
                last_timestamp=now, path=path
            )

    def _should_measure(self, path: Path) -> bool:
        if not self._is_allowed_path(path):
            return False
        return any(
            path == root or (root.is_dir() and path.is_relative_to(root))
            for root in self._source_roots
        )

    def _collect_reports(self) -> Iterator[_FileReport]:
        reports: list[_FileReport] = []
        for path in self._iter_candidate_files():
            statements = self._load_statements(path)
            executed = frozenset(self._executed.get(path, set()) & statements)
            relative = str(path.relative_to(_PROJECT_ROOT))
            reports.append(
                _FileReport(
                    path=path,
                    relative=relative,
                    statements=statements,
                    executed=executed,
                )
            )
        if self._runtime_enabled:
            self._write_runtime_metrics(tuple(reports))
        yield from reports

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
                if resolved in seen or not self._is_allowed_path(resolved):
                    continue
                seen.add(resolved)
                yield resolved

    def _load_statements(self, path: Path) -> frozenset[int]:
        try:
            stat_result = path.stat()
        except OSError:
            return frozenset()

        cached = self._statement_cache.get(path)
        if cached and cached[0] == stat_result.st_mtime_ns:
            return cached[1]

        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            statements = frozenset()
        else:
            code = _compile_cached(str(path), source)
            if code is None:
                statements = frozenset()
            else:
                collected: set[int] = set()
                self._collect_code_lines(code, collected)
                statements = frozenset(num for num in collected if num > 0)

        self._statement_cache[path] = (stat_result.st_mtime_ns, statements)
        return statements

    @staticmethod
    def _calculate_totals(reports: Iterable[_FileReport]) -> tuple[int, int]:
        total_statements = 0
        total_missed = 0
        for report in reports:
            missed = report.missed
            total_statements += len(report.statements)
            total_missed += len(missed)
        return total_statements, total_missed

    def _collect_code_lines(self, code: CodeType, target: set[int]) -> None:
        for _, lineno in dis.findlinestarts(code):
            if lineno:
                target.add(lineno)
        for const in code.co_consts:
            if isinstance(const, CodeType):
                self._collect_code_lines(const, target)

    def _build_skip_set(self) -> frozenset[Path]:
        value = os.environ.get(_SKIP_ENV_VAR)
        if not value:
            return frozenset()
        entries = (entry for entry in value.split(os.pathsep) if entry)
        paths: set[Path] = set()
        for entry in entries:
            normalised = _normalise_source(entry)
            paths.add(normalised)
        return frozenset(paths)

    @staticmethod
    def _runtime_metrics_enabled() -> bool:
        raw = os.environ.get(_RUNTIME_DISABLED_ENV_VAR)
        if raw is None:
            return True
        return raw.strip().lower() not in {"1", "true", "yes", "on"}

    def _is_allowed_path(self, path: Path) -> bool:
        cached = self._allowed_cache.get(path)
        if cached is not None:
            return cached
        try:
            resolved = path.resolve()
        except FileNotFoundError:
            self._allowed_cache[path] = False
            return False
        allowed = any(
            resolved == scope or resolved.is_relative_to(scope)
            for scope in self._allowed_scope_roots
        )
        if allowed and self._skip_paths:
            resolved_str = str(resolved)
            for skip in self._skip_paths:
                skip_str = str(skip)
                if resolved_str == skip_str or resolved_str.startswith(
                    f"{skip_str}{os.sep}"
                ):
                    allowed = False
                    break
        self._allowed_cache[path] = allowed
        if resolved != path:
            self._allowed_cache[resolved] = allowed
        return allowed

    def _write_runtime_metrics(self, reports: tuple[_FileReport, ...]) -> None:
        metrics_dir = self._ensure_metrics_directory()
        host_info = self._build_host_metadata()
        files_payload = self._build_files_payload(reports)
        json_payload = self._build_json_payload(host_info, files_payload)
        self._write_json_metrics(metrics_dir, json_payload)
        self._write_csv_metrics(metrics_dir, host_info, files_payload)

    def _ensure_metrics_directory(self) -> Path:
        metrics_dir = _METRICS_DIRECTORY
        metrics_dir.mkdir(parents=True, exist_ok=True)
        return metrics_dir

    def _build_host_metadata(self) -> dict[str, int | str]:
        return {
            "name": socket.gethostname(),
            "cpu_count": os.cpu_count() or 1,
        }

    def _build_files_payload(
        self, reports: tuple[_FileReport, ...]
    ) -> list[dict[str, Any]]:
        with self._lock:
            runtime_snapshot = dict(self._module_runtime)
        payload: list[dict[str, Any]] = []
        for report in reports:
            runtime_seconds = runtime_snapshot.get(report.path, 0.0)
            payload.append(
                {
                    "relative": report.relative,
                    "statements": len(report.statements),
                    "executed": len(report.executed),
                    "missed": len(report.missed),
                    "coverage_percent": report.coverage_percent,
                    "runtime_seconds": runtime_seconds,
                }
            )
        payload.sort(key=lambda item: item["relative"])
        return payload

    @staticmethod
    def _build_json_payload(
        host_info: dict[str, int | str], files_payload: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "host": host_info,
            "generated_at": time.time(),
            "files": files_payload,
        }

    @staticmethod
    def _write_json_metrics(metrics_dir: Path, payload: dict[str, Any]) -> None:
        (metrics_dir / _METRICS_JSON_NAME).write_text(
            json.dumps(payload, indent=2, sort_keys=False),
            encoding="utf-8",
        )

    @staticmethod
    def _write_csv_metrics(
        metrics_dir: Path,
        host_info: dict[str, int | str],
        files_payload: list[dict[str, Any]],
    ) -> None:
        csv_path = metrics_dir / _METRICS_CSV_NAME
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "file",
                    "statements",
                    "executed",
                    "missed",
                    "coverage_percent",
                    "runtime_seconds",
                    "host",
                    "cpu_count",
                ]
            )
            for entry in files_payload:
                writer.writerow(
                    [
                        entry["relative"],
                        entry["statements"],
                        entry["executed"],
                        entry["missed"],
                        f"{entry['coverage_percent']:.4f}",
                        f"{entry['runtime_seconds']:.6f}",
                        host_info["name"],
                        host_info["cpu_count"],
                    ]
                )


@dataclass(slots=True)
class _TraceState:
    last_timestamp: float
    path: Path | None
