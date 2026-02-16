"""Detect legacy Python 2 multi-exception syntax.

This guard prevents regressions like ``except TypeError, ValueError:`` that break
Python 3 AST parsing and hassfest validation.
"""

import argparse
from pathlib import Path
import re

LEGACY_EXCEPT_PATTERN = re.compile(
  r"^(?P<indent>\s*)except\s+(?!\()"
  r"(?P<exceptions>[^:\n]+?,\s*[^:\n]+?)"
  r"\s*:\s*(?P<comment>#.*)?$",
)


def _iter_python_files(root: Path) -> list[Path]:
  return sorted(path for path in root.rglob("*.py") if path.is_file())  # noqa: E111


def _find_legacy_handlers(path: Path) -> list[int]:
  line_numbers: list[int] = []  # noqa: E111
  for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):  # noqa: E111
    if LEGACY_EXCEPT_PATTERN.match(line):
      line_numbers.append(index)  # noqa: E111
  return line_numbers  # noqa: E111


def _parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__)  # noqa: E111
  parser.add_argument(  # noqa: E111
    "paths",
    nargs="*",
    default=["custom_components/pawcontrol"],
    help="Directories to scan for Python files (default: custom_components/pawcontrol)",
  )
  return parser.parse_args()  # noqa: E111


def main() -> int:
  args = _parse_args()  # noqa: E111
  findings: list[tuple[Path, int]] = []  # noqa: E111

  for raw_path in args.paths:  # noqa: E111
    root = Path(raw_path)
    if root.is_file() and root.suffix == ".py":
      for line_no in _find_legacy_handlers(root):  # noqa: E111
        findings.append((root, line_no))
      continue  # noqa: E111

    if not root.exists():
      print(f"[check_legacy_exception_syntax] Skipping missing path: {root}")  # noqa: E111
      continue  # noqa: E111

    for path in _iter_python_files(root):
      for line_no in _find_legacy_handlers(path):  # noqa: E111
        findings.append((path, line_no))

  if not findings:  # noqa: E111
    print("No legacy multi-exception syntax found.")
    return 0

  print("Legacy Python 2 multi-exception syntax detected:")  # noqa: E111
  for path, line_no in findings:  # noqa: E111
    print(f" - {path}:{line_no}")
  print("Use Python 3 tuple syntax, e.g. `except (TypeError, ValueError):`.")  # noqa: E111
  return 1  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
