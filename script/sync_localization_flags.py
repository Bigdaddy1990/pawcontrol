"""Synchronise setup flags localization keys across PawControl translations.

This helper keeps the ``setup_flags_panel`` translation keys consistent across
``strings.json`` and every language file in ``translations/``. Home Assistant
expects integrations to mirror the canonical English strings into the
``translations`` directory, so contributors can either copy the English default
or supply a translated value without drifting from the manifest-defined keys.

Run the module directly to update the repository in-place or use ``--check`` to
fail when a file would change.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
STRINGS_PATH = REPO_ROOT / "custom_components" / "pawcontrol" / "strings.json"
TRANSLATIONS_DIR = REPO_ROOT / "custom_components" / "pawcontrol" / "translations"

_FLAG_PREFIX = "setup_flags_panel_flag_"
_SOURCE_PREFIX = "setup_flags_panel_source_"
_FIXED_KEYS = {"setup_flags_panel_description", "setup_flags_panel_title"}
_COMMON_SECTION = "common"

JsonDict = dict[str, Any]


def _load_json(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(f"{serialized}\n", encoding="utf-8")


def _collect_expected_entries(common_section: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in common_section.items() if _is_setup_flag_key(key)
    }


def _is_setup_flag_key(key: str) -> bool:
    return (
        key.startswith(_FLAG_PREFIX)
        or key.startswith(_SOURCE_PREFIX)
        or key in _FIXED_KEYS
    )


def _build_synced_common(
    existing: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    enforce_expected_values: bool,
) -> dict[str, Any]:
    synced: dict[str, Any] = {
        key: value for key, value in existing.items() if not _is_setup_flag_key(key)
    }

    for key, default_value in expected.items():
        if enforce_expected_values or key not in existing:
            synced[key] = default_value
        else:
            synced[key] = existing[key]

    return synced


def _sync_translation_file(
    path: Path, expected: Mapping[str, Any], check_only: bool
) -> bool:
    payload = _load_json(path)
    common = dict(payload.get(_COMMON_SECTION, {}))

    enforce_expected_values = path.name == "en.json"
    synced_common = _build_synced_common(
        common, expected, enforce_expected_values=enforce_expected_values
    )

    if common == synced_common:
        return False

    if check_only:
        raise SystemExit(
            f"{path} is out of date. Run `python -m script.sync_localization_flags` to refresh it."
        )

    payload = dict(payload)
    payload[_COMMON_SECTION] = synced_common
    _dump_json(path, payload)
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify that translations are in sync.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    strings = _load_json(STRINGS_PATH)
    try:
        common_section = strings[_COMMON_SECTION]
    except KeyError as exc:  # pragma: no cover - guard against unexpected structure
        raise SystemExit("strings.json is missing the `common` section") from exc

    expected_entries = _collect_expected_entries(common_section)

    changed = False
    for translation_path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        changed |= _sync_translation_file(
            translation_path, expected_entries, args.check
        )

    if changed and not args.check:
        print("Updated PawControl translations.")
    elif not changed and not args.check:
        print("PawControl translations already in sync.")


if __name__ == "__main__":
    main()
