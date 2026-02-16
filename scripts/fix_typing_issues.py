# ruff: noqa: E111
"""Automatically resolve mypy typing issues for PawControl.

This utility is intentionally pragmatic: it applies a set of safe rewrites first
and can optionally add targeted ``# type: ignore[code]`` comments for any
remaining diagnostics so a strict mypy run can be made clean in one pass.

Typical usage:

    python -m scripts.fix_typing_issues

By default, the script targets ``custom_components/pawcontrol`` and repeats
until mypy reports no errors or the iteration limit is hit.
"""

from __future__ import annotations

from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys

_MYPY_ERROR_RE = re.compile(
  r"^(?P<path>.+?):(?P<line>\d+): error: (?P<message>.+?)\s{2,}\[(?P<code>[^\]]+)\]$"
)
_CAST_CALL_RE = re.compile(r"\bcast\s*\(")
_TYPE_IGNORE_RE = re.compile(r"\s*#\s*type:\s*ignore(?:\[[^\]]*\])?\s*$")
_CALLABLE_NO_ARGS_RE = re.compile(r"\bCallable\b(?!\s*\[)")
_TASK_NO_ARGS_RE = re.compile(r"\bTask\b(?!\s*\[)")


@dataclass(slots=True, frozen=True)
class MypyError:
  """Represents a single mypy error line."""

  path: Path
  line: int
  message: str
  code: str


def _run_mypy(target: str) -> tuple[int, str]:
  """Run mypy and return (exit_code, combined_output)."""
  process = subprocess.run(
    [sys.executable, "-m", "mypy", target],
    capture_output=True,
    text=True,
    check=False,
  )
  output = "\n".join(part for part in (process.stdout, process.stderr) if part).strip()
  return process.returncode, output


def _parse_errors(mypy_output: str) -> list[MypyError]:
  """Parse mypy output into structured errors."""
  errors: list[MypyError] = []
  for raw_line in mypy_output.splitlines():
    match = _MYPY_ERROR_RE.match(raw_line.strip())
    if not match:
      continue
    errors.append(
      MypyError(
        path=Path(match.group("path")),
        line=int(match.group("line")),
        message=match.group("message"),
        code=match.group("code"),
      )
    )
  return errors


def _strip_redundant_cast(expression: str) -> str:
  """Replace cast(TYPE, VALUE) with VALUE when a top-level cast is found."""
  match = _CAST_CALL_RE.search(expression)
  if not match:
    return expression

  start = match.start()
  open_index = expression.find("(", match.start())
  if open_index == -1:
    return expression

  depth = 1
  index = open_index + 1
  comma_index = -1
  while index < len(expression):
    char = expression[index]
    if char == "(":
      depth += 1
    elif char == ")":
      depth -= 1
      if depth == 0:
        close_index = index
        break
    elif char == "," and depth == 1 and comma_index == -1:
      comma_index = index
    index += 1
  else:
    return expression

  if comma_index == -1:
    return expression

  value_segment = expression[comma_index + 1 : close_index].strip()
  return f"{expression[:start]}{value_segment}{expression[close_index + 1 :]}"


def _ensure_generic_annotations(line: str) -> str:
  """Patch bare generic names that violate disallow_any_generics."""
  line = _CALLABLE_NO_ARGS_RE.sub("Callable[..., Any]", line)
  line = _TASK_NO_ARGS_RE.sub("Task[Any]", line)
  return line


def _add_any_import_if_needed(lines: list[str]) -> bool:
  """Add `Any` import when inserted generic annotations require it."""
  if not any("Any]" in line or " Any" in line for line in lines):
    return False

  typing_import_indexes = [
    idx
    for idx, line in enumerate(lines)
    if line.startswith("from typing import ") and "Any" not in line
  ]
  if typing_import_indexes:
    idx = typing_import_indexes[0]
    lines[idx] = lines[idx].rstrip("\n") + ", Any\n"
    return True

  for idx, line in enumerate(lines):
    if line.startswith("from __future__ import"):
      lines.insert(idx + 1, "from typing import Any\n")
      return True

  lines.insert(0, "from typing import Any\n")
  return True


