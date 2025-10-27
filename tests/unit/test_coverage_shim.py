"""Tests for the PawControl coverage shim runtime instrumentation."""

from __future__ import annotations

import io
import json
import os
import sys
import types
from pathlib import Path

import coverage
from coverage import _compile_cached
from homeassistant.helpers import aiohttp_client

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
