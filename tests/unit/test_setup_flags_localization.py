"""Validate setup flags localization coverage and documentation."""

from __future__ import annotations

import json
from pathlib import Path
import re

from scripts.sync_localization_flags import TABLE_END_MARKER, TABLE_START_MARKER

from custom_components.pawcontrol.options_flow_main import PawControlOptionsFlow

ROOT = Path(__file__).resolve().parents[2]
STRINGS_PATH = ROOT / "custom_components" / "pawcontrol" / "strings.json"
TRANSLATIONS_DIR = ROOT / "custom_components" / "pawcontrol" / "translations"
DOC_PATH = ROOT / "docs" / "diagnostics.md"

_FLAG_PREFIX = "setup_flags_panel_flag_"
_SOURCE_PREFIX = "setup_flags_panel_source_"


def _translation_languages() -> list[str]:
  languages = sorted(path.stem for path in TRANSLATIONS_DIR.glob("*.json"))  # noqa: E111
  assert "en" in languages, "English translation must always be present"  # noqa: E111
  languages.remove("en")  # noqa: E111
  return ["en", *languages]  # noqa: E111


def _split_table_row(row: str) -> list[str]:
  return [cell.strip() for cell in row.strip().strip("|").split("|")]  # noqa: E111


def _parse_localization_table(
  doc_content: str,
) -> tuple[list[str], dict[str, dict[str, str]]]:
  lines = doc_content.splitlines()  # noqa: E111
  start_index: int | None = None  # noqa: E111
  end_index: int | None = None  # noqa: E111
  for index, line in enumerate(lines):  # noqa: E111
    stripped = line.strip()
    if stripped == TABLE_START_MARKER:
      start_index = index  # noqa: E111
    elif stripped == TABLE_END_MARKER and start_index is not None:
      end_index = index  # noqa: E111
      break  # noqa: E111

  if start_index is None or end_index is None or end_index <= start_index:  # noqa: E111
    raise AssertionError("Localization table markers missing from docs/diagnostics.md")

  table_lines = [  # noqa: E111
    line for line in lines[start_index + 1 : end_index] if line.startswith("|")
  ]

  header: list[str] | None = None  # noqa: E111
  rows: list[list[str]] = []  # noqa: E111
  for line in table_lines:  # noqa: E111
    cells = _split_table_row(line)
    if header is None:
      header = cells  # noqa: E111
      continue  # noqa: E111

    if all(cell.startswith("-") for cell in cells):
      continue  # noqa: E111

    rows.append(cells)

  if header is None:  # noqa: E111
    raise AssertionError("Localization table missing from docs/diagnostics.md")

  if header[0] != "Übersetzungsschlüssel":  # noqa: E111
    raise AssertionError("Unexpected localization table header")

  languages: list[str] = []  # noqa: E111
  for cell in header[1:]:  # noqa: E111
    match = re.search(r"\(`([a-z0-9_-]+)`\)", cell)
    if match is None:
      raise AssertionError(f"Missing language code in header cell '{cell}'")  # noqa: E111
    languages.append(match.group(1))

  doc_rows: dict[str, dict[str, str]] = {}  # noqa: E111
  for cells in rows:  # noqa: E111
    if len(cells) != len(header):
      continue  # noqa: E111

    key_cell = cells[0]
    match = re.match(
      r"component\.pawcontrol\.common\.(setup_flags_panel_(?:flag|source)_[a-z0-9_]+)",
      key_cell,
    )
    if match is None:
      continue  # noqa: E111

    key = match.group(1)
    doc_rows[key] = {
      language: value.strip()
      for language, value in zip(languages, cells[1:], strict=True)
    }

  return languages, doc_rows  # noqa: E111


def _load_json(path: Path) -> dict[str, object]:
  return json.loads(path.read_text(encoding="utf-8"))  # noqa: E111


def _expected_setup_flag_keys() -> dict[str, str]:
  strings = _load_json(STRINGS_PATH)  # noqa: E111
  common = strings["common"]  # noqa: E111
  relevant_keys = {  # noqa: E111
    key: value
    for key, value in common.items()
    if key.startswith(_FLAG_PREFIX) or key.startswith(_SOURCE_PREFIX)
  }
  return relevant_keys  # noqa: E111


def test_setup_flag_supported_languages_match_translations() -> None:
  expected_languages = {path.stem for path in TRANSLATIONS_DIR.glob("*.json")}  # noqa: E111
  if STRINGS_PATH.exists():  # noqa: E111
    expected_languages.add("en")
  if not expected_languages:  # noqa: E111
    expected_languages.add("en")
  assert (  # noqa: E111
    frozenset(expected_languages)
    == PawControlOptionsFlow._SETUP_FLAG_SUPPORTED_LANGUAGES
  )


def test_translations_include_setup_flag_keys() -> None:
  expected = _expected_setup_flag_keys()  # noqa: E111
  expected_keys = set(expected)  # noqa: E111

  for language in _translation_languages():  # noqa: E111
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
      for key, value in expected.items():  # noqa: E111
        assert common[key] == value, (path, key)


def test_documentation_lists_all_setup_flag_translations() -> None:
  expected = _expected_setup_flag_keys()  # noqa: E111
  doc_content = DOC_PATH.read_text(encoding="utf-8")  # noqa: E111
  languages, doc_rows = _parse_localization_table(doc_content)  # noqa: E111

  translation_languages = _translation_languages()  # noqa: E111
  assert languages == translation_languages, (languages, translation_languages)  # noqa: E111

  doc_keys = set(doc_rows)  # noqa: E111
  assert doc_keys == set(expected), (sorted(expected), sorted(doc_keys))  # noqa: E111

  translations = {  # noqa: E111
    language: _load_json(TRANSLATIONS_DIR / f"{language}.json")["common"]
    for language in translation_languages
  }

  for key, expected_translations in doc_rows.items():  # noqa: E111
    for language in translation_languages:
      assert expected_translations[language] == translations[language][key], (  # noqa: E111
        key,
        language,
        expected_translations[language],
        translations[language][key],
      )
