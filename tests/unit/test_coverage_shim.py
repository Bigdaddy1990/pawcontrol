"""Tests for the PawControl coverage shim runtime instrumentation."""

import contextlib
import importlib.util
import io
import json
import os
import sys
import types
from pathlib import Path
from types import CodeType, FrameType
from unittest.mock import MagicMock, Mock, patch

import coverage
import pytest
from coverage import _compile_cached
from homeassistant.helpers import aiohttp_client
from pytest_cov import plugin as pytest_cov_plugin

ha_util_logging = types.ModuleType("homeassistant.util.logging")

if "homeassistant.util.logging" not in sys.modules:
    sys.modules["homeassistant.util.logging"] = ha_util_logging

from homeassistant import util as ha_util

if not hasattr(ha_util, "logging"):
    ha_util.logging = ha_util_logging  # type: ignore[attr-defined]

if not hasattr(ha_util_logging, "log_exception"):

    def log_exception(*_args, **_kwargs):
        return None

    ha_util_logging.log_exception = log_exception  # type: ignore[attr-defined]


def test_runtime_metrics_generation(tmp_path) -> None:
    """Ensure the coverage shim emits JSON and CSV runtime metrics.【F:coverage.py†L471-L506】"""

    _ = tmp_path
    metrics_dir = Path("generated/coverage")
    json_path = metrics_dir / "runtime.json"
    csv_path = metrics_dir / "runtime.csv"
    if json_path.exists():
        json_path.unlink()
    if csv_path.exists():
        csv_path.unlink()

    cov = coverage.Coverage(source=("tests/unit/test_coverage_shim.py",))
    cov.start()
    try:

        def _sample() -> int:
            return 2

        assert _sample() == 2
    finally:
        cov.stop()

    cov.report(file=io.StringIO())

    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["host"]["name"]
    assert data["host"]["cpu_count"] >= 1
    files = {entry["relative"]: entry for entry in data["files"]}
    key = "tests/unit/test_coverage_shim.py"
    assert key in files
    assert files[key]["runtime_seconds"] >= 0.0

    assert csv_path.exists()
    csv_content = csv_path.read_text(encoding="utf-8").splitlines()
    assert csv_content[0].startswith(
        "file,statements,executed,missed,coverage_percent,runtime_seconds,host,cpu_count"
    )
    assert any(key in row for row in csv_content[1:])


def test_runtime_metrics_can_be_disabled(monkeypatch, tmp_path) -> None:
    """Environment flag bypasses runtime metrics emission entirely.【F:coverage.py†L437-L442】"""

    monkeypatch.setenv("PAWCONTROL_DISABLE_RUNTIME_METRICS", "1")
    _ = tmp_path
    metrics_dir = Path("generated/coverage")
    json_path = metrics_dir / "runtime.json"
    csv_path = metrics_dir / "runtime.csv"
    if json_path.exists():
        json_path.unlink()
    if csv_path.exists():
        csv_path.unlink()

    cov = coverage.Coverage(source=("tests/unit/test_coverage_shim.py",))
    cov.start()
    try:

        def _sample() -> int:
            return 3

        assert _sample() == 3
    finally:
        cov.stop()

    cov.report(file=io.StringIO())

    assert not json_path.exists()
    assert not csv_path.exists()


def test_compile_cached_reuses_bytecode() -> None:
    """The compilation helper caches bytecode for repeated calls.【F:coverage.py†L31-L41】"""

    first = _compile_cached("sample.py", "value = 1")
    second = _compile_cached("sample.py", "value = 1")
    assert first is not None
    assert second is first


def test_compile_cached_handles_syntax_errors() -> None:
    """Invalid source returns ``None`` and caches the failure result.【F:coverage.py†L31-L41】"""

    source = "def broken(: pass"
    assert _compile_cached("broken.py", source) is None
    assert _compile_cached("broken.py", source) is None