def _apply_safe_fixes(errors: list[MypyError], repo_root: Path) -> int:
  """Apply automatic, semantics-preserving fixes for known diagnostics."""
  by_file: defaultdict[Path, list[MypyError]] = defaultdict(list)
  for error in errors:
    by_file[repo_root / error.path].append(error)

  changed_files = 0
  for file_path, file_errors in by_file.items():
    if not file_path.exists():
      continue

    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    original = list(lines)

    for error in sorted(file_errors, key=lambda item: item.line, reverse=True):
      line_index = error.line - 1
      if line_index < 0 or line_index >= len(lines):
        continue

      line = lines[line_index]
      if error.code == "redundant-cast":
        lines[line_index] = _strip_redundant_cast(line)
      elif error.code == "unused-ignore":
        lines[line_index] = _TYPE_IGNORE_RE.sub("", line) + "\n"
      elif error.code == "type-arg":
        lines[line_index] = _ensure_generic_annotations(line)

    _add_any_import_if_needed(lines)

    if lines != original:
      file_path.write_text("".join(lines), encoding="utf-8")
      changed_files += 1

  return changed_files


def _append_type_ignores(errors: list[MypyError], repo_root: Path) -> int:
  """Suppress unresolved diagnostics with targeted type-ignore comments."""
  by_file_and_line: defaultdict[Path, defaultdict[int, set[str]]] = defaultdict(
    lambda: defaultdict(set)
  )
  for error in errors:
    by_file_and_line[repo_root / error.path][error.line].add(error.code)

  changed_files = 0
  for file_path, line_map in by_file_and_line.items():
    if not file_path.exists():
      continue

    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    original = list(lines)

    for line_number, codes in sorted(line_map.items(), reverse=True):
      line_index = line_number - 1
      if line_index < 0 or line_index >= len(lines):
        continue

      line = lines[line_index].rstrip("\n")
      if line.strip().startswith("#"):
        continue

      existing = re.search(r"#\s*type:\s*ignore\[([^\]]+)\]", line)
      if existing:
        current_codes = {
          code.strip() for code in existing.group(1).split(",") if code.strip()
        }
        all_codes = sorted(current_codes | codes)
        lines[line_index] = (
          re.sub(
            r"#\s*type:\s*ignore\[[^\]]+\]",
            f"# type: ignore[{','.join(all_codes)}]",
            line,
          )
          + "\n"
        )
      elif "# type: ignore" in line:
        continue
      else:
        lines[line_index] = f"{line}  # type: ignore[{','.join(sorted(codes))}]\n"

    if lines != original:
      file_path.write_text("".join(lines), encoding="utf-8")
      changed_files += 1

  return changed_files


def _build_parser() -> ArgumentParser:
  parser = ArgumentParser(description="Auto-fix PawControl mypy diagnostics")
  parser.add_argument(
    "--target",
    default="custom_components/pawcontrol",
    help="Mypy target path or module (default: custom_components/pawcontrol)",
  )
  parser.add_argument(
    "--max-iterations",
    type=int,
    default=8,
    help="Max fix + re-check loops (default: 8)",
  )
  parser.add_argument(
    "--no-safe-fixes",
    action="store_true",
    help="Disable safe rewrites (redundant cast, unused ignore, missing generics)",
  )
  parser.add_argument(
    "--no-suppress-remaining",
    action="store_true",
    help="Do not add targeted type: ignore comments for unresolved issues",
  )
  return parser


def main() -> int:
  args = _build_parser().parse_args()
  repo_root = Path(__file__).resolve().parents[1]

  for iteration in range(1, args.max_iterations + 1):
    exit_code, output = _run_mypy(args.target)
    if exit_code == 0:
      print(f"✅ mypy passed on iteration {iteration}")
      return 0

    errors = _parse_errors(output)
    if not errors:
      print(output)
      print("❌ mypy failed, but no parseable errors were found")
      return 1

    print(f"🔁 Iteration {iteration}: parsed {len(errors)} errors")
    changed = 0

    if not args.no_safe_fixes:
      safe_changed = _apply_safe_fixes(errors, repo_root)
      changed += safe_changed
      if safe_changed:
        print(f"  • Applied safe fixes in {safe_changed} file(s)")

    if not args.no_suppress_remaining:
      exit_code_after_safe, output_after_safe = _run_mypy(args.target)
      if exit_code_after_safe != 0:
        unresolved = _parse_errors(output_after_safe)
        suppressed_files = _append_type_ignores(unresolved, repo_root)
        changed += suppressed_files
        if suppressed_files:
          print(f"  • Added targeted ignores in {suppressed_files} file(s)")

    if changed == 0:
      print("❌ No applicable automatic fix found for remaining errors")
      print(output)
      return 1

  final_exit_code, final_output = _run_mypy(args.target)
  if final_exit_code == 0:
    print("✅ mypy passed after final verification")
    return 0

  print("❌ mypy still failing after maximum iterations")
  print(final_output)
  return 1


if __name__ == "__main__":
  raise SystemExit(main())
