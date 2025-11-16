"""Ensure runtime dependencies stay consistent across metadata files."""

from __future__ import annotations

import tomllib
from pathlib import Path


def _read_requirements(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_pyproject_dependencies_match_requirements_file() -> None:
    project_root = Path(__file__).parents[2]
    pyproject_data = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = pyproject_data["project"]["dependencies"]
    requirements = _read_requirements(project_root / "requirements.txt")
    assert dependencies == requirements
