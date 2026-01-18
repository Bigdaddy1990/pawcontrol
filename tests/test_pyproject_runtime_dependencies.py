"""Tooling tests that ensure packaging metadata stays synchronized."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_runtime_dependencies_match_requirements_txt() -> None:
  repo_root = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").exists()
  )
  pyproject_data = tomllib.loads((repo_root / "pyproject.toml").read_text())
  project_data = pyproject_data.get("project", {})
  if "dependencies" in project_data:
    pyproject_deps = project_data["dependencies"]
  else:
    dynamic = pyproject_data.get("tool", {}).get("setuptools", {}).get("dynamic", {})
    deps_spec = dynamic.get("dependencies", {})
    dep_files = deps_spec.get("file", [])
    if isinstance(dep_files, str):
      dep_files = [dep_files]
    pyproject_deps = [
      line.strip()
      for dep_file in dep_files
      for line in (repo_root / dep_file).read_text().splitlines()
      if line.strip() and not line.strip().startswith("#")
    ]

  requirements = [
    line.strip()
    for line in (repo_root / "requirements.txt").read_text().splitlines()
    if line.strip() and not line.strip().startswith("#")
  ]

  assert sorted(pyproject_deps) == sorted(requirements)
