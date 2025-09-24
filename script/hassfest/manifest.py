"""Manifest validation helpers for hassfest tests."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from .model import Integration

_VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")


def _validate_version(value: Any) -> str:
    """Validate the version string stored in the manifest."""

    if not isinstance(value, str) or not value:
        raise vol.Invalid("Integration version must be a non-empty string")
    if not _VERSION_PATTERN.fullmatch(value):
        raise vol.Invalid("Integration version must contain only digits and dots")
    return value


CUSTOM_INTEGRATION_MANIFEST_SCHEMA = vol.Schema(
    {
        vol.Required("domain"): str,
        vol.Required("documentation"): str,
        vol.Required("name"): str,
        vol.Required("codeowners"): [str],
        vol.Optional("requirements", default=list): [str],
        vol.Optional("version"): _validate_version,
    },
    extra=vol.ALLOW_EXTRA,
)


def validate_version(integration: Integration) -> bool:
    """Ensure that custom integrations include a version key."""

    if "version" not in integration.manifest:
        integration.add_error("No 'version' key in the manifest file.")
        return False
    return True


__all__ = ["CUSTOM_INTEGRATION_MANIFEST_SCHEMA", "validate_version"]
