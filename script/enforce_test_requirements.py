"""Verify tests declare third-party imports in ``requirements_test.txt``."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

BASE_PATH = Path.cwd()
TESTS_PATH = BASE_PATH / "tests"
REQUIREMENTS_PATH = BASE_PATH / "requirements_test.txt"


def _iter_python_files(root: Path) -> Iterable[Path]:
    """Yield Python sources beneath ``root``."""

    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        yield path


def _gather_test_imports() -> set[str]:
    """Collect top-level module names imported inside ``tests``."""

    module_names: set[str] = set()

    for source_path in _iter_python_files(TESTS_PATH):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                module_names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                module_names.add(node.module.split(".")[0])

    return module_names


def _canonicalise_requirement(name: str) -> str:
    """Normalise requirement identifiers for comparison."""

    return name.replace("_", "-").lower()


def _load_declared_requirements() -> set[str]:
    """Return the requirement names declared for the test environment."""

    requirements: set[str] = set()

    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        requirement = line.split("#", 1)[0].strip()
        if not requirement:
            continue
        candidate = []
        for character in requirement:
            if character in "[]()<>=!~ ":
                break
            candidate.append(character)
        if not candidate:
            continue
        requirements.add(_canonicalise_requirement("".join(candidate)))

    return requirements


@dataclass(frozen=True)
class DependencyRule:
    """Describe the requirement that satisfies a module import."""

    requirement: str | None
    reason: str


THIRD_PARTY_OVERRIDES: dict[str, DependencyRule] = {
    # The stub exposes ``yaml`` but the distribution ships as ``pyyaml``.
    "yaml": DependencyRule("pyyaml", "The PyYAML distribution provides ``yaml``."),
    # ``homeassistant`` vendors ``aiohttp``; the requirement ensures the resolver stays explicit.
    "aiohttp": DependencyRule("homeassistant", "aiohttp ships with Home Assistant."),
    # ``pytest_homeassistant_custom_component`` has no separate distribution name.
    "pytest_homeassistant_custom_component": DependencyRule(
        "pytest-homeassistant-custom-component",
        "Integration test plugin",
    ),
}


LOCAL_MODULE_PREFIXES = {
    "__future__",
    "blueprint_context",
    "blueprint_helpers",
    "custom_components",
    "script",
    "scripts",
    "sitecustomize",
    "tests",
}


def _is_standard_library(module: str) -> bool:
    """Return ``True`` if ``module`` is provided by the Python standard library."""

    return module in sys.stdlib_module_names


def main() -> int:
    """Entry-point used by CI to confirm test dependencies stay declared."""

    declared_requirements = _load_declared_requirements()
    missing_requirements: list[str] = []

    for module in sorted(_gather_test_imports()):
        if _is_standard_library(module) or module in LOCAL_MODULE_PREFIXES:
            continue

        override = THIRD_PARTY_OVERRIDES.get(module)
        requirement_name = override.requirement if override else module

        if requirement_name is None:
            continue

        if _canonicalise_requirement(requirement_name) in declared_requirements:
            continue

        reason = override.reason if override else "Third-party module imported in tests"
        missing_requirements.append(f"{module} -> {requirement_name} ({reason})")

    if missing_requirements:
        formatted = "\n".join(missing_requirements)
        raise SystemExit(
            "The following third-party imports do not have test requirements:\n"
            f"{formatted}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
