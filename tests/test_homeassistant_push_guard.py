"""Tests for the Home Assistant push guard migration script."""

from __future__ import annotations


import json
from pathlib import Path
from urllib.error import URLError

import pytest
from scripts import homeassistant_push_guard as push_guard

Version = push_guard.Version


def _write_rule_file(path: Path) -> None:
  path.write_text(
    json.dumps({
      "min_covered_version": "2024.1.0",
      "max_covered_version": "2026.2.0",
      "rules": [
        {
          "id": "rule-1",
          "description": "replace async_timeout",
          "introduced_in": "2024.1.0",
          "pattern": r"import async_timeout",
          "replacement": "import asyncio",
          "file_globs": ["**/*.py"],
        }
      ],
    }),
    encoding="utf-8",
  )


def test_run_check_detects_findings(tmp_path: Path, monkeypatch) -> None:
  rules_path = tmp_path / "rules.json"
  _write_rule_file(rules_path)
  source_root = tmp_path / "src"
  source_root.mkdir()
  target = source_root / "module.py"
  target.write_text("import async_timeout\n", encoding="utf-8")

  rule_set = push_guard.load_rules(rules_path)
  monkeypatch.setattr(
    push_guard,
    "fetch_latest_homeassistant_version",
    lambda: Version.parse("2025.1.0"),
  )

  findings, version = push_guard.run(source_root, rule_set, fix=False)

  assert version == Version.parse("2025.1.0")
  assert len(findings) == 1
  assert findings[0].rule_id == "rule-1"
  assert "async_timeout" in target.read_text(encoding="utf-8")


def test_run_fix_applies_replacement(tmp_path: Path, monkeypatch) -> None:
  rules_path = tmp_path / "rules.json"
  _write_rule_file(rules_path)
  source_root = tmp_path / "src"
  source_root.mkdir()
  target = source_root / "module.py"
  target.write_text("import async_timeout\n", encoding="utf-8")

  rule_set = push_guard.load_rules(rules_path)
  monkeypatch.setattr(
    push_guard,
    "fetch_latest_homeassistant_version",
    lambda: Version.parse("2025.1.0"),
  )

  findings, _ = push_guard.run(source_root, rule_set, fix=True)

  assert len(findings) == 1
  assert "import asyncio" in target.read_text(encoding="utf-8")


def test_validate_coverage_reports_newer_release() -> None:
  rule_set = push_guard.RuleSet(
    min_covered_version=Version.parse("2024.1.0"),
    max_covered_version=Version.parse("2024.12.0"),
    rules=(),
  )

  assert not push_guard.validate_coverage(rule_set, Version.parse("2025.1.0"))


def test_fetch_latest_homeassistant_version_raises_on_network_error(
  monkeypatch,
) -> None:
  def _raise_url_error(*_args, **_kwargs):
    raise URLError("no network")

  monkeypatch.setattr(push_guard, "urlopen", _raise_url_error)

  with pytest.raises(
    RuntimeError,
    match="Failed to fetch latest Home Assistant version from PyPI",
  ):
    push_guard.fetch_latest_homeassistant_version()


def test_load_rules_rejects_invalid_pattern(tmp_path: Path) -> None:
  rules_path = tmp_path / "rules.json"
  rules_path.write_text(
    json.dumps({
      "min_covered_version": "2024.1.0",
      "max_covered_version": "2026.2.0",
      "rules": [
        {
          "id": "rule-1",
          "description": "broken regex",
          "introduced_in": "2024.1.0",
          "pattern": r"(",
          "replacement": "x",
        }
      ],
    }),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="invalid regex pattern"):
    push_guard.load_rules(rules_path)


def test_apply_rule_does_not_leave_backup_file(tmp_path: Path) -> None:
  target = tmp_path / "module.py"
  target.write_text("import async_timeout\n", encoding="utf-8")
  rule = push_guard.UpgradeRule(
    id="rule-1",
    description="replace async_timeout",
    pattern=r"import async_timeout",
    replacement="import asyncio",
    introduced_in=Version.parse("2024.1.0"),
    file_globs=("**/*.py",),
  )

  replaced = push_guard.apply_rule(target, rule, fix=True)

  assert replaced == 1
  assert "import asyncio" in target.read_text(encoding="utf-8")
  assert not target.with_suffix(".py.bak").exists()


def test_apply_rule_preserves_start_end_of_string_regex(tmp_path: Path) -> None:
  target = tmp_path / "module.py"
  target.write_text("header\nimport async_timeout\n", encoding="utf-8")
  rule = push_guard.UpgradeRule(
    id="rule-anchored",
    description="anchored match should apply only to full-string match",
    pattern=r"^import async_timeout$",
    replacement="import asyncio",
    introduced_in=Version.parse("2024.1.0"),
    file_globs=("**/*.py",),
  )

  replaced = push_guard.apply_rule(target, rule, fix=True)

  assert replaced == 0
  assert target.read_text(encoding="utf-8") == "header\nimport async_timeout\n"
