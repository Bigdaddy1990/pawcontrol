"""Minimal hassfest condition validation used in tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from annotatedyaml import loader as yaml_loader

CONDITION_DESCRIPTION_FILENAME = "conditions.yaml"
CONDITION_ICONS_FILENAME = "icons.json"
CONDITION_STRINGS_FILENAME = "strings.json"
ROOT_KEY = "conditions"


def grep_dir(path: Path, pattern: str) -> bool:  # pragma: no cover - patched in tests
    """Placeholder implementation patched by tests."""

    return path.exists()


def _load_description(domain: str) -> Mapping[str, Mapping[str, object]]:
    path = Path(domain) / CONDITION_DESCRIPTION_FILENAME
    return yaml_loader.load_yaml(str(path))


def _load_json(domain: str, filename: str) -> Mapping[str, object]:
    path = Path(domain) / filename
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _validate_entry(
    integration,
    entry_id: str,
    metadata: Mapping[str, object],
    icon_data: Mapping[str, object],
    string_data: Mapping[str, object],
) -> None:
    entry_strings = (
        string_data.get(entry_id, {}) if isinstance(string_data, Mapping) else {}
    )
    fields = metadata.get("fields") if isinstance(metadata, Mapping) else None
    string_fields = (
        entry_strings.get("fields") if isinstance(entry_strings, Mapping) else None
    )
    allowed_selectors = {
        "select",
        "entity",
        "time",
        "number",
        "boolean",
        "text",
        "datetime",
        "date",
        "action",
    }

    selector_translation_key_errors: set[str] = set()

    if isinstance(fields, Mapping):
        for field_name, field_config in fields.items():
            if not isinstance(field_config, Mapping):
                continue

            selector = field_config.get("selector")
            if not isinstance(selector, Mapping):
                continue

            for selector_type in selector:
                if selector_type not in allowed_selectors:
                    integration.add_error(
                        ROOT_KEY,
                        f"Unknown selector type {selector_type}",
                    )
                    return

            if any(
                isinstance(selector_config, Mapping)
                and selector_config.get("translation_key")
                for selector_config in selector.values()
            ):
                selector_translation_key_errors.add(field_name)

    entry_icons = icon_data.get(entry_id)

    if not entry_icons:
        integration.add_error(ROOT_KEY, f"{entry_id} has no icon")

    if not isinstance(entry_strings, Mapping) or not entry_strings.get("name"):
        integration.add_error(ROOT_KEY, f"{entry_id} has no name")
    if not isinstance(entry_strings, Mapping) or not entry_strings.get("description"):
        integration.add_error(ROOT_KEY, f"{entry_id} has no description")

    if isinstance(fields, Mapping):
        for field_name, field_config in fields.items():
            field_strings = (
                string_fields.get(field_name)
                if isinstance(string_fields, Mapping)
                else {}
            )
            if not isinstance(field_strings, Mapping) or not field_strings.get("name"):
                integration.add_error(ROOT_KEY, f"field {field_name} with no name")
            if not isinstance(field_strings, Mapping) or not field_strings.get(
                "description"
            ):
                integration.add_error(
                    ROOT_KEY, f"field {field_name} with no description"
                )
            if field_name in selector_translation_key_errors:
                integration.add_error(
                    ROOT_KEY,
                    f"field {field_name} with a selector with a translation key",
                )


def validate(integrations, config) -> None:
    """Validate condition metadata for the provided integrations."""

    for domain, integration in integrations.items():
        grep_dir(integration.path, ROOT_KEY)

        try:
            descriptions = _load_description(domain)
        except Exception:
            integration.add_error(ROOT_KEY, "Invalid conditions.yaml")
            continue
        icons = _load_json(domain, CONDITION_ICONS_FILENAME).get(ROOT_KEY, {})
        strings = _load_json(domain, CONDITION_STRINGS_FILENAME).get(ROOT_KEY, {})

        if not isinstance(descriptions, Mapping):
            integration.add_error(ROOT_KEY, "Invalid conditions.yaml")
            continue

        for entry_id, metadata in descriptions.items():
            _validate_entry(integration, entry_id, metadata, icons, strings)


__all__ = [
    "CONDITION_DESCRIPTION_FILENAME",
    "CONDITION_ICONS_FILENAME",
    "CONDITION_STRINGS_FILENAME",
    "grep_dir",
    "validate",
]
