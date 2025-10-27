"""Validate setup flags localization coverage and documentation."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STRINGS_PATH = ROOT / "custom_components" / "pawcontrol" / "strings.json"
TRANSLATIONS_DIR = ROOT / "custom_components" / "pawcontrol" / "translations"
DOC_PATH = ROOT / "docs" / "diagnostik.md"

_FLAG_PREFIX = "setup_flags_panel_flag_"
_SOURCE_PREFIX = "setup_flags_panel_source_"
_DOC_ROW_PATTERN = re.compile(
    r"^\|\s*component\.pawcontrol\.common\.(setup_flags_panel_(?:flag|source)_[a-z0-9_]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
    re.MULTILINE,
)


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


def test_translations_include_setup_flag_keys() -> None:
    expected = _expected_setup_flag_keys()
    expected_keys = set(expected)

    for path in TRANSLATIONS_DIR.glob("*.json"):
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

        if path.name == "en.json":
            for key, value in expected.items():
                assert common[key] == value, (path, key)


def test_documentation_lists_all_setup_flag_translations() -> None:
    expected = _expected_setup_flag_keys()
    doc_content = DOC_PATH.read_text(encoding="utf-8")

    matches = _DOC_ROW_PATTERN.findall(doc_content)
    assert matches, "Localization table missing from docs/diagnostik.md"

    doc_keys = {match[0] for match in matches}
    assert doc_keys == set(expected), (sorted(expected), sorted(doc_keys))

    en_translation = _load_json(TRANSLATIONS_DIR / "en.json")["common"]
    de_translation = _load_json(TRANSLATIONS_DIR / "de.json")["common"]

    for key, english_value, german_value in matches:
        english_value = english_value.strip()
        german_value = german_value.strip()
        assert english_value == en_translation[key], (
            key,
            english_value,
            en_translation[key],
        )
        assert german_value == de_translation[key], (
            key,
            german_value,
            de_translation[key],
        )
