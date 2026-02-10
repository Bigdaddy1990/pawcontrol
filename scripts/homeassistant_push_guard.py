"""Validate and auto-fix Home Assistant API migrations before pushing."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from packaging.version import Version

DEFAULT_RULES_PATH = Path("scripts/homeassistant_upgrade_rules.json")
DEFAULT_SOURCE_ROOT = Path("custom_components/pawcontrol")
PYPI_HOMEASSISTANT_URL = "https://pypi.org/pypi/homeassistant/json"


@dataclass(frozen=True)
class UpgradeRule:
  """Single codemod-style replacement rule."""

  id: str
  description: str
  pattern: str
  replacement: str
  introduced_in: Version
  file_globs: tuple[str, ...]


@dataclass(frozen=True)
class RuleSet:
  """Parsed rule set with version metadata."""

  min_covered_version: Version
  max_covered_version: Version
  rules: tuple[UpgradeRule, ...]


@dataclass(frozen=True)
class MatchResult:
  """Represents one matched rule occurrence."""

  rule_id: str
  path: Path
  count: int


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description=(
      "Checks PawControl against Home Assistant migration rules and can "
      "auto-apply known API fixes."
    )
  )
  parser.add_argument(
    "--rules",
    type=Path,
    default=DEFAULT_RULES_PATH,
    help="Path to JSON rule file.",
  )
  parser.add_argument(
    "--root",
    type=Path,
    default=DEFAULT_SOURCE_ROOT,
    help="Source folder to scan.",
  )
  parser.add_argument(
    "--fix",
    action="store_true",
    help="Apply replacements in-place.",
  )
  parser.add_argument(
    "--check",
    action="store_true",
    help="Do not modify files, fail if matching deprecated patterns are found.",
  )
  return parser.parse_args()


def load_rules(path: Path) -> RuleSet:
  payload = json.loads(path.read_text(encoding="utf-8"))
  rules: list[UpgradeRule] = []
  for entry in payload["rules"]:
    rules.append(
      UpgradeRule(
        id=entry["id"],
        description=entry["description"],
        pattern=entry["pattern"],
        replacement=entry["replacement"],
        introduced_in=Version(entry["introduced_in"]),
        file_globs=tuple(entry.get("file_globs", ["**/*.py"])),
      )
    )

  return RuleSet(
    min_covered_version=Version(payload["min_covered_version"]),
    max_covered_version=Version(payload["max_covered_version"]),
    rules=tuple(rules),
  )


def fetch_latest_homeassistant_version() -> Version:
  request = Request(
    PYPI_HOMEASSISTANT_URL, headers={"User-Agent": "pawcontrol-bot/1.0"}
  )
  with urlopen(request, timeout=20) as response:
    payload = json.loads(response.read().decode("utf-8"))
  return Version(payload["info"]["version"])


def applicable_rules(
  rule_set: RuleSet, latest_version: Version
) -> tuple[UpgradeRule, ...]:
  return tuple(rule for rule in rule_set.rules if latest_version >= rule.introduced_in)


def collect_python_files(root: Path, globs: tuple[str, ...]) -> list[Path]:
  files: set[Path] = set()
  for pattern in globs:
    files.update(root.glob(pattern))
  return sorted(path for path in files if path.is_file())


def apply_rule(path: Path, rule: UpgradeRule, *, fix: bool) -> int:
  content = path.read_text(encoding="utf-8")
  updated, count = re.subn(rule.pattern, rule.replacement, content, flags=re.MULTILINE)
  if fix and count:
    path.write_text(updated, encoding="utf-8")
  return count


def run(
  root: Path, rule_set: RuleSet, *, fix: bool
) -> tuple[list[MatchResult], Version]:
  latest_version = fetch_latest_homeassistant_version()
  rules = applicable_rules(rule_set, latest_version)

  findings: list[MatchResult] = []
  for rule in rules:
    for path in collect_python_files(root, rule.file_globs):
      count = apply_rule(path, rule, fix=fix)
      if count:
        findings.append(MatchResult(rule_id=rule.id, path=path, count=count))

  return findings, latest_version


def print_findings(findings: list[MatchResult]) -> None:
  grouped: dict[str, list[MatchResult]] = {}
  for finding in findings:
    grouped.setdefault(finding.rule_id, []).append(finding)

  for rule_id, results in grouped.items():
    print(f"- Regel {rule_id}:")
    for result in results:
      print(f"  * {result.path}: {result.count} Treffer")


def validate_coverage(rule_set: RuleSet, latest_version: Version) -> bool:
  if latest_version <= rule_set.max_covered_version:
    return True
  print(
    "WARNUNG: Die Rule-Definition deckt Home Assistant bis "
    f"{rule_set.max_covered_version} ab, gefunden wurde {latest_version}."
  )
  print(
    "Bitte scripts/homeassistant_upgrade_rules.json erweitern, damit neue "
    "Breaking-Changes automatisch gefixt werden können."
  )
  return False


def main() -> int:
  args = parse_args()
  if args.fix and args.check:
    print("Bitte entweder --fix oder --check nutzen.")
    return 2

  mode_fix = args.fix and not args.check
  rule_set = load_rules(args.rules)
  findings, latest_version = run(args.root, rule_set, fix=mode_fix)

  coverage_ok = validate_coverage(rule_set, latest_version)

  print(f"Neueste Home-Assistant-Version laut PyPI: {latest_version}")
  if findings:
    print_findings(findings)

  if args.check:
    if findings:
      print(
        "Fehler: Veraltete Muster gefunden. Nutze --fix für automatische Reparatur."
      )
      return 1
    if not coverage_ok:
      return 1
    print("OK: Keine bekannten veralteten Home-Assistant-Muster gefunden.")
    return 0

  if mode_fix:
    if findings:
      print("Automatische Migrationen wurden angewendet.")
    else:
      print("Keine automatischen Migrationen notwendig.")
    return 0 if coverage_ok else 1

  # Default mode behaves like check in CI-safe mode.
  if findings or not coverage_ok:
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
