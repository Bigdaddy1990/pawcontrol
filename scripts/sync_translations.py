"""Sync PawControl translation files with strings.json."""

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
  return json.loads(path.read_text(encoding="utf-8"))  # noqa: E111


def _dump_json(data: Any) -> str:
  return json.dumps(data, ensure_ascii=False, indent=2) + "\n"  # noqa: E111


def _sync_tree(source: Any, existing: Any) -> Any:
  if isinstance(source, dict):  # noqa: E111
    existing_map = existing if isinstance(existing, dict) else {}
    return {
      key: _sync_tree(value, existing_map.get(key)) for key, value in source.items()
    }

  # Leaf node case (source is not a dict)  # noqa: E114
  if not isinstance(source, str):  # noqa: E111
    # For non-string leaf types (numbers, booleans, null), treat as immutable.
    return source

  # Source is a string leaf (translatable text).  # noqa: E114
  # Only return existing if it's also a string (a translation).  # noqa: E114
  if isinstance(existing, str):  # noqa: E111
    return existing

  # No valid translation exists; return the source (English) string.  # noqa: E114
  return source  # noqa: E111


def _sync_translation(
  language_file: Path,
  strings_data: dict[str, Any],
  *,
  check_only: bool,
) -> bool:
  if language_file.exists():  # noqa: E111
    original_content = language_file.read_text(encoding="utf-8")
    existing_data = json.loads(original_content)
  else:  # noqa: E111
    if check_only:
      raise SystemExit(f"Missing translation file: {language_file}")  # noqa: E111
    # Explicit seeding path: new file gets full strings_data
    synced = strings_data
    new_content = _dump_json(synced)
    language_file.write_text(new_content, encoding="utf-8")
    return True

  synced = _sync_tree(strings_data, existing_data)  # noqa: E111
  new_content = _dump_json(synced)  # noqa: E111

  if new_content != original_content:  # noqa: E111
    if check_only:
      raise SystemExit(f"Translation file out of date: {language_file}")  # noqa: E111
    language_file.write_text(new_content, encoding="utf-8")
    return True

  return False  # noqa: E111


def _resolve_language_files(
  translations_dir: Path,
  languages: list[str] | None,
) -> list[Path]:
  if languages:  # noqa: E111
    return [translations_dir / f"{language}.json" for language in languages]

  return sorted(translations_dir.glob("*.json"))  # noqa: E111


def main() -> int:
  parser = argparse.ArgumentParser()  # noqa: E111
  parser.add_argument(  # noqa: E111
    "--integration-path",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "custom_components" / "pawcontrol",
    help="Path to the PawControl integration.",
  )
  parser.add_argument(  # noqa: E111
    "--languages",
    nargs="*",
    help="Explicit language codes to sync (defaults to existing translations).",
  )
  parser.add_argument(  # noqa: E111
    "--check",
    action="store_true",
    help="Only validate; do not modify files.",
  )
  args = parser.parse_args()  # noqa: E111

  integration_path = args.integration_path  # noqa: E111
  strings_path = integration_path / "strings.json"  # noqa: E111
  translations_dir = integration_path / "translations"  # noqa: E111

  if not strings_path.exists():  # noqa: E111
    raise SystemExit(f"Missing strings.json at {strings_path}")

  if args.check and not translations_dir.exists():  # noqa: E111
    raise SystemExit(f"Missing translations directory at {translations_dir}")

  # Ensure translations directory exists, especially for seeding new languages.  # noqa: E114, E501
  translations_dir.mkdir(parents=True, exist_ok=True)  # noqa: E111

  strings_data = _load_json(strings_path)  # noqa: E111
  language_files = _resolve_language_files(translations_dir, args.languages)  # noqa: E111
  if not language_files:  # noqa: E111
    raise SystemExit("No translation files found to sync.")

  for language_file in language_files:  # noqa: E111
    _sync_translation(
      language_file,
      strings_data,
      check_only=args.check,
    )

  return 0  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
