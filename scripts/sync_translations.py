"""Sync PawControl translation files with strings.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
  return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(data: Any) -> str:
  return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _sync_tree(source: Any, existing: Any) -> Any:
  if isinstance(source, dict):
    existing_map = existing if isinstance(existing, dict) else {}
    return {
      key: _sync_tree(value, existing_map.get(key)) for key, value in source.items()
    }

  # Leaf node case (source is not a dict)
  if not isinstance(source, str):
    # For non-string leaf types (numbers, booleans, null), treat as immutable.
    return source

  # Source is a string leaf (translatable text).
  # Only return existing if it's also a string (a translation).
  if isinstance(existing, str):
    return existing

  # No valid translation exists; return the source (English) string.
  return source


def _sync_translation(
  language_file: Path,
  strings_data: dict[str, Any],
  *,
  check_only: bool,
) -> bool:
  if language_file.exists():
    existing_data = _load_json(language_file)
    original_content = language_file.read_text(encoding="utf-8")
  else:
    if check_only:
      raise SystemExit(f"Missing translation file: {language_file}")
    # Explicit seeding path: new file gets full strings_data
    synced = strings_data
    new_content = _dump_json(synced)
    language_file.write_text(new_content, encoding="utf-8")
    return True

  synced = _sync_tree(strings_data, existing_data)
  new_content = _dump_json(synced)

  if new_content != original_content:
    if check_only:
      raise SystemExit(f"Translation file out of date: {language_file}")
    language_file.write_text(new_content, encoding="utf-8")
    return True

  return False


def _resolve_language_files(
  translations_dir: Path,
  languages: list[str] | None,
) -> list[Path]:
  if languages:
    return [translations_dir / f"{language}.json" for language in languages]

  return sorted(translations_dir.glob("*.json"))


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--integration-path",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "custom_components" / "pawcontrol",
    help="Path to the PawControl integration.",
  )
  parser.add_argument(
    "--languages",
    nargs="*",
    help="Explicit language codes to sync (defaults to existing translations).",
  )
  parser.add_argument(
    "--check",
    action="store_true",
    help="Only validate; do not modify files.",
  )
  args = parser.parse_args()

  integration_path = args.integration_path
  strings_path = integration_path / "strings.json"
  translations_dir = integration_path / "translations"

  if not strings_path.exists():
    raise SystemExit(f"Missing strings.json at {strings_path}")

  if args.check and not translations_dir.exists():
    raise SystemExit(f"Missing translations directory at {translations_dir}")

  # Ensure translations directory exists, especially for seeding new languages.
  translations_dir.mkdir(parents=True, exist_ok=True)

  strings_data = _load_json(strings_path)
  language_files = _resolve_language_files(translations_dir, args.languages)
  if not language_files:
    raise SystemExit("No translation files found to sync.")

  for language_file in language_files:
    _sync_translation(
      language_file,
      strings_data,
      check_only=args.check,
    )

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
