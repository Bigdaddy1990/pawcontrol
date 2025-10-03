"""Regression tests for the shared-session AST guard."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from scripts import enforce_shared_session_guard as guard


@pytest.mark.unit
def test_recursive_glob_roots_are_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure glob patterns like services/** add nested helper packages."""

    repo_root = tmp_path / "repo"
    integration_root = repo_root / "custom_components" / "pawcontrol"
    services_root = integration_root / "services"
    nested_helper = services_root / "helpers"
    nested_helper.mkdir(parents=True)
    (nested_helper / "__init__.py").write_text("", encoding="utf-8")

    config_dir = repo_root / "scripts"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "shared_session_guard_roots.toml"
    config_path.write_text(
        "roots = [\n"
        '  "custom_components/pawcontrol",\n'
        '  "custom_components/pawcontrol/services",\n'
        '  "custom_components/pawcontrol/services/**"\n'
        "]\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(guard, "REPO_ROOT", repo_root)
    monkeypatch.setattr(guard, "INTEGRATION_ROOT", integration_root)
    monkeypatch.setattr(guard, "CONFIG_PATH", config_path)

    resolved = guard._resolve_configured_roots()

    assert integration_root in resolved
    assert services_root in resolved
    assert nested_helper in resolved


@pytest.mark.unit
def test_package_roots_discovered_without_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Packages with an __init__ should be scanned even without config overrides."""

    repo_root = tmp_path / "repo"
    integration_root = repo_root / "custom_components" / "pawcontrol"
    nested_helper = integration_root / "services" / "helpers"
    nested_helper.mkdir(parents=True)
    (integration_root / "__init__.py").write_text("", encoding="utf-8")
    (nested_helper / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(guard, "REPO_ROOT", repo_root)
    monkeypatch.setattr(guard, "INTEGRATION_ROOT", integration_root)
    monkeypatch.setattr(
        guard,
        "CONFIG_PATH",
        repo_root / "scripts" / "shared_session_guard_roots.toml",
    )

    resolved = guard._resolve_configured_roots()

    assert integration_root in resolved
    assert nested_helper in resolved


@pytest.mark.unit
def test_alias_import_detection() -> None:
    """Aliased ClientSession imports should still be reported as violations."""

    tree = ast.parse(
        "from aiohttp.client import ClientSession as AioClientSession\n"
        "AioClientSession()\n"
    )

    offenders = guard._detect_client_session_calls(tree)

    assert len(offenders) == 1


@pytest.mark.unit
def test_module_alias_detection() -> None:
    """Aliased aiohttp modules should trigger the guard when instantiating pools."""

    tree = ast.parse(
        "import aiohttp.client as aio_client\naio_client.ClientSession()\n"
    )

    offenders = guard._detect_client_session_calls(tree)

    assert len(offenders) == 1


@pytest.mark.unit
def test_from_import_module_alias_detection() -> None:
    """Module aliases imported via ``from aiohttp import client`` are detected."""

    tree = ast.parse("from aiohttp import client\nclient.ClientSession()\n")

    offenders = guard._detect_client_session_calls(tree)

    assert len(offenders) == 1
