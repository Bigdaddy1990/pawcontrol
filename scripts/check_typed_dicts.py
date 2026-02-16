"""TypedDict guard for PawControl.

The Home Assistant core project has a variety of checks around TypedDicts.
This repo uses a lightweight audit to catch the most common refactor mistakes:

- A class inherits from TypedDict but has no annotations
- A TypedDict field is missing a type annotation

The goal is not to be overly strict, but to fail fast on broken typing.

This script is executed in CI via:

    python -m scripts.check_typed_dicts

Exit codes:
- 0: OK
- 1: Errors found
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "custom_components" / "pawcontrol"


def _is_typeddict_base(base: ast.expr) -> bool:
  """Return True if the base class expression looks like TypedDict."""  # noqa: E111
  if isinstance(base, ast.Name):  # noqa: E111
    return base.id == "TypedDict"
  if isinstance(base, ast.Attribute):  # noqa: E111
    return base.attr == "TypedDict"
  if isinstance(base, ast.Subscript):  # noqa: E111
    return _is_typeddict_base(base.value)
  return False  # noqa: E111


def _iter_py_files(path: Path) -> list[Path]:
  return [p for p in path.rglob("*.py") if p.is_file() and "__pycache__" not in p.parts]  # noqa: E111


def _audit_file(path: Path) -> list[str]:
  errors: list[str] = []  # noqa: E111

  try:  # noqa: E111
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
  except SyntaxError as err:  # noqa: E111
    return [f"{path}: SyntaxError: {err}"]

  for node in ast.walk(tree):  # noqa: E111
    if not isinstance(node, ast.ClassDef):
      continue  # noqa: E111

    if not any(_is_typeddict_base(b) for b in node.bases):
      continue  # noqa: E111

    # TypedDict must contain at least one AnnAssign.
    ann_assigns = [n for n in node.body if isinstance(n, ast.AnnAssign)]
    if not ann_assigns:
      errors.append(  # noqa: E111
        f"{path}:{node.lineno} TypedDict '{node.name}' has no annotated fields"
      )
      continue  # noqa: E111

    for ann in ann_assigns:
      # AnnAssign without an annotation should not happen, but guard anyway.  # noqa: E114
      if ann.annotation is None:  # noqa: E111
        errors.append(
          f"{path}:{ann.lineno} TypedDict '{node.name}' field missing annotation"
        )

  return errors  # noqa: E111


def main() -> int:
  if not TARGET.exists():  # noqa: E111
    print(f"TypedDict audit: target path not found: {TARGET}")
    return 1

  all_errors: list[str] = []  # noqa: E111

  for py_file in _iter_py_files(TARGET):  # noqa: E111
    # Skip generated/vendor files if ever added.
    if py_file.name.startswith("_") and py_file.name not in {"__init__.py"}:
      continue  # noqa: E111

    all_errors.extend(_audit_file(py_file))

  if all_errors:  # noqa: E111
    print("\n".join(all_errors))
    print(f"\nTypedDict audit failed: {len(all_errors)} error(s) found")
    return 1

  print("TypedDict audit passed")  # noqa: E111
  return 0  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
