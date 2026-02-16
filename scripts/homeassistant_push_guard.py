"""Validate and auto-fix Home Assistant API migrations before pushing."""

import argparse
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class InvalidVersion(ValueError):
  """Raised when a version string cannot be parsed."""  # noqa: E111


@dataclass(frozen=True, order=True)
class Version:
  """Small comparable version model for calendar-style Home Assistant versions."""  # noqa: E111

  major: int  # noqa: E111
  minor: int  # noqa: E111
  patch: int = 0  # noqa: E111

  @classmethod  # noqa: E111
  def parse(cls, value: str) -> Version:  # noqa: E111
    if not isinstance(value, str):
      raise InvalidVersion(f"Expected version string, got {type(value)!r}")  # noqa: E111

    match = re.fullmatch(r"\s*(\d+)\.(\d+)(?:\.(\d+))?\s*", value)
    if not match:
      raise InvalidVersion(f"Invalid version format: {value!r}")  # noqa: E111

    major, minor, patch = match.groups(default="0")
    return cls(int(major), int(minor), int(patch))

  def __str__(self) -> str:  # noqa: E111
    return f"{self.major}.{self.minor}.{self.patch}"


DEFAULT_RULES_PATH = Path("scripts/homeassistant_upgrade_rules.json")
DEFAULT_SOURCE_ROOT = Path("custom_components/pawcontrol")
PYPI_HOMEASSISTANT_URL = "https://pypi.org/pypi/homeassistant/json"
REQUEST_TIMEOUT_SECONDS = 30

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpgradeRule:
  """Single codemod-style replacement rule."""  # noqa: E111

  id: str  # noqa: E111
  description: str  # noqa: E111
  pattern: str  # noqa: E111
  replacement: str  # noqa: E111
  introduced_in: Version  # noqa: E111
  file_globs: tuple[str, ...]  # noqa: E111


@dataclass(frozen=True)
class RuleSet:
  """Parsed rule set with version metadata."""  # noqa: E111

  min_covered_version: Version  # noqa: E111
  max_covered_version: Version  # noqa: E111
  rules: tuple[UpgradeRule, ...]  # noqa: E111


@dataclass(frozen=True)
class MatchResult:
  """Represents one matched rule occurrence."""  # noqa: E111

  rule_id: str  # noqa: E111
  path: Path  # noqa: E111
  count: int  # noqa: E111


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(  # noqa: E111
    description=(
      "Checks PawControl against Home Assistant migration rules and can "
      "auto-apply known API fixes."
    )
  )
  parser.add_argument(  # noqa: E111
    "--rules",
    type=Path,
    default=DEFAULT_RULES_PATH,
    help="Path to JSON rule file.",
  )
  parser.add_argument(  # noqa: E111
    "--root",
    type=Path,
    default=DEFAULT_SOURCE_ROOT,
    help="Source folder to scan.",
  )
  parser.add_argument(  # noqa: E111
    "--fix",
    action="store_true",
    help="Apply replacements in-place.",
  )
  parser.add_argument(  # noqa: E111
    "--check",
    action="store_true",
    help="Do not modify files, fail if matching deprecated patterns are found.",
  )
  return parser.parse_args()  # noqa: E111


def _parse_rule(index: int, entry: dict[str, Any]) -> UpgradeRule:
  required_fields = (  # noqa: E111
    "id",
    "description",
    "pattern",
    "replacement",
    "introduced_in",
  )
  for field_name in required_fields:  # noqa: E111
    if field_name not in entry:
      raise ValueError(  # noqa: E111
        f"Rule at index {index} is missing required field '{field_name}'."
      )

  pattern = entry["pattern"]  # noqa: E111
  if not isinstance(pattern, str):  # noqa: E111
    raise ValueError(f"Rule at index {index} has non-string pattern.")

  try:  # noqa: E111
    re.compile(pattern)
  except re.error as err:  # noqa: E111
    raise ValueError(
      f"Rule '{entry.get('id', index)}' has invalid regex pattern: {err}"
    ) from err

  raw_globs = entry.get("file_globs", ["**/*.py"])  # noqa: E111
  if not isinstance(raw_globs, list) or not all(  # noqa: E111
    isinstance(glob, str) for glob in raw_globs
  ):
    raise ValueError(f"Rule '{entry.get('id', index)}' has invalid file_globs value.")

  try:  # noqa: E111
    introduced_in = Version.parse(entry["introduced_in"])
  except InvalidVersion as err:  # noqa: E111
    raise ValueError(
      f"Rule '{entry.get('id', index)}' has invalid introduced_in version."
    ) from err

  return UpgradeRule(  # noqa: E111
    id=entry["id"],
    description=entry["description"],
    pattern=pattern,
    replacement=entry["replacement"],
    introduced_in=introduced_in,
    file_globs=tuple(raw_globs),
  )


