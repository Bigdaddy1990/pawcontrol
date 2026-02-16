#!/usr/bin/env python3
"""Autofix common MyPy issues in the PawControl codebase.

This script focuses on deterministic, low-risk fixes:

* Remove redundant ``cast(...)`` wrappers reported by MyPy.
* Remove unused inline ``# type: ignore[...]`` comments.
* Generate ``custom_components/pawcontrol/utils/__init__.pyi`` so MyPy can
  statically resolve dynamically re-exported utility symbols.

Usage:
    python -m scripts.fix_mypy_issues --apply
    python -m scripts.fix_mypy_issues --check
"""

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
MYPY_TARGET: Final = "custom_components/pawcontrol"
UTILS_LEGACY: Final = REPO_ROOT / "custom_components/pawcontrol/utils/_legacy.py"
UTILS_SERIALIZE: Final = REPO_ROOT / "custom_components/pawcontrol/utils/serialize.py"
UTILS_STUB: Final = REPO_ROOT / "custom_components/pawcontrol/utils/__init__.pyi"

MYPY_ERROR_RE: Final = re.compile(
  r"^(?P<path>.+?):(?P<line>\d+):(?:\d+:)? error: (?P<message>.+?)\s+"
  r"\[(?P<code>[^\]]+)\]$"
)
TYPE_IGNORE_RE: Final = re.compile(r"\s+#\s*type:\s*ignore(?:\[[^\]]*\])?")


@dataclass(slots=True)
class MypyError:
  """Represents one parsed MyPy error line."""

  path: Path
  line_no: int
  code: str


def _run_mypy(mypy_target: str) -> list[MypyError]:
  """Run MyPy and parse reportable errors."""
  result = subprocess.run(
    [sys.executable, "-m", "mypy", mypy_target, "--show-error-codes"],
    cwd=REPO_ROOT,
    capture_output=True,
    text=True,
    check=False,
  )
  errors: list[MypyError] = []
  for raw_line in result.stdout.splitlines():
    match = MYPY_ERROR_RE.match(raw_line.strip())
    if not match:
      continue
    raw_path = Path(match.group("path"))
    path = raw_path if raw_path.is_absolute() else (REPO_ROOT / raw_path)
    errors.append(
      MypyError(
        path=path.resolve(),
        line_no=int(match.group("line")),
        code=match.group("code"),
      )
    )
  return errors


def _remove_redundant_cast(line: str) -> tuple[str, bool]:
  """Remove one ``cast(T, expr)`` wrapper from a single line when possible."""
  token = "cast("
  start = line.find(token)
  if start == -1:
    return line, False

  idx = start + len(token)
  depth = 1
  comma_index = -1
  while idx < len(line):
    char = line[idx]
    if char == "(":
      depth += 1
    elif char == ")":
      depth -= 1
      if depth == 0:
        break
    elif char == "," and depth == 1 and comma_index == -1:
      comma_index = idx
    idx += 1

  if depth != 0 or comma_index == -1 or idx >= len(line):
    return line, False

  expr = line[comma_index + 1 : idx].strip()
  if not expr:
    return line, False

  updated = f"{line[:start]}{expr}{line[idx + 1 :]}"
  return updated, updated != line


def _remove_redundant_casts(lines: list[str], line_no: int) -> bool:
  """Apply redundant cast removal to one line index."""
  idx = line_no - 1
  if idx < 0 or idx >= len(lines):
    return False
  updated, changed = _remove_redundant_cast(lines[idx])
  if changed:
    lines[idx] = updated
  return changed


def _remove_unused_ignore(lines: list[str], line_no: int) -> bool:
  """Remove an inline ``# type: ignore[...]`` comment from one line."""
  idx = line_no - 1
  if idx < 0 or idx >= len(lines):
    return False
  line = lines[idx]
  updated = TYPE_IGNORE_RE.sub("", line)
  if updated == line:
    return False
  lines[idx] = updated
  return True


def _apply_source_fixes(errors: list[MypyError], *, apply: bool) -> int:
  """Apply mechanical source fixes and return changed file count."""
  by_path: dict[Path, list[MypyError]] = {}
  for error in errors:
    by_path.setdefault(error.path, []).append(error)

  changed_files = 0
  for path, path_errors in by_path.items():
    if not path.exists() or path.suffix != ".py":
      continue
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False

    for error in sorted(path_errors, key=lambda item: item.line_no, reverse=True):
      if error.code == "redundant-cast":
        changed = _remove_redundant_casts(lines, error.line_no) or changed
      elif error.code == "unused-ignore":
        changed = _remove_unused_ignore(lines, error.line_no) or changed

    if changed:
      changed_files += 1
      if apply:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

  return changed_files


def _extract_public_names(module_path: Path) -> list[str]:
  """Extract exported symbol names from a module AST."""
  tree = ast.parse(module_path.read_text(encoding="utf-8"))

  for node in tree.body:
    if isinstance(node, ast.Assign):
      for target in node.targets:
        if (
          isinstance(target, ast.Name)
          and target.id == "__all__"
          and isinstance(node.value, (ast.List, ast.Tuple))
        ):
          exported: list[str] = []
          for item in node.value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
              exported.append(item.value)
          if exported:
            return sorted(set(exported))

  names: set[str] = set()
  for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
      names.add(node.name)
    elif isinstance(node, ast.Assign):
      for target in node.targets:
        if isinstance(target, ast.Name):
          names.add(target.id)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
      names.add(node.target.id)

  return sorted(name for name in names if not name.startswith("_"))


def _build_utils_stub() -> str:
  """Build content for ``utils/__init__.pyi``."""
  legacy_names = _extract_public_names(UTILS_LEGACY)
  serialize_names = _extract_public_names(UTILS_SERIALIZE)
  all_names = sorted(set(legacy_names) | set(serialize_names))

  lines = [
    '"""Typing stub for dynamic utils re-exports."""',
    "",
    "from ._legacy import *",
    (
      "from .serialize import serialize_dataclass, serialize_datetime, "
      "serialize_entity_attributes, serialize_timedelta"
    ),
    "",
    "__all__: list[str] = [",
  ]
  lines.extend([f'    "{name}",' for name in all_names])
  lines.append("]")
  lines.append("")
  return "\n".join(lines)


def _sync_utils_stub(*, apply: bool) -> bool:
  """Sync utils stub file, returning whether update is needed/performed."""
  content = _build_utils_stub()
  if UTILS_STUB.exists() and UTILS_STUB.read_text(encoding="utf-8") == content:
    return False
  if apply:
    UTILS_STUB.write_text(content, encoding="utf-8")
  return True


def _parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__)
  mode = parser.add_mutually_exclusive_group()
  mode.add_argument("--apply", action="store_true", help="Write fixes to disk")
  mode.add_argument("--check", action="store_true", help="Report pending fixes")
  parser.add_argument(
    "--target", default=MYPY_TARGET, help="Path/package passed to MyPy"
  )
  return parser.parse_args()


def main() -> int:
  """CLI entry point."""
  args = _parse_args()
  apply = args.apply or not args.check

  errors = _run_mypy(args.target)
  source_updates = _apply_source_fixes(errors, apply=apply)
  stub_updated = _sync_utils_stub(apply=apply)

  action = "Applied" if apply else "Detected"
  print(f"{action} source updates in {source_updates} file(s).")
  print(f"{action} utils stub update: {stub_updated}.")
  print(f"Observed MyPy errors: {len(errors)}")

  if args.check:
    return 1 if source_updates or stub_updated else 0
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