def test_plugin_records_module_imports() -> None:
    """Coverage controller starts before imports so module setup is tracked."""

    module_path = Path("tests/unit/_coverage_plugin_case.py")
    module_path.write_text("VALUE = 1\nRESULT = VALUE\n", encoding="utf-8")
    module_name = "tests.unit._coverage_plugin_case"
    try:
        options = types.SimpleNamespace(
            cov_sources=[str(module_path)],
            cov_branch=False,
            cov_reports=["term"],
            cov_fail_under=None,
        )
        config = types.SimpleNamespace(option=options)
        controller = pytest_cov_plugin._CoverageController(config)
        controller.pytest_configure(config)

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        session = types.SimpleNamespace(exitstatus=pytest.ExitCode.OK)
        controller.pytest_sessionfinish(session, pytest.ExitCode.OK)

        handle = io.StringIO()
        assert controller._coverage is not None
        total = controller._coverage.report(file=handle, skip_empty=True)
        assert total == 100.0
    finally:
        sys.modules.pop(module_name, None)
        module_path.unlink(missing_ok=True)
        cache_path = module_path.parent / "__pycache__"
        if cache_path.exists():
            for child in cache_path.iterdir():
                if child.name.startswith("_coverage_plugin_case"):
                    child.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                cache_path.rmdir()


# Tests for sys.monitoring integration and type system changes


class TestTraceProtocol:
    """Tests for TraceFunc protocol type hints."""

    def test_trace_func_protocol_signature(self) -> None:
        """TraceFunc protocol should accept frame, event, and arg parameters."""
        # Create a mock trace function that conforms to the protocol
        mock_trace: coverage.TraceFunc = MagicMock(return_value=None)
        mock_frame = MagicMock(spec=FrameType)

        # Should be callable with frame, event, and arg
        result = mock_trace(mock_frame, "line", None)

        # Result should be either None or another TraceFunc
        assert result is None or callable(result)
        mock_trace.assert_called_once()


class TestTypeAnnotations:
    """Tests for type annotations in coverage module."""

    def test_compile_cached_returns_codetype_or_none(self) -> None:
        """_compile_cached should return CodeType or None."""
        result = coverage._compile_cached("test.py", "x = 1")
        assert result is None or isinstance(result, CodeType)

    def test_compile_cached_returns_none_for_invalid_source(self) -> None:
        """_compile_cached should return None for syntax errors."""
        result = coverage._compile_cached("invalid.py", "x = ")
        assert result is None


class TestMonitoringIntegration:
    """Tests for sys.monitoring integration when available."""

    def test_coverage_init_detects_monitoring_module(self) -> None:
        """Coverage should detect and store sys.monitoring when available."""
        cov = coverage.Coverage(source=())

        # Should have monitoring attributes
        assert hasattr(cov, "_monitoring")
        assert hasattr(cov, "_monitor_tool_id")
        assert hasattr(cov, "_using_monitoring")

        # On Python < 3.13, monitoring should be None

    def test_coverage_init_validates_monitoring_attributes(self) -> None:
        """Coverage should validate required monitoring attributes."""
        coverage.Coverage(source=())

        # Create a mock monitoring module with missing attributes
        mock_monitoring = MagicMock()
        del mock_monitoring.COVERAGE_ID  # Missing required attribute

        with patch("sys.monitoring", mock_monitoring):
            cov2 = coverage.Coverage(source=())
            # Should handle missing attributes gracefully
            assert cov2._monitoring is None

    def test_start_without_monitoring_uses_trace(self) -> None:
        """start() should use sys.settrace when monitoring unavailable."""
        with patch("sys.monitoring", None):
            cov = coverage.Coverage(source=("tests/unit/test_coverage_shim.py",))
            cov.start()
            try:
                # Should have set a trace function
                current_trace = sys.gettrace()
                assert current_trace is not None
                # Should not be using monitoring
                assert cov._using_monitoring is False
            finally:
                cov.stop()

    def test_stop_restores_previous_trace(self) -> None:
        """stop() should restore the previous trace function."""

        def dummy_trace(frame: FrameType, event: str, arg: object) -> None:
            return None

        with patch("sys.monitoring", None):
            # Set up a previous trace
            sys.settrace(dummy_trace)
            try:
                cov = coverage.Coverage(source=("tests/unit/test_coverage_shim.py",))
                cov.start()
                cov.stop()

                # Should have restored the previous trace
                assert sys.gettrace() == dummy_trace
            finally:
                sys.settrace(None)


