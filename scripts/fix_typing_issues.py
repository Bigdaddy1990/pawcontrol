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

from argparse import ArgumentParser, Namespace
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

_MYPY_LINE_RE = re.compile(
  r"^(?P<path>[^:\n]+):(?P<line>\d+):(?:\d+:)? error: "
  r"(?P<message>.+?)\s+\[(?P<code>[^\]]+)\]$"
)
_UNUSED_IGNORE_RE = re.compile(r"\s*#\s*type:\s*ignore(?:\[[^\]]*\])?\s*$")
_BARE_CALLABLE_RE = re.compile(r"\bCallable\b(?!\s*\[)")
_BARE_TASK_RE = re.compile(r"\bTask\b(?!\s*\[)")
_CAST_CALL_RE = re.compile(r"\bcast\s*\(")


@dataclass(frozen=True)
class MypyError:
  """Represents a single parsed MyPy error line."""

  path: Path
  line: int
  message: str
  code: str


@dataclass
class FixStats:
  """Tracks modifications applied by fixers."""

  redundant_cast: int = 0
  unused_ignore: int = 0
  callable_type_arg: int = 0
  task_type_arg: int = 0

  @property
  def total(self) -> int:
    """Return count of all applied fixes."""
    return (
      self.redundant_cast
      + self.unused_ignore
      + self.callable_type_arg
      + self.task_type_arg
    )


def parse_mypy_errors(stdout: str, repo_root: Path) -> list[MypyError]:
  """Parse MyPy output into structured error entries."""
  parsed: list[MypyError] = []
  for raw_line in stdout.splitlines():
    match = _MYPY_LINE_RE.match(raw_line.strip())
    if not match:
      continue
    parsed.append(
      MypyError(
        path=(repo_root / match.group("path")).resolve(),
        line=int(match.group("line")),
        message=match.group("message"),
        code=match.group("code"),
      )
    )
  return parsed


def _remove_redundant_cast(line: str) -> tuple[str, bool]:
  """Remove one ``cast(T, value)`` wrapper from ``line`` when possible."""
  match = _CAST_CALL_RE.search(line)
  if not match:
    return line, False

  start = match.start()
  idx = match.end()
  depth = 1
  comma_index: int | None = None
  while idx < len(line):
    char = line[idx]
    if char == "(":
      depth += 1
    elif char == ")":
      depth -= 1
      if depth == 0:
        break
    elif char == "," and depth == 1 and comma_index is None:
      comma_index = idx
    idx += 1

  if depth != 0 or comma_index is None or idx >= len(line):
    return line, False

  inner = line[comma_index + 1 : idx].strip()
  if not inner:
    return line, False

  replacement = f"{line[:start]}{inner}{line[idx + 1 :]}"
  return replacement, replacement != line


def _apply_single_error_fix(
  error: MypyError, line: str, stats: FixStats
) -> tuple[str, bool]:
  """Apply one supported fixer to a single line."""
  if error.code == "unused-ignore":
    updated = _UNUSED_IGNORE_RE.sub("", line)
    if updated != line:
      stats.unused_ignore += 1
      return updated, True

  if error.code == "redundant-cast":
    updated, changed = _remove_redundant_cast(line)
    if changed:
      stats.redundant_cast += 1
      return updated, True

  if error.code == "type-arg":
    changed = False
    updated = line
    if "Callable" in error.message and _BARE_CALLABLE_RE.search(updated):
      updated = _BARE_CALLABLE_RE.sub("Callable[..., Any]", updated)
      if updated != line:
        stats.callable_type_arg += 1
        changed = True
    if "Task" in error.message and _BARE_TASK_RE.search(updated):
      previous = updated
      updated = _BARE_TASK_RE.sub("Task[Any]", updated)
      if updated != previous:
        stats.task_type_arg += 1
        changed = True
    return updated, changed

  return line, False


def apply_fixes(errors: list[MypyError]) -> FixStats:
  """Apply all supported fixes grouped by file and line."""
  stats = FixStats()
  grouped: dict[Path, dict[int, list[MypyError]]] = {}
  for error in errors:
    grouped.setdefault(error.path, {}).setdefault(error.line, []).append(error)

  for file_path, by_line in grouped.items():
    if not file_path.exists():
      continue

    original_lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines = list(original_lines)

    for line_number, line_errors in by_line.items():
      index = line_number - 1
      if index < 0 or index >= len(updated_lines):
        continue

      line_content = updated_lines[index].rstrip("\n")
      has_newline = updated_lines[index].endswith("\n")

      for error in line_errors:
        line_content, _ = _apply_single_error_fix(error, line_content, stats)

      updated_lines[index] = f"{line_content}\n" if has_newline else line_content

    if updated_lines != original_lines:
      file_path.write_text("".join(updated_lines), encoding="utf-8")

  return stats


def run_mypy(paths: list[str]) -> tuple[int, str]:
  """Run MyPy and return the process return code and stdout/stderr."""
  command = [sys.executable, "-m", "mypy", *paths]
  proc = subprocess.run(
    command,
    check=False,
    capture_output=True,
    text=True,
  )
  output_parts = [proc.stdout.strip(), proc.stderr.strip()]
  output = "\n".join(part for part in output_parts if part)
  return proc.returncode, output


def _parse_args(argv: list[str]) -> Namespace:
  parser = ArgumentParser(description=__doc__)
  parser.add_argument(
    "--paths",
    nargs="+",
    default=["custom_components/pawcontrol"],
    help="Paths passed to MyPy.",
  )
  parser.add_argument(
    "--max-rounds",
    type=int,
    default=4,
    help="Maximum fix rounds before giving up.",
  )
  parser.add_argument(
    "--apply",
    action="store_true",
    help="Apply fixes. Without this flag the script only reports findings.",
  )
  return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
  """CLI entry point."""
  args = _parse_args(argv or sys.argv[1:])
  repo_root = Path.cwd()

  return_code, output = run_mypy(args.paths)
  errors = parse_mypy_errors(output, repo_root)
  print(output)

  if not errors:
    print("✅ No MyPy issues found.")
    return return_code

  print(f"Found {len(errors)} MyPy errors.")
  if not args.apply:
    print("Dry run only. Re-run with --apply to patch supported issues.")
    return 1

  for round_index in range(1, args.max_rounds + 1):
    round_stats = apply_fixes(errors)
    print(
      "Round"
      f" {round_index}: applied {round_stats.total} fixes"
      f" (redundant-cast={round_stats.redundant_cast},"
      f" unused-ignore={round_stats.unused_ignore},"
      f" callable-type-arg={round_stats.callable_type_arg},"
      f" task-type-arg={round_stats.task_type_arg})"
    )

    if round_stats.total == 0:
      break

    return_code, output = run_mypy(args.paths)
    errors = parse_mypy_errors(output, repo_root)
    print(output)
    if not errors:
      print("✅ All detectable MyPy issues were fixed.")
      return 0

  print(f"⚠️ Remaining MyPy issues after auto-fix: {len(errors)}")
  return 1


if __name__ == "__main__":
  raise SystemExit(main())
