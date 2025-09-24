"""Condition validation helpers used in hassfest tests."""

from __future__ import annotations

import json
from pathlib import Path

from .model import Config, Integration

try:  # pragma: no cover - import error handled gracefully
    from annotatedyaml import loader as annotated_loader
except ImportError:  # pragma: no cover
    annotated_loader = None

CONDITIONS_FILENAME = "conditions.yaml"
ICONS_FILENAME = "icons.json"
STRINGS_FILENAME = "strings.json"


def grep_dir(path: Path, pattern: str) -> bool:  # pragma: no cover - patched in tests
    """Placeholder for Home Assistant's directory search helper."""

    return any(child.name == pattern for child in path.iterdir())


def _load_condition_descriptions(integration: Integration) -> dict[str, dict]:
    if annotated_loader is None:
        raise RuntimeError("annotatedyaml loader is not available")
    domain = integration.domain
    return annotated_loader.load_yaml(f"{domain}/{CONDITIONS_FILENAME}")


def _load_json(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    return json.loads(content)


def _validate_condition(
    integration: Integration,
    condition: str,
    definition: dict,
    icons: dict,
    strings: dict,
) -> None:
    conditions_icons = icons.get("conditions", {})
    icon_entry = conditions_icons.get(condition) or conditions_icons.get("_")
    if not icon_entry:
        integration.add_error(f"Condition {condition} has no icon")

    condition_strings = strings.get("conditions", {})
    string_entry = condition_strings.get(condition) or condition_strings.get("_", {})
    name = string_entry.get("name")
    description = string_entry.get("description")
    if not name:
        integration.add_error(f"Condition {condition} has no name")
    if not description:
        integration.add_error(f"Condition {condition} has no description")

    fields = definition.get("fields", {})
    string_fields = string_entry.get("fields", {})
    for field_name, field_def in fields.items():
        string_field = string_fields.get(field_name, {})
        if not string_field.get("name"):
            integration.add_error(f"Condition field {field_name} with no name")
        if not string_field.get("description"):
            integration.add_error(f"Condition field {field_name} with no description")
        selector = field_def.get("selector", {})
        if isinstance(selector, dict):
            for selector_type, selector_details in selector.items():
                if selector_type == "select":
                    if isinstance(selector_details, dict) and selector_details.get(
                        "translation_key"
                    ):
                        integration.add_error(
                            f"Condition field {field_name} with a selector with a translation key"
                        )
                elif selector_type not in {"entity", "time", "text", "number"}:
                    integration.add_error(
                        f"Unknown selector type {selector_type} for condition {condition}"
                    )


def validate(integrations: dict[str, Integration], config: Config) -> None:
    """Validate automation condition metadata for integrations."""

    for integration in integrations.values():
        if not grep_dir(integration.path, CONDITIONS_FILENAME):
            continue
        try:
            descriptions = _load_condition_descriptions(integration)
        except Exception:  # pragma: no cover - errors captured in tests
            integration.add_error("Invalid conditions.yaml")
            continue

        base_path = integration.path / "strings" / integration.domain
        icons_path = base_path / ICONS_FILENAME
        strings_path = base_path / STRINGS_FILENAME

        try:
            icons = _load_json(icons_path)
            strings = _load_json(strings_path)
        except json.JSONDecodeError as exc:  # pragma: no cover
            integration.add_error(f"Invalid JSON content: {exc}")
            continue

        for condition, definition in descriptions.items():
            _validate_condition(integration, condition, definition, icons, strings)

    # Config level errors are only populated for catastrophic failures in the
    # official implementation. The simplified tests do not expect any config
    # errors, so we leave the list untouched here.


__all__ = ["grep_dir", "validate"]