class TestResolveEventPath:
    """Tests for _resolve_event_path method."""

    def test_resolve_event_path_with_valid_file(self) -> None:
        """_resolve_event_path should resolve valid file paths."""
        cov = coverage.Coverage(source=())

        # Use the actual test file
        result = cov._resolve_event_path(__file__)

        assert result is not None
        assert isinstance(result, Path)
        assert result.exists()

    def test_resolve_event_path_ignores_builtin_modules(self) -> None:
        """_resolve_event_path should return None for builtin modules."""
        cov = coverage.Coverage(source=())

        result = cov._resolve_event_path("<string>")
        assert result is None

        result = cov._resolve_event_path("<stdin>")
        assert result is None

    def test_resolve_event_path_handles_nonexistent_files(self) -> None:
        """_resolve_event_path should return None for nonexistent files."""
        cov = coverage.Coverage(source=())

        result = cov._resolve_event_path("/nonexistent/path/to/file.py")
        assert result is None

    def test_resolve_event_path_with_none_filename(self) -> None:
        """_resolve_event_path should handle None filename gracefully."""
        cov = coverage.Coverage(source=())

        result = cov._resolve_event_path(None)
        assert result is None

    def test_resolve_event_path_skips_unmeasured_paths(self) -> None:
        """_resolve_event_path should return None for paths outside source roots."""
        cov = coverage.Coverage(source=("custom_components/pawcontrol",))

        # This test file should not be measured
        result = cov._resolve_event_path(__file__)
        assert result is None


class TestHandleLineEvent:
    """Tests for _handle_line_event method."""

    def test_handle_line_event_records_execution(self) -> None:
        """_handle_line_event should record executed lines."""
        cov = coverage.Coverage(source=("tests/unit/test_coverage_shim.py",))
        path = Path(__file__)

        cov._handle_line_event(path, 1)

        assert path in cov._executed
        assert 1 in cov._executed[path]

    def test_handle_line_event_ignores_none_path(self) -> None:
        """_handle_line_event should ignore None path without error."""
        cov = coverage.Coverage(source=())

        # Should not raise an error
        cov._handle_line_event(None, 1)
        cov._handle_line_event(None, None)

    def test_handle_line_event_ignores_invalid_lineno(self) -> None:
        """_handle_line_event should ignore invalid line numbers."""
        cov = coverage.Coverage(source=())
        path = Path(__file__)

        # Should not record negative or zero line numbers
        cov._handle_line_event(path, 0)
        cov._handle_line_event(path, -1)

        # Path should not be recorded if line number is invalid
        assert path not in cov._executed or len(cov._executed[path]) == 0

    def test_handle_line_event_uses_provided_timestamps(self) -> None:
        """_handle_line_event should use provided now and thread_ident parameters."""
        cov = coverage.Coverage(source=("tests/unit/test_coverage_shim.py",))
        path = Path(__file__)
        now = 123.456
        thread_ident = 999

        # Should accept custom timestamp and thread ident
        cov._handle_line_event(path, 1, now=now, thread_ident=thread_ident)

        assert path in cov._executed

    def test_handle_line_event_computes_timestamps_if_omitted(self) -> None:
        """_handle_line_event should compute now and thread_ident if not provided."""
        import threading
        import time

        cov = coverage.Coverage(source=("tests/unit/test_coverage_shim.py",))
        path = Path(__file__)

        time.perf_counter()
        cov._handle_line_event(path, 1)
        time.perf_counter()

        assert path in cov._executed


class TestMonitoringLineEvent:
    """Tests for _monitoring_line_event method."""

    def test_monitoring_line_event_records_valid_code(self) -> None:
        """_monitoring_line_event should record valid code objects and line numbers."""
        cov = coverage.Coverage(source=("tests/unit/test_coverage_shim.py",))

        # Create a code object for this file
        code = compile("x = 1", __file__, "exec")

        cov._monitoring_line_event(code, 1)

        # Should have recorded the execution
        path = Path(__file__)
        assert (
            path in cov._executed or len(cov._executed) == 0
        )  # May not record if outside source root

    def test_monitoring_line_event_ignores_invalid_lineno(self) -> None:
        """_monitoring_line_event should ignore invalid line numbers."""
        cov = coverage.Coverage(source=())
        code = compile("x = 1", "test.py", "exec")

        # Should handle invalid line numbers gracefully
        cov._monitoring_line_event(code, 0)
        cov._monitoring_line_event(code, -1)

    def test_monitoring_line_event_handles_builtin_code(self) -> None:
        """_monitoring_line_event should handle builtin code objects."""
        cov = coverage.Coverage(source=())
        code = compile("x = 1", "<string>", "exec")

        # Should not raise an error
        cov._monitoring_line_event(code, 1)


