"""Regression tests for local pytest plugin shims.

These tests guarantee that the lightweight plugin shims keep importing without
third-party dependencies, preventing regressions when upstream pytest plugins
change behaviour.
"""

import asyncio
from collections.abc import Generator
import importlib
from pathlib import Path
import sys


class _DummyParser:
  """Minimal parser capturing ini options registered by plugins."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.inis: list[tuple[str, str, str | None]] = []
    self.options: list[tuple[str, dict[str, object]]] = []

  def addoption(self, name: str, **kwargs: object) -> None:  # noqa: E111
    self.options.append((name, dict(kwargs)))

  def addini(self, name: str, help: str, *, default: str | None = None) -> None:  # noqa: E111
    self.inis.append((name, help, default))


class _DummyConfig:
  """Minimal config capturing markers registered by plugins."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.markers: list[tuple[str, str]] = []

  def addinivalue_line(self, name: str, line: str) -> None:  # noqa: E111
    self.markers.append((name, line))


def _reload(module_name: str):
  repo_root = Path(__file__).resolve().parents[1]  # noqa: E111
  if str(repo_root) not in sys.path:  # noqa: E111
    sys.path.insert(0, str(repo_root))
  sys.modules.pop(module_name, None)  # noqa: E111
  if "." in module_name:  # noqa: E111
    parent = module_name.split(".", 1)[0]
    sys.modules.pop(parent, None)
  return importlib.import_module(module_name)  # noqa: E111


def test_pytest_asyncio_stub_registers_asyncio_mode_and_loop() -> None:
  pytest_asyncio = _reload("pytest_asyncio")  # noqa: E111

  parser = _DummyParser()  # noqa: E111
  pytest_asyncio.pytest_addoption(parser)  # noqa: E111
  assert (  # noqa: E111
    "asyncio_mode",
    "Select asyncio integration mode",
    "auto",
  ) in parser.inis

  event_loop_func = pytest_asyncio.event_loop._fixture_function  # noqa: E111
  event_loop: Generator[asyncio.AbstractEventLoop] = event_loop_func()  # noqa: E111
  loop = next(event_loop)  # noqa: E111
  assert isinstance(loop, asyncio.AbstractEventLoop)  # noqa: E111

  event_loop.close()  # noqa: E111
  assert loop.is_closed()  # noqa: E111


def test_pytest_cov_plugin_registers_marker() -> None:
  pytest_cov_plugin = _reload("pytest_cov.plugin")  # noqa: E111

  config = _DummyConfig()  # noqa: E111
  pytest_cov_plugin.pytest_configure(config)  # noqa: E111

  assert ("markers", "cov: dummy marker for pytest-cov shim") in config.markers  # noqa: E111


def test_pytest_homeassistant_shim_registers_marker() -> None:
  plugin = _reload("pytest_homeassistant_custom_component")  # noqa: E111

  config = _DummyConfig()  # noqa: E111
  plugin.pytest_configure(config)  # noqa: E111

  assert (  # noqa: E111
    "markers",
    "hacc: compatibility marker for pytest-homeassistant stubs",
  ) in config.markers


def test_asyncio_stub_imports_and_restores_get_event_loop() -> None:
  stub = _reload("tests.plugins.asyncio_stub")  # noqa: E111

  original_get_event_loop = stub._ORIGINAL_GET_EVENT_LOOP  # noqa: E111
  config = type("Config", (), {})()  # noqa: E111

  stub.pytest_configure(config)  # noqa: E111
  loop = getattr(config, "_pawcontrol_asyncio_loop", None)  # noqa: E111
  assert isinstance(loop, asyncio.AbstractEventLoop)  # noqa: E111
  assert asyncio.get_event_loop is stub._patched_get_event_loop  # noqa: E111

  stub.pytest_unconfigure(config)  # noqa: E111
  assert asyncio.get_event_loop is original_get_event_loop  # noqa: E111
  if loop is not None and not loop.is_closed():  # noqa: E111
    loop.close()
