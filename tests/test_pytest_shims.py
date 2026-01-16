"""Regression tests for local pytest plugin shims.

These tests guarantee that the lightweight plugin shims keep importing without
third-party dependencies, preventing regressions when upstream pytest plugins
change behaviour.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from collections.abc import Generator


class _DummyParser:
    """Minimal parser capturing ini options registered by plugins."""

    def __init__(self) -> None:
        self.inis: list[tuple[str, str, str | None]] = []

    def addini(self, name: str, help: str, *, default: str | None = None) -> None:
        self.inis.append((name, help, default))


class _DummyConfig:
    """Minimal config capturing markers registered by plugins."""

    def __init__(self) -> None:
        self.markers: list[tuple[str, str]] = []

    def addinivalue_line(self, name: str, line: str) -> None:
        self.markers.append((name, line))


def _reload(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_pytest_asyncio_stub_registers_asyncio_mode_and_loop() -> None:
    pytest_asyncio = _reload("pytest_asyncio")

    parser = _DummyParser()
    pytest_asyncio.pytest_addoption(parser)
    assert (
        "asyncio_mode",
        "Select asyncio integration mode",
        "auto",
    ) in parser.inis

    event_loop_func = pytest_asyncio.event_loop._fixture_function
    event_loop: Generator[asyncio.AbstractEventLoop] = event_loop_func()
    loop = next(event_loop)
    assert isinstance(loop, asyncio.AbstractEventLoop)

    event_loop.close()
    assert loop.is_closed()


def test_pytest_cov_plugin_registers_marker() -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    config = _DummyConfig()
    pytest_cov_plugin.pytest_configure(config)

    assert ("markers", "cov: dummy marker for pytest-cov shim") in config.markers


def test_pytest_homeassistant_shim_registers_marker() -> None:
    plugin = _reload("pytest_homeassistant_custom_component")

    config = _DummyConfig()
    plugin.pytest_configure(config)

    assert (
        "markers",
        "hacc: compatibility marker for pytest-homeassistant stubs",
    ) in config.markers


def test_asyncio_stub_imports_and_restores_get_event_loop() -> None:
    stub = _reload("tests.plugins.asyncio_stub")

    original_get_event_loop = stub._ORIGINAL_GET_EVENT_LOOP
    config = type("Config", (), {})()

    stub.pytest_configure(config)
    loop = getattr(config, "_pawcontrol_asyncio_loop", None)
    assert isinstance(loop, asyncio.AbstractEventLoop)
    assert asyncio.get_event_loop is stub._patched_get_event_loop

    stub.pytest_unconfigure(config)
    assert asyncio.get_event_loop is original_get_event_loop
    if loop is not None and not loop.is_closed():
        loop.close()
