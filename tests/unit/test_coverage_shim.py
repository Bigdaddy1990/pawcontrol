"""Tests for the PawControl coverage shim runtime instrumentation."""

from __future__ import annotations

import io
import json
import sys
import types
from pathlib import Path

import coverage
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

if not hasattr(aiohttp_client, "_async_make_resolver"):

    async def _async_make_resolver(*args, **kwargs):  # type: ignore[unused-argument]
        return None

    aiohttp_client._async_make_resolver = _async_make_resolver  # type: ignore[attr-defined]


def test_runtime_metrics_generation(tmp_path) -> None:
    """Ensure the coverage shim emits JSON and CSV runtime metrics."""

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
