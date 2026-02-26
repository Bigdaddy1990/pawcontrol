"""Regression tests for local pytest plugin shims.

These tests guarantee that the lightweight plugin shims keep importing without
third-party dependencies, preventing regressions when upstream pytest plugins
change behaviour.
"""

import asyncio
import builtins
from collections.abc import Generator
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import coverage


class _DummyParser:
    """Minimal parser capturing ini options registered by plugins."""

    def __init__(self) -> None:
        self.inis: list[tuple[str, str, str | None]] = []
        self.options: list[tuple[str, dict[str, object]]] = []

    def addoption(self, name: str, **kwargs: object) -> None:
        self.options.append((name, dict(kwargs)))

    def addini(self, name: str, help: str, *, default: str | None = None) -> None:
        self.inis.append((name, help, default))


class _DummyConfig:
    """Minimal config capturing markers registered by plugins."""

    def __init__(self) -> None:
        self.markers: list[tuple[str, str]] = []

    def addinivalue_line(self, name: str, line: str) -> None:
        self.markers.append((name, line))


class _DummySession:
    def __init__(self, option: SimpleNamespace) -> None:
        self.config = SimpleNamespace(option=option)
        self.exitstatus = 0


def _reload(module_name: str):
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    sys.modules.pop(module_name, None)
    if "." in module_name:
        parent = module_name.split(".", 1)[0]
        sys.modules.pop(parent, None)
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


def test_pytest_cov_plugin_registers_options() -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    parser = _DummyParser()
    pytest_cov_plugin.pytest_addoption(parser)

    option_names = {name for name, _kwargs in parser.options}
    assert {
        "--cov",
        "--cov-report",
        "--cov-branch",
        "--cov-fail-under",
        "--no-cov-on-fail",
    } <= option_names


def test_pytest_cov_imports_without_coverage_dependency(tmp_path: Path) -> None:
    real_import = builtins.__import__

    def _blocked_import(name: str, *args: object, **kwargs: object):
        if name == "coverage" or name.startswith("coverage."):
            raise ModuleNotFoundError("No module named 'coverage'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_blocked_import):
        pytest_cov_plugin = _reload("pytest_cov.plugin")

    assert pytest_cov_plugin._COVERAGE_AVAILABLE is False

    xml_path = tmp_path / "cov.xml"
    option = SimpleNamespace(cov=[], cov_branch=False, cov_report=[f"xml:{xml_path}"])
    session = _DummySession(option)

    pytest_cov_plugin.pytest_sessionstart(session)
    pytest_cov_plugin.pytest_sessionfinish(session, 0)

    assert xml_path.exists()


def test_pytest_cov_source_aliases_include_dotted_packages() -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    expanded = pytest_cov_plugin._expand_source_aliases((
        "custom_components/pawcontrol",
        "tests/unit",
        "/tmp/absolute",
    ))

    assert "custom_components/pawcontrol" in expanded
    assert "custom_components.pawcontrol" in expanded
    assert "tests.unit" in expanded
    assert "/tmp/absolute" in expanded


def test_pytest_cov_include_patterns_cover_path_and_dotted_sources() -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    include = pytest_cov_plugin._build_include_patterns((
        "custom_components/pawcontrol",
        "custom_components.pawcontrol",
    ))

    assert include is not None
    assert "*custom_components/pawcontrol/*" in include


def test_pytest_cov_include_patterns_keep_python_file_targets() -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    include = pytest_cov_plugin._build_include_patterns((
        "custom_components/pawcontrol/validation.py",
    ))

    assert include is not None
    assert "custom_components/pawcontrol/validation.py" in include


def test_pytest_cov_split_report_target_preserves_terminal_modifier() -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    report_type, report_target = pytest_cov_plugin._split_report_target(
        "term-missing:skip-covered"
    )

    assert report_type == "term-missing:skip-covered"
    assert report_target is None


def test_pytest_cov_split_report_target_keeps_file_target() -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    report_type, report_target = pytest_cov_plugin._split_report_target("xml:cov.xml")

    assert report_type == "xml"
    assert report_target == "cov.xml"


def test_pytest_cov_session_hooks_generate_xml_and_cleanup(tmp_path: Path) -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    measured_file = tmp_path / "sample.py"
    measured_file.write_text("VALUE = 1\n", encoding="utf-8")

    option = SimpleNamespace(
        cov=[str(measured_file)],
        cov_branch=False,
        cov_report=[f"xml:{tmp_path / 'cov.xml'}"],
        cov_fail_under=0.0,
        no_cov_on_fail=False,
    )
    session = _DummySession(option)

    cov = Mock(spec=coverage.Coverage)
    cov.xml_report.side_effect = lambda outfile, include=None: Path(outfile).write_text(
        "<coverage/>", encoding="utf-8"
    )
    with patch.object(pytest_cov_plugin.coverage, "Coverage", return_value=cov):
        pytest_cov_plugin.pytest_sessionstart(session)
        pytest_cov_plugin.pytest_sessionfinish(session, 0)

    xml_path = tmp_path / "cov.xml"
    assert xml_path.exists()

    pytest_cov_plugin.pytest_unconfigure(session.config)
    assert not hasattr(session.config, "_pawcontrol_cov")


def test_pytest_cov_controller_synthesizes_lines_for_explicit_files(
    tmp_path: Path,
) -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    measured_file = tmp_path / "standalone.py"
    measured_file.write_text("X = 1\n# comment\nY = 2\n", encoding="utf-8")
    option = SimpleNamespace(cov_sources=[str(measured_file)], cov_branch=False)
    config = SimpleNamespace(option=option)

    fake_data = Mock()
    fake_data.measured_files.return_value = []
    fake_cov = Mock(spec=coverage.Coverage)
    fake_cov.get_data.return_value = fake_data

    with patch.object(pytest_cov_plugin.coverage, "Coverage", return_value=fake_cov):
        controller = pytest_cov_plugin._CoverageController(config)
        controller.pytest_configure(config)
        controller.pytest_sessionfinish(object(), 0)

    assert fake_data.add_lines.called
    added_lines = fake_data.add_lines.call_args.args[0]
    assert str(measured_file.resolve()) in added_lines
    assert added_lines[str(measured_file.resolve())] == {1, 3}


def test_pytest_cov_fail_under_sets_session_failure() -> None:
    pytest_cov_plugin = _reload("pytest_cov.plugin")

    option = SimpleNamespace(
        cov=[],
        cov_branch=False,
        cov_report=["term"],
        cov_fail_under=100.0,
        no_cov_on_fail=False,
    )
    session = _DummySession(option)
    cov = Mock(spec=coverage.Coverage)
    cov.report.return_value = 0.0
    session.config._pawcontrol_cov = cov
    session.config._pawcontrol_cov_include = None

    pytest_cov_plugin.pytest_sessionfinish(session, 0)

    assert session.exitstatus == 1


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
