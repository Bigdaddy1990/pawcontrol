"""Ensure test imports declare the third-party packages they rely on."""

import argparse
import ast
from collections.abc import Iterable
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPO_ROOT / "tests"
REQUIREMENT_FILES = [
  REPO_ROOT / "requirements_test.txt",
  REPO_ROOT / "requirements.txt",
]
STANDARD_LIB = {name.replace(".", "_") for name in sys.stdlib_module_names}
INTERNAL_PREFIXES = ("tests", "custom_components", "scripts")
INTERNAL_MODULES: set[str] = set()


def _extract_requirement_name(line: str) -> str | None:
  """Return the normalized package name from a requirement line."""  # noqa: E111

  stripped = line.split("#", 1)[0].strip()  # noqa: E111
  if not stripped or stripped.startswith("-"):  # noqa: E111
    return None

  delimiters = frozenset("[] <>!=~();")  # noqa: E111
  for i, char in enumerate(stripped):  # noqa: E111
    if char in delimiters:
      name = stripped[:i].strip()  # noqa: E111
      return name or None  # noqa: E111

  return stripped or None  # noqa: E111


def _parse_requirements() -> set[str]:
  modules: set[str] = set()  # noqa: E111

  for requirement_file in REQUIREMENT_FILES:  # noqa: E111
    content = requirement_file.read_text(encoding="utf-8")
    for raw_line in content.splitlines():
      name = _extract_requirement_name(raw_line)  # noqa: E111
      if not name:  # noqa: E111
        continue
      normalized = name.lower()  # noqa: E111
      modules.add(normalized)  # noqa: E111
      modules.add(normalized.replace("-", "_"))  # noqa: E111

  return modules  # noqa: E111


def _iter_test_files() -> Iterable[Path]:
  return TESTS_ROOT.rglob("*.py")  # noqa: E111


def _collect_imports(path: Path) -> set[str]:
  imports: set[str] = set()  # noqa: E111
  tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))  # noqa: E111

  for node in ast.walk(tree):  # noqa: E111
    if isinstance(node, ast.Import):
      for alias in node.names:  # noqa: E111
        imports.add(alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
      if node.module is None or node.level:  # noqa: E111
        continue
      imports.add(node.module.split(".")[0])  # noqa: E111

  return imports  # noqa: E111


def _is_third_party(module: str) -> bool:
  module_lower = module.lower()  # noqa: E111
  if module_lower in STANDARD_LIB:  # noqa: E111
    return False
  if module_lower in INTERNAL_MODULES:  # noqa: E111
    return False
  return not any(module_lower.startswith(prefix) for prefix in INTERNAL_PREFIXES)  # noqa: E111


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)  # noqa: E111
  parser.add_argument(  # noqa: E111
    "--verbose",
    action="store_true",
    help="print all discovered imports for debugging",
  )
  args = parser.parse_args()  # noqa: E111

  requirements = _parse_requirements()  # noqa: E111
  missing: dict[str, set[str]] = {}  # noqa: E111

  for file in _iter_test_files():  # noqa: E111
    imports = _collect_imports(file)
    if args.verbose:
      print(f"{file}: {sorted(imports)}")  # noqa: E111
    for module in imports:
      if not _is_third_party(module):  # noqa: E111
        continue
      normalized = module.lower().replace("-", "_")  # noqa: E111
      if normalized in requirements:  # noqa: E111
        continue
      missing.setdefault(file.as_posix(), set()).add(module)  # noqa: E111

  if missing:  # noqa: E111
    print("Missing test requirement declarations detected:")
    for file, modules in sorted(missing.items()):
      formatted = ", ".join(sorted(modules))  # noqa: E111
      print(f"  - {file}: {formatted}")  # noqa: E111
    print("Add the packages to requirements_test.txt to fix the violation.")
    return 1

  print("All third-party test imports map to requirements_test.txt entries.")  # noqa: E111
  return 0  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
