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
from collections.abc import Mapping, Sequence
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


def _load_allowlist(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"Allowlist file {path} does not exist") from exc

    allowlist: list[str] = []
    seen: set[str] = set()

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        entry = raw_line.strip()
        if not entry or entry.startswith("#"):
            continue

        if entry in seen:
            raise SystemExit(
                f"Allowlist entry '{entry}' is duplicated on line {line_number}"
            )

        allowlist.append(entry)
        seen.add(entry)

    return allowlist


def _determine_translation_targets(allowlist: Sequence[str] | None) -> list[tuple[str, Path]]:
    discovered: dict[str, Path] = {
        path.stem: path for path in TRANSLATIONS_DIR.glob("*.json")
    }

    codes: set[str] = set(discovered)
    if allowlist is not None:
        codes |= set(allowlist)

    codes.add("en")

    return [
        (code, discovered.get(code, TRANSLATIONS_DIR / f"{code}.json"))
        for code in sorted(codes)
    ]


def _ensure_translation_file(
    path: Path, template: Mapping[str, Any], *, check_only: bool
) -> bool:
    if path.exists():
        return False

    if check_only:
        raise SystemExit(
            f"{path} is missing. Run the sync script without --check to bootstrap it."
        )

    _dump_json(path, template)
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify that translations are in sync.",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        help=(
            "Optional path to a newline-delimited list of language codes that should be managed. "
            "Entries prefixed with '#' are treated as comments."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    allowlist: list[str] | None = None
    if args.allowlist is not None:
        allowlist = _load_allowlist(args.allowlist)

    strings = _load_json(STRINGS_PATH)
    try:
        common_section = strings[_COMMON_SECTION]
    except KeyError as exc:  # pragma: no cover - guard against unexpected structure
        raise SystemExit("strings.json is missing the `common` section") from exc

    expected_entries = _collect_expected_entries(common_section)

    english_path = TRANSLATIONS_DIR / "en.json"
    if not english_path.exists():
        raise SystemExit("translations/en.json is required as the canonical source")

    english_template = _load_json(english_path)

    changed = False
    bootstrapped_languages: list[str] = []

    for language, translation_path in _determine_translation_targets(allowlist):
        created = _ensure_translation_file(
            translation_path,
            english_template,
            check_only=args.check,
        )
        if created:
            bootstrapped_languages.append(language)

        changed |= created
        changed |= _sync_translation_file(
            translation_path, expected_entries, args.check
        )

    if changed and not args.check:
        if bootstrapped_languages:
            print(
                "Bootstrapped translation stubs for: "
                + ", ".join(sorted(bootstrapped_languages))
            )
        print("Updated PawControl translations.")
    elif not changed and not args.check:
        print("PawControl translations already in sync.")


if __name__ == "__main__":
    main()
