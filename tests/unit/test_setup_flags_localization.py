"""Validate setup flags localization coverage and documentation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from custom_components.pawcontrol.options_flow_main import PawControlOptionsFlow
from scripts.sync_localization_flags import TABLE_END_MARKER, TABLE_START_MARKER

ROOT = Path(__file__).resolve().parents[2]
STRINGS_PATH = ROOT / "custom_components" / "pawcontrol" / "strings.json"
TRANSLATIONS_DIR = ROOT / "custom_components" / "pawcontrol" / "translations"
DOC_PATH = ROOT / "docs" / "diagnostics.md"

_FLAG_PREFIX = "setup_flags_panel_flag_"
_SOURCE_PREFIX = "setup_flags_panel_source_"


def _translation_languages() -> list[str]:
  languages = sorted(path.stem for path in TRANSLATIONS_DIR.glob("*.json"))
  assert "en" in languages, "English translation must always be present"
  languages.remove("en")
  return ["en", *languages]


def _split_table_row(row: str) -> list[str]:
  return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _parse_localization_table(
  doc_content: str,
) -> tuple[list[str], dict[str, dict[str, str]]]:
  lines = doc_content.splitlines()
  start_index: int | None = None
  end_index: int | None = None
  for index, line in enumerate(lines):
    stripped = line.strip()
    if stripped == TABLE_START_MARKER:
      start_index = index
    elif stripped == TABLE_END_MARKER and start_index is not None:
      end_index = index
      break

  if start_index is None or end_index is None or end_index <= start_index:
    raise AssertionError("Localization table markers missing from docs/diagnostics.md")

  table_lines = [
    line for line in lines[start_index + 1 : end_index] if line.startswith("|")
  ]

  header: list[str] | None = None
  rows: list[list[str]] = []
  for line in table_lines:
    cells = _split_table_row(line)
    if header is None:
      header = cells
      continue

    if all(cell.startswith("-") for cell in cells):
      continue

    rows.append(cells)

  if header is None:
    raise AssertionError("Localization table missing from docs/diagnostics.md")

  if header[0] != "Übersetzungsschlüssel":
    raise AssertionError("Unexpected localization table header")

  languages: list[str] = []
  for cell in header[1:]:
    match = re.search(r"\(`([a-z0-9_-]+)`\)", cell)
    if match is None:
      raise AssertionError(f"Missing language code in header cell '{cell}'")
    languages.append(match.group(1))

  doc_rows: dict[str, dict[str, str]] = {}
  for cells in rows:
    if len(cells) != len(header):
      continue

    key_cell = cells[0]
    match = re.match(
      r"component\.pawcontrol\.common\.(setup_flags_panel_(?:flag|source)_[a-z0-9_]+)",
      key_cell,
    )
    if match is None:
      continue

    key = match.group(1)
    doc_rows[key] = {
      language: value.strip()
      for language, value in zip(languages, cells[1:], strict=True)
    }

  return languages, doc_rows


def _load_json(path: Path) -> dict[str, object]:
  return json.loads(path.read_text(encoding="utf-8"))


def _expected_setup_flag_keys() -> dict[str, str]:
  strings = _load_json(STRINGS_PATH)
  common = strings["common"]
  relevant_keys = {
    key: value
    for key, value in common.items()
    if key.startswith(_FLAG_PREFIX) or key.startswith(_SOURCE_PREFIX)
  }
  return relevant_keys


def test_setup_flag_supported_languages_match_translations() -> None:
  expected_languages = {path.stem for path in TRANSLATIONS_DIR.glob("*.json")}
  if STRINGS_PATH.exists():
    expected_languages.add("en")
  if not expected_languages:
    expected_languages.add("en")
  assert (
    frozenset(expected_languages)
    == PawControlOptionsFlow._SETUP_FLAG_SUPPORTED_LANGUAGES
  )


def test_translations_include_setup_flag_keys() -> None:
  expected = _expected_setup_flag_keys()
  expected_keys = set(expected)

  for language in _translation_languages():
    path = TRANSLATIONS_DIR / f"{language}.json"
    translation = _load_json(path)
    common = translation.get("common", {})
    seen_keys = {
      key
      for key in common
      if key.startswith(_FLAG_PREFIX) or key.startswith(_SOURCE_PREFIX)
    }
    assert seen_keys == expected_keys, (
      path,
      sorted(expected_keys - seen_keys),
      sorted(seen_keys - expected_keys),
    )

    if language == "en":
      for key, value in expected.items():
        assert common[key] == value, (path, key)


def test_documentation_lists_all_setup_flag_translations() -> None:
  expected = _expected_setup_flag_keys()
  doc_content = DOC_PATH.read_text(encoding="utf-8")
  languages, doc_rows = _parse_localization_table(doc_content)

  translation_languages = _translation_languages()
  assert languages == translation_languages, (languages, translation_languages)

  doc_keys = set(doc_rows)
  assert doc_keys == set(expected), (sorted(expected), sorted(doc_keys))

  translations = {
    language: _load_json(TRANSLATIONS_DIR / f"{language}.json")["common"]
    for language in translation_languages
  }

  for key, expected_translations in doc_rows.items():
    for language in translation_languages:
      assert expected_translations[language] == translations[language][key], (
        key,
        language,
        expected_translations[language],
        translations[language][key],
      )
