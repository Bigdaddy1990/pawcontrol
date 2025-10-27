"""Hassfest validator for automation triggers."""

from __future__ import annotations

from ._metadata import MetadataFiles, grep_dir, validate_metadata

TRIGGER_DESCRIPTION_FILENAME = "triggers.yaml"
TRIGGER_ICONS_FILENAME = "icons.json"
TRIGGER_STRINGS_FILENAME = "strings.json"
ROOT_KEY = "triggers"

_FILES = MetadataFiles(
    root_key=ROOT_KEY,
    description_filename=TRIGGER_DESCRIPTION_FILENAME,
    icons_filename=TRIGGER_ICONS_FILENAME,
    strings_filename=TRIGGER_STRINGS_FILENAME,
)


def validate(integrations, config) -> None:
    """Validate trigger metadata for the provided integrations."""

    validate_metadata(integrations, _FILES)


__all__ = [
    "TRIGGER_DESCRIPTION_FILENAME",
    "TRIGGER_ICONS_FILENAME",
    "TRIGGER_STRINGS_FILENAME",
    "grep_dir",
    "validate",
]
