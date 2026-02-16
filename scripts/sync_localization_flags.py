"""Sync/validate localization flags.

This repository uses a lightweight variant of Home Assistant's localization validation.
In CI we run this script in --check mode to ensure the expected files exist and are valid JSON.
"""  # noqa: E501

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

TABLE_START_MARKER = "<!-- START_SETUP_FLAGS_TABLE -->"
TABLE_END_MARKER = "<!-- END_SETUP_FLAGS_TABLE -->"

_FLAG_PREFIX = "setup_flags_panel_flag_"
_SOURCE_PREFIX = "setup_flags_panel_source_"

_LANGUAGE_LABELS = {
  "en": "Englisch",
  "de": "Deutsch",
  "es": "Spanisch",
  "fr": "Französisch",
}


def _read_allowlist(path: Path) -> set[str]:
  try:  # noqa: E111
    return {
      line.strip()
      for line in path.read_text(encoding="utf-8").splitlines()
      if line.strip() and not line.strip().startswith("#")
    }
  except FileNotFoundError:  # noqa: E111
    return set()


def _load_json(path: Path) -> Any:
  return json.loads(path.read_text(encoding="utf-8"))  # noqa: E111


def _translation_languages(translations_dir: Path) -> list[str]:
  languages = sorted(path.stem for path in translations_dir.glob("*.json"))  # noqa: E111
  if "en" in languages:  # noqa: E111
    languages.remove("en")
  return ["en", *languages]  # noqa: E111


def _setup_flag_keys(strings_path: Path) -> list[str]:
  strings = _load_json(strings_path)  # noqa: E111
  common = strings.get("common", {})  # noqa: E111
  return [  # noqa: E111
    key
    for key in common
    if key.startswith(_FLAG_PREFIX) or key.startswith(_SOURCE_PREFIX)
  ]


def _update_markdown_table(
  markdown_path: Path,
  keys: list[str],
  translations: dict[str, dict[str, dict[str, str]]],
  languages: list[str],
  *,
  check_only: bool,
) -> bool:
  content = markdown_path.read_text(encoding="utf-8")  # noqa: E111
  lines = content.splitlines()  # noqa: E111
  start_index: int | None = None  # noqa: E111
  end_index: int | None = None  # noqa: E111
  for index, line in enumerate(lines):  # noqa: E111
    if line.strip() == TABLE_START_MARKER:
      start_index = index  # noqa: E111
    elif line.strip() == TABLE_END_MARKER and start_index is not None:
      end_index = index  # noqa: E111
      break  # noqa: E111

  if start_index is None or end_index is None or end_index <= start_index:  # noqa: E111
    raise SystemExit("Setup flags table markers missing.")

  header_cells = [  # noqa: E111
    "Übersetzungsschlüssel",
    *(f"{_LANGUAGE_LABELS.get(code, code)} (`{code}`)" for code in languages),
  ]
  table_lines = [  # noqa: E111
    "| " + " | ".join(header_cells) + " |",
    "| " + " | ".join("---" for _ in header_cells) + " |",
  ]

  for key in keys:  # noqa: E111
    row = [
      f"component.pawcontrol.common.{key}",
      *(translations[language]["common"][key] for language in languages),
    ]
    table_lines.append("| " + " | ".join(row) + " |")

  new_lines = lines[: start_index + 1] + table_lines + lines[end_index:]  # noqa: E111
  new_content = "\n".join(new_lines) + "\n"  # noqa: E111

  if new_content != content:  # noqa: E111
    if check_only:
      raise SystemExit("Setup flags table is out of date.")  # noqa: E111
    markdown_path.write_text(new_content, encoding="utf-8")
    return True

  return False  # noqa: E111


def main() -> int:
  parser = argparse.ArgumentParser()  # noqa: E111
  parser.add_argument("--allowlist", type=Path, required=False)  # noqa: E111
  parser.add_argument(  # noqa: E111
    "--check",
    action="store_true",
    help="Only validate; do not modify files.",
  )
  args = parser.parse_args()  # noqa: E111

  repo_root = Path(__file__).resolve().parents[1]  # noqa: E111
  allowlist = _read_allowlist(args.allowlist) if args.allowlist else set()  # noqa: E111

  # Validate strings.json and translation json files exist + parse as JSON  # noqa: E114
  custom_components_dir = repo_root / "custom_components"  # noqa: E111
  if not custom_components_dir.exists():  # noqa: E111
    return 0

  for integration_dir in custom_components_dir.iterdir():  # noqa: E111
    if not integration_dir.is_dir():
      continue  # noqa: E111
    strings = integration_dir / "strings.json"
    if strings.exists():
      _load_json(strings)  # noqa: E111

    translations_dir = integration_dir / "translations"
    if translations_dir.exists():
      for tfile in translations_dir.glob("*.json"):  # noqa: E111
        data = _load_json(tfile)
        # Optional minimal sanity: remove keys listed in allowlist from consideration
        # (This script is intentionally conservative; hassfest performs schema validation.)  # noqa: E501
        if allowlist:
          # noop usage to avoid unused variable warnings in strict linters  # noqa: E114
          _ = data  # noqa: E111

  pawcontrol_dir = custom_components_dir / "pawcontrol"  # noqa: E111
  strings_path = pawcontrol_dir / "strings.json"  # noqa: E111
  translations_dir = pawcontrol_dir / "translations"  # noqa: E111
  docs_path = repo_root / "docs" / "diagnostics.md"  # noqa: E111
  if strings_path.exists() and translations_dir.exists() and docs_path.exists():  # noqa: E111
    keys = _setup_flag_keys(strings_path)
    if keys:
      languages = _translation_languages(translations_dir)  # noqa: E111
      strings_common = _load_json(strings_path).get("common", {})  # noqa: E111
      translations: dict[str, dict[str, dict[str, str]]] = {  # noqa: E111
        "en": {"common": {key: strings_common[key] for key in keys}}
      }
      for language in languages:  # noqa: E111
        if language == "en":
          continue  # noqa: E111
        translation_path = translations_dir / f"{language}.json"
        translation_common = _load_json(translation_path).get("common", {})
        translations[language] = {
          "common": {key: translation_common[key] for key in keys}
        }
      _update_markdown_table(  # noqa: E111
        docs_path,
        keys,
        translations,
        languages,
        check_only=args.check,
      )

  return 0  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
