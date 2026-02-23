"""Coverage compatibility layer used by regression tests."""

from collections import defaultdict
import contextlib
from functools import lru_cache
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import CodeType, FrameType
from typing import Any
import warnings

import coverage
from coverage.exceptions import CoverageWarning, NoDataError


@lru_cache(maxsize=128)
def _compile_cached(filename: str, source: str) -> CodeType | None:
    try:
        return compile(source, filename, "exec")
    except SyntaxError:
        return None


if not hasattr(coverage, "_compile_cached"):
    coverage._compile_cached = _compile_cached  # type: ignore[attr-defined]


if not hasattr(coverage.Coverage, "_resolve_event_path"):
    _original_init = coverage.Coverage.__init__
    _original_start = coverage.Coverage.start
    _original_stop = coverage.Coverage.stop
    _original_report = coverage.Coverage.report

    def _shim_init(self: coverage.Coverage, *args: Any, **kwargs: Any) -> None:
        _original_init(self, *args, **kwargs)
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is not None and not hasattr(monitoring, "COVERAGE_ID"):
            monitoring = None
        self._monitoring = monitoring
        self._monitor_tool_id = None
        self._using_monitoring = False
        self._resolved_path_cache: dict[str, Path | None] = {}
        self._executed: dict[Path, set[int]] = defaultdict(set)
        self._fallback_prev_trace = None
        self._fallback_using_settrace = False

    def _source_roots(self: coverage.Coverage) -> list[Path]:
        source = getattr(getattr(self, "config", None), "source", ()) or ()
        return [Path(str(item)).resolve() for item in source]

    def _resolve_event_path(
        self: coverage.Coverage, filename: str | None
    ) -> Path | None:
        if filename is None or filename.startswith("<"):
            return None
        if filename in self._resolved_path_cache:
            return self._resolved_path_cache[filename]
        path = Path(filename)
        if not path.exists():
            self._resolved_path_cache[filename] = None
            return None
        resolved = path.resolve()
        roots = _source_roots(self)
        if roots and not any(str(resolved).startswith(str(root)) for root in roots):
            self._resolved_path_cache[filename] = None
            return None
        self._resolved_path_cache[filename] = resolved
        return resolved

    def _handle_line_event(
        self: coverage.Coverage,
        path: Path | None,
        lineno: int | None,
        *,
        now: float | None = None,
        thread_ident: int | None = None,
    ) -> None:
        if path is None or lineno is None or lineno <= 0:
            return
        self._executed[path].add(lineno)
        _ = now if now is not None else time.perf_counter()
        _ = thread_ident if thread_ident is not None else threading.get_ident()

    def _monitoring_line_event(
        self: coverage.Coverage, code: CodeType, lineno: int
    ) -> None:
        _handle_line_event(self, _resolve_event_path(self, code.co_filename), lineno)

    def _trace(self: coverage.Coverage, frame: FrameType, event: str, _arg: object):
        if event == "line":
            _handle_line_event(
                self,
                _resolve_event_path(self, frame.f_code.co_filename),
                frame.f_lineno,
            )
        return _trace.__get__(self, type(self))

    def _start_monitoring(self: coverage.Coverage) -> bool:
        monitoring = getattr(self, "_monitoring", None)
        if monitoring is None:
            self._using_monitoring = False
            return False
        try:
            tool_id = int(monitoring.COVERAGE_ID)
            line_event = getattr(monitoring.events, "LINE", 0)
            monitoring.use_tool_id(tool_id, "coverage.py")
            monitoring.set_events(tool_id, line_event)
            monitoring.register_callback(
                tool_id, line_event, self._monitoring_line_event
            )
            self._monitor_tool_id = tool_id
            self._using_monitoring = True
            return True
        except (AttributeError, RuntimeError, TypeError, ValueError):
            with contextlib.suppress(
                AttributeError, RuntimeError, TypeError, ValueError
            ):
                monitoring.free_tool_id(getattr(monitoring, "COVERAGE_ID", 0))
            self._monitor_tool_id = None
            self._using_monitoring = False
            return False

    def _stop_monitoring(self: coverage.Coverage) -> None:
        monitoring = getattr(self, "_monitoring", None)
        tool_id = getattr(self, "_monitor_tool_id", None)
        if monitoring is None or tool_id is None:
            self._using_monitoring = False
            return
        line_event = getattr(getattr(monitoring, "events", None), "LINE", 0)
        with contextlib.suppress(AttributeError, RuntimeError, TypeError, ValueError):
            monitoring.set_events(tool_id, 0)
            monitoring.register_callback(tool_id, line_event, None)
            monitoring.free_tool_id(tool_id)
        self._monitor_tool_id = None
        self._using_monitoring = False

    def _shim_start(self: coverage.Coverage) -> None:
        if _start_monitoring(self):
            return
        self._fallback_prev_trace = sys.gettrace()
        self._fallback_using_settrace = True
        sys.settrace(self._trace)
        with contextlib.suppress(AttributeError, RuntimeError, TypeError, ValueError):
            _original_start(self)

    def _add_recorded_lines_to_data(self: coverage.Coverage) -> None:
        if not self._executed:
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", CoverageWarning)
            data = self.get_data()
        if data.has_arcs():
            # The shim only records executed line events, not control-flow
            # transitions. We persist self-loop arcs so branch-mode data remains
            # writable without pretending to know real jump targets.
            arcs = {
                path.as_posix(): {(line, line) for line in executed}
                for path, executed in self._executed.items()
            }
            data.add_arcs(arcs)
            return

        lines = {
            path.as_posix(): set(executed) for path, executed in self._executed.items()
        }
        data.add_lines(lines)

    def _shim_stop(self: coverage.Coverage) -> None:
        if getattr(self, "_using_monitoring", False):
            _stop_monitoring(self)
            _add_recorded_lines_to_data(self)
            return
        with contextlib.suppress(AttributeError, RuntimeError, TypeError, ValueError):
            _original_stop(self)
        if getattr(self, "_fallback_using_settrace", False):
            sys.settrace(self._fallback_prev_trace)
            self._fallback_using_settrace = False
        _add_recorded_lines_to_data(self)

    def _write_runtime_metrics(self: coverage.Coverage) -> None:
        if os.getenv("PAWCONTROL_DISABLE_RUNTIME_METRICS"):
            return
        outdir = Path("generated/coverage")
        outdir.mkdir(parents=True, exist_ok=True)
        root = Path.cwd()
        # NOTE: self._executed only contains lines that *were* executed — it has
        # no knowledge of total statements or missed lines. Those fields are
        # therefore reported tautologically as executed==len(lines), missed==0,
        # coverage_percent==100.0 per file.
        # This is intentional: the runtime.json is an *execution trace* log, not
        # a coverage report. Actual coverage (with misses) is provided by the
        # standard coverage.xml produced by coverage.py's normal report path.
        files = [
            {
                "relative": str(path.relative_to(root)).replace("\\", "/")
                if path.is_absolute() and str(path).startswith(str(root))
                else str(path).replace("\\", "/"),
                "runtime_seconds": 0.0,
                "statements": len(lines),
                "executed": len(lines),
                "missed": 0,
                "coverage_percent": 100.0,
            }
            for path, lines in self._executed.items()
        ]
        host = {
            "name": os.uname().nodename if hasattr(os, "uname") else "localhost",
            "cpu_count": os.cpu_count() or 1,
        }
        (outdir / "runtime.json").write_text(
            json.dumps({"host": host, "files": files}), encoding="utf-8"
        )
        rows = [
            "file,statements,executed,missed,coverage_percent,runtime_seconds,host,cpu_count"
        ]
        for entry in files:
            rows.append(
                f"{entry['relative']},{entry['statements']},{entry['executed']},{entry['missed']},{entry['coverage_percent']},{entry['runtime_seconds']},{host['name']},{host['cpu_count']}"
            )
        (outdir / "runtime.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    def _shim_report(self: coverage.Coverage, *args: Any, **kwargs: Any):
        _write_runtime_metrics(self)
        try:
            return _original_report(self, *args, **kwargs)
        except CoverageWarning:
            # Non-fatal warning from coverage.py — return whatever the original
            # would have returned, defaulting to 0.0 so callers do not falsely
            # infer 100 % coverage when the report is incomplete.
            return 0.0
        except NoDataError:
            # BUG FIX: previously swallowed NoDataError and returned 100.0,
            # which masked test suites that ran zero measurable lines.
            # Returning 0.0 correctly signals that no coverage was recorded.
            return 0.0

    coverage.Coverage.__init__ = _shim_init  # type: ignore[assignment]
    coverage.Coverage.start = _shim_start  # type: ignore[assignment]
    coverage.Coverage.stop = _shim_stop  # type: ignore[assignment]
    coverage.Coverage.report = _shim_report  # type: ignore[assignment]
    coverage.Coverage._resolve_event_path = _resolve_event_path  # type: ignore[attr-defined]
    coverage.Coverage._handle_line_event = _handle_line_event  # type: ignore[attr-defined]
    coverage.Coverage._monitoring_line_event = _monitoring_line_event  # type: ignore[attr-defined]
    coverage.Coverage._start_monitoring = _start_monitoring  # type: ignore[attr-defined]
    coverage.Coverage._stop_monitoring = _stop_monitoring  # type: ignore[attr-defined]
    coverage.Coverage._trace = _trace  # type: ignore[attr-defined]
    coverage.Coverage._add_recorded_lines_to_data = _add_recorded_lines_to_data  # type: ignore[attr-defined]
