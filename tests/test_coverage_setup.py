"""Regression tests for repository-level coverage configuration."""

from pathlib import Path
import shlex
import tomllib


def _load_pyproject() -> dict[str, object]:
    return tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))


def test_pytest_addopts_enable_local_coverage_plugin() -> None:
    """Pytest defaults should load the repository coverage shim consistently."""
    pyproject = _load_pyproject()
    tool = pyproject["tool"]
    pytest_ini = tool["pytest"]["ini_options"]

    addopts = str(pytest_ini["addopts"])
    args = set(shlex.split(addopts))

    assert "-p" in args
    assert "no:pytest_cov" in args
    assert "pytest_cov.plugin" in args


def test_pytest_addopts_emit_standard_coverage_artifacts() -> None:
    """Pytest defaults should emit terminal, XML, and HTML coverage outputs."""
    pyproject = _load_pyproject()
    tool = pyproject["tool"]
    pytest_ini = tool["pytest"]["ini_options"]

    addopts = str(pytest_ini["addopts"])
    args = set(shlex.split(addopts))

    assert "--cov=custom_components/pawcontrol" in args
    assert "--cov-branch" in args
    assert "--cov-report=term-missing" in args
    assert "--cov-report=xml:coverage.xml" in args
    assert "--cov-report=html:htmlcov" in args


def test_coverage_run_targets_custom_component_package() -> None:
    """Coverage.py source settings should match the integration package root."""
    pyproject = _load_pyproject()
    tool = pyproject["tool"]
    coverage_run = tool["coverage"]["run"]

    assert coverage_run["branch"] is True
    assert coverage_run["source"] == ["custom_components/pawcontrol"]
