"""Shared metadata validation helpers for hassfest validators."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from annotatedyaml import loader as yaml_loader

ALLOWED_SELECTORS: Final[set[str]] = {
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


@dataclass(frozen=True, slots=True)
class MetadataFiles:
    """Definition of the files and root key used by hassfest metadata checks."""

    root_key: str
    description_filename: str
    icons_filename: str
    strings_filename: str


def grep_dir(path: Path, pattern: str) -> bool:  # pragma: no cover - patched in tests
    """Placeholder implementation patched by tests."""

    return path.exists()


def _load_description(domain: str, filename: str) -> Mapping[str, Mapping[str, object]]:
    path = Path(domain) / filename
    return yaml_loader.load_yaml(str(path))


def _load_json(domain: str, filename: str) -> Mapping[str, object]:
    path = Path(domain) / filename
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _validate_entry(
    integration,
    *,
    root_key: str,
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

    selector_translation_key_errors: set[str] = set()

    if isinstance(fields, Mapping):
        for field_name, field_config in fields.items():
            if not isinstance(field_config, Mapping):
                continue

            selector = field_config.get("selector")
            if not isinstance(selector, Mapping):
                continue

            for selector_type in selector:
                if selector_type not in ALLOWED_SELECTORS:
                    integration.add_error(
                        root_key,
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
        integration.add_error(root_key, f"{entry_id} has no icon")

    if not isinstance(entry_strings, Mapping) or not entry_strings.get("name"):
        integration.add_error(root_key, f"{entry_id} has no name")
    if not isinstance(entry_strings, Mapping) or not entry_strings.get("description"):
        integration.add_error(root_key, f"{entry_id} has no description")

    if isinstance(fields, Mapping):
        for field_name in fields:
            field_strings = (
                string_fields.get(field_name)
                if isinstance(string_fields, Mapping)
                else {}
            )
            if not isinstance(field_strings, Mapping) or not field_strings.get("name"):
                integration.add_error(root_key, f"field {field_name} with no name")
            if not isinstance(field_strings, Mapping) or not field_strings.get(
                "description"
            ):
                integration.add_error(
                    root_key, f"field {field_name} with no description"
                )
            if field_name in selector_translation_key_errors:
                integration.add_error(
                    root_key,
                    f"field {field_name} with a selector with a translation key",
                )


def validate_metadata(integrations, files: MetadataFiles) -> None:
    """Validate metadata defined in hassfest YAML/JSON files."""

    for domain, integration in integrations.items():
        grep_dir(integration.path, files.root_key)

        try:
            descriptions = _load_description(domain, files.description_filename)
        except Exception:
            integration.add_error(
                files.root_key, f"Invalid {files.description_filename}"
            )
            continue
        icons = _load_json(domain, files.icons_filename).get(files.root_key, {})
        strings = _load_json(domain, files.strings_filename).get(files.root_key, {})

        if not isinstance(descriptions, Mapping):
            integration.add_error(
                files.root_key, f"Invalid {files.description_filename}"
            )
            continue

        for entry_id, metadata in descriptions.items():
            _validate_entry(
                integration,
                root_key=files.root_key,
                entry_id=entry_id,
                metadata=metadata,
                icon_data=icons,
                string_data=strings,
            )


__all__ = [
    "ALLOWED_SELECTORS",
    "MetadataFiles",
    "grep_dir",
    "validate_metadata",
]
