"""Verify docstring coverage stays above the documented baseline."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_ROOT = REPO_ROOT / "custom_components" / "pawcontrol"
BASELINE_PATH = REPO_ROOT / "docs" / "docstring_baseline.json"


@dataclass
class DocstringStats:
  total_defs: int = 0  # noqa: E111
  documented_defs: int = 0  # noqa: E111

  @property  # noqa: E111
  def coverage(self) -> float:  # noqa: E111
    if self.total_defs == 0:
      return 1.0  # noqa: E111
    return self.documented_defs / self.total_defs

  def to_dict(self) -> dict[str, float]:  # noqa: E111
    return {
      "total_defs": self.total_defs,
      "documented_defs": self.documented_defs,
      "coverage": self.coverage,
    }


_DEF_TYPES = (ast.AsyncFunctionDef, ast.FunctionDef, ast.ClassDef)


def _gather_docstring_stats() -> DocstringStats:
  stats = DocstringStats()  # noqa: E111

  for path in INTEGRATION_ROOT.rglob("*.py"):  # noqa: E111
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
      if isinstance(node, _DEF_TYPES):  # noqa: E111
        stats.total_defs += 1
        if ast.get_docstring(node):
          stats.documented_defs += 1  # noqa: E111

  return stats  # noqa: E111


def _load_baseline() -> dict[str, float] | None:
  if not BASELINE_PATH.exists():  # noqa: E111
    return None
  return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))  # noqa: E111


def _write_baseline(stats: DocstringStats) -> None:
  BASELINE_PATH.write_text(  # noqa: E111
    json.dumps(stats.to_dict(), indent=2) + "\n",
    encoding="utf-8",
  )


def _parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__)  # noqa: E111
  parser.add_argument(  # noqa: E111
    "--update",
    action="store_true",
    help="rewrite the baseline with the current docstring coverage",
  )
  return parser.parse_args()  # noqa: E111


def main() -> int:
  args = _parse_args()  # noqa: E111
  stats = _gather_docstring_stats()  # noqa: E111
  baseline = _load_baseline()  # noqa: E111

  if args.update or baseline is None:  # noqa: E111
    _write_baseline(stats)
    print(
      "Updated docstring baseline to",
      f"{stats.documented_defs}/{stats.total_defs} definitions",
    )
    return 0

  coverage = stats.coverage  # noqa: E111
  baseline_coverage = float(baseline.get("coverage", 0.0))  # noqa: E111

  if coverage + 1e-9 < baseline_coverage:  # noqa: E111
    print(
      "Docstring coverage regressed:",
      f"current={coverage:.4f}",
      f"baseline={baseline_coverage:.4f}",
    )
    print(
      "Run 'python scripts/enforce_docstring_baseline.py --update' after adding docstrings.",  # noqa: E501
    )
    return 1

  print(  # noqa: E111
    "Docstring coverage OK:",
    f"{stats.documented_defs}/{stats.total_defs} definitions",
    f"(baseline {baseline_coverage:.4f})",
  )
  return 0  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