def load_rules(path: Path) -> RuleSet:
  try:  # noqa: E111
    payload = json.loads(path.read_text(encoding="utf-8"))
  except OSError as err:  # noqa: E111
    raise ValueError(f"Failed to read rule file '{path}': {err}") from err
  except json.JSONDecodeError as err:  # noqa: E111
    raise ValueError(f"Invalid JSON in rules file '{path}': {err}") from err

  if not isinstance(payload, dict):  # noqa: E111
    raise ValueError("Rules file must contain a JSON object.")

  for field_name in ("min_covered_version", "max_covered_version", "rules"):  # noqa: E111
    if field_name not in payload:
      raise ValueError(f"Rules file is missing required field '{field_name}'.")  # noqa: E111

  try:  # noqa: E111
    min_covered_version = Version.parse(payload["min_covered_version"])
    max_covered_version = Version.parse(payload["max_covered_version"])
  except InvalidVersion as err:  # noqa: E111
    raise ValueError(
      "min_covered_version/max_covered_version must be valid versions."
    ) from err

  if min_covered_version > max_covered_version:  # noqa: E111
    raise ValueError("min_covered_version cannot be newer than max_covered_version.")

  raw_rules = payload["rules"]  # noqa: E111
  if not isinstance(raw_rules, list):  # noqa: E111
    raise ValueError("rules must be a list.")

  rules: list[UpgradeRule] = []  # noqa: E111
  for index, entry in enumerate(raw_rules):  # noqa: E111
    if not isinstance(entry, dict):
      raise ValueError(f"Rule at index {index} must be a JSON object.")  # noqa: E111
    rules.append(_parse_rule(index, entry))

  return RuleSet(  # noqa: E111
    min_covered_version=min_covered_version,
    max_covered_version=max_covered_version,
    rules=tuple(rules),
  )


def _validated_https_url(url: str) -> str:
  """Return a validated HTTPS URL for outbound requests."""  # noqa: E111
  parsed = urlparse(url)  # noqa: E111
  if parsed.scheme != "https" or not parsed.netloc:  # noqa: E111
    raise ValueError(f"Only absolute HTTPS URLs are allowed, got: {url!r}")
  return url  # noqa: E111


def fetch_latest_homeassistant_version() -> Version:
  request = Request(  # noqa: E111
    _validated_https_url(PYPI_HOMEASSISTANT_URL),
    headers={
      "User-Agent": "pawcontrol-bot/1.0",
      "Accept": "application/json",
    },
  )

  try:  # noqa: E111
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # nosec B310 - request URL is restricted by _validated_https_url.
      status = getattr(response, "status", 200)  # noqa: E111
      if status != 200:  # noqa: E111
        raise ValueError(f"PyPI API returned unexpected status {status}")
      payload = json.loads(response.read().decode("utf-8"))  # noqa: E111
    return Version.parse(payload["info"]["version"])
  except (HTTPError, URLError, TimeoutError, OSError) as err:  # noqa: E111
    raise RuntimeError(
      "Failed to fetch latest Home Assistant version from PyPI."
    ) from err
  except (json.JSONDecodeError, KeyError, ValueError, InvalidVersion) as err:  # noqa: E111
    raise RuntimeError("PyPI returned malformed Home Assistant version data.") from err


def applicable_rules(
  rule_set: RuleSet, latest_version: Version
) -> tuple[UpgradeRule, ...]:
  return tuple(rule for rule in rule_set.rules if latest_version >= rule.introduced_in)  # noqa: E111


def collect_python_files(root: Path, globs: tuple[str, ...]) -> list[Path]:
  files: set[Path] = set()  # noqa: E111
  for pattern in globs:  # noqa: E111
    files.update(root.glob(pattern))
  return sorted(path for path in files if path.is_file())  # noqa: E111


def _write_file_atomically(path: Path, content: str) -> None:
  with tempfile.NamedTemporaryFile(  # noqa: E111
    mode="w",
    encoding="utf-8",
    dir=path.parent,
    delete=False,
  ) as tmp_file:
    tmp_file.write(content)
    tmp_path = Path(tmp_file.name)

  try:  # noqa: E111
    os.replace(tmp_path, path)
  finally:  # noqa: E111
    if tmp_path.exists():
      tmp_path.unlink()  # noqa: E111


