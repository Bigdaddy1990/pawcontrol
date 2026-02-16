"""Tooling tests that ensure packaging metadata stays synchronized."""

from pathlib import Path
import tomllib


def test_runtime_dependencies_match_requirements_txt() -> None:
  repo_root = next(  # noqa: E111
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").exists()
  )
  pyproject_data = tomllib.loads((repo_root / "pyproject.toml").read_text())  # noqa: E111
  project_data = pyproject_data.get("project", {})  # noqa: E111
  if "dependencies" in project_data:  # noqa: E111
    pyproject_deps = project_data["dependencies"]
  else:  # noqa: E111
    dynamic = pyproject_data.get("tool", {}).get("setuptools", {}).get("dynamic", {})
    deps_spec = dynamic.get("dependencies", {})
    dep_files = deps_spec.get("file", [])
    if isinstance(dep_files, str):
      dep_files = [dep_files]  # noqa: E111
    pyproject_deps = [
      line.strip()
      for dep_file in dep_files
      for line in (repo_root / dep_file).read_text().splitlines()
      if line.strip() and not line.strip().startswith("#")
    ]

  requirements = [  # noqa: E111
    line.strip()
    for line in (repo_root / "requirements.txt").read_text().splitlines()
    if line.strip() and not line.strip().startswith("#")
  ]

  assert sorted(pyproject_deps) == sorted(requirements)  # noqa: E111
