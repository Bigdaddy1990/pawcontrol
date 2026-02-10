"""Tests for the Home Assistant push guard migration script."""

from __future__ import annotations

import json
from pathlib import Path

from packaging.version import Version

from scripts import homeassistant_push_guard as push_guard


def _write_rule_file(path: Path) -> None:
  path.write_text(
    json.dumps(
      {
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
      }
    ),
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
    lambda: Version("2025.1.0"),
  )

  findings, version = push_guard.run(source_root, rule_set, fix=False)

  assert version == Version("2025.1.0")
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
    lambda: Version("2025.1.0"),
  )

  findings, _ = push_guard.run(source_root, rule_set, fix=True)

  assert len(findings) == 1
  assert "import asyncio" in target.read_text(encoding="utf-8")


def test_validate_coverage_reports_newer_release() -> None:
  rule_set = push_guard.RuleSet(
    min_covered_version=Version("2024.1.0"),
    max_covered_version=Version("2024.12.0"),
    rules=(),
  )

  assert not push_guard.validate_coverage(rule_set, Version("2025.1.0"))
