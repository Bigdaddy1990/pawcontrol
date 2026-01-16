"""Tooling tests that ensure packaging metadata stays synchronized."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_runtime_dependencies_match_requirements_txt() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    pyproject_data = tomllib.loads((repo_root / "pyproject.toml").read_text())
    pyproject_deps = pyproject_data["project"]["dependencies"]

    requirements = [
        line.strip()
        for line in (repo_root / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert sorted(pyproject_deps) == sorted(requirements)