def apply_rule(path: Path, rule: UpgradeRule, *, fix: bool) -> int:
  try:  # noqa: E111
    content = path.read_text(encoding="utf-8")
  except OSError as err:  # noqa: E111
    _LOGGER.warning("Unable to read %s: %s", path, err)
    return 0

  updated, count = re.subn(rule.pattern, rule.replacement, content)  # noqa: E111

  if not (fix and count):  # noqa: E111
    return count

  backup_path = path.with_suffix(f"{path.suffix}.bak")  # noqa: E111
  backup_created = False  # noqa: E111
  try:  # noqa: E111
    shutil.copy2(path, backup_path)
    backup_created = True
    _write_file_atomically(path, updated)
  except OSError as err:  # noqa: E111
    _LOGGER.warning("Failed to update %s safely: %s", path, err)
    if backup_created:
      try:  # noqa: E111
        shutil.copy2(backup_path, path)
      except OSError as restore_err:  # noqa: E111
        _LOGGER.critical(
          "Failed to restore %s from backup %s: %s",
          path,
          backup_path,
          restore_err,
        )
    return 0
  finally:  # noqa: E111
    if backup_created and backup_path.exists():
      try:  # noqa: E111
        backup_path.unlink()
      except OSError as err:  # noqa: E111
        _LOGGER.warning("Failed to remove backup file %s: %s", backup_path, err)

  return count  # noqa: E111


def run(
  root: Path, rule_set: RuleSet, *, fix: bool
) -> tuple[list[MatchResult], Version]:
  latest_version = fetch_latest_homeassistant_version()  # noqa: E111
  rules = applicable_rules(rule_set, latest_version)  # noqa: E111

  findings: list[MatchResult] = []  # noqa: E111
  for rule in rules:  # noqa: E111
    for path in collect_python_files(root, rule.file_globs):
      count = apply_rule(path, rule, fix=fix)  # noqa: E111
      if count:  # noqa: E111
        findings.append(MatchResult(rule_id=rule.id, path=path, count=count))

  return findings, latest_version  # noqa: E111


def print_findings(findings: list[MatchResult]) -> None:
  grouped: dict[str, list[MatchResult]] = {}  # noqa: E111
  for finding in findings:  # noqa: E111
    grouped.setdefault(finding.rule_id, []).append(finding)

  for rule_id, results in grouped.items():  # noqa: E111
    print(f"- Rule {rule_id}:")
    for result in results:
      print(f"  * {result.path}: {result.count} matches")  # noqa: E111


def validate_coverage(rule_set: RuleSet, latest_version: Version) -> bool:
  if latest_version <= rule_set.max_covered_version:  # noqa: E111
    return True
  print(  # noqa: E111
    "WARNING: The rule definition covers Home Assistant versions only up to "
    f"{rule_set.max_covered_version}, but found {latest_version}."
  )
  print(  # noqa: E111
    "Please extend scripts/homeassistant_upgrade_rules.json so new breaking "
    "changes can be fixed automatically."
  )
  return False  # noqa: E111


def main() -> int:
  logging.basicConfig(  # noqa: E111
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
  )
  args = parse_args()  # noqa: E111
  if args.fix and args.check:  # noqa: E111
    print("Please use either --fix or --check.")
    return 2

  mode_fix = args.fix and not args.check  # noqa: E111
  rule_set = load_rules(args.rules)  # noqa: E111
  try:  # noqa: E111
    findings, latest_version = run(args.root, rule_set, fix=mode_fix)
  except RuntimeError as err:  # noqa: E111
    _LOGGER.error("Failed to run push guard: %s", err, exc_info=True)
    return 1

  coverage_ok = validate_coverage(rule_set, latest_version)  # noqa: E111

  print(f"Latest Home Assistant version from PyPI: {latest_version}")  # noqa: E111
  if findings:  # noqa: E111
    print_findings(findings)

  if args.check:  # noqa: E111
    if findings:
      print("Error: Deprecated patterns found. Use --fix for automatic repairs.")  # noqa: E111
      return 1  # noqa: E111
    if not coverage_ok:
      return 1  # noqa: E111
    print("OK: No known deprecated Home Assistant patterns found.")
    return 0

  if mode_fix:  # noqa: E111
    if findings:
      print("Automatic migrations were applied.")  # noqa: E111
    else:
      print("No automatic migrations were needed.")  # noqa: E111
    return 0 if coverage_ok else 1

  # Default mode behaves like check in CI-safe mode.  # noqa: E114
  if findings or not coverage_ok:  # noqa: E111
    return 1
  return 0  # noqa: E111


if __name__ == "__main__":
  sys.exit(main())  # noqa: E111
