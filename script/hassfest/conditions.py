"""Hassfest validator for automation conditions."""

from __future__ import annotations

from ._metadata import MetadataFiles, grep_dir, validate_metadata

CONDITION_DESCRIPTION_FILENAME = "conditions.yaml"
CONDITION_ICONS_FILENAME = "icons.json"
CONDITION_STRINGS_FILENAME = "strings.json"
ROOT_KEY = "conditions"

_FILES = MetadataFiles(
    root_key=ROOT_KEY,
    description_filename=CONDITION_DESCRIPTION_FILENAME,
    icons_filename=CONDITION_ICONS_FILENAME,
    strings_filename=CONDITION_STRINGS_FILENAME,
)


def validate(integrations, config) -> None:
    """Validate condition metadata for the provided integrations."""

    validate_metadata(integrations, _FILES)


__all__ = [
    "CONDITION_DESCRIPTION_FILENAME",
    "CONDITION_ICONS_FILENAME",
    "CONDITION_STRINGS_FILENAME",
    "grep_dir",
    "validate",
]
