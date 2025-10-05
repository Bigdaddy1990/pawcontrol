"""Manifest validation helpers used in hassfest tests."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from .model import Integration

_VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")

CUSTOM_INTEGRATION_MANIFEST_SCHEMA = vol.Schema(
    {
        vol.Optional("version"): vol.All(str, vol.Match(_VERSION_PATTERN)),
    },
    extra=vol.ALLOW_EXTRA,
)


def validate_version(integration: Integration) -> None:
    """Ensure the manifest advertises a semantic version."""

    manifest = integration.manifest
    version = manifest.get("version")
    if version is None:
        integration.add_error("manifest", "No 'version' key in the manifest file.")
        return

    try:
        CUSTOM_INTEGRATION_MANIFEST_SCHEMA(manifest)
    except vol.Invalid as err:  # pragma: no cover - schema raises in tests
        integration.add_error("manifest", str(err))


__all__ = ["CUSTOM_INTEGRATION_MANIFEST_SCHEMA", "validate_version"]