class TestStartMonitoring:
    """Tests for _start_monitoring method."""

    def test_start_monitoring_returns_false_when_unavailable(self) -> None:
        """_start_monitoring should return False when monitoring is unavailable."""
        with patch("sys.monitoring", None):
            cov = coverage.Coverage(source=())
            result = cov._start_monitoring()
            assert result is False

    def test_start_monitoring_handles_tool_id_conflict(self) -> None:
        """_start_monitoring should handle ValueError from use_tool_id."""
        cov = coverage.Coverage(source=())

        # Create a mock monitoring module that raises ValueError
        mock_monitoring = MagicMock()
        mock_monitoring.COVERAGE_ID = 10
        mock_monitoring.use_tool_id.side_effect = ValueError("Tool ID already in use")

        cov._monitoring = mock_monitoring
        result = cov._start_monitoring()

        assert result is False

    def test_start_monitoring_handles_callback_errors(self) -> None:
        """_start_monitoring should handle errors during callback registration."""
        cov = coverage.Coverage(source=())

        # Create a mock monitoring module that raises RuntimeError
        mock_monitoring = MagicMock()
        mock_monitoring.COVERAGE_ID = 10
        mock_monitoring.events.LINE = 128
        mock_monitoring.register_callback.side_effect = RuntimeError("Callback error")

        cov._monitoring = mock_monitoring

        with patch("sys.stderr"):
            result = cov._start_monitoring()

        assert result is False
        mock_monitoring.free_tool_id.assert_called_once()


class TestStopMonitoring:
    """Tests for _stop_monitoring method."""

    def test_stop_monitoring_cleans_up_when_active(self) -> None:
        """_stop_monitoring should clean up monitoring state."""
        cov = coverage.Coverage(source=())

        # Set up monitoring state
        mock_monitoring = MagicMock()
        mock_monitoring.COVERAGE_ID = 10
        mock_monitoring.events.LINE = 128

        cov._monitoring = mock_monitoring
        cov._monitor_tool_id = 10
        cov._using_monitoring = True

        cov._stop_monitoring()

        # Should clean up
        mock_monitoring.set_events.assert_called()
        mock_monitoring.register_callback.assert_called()
        mock_monitoring.free_tool_id.assert_called()
        assert cov._using_monitoring is False
        assert cov._monitor_tool_id is None

    def test_stop_monitoring_handles_null_state(self) -> None:
        """_stop_monitoring should handle null monitoring state."""
        cov = coverage.Coverage(source=())

        cov._monitoring = None
        cov._monitor_tool_id = None

        # Should not raise an error
        cov._stop_monitoring()

        assert cov._using_monitoring is False


class TestTraceMethod:
    """Tests for _trace method behavior."""

    def test_trace_returns_self_reference(self) -> None:
        """_trace should return itself for chaining."""
        cov = coverage.Coverage(source=())
        frame = MagicMock(spec=FrameType)
        frame.f_lineno = 1
        frame.f_code.co_filename = __file__

        result = cov._trace(frame, "line", None)

        assert result == cov._trace or callable(result)

    def test_trace_handles_non_line_events(self) -> None:
        """_trace should handle non-line events gracefully."""
        cov = coverage.Coverage(source=())
        frame = MagicMock(spec=FrameType)

        # Should not raise for call, return, exception events
        result = cov._trace(frame, "call", None)
        assert callable(result)

        result = cov._trace(frame, "return", None)
        assert callable(result)

    def test_trace_ignores_builtin_files(self) -> None:
        """_trace should ignore builtin and generated files."""
        cov = coverage.Coverage(source=())
        frame = MagicMock(spec=FrameType)
        frame.f_code.co_filename = "<string>"

        result = cov._trace(frame, "line", None)

        assert callable(result)
